"""Freshness contracts for computed analytics tables (TASK_142).

`daily_health_check.py`'s existing six checks all watch INPUTS (did a file
arrive, is there a gap in raw history). Nothing watched whether a computed
OUTPUT (drv_rule_outcome, drv_factor_snapshot, ...) is still current — a
stale number renders identically to a fresh one. This module reads
`ref_freshness_contract` and answers, per table, "is it current enough".

Breach condition:
    (anchor_date - MAX(date_column)) > (maturity_lag_days + max_lag_days)

`maturity_lag_days` is the *expected* structural lag before a table can ever
be current (e.g. a 20-trading-day forward return needs 20 future days of
price) — without it, tables like drv_rule_outcome would breach every day.
A table with zero rows is always a breach — the cold-start case this
whole task exists to catch.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import text

log = logging.getLogger(__name__)


def get_contracts(session, active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM ref_freshness_contract"
    if active_only:
        sql += " WHERE is_active"
    sql += " ORDER BY table_name"
    rows = session.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]


def check_table_freshness(session, contract: dict, anchor: date) -> dict:
    """Evaluate one contract row against the anchor date. Returns a dict with
    table/as_of/stale/days_over/expected_by/refreshed_by/screen/severity."""
    tbl = contract["table_name"]
    col = contract["date_column"]
    maturity = int(contract["maturity_lag_days"] or 0)
    max_lag = int(contract["max_lag_days"] or 0)
    allowed = maturity + max_lag

    max_date: Optional[date] = None
    try:
        row = session.execute(text(f"SELECT MAX({col})::date FROM {tbl}")).first()
        max_date = row[0] if row else None
    except Exception:
        log.exception("analytics_freshness: could not read %s.%s", tbl, col)
        # A raised DB error (e.g. a mis-seeded table_name) leaves the
        # session's transaction aborted in Postgres — roll back so this
        # contract row's failure doesn't cascade into every later one in
        # the same check_all() call. Missing/unreadable data == stale.
        try:
            session.rollback()
        except Exception:
            pass

    if max_date is None or anchor is None:
        stale = True
        days_over = None
    else:
        lag_days = (anchor - max_date).days
        days_over = lag_days - allowed
        stale = days_over > 0

    return {
        "table": tbl,
        "date_column": col,
        "as_of": max_date.isoformat() if max_date else None,
        "anchor": anchor.isoformat() if anchor else None,
        "maturity_lag_days": maturity,
        "max_lag_days": max_lag,
        "days_over": days_over,
        "stale": stale,
        "refreshed_by": contract["refreshed_by"],
        "screen": contract.get("screen"),
        "severity": contract.get("severity") or "warning",
    }


def check_all(session, anchor: Optional[date] = None) -> list[dict]:
    """Evaluate every active contract row. Lazily resolves the anchor via
    etl.derive.get_anchor_date if not supplied."""
    if anchor is None:
        from etl.derive import get_anchor_date
        anchor = get_anchor_date(session)
    return [check_table_freshness(session, c, anchor)
            for c in get_contracts(session)]


def get_freshness(session, table_name: str, anchor: Optional[date] = None) -> Optional[dict]:
    """Freshness result for a single table, or None if it has no active
    contract row. Used at the point of decision (API payloads)."""
    contracts = [c for c in get_contracts(session) if c["table_name"] == table_name]
    if not contracts:
        return None
    if anchor is None:
        from etl.derive import get_anchor_date
        anchor = get_anchor_date(session)
    return check_table_freshness(session, contracts[0], anchor)
