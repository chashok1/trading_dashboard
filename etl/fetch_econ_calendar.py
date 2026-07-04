"""
Econ calendar feed — pull upcoming economic release *dates* from the FRED
release/dates API (same FRED account/key as etl/fetch_macro.py, a different
endpoint: this is "when does CPI publish next" rather than "what was CPI").

FRED (Federal Reserve Economic Data, St. Louis Fed) is free; get a key at
https://fred.stlouisfed.org/docs/api/api_key.html and put it in .env as
    FRED_API_KEY=...

Like fetch_macro.py, this is a *pull* rather than a watched file drop, so it
is NOT wired into etl/scheduler.py. Run it on a daily schedule (e.g. via
Windows Task Scheduler or the app's scheduled tasks), or manually:

    python -m etl.fetch_econ_calendar                 # respects the throttle
    python -m etl.fetch_econ_calendar --force          # ignore the throttle
    python -m etl.fetch_econ_calendar --release 10     # one release_id only

Reads the release_id -> category catalog from ref_econ_release (seeded by
db/seeds_econ_calendar.sql). Writes into ref_calendar_event with
ON CONFLICT DO NOTHING (its PK is (category, event_date)) — the SAME table
the workbook loader (etl/load_raw.py::load_data_tab_calendar_events) writes
into, so both sources coexist: this fills in what FRED tracks, the workbook
still covers categories FRED doesn't (ISM, Michigan Consumer Sentiment,
NAHB, Fed Meeting/FOMC/Beige Book, options/futures expiration, etc).

Release calendars are announced months ahead and essentially never change
day to day, so a long throttle window (default 24h) and a modest lookback/
lookahead window (default -30/+180 days) are enough — this is not a feed
that benefits from frequent polling.
"""
from __future__ import annotations

import argparse
import json
import logging
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

from sqlalchemy import text

from config.settings import settings
from etl.db import insert_skip_duplicates, session_scope
from etl._logging import setup_logging

setup_logging()
log = logging.getLogger("fetch_econ_calendar")

FRED_RELEASE_DATES_URL = "https://api.stlouisfed.org/fred/release/dates"
REQUEST_TIMEOUT = 30               # seconds
DEFAULT_MIN_INTERVAL_MIN = 1440    # throttle: skip if a real fetch ran within this many minutes (24h)
DEFAULT_DAYS_BACK = 30             # keep a little history for context
DEFAULT_DAYS_AHEAD = 180           # far enough to cover a couple of scheduled releases per indicator


def _enabled_releases(session, only: int | None) -> dict[int, list[str]]:
    """release_id -> [category, ...] for enabled rows."""
    sql = "SELECT release_id, category FROM ref_econ_release WHERE enabled"
    if only is not None:
        sql += " AND release_id = :rid"
    params = {"rid": only} if only is not None else {}
    rows = session.execute(text(sql), params).all()
    out: dict[int, list[str]] = {}
    for release_id, category in rows:
        out.setdefault(release_id, []).append(category)
    return out


def _fetch_release_dates(release_id: int) -> list[date]:
    """Call FRED's release/dates endpoint; return all dates it reports (all history)."""
    params = {
        "release_id": str(release_id),
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "asc",
        "include_release_dates_with_no_data": "true",
    }
    url = f"{FRED_RELEASE_DATES_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "trading-dashboard/econ-calendar"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    out: list[date] = []
    for d in payload.get("release_dates", []):
        try:
            out.append(datetime.strptime(d["date"], "%Y-%m-%d").date())
        except (KeyError, ValueError):
            continue
    return out


def _minutes_since_last_fetch(session) -> float | None:
    """Minutes since the last real (logged) fetch run; None if never run."""
    return session.execute(text(
        "SELECT EXTRACT(EPOCH FROM (now() - MAX(started_at)))/60.0 "
        "FROM meta_econ_calendar_fetch"
    )).scalar()


def _min_interval_setting(session) -> int:
    """Throttle window (minutes), tunable via
    ref_settings.econ_calendar_fetch_min_interval_min; falls back to the code default."""
    try:
        val = session.execute(text(
            "SELECT setting_value FROM ref_settings "
            "WHERE setting_name = 'econ_calendar_fetch_min_interval_min'"
        )).scalar()
        return int(val) if val is not None else DEFAULT_MIN_INTERVAL_MIN
    except Exception:
        return DEFAULT_MIN_INTERVAL_MIN


def _log_run(session, started_at, status: str, releases_ok: int,
             releases_failed: int, rows_inserted: int, trigger: str,
             note: str | None = None) -> None:
    session.execute(text("""
        INSERT INTO meta_econ_calendar_fetch
            (started_at, finished_at, trigger, status,
             releases_ok, releases_failed, rows_inserted, note)
        VALUES (:s, now(), :t, :st, :ok, :fl, :ri, :n)
    """), {"s": started_at, "t": trigger, "st": status, "ok": releases_ok,
           "fl": releases_failed, "ri": rows_inserted, "n": note})


def fetch_econ_calendar(days_back: int = DEFAULT_DAYS_BACK,
                        days_ahead: int = DEFAULT_DAYS_AHEAD,
                        only: int | None = None, *, force: bool = False,
                        min_interval_min: int | None = None,
                        trigger: str = "cli") -> dict:
    """Pull all enabled releases (or one) and upsert their dates into
    ref_calendar_event, windowed to [today-days_back, today+days_ahead].

    Throttled: if a real fetch ran within the throttle window, this is a no-op
    returning {"skipped": True, ...} — unless `force=True`. The window comes from
    `min_interval_min` when given, else ref_settings.econ_calendar_fetch_min_interval_min,
    else DEFAULT_MIN_INTERVAL_MIN. Every real run is recorded in meta_econ_calendar_fetch.
    Returns a summary dict.
    """
    if not settings.fred_api_key:
        raise RuntimeError(
            "FRED_API_KEY is not set. Add it to .env "
            "(get a free key at https://fred.stlouisfed.org/docs/api/api_key.html)."
        )

    summary = {"skipped": False, "releases": 0, "fetched": 0, "inserted": 0, "failed": []}
    started_at = datetime.now()
    today = date.today()
    window_start = today - timedelta(days=days_back)
    window_end = today + timedelta(days=days_ahead)

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

        release_map = _enabled_releases(session, only)
        if not release_map:
            log.warning("no enabled rows in ref_econ_release%s",
                        f" matching release_id={only}" if only is not None else "")
            return summary

        for release_id, categories in release_map.items():
            try:
                dates = _fetch_release_dates(release_id)
            except Exception as exc:  # network / API error — keep going
                log.error("fetch failed for release_id=%s: %s", release_id, exc)
                summary["failed"].append(release_id)
                continue

            windowed = [d for d in dates if window_start <= d <= window_end]
            rows = [{"category": cat, "event_date": d} for cat in categories for d in windowed]

            if not rows:
                log.warning("release_id=%s: no dates in window", release_id)
                summary["releases"] += 1
                continue

            attempted, inserted = insert_skip_duplicates(session, "ref_calendar_event", rows)
            summary["releases"] += 1
            summary["fetched"] += attempted
            summary["inserted"] += inserted
            log.info("release_id=%-4s %-30s fetched=%d inserted=%d",
                     release_id, ",".join(categories), attempted, inserted)

        # --- record the run (skipped/throttled runs are intentionally NOT logged)
        n_failed = len(summary["failed"])
        status = ("error" if summary["releases"] == 0 and n_failed
                  else "partial" if n_failed else "ok")
        note = ("failed: " + ",".join(str(r) for r in summary["failed"])) if n_failed else None
        _log_run(session, started_at, status, summary["releases"], n_failed,
                 summary["inserted"], trigger, note)

    log.info("econ calendar fetch complete: %d releases, %d dates fetched, %d new rows%s",
             summary["releases"], summary["fetched"], summary["inserted"],
             f", {len(summary['failed'])} failed" if summary["failed"] else "")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Pull econ release dates from FRED into ref_calendar_event.")
    parser.add_argument("--days-back", type=int, default=DEFAULT_DAYS_BACK,
                        help=f"keep dates from this many days ago (default {DEFAULT_DAYS_BACK})")
    parser.add_argument("--days-ahead", type=int, default=DEFAULT_DAYS_AHEAD,
                        help=f"keep dates up to this many days ahead (default {DEFAULT_DAYS_AHEAD})")
    parser.add_argument("--release", type=int, default=None,
                        help="only this FRED release_id (e.g. 10 for CPI)")
    parser.add_argument("--force", action="store_true",
                        help="ignore the throttle and fetch now")
    parser.add_argument("--min-interval", type=int, default=None,
                        help="throttle window in minutes; overrides "
                             "ref_settings.econ_calendar_fetch_min_interval_min "
                             f"(code default {DEFAULT_MIN_INTERVAL_MIN}). "
                             "No-op if the last run was more recent (override with --force)")
    args = parser.parse_args()

    try:
        result = fetch_econ_calendar(days_back=args.days_back, days_ahead=args.days_ahead,
                                     only=args.release, force=args.force,
                                     min_interval_min=args.min_interval, trigger="cli")
    except Exception as exc:
        log.error("%s", exc)
        return 1
    if result.get("skipped"):
        return 0
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
