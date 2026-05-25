"""
File processing monitor — ETL pipeline visibility.

Exposes four endpoints for real-time monitoring of file loads and derives:
- /api/monitor/summary — KPI tiles
- /api/monitor/schedule — today's expected files vs received
- /api/monitor/etl-runs — recent ETL load runs
- /api/monitor/derive-runs — derive pipeline runs for a date
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from config.settings import settings, PROJECT_ROOT
from etl.db import session_scope

_LOCK_FILE = Path(settings.etl_working_dir) / "scheduler.lock"
_HEARTBEAT = Path(settings.etl_working_dir) / "scheduler_heartbeat.txt"  # legacy, kept for any old code that references it
_HEARTBEAT_STALE_SECS = 90

router = APIRouter(tags=["monitor"])


def _last_n_occurrences(week_day: str, n: int = 5) -> list[date]:
    """Return the last N dates on which this week_day pattern was expected (excluding today)."""
    DOW_MAP = {'SUN': 6, 'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5}
    today = date.today()
    if week_day == 'MTH':
        # Monthly cadence: the first of each of the last N months before today.
        results = []
        y, m = today.year, today.month
        while len(results) < n:
            mf = date(y, m, 1)
            if mf < today:
                results.append(mf)
            m -= 1
            if m == 0:
                m, y = 12, y - 1
        return results
    results, check = [], today - timedelta(days=1)
    while len(results) < n:
        wd = check.weekday()  # 0=Mon … 6=Sun
        if (week_day == 'WKDAY' and wd < 5) or \
           (week_day == 'ALL') or \
           (week_day in DOW_MAP and wd == DOW_MAP[week_day]):
            results.append(check)
        check -= timedelta(days=1)
    return results


@router.get("/api/monitor/summary")
def get_summary():
    """
    KPI summary: scheduled today, processed, running, errors, derives OK, last file at.
    """
    with session_scope() as s:
        result = s.execute(text("""
            WITH today AS (SELECT CURRENT_DATE AS d),
            sched AS (
                SELECT COUNT(*) AS total
                FROM ref_load_files r, today t
                WHERE r.enabled = TRUE
                  AND (
                      r.week_day = 'MON'   AND EXTRACT(DOW FROM t.d) = 1 OR
                      r.week_day = 'WKDAY' AND EXTRACT(DOW FROM t.d) BETWEEN 1 AND 5 OR
                      r.week_day = 'SUN'   AND EXTRACT(DOW FROM t.d) = 0 OR
                      r.week_day = 'SAT'   AND EXTRACT(DOW FROM t.d) = 6 OR
                      r.week_day = 'ALL'
                  )
            ),
            processed AS (
                SELECT COUNT(DISTINCT file_type) AS done
                FROM meta_file_processed, today t
                WHERE file_date = t.d
            ),
            running_etl AS (
                SELECT COUNT(*) AS cnt FROM meta_etl_run WHERE status = 'running'
            ),
            errors_today AS (
                SELECT COUNT(*) AS cnt FROM meta_etl_run, today t
                WHERE status = 'error' AND started_at::date = t.d
            ),
            derives AS (
                SELECT
                    COUNT(*) FILTER (WHERE status = 'success') AS ok,
                    COUNT(*) AS total
                FROM meta_derived_run, today t
                WHERE as_of_date = t.d
            ),
            last_file AS (
                SELECT MAX(processed_at) AS last_at FROM meta_file_processed
            )
            SELECT
                sched.total        AS scheduled_today,
                processed.done     AS processed_today,
                running_etl.cnt    AS running_now,
                errors_today.cnt   AS errors_today,
                derives.ok         AS derives_ok,
                derives.total      AS derives_total,
                last_file.last_at  AS last_file_at
            FROM sched, processed, running_etl, errors_today, derives, last_file
        """)).first()

        if result:
            return {
                "scheduled_today": int(result[0] or 0),
                "processed_today": int(result[1] or 0),
                "running_now": int(result[2] or 0),
                "errors_today": int(result[3] or 0),
                "derives_ok": int(result[4] or 0),
                "derives_total": int(result[5] or 0),
                "last_file_at": result[6].isoformat() if result[6] else None,
                "as_of": datetime.now().isoformat(),
            }
    return {
        "scheduled_today": 0,
        "processed_today": 0,
        "running_now": 0,
        "errors_today": 0,
        "derives_ok": 0,
        "derives_total": 0,
        "last_file_at": None,
        "as_of": datetime.now().isoformat(),
    }


@router.get("/api/monitor/schedule")
def get_schedule():
    """
    Today's schedule: what file types are expected vs what has been processed.

    Returns per-file-type status: done, running, pending, error.
    Sorted: errors first, then running, then by scheduled time.
    """
    with session_scope() as s:
        result = s.execute(text("""
            WITH today AS (SELECT CURRENT_DATE AS d),
            is_today AS (
                -- DISTINCT (file_type, week_day) so multiple schedule slots
                -- per file_type (different file_times) don't multiply the
                -- join. The "is today" flag depends only on week_day.
                SELECT DISTINCT r.file_type, r.week_day
                FROM ref_load_files r, today t
                WHERE r.enabled = TRUE
                  AND (
                      r.week_day = 'WKDAY' AND EXTRACT(DOW FROM t.d) BETWEEN 1 AND 5 OR
                      r.week_day = 'MON'   AND EXTRACT(DOW FROM t.d) = 1 OR
                      r.week_day = 'TUE'   AND EXTRACT(DOW FROM t.d) = 2 OR
                      r.week_day = 'WED'   AND EXTRACT(DOW FROM t.d) = 3 OR
                      r.week_day = 'THU'   AND EXTRACT(DOW FROM t.d) = 4 OR
                      r.week_day = 'FRI'   AND EXTRACT(DOW FROM t.d) = 5 OR
                      r.week_day = 'SAT'   AND EXTRACT(DOW FROM t.d) = 6 OR
                      r.week_day = 'SUN'   AND EXTRACT(DOW FROM t.d) = 0 OR
                      r.week_day = 'ALL'
                  )
            ),
            running AS (
                SELECT file_type FROM meta_etl_run WHERE status = 'running'
            ),
            today_fp_all AS (
                -- ALL files processed today (no DISTINCT). Per-slot filtering
                -- happens in the LATERAL join below so each schedule slot
                -- only matches files processed AT OR AFTER its file_time.
                -- This makes multi-slot file_types (e.g., TOSL @ 16:00 and
                -- 17:00) correctly transition the later slot to overdue
                -- when its file hasn't arrived yet.
                SELECT UPPER(file_type) AS file_type, file_date, processed_at,
                       last_run_id, file_path
                FROM meta_file_processed, today t
                WHERE file_date = t.d
            ),
            last_fp_all AS (
                -- All processed files, any date. Per-slot LATERAL join below
                -- picks the latest one whose processed_at time-of-day is
                -- >= this slot's file_time so multi-slot file_types
                -- transition correctly to overdue.
                SELECT UPPER(file_type) AS file_type, file_date, processed_at,
                       last_run_id, file_path
                FROM meta_file_processed
            ),
            last_etl AS (
                SELECT DISTINCT ON (UPPER(file_type)) UPPER(file_type) AS file_type, status, rows_inserted, rows_skipped, error_msg
                FROM meta_etl_run
                ORDER BY UPPER(file_type), started_at DESC
            ),
            last_err AS (
                SELECT UPPER(file_type) AS file_type, error_msg
                FROM last_etl
                WHERE status = 'error'
            ),
            window_start AS (
                -- window_date depends only on week_day; DISTINCT keeps the
                -- CTE to one row per (file_type, week_day) so multi-slot
                -- file_types don't multiply when joined back to `r`.
                SELECT DISTINCT
                    r.file_type, r.week_day,
                    CASE
                        -- Specific days: window = most recent occurrence of that day
                        -- Formula: current_date - ((current_dow - scheduled_dow + 7) % 7)
                        WHEN r.week_day = 'SUN'
                             THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 0 + 7) % 7)
                        WHEN r.week_day = 'MON'
                             THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 1 + 7) % 7)
                        WHEN r.week_day = 'TUE'
                             THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 2 + 7) % 7)
                        WHEN r.week_day = 'WED'
                             THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 3 + 7) % 7)
                        WHEN r.week_day = 'THU'
                             THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 4 + 7) % 7)
                        WHEN r.week_day = 'FRI'
                             THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 5 + 7) % 7)
                        WHEN r.week_day = 'SAT'
                             THEN CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 6 + 7) % 7)
                        -- WKDAY (daily Mon-Fri): window = today (if weekday) or most recent Friday (if weekend)
                        WHEN r.week_day = 'WKDAY'
                             THEN CASE WHEN EXTRACT(DOW FROM CURRENT_DATE)::int NOT IN (0, 6)
                                       THEN CURRENT_DATE
                                       ELSE CURRENT_DATE - ((EXTRACT(DOW FROM CURRENT_DATE)::int - 5 + 7) % 7)
                                  END
                        -- ALL day: always today
                        WHEN r.week_day = 'ALL'
                             THEN CURRENT_DATE
                        WHEN r.week_day = 'MTH'
                             THEN date_trunc('month', CURRENT_DATE)::date
                        ELSE NULL
                    END AS window_date
                FROM ref_load_files r
            )
            SELECT
                r.file_type, r.target_tab, r.file_time, r.week_day, r.source_dir,
                COALESCE(fp.file_date,     lp.file_date)     AS file_date,
                COALESCE(fp.processed_at,  lp.processed_at)  AS processed_at,
                COALESCE(fp.last_run_id,   lp.last_run_id)   AS last_run_id,
                COALESCE(le.rows_inserted, 0)::int,
                COALESCE(le.rows_skipped,  0)::int,
                CASE
                    WHEN ru.file_type IS NOT NULL THEN 'running'
                    WHEN er.file_type IS NOT NULL THEN 'error'
                    WHEN fp.file_date IS NOT NULL THEN 'done'
                    WHEN lp.file_date IS NOT NULL AND (ws.window_date IS NULL OR lp.file_date >= ws.window_date) THEN 'done'
                    WHEN r.optional = TRUE THEN 'optional'
                    WHEN it.file_type IS NOT NULL AND r.file_time IS NOT NULL AND CURRENT_TIME < r.file_time THEN 'done'
                    WHEN it.file_type IS NOT NULL AND r.file_time IS NOT NULL AND CURRENT_TIME >= r.file_time THEN 'overdue'
                    WHEN it.file_type IS NOT NULL THEN 'pending'
                    ELSE 'not today'
                END,
                er.error_msg,
                COALESCE(fp.file_path, lp.file_path)         AS file_path,
                COALESCE(r.optional, FALSE)                   AS optional,
                COALESCE(r.rows_should_match, TRUE)          AS rows_should_match,
                r.target_table
            FROM ref_load_files r
            -- Composite-key joins so multi-slot file_types stay 1:1 with r.
            LEFT JOIN is_today  it ON it.file_type = r.file_type
                                  AND it.week_day  = r.week_day
            -- Per-slot fp: pick the latest file processed today whose
            -- processed_at time-of-day is >= this slot's file_time. So the
            -- 17:00 slot won't see the 16:05 file (which belongs to the
            -- 16:00 slot) — it'll correctly read as pending/overdue.
            LEFT JOIN LATERAL (
                SELECT fp_inner.file_type, fp_inner.file_date,
                       fp_inner.processed_at, fp_inner.last_run_id,
                       fp_inner.file_path
                FROM today_fp_all fp_inner
                WHERE fp_inner.file_type = UPPER(r.file_type)
                  AND (r.file_time IS NULL
                       OR fp_inner.processed_at::time >= r.file_time)
                ORDER BY fp_inner.processed_at DESC
                LIMIT 1
            ) fp ON TRUE
            LEFT JOIN window_start ws ON ws.file_type = r.file_type
                                     AND ws.week_day  = r.week_day
            -- Per-slot lp (any date) with the same time-of-day constraint.
            -- Without this, the 17:00 slot would inherit the 16:05 file's
            -- date via lp.file_date and the status branch
            --   WHEN lp.file_date IS NOT NULL AND lp.file_date >= ws.window_date THEN 'done'
            -- would wrongly mark it done.
            LEFT JOIN LATERAL (
                SELECT lp_inner.file_type, lp_inner.file_date,
                       lp_inner.processed_at, lp_inner.last_run_id,
                       lp_inner.file_path
                FROM last_fp_all lp_inner
                WHERE lp_inner.file_type = UPPER(r.file_type)
                  AND (r.file_time IS NULL
                       OR lp_inner.processed_at::time >= r.file_time)
                ORDER BY lp_inner.processed_at DESC
                LIMIT 1
            ) lp ON TRUE
            LEFT JOIN last_etl  le ON le.file_type = UPPER(r.file_type)
            LEFT JOIN running   ru ON ru.file_type = r.file_type
            LEFT JOIN last_err  er ON er.file_type = UPPER(r.file_type)
            WHERE r.enabled = TRUE
            ORDER BY
                CASE WHEN it.file_type IS NOT NULL THEN 0 ELSE 1 END,
                -- Status priority — mirrors the status-LABEL CASE line-for-line
                -- so sort never disagrees with the visible badge:
                --   0 error
                --   1 running
                --   2 overdue   (today, past file_time, no in-window file)
                --   3 pending   (today, file_time NULL)
                --   4 done      (today's file, or in-window lp, or before file_time)
                --   5 optional
                --   6 not today
                CASE
                    WHEN er.file_type IS NOT NULL THEN 0
                    WHEN ru.file_type IS NOT NULL THEN 1
                    WHEN fp.file_date IS NOT NULL THEN 4
                    WHEN lp.file_date IS NOT NULL
                         AND (ws.window_date IS NULL OR lp.file_date >= ws.window_date) THEN 4
                    WHEN r.optional = TRUE THEN 5
                    WHEN it.file_type IS NOT NULL AND r.file_time IS NOT NULL
                         AND CURRENT_TIME < r.file_time THEN 4
                    WHEN it.file_type IS NOT NULL AND r.file_time IS NOT NULL
                         AND CURRENT_TIME >= r.file_time THEN 2
                    WHEN it.file_type IS NOT NULL THEN 3
                    ELSE 6
                END,
                CASE
                    WHEN it.file_type IS NULL THEN
                        -- not-today group: sort by days since last occurrence (most recent first)
                        CASE r.week_day
                            WHEN 'SUN' THEN (EXTRACT(DOW FROM CURRENT_DATE)::int - 0 + 7) % 7
                            WHEN 'MON' THEN (EXTRACT(DOW FROM CURRENT_DATE)::int - 1 + 7) % 7
                            WHEN 'TUE' THEN (EXTRACT(DOW FROM CURRENT_DATE)::int - 2 + 7) % 7
                            WHEN 'WED' THEN (EXTRACT(DOW FROM CURRENT_DATE)::int - 3 + 7) % 7
                            WHEN 'THU' THEN (EXTRACT(DOW FROM CURRENT_DATE)::int - 4 + 7) % 7
                            WHEN 'FRI' THEN (EXTRACT(DOW FROM CURRENT_DATE)::int - 5 + 7) % 7
                            WHEN 'SAT' THEN (EXTRACT(DOW FROM CURRENT_DATE)::int - 6 + 7) % 7
                            ELSE 99
                        END
                    ELSE
                        -- today group: fixed week_day priority order within each status band
                        CASE r.week_day
                            WHEN 'WKDAY' THEN 1
                            WHEN 'MON'   THEN 2
                            WHEN 'TUE'   THEN 3
                            WHEN 'WED'   THEN 4
                            WHEN 'THU'   THEN 5
                            WHEN 'FRI'   THEN 6
                            WHEN 'SAT'   THEN 7
                            WHEN 'SUN'   THEN 8
                            WHEN 'ALL'   THEN 9
                            ELSE 10
                        END
                END,
                r.file_time NULLS LAST,
                COALESCE(fp.processed_at, lp.processed_at) DESC NULLS LAST,
                r.file_type
        """)).fetchall()

        # Get previous run row counts for comparison
        prev_rows = s.execute(text("""
            WITH ranked AS (
                SELECT file_type, rows_inserted,
                       ROW_NUMBER() OVER (PARTITION BY file_type ORDER BY started_at DESC) AS rn
                FROM meta_etl_run
            )
            SELECT file_type, rows_inserted FROM ranked WHERE rn = 2
        """)).fetchall()
        prev_rows_map = {row[0]: row[1] for row in prev_rows}

        rows = [
            {
                "file_type": row[0],
                "target_tab": row[1],
                "file_time": row[2].strftime("%H:%M:%S") if row[2] else "event",
                "week_day": row[3],
                "source_dir": row[4],
                "file_date": row[5].isoformat() if row[5] else None,
                "processed_at": row[6].isoformat() if row[6] else None,
                "last_run_id": row[7],
                "rows_inserted": row[8],
                "rows_skipped": row[9],
                "prev_rows_inserted": prev_rows_map.get(row[0]),
                "status": row[10],
                "error_msg": row[11],
                "file_path": row[12],
                "optional": bool(row[13]),
                "rows_should_match": bool(row[14]),
                "target_table": row[15],
            }
            for row in result
        ]

        # Fetch all processed dates in last 6 weeks for history dots
        cutoff = date.today() - timedelta(weeks=6)
        processed_rows = s.execute(text("""
            SELECT file_type, file_date FROM meta_file_processed
            WHERE file_date >= :cutoff
        """), {"cutoff": cutoff}).fetchall()

        from collections import defaultdict
        processed_by_type = defaultdict(set)
        for r in processed_rows:
            processed_by_type[r[0]].add(r[1])

        def was_received(file_type: str, week_day: str, expected: date) -> bool:
            dates = processed_by_type.get(file_type, set())
            if week_day == 'MTH':
                # Monthly: received if any file landed in the expected month.
                return any(d.year == expected.year and d.month == expected.month
                           for d in dates)
            if week_day in ('WKDAY', 'ALL'):
                # Daily — exact date only
                return expected in dates
            else:
                # Weekly — any file_date within the 7-day window counts
                return any((expected + timedelta(days=i)) in dates for i in range(7))

        for row in rows:
            occurrences = _last_n_occurrences(row["week_day"], n=5)
            row["history"] = [
                {"date": d.isoformat(), "received": was_received(row["file_type"], row["week_day"], d)}
                for d in occurrences
            ]

        return rows


@router.get("/api/monitor/etl-runs")
def get_etl_runs(limit: int = Query(50, ge=25, le=250), file_type: Optional[str] = None):
    """
    Recent ETL load runs with previous row count for comparison.
    Optionally filtered by file_type.
    """
    with session_scope() as s:
        if file_type:
            result = s.execute(text("""
                WITH ranked AS (
                    SELECT
                        m.run_id, m.started_at, m.finished_at, m.file_path, m.file_type, m.target_tab,
                        m.rows_read, m.rows_inserted, m.rows_skipped, m.status, m.error_msg,
                        EXTRACT(EPOCH FROM (COALESCE(m.finished_at, now()) - m.started_at))::int AS duration_sec,
                        LAG(m.rows_inserted) OVER (PARTITION BY m.file_type ORDER BY m.started_at DESC) AS prev_rows_inserted,
                        COALESCE(r.rows_should_match, TRUE) AS rows_should_match,
                        r.target_table AS target_table
                    FROM meta_etl_run m
                    LEFT JOIN ref_load_files r ON LOWER(m.file_type) = LOWER(r.file_type)
                    WHERE m.file_type = :ft
                )
                SELECT * FROM ranked ORDER BY started_at DESC LIMIT :limit
            """), {"ft": file_type, "limit": limit}).fetchall()
        else:
            result = s.execute(text("""
                WITH ranked AS (
                    SELECT
                        m.run_id, m.started_at, m.finished_at, m.file_path, m.file_type, m.target_tab,
                        m.rows_read, m.rows_inserted, m.rows_skipped, m.status, m.error_msg,
                        EXTRACT(EPOCH FROM (COALESCE(m.finished_at, now()) - m.started_at))::int,
                        LAG(m.rows_inserted) OVER (PARTITION BY m.file_type ORDER BY m.started_at DESC),
                        COALESCE(r.rows_should_match, TRUE),
                        r.target_table
                    FROM meta_etl_run m
                    LEFT JOIN ref_load_files r ON LOWER(m.file_type) = LOWER(r.file_type)
                )
                SELECT * FROM ranked ORDER BY started_at DESC LIMIT :limit
            """), {"limit": limit}).fetchall()

        return [
            {
                "run_id": row[0],
                "started_at": row[1].isoformat(),
                "finished_at": row[2].isoformat() if row[2] else None,
                "file_path": row[3],
                "file_type": row[4],
                "target_tab": row[5],
                "rows_read": row[6],
                "rows_inserted": row[7],
                "rows_skipped": row[8],
                "status": row[9],
                "error_msg": row[10],
                "duration_sec": int(row[11]) if row[11] else 0,
                "prev_rows_inserted": row[12],
                "rows_should_match": bool(row[13]),
                "target_table": row[14],
            }
            for row in result
        ]


@router.get("/api/monitor/derive-runs")
def get_derive_runs(date_param: Optional[str] = Query(None, alias="date")):
    """
    Derive pipeline runs for a given date. Defaults to today.
    """
    target_date = date_param if date_param else str(date.today())

    with session_scope() as s:
        result = s.execute(text("""
            SELECT
                run_id,
                started_at,
                finished_at,
                as_of_date,
                target_table,
                rows_built,
                status,
                error_msg,
                parent_run_id,
                EXTRACT(EPOCH FROM (COALESCE(finished_at, now()) - started_at))::int AS duration_sec
            FROM meta_derived_run
            WHERE as_of_date = :d
            ORDER BY started_at DESC
        """), {"d": target_date}).fetchall()

        return [
            {
                "run_id": row[0],
                "started_at": row[1].isoformat(),
                "finished_at": row[2].isoformat() if row[2] else None,
                "as_of_date": row[3].isoformat(),
                "target_table": row[4],
                "rows_built": row[5],
                "status": row[6],
                "error_msg": row[7],
                "parent_run_id": row[8],
                "duration_sec": int(row[9]) if row[9] else 0,
            }
            for row in result
        ]


# ── Live SSE stream ───────────────────────────────────────────────────────────

def _query_running_jobs() -> list[dict]:
    """Fetch all currently running ETL jobs. Called in a thread from the SSE loop."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT
                run_id,
                file_type,
                file_path,
                target_tab,
                COALESCE(rows_inserted, 0) AS rows_inserted,
                COALESCE(rows_skipped,  0) AS rows_skipped,
                EXTRACT(EPOCH FROM (now() - started_at))::int AS elapsed_sec
            FROM meta_etl_run
            WHERE status = 'running'
            ORDER BY started_at
        """)).fetchall()
    return [
        {
            "run_id":        r[0],
            "file_type":     r[1],
            "file_path":     r[2] or "",
            "target_tab":    r[3] or "",
            "rows_inserted": int(r[4]),
            "rows_skipped":  int(r[5]),
            "elapsed_sec":   int(r[6] or 0),
        }
        for r in rows
    ]


@router.get("/api/monitor/live")
async def live_stream():
    """Server-Sent Events: pushes running ETL job state.

    Was 500 ms — that produced 120+ DB connections per minute per browser
    tab, and on Windows competed with the scheduler's psycopg connections
    enough to occasionally crash it. Slowed to 5 s, which is fast enough
    for "live" feel but light enough to leave the scheduler alone.
    """
    async def generate():
        while True:
            try:
                jobs = await asyncio.to_thread(_query_running_jobs)
                payload = json.dumps(
                    {"type": "running", "jobs": jobs} if jobs else {"type": "idle"}
                )
            except Exception as exc:
                payload = json.dumps({"type": "error", "msg": str(exc)})
            yield f"data: {payload}\n\n"
            await asyncio.sleep(5.0)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


# ── Scheduler status / control ────────────────────────────────────────────────

import os as _os

# Windows Startup folder — no admin required, runs at login for current user
_STARTUP_DIR      = Path(_os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
_STARTUP_SCHED    = _STARTUP_DIR / "TradingDashboard-ETLScheduler.bat"
_STARTUP_APP      = _STARTUP_DIR / "TradingDashboard-TradingApp.bat"

# Full runner bats in project root (called by the startup launchers)
_RUN_SCHED_BAT    = PROJECT_ROOT / "run_etl_scheduler.bat"
_RUN_APP_BAT      = PROJECT_ROOT / "run_trading_app.bat"


def _ensure_runner_bats() -> None:
    """Write the runner bat files into the project root if missing.

    These are tiny shims that just chain into the canonical top-level
    launchers in the project root:
      - ETL Scheduler  → run_scheduler.bat   (keep-alive wrapper)
      - Trading App    → start.bat           (uvicorn with --reload-dir api)
    We always rewrite these on every register call so a project-level
    update to start.bat / run_scheduler.bat doesn't get bypassed.
    """
    root = PROJECT_ROOT
    _RUN_SCHED_BAT.write_text(
        f'@echo off\r\ncd /d "{root}"\r\n'
        f'call "{root}\\run_scheduler.bat"\r\n'
    )
    _RUN_APP_BAT.write_text(
        f'@echo off\r\ncd /d "{root}"\r\n'
        f'call "{root}\\start.bat"\r\n'
    )


def _write_startup_launcher(startup_file: Path, target_bat: Path, title: str) -> None:
    """Write a small launcher into the Windows Startup folder."""
    _STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    startup_file.write_text(
        f'@echo off\r\nstart "{title}" "{target_bat}"\r\n'
    )


def _pid_is_alive(pid: int) -> bool:
    """Cross-platform check whether `pid` corresponds to a running process."""
    if not pid or pid <= 0:
        return False
    try:
        import os as _os
        _os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID exists, owned by another user — still alive
        return True
    except OSError:
        return False


def _count_scheduler_processes() -> int:
    """Best-effort count of python.exe processes running etl.scheduler.

    Uses Windows `tasklist /V` (verbose) to inspect window titles and command
    lines. Returns 0 if the count can't be determined — the caller should fall
    back to heartbeat-only diagnostics.
    """
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/V", "/FO", "CSV"],
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode != 0:
            return 0
        # Each non-header line is one process; window title carries the cmdline.
        n = 0
        for ln in out.stdout.splitlines()[1:]:
            if "scheduler" in ln.lower():
                n += 1
        return n
    except Exception:
        return 0


def _check_running() -> dict:
    """Probe scheduler.lock — running iff we cannot acquire the lock.
    Read-only / lock-only operation; never writes content."""
    if not _LOCK_FILE.exists():
        return {"running": False}
    fp = None
    try:
        fp = open(_LOCK_FILE, "r+b")   # open WITHOUT truncating
        try:
            if sys.platform == "win32":
                import msvcrt
                fp.seek(0)
                try:
                    msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    # Lock conflict → scheduler is running
                    return {"running": True}
                # Acquired → no one else has it → NOT running. Release.
                try:
                    fp.seek(0)
                    msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
                except Exception:
                    pass
                return {"running": False}
            else:
                import fcntl
                try:
                    fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return {"running": True}
                try:
                    fcntl.flock(fp.fileno(), fcntl.LOCK_UN)
                except Exception:
                    pass
                return {"running": False}
        finally:
            if fp is not None:
                try: fp.close()
                except Exception: pass
    except Exception:
        # If we can't even open it, assume not running so the UI prompts user.
        return {"running": False}

def _read_heartbeat() -> dict:
    """Back-compat shim — older code paths may still call this name.
    Returns the same minimal shape as _check_running.
    """
    return _check_running()


@router.get("/api/monitor/scheduler")
def get_scheduler_status():
    return _read_heartbeat()


@router.post("/api/monitor/scheduler/start")
def start_scheduler():
    status = _read_heartbeat()
    if status["lock_held"]:
        return {"started": False, "reason": "already running", "pid": status["pid"]}
    # Clean up a stale heartbeat (fresh timestamp but dead PID) so the new
    # scheduler's acquire_lock doesn't have to wait out the staleness window.
    if status["running"] and not status["pid_alive"]:
        _HEARTBEAT.unlink(missing_ok=True)

    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    python = str(venv_python) if venv_python.exists() else sys.executable

    # Setup window to be hidden
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    try:
        crash_log = Path(settings.etl_working_dir) / "scheduler_crash.log"
        crash_log.parent.mkdir(parents=True, exist_ok=True)

        # Write a tiny launcher .bat to the user's TEMP dir (NOT in the project!
        # uvicorn's --reload watches the project tree.) The .bat handles cwd,
        # venv activation, and stdout/stderr redirection. Then we `start` it
        # via cmd, which gives us a fully independent Windows process.
        import tempfile
        temp_dir = Path(tempfile.gettempdir())
        launcher_bat = temp_dir / "trading_dashboard_scheduler.bat"
        launcher_bat.write_text(
            "@echo off\r\n"
            f'cd /d "{PROJECT_ROOT}"\r\n'
            f'"{python}" -m etl.scheduler >> "{crash_log}" 2>&1\r\n',
            encoding="utf-8",
        )

        # `cmd /c start "" /MIN <bat>` creates a fully independent process.
        # The outer subprocess.Popen returns immediately; cmd.exe exits as
        # soon as `start` queues the bat; the bat then runs in its own
        # process group, fully detached.
        proc = subprocess.Popen(
            ["cmd.exe", "/c", "start", "", "/MIN", str(launcher_bat)],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        # proc.pid is the outer cmd.exe shell PID, not the scheduler's.
        # The scheduler writes its OWN pid to scheduler_heartbeat.txt once
        # started, and the UI reads that. We return the launcher_bat path
        # so users can inspect / rerun manually if needed.
        return {"started": True, "pid": "via-shell-launcher",
                "launcher": str(launcher_bat)}
    except Exception as e:
        return {"started": False, "reason": str(e)}


@router.post("/api/monitor/scheduler/stop")
def stop_scheduler():
    status = _read_heartbeat()
    if not status["running"]:
        return {"stopped": False, "reason": "not running"}

    pid = status["pid"]
    heartbeat_path = Path(settings.etl_working_dir) / "scheduler_heartbeat.txt"
    stop_flag_path = Path(settings.etl_working_dir) / "scheduler_stop.txt"
    try:
        stop_flag_path.parent.mkdir(parents=True, exist_ok=True)
        stop_flag_path.write_text(str(pid))
        for _ in range(8):
            time.sleep(1)
            try:
                os.kill(pid, 0)
            except (ProcessLookupError, OSError):
                break
        else:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                           check=False, capture_output=True, timeout=5)
        stop_flag_path.unlink(missing_ok=True)
        heartbeat_path.unlink(missing_ok=True)
        return {"stopped": True, "pid": pid}
    except Exception as e:
        return {"stopped": False, "reason": str(e)}


@router.get("/api/monitor/scheduler/output")
def get_scheduler_output(last_n: int = 50, level: str = '', file_type: str = ''):
    """Return last N rows from meta_scheduler_log table (latest first), optionally filtered by log level or file type."""
    try:
        with session_scope() as session:
            where_parts = []
            params = {"limit": last_n}

            if level:
                where_parts.append("log_level = :level")
                params["level"] = level.upper()

            if file_type:
                where_parts.append("file_name ILIKE :file_pattern")
                params["file_pattern"] = file_type + ' %'

            where_clause = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

            rows = session.execute(text(f"""
                SELECT logged_at, message, file_name, log_level FROM meta_scheduler_log
                {where_clause}
                ORDER BY logged_at DESC LIMIT :limit
            """), params).fetchall()

            total = session.execute(text(
                "SELECT COUNT(*) FROM meta_scheduler_log"
            )).scalar() or 0

            rows_out = [{"time": row[0].strftime('%H:%M:%S'), "message": row[1],
                         "file_name": row[2], "log_level": row[3]} for row in rows]
            return {"rows": rows_out, "total": total}
    except Exception as e:
        return {"rows": [], "error": str(e), "total": 0}


@router.get("/api/monitor/scheduler/levels")
def get_scheduler_levels():
    """Return the standard Python log levels (hard-coded — no DB hit).

    Originally this did SELECT DISTINCT against meta_scheduler_log, but with
    the scheduler writing tens-of-thousands of rows that scan was killing
    the API worker. The set of levels is small and fixed, so we just return
    the standard list.
    """
    return {"levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]}


@router.get("/api/monitor/startup")
def get_startup_status():
    """Report whether the Windows startup launchers for the scheduler and
    trading app are registered. Used by File Monitor → Auto-start tiles."""
    sched_file = _STARTUP_DIR / "TradingDashboard_Scheduler.bat"
    app_file   = _STARTUP_DIR / "TradingDashboard_App.bat"
    return {
        "scheduler_registered": sched_file.exists(),
        "app_registered":       app_file.exists(),
        "startup_dir":          str(_STARTUP_DIR),
    }


@router.post("/api/monitor/startup/register")
def register_startup(task: str):
    """Write startup launchers into the Windows Startup folder (no admin needed)."""
    _ensure_runner_bats()
    try:
        if task in (None, "scheduler"):
            _write_startup_launcher(_STARTUP_SCHED, _RUN_SCHED_BAT, "ETL Scheduler")
        if task in (None, "app"):
            _write_startup_launcher(_STARTUP_APP, _RUN_APP_BAT, "Trading App")
        label = ("ETL Scheduler" if task == "scheduler"
                 else "Trading App" if task == "app"
                 else "both")
        return {"success": True, "message": f"Registered {label} in Startup folder"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@router.post("/api/monitor/startup/unregister")
def unregister_startup():
    """Remove startup launchers from the Windows Startup folder."""
    for f in (_STARTUP_SCHED, _STARTUP_APP):
        f.unlink(missing_ok=True)
    return {"success": True, "message": "Removed from Startup folder"}

@router.post("/api/monitor/reprocess")
def reprocess_file(file_path: str = Query(...),
                   file_type: Optional[str] = Query(None),
                   force: bool = Query(True)):
    """Reprocess a specific source file.

    Called from the File Monitor screen's per-row Reprocess button. Defaults
    to force=True so an unchanged file is reloaded anyway — etl_load's
    already_processed() short-circuits without this. Loaders are idempotent
    (PK-conflict skip), so a re-run is safe.
    """
    try:
        from etl.etl_load import load_one_file
    except Exception as e:
        return {"success": False, "msg": f"load_one_file import failed: {e}"}
    # load_one_file(do_derive=True) always runs the derive cascade now.
    try:
        result = load_one_file(file_path, file_type=file_type,
                               do_derive=True, force=bool(force))
        return {"success": True, "result": result,
                "msg": f"Reprocessed {Path(file_path).name}"}
    except Exception as e:
        import traceback
        return {"success": False,
                "msg": f"reprocess failed: {e}",
                "trace": traceback.format_exc()}

# ─── Missing derives finder + runner ────────────────────────────────────
# A "missing" date is one where some hist_* table has a row for that
# snapshot_date but meta_derived_run has no successful row for the same
# date. Used by the File Monitor "Run Missing Derives" button.

def _find_missing_derive_dates(session, last_n_days: Optional[int] = None) -> list:
    """Return ascending list of snapshot dates with hist_* data but no
    successful meta_derived_run row.

    If ``last_n_days`` is provided (positive int), only return dates
    within the last N days (snapshot_date >= CURRENT_DATE - N).
    """
    sql = """
        WITH hist_dates AS (
            SELECT DISTINCT snapshot_date AS d FROM hist_cs
            UNION SELECT DISTINCT snapshot_date FROM hist_f
            UNION SELECT DISTINCT snapshot_date FROM hist_tl
            UNION SELECT DISTINCT snapshot_date FROM hist_td
        ),
        done AS (
            SELECT DISTINCT as_of_date AS d FROM meta_derived_run
             WHERE status = 'success'
        )
        SELECT d FROM hist_dates
        WHERE d NOT IN (SELECT d FROM done)
    """
    params = {}
    if last_n_days is not None and last_n_days > 0:
        sql += " AND d >= CURRENT_DATE - :ndays"
        params["ndays"] = int(last_n_days)
    sql += " ORDER BY d ASC"
    rows = session.execute(text(sql), params).all()
    return [r[0] for r in rows]


def _find_dates_to_rederive(session, last_n_days: Optional[int] = None) -> list:
    """Return ascending list of already-derived dates (force re-derive).

    Unlike _find_missing_derive_dates, this returns dates that ALREADY have a
    successful derive — used to re-apply derive-code changes to existing dates.
    """
    sql = """
        SELECT DISTINCT as_of_date AS d FROM meta_derived_run
         WHERE status = 'success'
    """
    params = {}
    if last_n_days is not None and last_n_days > 0:
        sql += " AND as_of_date >= CURRENT_DATE - :ndays"
        params["ndays"] = int(last_n_days)
    sql += " ORDER BY d ASC"
    rows = session.execute(text(sql), params).all()
    return [r[0] for r in rows]


@router.get("/api/monitor/derive-missing")
def get_missing_derive_dates(last_n_days: Optional[int] = Query(None, ge=1),
                             force: bool = Query(False)):
    """Preview the snapshot dates a derive run would cover.

    force=False -> dates with hist_* data but no successful derive (gaps).
    force=True  -> every already-derived date in the window (re-derive).
    """
    with session_scope() as s:
        dates = (_find_dates_to_rederive(s, last_n_days) if force
                 else _find_missing_derive_dates(s, last_n_days))
    return {"dates": [d.isoformat() for d in dates], "count": len(dates),
            "last_n_days": last_n_days, "force": force}


@router.post("/api/monitor/derive-missing/run")
def run_missing_derives(last_n_days: Optional[int] = Query(None, ge=1),
                        force: bool = Query(False)):
    """Run derive_all oldest→newest.

    force=False -> only dates with hist_* data but no successful derive.
    force=True  -> every already-derived date in the window (re-apply code).

    Failures on individual dates are caught — the loop keeps going.
    """
    try:
        from etl.derive import derive_all
    except Exception as e:
        return {"success": False, "msg": f"derive_all import failed: {e}",
                "results": []}

    results = []
    with session_scope() as s:
        dates = (_find_dates_to_rederive(s, last_n_days) if force
                 else _find_missing_derive_dates(s, last_n_days))
    for d in dates:
        entry = {"date": d.isoformat()}
        try:
            with session_scope() as s:
                counts = derive_all(s, d)
            entry["status"] = "success"
            entry["rows"] = (counts.get("drv_ma") if isinstance(counts, dict) else None)
            entry["counts"] = counts if isinstance(counts, dict) else None
        except Exception as e:
            import traceback
            entry["status"] = "failed"
            entry["error"] = str(e)
            entry["trace"] = traceback.format_exc()
        results.append(entry)
    return {"success": True, "count": len(results), "results": results,
            "last_n_days": last_n_days}


@router.get("/api/monitor/derive-stale")
def get_stale_derive_dates():
    """List drv_actionable dates that are stale - newer outlook-source
    data was loaded after the date was last derived."""
    from etl.derive_freshness import find_stale_actionable_dates
    with session_scope() as s:
        dates = find_stale_actionable_dates(s)
    return {"dates": [d.isoformat() for d in dates], "count": len(dates)}


@router.post("/api/monitor/derive-stale/run")
def run_stale_derives():
    """Re-derive every stale drv_actionable date (auto-heal, on demand)."""
    from etl.derive_freshness import run_stale_heal
    result = run_stale_heal()
    return {"success": True,
            "count": len(result.get("healed", [])),
            "healed": result.get("healed", []),
            "failed": result.get("failed", []),
            "stale": result.get("stale", [])}
