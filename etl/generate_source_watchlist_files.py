"""
etl/generate_source_watchlist_files.py

Generates ONE watchlist file per outlook/signal SOURCE (PS, ETF, II, RR,
CALL, SSS -- ref_outlook_source.source_code), in both TOS format (plain
symbol-per-line, same convention as WL<n>.csv) and Yahoo Finance
import-CSV format -- "what does this feed currently cover", independent of
held positions or account.

2026-08-24, user-directed. Two membership rules, by source:
  - RR / CALL / ETF / II: Bullish only. Read from drv_outlooks (already
    anchored + carry-forward'd per the periodic-feed convention --
    docs/derive_date_logic.md), filtered on that source's own outlook
    column. II's vocabulary includes 'Long' as well as 'Bullish' in some
    snapshots -- treated as bullish-equivalent.
  - PS / SSS: no outlook/direction concept exists for these two (PS is
    ref_outlook_source.base_weight_method='rank', not an outlook; SSS has
    no source column here beyond sss_signal_sign, and the user explicitly
    said "include all ranked PS symbols and SSS symbols" -- no Bullish
    filter). Read directly from hist_ps / hist_sss's own latest snapshot
    <= anchor (periodic-feed convention), since neither has a plain
    membership flag surfaced in drv_outlooks.

Output, both overwritten fresh each run, symbols sorted alphabetically:
  tos_dir (settings.source_tos_watch_lists_dir)/<source_code>.csv
      One tos_symbol per line.
  y_dir (settings.source_y_watch_lists_dir)/<source_code>.csv
      Yahoo Finance portfolio-import CSV: header row
      Symbol,Name,Quantity,Purchase Date,Purchase Price -- only Symbol is
      filled. RR (and occasionally CALL) can include macro/FX/futures
      instruments, not just stocks -- those TOS-internal codes ($COMP,
      /6E, /BTC, DXY, ...) are translated to their real Yahoo ticker via
      ref_rrt.y_ticker before writing (see _yahoo_ticker_map); the TOS
      file keeps the raw tos_symbol unchanged since TOS understands its
      own codes natively.

Usage:
    python -m etl.generate_source_watchlist_files
    python -m etl.generate_source_watchlist_files --tos-dir C:\\some\\folder --y-dir C:\\some\\other\\folder
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

# Bullish-outlook sources, read from drv_outlooks (already anchored/carried
# forward): source_code -> SQL boolean expression over drv_outlooks columns.
_OUTLOOK_BULLISH_FILTER = {
    "RR":   "rr_outlook ILIKE 'BULLISH'",
    "CALL": "call_outlook ILIKE 'BULLISH'",
    "ETF":  "etf_outlook ILIKE 'BULLISH'",
    "II":   "(ii_outlook ILIKE 'BULLISH' OR ii_outlook ILIKE 'LONG')",
}

# Membership-only sources (no Bullish/Bearish concept) -- read from their
# own raw hist_* table's latest snapshot <= anchor, all rows included.
_RAW_MEMBERSHIP_TABLE = {
    "PS":  {"table": "hist_ps",  "symbol_col": "COALESCE(NULLIF(tos_symbol, ''), ticker)"},
    "SSS": {"table": "hist_sss", "symbol_col": "COALESCE(NULLIF(tos_symbol, ''), symbol)"},
}

SOURCES = list(_OUTLOOK_BULLISH_FILTER) + list(_RAW_MEMBERSHIP_TABLE)


def _outlook_symbols(session: Session, source_code: str, anchor) -> set:
    filt = _OUTLOOK_BULLISH_FILTER[source_code]
    rows = session.execute(text(f"""
        SELECT DISTINCT tos_symbol FROM drv_outlooks
        WHERE as_of_date = :anchor AND {filt}
    """), {"anchor": anchor}).fetchall()
    return {r[0] for r in rows if r[0]}


def _raw_membership_symbols(session: Session, source_code: str, anchor) -> set:
    cfg = _RAW_MEMBERSHIP_TABLE[source_code]
    table, symbol_col = cfg["table"], cfg["symbol_col"]
    latest = session.execute(text(
        f"SELECT MAX(snapshot_date) FROM {table} WHERE snapshot_date <= :anchor"
    ), {"anchor": anchor}).scalar()
    if latest is None:
        return set()
    rows = session.execute(text(
        f"SELECT DISTINCT {symbol_col} AS sym FROM {table} WHERE snapshot_date = :d"
    ), {"d": latest}).fetchall()
    return {r[0] for r in rows if r[0]}


def _yahoo_ticker_map(session: Session) -> dict:
    """tos_ticker -> y_ticker from ref_rrt, for RR/CALL's macro/FX/futures
    codes ($COMP, /6E, /BTC, DXY, ...) that aren't themselves valid Yahoo
    tickers -- same approach as web/_common.js's dashboard Yahoo links.
    Anything not in this map (plain stock/ETF tickers) is already a valid
    Yahoo ticker as-is."""
    rows = session.execute(text(
        "SELECT tos_ticker, y_ticker FROM ref_rrt WHERE tos_ticker IS NOT NULL AND y_ticker IS NOT NULL"
    )).fetchall()
    return {r[0]: r[1] for r in rows}


def generate_source_watchlist_files(session: Session, tos_dir: str, y_dir: str) -> dict:
    anchor = session.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    if anchor is None:
        log.warning("generate_source_watchlist_files: no hist_td data at all -- nothing to generate")
        return {"sources": 0, "symbols": 0, "empty": []}

    yahoo_map = _yahoo_ticker_map(session)
    os.makedirs(tos_dir, exist_ok=True)
    os.makedirs(y_dir, exist_ok=True)

    result = {"sources": 0, "symbols": 0, "empty": []}
    for source_code in SOURCES:
        if source_code in _OUTLOOK_BULLISH_FILTER:
            symbols = _outlook_symbols(session, source_code, anchor)
        else:
            symbols = _raw_membership_symbols(session, source_code, anchor)

        ordered = sorted(symbols)
        with open(os.path.join(tos_dir, f"{source_code}.csv"), "w", newline="") as f:
            for s in ordered:
                f.write(s + "\n")
        with open(os.path.join(y_dir, f"{source_code}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(YAHOO_HEADER)
            for s in ordered:
                w.writerow([yahoo_map.get(s, s), "", "", "", ""])

        result["sources"] += 1
        result["symbols"] += len(ordered)
        if not ordered:
            result["empty"].append(source_code)

    log.info("generate_source_watchlist_files: anchor=%s -> %s", anchor, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tos-dir", default=None,
                         help="Per-source TOS-format .csv location. Defaults to settings.source_tos_watch_lists_dir")
    parser.add_argument("--y-dir", default=None,
                         help="Per-source Yahoo-format .csv location. Defaults to settings.source_y_watch_lists_dir")
    args = parser.parse_args()

    tos_dir = args.tos_dir or settings.source_tos_watch_lists_dir
    y_dir = args.y_dir or settings.source_y_watch_lists_dir
    with session_scope() as session:
        result = generate_source_watchlist_files(session, tos_dir, y_dir)
    print(f"tos_dir={tos_dir} y_dir={y_dir}")
    print(result)


if __name__ == "__main__":
    main()
