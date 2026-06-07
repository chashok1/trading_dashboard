"""
Macro feed endpoint.

Serves the latest economic data + EOD index levels pulled from FRED
(etl/fetch_macro.py → hist_macro → v_macro_latest). Used by the cockpit's
market-context band.

GET /api/macro
  -> {
       "as_of": "2026-06-05",          # newest observation date across series
       "groups": {
         "rates":     [ {series_id,label,unit,latest_value,latest_date,
                         prior_value,chg_abs,chg_pct}, ... ],
         "inflation": [ ... ], "jobs": [...], "risk": [...],
         "index": [...], "fx_cmdty": [...]
       }
     }
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from etl.db import session_scope

router = APIRouter(tags=["macro"])

# Stable display order for the groups.
_GROUP_ORDER = ["index", "rates", "inflation", "jobs", "risk", "fx_cmdty"]


def _last_fetch(s) -> dict | None:
    """Most recent real fetch run (for the 'last fetched' stamp by the button)."""
    row = s.execute(text("""
        SELECT started_at, finished_at, status, rows_inserted,
               series_ok, series_failed, note
        FROM meta_macro_fetch
        ORDER BY started_at DESC
        LIMIT 1
    """)).mappings().first()
    if not row:
        return None
    d = dict(row)
    for k in ("started_at", "finished_at"):
        d[k] = d[k].isoformat() if d[k] else None
    return d


@router.get("/api/macro")
def get_macro() -> dict:
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT series_id, label, grp, unit, sort_order,
                   latest_value, latest_date, prior_value, prior_date,
                   chg_abs, chg_pct
            FROM v_macro_latest
        """)).mappings().all()
        last_fetch = _last_fetch(s)

    groups: dict[str, list[dict]] = {}
    as_of = None
    for r in rows:
        d = dict(r)
        ld = d.get("latest_date")
        if ld is not None and (as_of is None or ld > as_of):
            as_of = ld
        item = {
            "series_id": d["series_id"],
            "label": d["label"],
            "unit": d["unit"],
            "latest_value": d["latest_value"],
            "latest_date": ld.isoformat() if ld else None,
            "prior_value": d["prior_value"],
            "prior_date": d["prior_date"].isoformat() if d["prior_date"] else None,
            "chg_abs": round(d["chg_abs"], 4) if d["chg_abs"] is not None else None,
            "chg_pct": round(d["chg_pct"], 2) if d["chg_pct"] is not None else None,
        }
        groups.setdefault(d["grp"], []).append(item)

    # Emit groups in a stable, sensible order (known groups first, then any extras).
    ordered = {g: groups[g] for g in _GROUP_ORDER if g in groups}
    for g in groups:
        if g not in ordered:
            ordered[g] = groups[g]

    return {
        "as_of": as_of.isoformat() if as_of else None,
        "groups": ordered,
        "last_fetch": last_fetch,
    }


@router.post("/api/macro/refresh")
def refresh_macro() -> dict:
    """Trigger a FRED fetch for the manual Refresh button.

    Throttled (respects ref_settings.macro_fetch_min_interval_min): if a real
    fetch ran within the window this is a no-op and returns
    {"skipped": true, "reason": "throttled", "age_min": N, ...} — so repeated
    clicks cannot stack up FRED requests. Use the CLI with --force for a forced
    refresh. Runs synchronously (a few seconds).
    """
    # Imported lazily so the API starts even if the etl module has an issue.
    from etl.fetch_macro import fetch_macro
    return fetch_macro(trigger="api")
