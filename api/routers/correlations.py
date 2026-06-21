"""
USD correlations endpoint — TASK_79.

GET /api/correlations?date=D
  Returns drv_usd_correlation for the anchor date, ordered by sort_order
  from ref_corr_asset.

Response:
  {
    as_of: "YYYY-MM-DD",
    windows: [15, 30, 90, 120, 180],
    rows: [
      {
        asset_key, label,
        w15, w30, w90, w120, w180,
        n15, n30, n90, n120, n180,
        roll30_high, roll30_low, roll30_pct_pos, roll30_pct_neg
      }, ...
    ]
  }

No recompute in the API — reads straight from drv_usd_correlation.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from api._helpers import _resolve_date
from etl.db import session_scope

router = APIRouter(tags=["correlations"])

WINDOWS = [15, 30, 90, 120, 180]


@router.get("/api/correlations")
def get_correlations(date: Optional[str] = Query(None)) -> dict:
    d = _resolve_date(date)

    with session_scope() as s:
        # Anchor: MAX(as_of_date) in drv_usd_correlation <= d
        anchor_row = s.execute(text(
            "SELECT MAX(as_of_date) FROM drv_usd_correlation"
            " WHERE as_of_date <= :d"
        ), {"d": d}).first()
        anchor = anchor_row[0] if anchor_row and anchor_row[0] else None

        rows_out: list[dict] = []
        if anchor:
            rows = s.execute(text("""
                SELECT c.asset_key, a.label,
                       c.w15, c.w30, c.w90, c.w120, c.w180,
                       c.n15, c.n30, c.n90, c.n120, c.n180,
                       c.roll30_high, c.roll30_low,
                       c.roll30_pct_pos, c.roll30_pct_neg
                FROM drv_usd_correlation c
                JOIN ref_corr_asset a ON a.asset_key = c.asset_key
                WHERE c.as_of_date = :d
                  AND a.is_usd_base = FALSE
                ORDER BY a.sort_order
            """), {"d": anchor}).mappings().all()

            for r in rows:
                rows_out.append({
                    "asset_key":      r["asset_key"],
                    "label":          r["label"],
                    "w15":            _f(r["w15"]),
                    "w30":            _f(r["w30"]),
                    "w90":            _f(r["w90"]),
                    "w120":           _f(r["w120"]),
                    "w180":           _f(r["w180"]),
                    "n15":            r["n15"],
                    "n30":            r["n30"],
                    "n90":            r["n90"],
                    "n120":           r["n120"],
                    "n180":           r["n180"],
                    "roll30_high":    _f(r["roll30_high"]),
                    "roll30_low":     _f(r["roll30_low"]),
                    "roll30_pct_pos": _f(r["roll30_pct_pos"]),
                    "roll30_pct_neg": _f(r["roll30_pct_neg"]),
                })

    return {
        "as_of":   str(anchor) if anchor else None,
        "windows": WINDOWS,
        "rows":    rows_out,
    }


def _f(v) -> Optional[float]:
    if v is None:
        return None
    try:
        import math
        f = float(v)
        return round(f, 4) if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None
