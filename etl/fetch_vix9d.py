"""
VIX9D daily-close feed — feeds the Risk Dial's short_vol_disc gauge
(etl/derive_risk_dial.py) with the CBOE 9-day (short-dated) implied
volatility index, VIX9D. Same yfinance-pull mechanics as
etl/fetch_quotes.py, but a dedicated single-symbol script rather than
piggybacking on ref_corr_asset -- that table also drives the Dollar
Correlation panel's UI, and VIX9D isn't a "correlation to USD" asset;
adding it there would leak it into that unrelated panel.

Writes to hist_quote_daily (source='yfinance', symbol='^VIX9D' -- the raw
yfinance ticker, same convention as the other yfinance-sourced symbols
already in that table, e.g. '^SPX', '^GSPC'). ON CONFLICT DO NOTHING
(convention 1 -- raw hist_* is append-only).

Usage:
    python -m etl.fetch_vix9d              # incremental: only new dates
    python -m etl.fetch_vix9d --full        # full history backfill
    python -m etl.fetch_vix9d --dry-run     # print rows, no DB write
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from sqlalchemy import text

from etl._logging import setup_logging
from etl.db import session_scope

setup_logging()
log = logging.getLogger("fetch_vix9d")

YF_SYMBOL = "^VIX9D"


def _fetch_yfinance(full: bool) -> list[dict]:
    """Download yfinance daily closes for VIX9D. Returns [{symbol, obs_date, close}]."""
    import yfinance as yf
    import pandas as pd

    period = "max" if full else "10d"
    ticker = yf.Ticker(YF_SYMBOL)
    hist = ticker.history(period=period, auto_adjust=True)
    if hist is None or hist.empty:
        return []

    rows = []
    for dt, row in hist.iterrows():
        close_val = row.get("Close")
        if close_val is None or (hasattr(close_val, "__class__") and pd.isna(close_val)):
            continue
        try:
            obs_date = dt.date() if hasattr(dt, "date") else date.fromisoformat(str(dt)[:10])
            rows.append({"symbol": YF_SYMBOL, "obs_date": obs_date, "close": float(close_val)})
        except Exception:
            continue
    return rows


def _existing_dates(session) -> set:
    result = session.execute(text("""
        SELECT obs_date FROM hist_quote_daily
        WHERE source = 'yfinance' AND symbol = :sym
    """), {"sym": YF_SYMBOL}).all()
    return {r[0] for r in result}


def _insert_rows(session, rows: list[dict]) -> int:
    if not rows:
        return 0
    inserted = 0
    for r in rows:
        session.execute(text("""
            INSERT INTO hist_quote_daily (source, symbol, obs_date, close)
            VALUES ('yfinance', :sym, :d, :c)
            ON CONFLICT (source, symbol, obs_date) DO NOTHING
        """), {"sym": r["symbol"], "d": r["obs_date"], "c": r["close"]})
        inserted += 1
    session.commit()
    return inserted


def fetch_vix9d(full: bool = False, dry_run: bool = False) -> dict:
    summary = {"rows_fetched": 0, "rows_inserted": 0, "error": None}
    try:
        rows = _fetch_yfinance(full)
    except Exception as exc:
        log.error("fetch_vix9d: yfinance '%s' failed: %s", YF_SYMBOL, exc)
        summary["error"] = str(exc)
        return summary

    summary["rows_fetched"] = len(rows)
    log.info("fetch_vix9d: '%s' -> %d rows from yfinance", YF_SYMBOL, len(rows))

    if dry_run:
        log.info("fetch_vix9d: dry-run -> %d rows (not written)", len(rows))
        return summary

    if not full:
        with session_scope() as s:
            existing = _existing_dates(s)
        rows = [r for r in rows if r["obs_date"] not in existing]

    if rows:
        with session_scope() as s:
            inserted = _insert_rows(s, rows)
        summary["rows_inserted"] = inserted
        log.info("fetch_vix9d: %d new rows inserted", inserted)
    else:
        log.info("fetch_vix9d: no new rows (all already loaded)")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="VIX9D daily-close feed")
    ap.add_argument("--full", action="store_true", help="Backfill full history (default: incremental)")
    ap.add_argument("--dry-run", action="store_true", help="Parse rows but do not write to DB")
    args = ap.parse_args()
    result = fetch_vix9d(full=args.full, dry_run=args.dry_run)
    print(result)


if __name__ == "__main__":
    main()
