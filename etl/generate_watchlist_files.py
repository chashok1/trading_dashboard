"""
etl/generate_watchlist_files.py

Generates TOS watchlist import files from drv_symbol_tier, for
TOSDownloads/LoadWatchlists.py (Program 1, full re-import) and
TOSDownloads/ImportAdditions.py (Program 2, additions-only import) to
consume. Writes into settings.watchlist_files_dir.

2026-08-18, user-directed design (TOS-export right-sizing, no task
number). Two modes:
    daily   -- Tier 1 only, spread across WL1-WL13 (fixed range, CAP=55
               each -- up to 715 symbols; any excess goes to overflow.csv).
    weekly  -- Tier 1 + Tier 2 combined. Tier 1 -> WL1-13 as above. Tier 2
               -> WL14, WL15, ... with no upper bound -- as many WL numbers
               as needed (CAP=55 each) so every Tier 2 symbol gets a slot
               and none of them land in overflow.csv.
Both modes assign Tier 1 to the same WL1-13 range -- weekly is a full
rebuild covering everything, daily only touches WL1-13 (its own Tier 1
portion). They don't collide even though weekly also covers WL1-13,
because it's the SAME assignment for the SAME symbols, not two different
things competing for the same names.

2026-08-21, user-directed: Tier 1 range widened WL1-10 -> WL1-13 (Tier 2
not in active use yet) and Tier 2's base pushed out to WL14 accordingly --
just the two constants below, TIER1_RANGE/TIER2_BASE; the reconciliation
algorithm itself (see _reconcile_assignment) is unchanged.

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

Output files, split across two directories (2026-08-18, user-directed
relocation -- settings.watchlist_base_dir is the single reference point
both hang off of):
  output_dir (settings.watchlist_files_dir, "...\Watchlists\TOS\Watchlists"):
    WL<n>.csv       -- one per occupied WL number, plain symbol-per-line
                       (LoadWatchlists.py's expected input format).
    overflow.csv    -- symbols that qualified for this run's tier(s) but
                       had no room in their WL range. Not silently dropped.
  lists_dir (settings.watchlist_lists_dir, "...\Watchlists\TOS"):
    additions.csv   -- tos_symbol,watchlist_name for every symbol assigned
                       in this run that ISN'T already on the real TOS
                       watchlist (hist_td, today) -- ImportAdditions.py's
                       input, so a full re-import isn't needed daily.
    removals.csv    -- tos_symbol,watchlist_name for every symbol still
                       pending manual removal from TOS (ref_pending_tos_
                       removal), only written when ref_settings
                       'tos_removal_list_enabled' is true. See "REMOVAL
                       TRACKING" below -- there is no Program to auto-
                       remove a symbol from a real TOS watchlist, so this
                       is purely informational, for you to act on by hand.
All overwritten fresh each run. Row order within WL<n>.csv/additions.csv
is plain alphabetical (tried sorting dashboard-dependency symbols to the
top first, 2026-08-18, but reverted same day -- see etl/derive_symbol_
tier.py's dashboard_dependency reason instead: important tickers are
guaranteed tier=1, not specially positioned within a file).

REMOVAL TRACKING (2026-08-18, user-directed -- "sticky" TOS-removal
design): when a symbol falls out of scope (its drv_symbol_tier.tier
actually changed, or it dropped out of the tier universe entirely -- NOT
merely "this run's --mode didn't ask for it", see _reconcile_assignment),
it's recorded in ref_pending_tos_removal instead of silently vanishing.
That table auto-resolves two ways, no /ref visit ever needed:
  1. Confirmed removed: the symbol no longer appears in today's hist_td
     export -- the user actually removed it from TOS. Cleared here.
  2. Cancelled: the symbol re-qualifies for its recorded tier again
     before the user acts -- removal request withdrawn. Cleared in
     _reconcile_assignment at the point it's re-assigned.
The user never removes a symbol from ref_watchlist_assignment/TOS
manually via this table -- it's a read-only "please go remove these from
TOS" worklist, surfaced via removals.csv and (monthly, if non-empty) a
meta_warning row from etl/scheduler.py's nightly job.

Usage:
    python -m etl.generate_watchlist_files --mode daily
    python -m etl.generate_watchlist_files --mode weekly
    python -m etl.generate_watchlist_files --mode daily --output-dir C:\\some\\folder --lists-dir C:\\some\\other\\folder
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

log = logging.getLogger(__name__)

CAP = 55
TIER1_RANGE = list(range(1, 14))  # WL1..WL13, fixed
TIER2_BASE = 14                   # WL14, WL15, ... -- unbounded, extends as far as needed

MODE_TIERS = {
    "daily": (1,),
    "weekly": (1, 2),
}


def _wl_range_for_tier(tier: int):
    if tier == 1:
        return TIER1_RANGE
    return itertools.count(TIER2_BASE)  # no upper bound -- every Tier 2 symbol gets a slot


def _reconcile_assignment(session: Session, target: dict, all_tiers: dict, real_watchlist: set) -> tuple:
    """target: {tos_symbol: tier} for THIS run's --mode scope (drives what
    gets assigned a WL slot). all_tiers: {tos_symbol: tier} for the FULL
    current drv_symbol_tier, unconditional of mode -- used only to decide
    whether an existing assignment's underlying tier actually changed (a
    real transition, e.g. active_90d expired) versus this run's --mode
    simply not targeting that tier this time (e.g. a Tier 2 symbol still
    sitting from an earlier manual --mode weekly run, while the standing
    nightly job runs --mode daily). Only a real transition -- or the
    symbol dropping out of drv_symbol_tier entirely -- triggers removal
    tracking; "not in target" alone must not, or every daily-only run
    would wrongly flag every Tier 2 symbol for TOS removal.

    Returns ({tos_symbol: wl_number}, overflow_list), persisting the
    result to ref_watchlist_assignment (+ ref_pending_tos_removal for any
    symbol dropped -- see module docstring "REMOVAL TRACKING"). See module
    docstring for the stability rationale."""
    existing = {
        row[0]: (row[1], row[2])
        for row in session.execute(
            text("SELECT tos_symbol, wl_number, tier FROM ref_watchlist_assignment")
        ).fetchall()
    }

    # Drop assignments only for symbols whose tier genuinely changed (vs
    # what they were assigned under) or that dropped out of drv_symbol_tier
    # entirely -- NOT just "outside this run's --mode scope". Each dropped
    # symbol is recorded in ref_pending_tos_removal -- but ONLY if it's
    # actually on the real TOS watchlist right now (real_watchlist); a
    # symbol that only ever sat in additions.csv, never actually imported,
    # has nothing to "remove from TOS" -- flagging it anyway would also
    # immediately false-auto-confirm as "removed" next run (trivially
    # true that it's "no longer" on a watchlist it was never on).
    to_delete = [
        sym for sym, (wl, tier) in existing.items()
        if sym not in all_tiers or all_tiers[sym] != tier
    ]
    to_track = [sym for sym in to_delete if sym in real_watchlist]
    if to_track:
        session.execute(text("""
            INSERT INTO ref_pending_tos_removal (tos_symbol, wl_number, tier)
            VALUES (:tos_symbol, :wl_number, :tier)
            ON CONFLICT (tos_symbol) DO NOTHING
        """), [{"tos_symbol": sym, "wl_number": existing[sym][0], "tier": existing[sym][1]}
               for sym in to_track])
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
        # Cancel any pending removal for a symbol that re-qualified before
        # the user acted on it -- see module docstring "REMOVAL TRACKING".
        session.execute(
            text("DELETE FROM ref_pending_tos_removal WHERE tos_symbol = ANY(:syms)"),
            {"syms": [r["tos_symbol"] for r in new_rows]},
        )

    return {sym: wl for sym, (wl, _tier) in result.items()}, overflow


def generate_watchlist_files(session: Session, mode: str, output_dir: str, lists_dir: str = None) -> dict:
    """output_dir: where WL<n>.csv + overflow.csv land (settings.watchlist_files_dir).
    lists_dir: where additions.csv + removals.csv land (settings.watchlist_lists_dir) --
    2026-08-18, user-directed relocation, defaults to output_dir if not given
    (back-compat for any caller not yet passing it explicitly)."""
    if lists_dir is None:
        lists_dir = output_dir
    if mode not in MODE_TIERS:
        raise ValueError(f"Unknown mode '{mode}' -- expected one of {sorted(MODE_TIERS)}")

    anchor = session.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    if anchor is None:
        log.warning("generate_watchlist_files: no hist_td data at all -- nothing to generate")
        return {"wl_files": 0, "symbols": 0, "additions": 0, "overflow": 0,
                "removals_confirmed": 0, "removals_pending": 0, "removals_written": False}

    all_tier_rows = session.execute(text("""
        SELECT tos_symbol, tier FROM drv_symbol_tier WHERE as_of_date = :d
    """), {"d": anchor}).fetchall()
    all_tiers = {r[0]: r[1] for r in all_tier_rows}

    tiers_wanted = MODE_TIERS[mode]
    target = {sym: tier for sym, tier in all_tiers.items() if tier in tiers_wanted}

    real_watchlist = {
        r[0] for r in session.execute(
            text("SELECT DISTINCT tos_symbol FROM hist_td WHERE export_date = :d"),
            {"d": anchor},
        ).fetchall()
    }

    assignment, overflow = _reconcile_assignment(session, target, all_tiers, real_watchlist)

    by_wl: dict = {}
    for sym, wl in assignment.items():
        by_wl.setdefault(wl, []).append(sym)

    os.makedirs(output_dir, exist_ok=True)
    for wl, syms in by_wl.items():
        path = os.path.join(output_dir, f"WL{wl}.csv")
        with open(path, "w", newline="") as f:
            for s in sorted(syms):
                f.write(s + "\n")

    os.makedirs(lists_dir, exist_ok=True)
    additions = sorted(
        (sym, f"WL{wl}") for sym, wl in assignment.items() if sym not in real_watchlist
    )
    with open(os.path.join(lists_dir, "additions.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tos_symbol", "watchlist_name"])
        w.writerows(additions)

    with open(os.path.join(output_dir, "overflow.csv"), "w", newline="") as f:
        for s in sorted(overflow):
            f.write(s + "\n")

    # REMOVAL TRACKING, part 2: confirm or keep each pending removal.
    # Confirmed (symbol no longer in today's real TOS watchlist -- the
    # user actually removed it) -> clear the pending-removal row. Still
    # present -> leave it pending, surfaced in removals.csv below.
    pending = session.execute(text(
        "SELECT tos_symbol, wl_number FROM ref_pending_tos_removal"
    )).fetchall()
    confirmed = [sym for sym, _wl in pending if sym not in real_watchlist]
    if confirmed:
        session.execute(
            text("DELETE FROM ref_pending_tos_removal WHERE tos_symbol = ANY(:syms)"),
            {"syms": confirmed},
        )
    # wl_number=0 is the backfill sentinel for symbols that fell out of
    # scope before this feature existed -- their original watchlist name
    # was never recorded (predates ref_pending_tos_removal), so it's
    # genuinely unknown rather than a real WL slot.
    still_pending = sorted(
        (sym, f"WL{wl}" if wl else "UNKNOWN (check manually)")
        for sym, wl in pending if sym not in confirmed
    )

    removal_toggle = session.execute(text(
        "SELECT setting_value FROM ref_settings WHERE setting_name = 'tos_removal_list_enabled'"
    )).scalar()
    removal_list_written = (removal_toggle or "").strip().lower() == "true"
    if removal_list_written:
        with open(os.path.join(lists_dir, "removals.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["tos_symbol", "watchlist_name"])
            w.writerows(still_pending)

    result = {
        "wl_files": len(by_wl),
        "symbols": len(assignment),
        "additions": len(additions),
        "overflow": len(overflow),
        "removals_confirmed": len(confirmed),
        "removals_pending": len(still_pending),
        "removals_written": removal_list_written,
    }
    log.info("generate_watchlist_files: mode=%s anchor=%s -> %s", mode, anchor, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(MODE_TIERS), default="daily")
    parser.add_argument("--output-dir", default=None,
                         help="WL<n>.csv + overflow.csv location. Defaults to settings.watchlist_files_dir")
    parser.add_argument("--lists-dir", default=None,
                         help="additions.csv + removals.csv location. Defaults to settings.watchlist_lists_dir")
    args = parser.parse_args()

    output_dir = args.output_dir or settings.watchlist_files_dir
    lists_dir = args.lists_dir or settings.watchlist_lists_dir
    with session_scope() as session:
        result = generate_watchlist_files(session, args.mode, output_dir, lists_dir)
    print(f"mode={args.mode} output_dir={output_dir} lists_dir={lists_dir}")
    print(result)


if __name__ == "__main__":
    main()
