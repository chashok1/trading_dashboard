"""
Daily health check — runs the same four checks as /api/health/derive-status
as a standalone CLI. Exits 0 if all green, 1 if any warning, 2 if any check
errored.

Designed for Windows Task Scheduler / cron:

    python -m etl.daily_health_check         # prints summary; exits nonzero on failure

The same logic powers the in-app health banner; this CLI lets you alert via
email/Slack/etc. without keeping a browser open.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from config.settings import settings
from etl._logging import setup_logging
from etl.db import session_scope

_SCHEDULER_HEARTBEAT_HOURS = 60
_RECENT_DATE_WINDOW = 5


def _check_hist_gap(session) -> dict:
    """Source-table snapshot dates from the last 60 days missing in drv_outlook_action."""
    rows = session.execute(text("""
        SELECT source_code, source_table FROM ref_outlook_source
        WHERE source_table IS NOT NULL
    """)).mappings().all()
    derived = {r[0] for r in session.execute(text(
        "SELECT DISTINCT as_of_date FROM drv_outlook_action"
    )).fetchall()}
    items = []
    for r in rows:
        tbl = r["source_table"]
        date_col = "event_date" if tbl.endswith("chg") else "snapshot_date"
        try:
            src_dates = {x[0] for x in session.execute(text(
                f"SELECT DISTINCT {date_col} FROM {tbl} "
                f"WHERE {date_col} >= (CURRENT_DATE - INTERVAL '60 days')"
            )).fetchall()}
        except Exception:
            continue
        missing = sorted(src_dates - derived, reverse=True)[:10]
        if missing:
            items.append({"source": r["source_code"], "table": tbl,
                          "missing_dates": [d.isoformat() for d in missing]})
    return {"id": "hist_gap", "title": "hist_* rows without drv_outlook_action",
            "ok": not items, "items": items}


def _check_stale_ref(session) -> dict:
    """Reference data edited after the last successful derive_outlook_action."""
    row = session.execute(text("""
        SELECT MAX(finished_at) FROM meta_derived_run
         WHERE target_table = 'drv_outlook_action' AND status = 'success'
    """)).first()
    last_derive = row[0] if row and row[0] else None
    stale = []
    for tbl, label in (("ref_param", "Outlook weights"),
                       ("ref_outlook_source", "Source priorities"),
                       ("ref_asset_allocation", "Asset allocation envelopes")):
        r = session.execute(text(f"SELECT MAX(loaded_at) FROM {tbl}")).first()
        edit = r[0] if r and r[0] else None
        if edit and last_derive and edit > last_derive:
            stale.append({"table": tbl, "label": label,
                          "last_edit": edit.isoformat(),
                          "last_derive": last_derive.isoformat()})
    return {"id": "stale_ref", "title": "Reference-data edits not propagated",
            "ok": not stale, "items": stale}


def _check_source_missing(session) -> dict:
    """For the last N dashboard dates, any source missing from drv_outlook_action."""
    recent = [r[0] for r in session.execute(text("""
        SELECT DISTINCT as_of_date FROM drv_dash
         ORDER BY as_of_date DESC LIMIT :n
    """), {"n": _RECENT_DATE_WINDOW}).fetchall()]
    sources = [r[0] for r in session.execute(text(
        "SELECT source_code FROM ref_outlook_source ORDER BY source_code"
    )).fetchall()]
    items = []
    for d in recent:
        got = {x[0] for x in session.execute(text(
            "SELECT DISTINCT source_code FROM drv_outlook_action WHERE as_of_date = :d"
        ), {"d": d}).fetchall()}
        miss = sorted(set(sources) - got)
        if miss:
            items.append({"date": d.isoformat(), "missing_sources": miss})
    return {"id": "source_missing", "title": "Source missing for recent dates",
            "ok": not items, "items": items}


def _check_scheduler_idle(session) -> dict:
    """Was a file processed in the last N hours?"""
    r = session.execute(text("SELECT MAX(loaded_at) FROM meta_file_processed")).first()
    last = r[0] if r and r[0] else None
    cutoff = datetime.now() - timedelta(hours=_SCHEDULER_HEARTBEAT_HOURS)
    ok = last is not None and last >= cutoff
    detail = (f"No file processed in the last {_SCHEDULER_HEARTBEAT_HOURS}h"
              f" (last: {last.isoformat() if last else 'never'})"
              if not ok else
              f"Last file processed {last.isoformat()}")
    return {"id": "scheduler_idle", "title": "ETL scheduler heartbeat",
            "ok": ok, "detail": detail, "items": []}


CHECKS = [_check_hist_gap, _check_stale_ref, _check_source_missing, _check_scheduler_idle]


def main() -> int:
    setup_logging()
    if not settings.pg_password:
        print("ERROR: PG_PASSWORD is empty in .env", file=sys.stderr)
        return 2

    overall_ok = True
    n_errors = 0
    print(f"=== Daily health check — {datetime.now().isoformat()} ===")
    try:
        with session_scope() as s:
            for check in CHECKS:
                try:
                    result = check(s)
                    icon = "OK  " if result["ok"] else "WARN"
                    print(f"  [{icon}] {result['title']}")
                    if not result["ok"]:
                        overall_ok = False
                        for item in result.get("items", [])[:5]:
                            print(f"           {item}")
                except Exception as e:
                    n_errors += 1
                    overall_ok = False
                    print(f"  [ERR ] {check.__name__}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"  [ERR ] could not open DB session: {e}", file=sys.stderr)
        return 2

    if overall_ok:
        print("All checks passing.")
        return 0
    if n_errors:
        print(f"FAILED: {n_errors} check(s) errored.", file=sys.stderr)
        return 2
    print("WARNING: at least one check failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
