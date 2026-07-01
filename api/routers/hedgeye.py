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

import threading
from typing import Optional

import json

from pathlib import Path

from fastapi import APIRouter, Query, Body, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text

from etl.db import session_scope
from api._helpers import _resolve_date

_gmail_fetch_lock = threading.Lock()
_gmail_fetch_state: dict = {"running": False, "last_run": None, "last_count": None, "last_error": None}

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

    def _recv(s, table: str, date_col: str, date_val) -> Optional[str]:
        """received_at via message_id join (works when message_id is populated)."""
        if date_val is None:
            return None
        row = s.execute(text(
            f"SELECT m.received_at FROM meta_hedgeye_msg m"
            f" JOIN {table} h ON h.message_id = m.message_id"
            f" WHERE h.{date_col} = :d AND m.received_at IS NOT NULL"
            f" ORDER BY m.received_at DESC LIMIT 1"
        ), {"d": date_val}).scalar()
        return row.isoformat() if row else None

    def _recv_by_type(s, email_type: str, data_date) -> Optional[str]:
        """received_at by matching email_type + ET calendar date.
        Used for file-lane feeds (hist_call, hist_etfchg) whose message_id
        is never written by the file loader, and for derived tables."""
        if data_date is None:
            return None
        row = s.execute(text(
            "SELECT received_at FROM meta_hedgeye_msg"
            " WHERE email_type = :et AND received_at IS NOT NULL"
            " AND (received_at AT TIME ZONE 'America/New_York')::date = :d"
            " ORDER BY received_at DESC LIMIT 1"
        ), {"et": email_type, "d": data_date}).scalar()
        return row.isoformat() if row else None

    with session_scope() as s:
        # viewing_live: is `d` the current anchor (no historical date requested)?
        # Only then do we clamp up to "latest available" data — a historical
        # date must not look ahead to today's data (same no-look-ahead rule as
        # drv_quote; see docs/derive_date_logic.md).
        anchor = s.execute(text("SELECT MAX(as_of_date) FROM v_available_dates")).scalar()
        viewing_live = anchor is not None and d >= anchor

        # Compute effective date: clamp up to latest available Hedgeye data,
        # but only when viewing live (see viewing_live above).
        if viewing_live:
            latest_q = (
                "SELECT MAX(d) FROM ("
                "SELECT MAX(snapshot_date) d FROM hist_rta "
                "UNION ALL SELECT MAX(snapshot_date) FROM hist_call_top5 "
                "UNION ALL SELECT MAX(event_date) FROM hist_etfchg) sub"
            )
            latest_hedgeye = s.execute(text(latest_q)).scalar()
            effective_date = max(d, latest_hedgeye) if latest_hedgeye else d
        else:
            effective_date = d

        # Bound for note-only sections (Early Look, Call Macro): these aren't
        # anchored to market-close data, so when viewing live they can show up
        # through today's real calendar date; when viewing history they're
        # capped at `d` like everything else — no look-ahead.
        note_bound = s.execute(text("SELECT CURRENT_DATE")).scalar() if viewing_live else d
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
            out["top5_received_at"] = _recv(s, "hist_call_top5", "snapshot_date", top_date)

        # Real-Time Alerts — latest snapshot on/before effective_date, non-superseded.
        rta_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_rta WHERE snapshot_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if rta_date is not None:
            out["rta_date"] = rta_date.isoformat()
            out["rta_received_at"] = _recv(s, "hist_rta", "snapshot_date", rta_date)
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
        # drv_rr_trend_change is derived; flip_date = prev_biz_day of the RR email.
        # Match the risk_range email received the next 1-3 calendar days after flip_date.
        flip_date = s.execute(text(
            "SELECT MAX(as_of_date) FROM drv_rr_trend_change WHERE as_of_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if flip_date is not None:
            out["trend_flips_date"] = flip_date.isoformat()
            rr_recv = s.execute(text(
                "SELECT received_at FROM meta_hedgeye_msg"
                " WHERE email_type = 'risk_range' AND received_at IS NOT NULL"
                " AND (received_at AT TIME ZONE 'America/New_York')::date > :d"
                " AND (received_at AT TIME ZONE 'America/New_York')::date <= :d + interval '3 days'"
                " ORDER BY received_at LIMIT 1"
            ), {"d": flip_date}).scalar()
            if rr_recv:
                out["trend_flips_received_at"] = rr_recv.isoformat()
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
            out["stance_received_at"] = _recv(s, "hist_hedgeye_stance", "snapshot_date", stance_date)

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
                "received_at": _recv_by_type(s, "the_call", call_date),
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

        # ETF Pro changes — latest event_date on/before effective_date.
        etf_date = s.execute(text(
            "SELECT MAX(event_date) FROM hist_etfchg WHERE event_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if etf_date is not None:
            etf_rows = s.execute(text(
                "SELECT COALESCE(tos_symbol,symbol) sym, outlook, change_str"
                " FROM hist_etfchg WHERE event_date = :ed"
                " ORDER BY change_str, sym"
            ), {"ed": etf_date}).fetchall()
            out["etf_changes"] = {
                "date": etf_date.isoformat(),
                "received_at": _recv_by_type(s, "etf_changes", etf_date),
                "changes": [
                    {"sym": r[0], "side": r[1], "action": r[2]}
                    for r in etf_rows
                ],
            }

        # Signal Strength (SSS) changes — latest snapshot_date on/before effective_date.
        sss_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_sss_change WHERE snapshot_date <= :eff"
        ), {"eff": effective_date}).scalar()
        if sss_date is not None:
            sss_rows = s.execute(text(
                "SELECT COALESCE(tos_symbol,symbol) sym, action"
                " FROM hist_sss_change WHERE snapshot_date = :sd AND symbol != 'NONE'"
                " ORDER BY action DESC, sym"
            ), {"sd": sss_date}).fetchall()
            out["sss_changes"] = {
                "date": sss_date.isoformat(),
                "received_at": _recv(s, "hist_sss_change", "snapshot_date", sss_date),
                "changes": [{"sym": r[0], "action": r[1]} for r in sss_rows],
            }

        # Early Look — note-only, not anchored to market close: show up through
        # today regardless of effective_date (TOSD lag shouldn't hold back same-day analysis).
        el_row = s.execute(text(
            "SELECT note_date, subject, note_text, message_id FROM note_repo"
            " WHERE source_type='early_look' AND note_date <= :b"
            " ORDER BY note_date DESC, note_id DESC LIMIT 1"
        ), {"b": note_bound}).first()
        if el_row:
            recv = s.execute(text(
                "SELECT received_at FROM meta_hedgeye_msg WHERE message_id=:m"
                " AND received_at IS NOT NULL LIMIT 1"
            ), {"m": el_row[3]}).scalar()
            out["early_look"] = {
                "date": el_row[0].isoformat(),
                "received_at": recv.isoformat() if recv else None,
                "subject": el_row[1],
                "takeaways": el_row[2],
            }

        # The Call — Macro Commentary — note-only, same rationale as Early Look above.
        cm_row = s.execute(text(
            "SELECT note_date, subject, note_text, message_id FROM note_repo"
            " WHERE source_type='the_call_macro' AND note_date <= :b"
            " ORDER BY note_date DESC, note_id DESC LIMIT 1"
        ), {"b": note_bound}).first()
        if cm_row:
            recv = s.execute(text(
                "SELECT received_at FROM meta_hedgeye_msg WHERE message_id=:m"
                " AND received_at IS NOT NULL LIMIT 1"
            ), {"m": cm_row[3]}).scalar()
            out["call_macro"] = {
                "date": cm_row[0].isoformat(),
                "received_at": recv.isoformat() if recv else None,
                "subject": cm_row[1],
                "note_text": cm_row[2],
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
                    "received_at": _recv(s, "hist_msr", "snapshot_date", msr_date),
                    "gamma_throttle": (
                        float(msr_row[0]) if msr_row[0] is not None else None
                    ),
                    "rvol_10day": (
                        float(msr_row[1]) if msr_row[1] is not None else None
                    ),
                    "image_url": f"/api/msr/image?date={msr_date.isoformat()}",
                }

    return out


@router.get("/api/ext-links")
def ext_links():
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT panel_key, label, url FROM ext_links ORDER BY sort_order"
        )).fetchall()
    return {r[0]: {"label": r[1], "url": r[2]} for r in rows}


@router.put("/api/ext-links/{panel_key}")
def update_ext_link(panel_key: str, payload: dict = Body(...)):
    url = payload.get("url", "")
    with session_scope() as s:
        s.execute(text(
            "UPDATE ext_links SET url=:u WHERE panel_key=:k"
        ), {"u": url, "k": panel_key})
        s.commit()
    return {"panel_key": panel_key, "url": url}


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
           "tickers, theme_tags, quad, signal_kind, gmail_link, status FROM note_repo" + where +
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

@router.get("/api/hedgeye/fetch-status")
def hedgeye_fetch_status():
    """Last Gmail fetch state + recent email counts by type."""
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT email_type, COUNT(*) n, MAX(received_at) latest"
            " FROM meta_hedgeye_msg WHERE received_at IS NOT NULL"
            " AND (received_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE"
            " GROUP BY email_type ORDER BY latest DESC"
        )).fetchall()
        total = s.execute(text(
            "SELECT COUNT(*) FROM meta_hedgeye_msg"
            " WHERE (received_at AT TIME ZONE 'America/New_York')::date = CURRENT_DATE"
        )).scalar()
    return {
        "running": _gmail_fetch_state["running"],
        "last_run": _gmail_fetch_state["last_run"],
        "last_count": _gmail_fetch_state["last_count"],
        "last_error": _gmail_fetch_state["last_error"],
        "today_total": total or 0,
        "today_by_type": [
            {"type": r[0], "count": r[1],
             "latest": r[2].isoformat() if r[2] else None}
            for r in rows
        ],
    }


@router.post("/api/hedgeye/fetch-now")
def hedgeye_fetch_now():
    """Trigger an on-demand Gmail fetch in the background."""
    if _gmail_fetch_state["running"]:
        return {"started": False, "reason": "already_running"}

    def _run():
        from datetime import date, timedelta
        _gmail_fetch_state["running"] = True
        _gmail_fetch_state["last_error"] = None
        try:
            from dotenv import load_dotenv
            load_dotenv()
            from etl.hedgeye import config as _cfg_mod
            from etl.hedgeye_fetch import _process_pass
            cfg = _cfg_mod.load()
            since = date.today() - timedelta(days=1)
            n = _process_pass(cfg, since, dry_run=False)
            _gmail_fetch_state["last_count"] = n
        except Exception as exc:
            _gmail_fetch_state["last_error"] = str(exc)
        finally:
            from datetime import datetime, timezone
            _gmail_fetch_state["last_run"] = datetime.now(timezone.utc).isoformat()
            _gmail_fetch_state["running"] = False

    t = threading.Thread(target=_run, name="hedgeye-adhoc", daemon=True)
    t.start()
    return {"started": True}


@router.get("/api/notes/{message_id}/llm")
def note_llm(message_id: str):
    with session_scope() as s:
        rows = s.execute(text(
            "SELECT model, prompt_version, json_output, created_at FROM llm_analysis "
            "WHERE message_id = :m ORDER BY created_at DESC"
        ), {"m": message_id}).mappings().fetchall()
    return {"message_id": message_id, "enriched": [dict(r) for r in rows]}
