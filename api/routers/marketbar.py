"""
Market tape endpoint.

GET /api/marketbar
  Returns the best available value for each enabled market metric, resolved
  from the registry (ref_market_metric) via pluggable source adapters
  (etl/marketbar.py).  Order: sort_order ASC.

Response shape:
  {
    "as_of": "2026-06-05",   # anchor date (MAX export_date FROM hist_td)
    "items": [
      {
        "metric_key":   "SPX",
        "label":        "S&P 500",
        "grp":          "index",
        "value":        5300.12,
        "chg":          -12.5,
        "chg_pct":      -0.24,
        "value_format": "index",
        "as_of":        "2026-06-05",
        "source":       "tos",
        "stale":        false
      },
      ...
    ]
  }
"""
from __future__ import annotations

from fastapi import APIRouter

from etl.db import session_scope
from etl.marketbar import resolve_all

router = APIRouter(tags=["marketbar"])


@router.get("/api/marketbar")
def get_marketbar() -> dict:
    """Return the market tape: one resolved item per enabled metric."""
    with session_scope() as s:
        items, anchor = resolve_all(s)
    return {
        "as_of": anchor.isoformat() if anchor else None,
        "items": items,
    }
