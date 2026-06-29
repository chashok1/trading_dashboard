"""
Hedgeye action data for the Actionable screen (TASK_100).

GET /api/actionable/hedgeye?date=YYYY-MM-DD
  Surfaces the intraday "money-maker" Hedgeye feeds for one date:
    - top5         : The Call's Top-5 actionable ideas (hist_call_top5)
    - alerts       : today's Real-Time Alerts, non-superseded (hist_rta)
    - trend_flips  : day-over-day Risk Range outlook flips (drv_rr_trend_change)
    - stance       : Macro Show Bullish/Bearish ticker lists (hist_hedgeye_stance)

Read-only. date defaults to the anchor via _resolve_date. tos_symbol everywhere.
"""
from __future__ import annotations

from typing import Optional

import json

from pathlib import Path

from fastapi import APIRouter, Query, Body, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text

from etl.db import session_scope
from api._helpers import _resolve_date

router = APIRouter(tags=["hedgeye"])


@router.get("/api/actionable/hedgeye")
def actionable_hedgeye(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    out: dict = {
        "date": d.isoformat(),
        "top5": [],
        "alerts": [],
        "trend_flips": [],
        "stance": {"bullish": [], "bearish": []},
    }

    with session_scope() as s:
        # Compute effective date: clamp up to latest available Hedgeye data.
        # Hedgeye emails arrive intraday and may be dated newer than the anchor
        # (TOSD) date, causing exact-date filters to return nothing. Use the
        # most-recent available Hedgeye date when it is newer than the anchor.
        latest_q = (
            "SELECT MAX(d) FROM ("
            "SELECT MAX(snapshot_date) d FROM hist_rta "
            "UNION ALL SELECT MAX(snapshot_date) FROM hist_call_top5) sub"
        )
        latest_hedgeye = s.execute(text(latest_q)).scalar()
        effective_date = max(d, latest_hedgeye) if latest_hedgeye else d
        out["as_of"] = effective_date.isoformat()

        # Top-5 actionable ideas — latest call snapshot on/before effective_date.
        top_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_call_top5"
            " WHERE snapshot_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if top_date is not None:
            rows = s.execute(text(
                "SELECT rank, COALESCE(tos_symbol, symbol) AS sym, side, rationale_snippet "
                "FROM hist_call_top5 WHERE snapshot_date = :td ORDER BY rank"
            ), {"td": top_date}).fetchall()
            out["top5"] = [
                {"rank": r[0], "symbol": r[1], "side": r[2], "rationale": r[3]}
                for r in rows
            ]
            out["top5_date"] = top_date.isoformat()

        # Real-Time Alerts — latest snapshot on/before effective_date, non-superseded.
        rta_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_rta WHERE snapshot_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if rta_date is not None:
            rows = s.execute(text(
                "SELECT alert_ts, action, side, COALESCE(tos_symbol, symbol) AS sym, price, "
                "dur_trade, dur_trend, dur_tail, is_correction, coaching_notes "
                "FROM hist_rta WHERE snapshot_date = :rd AND superseded = FALSE "
                "ORDER BY alert_ts DESC"
            ), {"rd": rta_date}).fetchall()
            for r in rows:
                durs = []
                if r[5]:
                    durs.append("TRADE")
                if r[6]:
                    durs.append("TREND")
                if r[7]:
                    durs.append("TAIL")
                out["alerts"].append({
                    "ts": r[0].isoformat() if r[0] is not None else None,
                    "action": r[1],
                    "side": r[2],
                    "symbol": r[3],
                    "price": float(r[4]) if r[4] is not None else None,
                    "durations": durs,
                    "is_correction": bool(r[8]),
                    "notes": r[9],
                })

        # Risk Range trend flips — latest as_of_date on/before effective_date.
        flip_date = s.execute(text(
            "SELECT MAX(as_of_date) FROM drv_rr_trend_change WHERE as_of_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if flip_date is not None:
            rows = s.execute(text(
                "SELECT tos_symbol, from_trend, to_trend "
                "FROM drv_rr_trend_change WHERE as_of_date = :fd ORDER BY tos_symbol"
            ), {"fd": flip_date}).fetchall()
            out["trend_flips"] = [
                {"symbol": r[0], "from": r[1], "to": r[2]} for r in rows
            ]

        # Macro Show stance — latest stance snapshot on/before effective_date.
        stance_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_hedgeye_stance WHERE snapshot_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if stance_date is not None:
            rows = s.execute(text(
                "SELECT stance, COALESCE(tos_symbol, symbol) AS sym "
                "FROM hist_hedgeye_stance WHERE snapshot_date = :sd "
                "AND COALESCE(tos_symbol, symbol) IS NOT NULL ORDER BY sym"
            ), {"sd": stance_date}).fetchall()
            for st, sym in rows:
                key = "bullish" if (st or "").strip().lower().startswith("bull") else \
                      "bearish" if (st or "").strip().lower().startswith("bear") else None
                if key:
                    out["stance"][key].append(sym)
            out["stance_date"] = stance_date.isoformat()

        # Hedgeye Positions — latest hist_call snapshot on/before effective_date.
        call_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_call WHERE snapshot_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if call_date is not None:
            call_rows = s.execute(text(
                "SELECT COALESCE(tos_symbol,symbol) sym, outlook, outlook_modifier"
                " FROM hist_call WHERE snapshot_date = :cd"
                " ORDER BY CASE WHEN outlook_modifier LIKE 'best idea%'"
                " THEN 0 ELSE 1 END, sym"
            ), {"cd": call_date}).fetchall()
            out["positions"] = {
                "date": call_date.isoformat(),
                "longs": [
                    {"sym": r[0], "best": "best idea" in (r[2] or "")}
                    for r in call_rows if r[1] == "BULLISH"
                ],
                "shorts": [
                    {"sym": r[0], "best": "best idea" in (r[2] or "")}
                    for r in call_rows if r[1] == "BEARISH"
                ],
                "neutral": [
                    {"sym": r[0]}
                    for r in call_rows if r[1] == "NEUTRAL"
                ],
            }

        # Early Look — latest key takeaways on/before effective_date.
        el_row = s.execute(text(
            "SELECT note_date, subject, note_text FROM note_repo"
            " WHERE source_type='early_look' AND note_date <= :eff"
            " ORDER BY note_date DESC, note_id DESC LIMIT 1"
        ), {"eff": effective_date}).first()
        if el_row:
            out["early_look"] = {
                "date": el_row[0].isoformat(),
                "subject": el_row[1],
                "takeaways": el_row[2],
            }

        # Market Situation Report — latest gamma metrics on/before effective_date.
        msr_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_msr WHERE snapshot_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if msr_date is not None:
            msr_row = s.execute(text(
                "SELECT gamma_throttle, rvol_10day FROM hist_msr"
                " WHERE snapshot_date = :md"
            ), {"md": msr_date}).first()
            if msr_row:
                out["msr"] = {
                    "date": msr_date.isoformat(),
                    "gamma_throttle": (
                        float(msr_row[0]) if msr_row[0] is not None else None
                    ),
                    "rvol_10day": (
                        float(msr_row[1]) if msr_row[1] is not None else None
                    ),
                    "image_url": f"/api/msr/image?date={msr_date.isoformat()}",
                }

    return out


@router.get("/api/msr/image")
def msr_image(date: Optional[str] = Query(None)):
    from etl.hedgeye import config as hcfg
    msr_dir = hcfg.get("msr_dir") or hcfg.DEFAULTS.get("msr_dir", "")
    d = _resolve_date(date)
    img_path = Path(msr_dir) / f"MSR {d.isoformat()}.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="MSR image not found")
    return FileResponse(str(img_path), media_type="image/png")


# ---------------------------------------------------------------------------
# Notes repository (P3) — browse note_repo
# ---------------------------------------------------------------------------

@router.get("/api/notes")
def list_notes(date: Optional[str] = Query(None), ticker: Optional[str] = Query(None),
               source_type: Optional[str] = Query(None), q: Optional[str] = Query(None),
               limit: int = Query(200)):
    clauses, params = [], {"lim": min(max(limit, 1), 2000)}
    if date:
        clauses.append("note_date = :d"); params["d"] = date
    if source_type:
        clauses.append("source_type = :st"); params["st"] = source_type
    if ticker:
        clauses.append(":tk = ANY(tickers)"); params["tk"] = ticker.upper()
    if q:
        clauses.append("(note_text ILIKE :q OR subject ILIKE :q)"); params["q"] = "%" + q + "%"
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = ("SELECT note_id, note_date, source_type, analyst, subject, note_text, "
           "tickers, theme_tags, quad, gmail_link, status FROM note_repo" + where +
           " ORDER BY note_date DESC NULLS LAST, note_id DESC LIMIT :lim")
    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().fetchall()
    return [dict(r) for r in rows]


@router.get("/api/notes/source-types")
def note_source_types():
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT source_type, count(*) n FROM note_repo GROUP BY 1 ORDER BY 1"
        )).fetchall()
    return [{"source_type": r[0], "count": r[1]} for r in rows]


# ---------------------------------------------------------------------------
# Rule-candidate builder (P3) — rule_candidate CRUD
# ---------------------------------------------------------------------------

@router.get("/api/rule-candidates")
def list_rule_candidates(status: Optional[str] = Query(None)):
    sql = ("SELECT candidate_id, title, hypothesis, linked_note_ids, proposed_rule_def, "
           "status, promoted_rule_id, created_at, updated_at FROM rule_candidate")
    params = {}
    if status:
        sql += " WHERE status = :st"; params["st"] = status
    sql += " ORDER BY updated_at DESC"
    with session_scope() as s:
        rows = s.execute(text(sql), params).mappings().fetchall()
    return [dict(r) for r in rows]


@router.post("/api/rule-candidates")
def create_rule_candidate(payload: dict = Body(...)):
    rule = payload.get("proposed_rule_def")
    params = {
        "title": payload.get("title"),
        "hypothesis": payload.get("hypothesis"),
        "notes": [int(x) for x in (payload.get("linked_note_ids") or [])],
        "rule": json.dumps(rule) if rule is not None else None,
        "status": payload.get("status") or "draft",
    }
    with session_scope() as s:
        row = s.execute(text(
            "INSERT INTO rule_candidate (title, hypothesis, linked_note_ids, "
            "proposed_rule_def, status) VALUES (:title, :hypothesis, :notes, "
            "CAST(:rule AS JSONB), :status) RETURNING candidate_id"
        ), params).first()
    return {"candidate_id": row[0]}


@router.patch("/api/rule-candidates/{cid}")
def update_rule_candidate(cid: int, payload: dict = Body(...)):
    sets, params = [], {"cid": cid}
    for k in ("title", "hypothesis", "status", "promoted_rule_id"):
        if k in payload:
            sets.append(k + " = :" + k); params[k] = payload[k]
    if "proposed_rule_def" in payload:
        sets.append("proposed_rule_def = CAST(:rule AS JSONB)")
        params["rule"] = json.dumps(payload["proposed_rule_def"])
    if not sets:
        raise HTTPException(status_code=400, detail="no updatable fields")
    sets.append("updated_at = now()")
    with session_scope() as s:
        r = s.execute(text(
            "UPDATE rule_candidate SET " + ", ".join(sets) +
            " WHERE candidate_id = :cid RETURNING candidate_id"
        ), params).first()
    if not r:
        raise HTTPException(status_code=404, detail="candidate not found")
    return {"candidate_id": r[0]}


# ---------------------------------------------------------------------------
# Digests (P4) — pre-open + weekly roll-up
# ---------------------------------------------------------------------------

def _notes_for(s, stypes, d, lim=5):
    rows = s.execute(text(
        "SELECT note_date, source_type, subject, note_text, gmail_link FROM note_repo "
        "WHERE source_type = ANY(:st) AND note_date <= :d "
        "ORDER BY note_date DESC, note_id DESC LIMIT :lim"
    ), {"st": stypes, "d": d, "lim": lim}).mappings().fetchall()
    return [dict(r) for r in rows]


@router.get("/api/digest/preopen")
def digest_preopen(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        sections = [
            {"label": "Market Situation", "notes": _notes_for(s, ["market_situation"], d)},
            {"label": "Early Look — Key Takeaways", "notes": _notes_for(s, ["early_look"], d)},
            {"label": "Macro Show / Top 3",
             "notes": _notes_for(s, ["top3", "macro_show_summary", "macro_show_access"], d)},
        ]
        alerts = s.execute(text(
            "SELECT alert_ts, action, side, COALESCE(tos_symbol, symbol) AS symbol, price "
            "FROM hist_rta WHERE snapshot_date = :d AND superseded = FALSE "
            "ORDER BY alert_ts DESC"
        ), {"d": d}).mappings().fetchall()
    return {"date": d.isoformat(), "sections": sections,
            "overnight_alerts": [dict(r) for r in alerts]}


@router.get("/api/digest/weekly")
def digest_weekly(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        ps_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_ps WHERE snapshot_date <= :d"
        ), {"d": d}).scalar()
        ps = []
        if ps_date is not None:
            ps = [dict(r) for r in s.execute(text(
                "SELECT rank, COALESCE(tos_symbol, ticker) AS ticker, asset_class, "
                "position_sizing FROM hist_ps WHERE snapshot_date = :pd ORDER BY rank LIMIT 25"
            ), {"pd": ps_date}).mappings().fetchall()]
        notes = _notes_for(s, ["macro_week_summary", "quarterly_outlook", "inflation_nowcast"], d, lim=12)
    return {"date": d.isoformat(),
            "ps_date": ps_date.isoformat() if ps_date else None,
            "portfolio_solutions": ps, "notes": notes}


# ---------------------------------------------------------------------------
# Quad/MACRO overlay tie-in (P4) — latest Hedgeye-derived Quad signal (read-only)
# ---------------------------------------------------------------------------

@router.get("/api/macro/hedgeye-quad")
def hedgeye_quad(date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    with session_scope() as s:
        row = s.execute(text(
            "SELECT note_date, quad, source_type, subject, gmail_link FROM note_repo "
            "WHERE quad IS NOT NULL AND note_date <= :d "
            "ORDER BY note_date DESC, note_id DESC LIMIT 1"
        ), {"d": d}).mappings().first()
    return dict(row) if row else {"quad": None, "date": d.isoformat()}


# ---------------------------------------------------------------------------
# Per-symbol Hedgeye dossier
# ---------------------------------------------------------------------------

@router.get("/api/symbol/{sym}/hedgeye")
def symbol_hedgeye(sym: str, date: Optional[str] = Query(None)):
    d = _resolve_date(date)
    u = sym.upper()
    out = {"symbol": u, "date": d.isoformat()}
    with session_scope() as s:
        out["risk_range"] = None
        rr = s.execute(text(
            "SELECT snapshot_date, outlook, buy_trade, sell_trade, last_price, market_close "
            "FROM hist_rr WHERE UPPER(COALESCE(tos_symbol, symbol)) = :u AND snapshot_date <= :d "
            "ORDER BY snapshot_date DESC LIMIT 1"
        ), {"u": u, "d": d}).mappings().first()
        if rr:
            out["risk_range"] = dict(rr)
        out["trend_flips"] = [dict(r) for r in s.execute(text(
            "SELECT as_of_date, from_trend, to_trend FROM drv_rr_trend_change "
            "WHERE UPPER(tos_symbol) = :u AND as_of_date <= :d ORDER BY as_of_date DESC LIMIT 10"
        ), {"u": u, "d": d}).mappings().fetchall()]
        out["alerts"] = [dict(r) for r in s.execute(text(
            "SELECT alert_ts, action, side, price, is_correction, superseded "
            "FROM hist_rta WHERE UPPER(COALESCE(tos_symbol, symbol)) = :u "
            "ORDER BY alert_ts DESC LIMIT 10"
        ), {"u": u}).mappings().fetchall()]
        out["ii_changes"] = [dict(r) for r in s.execute(text(
            "SELECT event_date, outlook, change_str FROM hist_iichg "
            "WHERE UPPER(COALESCE(tos_symbol, symbol)) = :u AND event_date <= :d "
            "ORDER BY event_date DESC LIMIT 10"
        ), {"u": u, "d": d}).mappings().fetchall()]
        out["etf_changes"] = [dict(r) for r in s.execute(text(
            "SELECT event_date, outlook, change_str FROM hist_etfchg "
            "WHERE UPPER(COALESCE(tos_symbol, symbol)) = :u AND event_date <= :d "
            "ORDER BY event_date DESC LIMIT 10"
        ), {"u": u, "d": d}).mappings().fetchall()]
        out["top5"] = [dict(r) for r in s.execute(text(
            "SELECT snapshot_date, rank, side, rationale_snippet FROM hist_call_top5 "
            "WHERE UPPER(COALESCE(tos_symbol, symbol)) = :u AND snapshot_date <= :d "
            "ORDER BY snapshot_date DESC LIMIT 10"
        ), {"u": u, "d": d}).mappings().fetchall()]
        out["notes"] = [dict(r) for r in s.execute(text(
            "SELECT note_date, source_type, subject, gmail_link FROM note_repo "
            "WHERE :u = ANY(tickers) AND note_date <= :d "
            "ORDER BY note_date DESC, note_id DESC LIMIT 15"
        ), {"u": u, "d": d}).mappings().fetchall()]
    return out


# ---------------------------------------------------------------------------
# LLM enrichment (optional, display-only) — read cached output if present
# ---------------------------------------------------------------------------

@router.get("/api/notes/{message_id}/llm")
def note_llm(message_id: str):
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT model, prompt_version, json_output, created_at FROM llm_analysis "
            "WHERE message_id = :m ORDER BY created_at DESC"
        ), {"m": message_id}).mappings().fetchall()
    return {"message_id": message_id, "enriched": [dict(r) for r in rows]}
