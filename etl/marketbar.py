"""
Market-tape resolver + source adapters.

Source-agnostic: each metric in ref_market_metric carries a source_priority
JSONB array of "adapter:symbol" strings.  resolve_metric() iterates left→right
and returns the first adapter that produces a value.

Adapters implemented:
  tos       — drv_quote (latest TOS price, net change, % change, as_of_date)
  fred      — v_macro_latest (FRED latest_value, chg_abs, chg_pct, latest_date)
  realtime  — STUB (always None; wired so the registry can carry "realtime:..."
               entries today with zero code change needed later)

SQL ≤ 965 bytes per statement, tos_symbol only in drv_* per repo convention.
DB access via SQLAlchemy + psycopg v3 only.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.db import session_scope
from etl.derive import get_anchor_date

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Adapter result shape
# ---------------------------------------------------------------------------
# Each adapter returns a dict with these keys, or None:
#   value    : float | None
#   chg      : float | None   (absolute change from prior)
#   chg_pct  : float | None   (% change from prior)
#   as_of    : date  | None
#   source   : str            (adapter name, e.g. 'tos' or 'fred')


# ---------------------------------------------------------------------------
# TOS adapter — reads drv_quote for the given tos_symbol
# ---------------------------------------------------------------------------

_TOS_SQL = text("""
SELECT last_price, net_chng, pct_change, as_of_date, export_date
FROM drv_quote
WHERE tos_symbol = :sym
ORDER BY as_of_date DESC
LIMIT 1
""")


def _tos_adapter(session: Session, symbol: str) -> dict | None:
    """Return latest TOS price from drv_quote, or None if absent."""
    row = session.execute(_TOS_SQL, {"sym": symbol}).mappings().first()
    if row is None or row["last_price"] is None:
        return None
    as_of = row["as_of_date"] or row["export_date"]
    return {
        "value":   float(row["last_price"]),
        "chg":     float(row["net_chng"])   if row["net_chng"]   is not None else None,
        "chg_pct": float(row["pct_change"]) if row["pct_change"] is not None else None,
        "as_of":   as_of,
        "source":  "tos",
    }


# ---------------------------------------------------------------------------
# FRED adapter — reads v_macro_latest for the given series_id
# ---------------------------------------------------------------------------

_FRED_SQL = text("""
SELECT latest_value, chg_abs, chg_pct, latest_date
FROM v_macro_latest
WHERE series_id = :sid
LIMIT 1
""")


def _fred_adapter(session: Session, symbol: str) -> dict | None:
    """Return latest FRED value from v_macro_latest, or None if absent."""
    row = session.execute(_FRED_SQL, {"sid": symbol}).mappings().first()
    if row is None or row["latest_value"] is None:
        return None
    return {
        "value":   float(row["latest_value"]),
        "chg":     float(row["chg_abs"])  if row["chg_abs"]  is not None else None,
        "chg_pct": float(row["chg_pct"])  if row["chg_pct"]  is not None else None,
        "as_of":   row["latest_date"],
        "source":  "fred",
    }


# ---------------------------------------------------------------------------
# Realtime adapter — STUB (always None)
# ---------------------------------------------------------------------------

def _realtime_adapter(session: Session, symbol: str) -> dict | None:
    """Placeholder for a future real-time feed. Always returns None today."""
    return None


# ---------------------------------------------------------------------------
# Adapter registry — maps prefix → callable(session, symbol) -> dict | None
# ---------------------------------------------------------------------------

_ADAPTERS: dict[str, Any] = {
    "tos":      _tos_adapter,
    "fred":     _fred_adapter,
    "realtime": _realtime_adapter,
}


# ---------------------------------------------------------------------------
# Resolve a single metric row
# ---------------------------------------------------------------------------

def resolve_metric(row: dict, session: Session, anchor: date | None) -> dict:
    """Resolve one ref_market_metric row to a value using source_priority.

    Iterates source_priority left→right, calls the matching adapter, and
    returns the first non-None result merged with registry fields.

    The returned dict shape:
      metric_key, label, grp, value_format, sort_order,
      value, chg, chg_pct, as_of, source,
      stale  (bool: as_of < anchor, or True when as_of is None)
    """
    priorities: list[str] = row.get("source_priority") or []
    result: dict | None = None

    for entry in priorities:
        if ":" not in entry:
            log.warning("Invalid source_priority entry (no colon): %s", entry)
            continue
        adapter_name, sym = entry.split(":", 1)
        adapter_fn = _ADAPTERS.get(adapter_name)
        if adapter_fn is None:
            log.warning("Unknown adapter '%s' in source_priority", adapter_name)
            continue
        try:
            # Use a savepoint so a DB error does not abort the whole
            # session transaction (PostgreSQL requires ROLLBACK TO SAVEPOINT
            # before any further statements after an error).
            sp = session.begin_nested()
            result = adapter_fn(session, sym)
            sp.commit()
        except Exception:
            log.exception("Adapter '%s' error for symbol '%s'", adapter_name, sym)
            try:
                sp.rollback()
            except Exception:
                pass
            result = None
        if result is not None:
            break

    # Build stale flag
    as_of = result["as_of"] if result else None
    stale: bool
    if as_of is None or anchor is None:
        stale = True
    else:
        stale = as_of < anchor

    as_of_str = as_of.isoformat() if as_of else None

    return {
        "metric_key":   row["metric_key"],
        "label":        row["label"],
        "grp":          row["grp"],
        "value_format": row["value_format"],
        "sort_order":   row["sort_order"],
        "value":        result["value"]   if result else None,
        "chg":          result["chg"]     if result else None,
        "chg_pct":      result["chg_pct"] if result else None,
        "as_of":        as_of_str,
        "source":       result["source"]  if result else None,
        "stale":        stale,
    }


# ---------------------------------------------------------------------------
# Resolve all enabled metrics
# ---------------------------------------------------------------------------

_REGISTRY_SQL = text("""
SELECT metric_key, label, grp, source_priority,
       value_format, sort_order
FROM ref_market_metric
WHERE enabled
ORDER BY sort_order, metric_key
""")


def resolve_all(session: Session) -> tuple[list[dict], date | None]:
    """Resolve all enabled metrics from the registry.

    Returns (items, anchor_date).  Items are ordered by sort_order.
    """
    anchor = get_anchor_date(session)
    rows = session.execute(_REGISTRY_SQL).mappings().all()
    items = [resolve_metric(dict(r), session, anchor) for r in rows]
    return items, anchor
