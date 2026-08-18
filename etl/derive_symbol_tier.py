"""
drv_symbol_tier — daily export-frequency tier per symbol.

2026-08-18, user-directed design (TOS-export right-sizing analysis, no task
number). Answers "how often does this symbol need fresh data" so the TOS/
Yfinance export automation can eventually export Tier 1 daily and Tier 2
weekly instead of exporting everything daily regardless of relevance.

tier=1 if ANY of these are true (checked in this priority order --
whichever fires first becomes `reason`):
  1. held               — a real position right now (hist_cs/hist_f, latest
                           snapshot <= D, qty <> 0).
  2. active_90d          — drv_actionable.consolidated_action was non-blank
                           for this symbol on any date in [D-90, D].
  3. hedgeye_directional_90d — a directional (BULLISH/BEARISH, not NEUTRAL)
                           Hedgeye call/stance/side/outlook in [D-90, D],
                           across hist_call, hist_hedgeye_stance,
                           hist_call_top5, hist_rta, hist_etfchg, hist_rr.
                           hist_sss_change is deliberately excluded — its
                           'action' column is add/remove list membership,
                           not a directional stance.
Else tier=2, reason='dormant'.

Idempotent: DELETE WHERE as_of_date=D then INSERT. Purely descriptive
today — nothing yet reads this table to change TOS export behavior; that's
a separate, later piece (see conversation this was designed in).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import _wrap
from etl.db import replace_for_date

log = logging.getLogger(__name__)

ACTIVE_WINDOW_DAYS = 90

# Hedgeye tables that carry some notion of directional stance, and how to
# read "directional, not neutral" out of each one's own vocabulary. Each
# entry: (table, date_column, directional_sql_predicate). hist_hedgeye_stance
# has no neutral value at all, so its predicate is just TRUE.
_HEDGEYE_DIRECTIONAL_SOURCES = [
    ("hist_call", "snapshot_date", "UPPER(outlook) IN ('BULLISH', 'BEARISH')"),
    ("hist_hedgeye_stance", "snapshot_date", "TRUE"),
    ("hist_call_top5", "snapshot_date", "LOWER(side) IN ('long', 'short')"),
    ("hist_rta", "snapshot_date", "LOWER(side) IN ('long', 'short')"),
    ("hist_etfchg", "event_date", "LOWER(outlook) IN ('long', 'short')"),
    ("hist_rr", "snapshot_date", "UPPER(outlook) IN ('BULLISH', 'BEARISH')"),
]


def _fetch_held(session: Session, d: date) -> set:
    rows = session.execute(text("""
        SELECT DISTINCT symbol FROM hist_cs
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
          AND qty <> 0
        UNION
        SELECT DISTINCT symbol FROM hist_f
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
          AND qty <> 0
    """), {"d": d}).fetchall()
    return {r[0] for r in rows if r[0]}


def _fetch_active_90d(session: Session, d: date) -> set:
    rows = session.execute(text("""
        SELECT DISTINCT tos_symbol FROM drv_actionable
        WHERE as_of_date BETWEEN :start AND :d
          AND consolidated_action IS NOT NULL AND consolidated_action <> ''
    """), {"start": d - timedelta(days=ACTIVE_WINDOW_DAYS), "d": d}).fetchall()
    return {r[0] for r in rows if r[0]}


def _fetch_hedgeye_directional_90d(session: Session, d: date) -> set:
    start = d - timedelta(days=ACTIVE_WINDOW_DAYS)
    out: set = set()
    for table, date_col, predicate in _HEDGEYE_DIRECTIONAL_SOURCES:
        rows = session.execute(text(f"""
            SELECT DISTINCT tos_symbol FROM {table}
            WHERE {date_col} BETWEEN :start AND :d
              AND tos_symbol IS NOT NULL
              AND ({predicate})
        """), {"start": start, "d": d}).fetchall()
        out.update(r[0] for r in rows if r[0])
    return out


def _derive_symbol_tier_impl(session: Session, as_of_date: date, run_id: int) -> int:
    universe = [r[0] for r in session.execute(
        text("SELECT tos_symbol FROM drv_symbols WHERE as_of_date = :d"),
        {"d": as_of_date},
    ).fetchall()]
    if not universe:
        return replace_for_date(session, "drv_symbol_tier", "as_of_date", as_of_date, [])

    held = _fetch_held(session, as_of_date)
    active_90d = _fetch_active_90d(session, as_of_date)
    hedgeye_90d = _fetch_hedgeye_directional_90d(session, as_of_date)

    out_rows = []
    for sym in universe:
        if sym in held:
            tier, reason = 1, "held"
        elif sym in active_90d:
            tier, reason = 1, "active_90d"
        elif sym in hedgeye_90d:
            tier, reason = 1, "hedgeye_directional_90d"
        else:
            tier, reason = 2, "dormant"
        out_rows.append({
            "as_of_date": as_of_date,
            "tos_symbol": sym,
            "tier": tier,
            "reason": reason,
        })

    return replace_for_date(session, "drv_symbol_tier", "as_of_date", as_of_date, out_rows)


derive_symbol_tier = _wrap("drv_symbol_tier", _derive_symbol_tier_impl)
