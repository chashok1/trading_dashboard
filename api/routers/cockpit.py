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
          GROUP BY tos_symbol
          UNION ALL
          SELECT tos_symbol, SUM(current_value) FROM hist_f
          WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
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
          UNION ALL
          SELECT tos_symbol, current_value AS mv FROM hist_f
          WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
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

        rows = s.execute(text("""
            WITH pos AS (
              SELECT tos_symbol, account, market_value AS mv FROM hist_cs
              WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
              UNION ALL
              SELECT hist_f.tos_symbol,
                     COALESCE(hist_f.account_name, hist_f.account_number) ||
                       COALESCE(' (' || ra.short_name || ')', ' (' || hist_f.account_number || ')') AS account,
                     hist_f.current_value AS mv
              FROM hist_f
              LEFT JOIN ref_accounts ra ON ra.account_number = hist_f.account_number
              WHERE hist_f.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
            ), agg AS (SELECT tos_symbol, account, SUM(mv) AS mv FROM pos GROUP BY tos_symbol, account)
            SELECT a.tos_symbol, a.account, a.mv, m.sector, m.asset_class, ms.style_stances
            FROM agg a
            LEFT JOIN drv_ma m ON m.tos_symbol = a.tos_symbol AND m.as_of_date = :d
            LEFT JOIN drv_macro_score ms ON ms.tos_symbol = a.tos_symbol AND ms.as_of_date = :d
            WHERE LOWER(TRIM(m.sector)) = ANY(:sector_cats)
               OR LOWER(TRIM(m.asset_class)) = ANY(:asset_cats)
               OR EXISTS (
                    SELECT 1 FROM jsonb_array_elements(COALESCE(ms.style_stances, '[]'::jsonb)) e
                    WHERE e->>'label' = ANY(:style_cats)
                  )
            ORDER BY a.mv DESC
        """), {"d": d, "sector_cats": _lc(sector_cats), "asset_cats": _lc(asset_cats),
               "style_cats": style_cats}).mappings().all()

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
            positions.append({"symbol": r["tos_symbol"], "account": r["account"],
                               "dollar": round(mv, 2), "tag": tag})

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
                         axis: str = Query("sector")):
    if axis not in ("sector", "asset_class", "style"):
        raise HTTPException(status_code=400, detail="axis must be sector|asset_class|style")
    d = _resolve_date(date)
    with session_scope() as s:
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
        rd["detail"] = _jsonb(rd["detail"])
        note = (rd["detail"] or {}).get("verdict_note") or ""
        rd["risk_budget_cap_applied"] = "capped to HOLD" in note
        for k in ("as_of_date",):
            if k in rd and hasattr(rd[k], "isoformat"):
                rd[k] = rd[k].isoformat()
        if rd["category"] == "Unmapped":
            unmapped = rd
        else:
            out_rows.append(rd)

    return {
        "as_of": d.isoformat(), "axis": axis, "risk_budget": risk_budget,
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
def get_factor_exposure_detail(axis: str, category: str, date: Optional[str] = Query(None)):
    if axis not in ("sector", "asset_class", "style"):
        raise HTTPException(status_code=400, detail="axis must be sector|asset_class|style")
    d = _resolve_date(date)
    with session_scope() as s:
        total_value = s.execute(text(
            "SELECT SUM(market_value) FROM drv_category_perf "
            "WHERE axis = 'asset_class' AND as_of_date = :d"
        ), {"d": d}).scalar()
        total_value = float(total_value) if total_value else None

        # sector/asset_class match case-insensitively against drv_ma (see
        # _lc() docstring -- 'Health care' vs 'Health Care' is a real, live
        # variant); style labels come from a fixed vocabulary in
        # etl/derive_macro.py::_classify_style with no known case drift.
        category_param = category if axis == "style" else category.strip().lower()
        if axis == "style":
            where_clause = """
                EXISTS (
                    SELECT 1 FROM jsonb_array_elements(COALESCE(ms.style_stances, '[]'::jsonb)) e
                    WHERE e->>'label' = :category
                )"""
        else:
            col = "m.sector" if axis == "sector" else "m.asset_class"
            where_clause = f"LOWER(TRIM({col})) = :category"

        rows = s.execute(text(f"""
            WITH pos AS (
              SELECT tos_symbol, account, market_value AS mv FROM hist_cs
              WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
              UNION ALL
              SELECT hist_f.tos_symbol,
                     COALESCE(hist_f.account_name, hist_f.account_number) ||
                       COALESCE(' (' || ra.short_name || ')', ' (' || hist_f.account_number || ')') AS account,
                     hist_f.current_value AS mv
              FROM hist_f
              LEFT JOIN ref_accounts ra ON ra.account_number = hist_f.account_number
              WHERE hist_f.snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
            ), agg AS (SELECT tos_symbol, account, SUM(mv) AS mv FROM pos GROUP BY tos_symbol, account)
            SELECT a.tos_symbol, a.account, a.mv
            FROM agg a
            LEFT JOIN drv_ma m ON m.tos_symbol = a.tos_symbol AND m.as_of_date = :d
            LEFT JOIN drv_macro_score ms ON ms.tos_symbol = a.tos_symbol AND ms.as_of_date = :d
            WHERE {where_clause}
            ORDER BY a.mv DESC
        """), {"d": d, "category": category_param}).mappings().all()

        positions = [{"symbol": r["tos_symbol"], "account": r["account"], "dollar": round(float(r["mv"] or 0), 2)}
                     for r in rows]
        dollar = sum(p["dollar"] for p in positions)

        return {
            "as_of": d.isoformat(),
            "axis": axis,
            "category": category,
            "dollar": round(dollar, 2),
            "pct": round(dollar / total_value * 100.0, 2) if total_value else None,
            "positions": positions,
        }


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
    UNION ALL
    SELECT 'Fidelity' AS broker, COALESCE(p.account_name, p.account_number) AS account,
           p.account_number AS account_id, p.pos_date, t.txn_date
      FROM f_pos p LEFT JOIN f_txn t ON t.account_number = p.account_number
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
