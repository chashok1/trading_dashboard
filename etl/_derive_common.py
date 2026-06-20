"""
Shared helpers for the derive pipeline.

Extracted from etl/derive.py on 2026-05-12 so that both etl/derive.py and
etl/derive_v2.py can import them without creating a circular dependency.

Building blocks:
  * _open_drv_run  — insert a meta_derived_run row with status='running'
  * _close_drv_run — update the row with rows_built, status, and any error
  * _wrap          — decorator that opens the run, calls the deriver, closes
                     the run, and propagates exceptions

TASK_56 additions (2026-06-17) — single definitions used by all derive modules:
  * _clean(v)          — Excel-style numeric coercion to float (NaN/blank → 0)
  * _safe_div(n, d)    — n / d with None / zero-guard (returns None on missing)
  * _load_outlook_weights(session, sheet)  — ref_param outlook weight map
  * _outlook_to_weight(outlook, modifier, wt_map)  — resolve weight with bench adj
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.db import get_table

log = logging.getLogger("etl.derive")


# =============================================================================
# TASK_56 — consolidated utilities (single definition, used by all derive modules)
# =============================================================================

def _clean(v) -> float:
    """Excel-style coercion: NaN / None / blank / error strings → 0.0."""
    if v is None:
        return 0.0
    if isinstance(v, str):
        s = v.strip()
        if s in ("", "NaN", "<empty>", "#N/A", "#REF!", "#VALUE!"):
            return 0.0
        try:
            return float(s.replace(",", ""))
        except ValueError:
            return 0.0
    try:
        f = float(v)
        return 0.0 if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return 0.0


def _safe_div(num, den):
    """num / den with None / zero-guard.  Returns None when inputs are missing."""
    try:
        n = float(num) if num is not None else None
        d = float(den) if den is not None else None
        if n is None or d is None or d == 0:
            return None
        return n / d
    except (TypeError, ValueError):
        return None


def _load_outlook_weights(session: Session,
                          sheet: str = "outlook") -> dict[str, float]:
    """Return {OUTLOOK_TEXT_UPPER: weight} from ref_param for the given sheet.

    Defaults to sheet='outlook'; pass sheet='outlook_rr' for RR variant.
    Provides fallback defaults (BULLISH=3, BEARISH=-3, NEUTRAL=0) so callers
    work even before the Parm workbook has been loaded.
    """
    rows = session.execute(
        text("SELECT param_name, value FROM ref_param WHERE sheet = :s"),
        {"s": sheet}
    ).fetchall()
    out: dict[str, float] = {}
    for name, val in rows:
        try:
            out[str(name).upper()] = float(val) if val is not None else 0.0
        except (TypeError, ValueError):
            continue
    out.setdefault("BULLISH",  3.0)
    out.setdefault("BEARISH", -3.0)
    out.setdefault("NEUTRAL",  0.0)
    return out


def _outlook_to_weight(outlook: Optional[str], modifier: Optional[str],
                       wt_map: dict[str, float]) -> Optional[float]:
    """Convert an outlook string to a numeric weight.

    Applies a /3 reduction when modifier contains 'bench'.
    Returns None for empty/missing outlooks; 0.0 for unrecognised strings.
    """
    if not outlook:
        return None
    base = wt_map.get(str(outlook).upper())
    if base is None:
        return 0.0
    if modifier and "bench" in str(modifier).lower():
        return base / 3.0
    return base


# =============================================================================
# D1 — change_str normalization: single source of truth for LONG/SHORT→BULLISH/BEARISH
# Both the Python helper and the SQL generator live here so callers never diverge.
# =============================================================================

def normalize_change_str(change_str: Optional[str]) -> Optional[str]:
    """Map etfchg/iichg change_str into hist_etf-style outlook tokens.

    LONG → BULLISH, SHORT → BEARISH, NEUTRAL → NEUTRAL.
    Case-insensitive; returns the input unchanged for any other value.
    Canonical Python version — SQL equivalent: normalize_change_str_sql().
    """
    if not change_str:
        return change_str
    cs = change_str.strip().upper()
    if cs == "LONG":
        return "BULLISH"
    if cs == "SHORT":
        return "BEARISH"
    if cs == "NEUTRAL":
        return "NEUTRAL"
    return change_str


def normalize_change_str_sql(col_expr: str) -> str:
    """Return a SQL CASE expression that maps change_str column to outlook tokens.

    Mirrors normalize_change_str() exactly — update both together if the
    mapping ever changes. Used inline in CTEs that run wholly in the DB.
    Canonical SQL version — Python equivalent: normalize_change_str().
    """
    return (
        f"CASE UPPER(COALESCE({col_expr},''))"
        " WHEN 'LONG'    THEN 'BULLISH'"
        " WHEN 'SHORT'   THEN 'BEARISH'"
        " WHEN 'NEUTRAL' THEN 'NEUTRAL'"
        f" ELSE {col_expr}"
        " END"
    )


def position_ceiling(session: Session, as_of_date: date) -> date:
    """Return the snapshot_date ceiling for F/CS position carry-forward.

    On the LIVE anchor (as_of_date == MAX(export_date) FROM hist_td) the ceiling
    is today, so a position file exported on a non-trading day (weekend/holiday,
    snapshot_date > D) is included.  On historical re-derives the ceiling stays
    at as_of_date to prevent look-ahead.

    Mirrors the pattern used by _derive_quote_impl (derive.py:1376-1377).
    """
    row = session.execute(
        text("SELECT MAX(export_date) FROM hist_td")
    ).first()
    anchor = row[0] if row and row[0] else None
    return date.today() if (anchor is not None and as_of_date == anchor) else as_of_date


def _open_drv_run(session: Session, target: str, as_of_date: date,
                  parent_run_id: Optional[int] = None) -> int:
    """Insert a meta_derived_run row and return its run_id."""
    table = get_table("meta_derived_run")
    rid = session.execute(
        table.insert().values(
            as_of_date=as_of_date,
            target_table=target,
            status="running",
            parent_run_id=parent_run_id,
        ).returning(table.c.run_id)
    ).scalar_one()
    return rid


def _close_drv_run(session: Session, run_id: int, *, rows_built: int = 0,
                   status: str = "success", error_msg: Optional[str] = None) -> None:
    """Update a meta_derived_run row with the final state."""
    if not run_id:
        return
    table = get_table("meta_derived_run")
    session.execute(
        table.update()
        .where(table.c.run_id == run_id)
        .values(
            finished_at=datetime.now(),
            rows_built=rows_built,
            status=status,
            error_msg=error_msg,
        )
    )


def _wrap(target: str, fn):
    """Decorator: open run, call fn, close run, propagate exceptions."""
    def runner(session: Session, as_of_date: date, parent_run_id: Optional[int] = None):
        rid = _open_drv_run(session, target, as_of_date, parent_run_id)
        try:
            n = fn(session, as_of_date, rid)
            _close_drv_run(session, rid, rows_built=n)
            log.info("%s @ %s: %d rows", target, as_of_date, n)
            return n
        except Exception as e:
            _close_drv_run(session, rid, rows_built=0, status="error",
                           error_msg=str(e)[:500])
            raise
    return runner
