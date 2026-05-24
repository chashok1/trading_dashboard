"""Staleness detection + auto-heal for drv_actionable.

A drv_actionable row for date D is *stale* when raw outlook-source data with
an effective snapshot on/before D was loaded AFTER that row was last derived.
Periodic sources (PS/ETF/II/SSS) carry forward, so a late or out-of-order
load of one week's file invalidates every later date.

This module provides:
  * find_stale_actionable_dates() - cheap metadata check, returns the dates.
  * run_stale_heal()              - re-derives only the dates flagged stale.

run_stale_heal is wired to run daily (etl/scheduler.py) and on app startup
(api/main.py). The same check powers the Actionable-screen banner and the
File Monitor "Stale derives" list.
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import text

from etl.db import session_scope

log = logging.getLogger(__name__)

DEFAULT_LOOKBACK_DAYS = 30

# Outlook-source raw tables that feed drv_outlook_action -> drv_actionable.
# (table, date_column) - etfchg/iichg are change-event feeds keyed by event_date.
_OUTLOOK_HIST = [
    ("hist_rr", "snapshot_date"),
    ("hist_call", "snapshot_date"),
    ("hist_etf", "snapshot_date"),
    ("hist_etfchg", "event_date"),
    ("hist_ii", "snapshot_date"),
    ("hist_iichg", "event_date"),
    ("hist_sss", "snapshot_date"),
    ("hist_ps", "snapshot_date"),
]


def get_lookback_days(session, default: int = DEFAULT_LOOKBACK_DAYS) -> int:
    """Read staleness_lookback_days from ref_settings; fall back to default."""
    try:
        row = session.execute(text(
            "SELECT setting_value FROM ref_settings "
            "WHERE setting_name = 'staleness_lookback_days'"
        )).first()
        return int(row[0]) if row and row[0] else default
    except Exception:
        return default


def find_stale_actionable_dates(session, lookback_days: int | None = None) -> list[date]:
    """Return the ascending list of drv_actionable dates (within the lookback
    window) whose newest contributing outlook-source row was loaded after the
    row's computed_at timestamp."""
    if lookback_days is None:
        lookback_days = get_lookback_days(session)

    derived = session.execute(text("""
        SELECT as_of_date, MAX(computed_at) AS ca
        FROM drv_actionable
        WHERE as_of_date >= CURRENT_DATE - :n
        GROUP BY as_of_date
        ORDER BY as_of_date
    """), {"n": int(lookback_days)}).all()
    if not derived:
        return []

    # Newest loaded_at per snapshot date across all outlook-source tables.
    # Unfiltered by date on purpose: a backfilled OLD snapshot still
    # invalidates later dates, and distinct snapshot dates are bounded.
    snap_loaded: dict = {}
    for tbl, dcol in _OUTLOOK_HIST:
        try:
            rows = session.execute(text(
                f"SELECT {dcol} AS sd, MAX(loaded_at) AS ml "
                f"FROM {tbl} GROUP BY {dcol}"
            )).all()
        except Exception:
            log.exception("staleness: scan failed for %s (continuing)", tbl)
            continue
        for sd, ml in rows:
            if sd is None or ml is None:
                continue
            cur = snap_loaded.get(sd)
            if cur is None or ml > cur:
                snap_loaded[sd] = ml

    pairs = sorted(snap_loaded.items())  # ascending by snapshot date
    stale: list[date] = []
    for d, ca in derived:
        if ca is None:
            continue
        threshold = None
        for sd, ml in pairs:
            if sd > d:
                break
            if threshold is None or ml > threshold:
                threshold = ml
        if threshold is not None and threshold > ca:
            stale.append(d)
    return stale


def run_stale_heal(lookback_days: int | None = None) -> dict:
    """Find stale drv_actionable dates and re-derive only those.

    Idempotent and safe to call repeatedly: on a normal day it finds nothing
    and re-derives nothing. Each date is re-derived in its own session so one
    failure does not abort the rest."""
    from etl.derive import derive_all  # lazy import - avoids import cycle

    with session_scope() as s:
        stale = find_stale_actionable_dates(s, lookback_days)

    healed: list[str] = []
    failed: list[str] = []
    for d in stale:
        try:
            with session_scope() as s:
                derive_all(s, d)
            healed.append(d.isoformat())
        except Exception:
            log.exception("stale-heal: derive_all failed for %s (continuing)", d)
            failed.append(d.isoformat())

    if stale:
        log.info("stale-heal: %d stale, %d healed, %d failed",
                 len(stale), len(healed), len(failed))
    else:
        log.debug("stale-heal: nothing stale")

    return {
        "stale": [d.isoformat() for d in stale],
        "healed": healed,
        "failed": failed,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    result = run_stale_heal()
    print(result)
