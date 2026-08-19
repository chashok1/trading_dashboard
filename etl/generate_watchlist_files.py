"""
etl/generate_watchlist_files.py

Generates TOS watchlist import files from drv_symbol_tier, for
TOSDownloads/LoadWatchlists.py (Program 1, full re-import) and
TOSDownloads/ImportAdditions.py (Program 2, additions-only import) to
consume. Writes into settings.watchlist_files_dir.

2026-08-18, user-directed design (TOS-export right-sizing, no task
number). Two modes:
    daily   -- Tier 1 only, spread across WL1-WL10 (fixed range, CAP=55
               each -- up to 550 symbols; any excess goes to overflow.csv).
    weekly  -- Tier 1 + Tier 2 combined. Tier 1 -> WL1-10 as above. Tier 2
               -> WL11, WL12, ... with no upper bound -- as many WL numbers
               as needed (CAP=55 each) so every Tier 2 symbol gets a slot
               and none of them land in overflow.csv.
Both modes assign Tier 1 to the same WL1-10 range -- weekly is a full
rebuild covering everything, daily only touches WL1-10 (its own Tier 1
portion). They don't collide even though weekly also covers WL1-10,
because it's the SAME assignment for the SAME symbols, not two different
things competing for the same names.

STABILITY: symbol -> WL-number assignment is persisted in
ref_watchlist_assignment, not recomputed from scratch (e.g. by sorting the
current symbol set and chunking into groups of 55) every run. Plain
alphabetical chunking looks simple but isn't stable -- inserting one new
symbol shifts every subsequent symbol's chunk boundary, so nearly the
whole list would look like it "moved" to a different WL number every time
membership changes even slightly, making the additions file meaningless
noise instead of a real delta. Reconciliation each run:
  1. Any symbol already assigned AND still in this run's target scope (same
     tier) keeps its existing wl_number -- untouched.
  2. Any symbol assigned but no longer in scope (demoted, or tier changed)
     has its assignment deleted, freeing that slot.
  3. Any symbol newly in scope gets the first wl_number in its tier's range
     that currently has room (< CAP occupants) -- in alphabetical order,
     so which specific new symbol claims which specific slot is still
     deterministic even though it's no longer position-based.
  4. A symbol with nowhere to go (its whole tier range is full) is written
     to overflow.csv instead of silently dropped or exceeding the cap.

Output files (all in the target output_dir, overwritten fresh each run).
Row order within WL<n>.csv/additions.csv (2026-08-18, user-directed):
dashboard-dependency symbols (indexes/RRT-benchmarks/sector ETFs -- same
set _fetch_dashboard_dependency() computes for tiering) sort first, then
everything else alphabetically -- so the important tickers are visible at
the top of each imported TOS watchlist page instead of buried mid-list.
    WL<n>.csv       -- one per occupied WL number, plain symbol-per-line
                       (LoadWatchlists.py's expected input format).
    additions.csv   -- tos_symbol,watchlist_name for every symbol assigned
                       in this run that ISN'T already on the real TOS
                       watchlist (hist_td, today) -- ImportAdditions.py's
                       input, so a full re-import isn't needed daily.
    overflow.csv    -- symbols that qualified for this run's tier(s) but
                       had no room in their WL range. Not silently dropped.

Usage:
    python -m etl.generate_watchlist_files --mode daily
    python -m etl.generate_watchlist_files --mode weekly
    python -m etl.generate_watchlist_files --mode daily --output-dir C:\\some\\folder
"""
from __future__ import annotations

import argparse
import csv
import itertools
import logging
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import settings
from etl.db import session_scope
from etl.derive_symbol_tier import _fetch_dashboard_dependency

log = logging.getLogger(__name__)

CAP = 55
TIER1_RANGE = list(range(1, 11))  # WL1..WL10, fixed
TIER2_BASE = 11                   # WL11, WL12, ... -- unbounded, extends as far as needed

MODE_TIERS = {
    "daily": (1,),
    "weekly": (1, 2),
}


def _wl_range_for_tier(tier: int):
    if tier == 1:
        return TIER1_RANGE
    return itertools.count(TIER2_BASE)  # no upper bound -- every Tier 2 symbol gets a slot


_SPECIAL_CHARS = (":", "/", "=")  # futures (/GC), RR-index codes (TNX:CGI), etc.


def _importance_sort_key(important: set):
    """2026-08-18: user asked that indexes/RRT/sector benchmarks -- the same
    'dashboard_dependency' set used for tiering -- sort to the top of each
    output file, with everything else alphabetical after. Also (same day,
    follow-up): symbols carrying a ':', '/', or '=' -- futures (/GC, /BTC),
    RR-index codes (TNX:CGI, MOVE:GIF) -- sort to that same top group even
    if not already in `important`, since their non-standard format is
    itself a signal they're an index/benchmark, not a plain equity. Returns
    a key function: (0, symbol) sorts before (1, symbol), alphabetical
    within each group."""
    def key(sym: str):
        is_top = sym in important or any(c in sym for c in _SPECIAL_CHARS)
        return (0 if is_top else 1, sym)
    return key


def _reconcile_assignment(session: Session, target: dict) -> tuple:
    """target: {tos_symbol: tier}. Returns ({tos_symbol: wl_number}, overflow_list),
    persisting the result to ref_watchlist_assignment. See module docstring
    for the stability rationale."""
    existing = {
        row[0]: (row[1], row[2])
        for row in session.execute(
            text("SELECT tos_symbol, wl_number, tier FROM ref_watchlist_assignment")
        ).fetchall()
    }

    # Drop assignments for symbols no longer in scope, or whose tier changed
    # (a tier change re-enters the "new symbol" path below, so it can land
    # in the correct range instead of keeping a stale one).
    to_delete = [
        sym for sym, (wl, tier) in existing.items()
        if sym not in target or tier != target[sym]
    ]
    if to_delete:
        session.execute(
            text("DELETE FROM ref_watchlist_assignment WHERE tos_symbol = ANY(:syms)"),
            {"syms": to_delete},
        )
        for sym in to_delete:
            del existing[sym]

    occupancy: dict = {}
    for sym, (wl, tier) in existing.items():
        occupancy[wl] = occupancy.get(wl, 0) + 1

    result = dict(existing)  # sym -> (wl, tier), kept assignments so far
    new_rows = []
    overflow = []
    for sym in sorted(target):
        if sym in result:
            continue
        tier = target[sym]
        assigned_wl = None
        for wl in _wl_range_for_tier(tier):
            if occupancy.get(wl, 0) < CAP:
                assigned_wl = wl
                break
        if assigned_wl is None:
            overflow.append(sym)
            continue
        occupancy[assigned_wl] = occupancy.get(assigned_wl, 0) + 1
        result[sym] = (assigned_wl, tier)
        new_rows.append({"tos_symbol": sym, "wl_number": assigned_wl, "tier": tier})

    if new_rows:
        session.execute(text("""
            INSERT INTO ref_watchlist_assignment (tos_symbol, wl_number, tier)
            VALUES (:tos_symbol, :wl_number, :tier)
            ON CONFLICT (tos_symbol) DO UPDATE
                SET wl_number = EXCLUDED.wl_number,
                    tier = EXCLUDED.tier,
                    assigned_at = NOW()
        """), new_rows)

    return {sym: wl for sym, (wl, _tier) in result.items()}, overflow


def generate_watchlist_files(session: Session, mode: str, output_dir: str) -> dict:
    if mode not in MODE_TIERS:
        raise ValueError(f"Unknown mode '{mode}' -- expected one of {sorted(MODE_TIERS)}")

    anchor = session.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    if anchor is None:
        log.warning("generate_watchlist_files: no hist_td data at all -- nothing to generate")
        return {"wl_files": 0, "symbols": 0, "additions": 0, "overflow": 0}

    tiers_wanted = MODE_TIERS[mode]
    tier_rows = session.execute(text("""
        SELECT tos_symbol, tier FROM drv_symbol_tier
        WHERE as_of_date = :d AND tier = ANY(:tiers)
    """), {"d": anchor, "tiers": list(tiers_wanted)}).fetchall()
    target = {r[0]: r[1] for r in tier_rows}

    assignment, overflow = _reconcile_assignment(session, target)
    important = _fetch_dashboard_dependency(session)
    sort_key = _importance_sort_key(important)

    by_wl: dict = {}
    for sym, wl in assignment.items():
        by_wl.setdefault(wl, []).append(sym)

    os.makedirs(output_dir, exist_ok=True)
    for wl, syms in by_wl.items():
        path = os.path.join(output_dir, f"WL{wl}.csv")
        with open(path, "w", newline="") as f:
            for s in sorted(syms, key=sort_key):
                f.write(s + "\n")

    real_watchlist = {
        r[0] for r in session.execute(
            text("SELECT DISTINCT tos_symbol FROM hist_td WHERE export_date = :d"),
            {"d": anchor},
        ).fetchall()
    }
    additions = sorted(
        ((sym, f"WL{wl}") for sym, wl in assignment.items() if sym not in real_watchlist),
        key=lambda row: sort_key(row[0]),
    )
    with open(os.path.join(output_dir, "additions.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tos_symbol", "watchlist_name"])
        w.writerows(additions)

    with open(os.path.join(output_dir, "overflow.csv"), "w", newline="") as f:
        for s in sorted(overflow):
            f.write(s + "\n")

    result = {
        "wl_files": len(by_wl),
        "symbols": len(assignment),
        "additions": len(additions),
        "overflow": len(overflow),
    }
    log.info("generate_watchlist_files: mode=%s anchor=%s -> %s", mode, anchor, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(MODE_TIERS), default="daily")
    parser.add_argument("--output-dir", default=None,
                         help="Defaults to settings.watchlist_files_dir")
    args = parser.parse_args()

    output_dir = args.output_dir or settings.watchlist_files_dir
    with session_scope() as session:
        result = generate_watchlist_files(session, args.mode, output_dir)
    print(f"mode={args.mode} output_dir={output_dir}")
    print(result)


if __name__ == "__main__":
    main()
