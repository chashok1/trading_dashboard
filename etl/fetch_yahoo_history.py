"""
etl/fetch_yahoo_history.py — TASK_133 Phase 4.2: KOSPI complex via Yahoo.

Follows the existing yfinance pattern already used by etl/yahoo_fetch.py
(lazy-import yfinance; that module's own fetchers are scoped to ref_rrt/
watchlist symbols, which these are not — Korean names + the KOSPI index
aren't tradeable positions or Hedgeye risk-range symbols, just macro-context
inputs for the korea_semis pattern). Writes daily closes into hist_macro
(source='YAHOO') alongside FRED ('FRED') and Cboe ('CBOE') series — same
table, keyed on series_id so there's no collision.

    ^KS11       KOSPI Composite (KRW; used directly for its own % change —
                a same-currency return, no FX distortion for z-scoring)
    005930.KS   Samsung Electronics (KRW) -- informational only, NOT used by
                the korea_semis pattern (spec 4.2: mixing a KRW price against
                USD instruments without dividing by KRW=X is wrong; EWY
                already embeds the currency move for a US read-through)
    000660.KS   SK hynix (KRW) -- same caveat, informational only
    EWY         iShares MSCI South Korea ETF (USD) -- the korea_semis pattern
                uses ^KS11 + EWY only, per spec

Korean holidays != US holidays: these sit on the CARRY-FORWARD side of the
derive-date model (snapshot_date <= D), same as every other hist_macro
consumer — nothing special needed here since hist_macro is read that way
everywhere already (see docs/derive_date_logic.md).

Usage:
    python -m etl.fetch_yahoo_history               # ~120 recent trading days, all 4
    python -m etl.fetch_yahoo_history --full         # full available history
    python -m etl.fetch_yahoo_history --symbol ^KS11
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime

from etl.db import insert_skip_duplicates, session_scope
from etl._logging import setup_logging

setup_logging()
log = logging.getLogger("fetch_yahoo_history")

_SYMBOLS = ["^KS11", "005930.KS", "000660.KS", "EWY"]
DEFAULT_PERIOD = "6mo"
FULL_PERIOD = "max"


def _fetch_one(symbol: str, period: str) -> list[dict]:
    import yfinance as yf
    hist = yf.Ticker(symbol).history(period=period)
    rows = []
    for idx, row in hist.iterrows():
        close = row.get("Close")
        if close is None or close != close:  # NaN guard
            continue
        rows.append({
            "series_id": symbol,
            "obs_date": idx.date(),
            "value": float(close),
            "source": "YAHOO",
        })
    return rows


def fetch_yahoo_history(full: bool = False, only: str | None = None) -> dict:
    period = FULL_PERIOD if full else DEFAULT_PERIOD
    symbols = [only] if only else _SYMBOLS
    summary = {"series": 0, "fetched": 0, "inserted": 0, "failed": []}
    with session_scope() as session:
        for sym in symbols:
            try:
                rows = _fetch_one(sym, period)
            except Exception as exc:
                log.error("fetch failed for %s: %s", sym, exc)
                summary["failed"].append(sym)
                continue
            if not rows:
                log.warning("%s: no rows parsed", sym)
                summary["series"] += 1
                continue
            attempted, inserted = insert_skip_duplicates(session, "hist_macro", rows)
            summary["series"] += 1
            summary["fetched"] += attempted
            summary["inserted"] += inserted
            log.info("%-10s fetched=%d inserted=%d (latest %s)",
                     sym, attempted, inserted, max(r["obs_date"] for r in rows))
    log.info("yahoo history fetch complete: %d series, %d fetched, %d new rows%s",
             summary["series"], summary["fetched"], summary["inserted"],
             f", {len(summary['failed'])} failed" if summary["failed"] else "")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--full", action="store_true")
    p.add_argument("--symbol", default=None)
    args = p.parse_args()
    result = fetch_yahoo_history(full=args.full, only=args.symbol)
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
