"""Builder plan storage and the To do assembly (DESIGN_SPEC_16, per-account plans).

One plan per account: a draft (edit any day) and an active copy (taken at Activate). Picks are the stocks the user
chose for an account ("buy one of these" when several); ticked picks and ticked sells are counted in the To do tally.
The Builder never trades and never changes the Actionable Final Call. Pure math is in etl/plan_check.py.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text

from etl import builder_data as bd
from etl import plan_check as pc
from etl.derive_model_portfolio import FLAVOURS, final_call_side

log = logging.getLogger(__name__)


class PlanError(Exception):
    """A user-facing refusal (shown as a plain message)."""


def _j(v):
    if v is None or isinstance(v, (dict, list)):
        return v
    return json.loads(v)


def style_groups() -> dict:
    return {k: list(v) for k, v in FLAVOURS.items() if v}


# ---------------------------------------------------------------- account snapshot
def snapshot(session, d: date, account: str, problems: Optional[list] = None) -> dict:
    """Value, cash, holdings (with asset class) and name info for one account."""
    problems = problems if problems is not None else []
    ctx = bd.load_context(session, d, account, "3M", problems)
    a = ctx["account"]
    return {"account": account, "value": a["value"], "cash": a["cash"], "holdings": a["holdings"],
            "snap_date": a["snap_date"], "stale": a["stale"], "problems": problems}


# ---------------------------------------------------------------- plans
def get_plan_row(session, account: str) -> dict:
    r = session.execute(text("SELECT draft, active, active_at FROM user_plan WHERE account_short = :a"), {"a": account}).fetchone()
    if not r:
        return {"draft": None, "active": None, "active_at": None}
    return {"draft": _j(r[0]) or None, "active": _j(r[1]), "active_at": r[2].isoformat() if r[2] else None}


def save_draft(session, account: str, plan: dict) -> dict:
    p = pc.clean_plan(plan)
    session.execute(text("INSERT INTO user_plan (account_short, draft) VALUES (:a, CAST(:p AS JSONB)) "
                         "ON CONFLICT (account_short) DO UPDATE SET draft = EXCLUDED.draft, updated_at = now()"),
                    {"a": account, "p": json.dumps(p)})
    sync_buy_picks(session, account, p.get("picks") or [])
    session.commit()
    return p


def activate(session, account: str, plan: dict, dry_run: bool = False) -> dict:
    errs = pc.validate_plan(plan)
    if errs:
        raise PlanError(" ".join(errs))
    row = get_plan_row(session, account)
    p = pc.clean_plan(plan)
    changes = pc.plan_diff(row["active"], p)
    if dry_run:
        return {"changes": changes}
    session.execute(text("INSERT INTO user_plan (account_short, draft, active, active_at) VALUES (:a, CAST(:p AS JSONB), CAST(:p AS JSONB), now()) "
                         "ON CONFLICT (account_short) DO UPDATE SET draft = EXCLUDED.draft, active = EXCLUDED.active, "
                         "active_at = now(), updated_at = now()"), {"a": account, "p": json.dumps(p)})
    sync_buy_picks(session, account, p.get("picks") or [])
    session.commit()
    return {"changes": changes, "active": p}


def turn_off(session, account: str) -> None:
    session.execute(text("UPDATE user_plan SET active = NULL, active_at = NULL, updated_at = now() WHERE account_short = :a"), {"a": account})
    session.commit()


def account_states(session) -> dict:
    """{account: 'active' | 'draft' | 'none'} for the account box."""
    out = {}
    for a, draft, active in session.execute(text("SELECT account_short, draft, active FROM user_plan")).fetchall():
        out[a] = "active" if active else ("draft" if draft else "none")
    return out


# ---------------------------------------------------------------- picks
def list_picks(session, account: str) -> list:
    rows = session.execute(text("SELECT pick_id, side, members, amount_usd, ticked FROM user_plan_pick "
                                "WHERE account_short = :a ORDER BY made_at, pick_id"), {"a": account}).fetchall()
    return [{"id": r[0], "side": r[1], "members": _j(r[2]) or [], "amount": float(r[3] or 0), "ticked": bool(r[4])} for r in rows]


def add_pick(session, account: str, side: str, members: list, amount: float = 0.0, ticked: bool = False) -> int:
    side = (side or "").upper()
    if side not in ("BUY", "SELL"):
        raise PlanError("side must be BUY or SELL.")
    members = [str(m).strip().upper() for m in (members or []) if str(m).strip()]
    if not members:
        raise PlanError("Choose at least one stock.")
    if side == "BUY":
        for pk in list_picks(session, account):
            if pk["side"] == "BUY" and set(pk["members"]) & set(members):
                dup = sorted(set(pk["members"]) & set(members))[0]
                raise PlanError("%s is already in a pick for %s." % (dup, account))
    elif side == "SELL":           # a sell tick is one holding: replace any earlier tick on it
        session.execute(text("DELETE FROM user_plan_pick WHERE account_short = :a AND side = 'SELL' AND members = CAST(:m AS JSONB)"),
                        {"a": account, "m": json.dumps(members)})
    r = session.execute(text("INSERT INTO user_plan_pick (account_short, side, members, amount_usd, ticked) "
                             "VALUES (:a, :s, CAST(:m AS JSONB), :amt, :t) RETURNING pick_id"),
                        {"a": account, "s": side, "m": json.dumps(members), "amt": max(0.0, float(amount or 0)), "t": bool(ticked)}).fetchone()
    session.commit()
    return r[0]


def patch_pick(session, pick_id: int, body: dict) -> None:
    sets, par = [], {"i": pick_id}
    if "amount" in body:
        sets.append("amount_usd = :amt")
        par["amt"] = max(0.0, float(body["amount"] or 0))
    if "ticked" in body:
        sets.append("ticked = :t")
        par["t"] = bool(body["ticked"])
    if not sets:
        return
    session.execute(text("UPDATE user_plan_pick SET %s WHERE pick_id = :i" % ", ".join(sets)), par)
    session.commit()


def delete_pick(session, pick_id: int) -> None:
    session.execute(text("DELETE FROM user_plan_pick WHERE pick_id = :i"), {"i": pick_id})
    session.commit()


def clear_sell_ticks(session, account: str) -> None:
    session.execute(text("DELETE FROM user_plan_pick WHERE account_short = :a AND side = 'SELL'"), {"a": account})
    session.commit()


def sync_buy_picks(session, account: str, picks: list) -> None:
    """The grid's picks that have an amount become this account's BUY picks: one row per 'buy one of' group (same group
    letter) or per single stock, amount = the group's amount. Ticks are kept for rows that did not change; rows no longer
    in the grid are removed. Does not commit."""
    groups, order = {}, []
    for pk in picks or []:
        g = pk.get("grp") or ""
        key = ("g", g) if g else ("s", pk["sym"])
        if key not in groups:
            groups[key] = {"members": [], "amount": 0.0}
            order.append(key)
        groups[key]["members"].append(pk["sym"])
        groups[key]["amount"] = max(groups[key]["amount"], float(pk.get("amt") or 0.0))
    items = [groups[k] for k in order if groups[k]["amount"] > 0]
    existing = {frozenset(p["members"]): p for p in list_picks(session, account) if p["side"] == "BUY"}
    keep = set()
    for it in items:
        ex = existing.get(frozenset(it["members"]))
        if ex:
            session.execute(text("UPDATE user_plan_pick SET amount_usd = :amt WHERE pick_id = :i"), {"amt": it["amount"], "i": ex["id"]})
            keep.add(ex["id"])
        else:
            session.execute(text("INSERT INTO user_plan_pick (account_short, side, members, amount_usd, ticked) "
                                 "VALUES (:a, 'BUY', CAST(:m AS JSONB), :amt, FALSE)"),
                            {"a": account, "m": json.dumps(it["members"]), "amt": it["amount"]})
    for p in existing.values():
        if p["id"] not in keep:
            session.execute(text("DELETE FROM user_plan_pick WHERE pick_id = :i"), {"i": p["id"]})
    session.flush()


# ---------------------------------------------------------------- my stocks
def hedgeye_names(session, d: date, problems: Optional[list] = None) -> set:
    """Every name any Hedgeye list is bullish on today."""
    codes = list(bd.SOURCE_LABELS.keys())
    return {r["sym"] for r in bd.source_names(session, d, codes, problems) if r.get("bullish")}


def my_stocks(session, d: date) -> list:
    """The user's own stocks. A stock Hedgeye now lists is stamped (moved_on) and counts as a Hedgeye name instead."""
    rows = session.execute(text("SELECT tos_symbol, note, moved_on FROM user_my_stock ORDER BY tos_symbol")).fetchall()
    if not rows:
        return []
    hed = hedgeye_names(session, d)
    moved = [r[0] for r in rows if r[2] is None and r[0] in hed]
    if moved:
        session.execute(text("UPDATE user_my_stock SET moved_on = :d WHERE tos_symbol = ANY(:s) AND moved_on IS NULL"), {"d": d, "s": moved})
        session.commit()
        rows = session.execute(text("SELECT tos_symbol, note, moved_on FROM user_my_stock ORDER BY tos_symbol")).fetchall()
    return [{"sym": r[0], "note": r[1], "moved_on": r[2].isoformat() if r[2] else None} for r in rows]


def add_my_stock(session, d: date, sym: str, note: Optional[str] = None) -> dict:
    sym = (sym or "").strip().upper()
    if not sym:
        raise PlanError("Type a symbol.")
    if sym in hedgeye_names(session, d):
        raise PlanError("%s is on a Hedgeye list today, so pick it from the Hedgeye names." % sym)
    session.execute(text("INSERT INTO user_my_stock (tos_symbol, note, moved_on) VALUES (:s, :n, NULL) "
                         "ON CONFLICT (tos_symbol) DO UPDATE SET note = EXCLUDED.note, moved_on = NULL"), {"s": sym, "n": note})
    session.commit()
    return {"sym": sym}


def remove_my_stock(session, sym: str) -> None:
    session.execute(text("DELETE FROM user_my_stock WHERE tos_symbol = :s"), {"s": (sym or "").strip().upper()})
    session.commit()


# ---------------------------------------------------------------- calls
def sizes_for(session, d: date, account: str, syms: list) -> dict:
    """The existing amount rules per stock in this account (drv_account_size): {sym: {min, max, unit}} dollars."""
    if not syms:
        return {}
    try:
        rows = session.execute(text("SELECT tos_symbol, min_dollar, max_dollar, unit_dollar FROM drv_account_size "
                                    "WHERE as_of_date = :d AND account_short = :a AND tos_symbol = ANY(:s)"),
                               {"d": d, "a": account, "s": list(syms)}).fetchall()
    except Exception as e:      # table missing on a fresh DB
        log.warning("plan_store.sizes_for: %s", e)
        session.rollback()
        return {}
    f = lambda v: float(v) if v is not None else None
    return {r[0]: {"min": f(r[1]), "max": f(r[2]), "unit": f(r[3])} for r in rows}


def account_default_size(session, d: date, account: str) -> dict:
    """The account's usual per-stock rule (the most common Min / Max / Unit among its amount rules). A stock or ETF with no rule of its own uses it."""
    try:
        rows = session.execute(text("SELECT min_dollar, max_dollar, unit_dollar, COUNT(*) AS n FROM drv_account_size "
                                    "WHERE as_of_date = :d AND account_short = :a AND max_dollar IS NOT NULL "
                                    "GROUP BY 1, 2, 3 ORDER BY n DESC, max_dollar DESC LIMIT 1"), {"d": d, "a": account}).fetchall()
    except Exception as e:      # table missing on a fresh DB
        log.warning("plan_store.account_default_size: %s", e)
        session.rollback()
        return {}
    if not rows:
        return {}
    f = lambda v: float(v) if v is not None else None
    return {"min": f(rows[0][0]), "max": f(rows[0][1]), "unit": f(rows[0][2])}


def calls_for(session, d: date, syms: list) -> dict:
    if not syms:
        return {}
    try:
        rows = session.execute(text("SELECT tos_symbol, final_code FROM drv_actionable WHERE as_of_date = :d AND tos_symbol = ANY(:s)"),
                               {"d": d, "s": list(syms)}).fetchall()
    except Exception as e:      # table missing on a fresh DB
        log.warning("plan_store.calls_for: %s", e)
        session.rollback()
        return {}
    return {r[0]: r[1] for r in rows}


# ---------------------------------------------------------------- page data
def plan_page(session, d: date, account: str) -> dict:
    """Everything the Plan tab needs for one account."""
    problems: list = []
    snap = snapshot(session, d, account, problems)
    row = get_plan_row(session, account)
    syms = list(snap["holdings"].keys())
    info = bd.name_info(session, d, syms, problems) if syms else {}
    now = pc.now_lines(snap["holdings"], info, snap["cash"], style_groups())
    state = "active" if row["active"] else ("draft" if row["draft"] else "none")
    return {"account": account, "state": state, "draft": row["draft"], "active": row["active"], "active_at": row["active_at"],
            "value": snap["value"], "cash": snap["cash"], "snap_date": snap["snap_date"].isoformat() if snap["snap_date"] else None,
            "stale": snap["stale"], "now": now, "classes": pc.CLASSES,
            "sectors": sorted(now["sector"].keys()), "styles": sorted(style_groups().keys()),
            "picks": list_picks(session, account), "problems": problems}


_PC_CACHE: dict = {}


def done_rows(session, d: date, account: str) -> list:
    """Today's Done marks for an account (empty if the table does not exist yet: run `python -m db.init_db`)."""
    try:
        rs = session.execute(text("SELECT tos_symbol, side, amount_usd, qty_at_done FROM user_plan_done WHERE account_short = :a AND as_of_date = :d ORDER BY id"),
                             {"a": account, "d": d}).fetchall()
    except Exception as e:      # table not created yet
        log.warning("plan_store.done_rows: %s", e)
        session.rollback()
        return []
    return [{"sym": r[0], "side": r[1], "amount": float(r[2] or 0.0), "qty_at_done": float(r[3] or 0.0)} for r in rs]


def record_done(session, d: date, account: str, sym: str, side: str, amount: float) -> dict:
    """The user marked a planned buy / sell Done for `amount` dollars (maybe part of it). Remembers the shares held now."""
    sym = str(sym or "").upper()
    side = "SELL" if str(side).upper() == "SELL" else "BUY"
    if amount is None or float(amount) <= 0:
        raise PlanError("Give the amount that was done.")
    snap = snapshot(session, d, account, [])
    q0 = float((snap["holdings"].get(sym) or {}).get("qty") or 0.0)
    try:
        session.execute(text("INSERT INTO user_plan_done (account_short, tos_symbol, as_of_date, side, amount_usd, qty_at_done) "
                             "VALUES (:a, :s, :d, :sd, :amt, :q)"), {"a": account, "s": sym, "d": d, "sd": side, "amt": float(amount), "q": q0})
        session.commit()
    except Exception as e:      # table not created yet
        session.rollback()
        raise PlanError("The Done table is missing: run  python -m db.init_db  once. (%s)" % str(e).splitlines()[0])
    _PC_CACHE.clear()
    return {"ok": True, "sym": sym, "side": side, "amount": float(amount)}


def clear_done(session, d: date, account: str, sym: str) -> None:
    try:
        session.execute(text("DELETE FROM user_plan_done WHERE account_short = :a AND as_of_date = :d AND tos_symbol = :s"), {"a": account, "d": d, "s": str(sym).upper()})
        session.commit()
    except Exception as e:
        session.rollback()
        log.warning("plan_store.clear_done: %s", e)
    _PC_CACHE.clear()


def acct_room_page(session, d: date, account: str) -> dict:
    """Actionable screen, ONE account: per symbol what that account holds, the most this one stock can still be bought (Max $), the room left in
    the buckets it falls in (Bucket $), and the planned buy still to do. Uses the account's ACTIVE plan; information only. Same maths as the Builder
    (plan_check.room_for). Rows: stocks held, planned, or with a Buy call today. {state, rows {sym: {...}}, value, cash, spendable}."""
    problems: list = []
    row = get_plan_row(session, account)
    snap = snapshot(session, d, account, problems)
    holdings = snap["holdings"]
    value = float(snap["value"] or 0.0)
    out = {"account": account, "state": "active" if row["active"] else "none", "rows": {}, "problems": problems, "value": value, "cash": snap["cash"]}
    for sym, h in holdings.items():
        v = float(h.get("value") or 0.0)
        if v > 0:
            out["rows"][sym] = {"held": v, "held_pct": (v / value * 100.0) if value else None}
    if not row["active"]:
        return out
    plan = pc.clean_plan(row["active"])
    try:
        all_calls = {r[0]: r[1] for r in session.execute(text("SELECT tos_symbol, final_code FROM drv_actionable WHERE as_of_date = :d"), {"d": d}).fetchall()}
    except Exception as e:      # table missing on a fresh DB
        log.warning("acct_room_page: %s", e)
        session.rollback()
        all_calls = {}
    buy_syms = [s for s, c in all_calls.items() if final_call_side(c) == "buy"]
    picks = [p for p in list_picks(session, account) if p["side"] == "BUY"]
    # planned buy still to do = the saved amount less what has been bought since the plan was saved (shares added x price)
    pend = pc.done_pending(done_rows(session, d, account), holdings)          # marked Done today, not in the positions file yet
    planned = {}
    for pk in picks:
        for i, m in enumerate(pk["members"]):
            h = holdings.get(m) or {}
            base = plan["pick_base"].get(m)
            bought = max(0.0, float(h.get("qty") or 0.0) - base) * float(h.get("price") or 0.0) if base is not None else 0.0
            left = max(0.0, float(pk["amount"] or 0.0) - bought)
            dn = (pend.get(m) or {}).get("BUY", 0.0)
            planned[m] = {"amount": max(0.0, left - dn), "group": len(pk["members"]) > 1, "first": i == 0}
    for m, v in pend.items():                                                  # a stock bought today that was not planned also uses room
        if v.get("BUY", 0.0) > 0:
            planned.setdefault(m, {"amount": 0.0, "group": False, "first": True})
    syms = sorted(set(holdings) | set(buy_syms) | set(planned))
    info = bd.name_info(session, d, syms, problems) if syms else {}
    cands = [{"sym": s, "bucket": (holdings.get(s) or {}).get("bucket"), "amt": ((planned[s]["amount"] + (pend.get(s) or {}).get("BUY", 0.0)) if s in planned and (not planned[s]["group"] or planned[s]["first"]) else 0.0), "pick": False}
             for s in syms]
    room = pc.room_for(plan, {"value": value, "cash": snap["cash"], "holdings": holdings}, cands, info, style_groups(),
                       sizes_for(session, d, account, syms), None, account_default_size(session, d, account))
    summ = pc.cash_summary(plan, {"value": value, "cash": snap["cash"], "holdings": holdings}, info, style_groups())
    for s in syms:
        r = room.get(s)
        if r is None:
            continue
        o = out["rows"].setdefault(s, {})
        o.update({"stock": r["stock"], "bucket": r["bucket"], "max": r["max"], "binding": r["binding"], "bucket_binding": r["bucket_binding"]})
        if s in planned:
            o["planned"] = planned[s]["amount"]
            o["planned_group"] = planned[s]["group"]
        if (pend.get(s) or {}).get("BUY", 0.0) > 0:
            o["done_buy"] = pend[s]["BUY"]
    # planned SELLS: each class above its plan is sold by the amount saved in the plan (default: the excess), split over its holdings in proportion to their value
    now = pc.now_lines(holdings, info, snap["cash"], style_groups())
    for n in pc.sell_needs(plan, now, value):
        vals = {sym: float(h.get("value") or 0.0) for sym, h in holdings.items() if h.get("bucket") == n["cls"] and float(h.get("value") or 0.0) > 0}
        amt = plan["sell"].get(n["cls"])
        amt = n["need"] if amt is None else min(amt, sum(vals.values()))
        for sym, v in pc.alloc_sell(vals, amt, plan["sell_hold"]).items():
            dn = (pend.get(sym) or {}).get("SELL", 0.0)
            if v - dn > 0.5:
                out["rows"].setdefault(sym, {})["planned_sell"] = v - dn
            if dn > 0:
                out["rows"].setdefault(sym, {})["done_sell"] = dn
    out["spendable"] = summ["spendable"]
    out["sells"] = summ["sells"]
    return out


def plan_check_page(session, d: date) -> dict:
    """For the Actionable screen: per symbol, what each ACTIVE plan says about it (information only, never changes a Final
    Call). Per account with an active plan: its sells (holdings in classes above plan), its planned picks / groups, and for
    every Buy call whether it would be over plan there. {rows: {sym: [{account, kind, ...}]}, accounts: [...]}."""
    import time
    states = account_states(session)
    active = sorted(a for a, st in states.items() if st == "active")
    plans = {a: get_plan_row(session, a) for a in active}
    key = (d, tuple((a, plans[a]["active_at"]) for a in active))
    hit = _PC_CACHE.get("k")
    if hit and hit[0] == key and time.time() - hit[1] < 120 and not _picks_changed(session, active, hit[3]):
        return hit[2]
    rows: dict = {}
    accounts = []
    sg = style_groups()
    try:
        all_calls = {r[0]: r[1] for r in session.execute(text("SELECT tos_symbol, final_code FROM drv_actionable WHERE as_of_date = :d"), {"d": d}).fetchall()}
    except Exception as e:      # table missing on a fresh DB
        log.warning("plan_check_page: %s", e)
        session.rollback()
        all_calls = {}
    buy_syms = [s for s, c in all_calls.items() if final_call_side(c) == "buy"]
    for acct in active:
        plan = pc.clean_plan(plans[acct]["active"])
        problems: list = []
        snap = snapshot(session, d, acct, problems)
        picks = list_picks(session, acct)
        syms = sorted(set(snap["holdings"]) | set(buy_syms) | {m for pk in picks for m in pk["members"]})
        info = bd.name_info(session, d, syms, problems) if syms else {}
        now = pc.now_lines(snap["holdings"], info, snap["cash"], sg)
        value = snap["value"]
        spend = pc.cash_to_spend(snap["cash"], 0.0, value, plan)
        accounts.append({"account": acct, "active_at": plans[acct]["active_at"], "cash_to_spend": spend, "stale": snap["stale"]})
        used = {"cls": {}, "sector": {}, "style": {}, "beta": {}, "quad": {}}
        left = {(r["kind"], r["key"]): r for r in pc._line_rows(plan, value, now, used)}
        # sells: holdings in classes above their plan
        for n in pc.sell_needs(plan, now, value):
            for sym, h in snap["holdings"].items():
                if h.get("bucket") == n["cls"] and float(h.get("value") or 0) > 0:
                    rows.setdefault(sym, []).append({"account": acct, "kind": "sell", "cls": n["cls"], "all": n["all"], "need": n["need"],
                                                     "plan_pct": n["plan_pct"], "value": float(h["value"])})
        # planned picks / groups
        for pk in picks:
            if pk["side"] != "BUY":
                continue
            for m in pk["members"]:
                rows.setdefault(m, []).append({"account": acct, "kind": "group" if len(pk["members"]) > 1 else "pick",
                                               "members": pk["members"], "amount": pk["amount"]})
        # every Buy call: would a buy be over plan here? (a line with no room left, or no cash left)
        for sym in buy_syms:
            ln = pc._lines_of(sym, (snap["holdings"].get(sym) or {}).get("bucket"), info, sg)
            if not ln["cls"] or ln["cls"] == "Cash":
                continue
            over, fits = [], None
            def look(kind, key):
                nonlocal fits
                r = left.get((kind, key))
                if r is None:
                    return
                if r["left"] <= 0:
                    over.append({"line": r.get("label") or key, "over": -r["left"]})
                fits = r["left"] if fits is None else min(fits, r["left"])
            look("cls", ln["cls"])
            look("sector", ln["sector"])
            for k in ln["style"]:
                look("style", k)
            look("beta", ln["beta"])
            for k in ln["quad"]:
                look("quad", k)
            fits = max(0.0, min(fits if fits is not None else spend, spend))
            if over or spend <= 0:
                rows.setdefault(sym, []).append({"account": acct, "kind": "buy", "over": over, "fits": fits, "cash": spend <= 0})
    out = {"as_of": d.isoformat(), "accounts": accounts, "rows": rows}
    _PC_CACHE["k"] = (key, time.time(), out, _picks_sig(session, active))
    return out


DEFAULT_VERSION = "Main"


def _vname(name) -> str:
    return (str(name or "").strip()[:40]) or DEFAULT_VERSION


def list_versions(session, account: str) -> dict:
    """{versions: [{name, saved_at}], checked: name or None}. Newest first. The checked one is the plan the warnings use."""
    rows = session.execute(text("SELECT name, saved_at FROM user_plan_version WHERE account_short = :a ORDER BY saved_at DESC"),
                           {"a": account}).fetchall()
    r = session.execute(text("SELECT active_name, active IS NOT NULL FROM user_plan WHERE account_short = :a"), {"a": account}).fetchone()
    checked = r[0] if (r and r[1]) else None
    return {"versions": [{"name": x[0], "saved_at": x[1].isoformat() if x[1] else None} for x in rows], "checked": checked}


def get_version(session, account: str, name: str) -> Optional[dict]:
    r = session.execute(text("SELECT plan FROM user_plan_version WHERE account_short = :a AND name = :n"),
                        {"a": account, "n": _vname(name)}).fetchone()
    return _j(r[0]) if r else None


def save_version(session, account: str, name: str, plan: dict) -> str:
    """Keep a named version. Kept as a saved version."""
    n, p = _vname(name), pc.clean_plan(plan)
    session.execute(text("INSERT INTO user_plan_version (account_short, name, plan) VALUES (:a, :n, CAST(:p AS JSONB)) "
                         "ON CONFLICT (account_short, name) DO UPDATE SET plan = EXCLUDED.plan, saved_at = now()"),
                    {"a": account, "n": n, "p": json.dumps(p)})
    session.commit()
    return n


def save_and_check(session, d: date, account: str, plan: dict, name: Optional[str] = None) -> dict:
    """ONE save: keeps the limits, planned buys and ticked lists as version `name` AND makes it the checked plan (the top-bar
    warning, the To do list, Actionable). A plan that cannot be checked yet (e.g. classes do not add to 100) is still saved.
    Returns {saved, checking, name, problems, warning, changes}."""
    n = save_version(session, account, name, plan)
    errs = pc.validate_plan(plan)
    if errs:
        res = {"saved": True, "checking": False, "name": n, "problems": errs, "warning": None, "changes": []}
    else:
        r = activate(session, account, plan)
        session.execute(text("UPDATE user_plan SET active_name = :n WHERE account_short = :a"), {"a": account, "n": n})
        session.commit()
        _PC_CACHE.clear()
        res = {"saved": True, "checking": True, "name": n, "problems": [], "changes": r["changes"],
               "warning": None}
    return res


def delete_plan(session, account: str, name: Optional[str] = None) -> None:
    """Delete one saved version. If it was the checked one, the checks for this account stop and its planned buys are cleared.
    (The account's My stocks list is kept.)"""
    n = _vname(name)
    session.execute(text("DELETE FROM user_plan_version WHERE account_short = :a AND name = :n"), {"a": account, "n": n})
    r = session.execute(text("SELECT active_name FROM user_plan WHERE account_short = :a AND active IS NOT NULL"), {"a": account}).fetchone()
    if r and (r[0] or DEFAULT_VERSION) == n:
        session.execute(text("DELETE FROM user_plan_pick WHERE account_short = :a"), {"a": account})
        session.execute(text("DELETE FROM user_plan WHERE account_short = :a"), {"a": account})
    session.commit()
    _PC_CACHE.clear()


def _picks_sig(session, active: list):
    r = session.execute(text("SELECT COUNT(*), COALESCE(SUM(amount_usd), 0), MAX(made_at) FROM user_plan_pick WHERE account_short = ANY(:a)"), {"a": list(active)}).fetchone()
    return (r[0], float(r[1] or 0), str(r[2]))


def _picks_changed(session, active: list, sig) -> bool:
    return _picks_sig(session, active) != sig


def todo_page(session, d: date, account: str) -> dict:
    """Everything the To do tab needs: sells, buys with Actionable's call, what is left."""
    problems: list = []
    row = get_plan_row(session, account)
    if not row["active"]:
        return {"account": account, "state": "none", "problems": problems}
    snap = snapshot(session, d, account, problems)
    picks = list_picks(session, account)
    syms = sorted(set(snap["holdings"].keys()) | {m for pk in picks for m in pk["members"]})
    info = bd.name_info(session, d, syms, problems) if syms else {}
    calls = calls_for(session, d, syms)
    pend = pc.done_pending(done_rows(session, d, account), snap["holdings"])
    for pk in picks:                              # a buy marked Done today comes off the to-do amount
        if pk["side"] == "BUY" and len(pk["members"]) == 1:
            pk["amount"] = max(0.0, float(pk["amount"] or 0.0) - (pend.get(pk["members"][0]) or {}).get("BUY", 0.0))
    out = pc.todo(row["active"], {"value": snap["value"], "cash": snap["cash"], "holdings": snap["holdings"]},
                  picks, calls, info, style_groups(), final_call_side, sizes_for(session, d, account, syms), assume_sells=True, warn_only=True)
    out.update({"account": account, "state": "active", "active_at": row["active_at"], "plan": row["active"],
                "snap_date": snap["snap_date"].isoformat() if snap["snap_date"] else None, "stale": snap["stale"],
                "problems": problems})
    return out
