"""Health, dates, sectors, dashboard side-panel endpoints."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from config.settings import settings
from etl.db import get_engine, session_scope

from api.models import HealthResponse
from api._helpers import discover_data_tables

logger = logging.getLogger(__name__)

router = APIRouter()


# -----------------------------------------------------------------------------
# Debug
# -----------------------------------------------------------------------------

@router.get("/debug/tables-dict")
def debug_tables_dict():
    """Debug endpoint: show what's actually discovered as data tables"""
    return {
        "total": len(discover_data_tables()),
        "drv_cat_count": len([k for k in discover_data_tables() if k.startswith('drv_cat_')]),
        "drv_cat_tables": sorted([k for k in discover_data_tables() if k.startswith('drv_cat_')]),
        "all_tables": discover_data_tables(),
    }


# -----------------------------------------------------------------------------
# Health
# -----------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
def health():
    db_ok = "ok"
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_ok = f"error: {e}"
    return HealthResponse(
        status="ok" if db_ok == "ok" else "degraded",
        db=db_ok,
        server_time=datetime.now(),
        pg_database=settings.pg_database,
    )


# -----------------------------------------------------------------------------
# Date listing
# -----------------------------------------------------------------------------

@router.get("/api/dates")
def list_dates():
    """Distinct snapshot dates available across drv_dash + drv_stks."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT as_of_date FROM v_available_dates ORDER BY 1 DESC
        """)).fetchall()
    return [r[0].isoformat() for r in rows]


@router.get("/api/sectors")
def list_sectors():
    """Distinct sectors present in drv_ma (used for filter dropdowns)."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT DISTINCT sector FROM drv_ma
            WHERE sector IS NOT NULL
            ORDER BY 1
        """)).fetchall()
    return [r[0] for r in rows]


# -----------------------------------------------------------------------------
# Dashboard side panels: economic indicators, earnings/calendar events, quads
# -----------------------------------------------------------------------------

@router.get("/api/dashboard/econ-indicators")
def get_dashboard_econ_indicators(
    date: Optional[str] = Query(None, description="As-of date (defaults to today)"),
    limit: int = Query(30, ge=1, le=200),
):
    """
    Active economic indicators for the dashboard side panel.
    Mirrors Dash A-J: filters ref_econ_indicator where show_on_dashboard='Y'
    (or incl='Y' as fallback), sorted by days ascending (soonest first).
    """
    d = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT
                indicator,
                indicator_date,
                (indicator_date - :d) AS days,
                ol AS signal,
                from_date,
                to_date,
                effective_today,
                expected,
                url
            FROM ref_econ_indicator
            WHERE COALESCE(show_on_dashboard, incl) = 'Y'
              AND indicator_date >= :d - INTERVAL '7 days'
            ORDER BY indicator_date ASC, days ASC
            LIMIT :lim
        """), {"d": d, "lim": limit}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/api/dashboard/earnings")
def get_dashboard_earnings(
    date: Optional[str] = Query(None, description="As-of date (defaults to today)"),
    days_ahead: int = Query(60, ge=1, le=365),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Earnings & market-structure events for the dashboard side panel.
    Pulls from ref_calendar_event but EXCLUDES any category that already appears
    in ref_econ_indicator (CPI, PPI, PCE, GDP, NFP, etc.) â€” those belong to the
    Economic Indicators panel, so showing them here would duplicate the data.
    What remains: VIX Expiration, Fed Meeting, FOMC Minutes, Beige Book,
    Monthly/Qtly Exp, Jackson Hole, and any future per-ticker 'Earnings' rows.
    Match is case- and whitespace-insensitive to tolerate naming drift between
    the two source tabs (e.g., 'CPI YOY' vs 'CPI YoY').
    """
    d = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT
                category,
                event_date,
                (event_date - :d) AS days_until
            FROM ref_calendar_event
            WHERE event_date >= :d
              AND event_date <= :d + (:days_ahead || ' days')::INTERVAL
              AND LOWER(REGEXP_REPLACE(category, '\\s+', '', 'g')) NOT IN (
                  SELECT LOWER(REGEXP_REPLACE(indicator, '\\s+', '', 'g'))
                  FROM ref_econ_indicator
                  WHERE COALESCE(show_on_dashboard, incl) = 'Y'
              )
            ORDER BY event_date ASC, category ASC
            LIMIT :lim
        """), {"d": d, "days_ahead": days_ahead, "lim": limit}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/api/dashboard/quads")
def get_dashboard_quads(
    date: Optional[str] = Query(None, description="As-of date (defaults to today)"),
):
    """
    Quads for the dashboard banner:
      - current_quarter: quarter containing :d
      - next_quarter:    quarter immediately after current_quarter
      - months:          list of 4 monthly periods (current month + next 3)
    All resolved from ref_quad_periods.
    """
    d = datetime.strptime(date, "%Y-%m-%d").date() if date else datetime.now().date()
    out = {
        "as_of_date": d.isoformat(),
        "current_quarter": None,
        "next_quarter": None,
        "months": [],
    }
    with session_scope() as s:
        cq = s.execute(text("""
            SELECT period_type, label, start_date, end_date, quad
            FROM ref_quad_periods
            WHERE period_type = 'quarterly'
              AND :d >= start_date
              AND (:d <= end_date OR end_date IS NULL)
            ORDER BY start_date DESC
            LIMIT 1
        """), {"d": d}).mappings().first()
        if cq:
            out["current_quarter"] = dict(cq)

        anchor = cq["start_date"] if cq else d
        nq = s.execute(text("""
            SELECT period_type, label, start_date, end_date, quad
            FROM ref_quad_periods
            WHERE period_type = 'quarterly'
              AND start_date > :anchor
            ORDER BY start_date ASC
            LIMIT 1
        """), {"anchor": anchor}).mappings().first()
        if nq:
            out["next_quarter"] = dict(nq)

        months = s.execute(text("""
            SELECT period_type, label, start_date, end_date, quad
            FROM ref_quad_periods
            WHERE period_type = 'monthly'
              AND COALESCE(end_date, start_date) >= :d
            ORDER BY start_date ASC
            LIMIT 4
        """), {"d": d}).mappings().all()
        out["months"] = [dict(m) for m in months]

    return out



# =============================================================================
# Derive-status health check + admin rebuild
# =============================================================================
# These run a handful of cheap SQL queries to surface the "things can fall
# through" cases for the derive pipeline (see docs/ma_jg_no_audit.md Â§2026-05-12
# "Deferred" notes). The status payload drives the topbar banner in web/.

# Hours to consider the scheduler "alive" â€” covers a 2-day weekend.
_SCHEDULER_HEARTBEAT_HOURS = 60

# How many recent dashboard dates to scan for "missing source" check.
_RECENT_DATE_WINDOW = 5


@router.get("/api/health/derive-status")
def get_derive_status():
    """
    Run three health checks against the derive pipeline. Returns a payload the
    UI banner can render. Each check is non-fatal: a failed check produces a
    warning, not a 500.

    Checks (all read-only, fast):
      1. stale_ref         â€” ref_param or ref_outlook_source edited after the last derive_outlook_action run
      2. source_missing    â€” for dashboard dates older than 24 hours, is every active source
                              represented in drv_outlook_action? Only alerts for stale data.
      3. scheduler_idle    â€” no file processed via meta_file_processed in the last _SCHEDULER_HEARTBEAT_HOURS
    """
    checks = []
    with session_scope() as s:
        # ------------------------------------------------------------------
        # 1. hist_gap check removed (too noisy during normal operations)
        # ------------------------------------------------------------------

        # ------------------------------------------------------------------
        # 2. stale_ref: ref_param / ref_outlook_source edited after last derive
        # ------------------------------------------------------------------
        try:
            last_derive = s.execute(text("""
                SELECT MAX(finished_at) AS last_derive
                FROM meta_derived_run
                WHERE target_table = 'drv_outlook_action' AND status = 'success'
            """)).first()
            last_derive_dt = last_derive[0] if last_derive and last_derive[0] else None

            stale = []
            for tbl, label in (
                ("ref_param", "Outlook weights (ref_param)"),
                ("ref_outlook_source", "Source priorities (ref_outlook_source)"),
                ("ref_asset_allocation", "Asset allocation envelopes"),
            ):
                # Each table has a loaded_at column.
                row = s.execute(text(f"SELECT MAX(loaded_at) FROM {tbl}")).first()
                edit_dt = row[0] if row and row[0] else None
                if edit_dt is None or last_derive_dt is None:
                    continue
                if edit_dt > last_derive_dt:
                    stale.append({
                        "table": tbl, "label": label,
                        "last_edit": edit_dt.isoformat(),
                        "last_derive": last_derive_dt.isoformat(),
                    })
            checks.append({
                "id": "stale_ref",
                "ok": len(stale) == 0,
                "severity": "warning" if stale else "ok",
                "title": "Reference-data edits not yet propagated",
                "detail": (f"{len(stale)} reference table(s) edited after last derive â€” "
                           f"rebuild to apply new weights/priorities"
                           if stale else "All reference edits have been propagated."),
                "items": stale,
            })
        except Exception as e:
            checks.append({
                "id": "stale_ref", "ok": False, "severity": "error",
                "title": "Reference-data edits not yet propagated",
                "detail": f"check failed: {e}", "items": [],
            })

        # ------------------------------------------------------------------
        # 3. source_missing: for dashboard dates older than 24 hours,
        #    check the daily-expected sources (RR, CALL) actually delivered raw
        #    data into hist_rr / hist_call. (Checking drv_outlook_action instead
        #    gave false positives: a quiet day with no emitted actions looked
        #    identical to a missing file.)
        #    Event-driven (ETFCHG, IICHG) and weekly sources (ETF, II, SSS, PS) are excluded.
        # ------------------------------------------------------------------
        try:
            recent_dates = [
                r[0] for r in s.execute(text("""
                    SELECT DISTINCT as_of_date FROM drv_dash
                    WHERE as_of_date < CURRENT_DATE - INTERVAL '1 day'
                      AND as_of_date NOT IN (SELECT holiday_date FROM ref_holiday)
                    ORDER BY as_of_date DESC LIMIT :n
                """), {"n": _RECENT_DATE_WINDOW}).fetchall()
            ]
            # Only check daily sources (RR = daily risk range, CALL = manual daily)
            # Exclude event-driven (ETFCHG, IICHG) and less-frequent (ETF, II, SSS, PS)
            daily_sources = ['RR', 'CALL']
            missing_items = []
            for d in recent_dates:
                # A source is "present" when its raw feed delivered any row for
                # the date, not when it emitted an action (a quiet day emits none).
                got = set()
                for _src, _tbl in (('RR', 'hist_rr'), ('CALL', 'hist_call')):
                    hit = s.execute(text(
                        f"SELECT 1 FROM {_tbl} WHERE snapshot_date = :d LIMIT 1"
                    ), {"d": d}).first()
                    if hit:
                        got.add(_src)
                miss = sorted(set(daily_sources) - got)
                if miss:
                    date_str = d.isoformat() if hasattr(d, "isoformat") else str(d)
                    missing_items.append({
                        "date": date_str,
                        "missing_sources": miss,
                        "label": f"{date_str}: missing {', '.join(miss)}",
                    })
            checks.append({
                "id": "source_missing",
                "ok": len(missing_items) == 0,
                "severity": "error" if missing_items else "ok",
                "title": "Missing daily sources (24+ hours old)",
                "detail": (f"{len(missing_items)} date(s) older than 24 hours missing RR or CALL â€” "
                           f"investigate scheduler or file delivery"
                           if missing_items else
                           "All daily sources (RR, CALL) present for dates older than 24 hours."),
                "items": missing_items,
            })
        except Exception as e:
            checks.append({
                "id": "source_missing", "ok": False, "severity": "error",
                "title": "Source missing for recent dates",
                "detail": f"check failed: {e}", "items": [],
            })

        # ------------------------------------------------------------------
        # 4. scheduler_idle: no file processed in the last N hours
        # ------------------------------------------------------------------
        try:
            row = s.execute(text("""
                SELECT MAX(processed_at) FROM meta_file_processed
            """)).first()
            last_file_dt = row[0] if row and row[0] else None
            cutoff = datetime.now() - timedelta(hours=_SCHEDULER_HEARTBEAT_HOURS)
            ok = last_file_dt is not None and last_file_dt >= cutoff
            checks.append({
                "id": "scheduler_idle",
                "ok": ok,
                "severity": "warning" if not ok else "ok",
                "title": "ETL scheduler heartbeat",
                "detail": (f"No file processed in the last {_SCHEDULER_HEARTBEAT_HOURS}h"
                           f" (last: {last_file_dt.isoformat() if last_file_dt else 'never'})"
                           if not ok else
                           f"Last file processed {last_file_dt.isoformat()}"),
                "items": [],
            })
        except Exception as e:
            checks.append({
                "id": "scheduler_idle", "ok": False, "severity": "error",
                "title": "ETL scheduler heartbeat",
                "detail": f"check failed: {e}", "items": [],
            })

    overall_ok = all(c["ok"] for c in checks)
    n_warn = sum(1 for c in checks if not c["ok"])
    return {
        "ok": overall_ok,
        "n_warnings": n_warn,
        "summary": "All checks passing." if overall_ok else f"{n_warn} warning(s)",
        "checks": checks,
        "checked_at": datetime.now().isoformat(),
    }


@router.get("/api/warnings")
def get_warnings():
    """The single warnings feed for the topbar badge (warning_badge.js).

    Aggregates every warning source into one list of {id, level, title, items}:
      - recent ETL failures      (meta_etl_run)
      - recent derive failures   (meta_derived_run)
      - the meta_warning table   (derive-discovered / per-screen warnings)
      - the derive-status checks (stale ref, missing sources, scheduler idle)
    """
    warnings = []
    with session_scope() as s:
        # A) Recent ETL failures (last 24 hours)
        try:
            rows = s.execute(text("""
                SELECT file_type, error_msg
                FROM meta_etl_run
                WHERE status = 'error' AND started_at > NOW() - INTERVAL '24 hours'
                ORDER BY started_at DESC LIMIT 10
            """)).fetchall()
            if rows:
                warnings.append({
                    "id": "etl_error",
                    "level": "error",
                    "title": f"{len(rows)} ETL failure(s)",
                    "items": [{"label": r[0], "detail": r[1] or ''} for r in rows]
                })
        except Exception:
            pass

        # B) Recent derive failures (last 24 hours)
        try:
            rows = s.execute(text("""
                SELECT target_table, error_msg
                FROM meta_derived_run
                WHERE status = 'error' AND started_at > NOW() - INTERVAL '24 hours'
                ORDER BY started_at DESC LIMIT 10
            """)).fetchall()
            if rows:
                warnings.append({
                    "id": "derive_error",
                    "level": "error",
                    "title": f"{len(rows)} derive failure(s)",
                    "items": [{"label": r[0], "detail": r[1] or ''} for r in rows]
                })
        except Exception:
            pass

        # C) meta_warning table - derive-discovered / per-screen warnings
        try:
            from etl.warnings import get_warnings as _meta_warnings
            for w in _meta_warnings(s):
                warnings.append({
                    "id": "mw-" + str(w["id"]),
                    "level": "error" if w.get("severity") == "error" else "warning",
                    "title": w.get("message") or w.get("code") or "Warning",
                    "items": [],
                })
        except Exception:
            pass

        # C.5) Check for missing tos_symbol in hist_rr (not defined in ref_rrt)
        try:
            null_count = s.execute(text("""
                SELECT COUNT(*) FROM hist_rr WHERE tos_symbol IS NULL
            """)).scalar() or 0
            if null_count > 0:
                warnings.append({
                    "id": "hist_rr_missing_tos_symbol",
                    "level": "warning",
                    "title": f"{null_count} RR row(s) missing tos_symbol",
                    "items": [{"label": f"{null_count} rows without TOS symbol mapping (not defined in ref_rrt)"}]
                })
        except Exception:
            pass

    # D) Derive-status health checks (stale ref, missing sources, scheduler idle)
    try:
        ds = get_derive_status()
        for c in ds.get("checks", []):
            if c.get("ok"):
                continue
            warnings.append({
                "id": c.get("id"),
                "level": c.get("severity") or "warning",
                "title": c.get("title") or c.get("id"),
                "items": [{"label": (it.get("label") or it.get("date") or "")}
                          for it in (c.get("items") or [])][:5],
            })
    except Exception:
        pass

    return warnings


class RebuildRequest(BaseModel):
    days: Optional[int] = None       # rebuild last N dashboard dates
    date: Optional[str] = None       # or one specific date (YYYY-MM-DD)


@router.post("/api/admin/rebuild")
def post_admin_rebuild(req: RebuildRequest):
    """
    Rebuild drv_outlook_action + drv_actionable for either:
      - the last N distinct dashboard dates (req.days), or
      - a single specific date (req.date YYYY-MM-DD).

    Inline / blocking. For each date, derive_outlook_action is called first,
    then derive_actionable. Failures on one date don't stop the others.
    Returns per-date counts.
    """
    if not req.days and not req.date:
        raise HTTPException(status_code=400, detail="Provide either 'days' or 'date'")
    if req.days and req.date:
        raise HTTPException(status_code=400, detail="Provide 'days' OR 'date', not both")
    if req.days is not None and (req.days < 1 or req.days > 90):
        raise HTTPException(status_code=400, detail="'days' must be in [1, 90]")

    # Resolve target dates
    target_dates: list = []
    with session_scope() as s:
        if req.date:
            try:
                target_dates = [datetime.strptime(req.date, "%Y-%m-%d").date()]
            except ValueError:
                raise HTTPException(status_code=400, detail="'date' must be YYYY-MM-DD")
        else:
            rows = s.execute(text("""
                SELECT DISTINCT as_of_date FROM drv_dash
                ORDER BY as_of_date DESC LIMIT :n
            """), {"n": req.days}).fetchall()
            target_dates = [r[0] for r in rows]

    if not target_dates:
        return {"ok": True, "rebuilt": [], "summary": "No dates to rebuild."}

    # Imports kept inline to avoid pulling derive at module load â€” these are
    # heavy imports that touch many tables, and the route is rarely called.
    from etl.derive_outlook_action import derive_outlook_action
    from etl.derive_actionable import derive_actionable

    rebuilt = []
    n_ok = 0
    for d in target_dates:
        entry = {"date": d.isoformat(), "ok": False,
                 "drv_outlook_action_rows": 0, "drv_actionable_rows": 0,
                 "error": None}
        try:
            with session_scope() as s:
                entry["drv_outlook_action_rows"] = derive_outlook_action(s, d, None)
                entry["drv_actionable_rows"] = derive_actionable(s, d)
                entry["ok"] = True
                n_ok += 1
        except Exception as e:
            entry["error"] = str(e)[:300]
        rebuilt.append(entry)

    return {
        "ok": n_ok == len(target_dates),
        "rebuilt": rebuilt,
        "summary": f"Rebuilt {n_ok}/{len(target_dates)} date(s).",
    }


class BackfillRRRequest(BaseModel):
    days: int = 365   # calendar days back from today


@router.post("/api/admin/backfill-drv-rr")
def post_backfill_drv_rr(req: BackfillRRRequest):
    """Populate drv_rr for every weekday in the last N calendar days that
    has no entry yet. Blocking. Safe to re-run (skips existing dates)."""
    from datetime import date
    if req.days < 1 or req.days > 1825:
        raise HTTPException(400, "'days' must be in [1, 1825]")
    d_end   = date.today()
    d_start = d_end - timedelta(days=req.days)
    from etl.derive import backfill_drv_rr
    result = backfill_drv_rr(d_start, d_end)
    return {"ok": result["errors"] == 0, **result,
            "range": f"{d_start} → {d_end}"}


class BackfillQuoteRequest(BaseModel):
    days: int = 365


@router.post("/api/admin/backfill-drv-quote")
def post_backfill_drv_quote(req: BackfillQuoteRequest):
    """Populate drv_quote for every weekday in the last N calendar days that
    has no entry yet. Blocking. Safe to re-run (skips existing dates)."""
    from datetime import date
    if req.days < 1 or req.days > 1825:
        raise HTTPException(400, "'days' must be in [1, 1825]")
    d_end   = date.today()
    d_start = d_end - timedelta(days=req.days)
    from etl.derive import backfill_drv_quote
    result = backfill_drv_quote(d_start, d_end)
    return {"ok": result["errors"] == 0, **result,
            "range": f"{d_start} → {d_end}"}


# =============================================================================
# Symbol comparison (master list vs all tables)
# =============================================================================

def _is_non_equity(sym: str) -> bool:
    return sym.startswith('^') or sym.endswith('=F') or sym.endswith('=X')


@router.get("/api/symbols/comparison")
def get_symbols_comparison(exclude_non_equity: bool = True):
    """
    Compare symbols across all hist_* tables using LATEST snapshots (not a fixed date).

    Returns ONLY missing symbols:
      - tl_date: latest date in hist_tl
      - tl_count: count of TL symbols
      - missing_by_source: list of {source, date, symbols, count} for symbols in other tables but NOT in TL

    Y and RR symbols are compared using tos_symbol (mapped via RRT table).
    TL, TW, TO, TD symbols are compared directly (TOS exports, no mapping needed).
    """
    result = {
        "tl_date": None,
        "tl_count": 0,
        "missing_by_source": [],
    }

    with session_scope() as s:
        # Get latest TL date and symbols
        tl_date_row = s.execute(text("SELECT MAX(snapshot_date) FROM hist_tl")).first()
        tl_date = tl_date_row[0] if tl_date_row and tl_date_row[0] else None
        result["tl_date"] = tl_date.isoformat() if tl_date else None

        if tl_date:
            # TL: Get direct symbols (TOS export format)
            tl_rows = s.execute(text("""
                SELECT DISTINCT symbol
                FROM hist_tl
                WHERE snapshot_date = :d
                ORDER BY symbol
            """), {"d": tl_date}).fetchall()
            tl_symbols = sorted(set(r[0] for r in tl_rows if r[0]))
            result["tl_count"] = len(tl_symbols)

            # Check core tables (TW, TO, TD, Y) with their latest dates
            source_names = {"tw": "TW", "to": "TO", "td": "TD", "y": "Y"}
            for table, key in [("hist_tw", "tw"), ("hist_to", "to"), ("hist_td", "td"), ("hist_y", "y")]:
                # Get latest date for this table
                table_date_row = s.execute(text(f"SELECT MAX(snapshot_date) FROM {table}")).first()
                table_date = table_date_row[0] if table_date_row and table_date_row[0] else None

                if table_date:
                    if key == "y":
                        # Y: Use tos_symbol column (already mapped via RRT during load)
                        rows = s.execute(text(f"""
                            SELECT DISTINCT COALESCE(tos_symbol, symbol) AS symbol
                            FROM {table}
                            WHERE snapshot_date = :d ORDER BY symbol
                        """), {"d": table_date}).fetchall()
                        y_symbols = sorted(set(r[0] for r in rows if r[0]))

                        # Missing: symbols in Y (tos_symbol) not in TL
                        missing = sorted(set(y_symbols) - set(tl_symbols))

                        # Filter out contract symbols
                        contract_symbols = {
                            '/6B', '/6C', '/6E', '/6J', '/6M', '/6N', '/6S', '/6Z',
                            '/BZ', '/CL', '/ES', '/GC', '/HG', '/NG', '/NQ', '/SI', '/YM', '/ZB', '/ZF', '/ZN', '/ZT',
                        }
                        missing = [s for s in missing if s not in contract_symbols]
                    else:
                        # TW, TO, TD: TOS exports, direct comparison (no RRT mapping)
                        rows = s.execute(text(f"""
                            SELECT DISTINCT symbol
                            FROM {table}
                            WHERE snapshot_date = :d
                            ORDER BY symbol
                        """), {"d": table_date}).fetchall()
                        table_symbols = sorted(set(r[0] for r in rows if r[0]))
                        missing = sorted(set(table_symbols) - set(tl_symbols))

                    # For Y: filter out contract symbols (those with contracts='Y' flag)
                    if key == "y":
                        # Symbols that are futures contracts with dynamic contract months
                        contract_symbols = {
                            '/6B', '/6C', '/6E', '/6J', '/6M', '/6N', '/6S', '/6Z',
                            '/BZ', '/CL', '/ES', '/GC', '/HG', '/NG', '/NQ', '/SI', '/YM', '/ZB', '/ZF', '/ZN', '/ZT',
                        }
                        # Don't show contract symbols as missing (they're expected to be different)
                        missing = [s for s in missing if s not in contract_symbols]

                    if exclude_non_equity:
                        missing = [s for s in missing if not _is_non_equity(s)]

                    if missing:
                        result["missing_by_source"].append({
                            "source": source_names[key],
                            "date": table_date.isoformat(),
                            "symbols": missing,
                            "count": len(missing),
                        })

            # Check all other hist_* tables for symbols NOT in TL
            other_tables = [
                ("hist_rr", "RR"),
                ("hist_call", "CALL"),
                ("hist_etf", "ETF"),
                ("hist_ii", "II"),
                ("hist_sss", "SSS"),
                ("hist_ps", "PS"),
                ("hist_etfchg", "ETFCHG"),
                ("hist_iichg", "IICHG"),
                ("hist_f", "FIDELITY"),
                ("hist_cs", "SCHWAB"),
            ]

            for table, source_name in other_tables:
                try:
                    # Get latest date for this table
                    date_col = "event_date" if table in ("hist_etfchg", "hist_iichg") else "snapshot_date"
                    table_date_row = s.execute(text(f"SELECT MAX({date_col}) FROM {table}")).first()
                    table_date = table_date_row[0] if table_date_row and table_date_row[0] else None

                    if table_date:
                        if table == "hist_rr":
                            # RR: Use tos_symbol column (already mapped via RRT during load)
                            rows = s.execute(text(f"""
                                SELECT DISTINCT COALESCE(tos_symbol, symbol) AS symbol
                                FROM {table}
                                WHERE {date_col} = :d ORDER BY symbol
                            """), {"d": table_date}).fetchall()
                            rr_symbols = sorted(set(r[0] for r in rows if r[0]))

                            # Missing: symbols in RR (tos_symbol) not in TL
                            missing = sorted(set(rr_symbols) - set(tl_symbols))
                        else:
                            rows = s.execute(text(f"""
                                SELECT DISTINCT symbol FROM {table}
                                WHERE {date_col} = :d ORDER BY symbol
                            """), {"d": table_date}).fetchall()

                            table_symbols = sorted(set(r[0] for r in rows if r[0]))
                            # Find symbols NOT in TL
                            missing = sorted(set(table_symbols) - set(tl_symbols))

                        if exclude_non_equity:
                            missing = [s for s in missing if not _is_non_equity(s)]
                        if missing:
                            result["missing_by_source"].append({
                                "source": source_name,
                                "date": table_date.isoformat(),
                                "symbols": missing,
                                "count": len(missing),
                            })
                except Exception:
                    # Table doesn't exist or query failed
                    pass

    return result

