"""
Monthly Yahoo pull of period-start closes (for the Macro Rail MTD% / QTD% / YTD%).

For every symbol in the Major Markets (top9) and Sectors (sector_etfs) rail areas,
stores the last close BEFORE the start of the current month, quarter and year in
ref_perf_base. The API then computes  (last_price / base_close - 1) * 100.

Closes are unadjusted (auto_adjust=False) so they match the TOS prices the rail shows.
Run by etl/scheduler.py once per calendar month (maybe_run_perf_base_fetch), or by hand:

    python -m etl.fetch_perf_base [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from sqlalchemy import text

from etl._logging import setup_logging
from etl.db import session_scope

setup_logging()
log = logging.getLogger("fetch_perf_base")

PERF_AREAS = ("top9", "sector_etfs")
# tos_ticker -> Yahoo ticker where ref_rrt is missing or uses a non-Yahoo name
_YAHOO_OVERRIDE = {"^SPX": "^GSPC", "SPX": "^GSPC", "$DJI": "^DJI", "$COMP": "^IXIC",
                   "RUT": "^RUT", "$DXY": "DX-Y.NYB"}


def period_starts(today: date) -> dict:
    q_month = 3 * ((today.month - 1) // 3) + 1
    return {"month": today.replace(day=1), "quarter": date(today.year, q_month, 1),
            "year": date(today.year, 1, 1)}


def _yahoo_ticker(session, sym: str) -> str:
    if sym in _YAHOO_OVERRIDE:
        return _YAHOO_OVERRIDE[sym]
    y = session.execute(text(
        "SELECT y_ticker FROM ref_rrt WHERE tos_ticker = :s AND y_ticker IS NOT NULL "
        "ORDER BY preferred_display DESC NULLS LAST LIMIT 1"), {"s": sym}).scalar()
    y = y or sym
    return _YAHOO_OVERRIDE.get(y, y)


def _last_close_before(hist, start: date):
    """(date, close) of the last bar strictly before `start`, else (None, None)."""
    best = (None, None)
    for dt, row in hist.iterrows():
        d = dt.date() if hasattr(dt, "date") else date.fromisoformat(str(dt)[:10])
        if d < start and row.get("Close") == row.get("Close"):   # NaN check
            best = (d, float(row["Close"]))
    return best


def fetch_perf_base(dry_run: bool = False, today: date | None = None) -> dict:
    import yfinance as yf
    today = today or date.today()
    starts = period_starts(today)
    summary = {"symbols": 0, "ok": 0, "errors": []}
    with session_scope() as s:
        syms = [r[0] for r in s.execute(text(
            "SELECT DISTINCT member_symbol FROM ref_macro_area "
            "WHERE area_key = ANY(:a)"), {"a": list(PERF_AREAS)}).all()]
        summary["symbols"] = len(syms)
        for sym in syms:
            yt = _yahoo_ticker(s, sym)
            try:
                hist = yf.Ticker(yt).history(start=starts["year"] - timedelta(days=10),
                                             end=today + timedelta(days=1), auto_adjust=False)
                if hist is None or hist.empty:
                    raise ValueError("no data")
                vals = {k: _last_close_before(hist, v) for k, v in starts.items()}
                if dry_run:
                    log.info("%s (%s): %s", sym, yt, vals)
                    continue
                s.execute(text("""
                    INSERT INTO ref_perf_base (tos_symbol, y_ticker,
                        month_base_date, month_base_close, quarter_base_date, quarter_base_close,
                        year_base_date, year_base_close, fetched_at)
                    VALUES (:s, :y, :md, :mc, :qd, :qc, :yd, :yc, now())
                    ON CONFLICT (tos_symbol) DO UPDATE SET
                        y_ticker = EXCLUDED.y_ticker,
                        month_base_date = EXCLUDED.month_base_date, month_base_close = EXCLUDED.month_base_close,
                        quarter_base_date = EXCLUDED.quarter_base_date, quarter_base_close = EXCLUDED.quarter_base_close,
                        year_base_date = EXCLUDED.year_base_date, year_base_close = EXCLUDED.year_base_close,
                        fetched_at = now()"""),
                    {"s": sym, "y": yt, "md": vals["month"][0], "mc": vals["month"][1],
                     "qd": vals["quarter"][0], "qc": vals["quarter"][1],
                     "yd": vals["year"][0], "yc": vals["year"][1]})
                summary["ok"] += 1
            except Exception as e:   # one bad ticker must not stop the rest
                summary["errors"].append(f"{sym}({yt}): {e}")
                log.warning("perf base %s (%s) failed: %s", sym, yt, e)
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    print(fetch_perf_base(dry_run=ap.parse_args().dry_run))
