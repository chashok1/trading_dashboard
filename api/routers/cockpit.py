"""
api/routers/cockpit.py -- TASK_133 Phase 6: dashboard cockpit API.

Thin reads over drv_market_stat / drv_market_event / drv_category_perf /
ref_gauge_transmission / drv_actionable. No heavy computation at request
time -- the real work happens in the derivers (etl/derive_risk_dial.py,
etl/derive_market_stat.py, etl/derive_market_event.py,
etl/derive_category_perf.py). All endpoints take optional ?date=D and
default via _resolve_date (the anchor).
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from api._helpers import _resolve_date
from etl.db import session_scope

router = APIRouter()

# TASK_134 B.2 -- imperative-with-a-target phrasing, one per risk_label band.
# Single source of truth: risk_label itself is computed in
# etl/derive_risk_dial.py::_risk_label from the exact same budget boundaries
# (>=80/>=55/>=30/else) that drive suggested_size_multiplier (risk_budget/100)
# below, so looking the phrase up by risk_label can never disagree with the
# multiplier -- they're both keyed off the one banding function.
_RISK_SIZE_PHRASE = {
    "CLEAR": "Full size.",
    "CAUTION": "Three-quarter size.",
    "DEFENSIVE": "Half size.",
    "NOT INVESTABLE": "No new risk.",
}


def _lc(xs):
    """Lowercase a list of category names for case-insensitive SQL matching.

    drv_ma.sector carries real case variants for the same GICS sector (e.g.
    'Health care' vs 'Health Care' -- confirmed live, TASK_139) that
    etl/derive_category_perf.py::_canon_sector folds together before
    aggregating into drv_category_perf. The exposure queries below read
    drv_ma directly (they need per-position rows, not the pre-aggregated
    table), so they must fold case themselves or silently miss real
    positions -- LOWER(TRIM(...)) on both sides of every sector/asset_class
    comparison, everywhere in this file that joins drv_ma."""
    return [x.lower() for x in xs]


def _jsonb(v):
    """jsonb columns sometimes come back as str depending on driver config."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v


# 2026-08-08 -- shared LATERAL-join fragment for classifying a CLOSED
# position's sector/asset_class/style: drv_ma/drv_macro_score are scoped to
# the CURRENT day's holdings universe (drv_symbols = symbols in hist_td
# WHERE export_date=D), so a sold-out symbol has no row at exactly `:d` --
# unlike an open position, a closed one needs its latest available
# classification AT OR BEFORE the anchor instead of an exact-date match.
# User: "is there a way i can see closed/sold positions also in these
# dashboard graphs".
_CLOSED_CLASSIFY_JOIN = """
    LEFT JOIN LATERAL (
        SELECT tos_symbol, sector, asset_class FROM drv_ma
        WHERE tos_symbol = c.tos_symbol AND as_of_date <= :d
        ORDER BY as_of_date DESC LIMIT 1
    ) m ON TRUE
    LEFT JOIN ref_sector rs ON rs.ticker = c.tos_symbol
    LEFT JOIN LATERAL (
        SELECT style_stances FROM drv_macro_score
        WHERE tos_symbol = c.tos_symbol AND as_of_date <= :d
        ORDER BY as_of_date DESC LIMIT 1
    ) ms ON TRUE
"""
# 2026-08-09 BUGFIX -- `m` now selects tos_symbol too (not just sector/
# asset_class): get_factor_exposure_detail's `where_clause` is built for
# and reused verbatim against BOTH the open-position query (whose own `m`
# is `LEFT JOIN drv_ma m ON m.tos_symbol = a.tos_symbol`, so m.tos_symbol
# always exists) and this LATERAL join -- the Unmapped branch's
# `m.tos_symbol IS NULL` check (its way of detecting "no drv_ma row
# matched") crashed with "column m.tos_symbol does not exist" the moment
# anyone opened Sector/Asset Class's Unmapped popup with a closed position
# in the trailing 30 days, since the LATERAL subquery hadn't selected that
# column at all. User: "sector grid -> unmapped -> check and tell me
# which ones are unmapped" surfaced it live.
# 2026-08-09 -- added a plain `ref_sector rs` join alongside `m` (drv_ma)
# so callers can COALESCE(m.sector, rs.equity_sector) the same fallback
# etl/derive_category_perf.py::_build_category_map already uses -- a
# symbol ToS never exports (no hist_td row ever, e.g. GSL: held, but not
# ToS-tracked) never gets a drv_ma row at all, so the popup was one symbol
# short of the aggregate grid card without this. Purely additive; once a
# symbol gets a real drv_ma row that value wins automatically (COALESCE
# order). User: "fix it. Keep in mind i will be adding the new stock
# symbols to tos exports. Not sure if your fix is going to affect that."


def _closed_positions_base(d, accounts: Optional[list] = None) -> str:
    """CTE selecting realized sells in the trailing 30 days before/at the
    anchor (drv_realized_gain already excludes inactive accounts --
    etl/derive_realized.py's own is_active filter -- so no re-filtering
    needed here). 2026-08-08 -- was originally scoped to the anchor's
    fiscal year, but a gauge popup's OR-union across several sector/
    asset_class/style tags matched 300-700+ closed trades that way (most
    trades carry SOME broad style tag like High Beta/Secular/Cyclical) --
    unusable in a popup. Narrowed to a 30-day trailing window (anchor-date
    based, never the real system clock, per the app's standing anchor-date
    rule), matching the Daily gain/loss chart's own lookback. User: "popup
    include stocks traded in last 30 days".
    2026-08-09 -- optional accounts filter (rg.account stores the same
    account_number domain as ref_accounts.account_number directly, same
    join used everywhere else) so closed positions also respect the
    Cockpit Accounts filter, matching the open-position query alongside
    it. User: "popups on the my accounts not considering the filters
    (ex: one account)"."""
    acct_clause = " AND rg.account = ANY(:accounts)" if accounts else ""
    return f"""
        closed AS (
          SELECT rg.tos_symbol, COALESCE(ra.short_name, rg.account) AS account,
                 rg.sell_date, rg.realized_gain AS gl, rg.realized_gain_pct AS glpct
          FROM drv_realized_gain rg
          LEFT JOIN ref_accounts ra ON ra.account_number = rg.account
          WHERE rg.sell_date BETWEEN :d - INTERVAL '30 days' AND :d
          {acct_clause}
        )
    """


def _yesterday_by_symbol_account(session, d) -> dict:
    """Per-(tos_symbol, account) broker day-change for the exposure-detail
    popups (day_chng_dollar/pct for Schwab, today_gl_dollar/pct for
    Fidelity), read from the LATEST available snapshot at or before `d`.
    2026-08-08 -- this used to always step back one snapshot further than
    that (assuming `d`'s own CS/F row could never be a finalized capture),
    but that's wrong: CS/F loads land in the evening, well after market
    close (confirmed via hist_cs.loaded_at ~18:xx on the snapshot's own
    date), so a `d`-dated row IS already the real, finalized close figure
    once it exists -- stepping past it just showed stale D-1 data on a
    day D's data was sitting right there. If `d`'s own CS/F hasn't loaded
    yet (still mid-day, before the evening file lands), `snapshot_date <=
    :d` naturally already resolves to the prior completed day -- no
    special-casing needed. User: "shouldn't I see that data in the grid
    instead of 8/6 data... I need to see market close data and
    corresponding bar." Returns {(tos_symbol, account): (dollar, pct)};
    a symbol with no snapshot at or before `d` (e.g. bought today, no
    prior data at all) is simply absent. account strings must match
    _lc()-style expressions used by the callers' own `pos` CTEs exactly,
    so they join up in Python."""
    out: dict = {}
    for r in session.execute(text("""
        SELECT hist_cs.tos_symbol, COALESCE(ra.short_name, hist_cs.account) AS account,
               day_chng_dollar AS yd, day_chng_pct AS ypct
        FROM hist_cs
        LEFT JOIN ref_accounts ra ON ra.account_number = hist_cs.account
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
          AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
    """), {"d": d}).mappings().all():
        out[(r["tos_symbol"], r["account"])] = (r["yd"], r["ypct"])
    for r in session.execute(text("""
        SELECT hist_f.tos_symbol,
               COALESCE(ra.short_name, hist_f.account_name, hist_f.account_number) AS account,
               hist_f.today_gl_dollar AS yd, hist_f.today_gl_pct AS ypct
        FROM hist_f
        LEFT JOIN ref_accounts ra ON ra.account_number = hist_f.account_number
        WHERE hist_f.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
          AND COALESCE(ra.is_active, TRUE) = TRUE
    """), {"d": d}).mappings().all():
        out[(r["tos_symbol"], r["account"])] = (r["yd"], r["ypct"])
    return out


# ---------------------------------------------------------------------------
# 6.1 GET /api/cockpit/risk-dial
# ---------------------------------------------------------------------------

def _top_holdings(session, d, axis: str, categories: list, limit: int = 3) -> list:
    """Top N holdings by dollar market value within the given sector/
    asset_class categories, latest position snapshot on or before d.
    style-axis categories are skipped (style tags aren't a stored per-symbol
    column anywhere queryable -- they're computed on the fly by
    etl/derive_macro.py::_classify_style -- so style exposure still counts
    in the dollar total but contributes no top_holdings; documented in
    DEV_HANDOFF.md)."""
    if not categories or axis not in ("sector", "asset_class"):
        return []
    col = "sector" if axis == "sector" else "asset_class"
    rows = session.execute(text(f"""
        WITH pos AS (
          SELECT tos_symbol, SUM(market_value) AS mv FROM hist_cs
          WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
            AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
          GROUP BY tos_symbol
          UNION ALL
          SELECT tos_symbol, SUM(current_value) FROM hist_f
          WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
            AND account_number NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
          GROUP BY tos_symbol
        ), agg AS (SELECT tos_symbol, SUM(mv) AS dollar FROM pos GROUP BY tos_symbol)
        SELECT a.tos_symbol, a.dollar FROM agg a
        JOIN drv_ma m ON m.tos_symbol = a.tos_symbol AND m.as_of_date = :d
        WHERE m.{col} = ANY(:cats)
        ORDER BY a.dollar DESC LIMIT :lim
    """), {"d": d, "cats": categories, "lim": limit}).all()
    return [{"symbol": r[0], "dollar": float(r[1])} for r in rows if r[1]]


def _gauge_exposure(session, d, gauge_key: str, total_value: Optional[float]) -> Optional[dict]:
    trans = session.execute(text(
        "SELECT axis, category FROM ref_gauge_transmission WHERE gauge_key = :k"
    ), {"k": gauge_key}).all()
    if not trans:
        return None
    # TASK_136-followup: dollar exposure must count each position at most
    # once even when a gauge transmits into several categories/axes that the
    # same holding matches (e.g. a stock tagged both 'High Beta' and
    # 'Momentum' style, or matching a sector AND an asset_class category).
    # Summing drv_category_perf's per-category totals (the old approach)
    # double/triple-counted such positions -- this instead resolves the
    # qualifying position set once (OR across axes, not a per-category sum)
    # and sums each symbol's market value a single time.
    sector_cats = [c for a, c in trans if a == "sector"]
    asset_cats = [c for a, c in trans if a == "asset_class"]
    style_cats = [c for a, c in trans if a == "style"]
    dollar_row = session.execute(text("""
        WITH pos AS (
          SELECT tos_symbol, market_value AS mv FROM hist_cs
          WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
            AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
          UNION ALL
          SELECT tos_symbol, current_value AS mv FROM hist_f
          WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
            AND account_number NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
        ), agg AS (SELECT tos_symbol, SUM(mv) AS mv FROM pos GROUP BY tos_symbol)
        SELECT SUM(a.mv) FROM agg a
        LEFT JOIN drv_ma m ON m.tos_symbol = a.tos_symbol AND m.as_of_date = :d
        LEFT JOIN drv_macro_score ms ON ms.tos_symbol = a.tos_symbol AND ms.as_of_date = :d
        WHERE LOWER(TRIM(m.sector)) = ANY(:sector_cats)
           OR LOWER(TRIM(m.asset_class)) = ANY(:asset_cats)
           OR EXISTS (
                SELECT 1 FROM jsonb_array_elements(COALESCE(ms.style_stances, '[]'::jsonb)) e
                WHERE e->>'label' = ANY(:style_cats)
              )
    """), {"d": d, "sector_cats": _lc(sector_cats), "asset_cats": _lc(asset_cats),
           "style_cats": style_cats}).scalar()
    dollar = float(dollar_row) if dollar_row is not None else 0.0
    categories = sorted({c for _, c in trans})
    top = []
    for axis, cats in (("sector", [c for a, c in trans if a == "sector"]),
                       ("asset_class", [c for a, c in trans if a == "asset_class"])):
        top.extend(_top_holdings(session, d, axis, cats))
    top.sort(key=lambda h: h["dollar"], reverse=True)
    return {
        "dollar": round(dollar, 2),
        "pct": round(dollar / total_value * 100.0, 2) if total_value else None,
        "categories": categories,
        "top_holdings": top[:3],
    }


@router.get("/api/cockpit/risk-dial")
def get_risk_dial(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        row = s.execute(text(
            "SELECT risk_budget, risk_label, gauges_fired FROM drv_market_stat "
            "WHERE as_of_date = :d"
        ), {"d": d}).mappings().first()
        if not row:
            return {"as_of": d.isoformat(), "risk_budget": None, "risk_label": None,
                    "headline": "No risk-dial data for this date.",
                    "fired": [], "quiet": [], "evaluable_weight": 0, "fired_weight": 0,
                    "suggested_size_multiplier": None}

        gauges = _jsonb(row["gauges_fired"]) or []
        fired = [g for g in gauges if g.get("fired") is True]
        quiet = [g for g in gauges if g.get("fired") is not True]
        fired.sort(key=lambda g: g.get("weight") or 0, reverse=True)

        total_value = s.execute(text(
            "SELECT SUM(market_value) FROM drv_category_perf "
            "WHERE axis = 'asset_class' AND as_of_date = :d"
        ), {"d": d}).scalar()
        total_value = float(total_value) if total_value else None

        for g in fired:
            g["exposure"] = _gauge_exposure(s, d, g["key"], total_value)

        risk_budget = row["risk_budget"]
        risk_label = row["risk_label"]
        evaluable_weight = sum(g.get("weight") or 0 for g in gauges if g.get("fired") is not None)
        fired_weight = sum(g.get("weight") or 0 for g in fired)

        size_phrase = _RISK_SIZE_PHRASE.get(risk_label, "")
        if fired:
            top2 = fired[:2]
            detail_bits = "; ".join(g.get("detail") or g["label"] for g in top2)
            headline = f"{size_phrase} {detail_bits}".strip()
        else:
            headline = f"{size_phrase} No risk gauges fired.".strip()

        return {
            "as_of": d.isoformat(),
            "risk_budget": risk_budget,
            "risk_label": risk_label,
            "headline": headline,
            "fired": fired,
            "quiet": quiet,
            "evaluable_weight": evaluable_weight,
            "fired_weight": fired_weight,
            "suggested_size_multiplier": round(risk_budget / 100.0, 2) if risk_budget is not None else None,
        }


# ---------------------------------------------------------------------------
# 6.1b GET /api/cockpit/risk-dial/{gauge_key}/exposure-detail
# GET /api/cockpit/risk-dial/all-exposure
# GET /api/cockpit/risk-dial/history
#
# Risk Detail screen support (drill-down modal + structural/historical
# charts). All three reuse the same dedup-by-position logic fixed in
# _gauge_exposure above -- exposure-detail just returns the uncapped row
# list instead of a top-3 summary, all-exposure runs it for every active
# gauge (not only fired ones), history reads drv_market_stat's own trailing
# rows. No new derive logic -- pure reads over what already exists daily.
# ---------------------------------------------------------------------------

@router.get("/api/cockpit/risk-dial/{gauge_key}/exposure-detail")
def get_gauge_exposure_detail(gauge_key: str, date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        gauge_row = s.execute(text(
            "SELECT label FROM ref_risk_gauge WHERE gauge_key = :k"
        ), {"k": gauge_key}).mappings().first()
        if not gauge_row:
            raise HTTPException(status_code=404, detail=f"unknown gauge_key {gauge_key!r}")

        trans = s.execute(text(
            "SELECT axis, category FROM ref_gauge_transmission WHERE gauge_key = :k"
        ), {"k": gauge_key}).all()
        if not trans:
            return {"as_of": d.isoformat(), "gauge_key": gauge_key, "label": gauge_row["label"],
                    "dollar": None, "pct": None, "categories": [], "positions": []}

        sector_cats = [c for a, c in trans if a == "sector"]
        asset_cats = [c for a, c in trans if a == "asset_class"]
        style_cats = [c for a, c in trans if a == "style"]

        total_value = s.execute(text(
            "SELECT SUM(market_value) FROM drv_category_perf "
            "WHERE axis = 'asset_class' AND as_of_date = :d"
        ), {"d": d}).scalar()
        total_value = float(total_value) if total_value else None

        # 2026-08-08 -- cost_basis/gain_dollar carried through for the
        # popup's %gain/loss column, same as get_factor_exposure_detail.
        # 2026-08-08 -- Account column uses ref_accounts.short_name only
        # (e.g. "IRA", "HSA", "F-M") instead of the raw hist_cs.account
        # string / composite Fidelity name -- user: "popup -> left column
        # grid (stock listing) -> use account desc". Falls back to the raw
        # value when an account has no short_name mapped.
        # 2026-08-09 BUGFIX -- sector/asset_class now COALESCE(drv_ma,
        # ref_sector) instead of drv_ma alone, matching etl/derive_
        # category_perf.py::_build_category_map's own precedence (drv_ma
        # first, ref_sector fallback). drv_ma only has rows for symbols in
        # the CURRENT day's hist_td/TOSD universe (drv_symbols) -- a symbol
        # ToS never exports at all (e.g. GSL, held but not ToS-tracked)
        # never gets a drv_ma row no matter what, so this popup was one
        # symbol short of the aggregate grid card (which already reads
        # ref_sector via _build_category_map) whenever that happened.
        # Purely additive/fallback -- once a symbol DOES get a real drv_ma
        # row (e.g. after being added to a ToS export), that value wins
        # automatically, no behavior change. User: "fix it. Keep in mind i
        # will be adding the new stock symbols to tos exports. Not sure if
        # your fix is going to affect that" -- it doesn't.
        rows = s.execute(text("""
            WITH pos AS (
              SELECT hist_cs.tos_symbol, COALESCE(ra.short_name, hist_cs.account) AS account,
                     market_value AS mv, cost_basis AS cb, gain_dollar AS gl
              FROM hist_cs
              LEFT JOIN ref_accounts ra ON ra.account_number = hist_cs.account
              WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
                AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
              UNION ALL
              SELECT hist_f.tos_symbol,
                     COALESCE(ra.short_name, hist_f.account_name, hist_f.account_number) AS account,
                     hist_f.current_value AS mv,
                     hist_f.cost_basis_total AS cb, hist_f.total_gl_dollar AS gl
              FROM hist_f
              LEFT JOIN ref_accounts ra ON ra.account_number = hist_f.account_number
              WHERE hist_f.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
                AND COALESCE(ra.is_active, TRUE) = TRUE
            ), agg AS (SELECT tos_symbol, account, SUM(mv) AS mv, SUM(cb) AS cb, SUM(gl) AS gl
                       FROM pos GROUP BY tos_symbol, account)
            SELECT a.tos_symbol, a.account, a.mv, a.cb, a.gl,
                   COALESCE(m.sector, rs.equity_sector) AS sector,
                   COALESCE(m.asset_class, rs.asset_class) AS asset_class,
                   ms.style_stances
            FROM agg a
            LEFT JOIN drv_ma m ON m.tos_symbol = a.tos_symbol AND m.as_of_date = :d
            LEFT JOIN drv_macro_score ms ON ms.tos_symbol = a.tos_symbol AND ms.as_of_date = :d
            LEFT JOIN ref_sector rs ON rs.ticker = a.tos_symbol
            WHERE LOWER(TRIM(COALESCE(m.sector, rs.equity_sector))) = ANY(:sector_cats)
               OR LOWER(TRIM(COALESCE(m.asset_class, rs.asset_class))) = ANY(:asset_cats)
               OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(COALESCE(ms.style_stances, '[]'::jsonb)) e
                    WHERE e->>'label' = ANY(:style_cats)
                  )
            ORDER BY a.mv DESC
        """), {"d": d, "sector_cats": _lc(sector_cats), "asset_cats": _lc(asset_cats),
               "style_cats": style_cats}).mappings().all()
        yesterday_map = _yesterday_by_symbol_account(s, d)

        sector_cats_lc, asset_cats_lc = _lc(sector_cats), _lc(asset_cats)
        positions, dollar = [], 0.0
        for r in rows:
            mv = float(r["mv"] or 0)
            dollar += mv
            if (r["sector"] or "").strip().lower() in sector_cats_lc:
                tag = r["sector"]
            elif (r["asset_class"] or "").strip().lower() in asset_cats_lc:
                tag = r["asset_class"]
            else:
                stances = _jsonb(r["style_stances"]) or []
                tag = ", ".join(sorted({e["label"] for e in stances if e.get("label") in style_cats}))
            cb, gl = r["cb"], r["gl"]
            gain_dollar = round(float(gl), 2) if gl is not None else None
            gain_pct = round(float(gl) / float(cb) * 100.0, 2) if (cb and gl is not None) else None
            # 2026-08-08 -- broker's own daily gain/loss, from YESTERDAY's
            # snapshot (_yesterday_by_symbol_account), not this row's own --
            # same distinction etl/derive_category_perf.py::
            # _yesterday_actual_change draws for the category-level
            # "Yesterday" column. User request: "Can the popups include
            # these numbers for each stock?"
            yd, ypct = yesterday_map.get((r["tos_symbol"], r["account"]), (None, None))
            yesterday_dollar = round(float(yd), 2) if yd is not None else None
            yesterday_pct = round(float(ypct), 2) if ypct is not None else None
            positions.append({"symbol": r["tos_symbol"], "account": r["account"],
                               "dollar": round(mv, 2), "tag": tag,
                               "gain_dollar": gain_dollar, "gain_pct": gain_pct,
                               "yesterday_dollar": yesterday_dollar, "yesterday_pct": yesterday_pct})

        # 2026-08-08 -- closed/sold positions (this fiscal year), same
        # sector/asset_class/style OR-union as the open-position query
        # above, tagged closed:true with $0 current exposure (excluded from
        # `dollar`/`pct` totals -- they're realized, not live) and
        # realized_gain_dollar/pct + sell_date instead of gain_dollar/pct.
        # Still clickable in the UI for the Daily gain/loss chart, which
        # already has history up through the sell date regardless.
        # User: "is there a way i can see closed/sold positions also in
        # these dashboard graphs".
        closed_rows = s.execute(text(f"""
            WITH {_closed_positions_base(d)}
            SELECT c.tos_symbol, c.account, c.sell_date, c.gl, c.glpct,
                   COALESCE(m.sector, rs.equity_sector) AS sector,
                   COALESCE(m.asset_class, rs.asset_class) AS asset_class,
                   ms.style_stances
            FROM closed c
            {_CLOSED_CLASSIFY_JOIN}
            WHERE LOWER(TRIM(COALESCE(m.sector, rs.equity_sector))) = ANY(:sector_cats)
               OR LOWER(TRIM(COALESCE(m.asset_class, rs.asset_class))) = ANY(:asset_cats)
               OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(COALESCE(ms.style_stances, '[]'::jsonb)) e
                    WHERE e->>'label' = ANY(:style_cats)
                  )
            ORDER BY c.sell_date DESC
        """), {"d": d, "sector_cats": sector_cats_lc, "asset_cats": asset_cats_lc,
               "style_cats": style_cats}).mappings().all()
        for r in closed_rows:
            if (r["sector"] or "").strip().lower() in sector_cats_lc:
                tag = r["sector"]
            elif (r["asset_class"] or "").strip().lower() in asset_cats_lc:
                tag = r["asset_class"]
            else:
                stances = _jsonb(r["style_stances"]) or []
                tag = ", ".join(sorted({e["label"] for e in stances if e.get("label") in style_cats}))
            gl = r["gl"]
            positions.append({
                "symbol": r["tos_symbol"], "account": r["account"], "tag": tag,
                "closed": True, "sell_date": r["sell_date"].isoformat(),
                "dollar": 0.0,
                "realized_gain_dollar": round(float(gl), 2) if gl is not None else None,
                "realized_gain_pct": round(float(r["glpct"]), 2) if r["glpct"] is not None else None,
            })

        return {
            "as_of": d.isoformat(),
            "gauge_key": gauge_key,
            "label": gauge_row["label"],
            "dollar": round(dollar, 2),
            "pct": round(dollar / total_value * 100.0, 2) if total_value else None,
            "categories": sorted(set(sector_cats + asset_cats + style_cats)),
            "positions": positions,
        }


@router.get("/api/cockpit/risk-dial/all-exposure")
def get_all_gauge_exposure(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        gauges = s.execute(text(
            "SELECT gauge_key, label, weight FROM ref_risk_gauge "
            "WHERE is_active ORDER BY weight DESC, label"
        )).mappings().all()

        row = s.execute(text(
            "SELECT gauges_fired FROM drv_market_stat WHERE as_of_date = :d"
        ), {"d": d}).mappings().first()
        gf = (_jsonb(row["gauges_fired"]) if row else None) or []
        fired_map = {g["key"]: g.get("fired") for g in gf}

        total_value = s.execute(text(
            "SELECT SUM(market_value) FROM drv_category_perf "
            "WHERE axis = 'asset_class' AND as_of_date = :d"
        ), {"d": d}).scalar()
        total_value = float(total_value) if total_value else None

        out = []
        for g in gauges:
            exp = _gauge_exposure(s, d, g["gauge_key"], total_value)
            out.append({
                "gauge_key": g["gauge_key"], "label": g["label"], "weight": float(g["weight"]),
                "fired": fired_map.get(g["gauge_key"]),
                "has_mapping": exp is not None,
                "dollar": exp["dollar"] if exp else None,
                "pct": exp["pct"] if exp else None,
            })
        return {"as_of": d.isoformat(), "gauges": out}


@router.get("/api/cockpit/risk-dial/history")
def get_risk_dial_history(days: int = Query(90, ge=1, le=365), date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT as_of_date, risk_budget, risk_label, gauges_fired
            FROM drv_market_stat WHERE as_of_date <= :d
            ORDER BY as_of_date DESC LIMIT :n
        """), {"d": d, "n": days}).mappings().all()

    history = []
    for r in reversed(rows):
        gf = _jsonb(r["gauges_fired"]) or []
        fired_keys = [g["key"] for g in gf if g.get("fired") is True]
        history.append({
            "as_of": r["as_of_date"].isoformat(),
            "risk_budget": r["risk_budget"],
            "risk_label": r["risk_label"],
            "fired": fired_keys,
        })
    return {"as_of": d.isoformat(), "days": days, "history": history}


# ---------------------------------------------------------------------------
# 6.2 GET /api/cockpit/events
# ---------------------------------------------------------------------------

@router.get("/api/cockpit/events")
def get_events(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT event_seq, event_type, severity, tos_symbol, pattern_key, "
            "title, legs, read_text, exposure FROM drv_market_event "
            "WHERE as_of_date = :d ORDER BY event_seq"
        ), {"d": d}).mappings().all()

    events, quiet_payload = [], None
    for r in rows:
        rd = dict(r)
        rd["legs"] = _jsonb(rd["legs"])
        rd["exposure"] = _jsonb(rd["exposure"])
        if rd["event_type"] == "quiet":
            quiet_payload = rd["exposure"] or {}
            continue
        events.append(rd)

    if not events:
        payload = {"quiet": True, "instruments_checked": 0, "max_abs_z": None,
                   "max_z_symbol": None, "range_breaks": 0}
        if quiet_payload:
            payload.update(quiet_payload)
        payload["as_of"] = d.isoformat()
        return payload
    return {"as_of": d.isoformat(), "quiet": False, "events": events}


# ---------------------------------------------------------------------------
# 6.3 GET /api/cockpit/factor-scorecard
# ---------------------------------------------------------------------------

@router.get("/api/cockpit/factor-scorecard")
def get_factor_scorecard(date: Optional[str] = Query(None),
                         axis: str = Query("sector"),
                         accounts: Optional[str] = Query(
                             None, description="Comma-separated account_number values "
                             "(ref_accounts.account_number) to narrow the grid to. "
                             "Omit for the full portfolio (reads the pre-computed nightly "
                             "drv_category_perf table); when set, recomputes live for just "
                             "those accounts via etl.derive_category_perf._compute_category_rows "
                             "-- same TWR/flow-adjustment math, just filtered input.")):
    if axis not in ("sector", "asset_class", "style"):
        raise HTTPException(status_code=400, detail="axis must be sector|asset_class|style")
    d = _resolve_date(date)
    accounts_list = [a.strip() for a in accounts.split(",") if a.strip()] if accounts else None

    with session_scope() as s:
        if accounts_list:
            # 2026-08-09 -- Cockpit Accounts filter ("why can't you calculate
            # Today/MTD/QTD by account?"): live per-account recompute, same
            # function the nightly full-portfolio derive uses internally,
            # just given a narrower `accounts` list -- not a separate/
            # simplified $-only path. risk_budget/detail/verdict_note
            # handling below stays identical to the drv_category_perf path
            # so the rest of this function doesn't need two branches.
            from etl.derive_category_perf import _compute_category_rows
            computed = _compute_category_rows(s, d, accounts=accounts_list)
            rows = [r for r in computed if r["axis"] == axis]
            rows.sort(key=lambda r: (r["weight_pct"] is None, -(r["weight_pct"] or 0)))
        else:
            rows = s.execute(text(
                "SELECT * FROM drv_category_perf WHERE as_of_date = :d AND axis = :a "
                "ORDER BY weight_pct DESC NULLS LAST"
            ), {"d": d, "a": axis}).mappings().all()
        risk_budget = s.execute(text(
            "SELECT risk_budget FROM drv_market_stat WHERE as_of_date = :d"
        ), {"d": d}).scalar()

    out_rows, unmapped = [], None
    for r in rows:
        rd = dict(r)
        rd["detail"] = _jsonb(rd["detail"]) if accounts_list is None else rd.get("detail")
        note = (rd["detail"] or {}).get("verdict_note") or ""
        rd["risk_budget_cap_applied"] = "capped to HOLD" in note
        for k in ("as_of_date",):
            if k in rd and hasattr(rd[k], "isoformat"):
                rd[k] = rd[k].isoformat()
        if rd["category"] == "Unmapped":
            unmapped = rd
        elif rd["category"] == "Non-Equity (excluded)":
            # 2026-08-08 -- deliberately excluded from the response, not just
            # from the grid rendering: these dollars (bond/gold/commodity
            # ETFs) were never supposed to count toward an equity-sector
            # view. Kept as its own row in drv_category_perf (exhaustive-
            # partition invariant, auditable via SQL) but the user does not
            # want it surfaced anywhere in the UI -- not the grid, not a
            # note line, not the category filter dropdown (portfolio.js
            # sources its filter list from this same endpoint).
            continue
        else:
            out_rows.append(rd)

    return {
        "as_of": d.isoformat(), "axis": axis, "risk_budget": risk_budget,
        "accounts": accounts_list,
        "rows": out_rows, "unmapped": unmapped,
    }


# ---------------------------------------------------------------------------
# 6.3b GET /api/cockpit/factor-scorecard/{axis}/{category}/exposure-detail
#
# TASK_139 -- same drill-down as the Risk Dial's gauge exposure-detail (Screen
# D of the design doc: a Factor Scorecard row click, not a fired gauge). Only
# one (axis, category) pair here instead of a gauge's multi-category OR union,
# so the query is simpler than _gauge_exposure/get_gauge_exposure_detail --
# no need to fold sector/asset_class/style together, just match the one axis.
# Reused as-is by the Portfolio screen's Category filter (Screen E) to build
# both the "Exposure by account" panel and the position-table narrowing --
# see web/portfolio.js -- so this response's positions list is deliberately
# generic (symbol/account/dollar), not Dashboard-specific.
# ---------------------------------------------------------------------------

@router.get("/api/cockpit/factor-scorecard/{axis}/{category}/exposure-detail")
def get_factor_exposure_detail(axis: str, category: str, date: Optional[str] = Query(None),
                               accounts: Optional[str] = Query(
                                   None, description="Comma-separated account_number values -- "
                                   "narrows this popup to match the Cockpit Accounts filter "
                                   "active on the $ grid the row was clicked from.")):
    if axis not in ("sector", "asset_class", "style"):
        raise HTTPException(status_code=400, detail="axis must be sector|asset_class|style")
    d = _resolve_date(date)
    # 2026-08-09 BUGFIX -- this popup previously always showed ALL
    # accounts regardless of the Cockpit Accounts filter active on the $
    # grid it was opened from -- the filter narrowed the grid's own
    # numbers but the row-click popup ignored it entirely. Reuses the same
    # account_number-list filtering pattern as etl/derive_category_perf.py
    # ::_acct_clause (CS's `account` / F's `account_number` both store the
    # same domain as ref_accounts.account_number directly). User: "top 3
    # graphs -> also popups on the my accounts not considering the
    # filters (ex: one account)".
    accounts_list = [a.strip() for a in accounts.split(",") if a.strip()] if accounts else None
    cs_acct = " AND account = ANY(:accounts)" if accounts_list else ""
    # hist_f.account_number, qualified -- both call sites below LEFT JOIN
    # ref_accounts ra ON ra.account_number = hist_f.account_number, so an
    # unqualified "account_number" is ambiguous between the two tables
    # (caught live: psycopg.errors.AmbiguousColumn).
    f_acct = " AND hist_f.account_number = ANY(:accounts)" if accounts_list else ""
    with session_scope() as s:
        total_value = s.execute(text(
            "SELECT SUM(market_value) FROM drv_category_perf "
            "WHERE axis = 'asset_class' AND as_of_date = :d"
        ), {"d": d}).scalar()
        total_value = float(total_value) if total_value else None

        # 2026-08-09 BUGFIX -- Cash (asset_class axis) is classified via the
        # is_cash() SQL function (symbol/security_type/description text
        # patterns -- SPAXX**, "PENDING ACTIVITY", money-market
        # descriptions, etc; etl/derive_category_perf.py's own cash_keys
        # membership uses the exact same function), NOT via any drv_ma/
        # ref_sector asset_class column value -- no symbol has
        # asset_class='Cash' anywhere. The generic where_clause below
        # (COALESCE(m.asset_class, rs.asset_class) = :category) can
        # therefore never match a single row for category=Cash, even
        # though the aggregate grid card shows a real, large dollar figure
        # for it -- the popup silently returned $0/zero positions. Handled
        # as a dedicated early branch instead of teaching the generic
        # where_clause about is_cash(), since it's a completely different
        # matching mechanism (text patterns, not a column equality).
        # User: "asset class -> cash popup -> doesn't have data/details on
        # which account is holding how much or total cash amount".
        if axis == "asset_class" and category.strip().lower() == "cash":
            cash_rows = s.execute(text(f"""
                WITH pos AS (
                  SELECT hist_cs.tos_symbol, hist_cs.symbol,
                         COALESCE(ra.short_name, hist_cs.account) AS account,
                         market_value AS mv, hist_cs.security_type, hist_cs.description
                  FROM hist_cs
                  LEFT JOIN ref_accounts ra ON ra.account_number = hist_cs.account
                  WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
                    AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
                    AND is_cash(symbol, security_type, description)
                    {cs_acct}
                  UNION ALL
                  SELECT hist_f.tos_symbol, hist_f.symbol,
                         COALESCE(ra.short_name, hist_f.account_name, hist_f.account_number) AS account,
                         hist_f.current_value AS mv, hist_f.type AS security_type, hist_f.description
                  FROM hist_f
                  LEFT JOIN ref_accounts ra ON ra.account_number = hist_f.account_number
                  WHERE hist_f.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
                    AND COALESCE(ra.is_active, TRUE) = TRUE
                    AND is_cash(symbol, type, description)
                    {f_acct}
                )
                SELECT COALESCE(tos_symbol, symbol) AS symbol, account, SUM(mv) AS mv
                FROM pos GROUP BY COALESCE(tos_symbol, symbol), account
                ORDER BY mv DESC
            """), {"d": d, "accounts": accounts_list}).mappings().all()
            positions = [{"symbol": r["symbol"] or "CASH", "account": r["account"],
                          "dollar": round(float(r["mv"] or 0), 2),
                          "gain_dollar": None, "gain_pct": None,
                          "yesterday_dollar": None, "yesterday_pct": None}
                         for r in cash_rows]
            dollar = sum(p["dollar"] for p in positions)
            return {
                "as_of": d.isoformat(), "axis": axis, "category": category,
                "dollar": round(dollar, 2),
                "pct": round(dollar / total_value * 100.0, 2) if total_value else None,
                "positions": positions,
                "category_yesterday_pct": None, "sector_yesterday_pct": None,
            }

        # sector/asset_class match case-insensitively against drv_ma (see
        # _lc() docstring -- 'Health care' vs 'Health Care' is a real, live
        # variant); style labels come from a fixed vocabulary in
        # etl/derive_macro.py::_classify_style with no known case drift.
        # 2026-08-08 -- sector/style are equity-only axes (etl/derive_
        # category_perf.py::_categories_for excludes any symbol with a
        # KNOWN non-equity asset_class -- bond/gold/crypto/FX ETFs that
        # still carry a spurious GICS sector tag or beta/PE-derived style
        # tag from the data vendor, e.g. CLOX/CLOZ/BUXX tagging sector=
        # "Financials" despite being Fixed Income). This popup queried
        # hist_cs/hist_f directly and had no such filter, so a Sector/Style
        # row's exposure-detail popup could show non-equity holdings the
        # aggregate card itself had already excluded -- same exclusion
        # applied here (asset_class NULL/unknown still passes -- some real
        # equities have no asset_class tag but a valid sector, see
        # _categories_for's DESK/IPAY/NOBL/VYM docstring note).
        # 2026-08-09 -- COALESCE(m.*, rs.*) throughout below, not m.* alone
        # -- matches etl/derive_category_perf.py::_build_category_map's own
        # drv_ma-first/ref_sector-fallback precedence. drv_ma only has rows
        # for symbols in the CURRENT day's hist_td/TOSD universe
        # (drv_symbols); a symbol ToS never exports at all (e.g. GSL: held,
        # but not ToS-tracked) never gets a drv_ma row no matter what, so
        # this popup was one symbol short of the aggregate grid card
        # whenever that happened. Purely additive -- once a symbol gets a
        # real drv_ma row that value wins automatically (COALESCE order).
        # User: "fix it. Keep in mind i will be adding the new stock
        # symbols to tos exports. Not sure if your fix is going to affect
        # that" -- it doesn't.
        equity_only_clause = " AND (COALESCE(m.asset_class, rs.asset_class) IS NULL OR COALESCE(m.asset_class, rs.asset_class) = 'Equities')" \
            if axis in ("sector", "style") else ""
        category_param = category if axis == "style" else category.strip().lower()
        # category.strip().lower(), not category_param -- category_param
        # preserves case for style (real labels like "Low Beta" are
        # case-sensitive), so comparing IT against a lowercase literal
        # would never match "Unmapped" for axis=style.
        category_is_unmapped = category.strip().lower() == "unmapped"

        # 2026-08-08 -- "Unmapped" is a synthetic bucket, not a real
        # sector/asset_class/style value -- no symbol ever has
        # m.sector='Unmapped' in drv_ma, so a click on the Unmapped row
        # ("how can i see what stocks are unmapped?") previously matched
        # zero rows every time. Mirrors etl/derive_category_perf.py::
        # _categories_for's OWN routing rules for what lands in Unmapped:
        # sector -- no drv_ma row or no sector tag, PROVIDED it isn't a
        # known non-equity asset_class (those route to the separate
        # "Non-Equity (excluded)" category since 2026-08-08 and are never
        # shown in the UI -- this where_clause used to fold them back into
        # Unmapped, which made the popup show 16 mixed positions/$304,680
        # right after the grid label said 7.3%/$74,816.75; fixed to match
        # _categories_for exactly); asset_class -- no drv_ma row or no
        # asset_class tag; style -- no drv_ma row at all (a mapped equity
        # with zero qualifying style tags is NOT Unmapped, see
        # _categories_for's docstring -- that case just naturally matches no
        # style category and never reaches this popup).
        if category_is_unmapped:
            if axis == "sector":
                where_clause = ("COALESCE(m.sector, rs.equity_sector) IS NULL "
                                 "AND (COALESCE(m.asset_class, rs.asset_class) IS NULL OR COALESCE(m.asset_class, rs.asset_class) = 'Equities')")
            elif axis == "asset_class":
                where_clause = "COALESCE(m.asset_class, rs.asset_class) IS NULL"
            else:  # style
                where_clause = "m.tos_symbol IS NULL"
        elif axis == "style":
            where_clause = """
                EXISTS (
                    SELECT 1 FROM jsonb_array_elements(COALESCE(ms.style_stances, '[]'::jsonb)) e
                    WHERE e->>'label' = :category
                )""" + equity_only_clause
        else:
            col = "COALESCE(m.sector, rs.equity_sector)" if axis == "sector" else "COALESCE(m.asset_class, rs.asset_class)"
            where_clause = f"LOWER(TRIM({col})) = :category" + equity_only_clause

        # 2026-08-08 -- cost_basis/gain_dollar carried through for the
        # popup's %gain/loss column (unrealized, current snapshot only --
        # hist_cs.cost_basis/gain_dollar, hist_f.cost_basis_total/
        # total_gl_dollar). gain_pct is derived AFTER aggregation
        # (gain_dollar/cost_basis), not summed/averaged directly, so it's
        # correct even if a symbol+account somehow spans multiple source
        # rows (naively averaging two rows' gain_pct would be wrong).
        # sector/style axes never include cash at all (etl/_build_series
        # excludes cash_keys from those series entirely -- it only ever
        # appears in asset_class's own "Cash" bucket, assigned by cash_keys
        # membership, NOT via drv_ma.asset_class -- cash symbols have no
        # drv_ma row). This popup queries hist_cs/hist_f directly with no
        # such filter, so without this a click on Sector/Style's Unmapped
        # row would list cash lines too, and (since cash's "no drv_ma row"
        # look identical to a genuinely-unmapped symbol) so would
        # asset_class's OWN Unmapped row -- excluded in both cases to match
        # the aggregate's universe; asset_class's real "Cash" category is
        # unaffected (this only touches the Unmapped special-case).
        cash_exclude_clause = " AND NOT is_cash(symbol, security_type, description)" \
            if axis in ("sector", "style") or (axis == "asset_class" and category_is_unmapped) else ""
        # 2026-08-08 -- Account column uses ref_accounts.short_name only,
        # same as get_gauge_exposure_detail -- user: "popup -> left column
        # grid (stock listing) -> use account desc".
        rows = s.execute(text(f"""
            WITH pos AS (
              SELECT hist_cs.tos_symbol, COALESCE(ra.short_name, hist_cs.account) AS account,
                     market_value AS mv, cost_basis AS cb, gain_dollar AS gl
              FROM hist_cs
              LEFT JOIN ref_accounts ra ON ra.account_number = hist_cs.account
              WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
                AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
                {cash_exclude_clause}
                {cs_acct}
              UNION ALL
              SELECT hist_f.tos_symbol,
                     COALESCE(ra.short_name, hist_f.account_name, hist_f.account_number) AS account,
                     hist_f.current_value AS mv,
                     hist_f.cost_basis_total AS cb, hist_f.total_gl_dollar AS gl
              FROM hist_f
              LEFT JOIN ref_accounts ra ON ra.account_number = hist_f.account_number
              WHERE hist_f.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
                AND COALESCE(ra.is_active, TRUE) = TRUE
                {cash_exclude_clause.replace('security_type', 'type') if cash_exclude_clause else ''}
                {f_acct}
            ), agg AS (SELECT tos_symbol, account, SUM(mv) AS mv, SUM(cb) AS cb, SUM(gl) AS gl
                       FROM pos GROUP BY tos_symbol, account)
            SELECT a.tos_symbol, a.account, a.mv, a.cb, a.gl
            FROM agg a
            LEFT JOIN drv_ma m ON m.tos_symbol = a.tos_symbol AND m.as_of_date = :d
            LEFT JOIN drv_macro_score ms ON ms.tos_symbol = a.tos_symbol AND ms.as_of_date = :d
            LEFT JOIN ref_sector rs ON rs.ticker = a.tos_symbol
            WHERE {where_clause}
            ORDER BY a.mv DESC
        """), {"d": d, "category": category_param, "accounts": accounts_list}).mappings().all()
        yesterday_map = _yesterday_by_symbol_account(s, d)

        def _gain_fields(r):
            cb, gl = r["cb"], r["gl"]
            gain_dollar = round(float(gl), 2) if gl is not None else None
            gain_pct = round(float(gl) / float(cb) * 100.0, 2) if (cb and gl is not None) else None
            return gain_dollar, gain_pct

        # 2026-08-08 -- broker's own daily gain/loss, from YESTERDAY's
        # snapshot, not this row's own -- see _yesterday_by_symbol_account's
        # docstring. User request: "Can the popups include these numbers
        # for each stock?"
        def _yesterday_fields(r):
            yd, ypct = yesterday_map.get((r["tos_symbol"], r["account"]), (None, None))
            return (round(float(yd), 2) if yd is not None else None,
                    round(float(ypct), 2) if ypct is not None else None)

        positions = []
        for r in rows:
            gain_dollar, gain_pct = _gain_fields(r)
            yesterday_dollar, yesterday_pct = _yesterday_fields(r)
            positions.append({"symbol": r["tos_symbol"], "account": r["account"],
                               "dollar": round(float(r["mv"] or 0), 2),
                               "gain_dollar": gain_dollar, "gain_pct": gain_pct,
                               "yesterday_dollar": yesterday_dollar, "yesterday_pct": yesterday_pct})
        dollar = sum(p["dollar"] for p in positions)

        # 2026-08-08 -- closed/sold positions (this fiscal year) for this
        # one axis/category, reusing the exact same `where_clause` (incl.
        # the Unmapped/equity-only special-casing) the open-position query
        # above already computed -- same m./ms. aliases via
        # _CLOSED_CLASSIFY_JOIN. $0 current exposure, excluded from
        # `dollar`/`pct` (computed above, unaffected). User: "is there a
        # way i can see closed/sold positions also in these dashboard
        # graphs".
        closed_rows = s.execute(text(f"""
            WITH {_closed_positions_base(d, accounts_list)}
            SELECT c.tos_symbol, c.account, c.sell_date, c.gl, c.glpct
            FROM closed c
            {_CLOSED_CLASSIFY_JOIN}
            WHERE {where_clause}
            ORDER BY c.sell_date DESC
        """), {"d": d, "category": category_param, "accounts": accounts_list}).mappings().all()
        for r in closed_rows:
            gl = r["gl"]
            positions.append({
                "symbol": r["tos_symbol"], "account": r["account"],
                "closed": True, "sell_date": r["sell_date"].isoformat(),
                "dollar": 0.0,
                "realized_gain_dollar": round(float(gl), 2) if gl is not None else None,
                "realized_gain_pct": round(float(r["glpct"]), 2) if r["glpct"] is not None else None,
            })

        # 2026-08-08 -- category's own Yesterday % (the whole category,
        # already-computed by etl/derive_category_perf.py::
        # _yesterday_actual_change) and the benchmark ETF's Yesterday %
        # (the "sector"/market reference) -- for the new "stock vs rest vs
        # sector" comparison chart. User: "show it as a stock's %gain/loss
        # of the category vs rest vs sector" -- "rest" (category minus this
        # stock) is derived client-side from the positions list already
        # returned (each carries its own yesterday_dollar); only "sector"
        # (the benchmark) needs a value not derivable from position data.
        cat_perf_row = s.execute(text(
            "SELECT twr_yesterday, bench_yesterday FROM drv_category_perf"
            " WHERE axis = :axis AND category = :cat AND as_of_date = :d"
        ), {"axis": axis, "cat": category, "d": d}).mappings().first()
        category_yesterday_pct = (round(float(cat_perf_row["twr_yesterday"]) * 100, 2)
                                   if cat_perf_row and cat_perf_row["twr_yesterday"] is not None else None)
        sector_yesterday_pct = (round(float(cat_perf_row["bench_yesterday"]) * 100, 2)
                                 if cat_perf_row and cat_perf_row["bench_yesterday"] is not None else None)

        return {
            "as_of": d.isoformat(),
            "axis": axis,
            "category": category,
            "dollar": round(dollar, 2),
            "pct": round(dollar / total_value * 100.0, 2) if total_value else None,
            "positions": positions,
            "category_yesterday_pct": category_yesterday_pct,
            "sector_yesterday_pct": sector_yesterday_pct,
        }


# ---------------------------------------------------------------------------
# 6.3c GET /api/cockpit/symbol-daily-change -- per-day $/% for one symbol,
# across every snapshot date we have it (broker day_chng_dollar/today_gl_
# dollar, same figures the Yesterday column/popup already use, just one
# symbol's full history instead of a single day). Powers the exposure-
# detail popup's "select a stock, see its daily bars" chart -- user
# request: "i also want to see daily (or imported days) gains/losses as a
# graph when i select a specific stock ... Use one graph and change the
# bars based on the stock selection."
# ---------------------------------------------------------------------------

@router.get("/api/cockpit/symbol-daily-change")
def get_symbol_daily_change(symbol: str = Query(...), days: int = Query(30, ge=1, le=180),
                             date: Optional[str] = Query(None)):
    sym = symbol.strip().upper()
    # 2026-08-08 -- anchor-gated at <= :d (not < :d). A prior version
    # excluded the anchor's own snapshot on the theory it's never a
    # finalized capture -- wrong: CS/F loads land in the evening, well
    # after market close (confirmed via hist_cs.loaded_at ~18:xx on the
    # snapshot's own date), so a `d`-dated row IS the real, finalized
    # close figure once it exists. Matches _yesterday_by_symbol_account's
    # same fix. User: "shouldn't I see that data in the grid instead of
    # 8/6 data... I need to see market close data and corresponding bar."
    d = _resolve_date(date)
    with session_scope() as s:
        by_date: dict = {}
        for r in s.execute(text("""
            SELECT snapshot_date, SUM(day_chng_dollar) AS dc, AVG(day_chng_pct) AS dp
            FROM hist_cs WHERE tos_symbol = :sym AND snapshot_date <= :d
              AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
            GROUP BY snapshot_date
        """), {"sym": sym, "d": d}).mappings().all():
            by_date[r["snapshot_date"]] = (float(r["dc"] or 0), float(r["dp"]) if r["dp"] is not None else None)
        for r in s.execute(text("""
            SELECT snapshot_date, SUM(today_gl_dollar) AS dc, AVG(today_gl_pct) AS dp
            FROM hist_f WHERE tos_symbol = :sym AND snapshot_date <= :d
              AND account_number NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
            GROUP BY snapshot_date
        """), {"sym": sym, "d": d}).mappings().all():
            prev = by_date.get(r["snapshot_date"])
            dc = float(r["dc"] or 0) + (prev[0] if prev else 0)
            dp = float(r["dp"]) if r["dp"] is not None else (prev[1] if prev else None)
            by_date[r["snapshot_date"]] = (dc, dp)

        # 2026-08-08 -- synthetic "Today" bar, marked-to-market (yesterday's
        # held qty x live drv_quote price), ONLY when the anchor's own CS/F
        # snapshot hasn't loaded yet (mid-day, before the evening file
        # lands) -- i.e. `d` has no real entry in by_date above. Once the
        # real snapshot lands, the loop above already supplies the real
        # bar and this is skipped entirely. Same technique
        # etl/derive_category_perf.py::_today_marked_to_market uses at
        # category level, as a live preview only.
        today_entry = None
        if d not in by_date:
            d_prev = s.execute(text("""
                SELECT MAX(sd) FROM (
                  SELECT MAX(snapshot_date) AS sd FROM hist_cs WHERE snapshot_date < :d
                  UNION ALL
                  SELECT MAX(snapshot_date) AS sd FROM hist_f WHERE snapshot_date < :d
                ) t
            """), {"d": d}).scalar()
            if d_prev:
                qty = s.execute(text("""
                    SELECT
                      COALESCE((SELECT SUM(qty) FROM hist_cs WHERE tos_symbol=:sym AND snapshot_date=:dp
                                AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active=FALSE)),0)
                    + COALESCE((SELECT SUM(qty) FROM hist_f WHERE tos_symbol=:sym AND snapshot_date=:dp
                                AND account_number NOT IN (SELECT account_number FROM ref_accounts WHERE is_active=FALSE)),0)
                      AS qty
                """), {"sym": sym, "dp": d_prev}).scalar()
                qty = float(qty) if qty else 0.0
                if qty:
                    px = {r["as_of_date"]: float(r["last_price"]) for r in s.execute(text(
                        "SELECT as_of_date, last_price FROM drv_quote WHERE tos_symbol=:sym"
                        " AND as_of_date IN (:dp, :d) AND last_price IS NOT NULL"
                    ), {"sym": sym, "dp": d_prev, "d": d}).mappings().all()}
                    p_prev = px.get(d_prev)
                    if p_prev:
                        p_today = px.get(d, p_prev)  # no live tick yet -> flat vs yesterday's close
                        dollar = qty * (p_today - p_prev)
                        pct = (p_today - p_prev) / p_prev * 100
                        today_entry = {"date": d.isoformat(), "dollar": round(dollar, 2), "pct": round(pct, 2)}

        dates = sorted(by_date.keys())[-days:]
        out_days = [{"date": dt.isoformat(), "dollar": round(by_date[dt][0], 2),
                     "pct": round(by_date[dt][1], 2) if by_date[dt][1] is not None else None}
                    for dt in dates]
        if today_entry:
            out_days.append(today_entry)
        return {"symbol": sym, "days": out_days}


# ---------------------------------------------------------------------------
# 6.3d GET /api/cockpit/benchmark-daily-change -- per-day % change for a bare
# ETF/index symbol (e.g. XLK, SPY) with NO holdings involved -- Market View's
# stock-details popup daily gain/loss chart (user: "right side graphs ->
# daily gain/loss for given sector symbol (ex: XLK for tech etc)").
# symbol-daily-change above only works for symbols you actually hold
# (queries hist_cs/hist_f); this reads drv_quote's own daily net_chng/
# pct_change instead, which exists for any tracked symbol regardless of
# whether it's ever been a position.
# ---------------------------------------------------------------------------

@router.get("/api/cockpit/benchmark-daily-change")
def get_benchmark_daily_change(symbol: str = Query(...), days: int = Query(30, ge=1, le=180),
                                date: Optional[str] = Query(None)):
    # 2026-08-10 -- `symbol` may be a "+"-joined blend (e.g.
    # "BUXX+CLOX+CLOZ", Fixed Income's drv_category_perf.bench_symbol label
    # -- see etl/derive_category_perf.py::_bench_symbol_label/_bench_return)
    # instead of one ticker. Blended day = equal-weighted average of
    # whichever members have a value that day (not requiring all three --
    # same partial-blend tolerance _bench_return uses for the window
    # returns), so the daily chart stays consistent with the MTD/QTD/YTD
    # numbers next to it.
    syms = [s.strip().upper() for s in symbol.split("+") if s.strip()]
    d = _resolve_date(date)
    with session_scope() as s:
        by_date: dict = {}
        for sym in syms:
            rows = s.execute(text(
                "SELECT as_of_date, net_chng, pct_change FROM drv_quote"
                " WHERE tos_symbol = :sym AND as_of_date <= :d"
                " ORDER BY as_of_date DESC LIMIT :n"
            ), {"sym": sym, "d": d, "n": days}).fetchall()
            for r in rows:
                bucket = by_date.setdefault(r[0], {"dollar": [], "pct": []})
                if r[1] is not None:
                    bucket["dollar"].append(float(r[1]))
                if r[2] is not None:
                    bucket["pct"].append(float(r[2]))
        dates = sorted(by_date.keys())[-days:]
        out_days = [{"date": dt.isoformat(),
                     "dollar": (sum(by_date[dt]["dollar"]) / len(by_date[dt]["dollar"])) if by_date[dt]["dollar"] else None,
                     "pct": (sum(by_date[dt]["pct"]) / len(by_date[dt]["pct"])) if by_date[dt]["pct"] else None}
                    for dt in dates]
        return {"symbol": "+".join(syms), "days": out_days}


# ---------------------------------------------------------------------------
# 6.4 GET /api/cockpit/shortlist
# ---------------------------------------------------------------------------

# Round-2 investigation clarified a spec ambiguity (TASK_133 6.4): "Excluded
# always: ... Gate/Mixed confidence" reads as a BUY-side restriction (the buy
# path is narrowly RR/SSS+B only, never gate-based) -- it can't also be an
# absolute exclusion, because the very next line explicitly allows "gate-
# confidence sells", matching docs/actionable_playbook.md's own framing
# ("trust SA/gate sells; distrust SS/high sells"). Implemented as: buys never
# include fc_confidence IN ('gate','mixed'); sells are SA OR fc_confidence=
# 'gate'; 'mixed' is excluded on both sides (unambiguous). See DEV_HANDOFF.md.
# TASK_137: SO ("Sell Overage") is excluded outright, regardless of which OR
# branch would otherwise admit it. SO/OVER_MAX (etl/derive_actionable.py
# _FC_MAP) is a position-sizing action -- it fires because a holding drifted
# above its ref_asset_allocation category ceiling, not because the market
# signaled anything -- so it is not an edge-validated trade and must never
# occupy one of the three Shortlist slots. Do not re-admit it via the sell
# branch below.
_SHORTLIST_SQL = text("""
    SELECT a.tos_symbol, a.description, a.final_code, a.final_side,
           a.winning_source, a.consolidated_action, a.current_position_dollar,
           a.stop_breached, a.fc_confidence, r.rr_bull_bear
    FROM drv_actionable a
    LEFT JOIN drv_tn_td_bb_rr r
      ON r.tos_symbol = a.tos_symbol AND r.as_of_date = a.as_of_date
    WHERE a.as_of_date = :d
      AND COALESCE(a.fc_confidence, '') <> 'mixed'
      AND COALESCE(a.final_code, '') <> 'SO'
      AND (
        (a.final_code IN ('BM', 'BMN') AND a.winning_source IN ('RR', 'SSS')
         AND r.rr_bull_bear = 'B' AND COALESCE(a.stop_breached, FALSE) = FALSE
         AND COALESCE(a.fc_confidence, '') NOT IN ('gate', 'mixed'))
        OR (a.final_code = 'SA')
        OR (a.final_side = 'sell' AND a.fc_confidence = 'gate')
      )
""")


# ---------------------------------------------------------------------------
# 6.5 GET /api/cockpit/housekeeping -- TASK_134 C.1: per-account
# transaction-feed staleness. Positions (hist_cs/hist_f) keep updating daily
# even when the matching transaction feed (hist_cst/hist_ft) has stalled or
# never loaded -- every trade in that account is then invisible to netflow
# detection, degrading flows_confidence/factor-scorecard returns silently.
# This surfaces the gap instead of quietly showing weakened numbers.
# ---------------------------------------------------------------------------

_TXN_GAP_SQL = text("""
    WITH cs_pos AS (
      SELECT account, MAX(snapshot_date) AS pos_date FROM hist_cs GROUP BY account
    ), cs_txn AS (
      SELECT account, MAX(trade_date) AS txn_date FROM hist_cst GROUP BY account
    ), f_pos AS (
      SELECT account_number, MAX(snapshot_date) AS pos_date,
             MAX(account_name) AS account_name FROM hist_f GROUP BY account_number
    ), f_txn AS (
      SELECT account_number, MAX(trade_date) AS txn_date FROM hist_ft GROUP BY account_number
    )
    SELECT 'Schwab' AS broker, p.account AS account, p.account AS account_id,
           p.pos_date, t.txn_date
      FROM cs_pos p LEFT JOIN cs_txn t ON t.account = p.account
     WHERE p.account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
    UNION ALL
    SELECT 'Fidelity' AS broker, COALESCE(p.account_name, p.account_number) AS account,
           p.account_number AS account_id, p.pos_date, t.txn_date
      FROM f_pos p LEFT JOIN f_txn t ON t.account_number = p.account_number
     WHERE p.account_number NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
""")

_TXN_GAP_TRADING_DAYS = 10  # spec C.1: flag any account more than this apart


def _txn_feed_gaps(session, as_of_date) -> list:
    """[{broker, account, positions_last, transactions_last, gap_trading_days}]
    for every account where hist_cst/hist_ft has fallen more than
    _TXN_GAP_TRADING_DAYS trading days behind hist_cs/hist_f (or never
    loaded a single row). Trading days are approximated by the count of
    distinct hist_td export_date rows in the interval -- the app's own
    definition of "a day the market traded" (docs/derive_date_logic.md)."""
    rows = session.execute(_TXN_GAP_SQL).all()
    out = []
    for broker, account, account_id, pos_date, txn_date in rows:
        if pos_date is None or account is None:
            continue
        if txn_date is None:
            gap_days = None  # zero transaction rows, ever
        else:
            gap_days = session.execute(text(
                "SELECT COUNT(DISTINCT export_date) FROM hist_td "
                "WHERE export_date > :t AND export_date <= :p"
            ), {"t": txn_date, "p": pos_date}).scalar() or 0
        flagged = txn_date is None or gap_days > _TXN_GAP_TRADING_DAYS
        if not flagged:
            continue
        out.append({
            "broker": broker, "account": account, "account_id": account_id,
            "positions_last": pos_date.isoformat(),
            "transactions_last": txn_date.isoformat() if txn_date else None,
            "gap_trading_days": gap_days,
        })
    return out


@router.get("/api/cockpit/housekeeping")
def get_housekeeping(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        gaps = _txn_feed_gaps(s, d)
    return {"as_of": d.isoformat(), "txn_feed_gaps": gaps, "degraded_returns": len(gaps) > 0}


@router.get("/api/cockpit/shortlist")
def get_shortlist(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        rows = s.execute(_SHORTLIST_SQL, {"d": d}).mappings().all()

    # "Existing default sort (dollar-weighted edge, TASK_120)" lives entirely
    # client-side in web/actionable.js (~200 lines of tiered scoring against
    # rules_engine_fires + live scorecard edges) -- reimplementing it here
    # would be new ranking logic, which the spec explicitly forbids. Using
    # current_position_dollar desc as the practical "dollar-weighted" proxy
    # already available server-side; documented in DEV_HANDOFF.md.
    ranked = sorted(rows, key=lambda r: float(r["current_position_dollar"] or 0), reverse=True)
    out = []
    for r in ranked[:3]:
        rd = dict(r)
        out.append(rd)
    return {"as_of": d.isoformat(), "rows": out}
