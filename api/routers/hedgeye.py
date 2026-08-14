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

import re
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

# email_types that drive the panel's effective_date. Kept to the reliably-daily
# morning feeds with a panel card (see actionable_hedgeye below) — every other
# type has no panel card or isn't daily, so it must not move this date.
_PANEL_EMAIL_TYPES = ("risk_range", "early_look", "macro_show_access")

# Strips the leading "Company Name (TICKER): " prefix each the_call_commentary
# note starts with, matching the same convention web/notes.js bolds instead of
# dropping — here we want the bare commentary text only, for a plain tooltip.
_NAME_TICKER_PREFIX_RE = re.compile(r"^[^\n(]*\([A-Z][A-Z0-9.\-]{0,9}\):\s*")


def _strip_name_prefix(text_: str) -> str:
    return _NAME_TICKER_PREFIX_RE.sub("", text_ or "", count=1)


# Pulls the "3.83% y/y" + "-24.0 bp" figures back out of the note_repo text
# parse_inflation_nowcast already writes ("CPI nowcast {value}% y/y, {seq_bp}
# bp (...)"), so the panel doesn't need its own copy of these numbers.
_INFL_NOTE_RE = re.compile(r"CPI nowcast\s+([+-]?[\d.]+)%\s*y/y,\s*([+-]?[\d.]+)\s*bp", re.I)


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

        # Compute effective date: clamp up to the latest calendar date a
        # panel-relevant email was received (_PANEL_EMAIL_TYPES only — a
        # weekly/analysis email with no panel card must not move this), but
        # only when viewing live (see viewing_live above). Weekend dates are
        # excluded too: the anchor is always a market weekday, and a stray
        # weekend send (e.g. a resend) should never park the panel on a
        # Saturday/Sunday it can never advance past. This is a ceiling, not a
        # manufacture — bumping it only lets already-ingested rows whose own
        # date already qualifies show through; it can't pull in data that
        # isn't there yet. So every section below can share one effective_date
        # instead of each computing its own, which used to let some cards
        # advance to today while others stayed on yesterday.
        if viewing_live:
            latest_hedgeye = s.execute(text(
                "SELECT MAX((received_at AT TIME ZONE 'America/New_York')::date)"
                " FROM meta_hedgeye_msg WHERE received_at IS NOT NULL"
                " AND email_type = ANY(:types)"
                " AND EXTRACT(DOW FROM received_at AT TIME ZONE 'America/New_York') NOT IN (0, 6)"
            ), {"types": list(_PANEL_EMAIL_TYPES)}).scalar()
            effective_date = max(d, latest_hedgeye) if latest_hedgeye else d
        else:
            effective_date = d
        out["as_of"] = effective_date.isoformat()

        # Top-5 actionable ideas — only if received exactly on effective_date;
        # no carry-forward, so a day with nothing new shows blank rather than
        # quietly repeating an older snapshot.
        top_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_call_top5"
            " WHERE snapshot_date = :eff"
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

        # Real-Time Alerts — only if received exactly on effective_date, non-superseded.
        rta_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_rta WHERE snapshot_date = :eff"
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

        # Risk Range trend flips — blank unless a risk_range email was actually
        # received on effective_date. Flip data itself is intrinsically dated
        # the prior business day (RR reports on prior close), so unlike the
        # other sections we can't match on date equality directly — instead
        # gate on "did an RR email land today", then look up its flip data.
        rr_recv = s.execute(text(
            "SELECT received_at FROM meta_hedgeye_msg"
            " WHERE email_type = 'risk_range' AND received_at IS NOT NULL"
            " AND (received_at AT TIME ZONE 'America/New_York')::date = :eff"
            " ORDER BY received_at DESC LIMIT 1"
        ), {"eff": effective_date}).scalar()
        if rr_recv is not None:
            flip_date = s.execute(text(
                "SELECT MAX(as_of_date) FROM drv_rr_trend_change WHERE as_of_date <= :eff"
            ), {"eff": effective_date}).scalar()
            if flip_date is not None:
                out["trend_flips_date"] = flip_date.isoformat()
                out["trend_flips_received_at"] = rr_recv.isoformat()
                rows = s.execute(text(
                    "SELECT tos_symbol, from_trend, to_trend "
                    "FROM drv_rr_trend_change WHERE as_of_date = :fd ORDER BY tos_symbol"
                ), {"fd": flip_date}).fetchall()
                out["trend_flips"] = [
                    {"symbol": r[0], "from": r[1], "to": r[2]} for r in rows
                ]

        # Macro Show stance — only if received exactly on effective_date.
        stance_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_hedgeye_stance WHERE snapshot_date = :eff"
        ), {"eff": effective_date}).scalar()
        if stance_date is not None:
            rows = s.execute(text(
                "SELECT stance, COALESCE(tos_symbol, symbol) AS sym, label "
                "FROM hist_hedgeye_stance WHERE snapshot_date = :sd "
                "AND COALESCE(tos_symbol, symbol) IS NOT NULL ORDER BY sym"
            ), {"sd": stance_date}).fetchall()
            for st, sym, label in rows:
                key = "bullish" if (st or "").strip().lower().startswith("bull") else \
                      "bearish" if (st or "").strip().lower().startswith("bear") else None
                if key:
                    out["stance"][key].append({"sym": sym, "label": label})
            out["stance_date"] = stance_date.isoformat()
            out["stance_received_at"] = _recv(s, "hist_hedgeye_stance", "snapshot_date", stance_date)

        # Hedgeye Positions — only if received exactly on effective_date.
        call_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_call WHERE snapshot_date = :eff"
        ), {"eff": effective_date}).scalar()
        if call_date is not None:
            call_rows = s.execute(text(
                "SELECT COALESCE(tos_symbol,symbol) sym, outlook, outlook_modifier"
                " FROM hist_call WHERE snapshot_date = :cd"
                " ORDER BY CASE WHEN outlook_modifier LIKE 'best idea%'"
                " THEN 0 ELSE 1 END, sym"
            ), {"cd": call_date}).fetchall()

            # Per-symbol sector/policy commentary paragraph (same source as the
            # Notes screen's the_call_commentary cards) for the Call section's
            # symbol hover tooltip — bare commentary text, prefix stripped.
            commentary_rows = s.execute(text(
                "SELECT tickers, note_text FROM note_repo"
                " WHERE source_type='the_call_commentary' AND note_date = :cd"
            ), {"cd": call_date}).fetchall()
            commentary_by_sym: dict[str, str] = {}
            for tickers, note_text in commentary_rows:
                for t in (tickers or []):
                    if t not in commentary_by_sym:
                        commentary_by_sym[t] = _strip_name_prefix(note_text)

            # Fallback: symbols with no separate commentary paragraph today
            # (e.g. only covered in the Top-5 write-up) still get their
            # Top-5 rationale text as the tooltip, instead of nothing.
            top5_note_rows = s.execute(text(
                "SELECT tickers, note_text FROM note_repo"
                " WHERE source_type='the_call_top5' AND note_date = :cd"
            ), {"cd": call_date}).fetchall()
            for tickers, note_text in top5_note_rows:
                for t in (tickers or []):
                    if t not in commentary_by_sym:
                        commentary_by_sym[t] = _strip_name_prefix(note_text)

            out["positions"] = {
                "date": call_date.isoformat(),
                "received_at": _recv_by_type(s, "the_call", call_date),
                "longs": [
                    {"sym": r[0], "best": "best idea" in (r[2] or ""), "modifier": r[2],
                     "commentary": commentary_by_sym.get(r[0])}
                    for r in call_rows if r[1] == "BULLISH"
                ],
                "shorts": [
                    {"sym": r[0], "best": "best idea" in (r[2] or ""), "modifier": r[2],
                     "commentary": commentary_by_sym.get(r[0])}
                    for r in call_rows if r[1] == "BEARISH"
                ],
                "neutral": [
                    {"sym": r[0], "commentary": commentary_by_sym.get(r[0])}
                    for r in call_rows if r[1] == "NEUTRAL"
                ],
            }

        # ETF Pro changes — only if received exactly on effective_date.
        etf_date = s.execute(text(
            "SELECT MAX(event_date) FROM hist_etfchg WHERE event_date = :eff"
        ), {"eff": effective_date}).scalar()
        if etf_date is not None:
            etf_rows = s.execute(text(
                "SELECT COALESCE(tos_symbol,symbol) sym, outlook, change_str, description"
                " FROM hist_etfchg WHERE event_date = :ed"
                " ORDER BY change_str, sym"
            ), {"ed": etf_date}).fetchall()
            out["etf_changes"] = {
                "date": etf_date.isoformat(),
                "received_at": _recv_by_type(s, "etf_changes", etf_date),
                "changes": [
                    {"sym": r[0], "side": r[1], "action": r[2], "desc": r[3]}
                    for r in etf_rows
                ],
            }

        # Investing Ideas changes — only if received exactly on effective_date.
        ii_date = s.execute(text(
            "SELECT MAX(event_date) FROM hist_iichg WHERE event_date = :eff"
        ), {"eff": effective_date}).scalar()
        if ii_date is not None:
            ii_rows = s.execute(text(
                "SELECT COALESCE(tos_symbol,symbol) sym, outlook, change_str"
                " FROM hist_iichg WHERE event_date = :ed"
                " ORDER BY change_str, sym"
            ), {"ed": ii_date}).fetchall()
            out["ii_changes"] = {
                "date": ii_date.isoformat(),
                "received_at": _recv_by_type(s, "investing_ideas", ii_date),
                "changes": [
                    {"sym": r[0], "side": r[1], "action": r[2]}
                    for r in ii_rows
                ],
            }

        # Signal Strength (SSS) changes — only if received exactly on effective_date.
        sss_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_sss_change WHERE snapshot_date = :eff"
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

        # Early Look — note-only; only if received exactly on effective_date.
        el_row = s.execute(text(
            "SELECT note_date, subject, note_text, message_id FROM note_repo"
            " WHERE source_type='early_look' AND note_date = :b"
            " ORDER BY note_id DESC LIMIT 1"
        ), {"b": effective_date}).first()
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

        # The Call — Macro Commentary — note-only; only if received exactly on effective_date.
        cm_row = s.execute(text(
            "SELECT note_date, subject, note_text, message_id FROM note_repo"
            " WHERE source_type='the_call_macro' AND note_date = :b"
            " ORDER BY note_id DESC LIMIT 1"
        ), {"b": effective_date}).first()
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

        # Macro Show — Hedgeye's Top 3 Things — note-only; only if received
        # exactly on effective_date.
        t3_row = s.execute(text(
            "SELECT note_date, subject, note_text, message_id FROM note_repo"
            " WHERE source_type='macro_show_top3' AND note_date = :b"
            " ORDER BY note_id DESC LIMIT 1"
        ), {"b": effective_date}).first()
        if t3_row:
            recv = s.execute(text(
                "SELECT received_at FROM meta_hedgeye_msg WHERE message_id=:m"
                " AND received_at IS NOT NULL LIMIT 1"
            ), {"m": t3_row[3]}).scalar()
            out["top3_things"] = {
                "date": t3_row[0].isoformat(),
                "received_at": recv.isoformat() if recv else None,
                "subject": t3_row[1],
                "note_text": t3_row[2],
            }

        # Market Situation Report — only if received exactly on effective_date.
        msr_date = s.execute(text(
            "SELECT MAX(snapshot_date) FROM hist_msr WHERE snapshot_date = :eff"
        ), {"eff": effective_date}).scalar()
        if msr_date is not None:
            msr_row = s.execute(text(
                "SELECT gamma_throttle, rvol_10day FROM hist_msr"
                " WHERE snapshot_date = :md"
            ), {"md": msr_date}).first()
            if msr_row:
                # VIX alongside gamma_throttle/rvol_10day so the panel can show
                # a VRP-style (VIX vs realized) tooltip on Realized Vol -- same
                # source (drv_quote) other quote reads in this router use.
                # TASK: hover tooltip on Gamma Throttle/Realized Vol (2026-08-14).
                vix_val = s.execute(text(
                    "SELECT last_price FROM drv_quote WHERE as_of_date = :d AND tos_symbol = 'VIX'"
                ), {"d": d}).scalar()
                out["msr"] = {
                    "date": msr_date.isoformat(),
                    "received_at": _recv(s, "hist_msr", "snapshot_date", msr_date),
                    "gamma_throttle": (
                        float(msr_row[0]) if msr_row[0] is not None else None
                    ),
                    "rvol_10day": (
                        float(msr_row[1]) if msr_row[1] is not None else None
                    ),
                    "vix": float(vix_val) if vix_val is not None else None,
                    "image_url": f"/api/msr/image?date={msr_date.isoformat()}",
                }

        # Hedgeye Monthly Inflation Nowcast image — monthly cadence, so show the
        # latest one received on or before effective_date (not an exact-date
        # match, which would blank the card on every non-arrival day).
        infl_row = s.execute(text(
            "SELECT (received_at AT TIME ZONE 'America/New_York')::date AS d, received_at"
            " FROM meta_hedgeye_msg WHERE email_type='inflation_nowcast'"
            " AND received_at IS NOT NULL"
            " AND (received_at AT TIME ZONE 'America/New_York')::date <= :eff"
            " ORDER BY received_at DESC LIMIT 1"
        ), {"eff": effective_date}).first()
        if infl_row is not None:
            infl_note = s.execute(text(
                "SELECT note_text FROM note_repo"
                " WHERE source_type='inflation' AND note_date = :d"
                " AND note_text NOT LIKE '%None%'"
                " ORDER BY note_id DESC LIMIT 1"
            ), {"d": infl_row[0]}).scalar()
            m_infl = _INFL_NOTE_RE.search(infl_note or "")
            out["inflation_nowcast"] = {
                "date": infl_row[0].isoformat(),
                "received_at": infl_row[1].isoformat(),
                "image_url": f"/api/inflation-nowcast/image?date={infl_row[0].isoformat()}",
                "value": float(m_infl.group(1)) if m_infl else None,
                "seq_bp": float(m_infl.group(2)) if m_infl else None,
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


@router.get("/api/inflation-nowcast/image")
def inflation_nowcast_image(date: Optional[str] = Query(None)):
    from etl.hedgeye import config as hcfg
    hefiles_dir = hcfg.get("hefiles_dir") or hcfg.DEFAULTS.get("hefiles_dir", "")
    d = _resolve_date(date)
    img_path = Path(hefiles_dir) / f"INFL_{d.isoformat()}.png"
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Inflation Nowcast image not found")
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
        "SELECT note_date, source_type, subject, note_text, signal_kind, gmail_link FROM note_repo "
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
