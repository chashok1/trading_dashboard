"""Per-account plan checks for the Builder (DESIGN_SPEC_16, simplified to the "Plan" and "To do" tabs).

Pure functions, no database. The plan is one account's target mix: asset classes are required and add to 100,
beta / sector / style / My stocks are optional (a blank line is "Open": shown, never limits anything).
Money limits BLOCK (an account cannot spend cash it does not have, and keeps its cash floor and the plan's Cash %).
Percentage lines only WARN. Nothing here trades and nothing changes the Actionable Final Call.

Plan shape:
  {"cls": {"Equities": 50, ..., "Cash": 18}, "beta": {"low": None, "high": None},
   "sector": {"Technology": None, ...}, "style": {"Growth": None, ...}, "my_stocks": None, "cash_keep": 1000}
"""
from __future__ import annotations

from typing import Optional

CLASSES = ["Equities", "Fixed Income", "Gold", "Commodities", "Crypto", "Currency", "Cash"]
TOL = 0.1                 # class percentages must add to 100 within this
MIN_NEED = 500.0          # a class over its plan by less than this is "on plan" (no sell asked)
DEFAULT_CASH_KEEP = 1000.0
BETA_LABEL = {"low": "Low beta (0.8 or less)", "high": "High beta (over 1.2)", "mid": "Middle beta (0.8 to 1.2)", "none": "No beta known"}
NEAR = 0.90               # a sector / style / beta limit that is this much used (or more) is "Near" (GUESS, one place)


def tolerance(value: float) -> float:
    """On-plan band in dollars: the smaller of $500 and 0.5% of the account (GUESS), so small accounts are not too loose."""
    return min(MIN_NEED, 0.005 * float(value or 0.0)) if value else MIN_NEED


def line_state(r: dict, value: float) -> str:
    """One word per plan line. Asset classes: ROOM / ON_PLAN / OVER (Cash: ROOM / ON_PLAN / SHORT).
    Optional ceilings (sector, style, beta): OK / NEAR / OVER."""
    tol = tolerance(value)
    if r["kind"] == "cls":
        if r["key"] == "Cash":
            return "SHORT" if r["left"] < -tol else ("ROOM" if r["left"] > tol else "ON_PLAN")
        return "OVER" if r["left"] < -tol else ("ROOM" if r["left"] > tol else "ON_PLAN")
    after = r["now"] + r["used"]
    plan = r["plan"]
    if after > plan + tol:
        return "OVER"
    if plan > 0 and after >= NEAR * plan:
        return "NEAR"
    return "OK"


def _f(x) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def clean_plan(plan: Optional[dict]) -> dict:
    """Plan with every number a float or None, and every asset class present (missing = 0)."""
    plan = plan or {}
    cls = {c: (_f((plan.get("cls") or {}).get(c)) or 0.0) for c in CLASSES}
    out = {"cls": cls,
           "beta": {k: _f((plan.get("beta") or {}).get(k)) for k in ("low", "high", "mid", "none")},
           "sector": {k: _f(v) for k, v in (plan.get("sector") or {}).items()},
           "style": {k: _f(v) for k, v in (plan.get("style") or {}).items()},
           "quad": {k: _f((plan.get("quad") or {}).get(k)) for k in ("Q1", "Q2", "Q3", "Q4")},
           "my_stocks": _f(plan.get("my_stocks")),
           "cash_keep": _f(plan.get("cash_keep")),
           # 2026-11-20: dollars to sell per asset class, and per holding when typed over (saved with the plan)
           "sell": {k: v for k, v in ((k, _f(v)) for k, v in (plan.get("sell") or {}).items()) if v is not None and v >= 0},
           "sell_hold": {str(k).upper(): v for k, v in ((k, _f(v)) for k, v in (plan.get("sell_hold") or {}).items()) if v is not None and v >= 0},
           # 2026-11-20: shares held of each planned buy when the plan was saved, so later purchases come off the planned amount
           "pick_base": {str(k).upper(): v for k, v in ((k, _f(v)) for k, v in (plan.get("pick_base") or {}).items()) if v is not None and v >= 0},
           # 2026-11-20, user: the user's own lower cap on the TOTAL held of a stock (never above the stock's rule Max)
           "my_max": {str(k).upper(): v for k, v in ((k, _f(v)) for k, v in (plan.get("my_max") or {}).items()) if v is not None and v >= 0}}
    if out["cash_keep"] is None:
        out["cash_keep"] = DEFAULT_CASH_KEEP
    picks = []
    for pk in (plan.get("picks") or []):
        sym = str((pk or {}).get("sym") or "").strip().upper()
        if sym:
            picks.append({"sym": sym, "bucket": pk.get("bucket"), "pct": _f(pk.get("pct")), "amt": _f(pk.get("amt")) or 0.0,
                          "grp": str(pk.get("grp") or "")[:4]})
    out["picks"] = picks
    out["sources"] = [str(x) for x in (plan.get("sources") or []) if x]    # the lists that were ticked
    return out


def eff_max(cap: Optional[dict], mine: Optional[float]):
    """(max, yours) -- the cap on the total held of a stock: the stock's rule Max, lowered (never raised) by the user's own max."""
    rule = (cap or {}).get("max")
    rule = float(rule) if rule is not None else None
    if mine is None:
        return rule, False
    if rule is None or float(mine) < rule:
        return float(mine), True
    return rule, False


def validate_plan(plan: dict) -> list:
    """Plain-language reasons the plan cannot be activated (empty list = fine)."""
    p = clean_plan(plan)
    errs = []
    nums = list(p["cls"].values()) + [v for v in p["sector"].values() if v is not None] + \
        [v for v in p["style"].values() if v is not None] + [v for v in p["beta"].values() if v is not None] + \
        [v for v in p["quad"].values() if v is not None]
    if p["my_stocks"] is not None:
        nums.append(p["my_stocks"])
    if any(n < 0 for n in nums):
        errs.append("A percentage cannot be negative.")
    tot = sum(p["cls"].values())
    if abs(tot - 100.0) > TOL:
        errs.append("Asset classes add to %s%%. They must add to 100." % ("%g" % round(tot, 2)))
    sec = sum(v for v in p["sector"].values() if v is not None)
    if sec > p["cls"]["Equities"] + TOL:
        errs.append("Sectors add to %s%%, more than Equities (%s%%)." % ("%g" % round(sec, 2), "%g" % p["cls"]["Equities"]))
    if sum((p["beta"][k] or 0) for k in ("low", "high", "mid", "none")) > 100 + TOL:
        errs.append("The beta limits add to more than 100%.")
    return errs


def plan_diff(old: Optional[dict], new: dict) -> list:
    """Bulleted change list shown before Activate, e.g. 'Equities 48% to 52%'."""
    a, b = clean_plan(old) if old else None, clean_plan(new)
    out = []
    for c in CLASSES:
        n = b["cls"][c]
        o = a["cls"][c] if a else None
        if o is None or abs(o - n) > 1e-9:
            out.append(("%s %g%% to %g%%" % (c, o, n)) if o is not None else ("%s set to %g%%" % (c, n)))
    for grp in ("sector", "style"):
        for k, v in b[grp].items():
            o = (a[grp].get(k) if a else None)
            if v != o:
                out.append("%s %s to %s" % (k, ("%g%%" % o) if o is not None else "Open", ("%g%%" % v) if v is not None else "Open"))
    for k in ("Q1", "Q2", "Q3", "Q4"):
        o = a["quad"][k] if a else None
        if b["quad"][k] != o:
            out.append("%s favored %s to %s" % (k, ("%g%%" % o) if o is not None else "Open", ("%g%%" % b["quad"][k]) if b["quad"][k] is not None else "Open"))
    for k in ("low", "high", "mid", "none"):
        o = a["beta"][k] if a else None
        if b["beta"][k] != o:
            out.append("%s %s to %s" % (BETA_LABEL[k], ("%g%%" % o) if o is not None else "Open",
                                        ("%g%%" % b["beta"][k]) if b["beta"][k] is not None else "Open"))
    return out


def now_lines(holdings: dict, info: dict, cash: float, style_groups: Optional[dict] = None) -> dict:
    """Dollars held per line. holdings {sym: {value, bucket}}, info {sym: {sector, beta, styles}}.
    Style / beta lines count stocks (names with a known row); styles can overlap."""
    cls = {c: 0.0 for c in CLASSES}
    cls["Cash"] = float(cash or 0.0)
    sector, style, beta = {}, {}, {"low": 0.0, "high": 0.0, "mid": 0.0, "none": 0.0}
    quad = {q: 0.0 for q in ("Q1", "Q2", "Q3", "Q4")}
    groups = {k: {str(t).lower() for t in v} for k, v in (style_groups or {}).items() if v}
    for sym, h in holdings.items():
        v = float(h.get("value") or 0.0)
        if v <= 0:
            continue
        b = h.get("bucket") if h.get("bucket") in CLASSES else "Unmapped"
        cls[b] = cls.get(b, 0.0) + v
        r = info.get(sym) or {}
        for i, w in enumerate(r.get("quad") or []):
            if w == "bull" and i < 4:
                quad["Q%d" % (i + 1)] += v       # all asset classes: money in names Hedgeye favours (Bull) in that Quad
        if b == "Equities":
            s = r.get("sector")
            if s and s not in ("Unmapped", "Other"):
                sector[s] = sector.get(s, 0.0) + v
            have = {str(t).lower() for t in (r.get("styles") or [])}
            hit = False
            for k, tags in groups.items():
                if have & tags:
                    style[k] = style.get(k, 0.0) + v
                    hit = True
            if not hit:
                style["none"] = style.get("none", 0.0) + v
            bt = r.get("beta")
            if bt is None:
                beta["none"] += v
            elif bt <= 0.8:
                beta["low"] += v
            elif bt > 1.2:
                beta["high"] += v
            else:
                beta["mid"] += v
    return {"cls": cls, "sector": sector, "style": style, "beta": beta, "quad": quad}


def cash_to_spend(cash: float, sell_cash: float, value: float, plan: dict) -> float:
    """Cash that may be spent: keeps the account's cash floor AND the plan's Cash %. Never below 0."""
    p = clean_plan(plan)
    avail = float(cash or 0.0) + float(sell_cash or 0.0)
    room = avail - p["cash_keep"]
    pct = p["cls"].get("Cash")
    if pct is not None:
        room = min(room, avail - pct / 100.0 * value)
    return max(0.0, room)


def _lines_of(sym: str, h_bucket: Optional[str], info: dict, style_groups: dict) -> dict:
    """The plan lines a stock counts in: its class, its sector, its style groups, its beta side."""
    r = info.get(sym) or {}
    b = h_bucket if h_bucket in CLASSES else (r.get("bucket") if r.get("bucket") in CLASSES else None)
    out = {"cls": b, "sector": None, "style": [], "beta": None,
           "quad": ["Q%d" % (i + 1) for i, w in enumerate(r.get("quad") or []) if w == "bull" and i < 4]}
    if b == "Equities":
        s = r.get("sector")
        if s and s not in ("Unmapped", "Other"):
            out["sector"] = s
        have = {str(t).lower() for t in (r.get("styles") or [])}
        out["style"] = [k for k, tags in style_groups.items() if have & {str(t).lower() for t in tags}] or ["none"]
        bt = r.get("beta")
        out["beta"] = "none" if bt is None else ("low" if bt <= 0.8 else ("high" if bt > 1.2 else "mid"))
    return out


def alloc_sell(values: dict, amount: float, overrides: Optional[dict] = None) -> dict:
    """Split a sale of `amount` dollars over holdings {sym: value}: every holding is cut in the same proportion to its value.
    A holding in `overrides` ({sym: dollars}) takes exactly that (never more than it holds) and the others share what is left.
    Whole dollars; the rounding remainder goes to the largest holding that is not overridden. Returns {sym: dollars to sell}."""
    values = {k: max(0.0, float(v or 0.0)) for k, v in values.items()}
    ov = {k: min(max(0.0, float(v)), values[k]) for k, v in (overrides or {}).items() if k in values}
    total = sum(values.values())
    amount = min(max(0.0, float(amount or 0.0)), total)
    fixed = sum(ov.values())
    rest = max(0.0, amount - fixed)
    free = {k: v for k, v in values.items() if k not in ov}
    base = sum(free.values())
    out = {k: float(round(v)) for k, v in ov.items()}
    if base > 0 and rest > 0:
        for k, v in free.items():
            out[k] = float(round(rest * v / base))
        diff = round(rest) - sum(out[k] for k in free)
        big = max(free, key=lambda k: free[k])
        out[big] = min(free[big], max(0.0, out[big] + diff))
    for k in free:
        out.setdefault(k, 0.0)
    return out


def done_pending(rows: list, holdings: dict) -> dict:
    """What was marked Done today and the positions file does not show yet. rows = [{sym, side, amount, qty_at_done}], holdings {sym: {qty, price}}.
    A buy is reflected by the file once the shares rose above qty_at_done (x price); a sell once they fell below it. Returns {sym: {"BUY": d, "SELL": d}}."""
    out: dict = {}
    for r in rows:
        sym = str(r.get("sym") or "").upper()
        side = r.get("side")
        if not sym or side not in ("BUY", "SELL"):
            continue
        h = holdings.get(sym) or {}
        qty, price = float(h.get("qty") or 0.0), float(h.get("price") or 0.0)
        q0 = float(r.get("qty_at_done") or 0.0)
        moved = (max(0.0, qty - q0) if side == "BUY" else max(0.0, q0 - qty)) * price
        pend = max(0.0, float(r.get("amount") or 0.0) - moved)
        d = out.setdefault(sym, {"BUY": 0.0, "SELL": 0.0})
        d[side] += pend
    return out


def sell_needs(plan: dict, now: dict, value: float) -> list:
    """Classes held above their plan %, in dollars. A class planned at 0 and still held = 'sell all'."""
    p = clean_plan(plan)
    out = []
    for c in CLASSES:
        if c == "Cash":
            continue
        held = now["cls"].get(c, 0.0)
        target = p["cls"][c] / 100.0 * value
        need = held - target
        if held > 0 and need > MIN_NEED:
            out.append({"cls": c, "plan_pct": p["cls"][c], "held": held, "need": need, "all": p["cls"][c] == 0})
    return out


def _line_rows(p: dict, value: float, now: dict, used: dict) -> list:
    """What is left per plan line (class always; sector / style / beta only when the user gave a number)."""
    rows = []
    for c in CLASSES:
        tgt = p["cls"][c] / 100.0 * value
        rows.append({"kind": "cls", "key": c, "plan": tgt, "plan_pct": p["cls"][c], "now": now["cls"].get(c, 0.0),
                     "used": used["cls"].get(c, 0.0), "required": True})
    for kind in ("sector", "style"):
        for k, v in p[kind].items():
            if v is None:
                continue
            rows.append({"kind": kind, "key": k, "plan": v / 100.0 * value, "plan_pct": v, "now": now[kind].get(k, 0.0),
                         "used": used[kind].get(k, 0.0), "required": False})
    for k in ("Q1", "Q2", "Q3", "Q4"):
        v = p["quad"][k]
        if v is not None:
            rows.append({"kind": "quad", "key": k, "label": k + " favored (Bull)", "plan": v / 100.0 * value, "plan_pct": v, "now": now["quad"].get(k, 0.0),
                         "used": used["quad"].get(k, 0.0), "required": False})
    for k in ("low", "high", "mid", "none"):
        v = p["beta"][k]
        if v is not None:
            rows.append({"kind": "beta", "key": k, "label": BETA_LABEL[k], "plan": v / 100.0 * value, "plan_pct": v, "now": now["beta"].get(k, 0.0),
                         "used": used["beta"].get(k, 0.0), "required": False})
    for r in rows:
        r["label"] = r.get("label") or ("No style tag" if (r["kind"] == "style" and r["key"] == "none") else r["key"])
        r["left"] = r["plan"] - r["now"] - r["used"]
    return rows


def todo(plan: dict, account: dict, picks: list, calls: dict, info: dict, style_groups: Optional[dict] = None,
         buy_side=lambda code: "neutral", caps: Optional[dict] = None, assume_sells: bool = False, warn_only: bool = False) -> dict:
    """The To do tab for one account.

    account = {value, cash, holdings {sym: {value, bucket, qty, price}}}
    picks   = [{id, side 'BUY'|'SELL', members [sym], amount, ticked}] in the order made
    calls   = {sym: Actionable final_code}; buy_side(code) -> 'buy' | 'sell' | 'neutral'
    caps    = {sym: {min, max, unit}} dollars from the existing amount rules (drv_account_size); optional.
    assume_sells = (2026-11-19, read-only To do list) count the excess of every class above its plan as sold: no ticks needed.
    warn_only    = a buy is never cut or blocked for lack of cash: the planned amount stands and the result says it is over.

    A planned buy counts as soon as it has an amount (a Buy call is NOT needed: this is planning). Each buy also reports
    max_add (the most that still fits: the smallest room among its class, sector, styles, beta, the cash and the stock's own
    Max), binding (which one is tightest) and suggest (the amount rules' starting size capped at max_add).
    """
    caps = caps or {}
    p = clean_plan(plan)
    style_groups = style_groups or {}
    value = float(account.get("value") or 0.0)
    cash = float(account.get("cash") or 0.0)
    holdings = account.get("holdings") or {}
    now = now_lines(holdings, info, cash, style_groups)

    # ---- sells: holdings in classes above the plan, ticked ones free up cash in THIS account only
    ticked_sell = {}
    for pk in picks:
        if pk["side"] == "SELL" and pk.get("ticked"):
            for s in pk["members"]:
                ticked_sell[s] = pk
    needs = sell_needs(p, now, value)
    sells = []
    sell_cash = 0.0
    sold_by_cls = {}
    for n in needs:
        rows = []
        tot = 0.0
        for sym, h in sorted(holdings.items(), key=lambda kv: -float(kv[1].get("value") or 0)):
            if h.get("bucket") != n["cls"] or float(h.get("value") or 0) <= 0:
                continue
            on = sym in ticked_sell
            v = float(h["value"])
            if on:
                tot += v
            rows.append({"sym": sym, "value": v, "qty": float(h.get("qty") or 0.0) or None, "call": calls.get(sym), "side": buy_side(calls.get(sym)), "ticked": on,
                         "pick_id": ticked_sell[sym]["id"] if on else None})
        if assume_sells:
            amt = p["sell"].get(n["cls"])
            amt = n["need"] if amt is None else min(amt, sum(r["value"] for r in rows))
            split = alloc_sell({r["sym"]: r["value"] for r in rows}, amt, p["sell_hold"])
            for r in rows:
                hh = holdings.get(r["sym"]) or {}
                r["sell"] = split.get(r["sym"], 0.0)
                q = float(hh.get("qty") or 0.0)
                r["shares"] = round(q * r["sell"] / r["value"], 1) if q and r["value"] else None
            tot = sum(split.values())
            n = dict(n, amount=amt, default=n["need"])
        sell_cash += tot
        sold_by_cls[n["cls"]] = tot
        sells.append(dict(n, holdings=rows, ticked_total=tot, left=max(0.0, n["need"] - tot)))

    # ---- what each line looks like after the ticked sells
    now_after = {"cls": dict(now["cls"]), "sector": dict(now["sector"]), "style": dict(now["style"]), "beta": dict(now["beta"]), "quad": dict(now["quad"])}
    for sym in ticked_sell:
        h = holdings.get(sym)
        if not h:
            continue
        v = float(h.get("value") or 0.0)
        ln = _lines_of(sym, h.get("bucket"), info, style_groups)
        if ln["cls"]:
            now_after["cls"][ln["cls"]] = now_after["cls"].get(ln["cls"], 0.0) - v
        if ln["sector"]:
            now_after["sector"][ln["sector"]] = now_after["sector"].get(ln["sector"], 0.0) - v
        for k in ln["style"]:
            now_after["style"][k] = now_after["style"].get(k, 0.0) - v
        if ln["beta"]:
            now_after["beta"][ln["beta"]] = now_after["beta"].get(ln["beta"], 0.0) - v
        for k in ln["quad"]:
            now_after["quad"][k] = now_after["quad"].get(k, 0.0) - v
    if assume_sells:                                  # class level: the sold dollars leave their class
        for c, v in sold_by_cls.items():
            now_after["cls"][c] = now_after["cls"].get(c, 0.0) - v
    now_after["cls"]["Cash"] = cash + sell_cash

    # ---- buys, walked in the order made. Money limits block / shrink; % lines only warn.
    spend0 = cash_to_spend(cash, sell_cash, value, p)
    left_cash = spend0
    used = {"cls": {}, "sector": {}, "style": {}, "beta": {}, "quad": {}}
    buys = []
    for pk in picks:
        if pk["side"] != "BUY":
            continue
        members = list(pk["members"])
        ask = float(pk.get("amount") or 0.0)
        by_member = {s: calls.get(s) for s in members}
        buyers = [s for s in members if buy_side(calls.get(s)) == "buy"]
        cand = buyers or members
        item = {"id": pk["id"], "members": members, "kind": "one" if len(members) > 1 else "single", "amount": ask,
                "ticked": bool(pk.get("ticked")), "calls": by_member, "buy_member": buyers[0] if buyers else None,
                "buyers": buyers, "has_call": bool(buyers), "allowed": 0.0, "result": "WAITING", "why": "", "over": [],
                "max_add": None, "binding": None, "suggest": None}
        if ask <= 0:
            item["result"] = "READY" if buyers else "WAITING"
            item["why"] = "Has a Buy call. Set an amount to count it." if buyers else "Set an amount to count it."
            buys.append(item)
            continue
        # which stock the amount counts against: the member with the least room in its class (cautious)
        pick_sym = cand[0]
        if len(cand) > 1:
            def _room(sym):
                ln = _lines_of(sym, (holdings.get(sym) or {}).get("bucket"), info, style_groups)
                c = ln["cls"]
                return (p["cls"].get(c, 0.0) / 100.0 * value - now_after["cls"].get(c, 0.0) - used["cls"].get(c, 0.0)) if c else 0.0
            pick_sym = min(cand, key=_room)
        item["count_sym"] = pick_sym
        if buyers:
            item["buy_member"] = pick_sym
        ln = _lines_of(pick_sym, (holdings.get(pick_sym) or {}).get("bucket"), info, style_groups)
        # ---- the most that still fits, and which limit is the tightest
        rooms = [("Cash to spend", left_cash)]
        def _rm(kind, key, pct, label=None):
            if key and pct is not None:
                rooms.append((label or key, pct / 100.0 * value - now_after[kind].get(key, 0.0) - used[kind].get(key, 0.0)))
        _rm("cls", ln["cls"], p["cls"].get(ln["cls"]) if ln["cls"] else None)
        _rm("sector", ln["sector"], p["sector"].get(ln["sector"]) if ln["sector"] else None)
        for k in ln["style"]:
            _rm("style", k, p["style"].get(k))
        _rm("beta", ln["beta"], p["beta"].get(ln["beta"]) if ln["beta"] else None,
            BETA_LABEL[ln["beta"]] if ln["beta"] else None)
        for k in ln["quad"]:
            _rm("quad", k, p["quad"].get(k), k + " favored (Bull)")
        cap = caps.get(pick_sym) or {}
        held_v = float((holdings.get(pick_sym) or {}).get("value") or 0.0)
        stock_room = None
        _mx, _mine = eff_max(cap, p["my_max"].get(pick_sym))
        if _mx is not None:
            stock_room = _mx - held_v
            rooms.append(("Your ceiling" if _mine else "The stock's own Max", stock_room))
        tight = min(rooms, key=lambda x: x[1])
        item["max_add"] = max(0.0, float(int(max(tight[1], 0.0) // 100) * 100))
        item["binding"] = tight[0]
        if cap:
            start = cap.get("unit") if held_v > 0 else cap.get("min")
            if start:
                item["suggest"] = min(float(start), item["max_add"])
        allowed = ask if warn_only else min(ask, left_cash)
        allowed = float(int(allowed // 100) * 100) if allowed >= 100 else 0.0
        item["allowed"] = allowed
        if warn_only and allowed > left_cash + 0.5:
            item["result"] = "OVER_PLAN"
            item["why"] = "More than the cash that can be spent here by $%s (warning only)." % format(int(allowed - max(left_cash, 0.0)), ",")
        elif allowed <= 0:
            item["result"] = "BLOCKED"
            item["why"] = "No cash left to spend in this account. Tick a sell, lower another pick, or change the plan."
        elif allowed < ask:
            item["result"] = "SHRUNK"
            item["why"] = "Cut from $%s to $%s: this account can spend only $%s." % (format(int(ask), ","), format(int(allowed), ","), format(int(left_cash), ","))
        else:
            item["result"] = "OK"
            if not buyers:
                item["why"] = "Planned. No Buy call today."
        left_cash -= allowed
        over = []
        def _touch(kind, key, plan_pct):
            if not key:
                return
            used[kind][key] = used[kind].get(key, 0.0) + allowed
            if plan_pct is None:
                return
            tgt = plan_pct / 100.0 * value
            lft = tgt - now_after[kind].get(key, 0.0) - used[kind][key] + allowed   # room before this pick
            if allowed > lft:
                over.append({"line": key, "over": allowed - max(lft, 0.0), "fits": max(lft, 0.0)})
        _touch("cls", ln["cls"], p["cls"].get(ln["cls"]) if ln["cls"] else None)
        _touch("sector", ln["sector"], p["sector"].get(ln["sector"]) if ln["sector"] else None)
        for k in ln["style"]:
            _touch("style", k, p["style"].get(k))
        _touch("beta", ln["beta"], p["beta"].get(ln["beta"]) if ln["beta"] else None)
        for k in ln["quad"]:
            _touch("quad", k, p["quad"].get(k))
        if stock_room is not None and allowed > stock_room:
            over.append({"line": "The stock's own Max", "over": allowed - max(stock_room, 0.0), "fits": max(stock_room, 0.0)})
        item["over"] = over
        if over and item["result"] == "OK":
            item["result"] = "OVER_PLAN"
            o = max(over, key=lambda x: x["over"])
            item["why"] = "%s is $%s over plan. $%s fits." % (o["line"], format(int(o["over"]), ","), format(int(o["fits"]), ","))
        elif over:
            o = max(over, key=lambda x: x["over"])
            item["why"] += " Also over plan: %s by $%s." % (o["line"], format(int(o["over"]), ","))
        buys.append(item)

    # ---- the "what is left" lines
    bought = sum(b["allowed"] for b in buys)
    now_after["cls"]["Cash"] = cash + sell_cash - bought
    rows = _line_rows(p, value, now_after, used)
    for r in rows:
        if r["kind"] == "cls" and r["key"] == "Cash":
            r["used"] = 0.0
            r["left"] = r["now"] - r["plan"]          # cash above the plan's Cash % (can be spent)
        r["state"] = line_state(r, value)
    notes = []
    for r in rows:
        if r["kind"] != "cls" and r["left"] < -tolerance(value):      # inside the on-plan band (rounding of a limit taken from holdings) is not "over"
            notes.append("%s is $%s over its plan." % (r["label"], format(int(-r["left"]), ",")))
        elif r["kind"] == "cls" and r["key"] not in ("Cash",) and r["left"] < -max(MIN_NEED, tolerance(value)) and r["used"] > 0:
            notes.append("%s is $%s over its plan." % (r["label"], format(int(-r["left"]), ",")))
    if now["cls"].get("Unmapped", 0) > MIN_NEED:
        notes.append("$%s of holdings have no asset class, so no plan line covers them." % format(int(now["cls"]["Unmapped"]), ","))
    return {"value": value, "cash": cash, "cash_keep": p["cash_keep"], "cash_to_spend": spend0, "cash_left": left_cash,
            "sell_cash": sell_cash, "bought": bought, "sells": sells, "buys": buys, "lines": rows, "notes": notes,
            "now": now, "now_after": now_after}


def cash_summary(plan: dict, account: dict, info: dict, style_groups: Optional[dict] = None) -> dict:
    """The money behind Max $: real cash, sale money assumed from asset classes over their target, and what may be spent
    (cash floor and the plan's Cash % applied). Dollars, one set per account."""
    p = clean_plan(plan)
    value = float(account.get("value") or 0.0)
    cash = float(account.get("cash") or 0.0)
    now = now_lines(account.get("holdings") or {}, info, cash, style_groups or {})
    sells = sum(n["need"] for n in sell_needs(p, now, value))
    return {"cash": cash, "sells": sells, "keep": p["cash_keep"], "spendable": cash_to_spend(cash, sells, value, p)}


def room_for(plan: dict, account: dict, cands: list, info: dict, style_groups: Optional[dict] = None,
             caps: Optional[dict] = None, buyers: Optional[set] = None, default_cap: Optional[dict] = None) -> dict:
    """Max $ per stock for the Builder picks grids (2026-11-17). WARN-ONLY: nothing here blocks anything.

    account = {value, cash, holdings {sym: {value, bucket}}}
    cands   = [{sym, bucket, amt, pick}] in the order made. amt = dollars already typed (0 = none), pick = ticked as a pick.
    buyers  = symbols with a Buy call in Actionable (these are served first; a Buy call is NOT needed to get a starting amount).

    default_cap = the account's usual per-stock rule {min, max, unit}: an Equities name (ETFs count as equities) with no rule of
                its own uses it. Other classes without a rule have no per-stock limit.

    Returns {sym: {stock, bucket, max, binding, bucket_binding, start}}:
      stock   = the most this ONE stock can still be bought (its Max rule minus what is held; None = no per-stock rule).
      bucket  = the room left in the buckets it falls in, counting every OTHER planned buy: smallest of cash to spend, class,
                sector, styles, beta, Quad (rounded down to $100, never below 0).
      max     = the smaller of the two; binding = which limit is tightest overall; bucket_binding = the tightest bucket.
      sells   = dollars of over-target asset classes assumed sold and counted as cash to spend (same for every stock).
      start   = the default Buy $ for a pick with no amount: picks are walked (Buy-call stocks first, then the order made) and each
                takes what still fits after the ones before it (first come, first served). None for stocks that are not picks and for stocks already held.
    """
    caps = caps or {}
    p = clean_plan(plan)
    sg = style_groups or {}
    value = float(account.get("value") or 0.0)
    cash = float(account.get("cash") or 0.0)
    holdings = account.get("holdings") or {}
    now = now_lines(holdings, info, cash, sg)
    # 2026-11-17, user: count selling whatever sits above its asset class target as cash you can spend (class level only: which stocks
    # would be sold is not known, so sector / style / beta room is left as it is). Cash floor and the plan's Cash % still apply.
    summ = cash_summary(plan, account, info, sg)
    sell_cash = summ["sells"]
    cash0 = summ["spendable"]
    used = {"cls": {}, "sector": {}, "style": {}, "beta": {}, "quad": {}}
    lines = {}
    mine_flag = {}
    rule_max = {}

    def _ln(c):
        sym = c["sym"]
        if sym not in lines:
            lines[sym] = _lines_of(sym, c.get("bucket") or (holdings.get(sym) or {}).get("bucket"), info, sg)
        return lines[sym]

    def _touch(ln, amt):
        for kind, key in (("cls", ln["cls"]), ("sector", ln["sector"]), ("beta", ln["beta"])):
            if key:
                used[kind][key] = used[kind].get(key, 0.0) + amt
        for k in ln["style"]:
            used["style"][k] = used["style"].get(k, 0.0) + amt
        for k in ln["quad"]:
            used["quad"][k] = used["quad"].get(k, 0.0) + amt

    def _room(c, left_cash):
        ln = _ln(c)
        rooms = [("Cash to spend", left_cash)]

        def _rm(kind, key, pct, label=None):
            if key and pct is not None:
                rooms.append((label or key, pct / 100.0 * value - now[kind].get(key, 0.0) - used[kind].get(key, 0.0)))
        _rm("cls", ln["cls"], p["cls"].get(ln["cls"]) if ln["cls"] else None)
        _rm("sector", ln["sector"], p["sector"].get(ln["sector"]) if ln["sector"] else None)
        for k in ln["style"]:
            _rm("style", k, p["style"].get(k))
        _rm("beta", ln["beta"], p["beta"].get(ln["beta"]) if ln["beta"] else None, BETA_LABEL[ln["beta"]] if ln["beta"] else None)
        for k in ln["quad"]:
            _rm("quad", k, p["quad"].get(k), k + " favored (Bull)")
        tight = min(rooms, key=lambda x: x[1])
        bucket = max(0.0, float(int(max(tight[1], 0.0) // 100) * 100))
        cap = caps.get(c["sym"]) or ((default_cap or {}) if ln["cls"] == "Equities" else {})
        stock = None
        _mx, _mine = eff_max(cap, p["my_max"].get(c["sym"]))
        if _mx is not None:
            stock = max(0.0, float(int(max(_mx - float((holdings.get(c["sym"]) or {}).get("value") or 0.0), 0.0) // 100) * 100))
        mine_flag[c["sym"]] = _mine
        rule_max[c["sym"]] = cap.get("max")
        return stock, bucket, tight[0]

    typed = {c["sym"]: float(c.get("amt") or 0.0) for c in cands}
    for c in cands:
        if typed[c["sym"]] > 0:
            _touch(_ln(c), typed[c["sym"]])
    spent = sum(typed.values())
    out = {}
    for c in cands:                                   # ceiling for each stock alone: take its own typed amount back out first
        own = typed[c["sym"]]
        if own > 0:
            _touch(_ln(c), -own)
        stk, bkt, bb = _room(c, cash0 - spent + own)
        if own > 0:
            _touch(_ln(c), own)
        m = bkt if stk is None else min(stk, bkt)
        b = ("Your ceiling" if mine_flag.get(c["sym"]) else "The stock's own Max") if (stk is not None and stk < bkt) else bb
        out[c["sym"]] = {"stock": stk, "bucket": bkt, "max": m, "binding": b, "bucket_binding": bb, "start": None, "sells": round(sell_cash), "rule_max": rule_max.get(c["sym"])}
    left = cash0 - spent
    # starting amounts: every pick without an amount (this is planning: a Buy call is not needed today), first come first served.
    # Stocks with a Buy call in Actionable now go first; the rest follow in the order picked.
    order = [c for c in cands if buyers and c["sym"] in buyers] + [c for c in cands if not (buyers and c["sym"] in buyers)]
    for c in order:
        held_v = float((holdings.get(c["sym"]) or {}).get("value") or 0.0)
        if c.get("pick") and typed[c["sym"]] <= 0 and held_v <= 0:      # stocks you already hold keep their Max $ but get no starting amount: new picks come first
            stk, bkt, _bb = _room(c, left)
            m = bkt if stk is None else min(stk, bkt)
            out[c["sym"]]["start"] = m
            if m > 0:
                _touch(_ln(c), m)
                left -= m
    return out
