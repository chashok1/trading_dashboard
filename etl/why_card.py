"""Plain-English "Why this action" card for the Actionable Action popup.

2026-10-20, user-directed: a short decision trail -- Sources, Technical, Position, Rules -- that ends in ONE plain sentence for
the Final Call and, when there is no buy/sell signal, what would change it. Built once at derive time
(etl/derive_actionable.py -> drv_actionable.why_card JSONB) so the popup, the Gate hover and the grid all read the same text.

Pure function: build_why_card(ctx) takes already-derived facts and returns a JSON-able dict:

    {"verdict": "HOLD", "side": "neutral",
     "steps": [{"key", "title", "tone": buy|sell|warn|neutral, "text", "lines": [{"ok": True|False|None, "text"}]}],
     "result": "one plain sentence",
     "flip": ["BUY MORE if ...: still needs ...", ...]}

ctx keys (all optional): consolidated, winning_source, sources [{source, action, reason}], rr_action, trail (technical_trail output),
held_today, held_dollar, target_max, stop_breached, stop_signal, suppressed, fc (dict from _compute_final_call incl. fc_reason),
trig_action, groups [{rule_group_code, action}], low_confidence.
"""
from __future__ import annotations

from typing import Optional

_BUY = {"INCREASE", "BS", "BM", "ADD", "BMN"}
_SELL = {"REMOVE", "SA", "REDUCE", "SS", "STM", "SO"}
_NAME = {
    "INCREASE": "INCREASE", "ADD": "ADD", "REMOVE": "REMOVE", "REDUCE": "REDUCE", "HOLD": "HOLD",
    "BS": "BUY SOME", "BM": "BUY MORE", "BMN": "BUY TO MIN", "SS": "SELL SOME", "STM": "SELL TO MIN", "SA": "SELL ALL", "SO": "SELL OVER",
}


def _up(a) -> str:
    return str(a or "").strip().upper()


def _side(a) -> str:
    u = _up(a)
    return "buy" if u in _BUY else ("sell" if u in _SELL else "neutral")


def _name(a) -> str:
    u = _up(a)
    return _NAME.get(u, u or "none")


def _usd(v) -> str:
    try:
        return "${:,.0f}".format(float(v))
    except (TypeError, ValueError):
        return "?"


def _md(d) -> str:
    """'2026-10-14' -> '10/14' (empty if missing)."""
    p = str(d or "")[:10].split("-")
    return f"{p[1]}/{p[2]}" if len(p) == 3 else ""


def _sources_step(ctx: dict) -> dict:
    all_srcs = list(ctx.get("sources") or [])
    warn = [x for x in all_srcs if x.get("warning_only")]   # SSS weight fell: shown, never counted
    srcs = [x for x in all_srcs if not x.get("warning_only")]
    win = str(ctx.get("winning_source") or "")
    wlines = [{"ok": None, "warn": True, "text": f"Warning only - SSS weight fell{' on ' + _md(w.get('snapshot_date')) if _md(w.get('snapshot_date')) else ''}: {str(w.get('reason') or '').strip()}"} for w in warn]
    if not srcs:
        return {"key": "sources", "title": "Sources", "tone": "warn" if warn else "neutral",
                "text": "No source (SSS, CALL, Top-5, RR ...) is recommending anything for this stock.", "lines": wlines}
    # 2026-10-21, user: newest first (an RTA today goes on top); on the same date the winning source leads. Undated sources go last.
    srcs.sort(key=lambda s: (str(s.get("snapshot_date") or "")[:10], 1 if str(s.get("source") or "") == win else 0), reverse=True)
    buys = sum(1 for s in srcs if _side(s.get("action")) == "buy")
    sells = sum(1 for s in srcs if _side(s.get("action")) == "sell")
    if buys and sells:
        tone, head = "warn", f"Mixed: {buys} lean buy, {sells} lean sell"
    elif buys:
        tone, head = "buy", "Lean BUY" + (f" ({buys} sources agree)" if buys > 1 else "")
    elif sells:
        tone, head = "sell", "Lean SELL" + (f" ({sells} sources agree)" if sells > 1 else "")
    else:
        tone, head = "neutral", "Neutral"
    # Mirrors the popup driver rows (actionable_pops.js): the winning source did not drive the Final Call when a breached stop
    # turned it into HOLD, or when it points the other way and Technical is what matches the Final Call.
    fc_side = (ctx.get("fc") or {}).get("final_side") or _side(ctx.get("consolidated"))
    win_side = next((_side(s.get("action")) for s in srcs if str(s.get("source") or "") == win), None)
    tech_overrides = bool(win_side and fc_side != "neutral" and win_side != fc_side and _side(ctx.get("rr_action")) == fc_side)
    win_drove = not ctx.get("stop_breached") and not tech_overrides
    lines = []
    for s in srcs:
        is_win = str(s.get("source") or "") == win
        # 2026-10-21, user: every other source is labeled by how it relates to the Final Call -- supports / opposes (not "not counted",
        # which only ever fits the warning-only lines). When the call is HOLD the winning source's side is the reference.
        ref_side = fc_side if fc_side != "neutral" else win_side
        rel = _side(s.get("action"))
        # ok drives the tick / cross the card draws: supports (and the source that drove it) = tick, opposes = cross.
        if win_drove and is_win:
            tag, ok = " (drove it)", True
        elif rel != "neutral" and ref_side in ("buy", "sell"):
            tag, ok = (" (supports)", True) if rel == ref_side else (" (opposes)", False)
        else:
            tag, ok = "", None
        reason = str(s.get("reason") or "").strip()
        when = _md(s.get("snapshot_date"))
        lines.append({"ok": ok, "text": f"{s.get('source')} {_name(s.get('action'))}{tag}" + (f" ({when})" if when else "") + (f": {reason}" if reason else "")})
    # "ref" = the side the ticks/crosses are measured against (the Final Call's side, or the winning source's when the call is HOLD); the card
    # colours a tick like that side and a cross like the other one.
    ref = fc_side if fc_side != "neutral" else win_side
    # 2026-10-21, user: the per-source rows live in the driver list right below the card, so the card keeps ONE summary line (counts + who drove
    # it) and only the warning-only lines, which the driver list does not show.
    if win and win_drove:
        head += f" - {win} drove it"
    elif win and tech_overrides:
        head += f" - Technical overrode {win}"
    elif win and ctx.get("stop_breached"):
        head += f" - the breached stop overrode {win}"
    return {"key": "sources", "title": "Sources", "tone": tone, "text": head, "ref": ref, "lines": wlines}


def _technical_step(ctx: dict) -> dict:
    rr = ctx.get("rr_action")
    trail = ctx.get("trail") or {}
    stages = trail.get("stages") or []
    lines = [{"ok": st.get("ok"), "text": f"{st.get('name')}: {st.get('text')}", **({"warn": True} if st.get("warn") else {})} for st in stages]
    if rr:
        tone = _side(rr)
        head = f"{_name(rr)}"
    else:
        tone, head = "neutral", "No signal"
    if not stages and not rr:
        head = "No Technical read for this stock"
    return {"key": "technical", "title": "Technical", "tone": tone, "text": head, "lines": lines}


def _position_step(ctx: dict) -> dict:
    held = bool(ctx.get("held_today"))
    dollar = ctx.get("held_dollar")
    lines = [{"ok": None, "text": (f"You have a position: {_usd(dollar)}" if held else "No position ($0)")}]
    tone = "neutral"
    if ctx.get("stop_breached"):
        tone = "warn"
        lines.append({"ok": False, "text": f"Stop breached ({ctx.get('stop_signal') or 'stop'}): a buy/add is downgraded to HOLD"})
    elif ctx.get("stop_signal"):
        lines.append({"ok": None, "text": f"Stop signal: {ctx.get('stop_signal')}"})
    tmax = ctx.get("target_max")
    try:
        if held and tmax and float(dollar or 0) >= float(tmax):
            lines.append({"ok": None, "text": f"At or over your Max ({_usd(dollar)} of {_usd(tmax)}) - shown as OVER MAX, does not change the call"})
    except (TypeError, ValueError):
        pass
    if ctx.get("suppressed"):
        lines.append({"ok": None, "text": f"Suppressed: {ctx.get('suppressed')}"})
    return {"key": "position", "title": "Position", "tone": tone, "text": lines[0]["text"], "lines": lines[1:]}


def _rules_step(ctx: dict) -> dict:
    groups = list(ctx.get("groups") or [])
    buys = [g for g in groups if str(g.get("action") or "").upper().startswith("B")]
    sells = [g for g in groups if str(g.get("action") or "").upper().startswith("S")]
    if not groups:
        return {"key": "rules", "title": "Rules", "tone": "neutral", "text": "No rule group fired", "lines": []}
    if buys and sells:
        tone = "warn"
    elif buys:
        tone = "buy"
    elif sells:
        tone = "sell"
    else:
        tone = "neutral"
    bits = []
    if buys:
        bits.append(f"{len(buys)} buy group{'s' if len(buys) != 1 else ''}")
    if sells:
        bits.append(f"{len(sells)} sell group{'s' if len(sells) != 1 else ''}")
    head = ", ".join(bits) + (" - mixed" if buys and sells else "")
    lines = []
    if ctx.get("trig_action"):
        lines.append({"ok": None, "text": f"Rules engine Trig action: {_name(ctx.get('trig_action'))}"})
    if ctx.get("low_confidence"):
        lines.append({"ok": None, "text": "Low confidence: the only sell-side evidence comes from rules without a proven track record"})
    return {"key": "rules", "title": "Rules", "tone": tone, "text": head, "lines": lines}


_RESULT = {
    "no_rec": "No source is recommending anything for this stock, so there is nothing to act on.",
    "stop_breach": "You have a position in it and it is below its stop, so the buy/add the sources want is downgraded to HOLD.",
    "exit_not_held": "The sources say exit, but you have no position in it - nothing to sell.",
    "exit_held": "The sources say exit and you have a position in it - SELL ALL. Technical is shown for context but does not decide an exit.",
    "dont_initiate": "You have no position in it and the sources are not recommending a buy, so there is nothing to start.",
    "bypass_rta": "A real-time alert is itself a live trigger, so it does not need Technical to confirm - the buy goes through.",
    "tech_sell_not_held": "Technical says sell, but you have no position in it - nothing to sell, so HOLD.",
    "tech_sell_reduce": "The sources and Technical both point to selling - the sell goes through.",
    "tech_sell_other": "Technical says sell and overrides the sources' buy, so the call is a sell (lower confidence because they disagree).",
    "tech_buy_reduce": "The sources say reduce but Technical says buy - they conflict, so HOLD.",
    "tech_buy_new_add": "The sources say add and Technical confirms - a new position is allowed (BUY TO MIN).",
    "tech_buy": "The sources lean buy and Technical confirms - the buy goes through.",
    "tech_neutral_reduce": "The sources say reduce but Technical has no sell signal - not enough to sell, so HOLD.",
}


def _result_sentence(ctx: dict, reason: str) -> str:
    held = bool(ctx.get("held_today"))
    if reason == "tech_neutral_hold":
        if not held:
            return "The sources like it, but a NEW position needs Technical to confirm, and Technical has no signal - so HOLD."
        return "You already have a position and the sources lean buy, but Technical has no confirmation to add more - so HOLD."
    return _RESULT.get(reason, "")


def _flip_lines(ctx: dict, reason: str) -> list:
    out: list = []
    trail = ctx.get("trail") or {}
    if reason in ("tech_neutral_hold", "tech_neutral_reduce"):
        for f in (trail.get("flip") or [])[:2]:
            miss = "; ".join(f.get("missing") or [])
            out.append(f"{f.get('label')} if {f.get('name')}: still needs {miss}")
        if not out:
            if (trail.get("stages") or [{}])[0].get("ok") is None and trail.get("stages"):
                out.append("Technical needs price back above both the Trade and Trend lines to start giving buy signals")
            elif reason == "tech_neutral_hold":
                out.append("Technical needs to turn bullish (a buy setup on the risk range) before a new position opens")
    elif reason == "stop_breach":
        out.append("Price recovering back above its stop (or you reducing the position)")
    elif reason == "dont_initiate":
        out.append("A source (SSS, CALL, Top-5, RR ...) would have to recommend a buy")
    elif reason == "tech_buy_reduce":
        out.append("Sources moving from REDUCE to neutral or buy, or Technical turning neutral")
    return out


def build_why_card(ctx: dict) -> dict:
    fc = ctx.get("fc") or {}
    reason = str(fc.get("fc_reason") or "")
    pos = _position_step(ctx)
    # 2026-10-21, user: "You have a position: $X" is already in the popup header, so the Position step only appears when it adds something
    # (stop breached / stop signal / over Max / suppressed).
    steps = [_sources_step(ctx), _technical_step(ctx)] + ([pos] if pos["lines"] else []) + [_rules_step(ctx)]
    return {
        "verdict": fc.get("final_action") or "HOLD",
        "side": fc.get("final_side") or "neutral",
        "steps": steps,
        "result": _result_sentence(ctx, reason),
        "flip": _flip_lines(ctx, reason),
    }
