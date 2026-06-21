"""
yfinance daily-close backfill feed — TASK_79.

Pulls daily adjusted-close history via yfinance for each enabled asset in
ref_corr_asset that has a 'yfinance:' source_spec entry.
Writes closes to hist_quote_daily (source='yfinance').
ON CONFLICT DO NOTHING (convention 1 — raw hist_* is append-only).

Usage:
    python -m etl.fetch_quotes            # incremental: only new dates
    python -m etl.fetch_quotes --full     # full history backfill
    python -m etl.fetch_quotes --symbol ^GSPC  # single yfinance ticker
    python -m etl.fetch_quotes --dry-run  # print rows, no DB write
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text

from etl._logging import setup_logging
from etl.db import session_scope

setup_logging()
log = logging.getLogger("fetch_quotes")

THROTTLE_SECONDS = 0.5  # yfinance is polite by default; small gap between tickers


def _yf_symbols(session) -> list[dict]:
    """Return list of {asset_key, yf_sym} for enabled assets with yfinance: source."""
    rows = session.execute(text("""
        SELECT asset_key, source_spec
        FROM ref_corr_asset
        WHERE enabled = TRUE
    """)).mappings().all()
    result = []
    for r in rows:
        spec = r["source_spec"] or []
        if isinstance(spec, str):
            import json
            spec = json.loads(spec)
        for entry in spec:
            if isinstance(entry, str) and entry.startswith("yfinance:"):
                sym = entry[9:]  # strip 'yfinance:' prefix
                result.append({"asset_key": r["asset_key"], "yf_sym": sym})
                break  # first yfinance: entry only
    return result


def _fetch_yfinance(yf_sym: str, full: bool) -> list[dict]:
    """Download yfinance daily adjusted closes for yf_sym.
    Returns list of {symbol, obs_date, close}.
    """
    import yfinance as yf
    import pandas as pd

    period = "max" if full else "10d"
    ticker = yf.Ticker(yf_sym)
    hist = ticker.history(period=period, auto_adjust=True)
    if hist is None or hist.empty:
        return []

    rows = []
    for dt, row in hist.iterrows():
        close_val = row.get("Close")
        if close_val is None or (hasattr(close_val, '__class__') and pd.isna(close_val)):
            continue
        try:
            obs_date = dt.date() if hasattr(dt, "date") else date.fromisoformat(str(dt)[:10])
            rows.append({
                "symbol": yf_sym,
                "obs_date": obs_date,
                "close": float(close_val),
            })
        except Exception:
            continue
    return rows


def _existing_dates(session, symbol: str) -> set:
    """Dates already in hist_quote_daily for this yfinance symbol."""
    result = session.execute(text("""
        SELECT obs_date FROM hist_quote_daily
        WHERE source = 'yfinance' AND symbol = :sym
    """), {"sym": symbol}).all()
    return {r[0] for r in result}


def _insert_rows(session, rows: list[dict]) -> int:
    """Bulk-insert with ON CONFLICT DO NOTHING; returns rows inserted."""
    if not rows:
        return 0
    inserted = 0
    for chunk in _chunks(rows, 500):
        for r in chunk:
            session.execute(text("""
                INSERT INTO hist_quote_daily (source, symbol, obs_date, close)
                VALUES ('yfinance', :sym, :d, :c)
                ON CONFLICT (source, symbol, obs_date) DO NOTHING
            """), {"sym": r["symbol"], "d": r["obs_date"], "c": r["close"]})
            inserted += 1
        session.commit()
    return inserted


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def fetch_quotes(
    full: bool = False,
    only_sym: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Main entry: pull yfinance daily closes for all enabled corr assets."""
    import time

    summary = {"symbols": 0, "rows_fetched": 0, "rows_inserted": 0, "errors": []}

    with session_scope() as s:
        asset_list = _yf_symbols(s)

    if not asset_list:
        log.warning("No enabled assets with yfinance: source_spec in ref_corr_asset.")
        return summary

    for asset in asset_list:
        yf_sym = asset["yf_sym"]
        if only_sym and yf_sym != only_sym:
            continue

        log.info("fetch_quotes: pulling yfinance '%s'", yf_sym)
        try:
            rows = _fetch_yfinance(yf_sym, full)
        except Exception as exc:
            log.error("fetch_quotes: yfinance '%s' failed: %s", yf_sym, exc)
            summary["errors"].append(yf_sym)
            time.sleep(THROTTLE_SECONDS)
            continue

        summary["rows_fetched"] += len(rows)
        log.info("fetch_quotes: '%s' -> %d rows from yfinance", yf_sym, len(rows))

        if not dry_run:
            if not full:
                with session_scope() as s:
                    existing = _existing_dates(s, yf_sym)
                rows = [r for r in rows if r["obs_date"] not in existing]

            if rows:
                with session_scope() as s:
                    inserted = _insert_rows(s, rows)
                summary["rows_inserted"] += inserted
                log.info("fetch_quotes: '%s' -> %d new rows inserted", yf_sym, inserted)
            else:
                log.info("fetch_quotes: '%s' -> no new rows (all already loaded)", yf_sym)
        else:
            log.info("fetch_quotes: dry-run '%s' -> %d rows (not written)", yf_sym, len(rows))

        summary["symbols"] += 1
        time.sleep(THROTTLE_SECONDS)

    log.info(
        "fetch_quotes: done — %d symbols, %d fetched, %d inserted, %d errors",
        summary["symbols"], summary["rows_fetched"],
        summary["rows_inserted"], len(summary["errors"])
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="yfinance daily-close backfill feed")
    ap.add_argument("--full", action="store_true",
                    help="Backfill full history (default: incremental)")
    ap.add_argument("--symbol", default=None,
                    help="Fetch a single yfinance ticker only (e.g. ^GSPC)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse rows but do not write to DB")
    args = ap.parse_args()
    result = fetch_quotes(
        full=args.full,
        only_sym=args.symbol,
        dry_run=args.dry_run,
    )
    print(result)


if __name__ == "__main__":
    main()
