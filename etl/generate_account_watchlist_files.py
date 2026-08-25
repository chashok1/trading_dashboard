"""
etl/generate_account_watchlist_files.py

Generates ONE watchlist file per active account (ref_accounts.short_name),
in both TOS format (plain symbol-per-line, same convention as WL<n>.csv)
and Yahoo Finance import-CSV format -- the held-positions counterpart to
etl/generate_watchlist_files.py's tier-based WL<n>.csv files.

2026-08-24, user-directed ("generate account watchlists for all accounts
every night, for both yahoo and TOS"). Design decisions from that
conversation:
  - Symbol scope: HELD POSITIONS ONLY for that account (not the broader
    tracked/tier universe -- drv_symbol_tier isn't account-scoped).
  - One file per account, named <short_name>.csv (e.g. F-A.csv, HSA.csv).
  - Inactive accounts (ref_accounts.is_active=FALSE, e.g. the 401k) are
    skipped -- same convention every other rollup/derive in the app uses.

Grouped by short_name, NOT by raw account_number/account row: several raw
labels can map to the same logical account (a broker renaming an account's
export label mid-history -- see db/baseline.sql's 2026-08-24 comment on the
Schwab HSA_Brokerage -> HSA rename). Within a short_name group, only the
CURRENTLY ACTIVE label's positions are used: found by taking the latest
snapshot_date <= anchor across every raw label in the group, which lands on
whichever label the broker is presently using (a retired label's own
latest date is always older -- confirmed no overlap for the HSA case).

Output, both overwritten fresh each run, symbols sorted alphabetically:
  tos_dir (settings.account_tos_watch_lists_dir)/<short_name>.csv
      One tos_symbol per line (LoadWatchlists.py-compatible format).
  y_dir (settings.account_y_watch_lists_dir)/<short_name>.csv
      Yahoo Finance portfolio-import CSV: header row
      Symbol,Name,Quantity,Purchase Date,Purchase Price -- only Symbol is
      filled (watchlist import, not cost-basis/lot tracking).

Cash rows (SPAXX**, "Cash & Cash Investments", money-market sweep, etc.)
are excluded via the same is_cash() DB function used everywhere else in
the app (db/baseline.sql).

Usage:
    python -m etl.generate_account_watchlist_files
    python -m etl.generate_account_watchlist_files --tos-dir C:\\some\\folder --y-dir C:\\some\\other\\folder
"""
from __future__ import annotations

import argparse
import csv
import logging
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import settings
from etl.db import session_scope

log = logging.getLogger(__name__)

YAHOO_HEADER = ["Symbol", "Name", "Quantity", "Purchase Date", "Purchase Price"]


def _held_symbols_for_group(session: Session, source: str, account_numbers: list, anchor) -> set:
    """Held, non-cash tos_symbols for one short_name group's accounts of a
    single source (F or CS), as of the latest snapshot <= anchor across the
    WHOLE group -- see module docstring for why grouping (not per-label)
    matters for a renamed account."""
    if not account_numbers:
        return set()
    if source == "F":
        latest = session.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_f
            WHERE account_number = ANY(:accts) AND snapshot_date <= :anchor
        """), {"accts": account_numbers, "anchor": anchor}).scalar()
        if latest is None:
            return set()
        rows = session.execute(text("""
            SELECT DISTINCT COALESCE(NULLIF(tos_symbol, ''), symbol) AS sym
            FROM hist_f
            WHERE account_number = ANY(:accts) AND snapshot_date = :d
              AND NOT is_cash(COALESCE(NULLIF(tos_symbol, ''), symbol), type, description)
        """), {"accts": account_numbers, "d": latest}).fetchall()
    else:  # CS
        latest = session.execute(text("""
            SELECT MAX(snapshot_date) FROM hist_cs
            WHERE account = ANY(:accts) AND snapshot_date <= :anchor
        """), {"accts": account_numbers, "anchor": anchor}).scalar()
        if latest is None:
            return set()
        rows = session.execute(text("""
            SELECT DISTINCT COALESCE(NULLIF(tos_symbol, ''), symbol) AS sym
            FROM hist_cs
            WHERE account = ANY(:accts) AND snapshot_date = :d
              AND NOT is_cash(COALESCE(NULLIF(tos_symbol, ''), symbol), security_type, description)
        """), {"accts": account_numbers, "d": latest}).fetchall()
    return {r[0] for r in rows if r[0]}


def generate_account_watchlist_files(session: Session, tos_dir: str, y_dir: str) -> dict:
    anchor = session.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    if anchor is None:
        log.warning("generate_account_watchlist_files: no hist_td data at all -- nothing to generate")
        return {"accounts": 0, "symbols": 0, "empty": []}

    rows = session.execute(text("""
        SELECT short_name, source, account_number
        FROM ref_accounts
        WHERE is_active = TRUE AND short_name IS NOT NULL AND short_name <> ''
        ORDER BY short_name
    """)).fetchall()

    groups: dict = {}
    for short_name, source, account_number in rows:
        groups.setdefault(short_name, {}).setdefault(source, []).append(account_number)

    os.makedirs(tos_dir, exist_ok=True)
    os.makedirs(y_dir, exist_ok=True)

    result = {"accounts": 0, "symbols": 0, "empty": []}
    for short_name in sorted(groups):
        symbols = set()
        for source, account_numbers in groups[short_name].items():
            symbols |= _held_symbols_for_group(session, source, account_numbers, anchor)

        ordered = sorted(symbols)
        with open(os.path.join(tos_dir, f"{short_name}.csv"), "w", newline="") as f:
            for s in ordered:
                f.write(s + "\n")
        with open(os.path.join(y_dir, f"{short_name}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(YAHOO_HEADER)
            for s in ordered:
                w.writerow([s, "", "", "", ""])

        result["accounts"] += 1
        result["symbols"] += len(ordered)
        if not ordered:
            result["empty"].append(short_name)

    log.info("generate_account_watchlist_files: anchor=%s -> %s", anchor, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tos-dir", default=None,
                         help="Per-account TOS-format .csv location. Defaults to settings.account_tos_watch_lists_dir")
    parser.add_argument("--y-dir", default=None,
                         help="Per-account Yahoo-format .csv location. Defaults to settings.account_y_watch_lists_dir")
    args = parser.parse_args()

    tos_dir = args.tos_dir or settings.account_tos_watch_lists_dir
    y_dir = args.y_dir or settings.account_y_watch_lists_dir
    with session_scope() as session:
        result = generate_account_watchlist_files(session, tos_dir, y_dir)
    print(f"tos_dir={tos_dir} y_dir={y_dir}")
    print(result)


if __name__ == "__main__":
    main()
