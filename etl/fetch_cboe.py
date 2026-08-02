"""
Cboe free CSV feed (TASK_133 Phase 4.3) — VVIX + RVOL, no API key/registration.

Both are `DATE,<VALUE>` two-column CSVs, close only, decades of history.
Writes to hist_macro with source='CBOE' (same table FRED writes to, keyed on
series_id so 'VVIX'/'RVOL' don't collide with any FRED series id).

  VVIX  https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv
        ref_vol_threshold already has a VVIX row (100/150) with no feed behind it.
  RVOL  https://cdn.cboe.com/api/global/us_indices/daily_prices/RVOL_History.csv
        Independent cross-check on the Phase 3 Yang-Zhang calc (drv_market_stat.rv21).

Usage:
    python -m etl.fetch_cboe               # incremental (last ~120 obs) for both
    python -m etl.fetch_cboe --full        # full history (first backfill)
    python -m etl.fetch_cboe --series VVIX

Not wired into etl/scheduler.py (a pull, not a watched file drop) — same
convention as etl/fetch_macro.py. An unavailable CDN must not fail the
derive: every fetch is wrapped in try/except and logged to meta_macro_fetch.
"""
from __future__ import annotations

import argparse
import logging
import urllib.request
from datetime import datetime

from etl.db import insert_skip_duplicates, session_scope
from etl._logging import setup_logging

setup_logging()
log = logging.getLogger("fetch_cboe")

REQUEST_TIMEOUT = 30
DEFAULT_RECENT_ROWS = 120

_SOURCES = {
    "VVIX": "https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv",
    "RVOL": "https://cdn.cboe.com/api/global/us_indices/daily_prices/RVOL_History.csv",
}


def _fetch_csv(series_id: str, url: str, full: bool, recent: int) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "trading-dashboard/cboe"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        text_body = resp.read().decode("utf-8")

    lines = [ln.strip() for ln in text_body.splitlines() if ln.strip()]
    if not lines:
        return []
    rows: list[dict] = []
    for ln in lines[1:]:  # skip header "DATE,<SERIES>"
        parts = ln.split(",")
        if len(parts) < 2:
            continue
        try:
            obs_date = datetime.strptime(parts[0].strip(), "%m/%d/%Y").date()
            value = float(parts[1].strip())
        except (ValueError, IndexError):
            continue
        rows.append({"series_id": series_id, "obs_date": obs_date,
                     "value": value, "source": "CBOE"})
    if not full:
        rows = sorted(rows, key=lambda r: r["obs_date"], reverse=True)[:recent]
    return rows


def _log_run(session, started_at, status: str, series_ok: int,
             series_failed: int, rows_inserted: int, note: str | None = None) -> None:
    from sqlalchemy import text as _text
    session.execute(_text("""
        INSERT INTO meta_macro_fetch
            (started_at, finished_at, trigger, status,
             series_ok, series_failed, rows_inserted, note)
        VALUES (:s, now(), 'cboe_cli', :st, :ok, :fl, :ri, :n)
    """), {"s": started_at, "st": status, "ok": series_ok,
           "fl": series_failed, "ri": rows_inserted, "n": note})


def fetch_cboe(full: bool = False, only: str | None = None,
              recent: int = DEFAULT_RECENT_ROWS) -> dict:
    started_at = datetime.now()
    series_ids = [only.upper()] if only else list(_SOURCES.keys())
    summary = {"series": 0, "fetched": 0, "inserted": 0, "failed": []}

    with session_scope() as session:
        for sid in series_ids:
            url = _SOURCES.get(sid)
            if url is None:
                log.error("unknown Cboe series %r (known: %s)", sid, list(_SOURCES))
                summary["failed"].append(sid)
                continue
            try:
                rows = _fetch_csv(sid, url, full, recent)
            except Exception as exc:  # CDN unavailable must not fail the derive
                log.error("fetch failed for %s: %s", sid, exc)
                summary["failed"].append(sid)
                continue
            if not rows:
                log.warning("%s: no observations parsed", sid)
                summary["series"] += 1
                continue
            attempted, inserted = insert_skip_duplicates(session, "hist_macro", rows)
            summary["series"] += 1
            summary["fetched"] += attempted
            summary["inserted"] += inserted
            log.info("%-6s fetched=%d inserted=%d (latest %s)",
                     sid, attempted, inserted, max(r["obs_date"] for r in rows))

        n_failed = len(summary["failed"])
        status = ("error" if summary["series"] == 0 and n_failed
                  else "partial" if n_failed else "ok")
        note = ("failed: " + ",".join(summary["failed"])) if n_failed else None
        _log_run(session, started_at, status, summary["series"], n_failed,
                 summary["inserted"], note)

    log.info("cboe fetch complete: %d series, %d obs fetched, %d new rows%s",
             summary["series"], summary["fetched"], summary["inserted"],
             f", {n_failed} failed" if summary["failed"] else "")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--full", action="store_true", help="fetch full available history")
    p.add_argument("--series", default=None, help="VVIX or RVOL only")
    p.add_argument("--recent", type=int, default=DEFAULT_RECENT_ROWS)
    args = p.parse_args()
    result = fetch_cboe(full=args.full, only=args.series, recent=args.recent)
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
