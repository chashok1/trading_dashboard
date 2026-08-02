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
    cat_rows = session.execute(text(
        "SELECT axis, category, market_value FROM drv_category_perf WHERE as_of_date = :d"
    ), {"d": d}).all()
    mv_map = {(a, c): float(v or 0) for a, c, v in cat_rows}
    dollar = sum(mv_map.get((a, c), 0.0) for a, c in trans)
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
_SHORTLIST_SQL = text("""
    SELECT a.tos_symbol, a.description, a.final_code, a.final_side,
           a.winning_source, a.consolidated_action, a.current_position_dollar,
           a.stop_breached, a.fc_confidence, r.rr_bull_bear
    FROM drv_actionable a
    LEFT JOIN drv_tn_td_bb_rr r
      ON r.tos_symbol = a.tos_symbol AND r.as_of_date = a.as_of_date
    WHERE a.as_of_date = :d
      AND COALESCE(a.fc_confidence, '') <> 'mixed'
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
