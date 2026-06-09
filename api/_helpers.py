"""Shared helpers, dependencies, and constants used by multiple routers.

Extracted from the original api/main.py monolith. Each helper here is used by
at least two routers; helpers used by only one router stayed with that router.
"""
from __future__ import annotations

from datetime import date, datetime, time as _dtime, timedelta
from functools import lru_cache as _lru_cache  # noqa: F401  (kept for parity)
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import text

from etl.db import session_scope


# -----------------------------------------------------------------------------
# SQL Identifier validation (prevent injection)
# -----------------------------------------------------------------------------

def safe_ident(name: str, allowed: set) -> str:
    """Validate identifier is in the allowed list; raise ValueError if not."""
    if name not in allowed:
        raise ValueError(f"'{name}' is not a valid column name")
    return name


# -----------------------------------------------------------------------------
# Filesystem constants
# -----------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"


# -----------------------------------------------------------------------------
# Date resolver — used by dash, ref, rules endpoints
# -----------------------------------------------------------------------------

def _resolve_date(d: Optional[str]) -> date:
    """If date is None, return the default (latest available); else parse
    YYYY-MM-DD.

    The default is the anchor D = MAX(export_date) FROM hist_td (TOSD market
    close): v_available_dates is capped at the anchor, so MAX(as_of_date) there
    IS the anchor. See docs/derive_date_logic.md."""
    if d is None:
        with session_scope() as s:
            row = s.execute(text(
                "SELECT MAX(as_of_date) FROM v_available_dates"
            )).first()
        if not row or row[0] is None:
            raise HTTPException(status_code=404,
                                detail="No data loaded. Run etl/tickers_initial_load.py first.")
        return row[0]
    try:
        return datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400,
                            detail="date must be YYYY-MM-DD")


# -----------------------------------------------------------------------------
# Expected market-close date — for the "data is stale" toolbar warning
# -----------------------------------------------------------------------------

def _get_ref_setting(name: str, default: str) -> str:
    """Read a ref_settings value, falling back to `default` on any miss/error."""
    try:
        with session_scope() as s:
            row = s.execute(text(
                "SELECT setting_value FROM ref_settings WHERE setting_name = :n"
            ), {"n": name}).first()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default


def expected_market_close_date(now: Optional[datetime] = None) -> date:
    """Most recent COMPLETED US market session as of `now`, in market time.

    A session counts as complete once the wall clock passes the cutoff
    (ref_settings.market_close_cutoff, default '16:30') in the market timezone
    (ref_settings.market_timezone, default 'America/New_York'). So Friday after
    16:30 ET → Friday; Sat/Sun → Friday; Monday before 16:30 ET → Friday.

    Weekday-based: it does NOT account for market holidays, so on a holiday it
    may name a session that didn't trade until the next real session loads. On
    Windows, accurate tz handling needs the `tzdata` package; without it this
    falls back to the server's local clock."""
    cutoff_str = _get_ref_setting("market_close_cutoff", "16:30")
    tzname = _get_ref_setting("market_timezone", "America/New_York")
    try:
        hh, mm = (int(x) for x in str(cutoff_str).split(":")[:2])
    except Exception:
        hh, mm = 16, 30
    if now is None:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo(tzname))
        except Exception:
            now = datetime.now()  # fallback: server local clock
    # Market holidays (recent window — we only ever walk back a few days).
    holidays: set = set()
    try:
        with session_scope() as s:
            rows = s.execute(text(
                "SELECT holiday_date FROM ref_holiday "
                "WHERE holiday_date >= :lo AND holiday_date <= :hi"
            ), {"lo": now.date() - timedelta(days=20), "hi": now.date()}).all()
        holidays = {r[0] for r in rows}
    except Exception:
        holidays = set()

    def _is_session(dd: date) -> bool:
        return dd.weekday() < 5 and dd not in holidays

    d = now.date()
    # Today qualifies only if it's a trading day AND we're past the cutoff.
    if _is_session(d) and (now.hour, now.minute) >= (hh, mm):
        return d
    # Otherwise the latest completed session is the most recent prior trading day.
    d -= timedelta(days=1)
    while not _is_session(d):
        d -= timedelta(days=1)
    return d


def anchor_date_and_status(now: Optional[datetime] = None) -> dict:
    """Resolve the loaded anchor (MAX(export_date) FROM hist_td) and whether it
    is behind the expected market close. Used by GET /api/anchor-status."""
    with session_scope() as s:
        row = s.execute(text("SELECT MAX(export_date) FROM hist_td")).first()
    anchor = row[0] if row and row[0] else None
    expected = expected_market_close_date(now)
    is_stale = False
    message = None
    if anchor is None:
        is_stale = True
        message = "No TOSD (hist_td) data loaded yet."
    elif anchor < expected:
        is_stale = True
        message = (f"Latest market session ({expected:%a %Y-%m-%d}) not loaded — "
                   f"showing {anchor:%a %Y-%m-%d}. Load that day's "
                   f"TOSD/TOSL/TOSW/Y files.")
    return {
        "anchor_date": anchor.isoformat() if anchor else None,
        "expected_close": expected.isoformat(),
        "is_stale": is_stale,
        "message": message,
    }


# -----------------------------------------------------------------------------
# Table discovery — SQL-driven (information_schema). Replaces hardcoded lists.
# Adding a CREATE TABLE in db/*.sql and re-running schema is enough — no Python
# changes needed for new tables to appear in the dropdowns.
# -----------------------------------------------------------------------------

# Tables hidden from the user-facing dropdowns even though they exist.
# Use sparingly — only for true ops/internal tables that shouldn't be edited.
HIDDEN_TABLES: set = set()


def _list_tables_like(patterns):
    """Query information_schema for public BASE TABLEs matching any pattern."""
    where = " OR ".join(f"table_name LIKE :p{i}" for i in range(len(patterns)))
    params = {f"p{i}": p for i, p in enumerate(patterns)}
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            f"AND ({where}) ORDER BY table_name"
        ), params).all()
    return [r[0] for r in rows if r[0] not in HIDDEN_TABLES]


def _list_views_like(patterns):
    """Same as _list_tables_like but for VIEWs (v_* are views)."""
    where = " OR ".join(f"table_name LIKE :p{i}" for i in range(len(patterns)))
    params = {f"p{i}": p for i, p in enumerate(patterns)}
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'VIEW' "
            f"AND ({where}) ORDER BY table_name"
        ), params).all()
    return [r[0] for r in rows if r[0] not in HIDDEN_TABLES]


def discover_ref_tables():
    """All ref_* tables currently in the public schema."""
    return _list_tables_like(["ref_%"])


def discover_data_tables():
    """All hist_/drv_/meta_/cache_ tables and v_* views — browsable in /explore."""
    base = _list_tables_like(["hist_%", "drv_%", "meta_%", "cache_%"])
    views = _list_views_like(["v_%"])
    return sorted(set(base + views))


# -----------------------------------------------------------------------------
# Data-filter registry (driven by ref_data_filter_logic table)
# -----------------------------------------------------------------------------

# Filter type constants — keep in sync with db/baseline.sql CHECK.
FILTER_EXACT_MATCH         = "EXACT_MATCH"
FILTER_LATEST_BEFORE       = "LATEST_BEFORE"
FILTER_LATEST_ON_OR_BEFORE = "LATEST_ON_OR_BEFORE"
FILTER_WINDOW_30_DAYS      = "WINDOW_30_DAYS"
FILTER_WINDOW_14_DAYS      = "WINDOW_14_DAYS"
FILTER_NO_FILTER           = "NO_FILTER"


def _lookup_filter_rule(session, table_name: str) -> Optional[dict]:
    """Return the ref_data_filter_logic row for this table (or None)."""
    row = session.execute(text("""
        SELECT table_name, filter_type, date_column, window_days, description
        FROM ref_data_filter_logic
        WHERE table_name = :t
    """), {"t": table_name}).mappings().first()
    return dict(row) if row else None


def _apply_filter_rule(session, table, table_name: str, rule: dict, d):
    """Translate a ref_data_filter_logic row into (where_clause, params, description).

    `table` is the SQLAlchemy Table reflection (used only to detect timestamp
    columns that need ::date casting). `d` is the resolved as-of date.
    """
    if not rule:
        # Unknown table — show everything, but no description
        return "", {}, None

    ft = rule["filter_type"]
    date_col = rule["date_column"]
    win = rule["window_days"]

    # NO_FILTER: nothing to do
    if ft == FILTER_NO_FILTER or not date_col:
        return "", {}, "all rows (no date filter applied)"

    # Cast timestamp columns to date for sane comparisons
    is_ts = str(table.columns[date_col].type).startswith("TIMESTAMP")
    date_cast = f"{date_col}::date" if is_ts else date_col

    if ft == FILTER_EXACT_MATCH:
        return (
            f"WHERE {date_cast} = :d",
            {"d": d},
            f"{date_col} = {d.isoformat()} (exact match for as-of date)",
        )

    if ft == FILTER_LATEST_BEFORE:
        max_d = session.execute(
            text(f"SELECT MAX({date_cast}) FROM {table_name} WHERE {date_cast} < :d"),
            {"d": d},
        ).scalar()
        if max_d:
            return (
                f"WHERE {date_cast} = :max_d",
                {"max_d": max_d},
                f"latest {date_col} < {d.isoformat()} (resolved to {max_d.isoformat()})",
            )
        return ("WHERE 1=0", {}, f"no {date_col} < {d.isoformat()} found - empty result")

    if ft == FILTER_LATEST_ON_OR_BEFORE:
        # Special case: for hist_etfchg/hist_iichg, get the absolute latest date in the table
        if table_name in ("hist_etfchg", "hist_iichg"):
            max_d = session.execute(
                text(f"SELECT MAX({date_cast}) FROM {table_name}"),
            ).scalar()
        else:
            max_d = session.execute(
                text(f"SELECT MAX({date_cast}) FROM {table_name} WHERE {date_cast} <= :d"),
                {"d": d},
            ).scalar()
        if max_d:
            return (
                f"WHERE {date_cast} = :max_d",
                {"max_d": max_d},
                f"latest {date_col} = {max_d.isoformat()}",
            )
        return ("WHERE 1=0", {}, f"no data found in {table_name}")

    if ft in (FILTER_WINDOW_30_DAYS, FILTER_WINDOW_14_DAYS):
        from datetime import timedelta as _td
        days = win or (30 if ft == FILTER_WINDOW_30_DAYS else 14)
        d_minus = d - _td(days=days)
        return (
            f"WHERE {date_cast} >= :d_minus AND {date_cast} <= :d",
            {"d": d, "d_minus": d_minus},
            f"{date_col} between {d_minus.isoformat()} and {d.isoformat()} ({days}-day window)",
        )

    # Unknown filter_type — defensive: show everything
    return "", {}, f"unknown filter_type {ft!r} - showing all rows"
