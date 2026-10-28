"""Portfolio Builder storage: accept / freeze, daily paper marks, list, detail, review, warnings.

Frozen portfolios hold SHARES bought on day 1 (set and forget); positions are write-once. The
Builder never trades and never changes the Actionable Final Call. Spec: DESIGN_SPEC_9 R7-R9,
DESIGN_SPEC_10 (one running model per account), docs/portfolio_builder_logic.md.
"""
from __future__ import annotations

import calendar
import json
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text

from etl import builder_data as bd
from etl.builder_engine import build_positions, vs_account, drift_table
from etl.derive_model_portfolio import (
    PB_PARAMS, BUCKETS, final_call_side, series_stats, evaluate_alerts, fire_once, promise_check,
)

log = logging.getLogger(__name__)


class BuilderError(Exception):
    """A user-facing refusal (shown as a plain message)."""


def add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, mo = d.year + m // 12, m % 12 + 1
    return date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def _dumps(o) -> str:
    return json.dumps(o, default=str)


def _fl(v):
    return None if v is None else float(v)


# ---------------------------------------------------------------------------
# Accept / freeze
# ---------------------------------------------------------------------------
def _area_chips(res: dict) -> dict:
    chips = {}
    for info in res.get("buckets", {}).values():
        for a in info.get("areas", []):
            chips[a["name"]] = a["chip"]
    return chips


def accept(session, d: date, req: dict, name: Optional[str], data_stale: bool, rolled_from: Optional[int] = None,
           close_reason: str = "replaced") -> dict:
    account = req.get("account")
    if not account or account == "ALL":
        raise BuilderError("Whole book is preview only: pick one account to freeze a model.")
    if data_stale:
        raise BuilderError("The data is behind market close: wait for the evening load, then accept.")
    horizon = req.get("horizon") or "3M"
    if horizon not in PB_PARAMS["horizon_months"]:
        raise BuilderError("Pick 1M, 3M, 6M or 12M.")
    ctx = bd.load_context(session, d, account, horizon, sources=(None if req.get("manual") else req.get("sources")), **bd.manual_kwargs(req))
    res = build_positions(ctx, req)
    if res["amount"] <= 0:
        raise BuilderError("The amount is 0.")
    new_pos = [x for x in res["positions"] if not x["is_kept"]]
    if len(new_pos) < 3:
        raise BuilderError("Fewer than 3 funds qualify (%d): not enough to freeze." % len(new_pos))
    spy = (ctx["funds"].get("SPY") or {}).get("price")
    if not spy:
        raise BuilderError("No SPY price today: cannot track against SPY.")
    start, end = d, add_months(d, PB_PARAMS["horizon_months"][horizon])
    acct = ctx["account"]
    cash_at_build = res["amount"] - sum(x["value"] for x in res["positions"])
    quad = ctx.get("quad") or {}
    quad_sum = {"shares": quad.get("shares"), "coverage_pct": quad.get("coverage_pct"), "note": quad.get("note"),
                "blend": quad.get("blend"), "check_label": quad.get("check_label")}
    settings = {
        "req": {k: v for k, v in req.items()}, "preset": req.get("preset"), "flavour": req.get("flavour") or "all",
        "buckets": {b: {"split": i.get("split"), "dollars": i["dollars"], "pct": i["pct"], "areas": i.get("areas", [])}
                    for b, i in res["buckets"].items()},
        "quad": quad_sum, "risk": res.get("risk"), "skipped": res["skipped"], "notes": res["notes"],
        "mix_final": res["mix_final"], "chips": _area_chips(res),
        "account_start": {"cash": acct["cash"], "holdings": {s: {"qty": h["qty"], "price": h.get("price")}
                                                              for s, h in acct["holdings"].items()}},
        "account_value_at_build": acct["value"],
    }
    default_name = "%s %s %s %s" % (account, (ctx["presets"].get(req.get("preset") or "", {}) or {}).get("label", req.get("preset") or "Mix").split(" ")[0],
                                    horizon, d.strftime("%b-%y"))
    prior = session.execute(text(
        "SELECT portfolio_id FROM user_model_portfolio WHERE account_short = :a AND status IN ('PENDING', 'RUNNING')"),
        {"a": account}).fetchall()
    session.execute(text(
        "UPDATE user_model_portfolio SET status = 'CLOSED', close_reason = :r, closed_at = now() "
        "WHERE account_short = :a AND status IN ('PENDING', 'RUNNING')"), {"a": account, "r": close_reason})
    pid = session.execute(text(
        "INSERT INTO user_model_portfolio (name, account_short, account_type, start_date, end_date, horizon, amount, "
        "cash_at_build, size_multiplier, mix_target, mix_at_build, bucket_recipes, kept, settings, warnings, spy_entry, "
        "status, rolled_from_id) VALUES (:n, :a, :t, :s, :e, :h, :amt, :cash, :mult, CAST(:mt AS JSONB), CAST(:mb AS JSONB), "
        "CAST(:br AS JSONB), CAST(:k AS JSONB), CAST(:st AS JSONB), CAST(:w AS JSONB), :spy, 'RUNNING', :rf) "
        "RETURNING portfolio_id"),
        {"n": name or default_name, "a": account, "t": acct.get("type"), "s": start, "e": end, "h": horizon, "amt": res["amount"],
         "cash": cash_at_build, "mult": ctx.get("risk_mult") if (res.get("risk") or {}).get("applied") else None,
         "mt": _dumps(res["mix_final"]), "mb": _dumps(acct["current_mix"]), "br": _dumps(req.get("buckets") or {}),
         "k": _dumps(ctx.get("kept") or []), "st": _dumps(settings),
         "w": _dumps({"opt_in": req.get("warnings") or {}, "fired": [], "dismissed": []}),
         "spy": spy, "rf": rolled_from or (prior[0][0] if prior else None)}).scalar()
    rows = [{"p": pid, "s": x["sym"], "b": x["bucket"], "a": x["area"], "k": x["is_kept"],
             "sl": _dumps({"bucket": x["bucket"], "rule": x.get("rule")}), "w": x["weight"], "td": x["dollars"],
             "e": x["price"], "sh": x["shares"], "why": x["why"], "wd": _dumps(x["why_detail"]), "fc": x.get("final_code")}
            for x in res["positions"]]
    session.execute(text(
        "INSERT INTO user_model_position (portfolio_id, tos_symbol, bucket, area, is_kept, sleeves, target_weight, "
        "target_dollars, entry_price, shares, why, why_detail, final_call_at_build) VALUES (:p, :s, :b, :a, :k, "
        "CAST(:sl AS JSONB), :w, :td, :e, :sh, :why, CAST(:wd AS JSONB), :fc)"), rows)
    session.commit()
    return {"portfolio_id": pid, "start_date": start.isoformat(), "end_date": end.isoformat(),
            "replaced": [r[0] for r in prior], "positions": len(rows)}


# ---------------------------------------------------------------------------
# Daily marks
# ---------------------------------------------------------------------------
def _quotes(session, syms: list, d: date) -> dict:
    return {r[0]: float(r[1]) for r in session.execute(text(
        "SELECT tos_symbol, last_price FROM drv_quote WHERE as_of_date = :d AND tos_symbol = ANY(:s) AND last_price IS NOT NULL"),
        {"d": d, "s": syms}).fetchall()}


def mark_all(session, d: date) -> int:
    """Idempotent per as_of_date: DELETE the date's marks for the portfolios we process, then INSERT."""
    from etl.warnings import add_warning, clear_screen_warnings
    try:
        pfs = session.execute(text(
            "SELECT portfolio_id, name, account_short, start_date, end_date, amount, cash_at_build, spy_entry, entry_final, "
            "status, warnings, settings FROM user_model_portfolio WHERE status IN ('PENDING', 'RUNNING', 'REVIEW_DUE') "
            "AND start_date <= :d"), {"d": d}).fetchall()
    except Exception as e:
        session.rollback()
        log.info("derive_model_marks: model tables not there yet (%s)", type(e).__name__)
        return 0
    if not pfs:
        return 0
    chk = session.execute(text("SELECT label_shown FROM drv_quad_check WHERE as_of_date <= :d ORDER BY as_of_date DESC LIMIT 1"),
                          {"d": d}).fetchone()
    rk = session.execute(text("SELECT risk_label FROM drv_market_stat WHERE as_of_date = :d"), {"d": d}).fetchone()
    quad_label, risk_label = (chk[0] if chk else None), (rk[0] if rk else None)
    clear_screen_warnings(session, "builder", d)
    n_done = 0
    for pid, name, acct, start, end, amount, cash0, spy_entry, entry_final, status, warns, settings in pfs:
        try:
            n_done += _mark_one(session, d, pid, name, acct, start, end, float(amount), float(cash0 or 0), _fl(spy_entry),
                                bool(entry_final), status, warns if isinstance(warns, dict) else json.loads(warns or "{}"),
                                settings if isinstance(settings, dict) else json.loads(settings or "{}"),
                                quad_label, risk_label, add_warning)
            session.commit()
        except Exception:
            log.exception("derive_model_marks: portfolio %s failed (continuing)", pid)
            session.rollback()
    return n_done


def _mark_one(session, d, pid, name, acct, start, end, amount, cash0, spy_entry, entry_final, status, warns, settings,
              quad_label, risk_label, add_warning) -> int:
    pos = session.execute(text(
        "SELECT tos_symbol, bucket, area, is_kept, entry_price, shares, target_dollars FROM user_model_position "
        "WHERE portfolio_id = :p"), {"p": pid}).fetchall()
    syms = [r[0] for r in pos] + ["SPY"] + list(((settings.get("account_start") or {}).get("holdings") or {}).keys())
    q = _quotes(session, syms, d)
    # entry price refresh: on the start date the last (evening) derive's close wins; frozen the day after
    if d == start and not entry_final:
        new_pos = []
        for sym, b, area, kept, entry, shares, tdol in pos:
            px = q.get(sym)
            if kept or not px or not tdol:
                new_pos.append((sym, b, area, kept, entry, shares, tdol))
                continue
            sh = int(float(tdol) // px)
            session.execute(text("UPDATE user_model_position SET entry_price = :e, shares = :s WHERE portfolio_id = :p AND tos_symbol = :y"),
                            {"e": px, "s": sh, "p": pid, "y": sym})
            new_pos.append((sym, b, area, kept, px, sh, tdol))
        pos = new_pos
        if q.get("SPY"):
            spy_entry = q["SPY"]
        cash0 = amount - sum(float(r[4] or 0) * float(r[5] or 0) for r in pos)
        session.execute(text("UPDATE user_model_portfolio SET spy_entry = :s, cash_at_build = :c WHERE portfolio_id = :p"),
                        {"s": spy_entry, "c": cash0, "p": pid})
    elif d > start and not entry_final:
        session.execute(text("UPDATE user_model_portfolio SET entry_final = TRUE WHERE portfolio_id = :p"), {"p": pid})
    if d > end:  # past the end date: no more marks, only the status change
        if status == "RUNNING":
            session.execute(text("UPDATE user_model_portfolio SET status = 'REVIEW_DUE' WHERE portfolio_id = :p"), {"p": pid})
        return 0
    last = {r[0]: (r[1], r[2]) for r in session.execute(text(
        "SELECT DISTINCT ON (tos_symbol) tos_symbol, close, stale_days FROM drv_model_position_mark "
        "WHERE portfolio_id = :p AND as_of_date < :d ORDER BY tos_symbol, as_of_date DESC"), {"p": pid, "d": d}).fetchall()}
    fcalls = {r[0]: r[1] for r in session.execute(text(
        "SELECT tos_symbol, final_code FROM drv_actionable WHERE as_of_date = :d AND tos_symbol = ANY(:s)"),
        {"d": d, "s": [r[0] for r in pos]}).fetchall()}
    pmarks, total, stale_max, alert_pos = [], 0.0, 0, []
    for sym, b, area, kept, entry, shares, _t in pos:
        entry, shares = float(entry or 0), float(shares or 0)
        close = q.get(sym)
        prev_close, prev_stale = last.get(sym, (entry, 0))
        prev_close = float(prev_close or entry)
        if close is None:
            close, stale = prev_close, int(prev_stale or 0) + 1
        else:
            stale = 0
        val = shares * close
        total += val
        stale_max = max(stale_max, stale)
        move = (close / prev_close - 1.0) if (prev_close and stale == 0) else None
        alert_pos.append({"sym": sym, "stale_days": stale, "move": move, "is_kept": kept,
                          "final_side": final_call_side(fcalls.get(sym))})
        pmarks.append({"d": d, "p": pid, "s": sym, "c": close, "st": stale, "v": val,
                       "r": (close / entry - 1.0) if entry else None, "fc": fcalls.get(sym), "b": b, "area": area})
    value = total + cash0
    for m in pmarks:
        m["w"] = m["v"] / value if value else None
    spy_close = q.get("SPY")
    if spy_close is None:
        prev = session.execute(text("SELECT spy_value FROM drv_model_mark WHERE portfolio_id = :p AND as_of_date < :d "
                                    "ORDER BY as_of_date DESC LIMIT 1"), {"p": pid, "d": d}).fetchone()
        spy_value = float(prev[0]) if prev and prev[0] is not None else amount
    else:
        spy_value = amount * spy_close / spy_entry if spy_entry else None
    ast = settings.get("account_start") or {}
    acct_ret = None
    if ast.get("holdings") is not None:
        v0 = float(ast.get("cash") or 0) + sum(float(h["qty"]) * float(h["price"] or 0) for h in ast["holdings"].values())
        v1 = float(ast.get("cash") or 0) + sum(float(h["qty"]) * float(q.get(s) or h["price"] or 0) for s, h in ast["holdings"].items())
        acct_ret = (v1 / v0 - 1.0) if v0 else None
    model_mix: dict = {}
    for m in pmarks:
        model_mix[m["b"] or "Unmapped"] = model_mix.get(m["b"] or "Unmapped", 0.0) + (m["w"] or 0.0) * 100.0
    model_mix["Cash"] = (cash0 / value * 100.0) if value else 0.0
    acct_mix = None
    try:
        g = bd.account_groups(session).get(acct)
        if g:
            ap = bd.account_positions(session, g, d)
            if ap:
                funds = {r[0]: {"bucket": r[1], "area": r[2]} for r in session.execute(text(
                    "SELECT tos_symbol, bucket, area FROM ref_pb_universe")).fetchall()}
                bd.classify_holdings(session, d, ap, funds)
                acct_mix = bd.current_mix(ap)
    except Exception:
        log.warning("derive_model_marks: account mix unavailable for %s", acct)
    state = {"value": value, "amount": amount, "quad_label": quad_label, "risk_label": risk_label, "positions": alert_pos}
    alerts = evaluate_alerts((warns or {}).get("opt_in"), state)
    warns = fire_once(warns, alerts, d)
    session.execute(text("DELETE FROM drv_model_mark WHERE as_of_date = :d AND portfolio_id = :p"), {"d": d, "p": pid})
    session.execute(text("DELETE FROM drv_model_position_mark WHERE as_of_date = :d AND portfolio_id = :p"), {"d": d, "p": pid})
    session.execute(text(
        "INSERT INTO drv_model_mark (as_of_date, portfolio_id, value, cash, spy_value, account_ret, account_mix, model_mix, "
        "stale_count, alerts) VALUES (:d, :p, :v, :c, :sv, :ar, CAST(:am AS JSONB), CAST(:mm AS JSONB), :sc, CAST(:al AS JSONB))"),
        {"d": d, "p": pid, "v": value, "c": cash0, "sv": spy_value, "ar": acct_ret, "am": _dumps(acct_mix),
         "mm": _dumps(model_mix), "sc": stale_max, "al": _dumps(alerts)})
    if pmarks:
        session.execute(text(
            "INSERT INTO drv_model_position_mark (as_of_date, portfolio_id, tos_symbol, close, stale_days, value, ret, "
            "weight_now, final_call_now) VALUES (:d, :p, :s, :c, :st, :v, :r, :w, :fc)"),
            [{k: m[k] for k in ("d", "p", "s", "c", "st", "v", "r", "w", "fc")} for m in pmarks])
    new_status = status
    if status in ("PENDING", "RUNNING") and d >= end:
        new_status = "REVIEW_DUE"
    session.execute(text("UPDATE user_model_portfolio SET warnings = CAST(:w AS JSONB), status = :s WHERE portfolio_id = :p"),
                    {"w": _dumps(warns), "s": new_status, "p": pid})
    for f in warns.get("fired", []):
        if f["code"] not in (warns.get("dismissed") or []):
            add_warning(session, "builder", "%s: %s" % (name, f["message"]), as_of_date=d, code="builder_" + f["code"].split(":")[0],
                        severity="warning")
    return 1


# ---------------------------------------------------------------------------
# Lists and detail
# ---------------------------------------------------------------------------
def _mix_label(mix: dict) -> str:
    eq, fi = round(mix.get("Equities", 0)), round(mix.get("Fixed Income", 0))
    other = round(100 - eq - fi)
    return "%d/%d/%d" % (eq, fi, other)


def list_portfolios(session, account: Optional[str] = None, status: Optional[str] = None) -> dict:
    rows = session.execute(text(
        "SELECT p.portfolio_id, p.name, p.account_short, p.start_date, p.end_date, p.horizon, p.amount, p.mix_target, "
        "p.settings, p.status, p.warnings, p.close_reason, m.as_of_date, m.value, m.spy_value, m.account_ret, m.alerts, "
        "(SELECT COUNT(*) FROM drv_model_mark x WHERE x.portfolio_id = p.portfolio_id) AS ndays "
        "FROM user_model_portfolio p LEFT JOIN LATERAL (SELECT * FROM drv_model_mark x WHERE x.portfolio_id = p.portfolio_id "
        "ORDER BY as_of_date DESC LIMIT 1) m ON TRUE ORDER BY p.account_short, p.portfolio_id DESC")).fetchall()
    out, tot_by_acct = [], {}
    for r in rows:
        (pid, name, acc, s, e, hz, amt, mt, st, stt, w, cr, md, val, spyv, aret, alerts, nd) = r
        mt = mt if isinstance(mt, dict) else json.loads(mt or "{}")
        st = st if isinstance(st, dict) else json.loads(st or "{}")
        w = w if isinstance(w, dict) else json.loads(w or "{}")
        amt = float(amt)
        ret = (float(val) / amt - 1.0) if val is not None else None
        spy_ret = (float(spyv) / amt - 1.0) if spyv is not None else None
        eq = (st.get("buckets") or {}).get("Equities") or {}
        split = ("Area" if eq.get("split") == "area" else "Recipe") if eq else "-"
        fired = [f for f in w.get("fired", []) if f["code"] not in (w.get("dismissed") or [])]
        item = {"portfolio_id": pid, "name": name, "account": acc, "mix": _mix_label(mt), "split": split,
                "start": s.isoformat(), "end": e.isoformat(), "horizon": hz, "days": int(nd or 0),
                "total_days": PB_PARAMS["horizon_trading_days"].get(hz), "value": _fl(val), "ret": ret,
                "vs_spy": None if (ret is None or spy_ret is None) else ret - spy_ret,
                "vs_account": None if (ret is None or aret is None) else ret - float(aret),
                "status": stt, "close_reason": cr, "alerts": [f["message"] for f in fired], "amount": amt,
                "gain": None if val is None else float(val) - amt}
        out.append(item)
    if account:
        out = [x for x in out if x["account"] == account]
    if status == "active":
        out = [x for x in out if x["status"] in ("PENDING", "RUNNING", "REVIEW_DUE")]
    elif status == "closed":
        out = [x for x in out if x["status"] == "CLOSED"]
    totals: dict = {}
    for x in out:
        t = totals.setdefault(x["account"], {"account": x["account"], "running_value": 0.0, "running_amount": 0.0,
                                             "running_ret": None, "all_gain": 0.0})
        t["all_gain"] += x["gain"] or 0.0
        if x["status"] in ("PENDING", "RUNNING", "REVIEW_DUE") and x["value"] is not None:
            t["running_value"] += x["value"]
            t["running_amount"] += x["amount"]
    for t in totals.values():
        t["running_ret"] = (t["running_value"] / t["running_amount"] - 1.0) if t["running_amount"] else None
    grand_v = sum(t["running_value"] for t in totals.values())
    grand_a = sum(t["running_amount"] for t in totals.values())
    return {"portfolios": out, "totals": list(totals.values()),
            "grand": {"value": grand_v, "ret": (grand_v / grand_a - 1.0) if grand_a else None},
            "shared_funds": _shared_funds(session)}


def _shared_funds(session) -> dict:
    rows = session.execute(text(
        "SELECT pm.tos_symbol, COUNT(DISTINCT pm.portfolio_id), SUM(pm.value) FROM drv_model_position_mark pm "
        "JOIN user_model_portfolio p ON p.portfolio_id = pm.portfolio_id AND p.status IN ('PENDING', 'RUNNING', 'REVIEW_DUE') "
        "WHERE pm.as_of_date = (SELECT MAX(as_of_date) FROM drv_model_position_mark x WHERE x.portfolio_id = pm.portfolio_id) "
        "GROUP BY pm.tos_symbol")).fetchall()
    total = sum(float(r[2] or 0) for r in rows)
    shared = [{"sym": r[0], "models": r[1], "value": float(r[2] or 0), "share": (float(r[2] or 0) / total) if total else None}
              for r in rows if r[1] >= 2]
    return {"funds": sorted(shared, key=lambda x: -x["value"]),
            "over_note": [x["sym"] for x in shared if x["share"] and x["share"] > PB_PARAMS["household_fund_note"]]}


def detail(session, d: date, pid: int) -> Optional[dict]:
    r = session.execute(text(
        "SELECT portfolio_id, name, account_short, account_type, start_date, end_date, horizon, amount, cash_at_build, "
        "size_multiplier, mix_target, mix_at_build, bucket_recipes, kept, settings, warnings, status, close_reason, "
        "rolled_from_id, entry_final FROM user_model_portfolio WHERE portfolio_id = :p"), {"p": pid}).fetchone()
    if not r:
        return None
    (pid, name, acct, atype, s, e, hz, amt, cash0, mult, mt, mb, br, kept, st, w, status, cr, rf, ef) = r
    J = lambda v: v if isinstance(v, (dict, list)) else json.loads(v or "null")
    mt, mb, kept, st, w = J(mt) or {}, J(mb) or {}, J(kept) or [], J(st) or {}, J(w) or {}
    amt = float(amt)
    marks = session.execute(text("SELECT as_of_date, value, spy_value, account_ret, model_mix, account_mix, stale_count, alerts "
                                 "FROM drv_model_mark WHERE portfolio_id = :p ORDER BY as_of_date"), {"p": pid}).fetchall()
    dates = [m[0].isoformat() for m in marks]
    values = [float(m[1]) for m in marks]
    spyv = [float(m[2]) if m[2] is not None else None for m in marks]
    stats = series_stats(values, [x for x in spyv if x is not None], amt)
    last = marks[-1] if marks else None
    pos = session.execute(text(
        "SELECT p.tos_symbol, p.bucket, p.area, p.is_kept, p.entry_price, p.shares, p.why, p.why_detail, p.final_call_at_build, "
        "p.target_weight, m.close, m.ret, m.weight_now, m.final_call_now, m.value, m.stale_days "
        "FROM user_model_position p LEFT JOIN LATERAL (SELECT * FROM drv_model_position_mark x WHERE x.portfolio_id = p.portfolio_id "
        "AND x.tos_symbol = p.tos_symbol ORDER BY as_of_date DESC LIMIT 1) m ON TRUE WHERE p.portfolio_id = :p "
        "ORDER BY p.bucket, p.tos_symbol"), {"p": pid}).fetchall()
    positions = [{"sym": x[0], "bucket": x[1], "area": x[2], "is_kept": x[3], "entry": _fl(x[4]), "shares": _fl(x[5]), "why": x[6],
                  "why_detail": J(x[7]) or [], "final_at_build": x[8], "target_weight": _fl(x[9]), "close": _fl(x[10]),
                  "ret": _fl(x[11]), "weight_now": _fl(x[12]), "final_now": x[13], "value": _fl(x[14]), "stale_days": x[15]}
                 for x in pos]
    chips = st.get("chips") or {}
    rules = []
    req = st.get("req") or {}
    for b, cfg in (req.get("buckets") or {}).items():
        bi = (st.get("buckets") or {}).get(b) or {}
        if bi.get("split") == "area":
            rules.append(cfg.get("pick") or ("low_vol" if b == "Equities" else "core"))
        elif b == "Equities":
            rules.append(cfg.get("recipe") or "momentum")
        elif bi.get("split") in ("core", "low_vol"):
            rules.append(bi["split"])
    area_mode = any((b or {}).get("split") == "area" for b in (st.get("buckets") or {}).values())
    qlabels = [row[0] for row in session.execute(text(
        "SELECT label_shown FROM drv_quad_check WHERE as_of_date >= :s AND as_of_date <= :e"), {"s": s, "e": e}).fetchall()]
    prom = promise_check(rules, area_mode, stats, {p["sym"]: p["ret"] for p in positions if not p["is_kept"]},
                         {p["sym"]: chips.get(p["area"]) for p in positions}, qlabels)
    # account side: today's holdings, drift, gaps and trades
    account_info, gaps, drift, area_drift = None, None, None, None
    try:
        groups = bd.account_groups(session)
        g = groups.get(acct)
        if g:
            ap = bd.account_positions(session, g, d)
            funds = {x[0]: {"bucket": x[1], "area": x[2]} for x in session.execute(text(
                "SELECT tos_symbol, bucket, area FROM ref_pb_universe")).fetchall()}
            if ap:
                bd.classify_holdings(session, d, ap, funds)
                amix = bd.current_mix(ap)
                mm = J(last[4]) if last else {}
                drift = drift_table(mt, mm or {}, amix)
                tot = ap["value"] or 0.0
                acc_area: dict = {}
                for sym, h in ap["holdings"].items():
                    if h["bucket"] == "Equities" and tot:
                        acc_area[h["area"]] = acc_area.get(h["area"], 0.0) + h["value"] / tot * 100.0
                mod_area: dict = {}
                for p_ in positions:
                    if p_["bucket"] == "Equities" and last and values and values[-1]:
                        mod_area[p_["area"]] = mod_area.get(p_["area"], 0.0) + (p_["value"] or 0.0) / values[-1] * 100.0
                area_rows = []
                eq_info = (st.get("buckets") or {}).get("Equities") or {}
                eq_pct = eq_info.get("pct", 0.0)
                for a in eq_info.get("areas", []):
                    tgt = a["fill"] * eq_pct
                    area_rows.append({"area": a["name"], "chip_at_build": a["chip"], "target": tgt,
                                      "model": mod_area.get(a["name"], 0.0), "account": acc_area.get(a["name"], 0.0),
                                      "gap": acc_area.get(a["name"], 0.0) - tgt,
                                      "amber": abs(acc_area.get(a["name"], 0.0) - tgt) >= PB_PARAMS["drift_amber_pts"]})
                area_drift = area_rows
                model_rows = [{"sym": p_["sym"], "value": p_["value"] or 0.0, "price": p_["close"], "area": p_["area"], "bucket": p_["bucket"]}
                              for p_ in positions]
                gaps = vs_account(model_rows, ap["holdings"], set(kept), atype)
                account_info = {"snap_date": ap["snap_date"].isoformat(), "value": ap["value"], "stale": ap["stale"], "active": True}
        else:
            account_info = {"active": False}
    except Exception:
        log.exception("builder detail: account side failed")
    fired = [f for f in w.get("fired", []) if f["code"] not in (w.get("dismissed") or [])]
    return {
        "portfolio_id": pid, "name": name, "account": acct, "account_type": atype, "start": s.isoformat(), "end": e.isoformat(),
        "horizon": hz, "amount": amt, "cash_at_build": _fl(cash0), "size_multiplier": _fl(mult), "mix_target": mt,
        "mix_at_build": mb, "kept": kept, "settings": {k: st.get(k) for k in ("preset", "flavour", "quad", "risk", "skipped", "notes", "buckets", "req")},
        "status": status, "close_reason": cr, "rolled_from_id": rf, "entry_final": ef,
        "day": len(marks), "total_days": PB_PARAMS["horizon_trading_days"].get(hz),
        "series": {"dates": dates, "model": values, "spy": spyv,
                   "account": [None if m[3] is None else amt * (1 + float(m[3])) for m in marks]},
        "kpis": {"ret": stats["ret"], "vs_spy": None if (stats["ret"] is None or stats["spy_ret"] is None) else stats["ret"] - stats["spy_ret"],
                 "vs_account": None if (not last or last[3] is None or stats["ret"] is None) else stats["ret"] - float(last[3]),
                 "worst_drop": stats["worst_drop"], "swings": stats["swings"], "spy_swings": stats["spy_swings"], "alerts": len(fired)},
        "alerts": fired, "opt_in": w.get("opt_in") or {}, "positions": positions, "promise": prom, "drift": drift,
        "area_drift": area_drift, "vs_account": gaps, "account_info": account_info,
        "review_available": status in ("RUNNING", "REVIEW_DUE") and d >= e,
        "note": "Price return only: dividends are not included. Cash earns 0%.",
    }


# ---------------------------------------------------------------------------
# Review (end of period), warnings, keep list
# ---------------------------------------------------------------------------
def _stored_req(session, pid: int):
    r = session.execute(text("SELECT account_short, end_date, status, settings, amount FROM user_model_portfolio WHERE portfolio_id = :p"),
                        {"p": pid}).fetchone()
    if not r:
        raise BuilderError("Model portfolio not found.")
    st = r[3] if isinstance(r[3], dict) else json.loads(r[3] or "{}")
    return r, dict(st.get("req") or {})


def review_preview(session, d: date, pid: int) -> dict:
    r, req = _stored_req(session, pid)
    if d < r[1]:
        raise BuilderError("The review opens on the end date (%s)." % r[1].isoformat())
    last = session.execute(text("SELECT value FROM drv_model_mark WHERE portfolio_id = :p ORDER BY as_of_date DESC LIMIT 1"), {"p": pid}).fetchone()
    req["amount"] = float(last[0]) if last else float(r[4])
    req["account"] = r[0]
    ctx = bd.load_context(session, d, r[0], req.get("horizon") or "3M", sources=(None if req.get("manual") else req.get("sources")), **bd.manual_kwargs(req))
    res = build_positions(ctx, req)
    old = {x[0]: float(x[1] or 0) for x in session.execute(text(
        "SELECT tos_symbol, shares FROM user_model_position WHERE portfolio_id = :p"), {"p": pid}).fetchall()}
    new = {x["sym"]: x["shares"] for x in res["positions"]}
    change = {"keep": [{"sym": s, "old_shares": old[s], "new_shares": new[s]} for s in new if s in old],
              "add": [{"sym": s, "new_shares": new[s]} for s in new if s not in old],
              "drop": [{"sym": s, "old_shares": old[s]} for s in old if s not in new]}
    return {"preview": res, "change": change, "req": req}


def review_action(session, d: date, pid: int, action: str, data_stale: bool, name: Optional[str] = None) -> dict:
    r, req = _stored_req(session, pid)
    if d < r[1]:
        raise BuilderError("The review opens on the end date (%s)." % r[1].isoformat())
    if action == "close":
        session.execute(text("UPDATE user_model_portfolio SET status = 'CLOSED', close_reason = 'closed by you', closed_at = now() "
                             "WHERE portfolio_id = :p"), {"p": pid})
        session.commit()
        return {"closed": pid}
    if action == "roll":
        rp = review_preview(session, d, pid)
        session.execute(text("UPDATE user_model_portfolio SET status = 'CLOSED', close_reason = 'rolled over', closed_at = now() "
                             "WHERE portfolio_id = :p"), {"p": pid})
        try:
            res = accept(session, d, rp["req"], name, data_stale, rolled_from=pid, close_reason="replaced")
        except BuilderError:
            session.rollback()
            raise
        return res
    raise BuilderError("Unknown review action.")


def patch_warnings(session, pid: int, opt_in: Optional[dict], dismiss: Optional[list]) -> dict:
    r = session.execute(text("SELECT warnings FROM user_model_portfolio WHERE portfolio_id = :p"), {"p": pid}).fetchone()
    if not r:
        raise BuilderError("Model portfolio not found.")
    w = r[0] if isinstance(r[0], dict) else json.loads(r[0] or "{}")
    w.setdefault("opt_in", {})
    w.setdefault("fired", [])
    w.setdefault("dismissed", [])
    if opt_in:
        w["opt_in"].update({k: bool(v) for k, v in opt_in.items() if k in ("drop", "quad_turn", "no_new_risk", "final_call_sell")})
    for c in dismiss or []:
        if c not in w["dismissed"]:
            w["dismissed"].append(c)
    session.execute(text("UPDATE user_model_portfolio SET warnings = CAST(:w AS JSONB) WHERE portfolio_id = :p"), {"w": _dumps(w), "p": pid})
    session.commit()
    return w


def keep_add(session, short: str, sym: str, note: Optional[str] = None) -> None:
    session.execute(text("INSERT INTO ref_account_keep (account_short, tos_symbol, note) VALUES (:a, :s, :n) "
                         "ON CONFLICT (account_short, tos_symbol) DO UPDATE SET note = EXCLUDED.note"),
                    {"a": short, "s": sym.strip().upper(), "n": note})
    session.commit()


def keep_remove(session, short: str, sym: str) -> None:
    session.execute(text("DELETE FROM ref_account_keep WHERE account_short = :a AND tos_symbol = :s"), {"a": short, "s": sym.strip().upper()})
    session.commit()


def keep_add_lt(session, short: str, d: date) -> list:
    """One-click helper: add the active LT Hold names this account actually holds."""
    groups = bd.account_groups(session)
    g = groups.get(short)
    ap = bd.account_positions(session, g, d) if g else None
    held = set((ap or {}).get("holdings", {}).keys())
    added = [s for s in bd.lt_hold_symbols(session) if s in held]
    for s in added:
        keep_add(session, short, s, "LT Hold")
    return added


# ---------------------------------------------------------------------------
# Saved work: named sets of picks + targets (no freezing, no tracking)
# ---------------------------------------------------------------------------
def set_list(session) -> list:
    rows = session.execute(text("SELECT set_id, name, account_short, updated_at FROM user_builder_set ORDER BY updated_at DESC")).fetchall()
    return [{"id": r[0], "name": r[1], "account": r[2], "updated": r[3].isoformat() if r[3] else None} for r in rows]


def set_get(session, sid: int) -> dict:
    r = session.execute(text("SELECT set_id, name, account_short, state FROM user_builder_set WHERE set_id = :i"), {"i": sid}).fetchone()
    if not r:
        raise BuilderError("Saved set not found.")
    st = r[3] if isinstance(r[3], dict) else json.loads(r[3])
    return {"id": r[0], "name": r[1], "account": r[2], "state": st}


def set_save(session, name: str, account: Optional[str], state: dict) -> dict:
    name = (name or "").strip()
    if not name:
        raise BuilderError("Give the set a name.")
    r = session.execute(text(
        "INSERT INTO user_builder_set (name, account_short, state) VALUES (:n, :a, CAST(:s AS JSONB)) "
        "ON CONFLICT (name) DO UPDATE SET account_short = EXCLUDED.account_short, state = EXCLUDED.state, updated_at = now() "
        "RETURNING set_id"), {"n": name, "a": account, "s": json.dumps(state)}).fetchone()
    return {"id": r[0], "name": name}


def set_delete(session, sid: int) -> None:
    session.execute(text("DELETE FROM user_builder_set WHERE set_id = :i"), {"i": sid})
