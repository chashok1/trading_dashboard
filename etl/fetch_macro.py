"""
Macro feed — pull economic data + EOD index levels from the FRED API.

FRED (Federal Reserve Economic Data, St. Louis Fed) is free; get a key at
https://fred.stlouisfed.org/docs/api/api_key.html and put it in .env as
    FRED_API_KEY=...

This is the one ingest path that is a *pull* rather than a watched file drop,
so it is NOT wired into etl/scheduler.py. Run it on a daily schedule after
the US market close (e.g. via Windows Task Scheduler or the app's scheduled
tasks), or manually:

    python -m etl.fetch_macro                 # latest ~120 obs per enabled series
    python -m etl.fetch_macro --limit 5       # just the most recent few
    python -m etl.fetch_macro --full          # full history (first backfill)
    python -m etl.fetch_macro --series DGS10  # one series only

Reads the series catalog from ref_macro_series (seeded by db/seeds_macro.sql).
Writes raw observations to hist_macro with ON CONFLICT DO NOTHING (convention 1:
raw hist_* is append-only; FRED revisions to past dates are intentionally not
overwritten — the displayed "latest" is always the newest obs_date, which is
freshly inserted each run).
"""
from __future__ import annotations

import argparse
import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime

from sqlalchemy import text

from config.settings import settings
from etl.db import insert_skip_duplicates, session_scope
from etl._logging import setup_logging

setup_logging()
log = logging.getLogger("fetch_macro")

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_LIMIT = 120                # recent observations per series (enough for cockpit + a little history)
REQUEST_TIMEOUT = 30               # seconds
DEFAULT_MIN_INTERVAL_MIN = 360     # throttle: skip if a real fetch ran within this many minutes (6h)


def _enabled_series(session, only: str | None) -> list[str]:
    sql = "SELECT series_id FROM ref_macro_series WHERE enabled"
    if only:
        sql += " AND series_id = :sid"
    sql += " ORDER BY grp, sort_order, series_id"
    params = {"sid": only.upper()} if only else {}
    return [r[0] for r in session.execute(text(sql), params).all()]


def _fetch_observations(series_id: str, limit: int | None, full: bool) -> list[dict]:
    """Call the FRED observations endpoint; return list of {series_id, obs_date, value}."""
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
    }
    if not full and limit:
        params["limit"] = str(limit)
    url = f"{FRED_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "trading-dashboard/macro"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    rows: list[dict] = []
    for obs in payload.get("observations", []):
        raw = obs.get("value")
        # FRED reports missing values as "." — store NULL.
        val: float | None
        if raw is None or raw == "." or raw == "":
            val = None
        else:
            try:
                val = float(raw)
            except (TypeError, ValueError):
                val = None
        try:
            obs_date = datetime.strptime(obs["date"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            continue
        rows.append({
            "series_id": series_id,
            "obs_date": obs_date,
            "value": val,
            "source": "FRED",
        })
    return rows


def _minutes_since_last_fetch(session) -> float | None:
    """Minutes since the last real (logged) fetch run; None if never run."""
    return session.execute(text(
        "SELECT EXTRACT(EPOCH FROM (now() - MAX(started_at)))/60.0 "
        "FROM meta_macro_fetch"
    )).scalar()


def _min_interval_setting(session) -> int:
    """Throttle window (minutes), tunable via
    ref_settings.macro_fetch_min_interval_min; falls back to the code default."""
    try:
        val = session.execute(text(
            "SELECT setting_value FROM ref_settings "
            "WHERE setting_name = 'macro_fetch_min_interval_min'"
        )).scalar()
        return int(val) if val is not None else DEFAULT_MIN_INTERVAL_MIN
    except Exception:
        return DEFAULT_MIN_INTERVAL_MIN


def _log_run(session, started_at, status: str, series_ok: int,
             series_failed: int, rows_inserted: int, trigger: str,
             note: str | None = None) -> None:
    session.execute(text("""
        INSERT INTO meta_macro_fetch
            (started_at, finished_at, trigger, status,
             series_ok, series_failed, rows_inserted, note)
        VALUES (:s, now(), :t, :st, :ok, :fl, :ri, :n)
    """), {"s": started_at, "t": trigger, "st": status, "ok": series_ok,
           "fl": series_failed, "ri": rows_inserted, "n": note})


def fetch_macro(limit: int | None = DEFAULT_LIMIT, full: bool = False,
                only: str | None = None, *, force: bool = False,
                min_interval_min: int | None = None,
                trigger: str = "cli") -> dict:
    """Pull all enabled series (or one) and upsert into hist_macro.

    Throttled: if a real fetch ran within the throttle window, this is a no-op
    returning {"skipped": True, ...} — unless `force=True`. The window comes from
    `min_interval_min` when given, else ref_settings.macro_fetch_min_interval_min,
    else DEFAULT_MIN_INTERVAL_MIN. Every real run is recorded in meta_macro_fetch.
    Returns a summary dict.
    """
    if not settings.fred_api_key:
        raise RuntimeError(
            "FRED_API_KEY is not set. Add it to .env "
            "(get a free key at https://fred.stlouisfed.org/docs/api/api_key.html)."
        )

    summary = {"skipped": False, "series": 0, "fetched": 0, "inserted": 0, "failed": []}
    started_at = datetime.now()

    with session_scope() as session:
        # --- throttle guard: protect the FRED rate limit from accidental reruns
        effective_interval = (min_interval_min if min_interval_min is not None
                              else _min_interval_setting(session))
        if not force:
            age = _minutes_since_last_fetch(session)
            if age is not None and age < effective_interval:
                log.info("throttled: last fetch %.0f min ago (< %d min); "
                         "use --force to override.", age, effective_interval)
                return {**summary, "skipped": True, "reason": "throttled",
                        "age_min": round(age), "min_interval_min": effective_interval}

        series_ids = _enabled_series(session, only)
        if not series_ids:
            log.warning("no enabled series in ref_macro_series%s",
                        f" matching {only!r}" if only else "")
            return summary

        for sid in series_ids:
            try:
                rows = _fetch_observations(sid, limit, full)
            except Exception as exc:  # network / API error — keep going
                log.error("fetch failed for %s: %s", sid, exc)
                summary["failed"].append(sid)
                continue

            if not rows:
                log.warning("%s: no observations returned", sid)
                summary["series"] += 1
                continue

            attempted, inserted = insert_skip_duplicates(session, "hist_macro", rows)
            summary["series"] += 1
            summary["fetched"] += attempted
            summary["inserted"] += inserted
            log.info("%-12s fetched=%d inserted=%d (latest %s)",
                     sid, attempted, inserted, rows[0]["obs_date"])

        # --- record the run (skipped/throttled runs are intentionally NOT logged)
        n_failed = len(summary["failed"])
        status = ("error" if summary["series"] == 0 and n_failed
                  else "partial" if n_failed else "ok")
        note = ("failed: " + ",".join(summary["failed"])) if n_failed else None
        _log_run(session, started_at, status, summary["series"], n_failed,
                 summary["inserted"], trigger, note)

    log.info("macro fetch complete: %d series, %d obs fetched, %d new rows%s",
             summary["series"], summary["fetched"], summary["inserted"],
             f", {len(summary['failed'])} failed" if summary["failed"] else "")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull macro series from FRED into hist_macro.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                        help=f"recent observations per series (default {DEFAULT_LIMIT})")
    parser.add_argument("--full", action="store_true",
                        help="fetch full available history (ignores --limit; use for first backfill)")
    parser.add_argument("--series", default=None,
                        help="only this FRED series id (e.g. DGS10)")
    parser.add_argument("--force", action="store_true",
                        help="ignore the throttle and fetch now")
    parser.add_argument("--min-interval", type=int, default=None,
                        help="throttle window in minutes; overrides "
                             "ref_settings.macro_fetch_min_interval_min "
                             f"(code default {DEFAULT_MIN_INTERVAL_MIN}). "
                             "No-op if the last run was more recent (override with --force)")
    args = parser.parse_args()

    try:
        result = fetch_macro(limit=args.limit, full=args.full, only=args.series,
                             force=args.force, min_interval_min=args.min_interval,
                             trigger="cli")
    except Exception as exc:
        log.error("%s", exc)
        return 1
    if result.get("skipped"):
        return 0
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
