"""Plain-English Technical reason for a symbol's Technical signal (td_tn_bb_rr_action).

Follows the same decision order as etl/derive.py::_derive_trend_trade_rules_impl
(Pass 2):

    1. Trend/Trade read (trend_trade_rule QE):  bearish codes (-2, -1, 1) win outright;
       code 2 (between the lines) is neutral -> no signal; 3/4 are bullish -> continue.
       Code 1 with bounce_exempt (2026-10-21 bounce exception) also continues, with a warning line.
    2. Bollinger band streak (bb_rng_strk_rule QJ): a falling band is a warning only (2026-10-21: for buys too).
    3. Range position (QM bull path when QJ >= 2, QN not-bull path otherwise),
       with a broken LRR support (lrr_idx = -1) overriding both.

Pure function: takes a dict of the already-derived inputs, returns two lines
joined by a newline -- line 1 = the situation ("Why"), line 2 = the short
verdict. The popup (web/actionable.js::_actpopDriverBullets) shows them as
"Why <line 1>" / "Call <action>: <line 2>". None when there is no signal.
"""
from __future__ import annotations

from typing import Optional

NL = chr(10)
# Highlight markers, rendered by web/actionable.js::_whyHtml (red / green).
# Stripped to plain text anywhere the text can't carry markup.
R, G, E = "{r}", "{g}", "{/}"


def _n(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _usd(v) -> str:
    x = _n(v)
    return "?" if x is None else f"${x:,.2f}"


def _two(why: str, verdict: str) -> str:
    return why + NL + verdict


# bull path (QJ >= 2): bull_rr_rule codes
_BULL = {
    -1: "Down 1+ SD, below midpoint, low still above LRR: bearish in the bull zone",
    1:  "At midpoint, up/flat day",
    2:  "Down day, low at LRR, Trade line positive",
    3:  "Up day, low above LRR, below midpoint, MACD rising but MACDH not rising",
    4:  "Up day, low touched LRR, price at or below the midpoint",
    5:  "Down day, above midpoint",
    6:  "Up day, low above LRR, below midpoint, MACD rising and MACDH rising",
    7:  "Touched TRR zone, pulled back, still above midpoint, TRR rising",
}
# not-bull path (QJ 0..1): nbull_rr_rule codes
_NBULL = {
    -1: "At TRR (top of range), price above the midpoint",
    2:  "Up day, low above LRR, at/below midpoint, MACD rising but MACDH not rising",
    3:  "Down day, low at LRR, above Trade and Trend",
    4:  "Up day, low touched LRR, price at or below the midpoint",
    5:  "Up day, low above LRR, at/below midpoint, MACD rising and MACDH rising",
}


def _touch_clause(why: str, d: dict) -> str:
    """2026-10-22, user: say WHICH of price / the day's high (TRR) / the day's low (LRR) is in the end zone of the range,
    since "At TRR" / "low touched LRR" read the same whether the price is there now or only the high/low got there."""
    last, high, low = _n(d.get("last")), _n(d.get("high")), _n(d.get("low"))
    lrr, trr = _n(d.get("lrr")), _n(d.get("trr"))
    if None in (last, lrr, trr) or trr <= lrr:
        return ""
    rng = trr - lrr
    top_edge = trr - (_n(d.get("trr_zone")) or 0.20) * rng
    bot_edge = lrr + (_n(d.get("lrr_zone")) or 0.25) * rng
    parts = []
    if "TRR" in why and high is not None and high >= top_edge:
        parts.append(f"Price {_usd(last)} is in the top zone (TRR {_usd(trr)})" if last >= top_edge else
                     f"Only the day's high {_usd(high)} reached the top zone (TRR {_usd(trr)}); price {_usd(last)} is below it")
    if "LRR" in why and low is not None and low <= bot_edge:
        parts.append(f"Price {_usd(last)} is in the bottom zone (LRR {_usd(lrr)})" if last <= bot_edge else
                     f"Only the day's low {_usd(low)} reached the bottom zone (LRR {_usd(lrr)}); price {_usd(last)} is above it")
    return ". ".join(parts)


def _tol_txt(d: dict) -> str:
    """LRR-break depth in ATRs for the wording (ref_settings lrr_break_atr_mult; default 1.5)."""
    t = _n(d.get("lrr_tol"))
    return format(t if t else 1.5, "g")


def _below_trade_pct(d: dict) -> str:
    last, trade = _n(d.get("last")), _n(d.get("trade_line"))
    if last is None or trade is None or trade <= 0:
        return ""
    return f" ({(trade - last) / trade * 100:.0f}% below)"


def _bounce_grade(d: dict) -> str:
    """Grade of a bounce-exception buy: MACDH rising = momentum confirmed, else capped to a small buy."""
    mh = _n(d.get("macdh_dir"))
    return "momentum confirmed (MACDH rising)" if mh is not None and mh > 0 else "momentum not confirmed (MACDH not rising), so the buy is capped small"


def _bounce_note(d: dict) -> str:
    return (f"Price {_usd(d.get('last'))} is below Trade ({_usd(d.get('trade_line'))}){_below_trade_pct(d)}: sell skipped because "
            f"the stock closed up 2 days in a row, is above yesterday's high and LRR held; {_bounce_grade(d)}. "
            f"The sell returns on a down day, a fall back under yesterday's high or an LRR break")


def explain_technical(d: dict, bounce_note: bool = True) -> Optional[str]:
    """Why line + verdict line (newline-separated) for the Technical signal, or None.

    Keys used: trend_trade_rule, bb_rng_strk_rule, bb_desc, bull_rr_action,
    not_bull_rr_action, td_tn_bb_rr_action (None = no signal),
    lrr_idx_eff / lrr_idx_raw, last, low, lrr, trade_line, trend_line.
    """
    qe = _n(d.get("trend_trade_rule"))
    if _n(d.get("td_tn_bb_rr_action")) is None or qe is None:
        return None
    qe = int(qe)
    last, trade, trend = d.get("last"), d.get("trade_line"), d.get("trend_line")
    if d.get("reclaim_buy"):
        # 2026-10-21 reclaim buy (etl/derive.py Pass 2b): fill-only, low confidence.
        return _two(f"Price {_usd(last)} is back above a recent Trade line ({_usd(d.get('reclaim_line'))}, one of the last 3) after closing below it "
                    f"2 days ago, on an up day; Trade is well above Trend ({_usd(trend)}) and no other Technical setup matched",
                    "reclaim buy: BUY SOME, low confidence")

    # 1. Trend / Trade read
    if qe == -2:
        return _two(f"Price {_usd(last)} {R}below{E} Trade ({_usd(trade)}) and Trend ({_usd(trend)})",
                    "bearish, overrides all other checks")
    if qe == -1:
        return _two(f"Trade ({_usd(trade)}) {R}below{E} Trend ({_usd(trend)}), price {_usd(last)} "
                    f"above Trade by less than one typical daily move",
                    "bearish, overrides all other checks")
    exempt = qe == 1 and bool(d.get("bounce_exempt"))
    if qe == 1 and not exempt:
        return _two(f"Price {_usd(last)} {R}below{E} Trade ({_usd(trade)}) by more than half a "
                    f"typical daily move, above Trend ({_usd(trend)})",
                    "bearish, overrides range position")
    if qe == 2:
        return _two(f"Price {_usd(last)} above Trade ({_usd(trade)}), {R}below{E} Trend ({_usd(trend)})",
                    "neutral zone, no signal")

    # 2. Bollinger band streak
    qj = _n(d.get("bb_rng_strk_rule"))
    qj = 0 if qj is None else int(qj)
    # 2026-10-21, user: a falling band is a warning only -- no longer stops the range-position read.

    # 3. Range position
    # Effective break uses the latest price (live intraday / the close), not the
    # day's low; a low that broke but recovered counts as "touched LRR" (support held).
    eff = _n(d.get("lrr_idx_eff"))
    raw = _n(d.get("lrr_idx_raw"))
    if eff is None:
        eff = _n(d.get("lrr_idx"))
    if raw is None:
        raw = _n(d.get("lrr_idx"))
    if eff is not None and int(eff) == -1:
        return _two(f"Price {_usd(last)} {R}below{E} LRR ({_usd(d.get('lrr'))}) by more than "
                    f"{_tol_txt(d)} typical daily moves",
                    "broken support overrides bullish Trend, Trade and band")
    held = ""
    if raw is not None and int(raw) == -1:
        lrr_v, last_v = _n(d.get("lrr")), _n(last)
        if lrr_v is not None and last_v is not None and last_v < lrr_v:
            # Shallow dip: still under LRR, but by less than the break depth -- these
            # usually bounce (past-data check, 2026-10-14), so watch rather than sell.
            held = (f"Low {_usd(d.get('low'))} dipped below LRR ({_usd(d.get('lrr'))}) and price "
                    f"{_usd(last)} is still just under it (less than {_tol_txt(d)} typical "
                    f"daily moves): watch for a bounce or a deeper break. ")
        else:
            held = (f"Low {_usd(d.get('low'))} dipped below LRR ({_usd(d.get('lrr'))}) but price "
                    f"{_usd(last)} recovered: {G}support held{E}. ")
    if qj >= 2:
        q = _n(d.get("bull_rr_action"))
        why = _BULL.get(int(q)) if q is not None else None
    else:
        q = _n(d.get("not_bull_rr_action"))
        why = _NBULL.get(int(q)) if q is not None else None
    if why:
        _tc = _touch_clause(why, d)
        if _tc:
            why = why + ". " + _tc
    if exempt:
        return _two(f"{_bounce_note(d) + '. ' if bounce_note else ''}{held}{why or 'No range-position condition matched'}",
                    "bounce exception: below Trade but turning up")
    return _two(f"{held}{why or 'No range-position condition matched'}",
                "above Trade and Trend" + (", band falling (warning only)" if qj < 0 else ", band not bearish"))


# ---------------------------------------------------------------------------
# 2026-10-20: stage-by-stage trail of the Technical read + "what would change it" hints.
# Mirrors the same three stages as explain_technical() above and the bull-path setups in
# etl/derive.py::_derive_trend_trade_rules_impl (Pass 1 bull_rr_action CASE). Pure function.
# Used by etl/derive.py (stored as drv_tn_td_bb_rr.tech_trail) and read by etl/why_card.py.
# ---------------------------------------------------------------------------
def _day_word(perf: Optional[float]) -> str:
    if perf is None:
        return "day"
    return "up day" if perf > 0 else ("down day" if perf < 0 else "flat day")


def _bull_setups(d: dict) -> list:
    """Every bull-path buy setup as (action label, name, [(met, what it needs)]), in the same terms as the SQL CASE."""
    last, high = _n(d.get("last")), _n(d.get("high"))
    lrr, trr, prev_trr = _n(d.get("lrr")), _n(d.get("trr")), _n(d.get("prev_trr"))
    perf = _n(d.get("perf1d"))
    lrr_eff, mrr = _n(d.get("lrr_idx_eff")), _n(d.get("mrr_idx"))
    trr_idx = _n(d.get("trr_idx"))
    macd, macdh = _n(d.get("macd_dir")), _n(d.get("macdh_dir"))
    trade_rule = _n(d.get("trade_rule"))
    pb = _n(d.get("pullback")) or 0.10
    if None in (last, lrr, trr) or trr <= lrr:
        return []
    mid = (lrr + trr) / 2.0
    pbd = pb * (trr - lrr)
    up = perf is not None and perf > 0
    down = perf is not None and perf < 0
    return [
        ("BUY MORE", "bounce from the lower half (up day, MACD and MACDH rising)", [
            (up, "an up day"), (lrr_eff == 1, f"the day's low to stay above LRR ({_usd(lrr)})"),
            (mrr == -1, f"price below the range midpoint ({_usd(mid)}, now {_usd(last)})"),
            (macd is not None and macd > 0, "MACD rising"), (macdh is not None and macdh > 0, "MACDH rising")]),
        ("BUY SOME", "dip while still above the midpoint (moderate down day)", [
            (perf == -1, "a moderate down day (not a big drop)"), (mrr == 1, f"price above the range midpoint ({_usd(mid)}, now {_usd(last)})")]),
        ("BUY SOME", "bounce off LRR (up day, low touched LRR)", [
            (up, "an up day"), (lrr_eff == 0, f"the day's low to touch LRR ({_usd(lrr)})"),
            (last <= mid, f"price at or below the range midpoint ({_usd(mid)}, now {_usd(last)})")]),
        ("BUY TO MIN", "up day below the midpoint (MACD rising, MACDH not)", [
            (up, "an up day"), (lrr_eff == 1, f"the day's low to stay above LRR ({_usd(lrr)})"),
            (mrr == -1, f"price below the range midpoint ({_usd(mid)}, now {_usd(last)})"),
            (macd is not None and macd > 0, "MACD rising"), (macdh is not None and macdh < 0, "MACDH falling")]),
        ("BUY TO MIN", "down day at LRR with the Trade line positive", [
            (down, "a down day"), (lrr_eff == 0, f"the day's low to touch LRR ({_usd(lrr)})"),
            (trade_rule is not None and trade_rule > 0, "price above the Trade line")]),
        ("BUY MORE", "pullback from the top zone (down day, still above the midpoint, TRR rising)", [
            (trr_idx is not None and trr_idx >= 0, "the day's high to reach the top zone"), (down, "a down day"),
            (high is not None and high > last and high - last >= pbd, f"a pullback of at least {_usd(pbd)} from the day's high"),
            (last > mid, f"price still above the range midpoint ({_usd(mid)}, now {_usd(last)})"),
            (prev_trr is not None and trr > prev_trr, "TRR higher than the day before")]),
        ("BUY TO MIN", "price at the midpoint on an up or flat day", [
            (perf is not None and perf >= 0, "an up or flat day"), (mrr == 0, f"price in the midpoint zone (about {_usd(mid)})")]),
    ]


def _bb_falling_txt(d: dict) -> str:
    """2026-10-21, user: '' unless the TOP or the BOTTOM Bollinger band is falling (score <= -bb_lo, default 2; the same
    +/-2.0 cut the TOS Score study colors red), else which band(s). Warning only -- never changes the signal."""
    lo = _n(d.get("bb_lo")) or 2.0
    top, bot = _n(d.get("bb_top_slope")), _n(d.get("bb_bot_slope"))
    parts = []
    if top is not None and top <= -lo:
        parts.append(f"top band {format(top, 'g')}")
    if bot is not None and bot <= -lo:
        parts.append(f"bottom band {format(bot, 'g')}")
    return ", ".join(parts)


def technical_trail(d: dict) -> dict:
    """Same as _technical_trail_core, plus a warning-only 'Bollinger bands' line when the top or bottom band is falling."""
    out = _technical_trail_core(d)
    fall = _bb_falling_txt(d)
    if fall:
        msg = f"A band is falling ({fall}): warning only, not counted as a sell"
        bb_st = next((s for s in out["stages"] if s.get("name") == "Bollinger bands"), None)
        if bb_st is None:
            out["stages"].append({"name": "Bollinger bands", "ok": None, "warn": True, "text": msg})
        elif not bb_st.get("warn"):
            bb_st.update({"warn": True, "text": bb_st["text"] + "; " + msg})
    return out


def _technical_trail_core(d: dict) -> dict:
    """{'signal': bool, 'stages': [{'name', 'ok': True|False|None, 'text'}], 'flip': [{'label','name','missing':[...]}]}.

    Stages: 1 Trend & Trade, 2 Bollinger bands, 3 Range position. ok=None means neutral / not evaluated.
    `flip` is only filled when stages 1 and 2 are bullish and no signal came out: the closest buy setups and what each one lacks.
    """
    signal = _n(d.get("td_tn_bb_rr_action")) is not None
    qe, qj = _n(d.get("trend_trade_rule")), _n(d.get("bb_rng_strk_rule"))
    last, trade, trend = d.get("last"), d.get("trade_line"), d.get("trend_line")
    stages: list = []
    out = {"signal": signal, "stages": stages, "flip": []}
    if qe is None:
        stages.append({"name": "Trend & Trade", "ok": None, "text": "No Trend/Trade data for this stock"})
        return out
    qe = int(qe)
    if qe in (3, 4):
        ext = " and extended (more than 2 daily SDs away)" if qe == 4 else ""
        stages.append({"name": "Trend & Trade", "ok": True,
                       "text": f"Price {_usd(last)} is above Trade ({_usd(trade)}) and Trend ({_usd(trend)}){ext}"})
    elif qe == 1 and d.get("bounce_exempt"):
        stages.append({"name": "Trend & Trade", "ok": None, "warn": True, "text": "⚠ " + _bounce_note(d)})
    elif qe == 2:
        stages.append({"name": "Trend & Trade", "ok": None,
                       "text": f"Price {_usd(last)} is above Trade ({_usd(trade)}) but below Trend ({_usd(trend)}): neutral zone, no signal"})
        return out
    else:
        stages.append({"name": "Trend & Trade", "ok": False,
                       "text": f"Price {_usd(last)} is below Trade ({_usd(trade)}) / Trend ({_usd(trend)}): bearish, overrides everything else"})
        return out
    qj = 0 if qj is None else int(qj)
    bb = d.get("bb_desc") or ""
    bb_txt = (" (" + bb + ")") if bb else ""
    if qj >= 2:
        stages.append({"name": "Bollinger bands", "ok": True, "text": "Bands are rising" + bb_txt})
    elif qj >= 0:
        stages.append({"name": "Bollinger bands", "ok": None, "text": "Bands are not rising enough to call it bullish"})
    else:
        # 2026-10-20: a falling band is a warning only (no sell on its own); see etl/derive.py Pass 2.
        stages.append({"name": "Bollinger bands", "ok": None, "warn": True,
                       "text": "Bands are falling" + bb_txt + ": warning only, not counted as a sell or a block on buys"})
    lrr, trr, last_n = _n(d.get("lrr")), _n(d.get("trr")), _n(last)
    pos = None
    if lrr is not None and trr is not None and trr > lrr and last_n is not None:
        pos = round((last_n - lrr) / (trr - lrr) * 100)
    perf = _n(d.get("perf1d"))
    chg = _n(d.get("pct_change"))
    day_txt = _day_word(perf) + ((" (" + format(chg, "+.1f") + "%)") if chg is not None else "")
    where = (f"price {_usd(last)} is {pos}% of the way up its range ({_usd(lrr)} to {_usd(trr)})"
             if pos is not None else "range position unknown")
    macd, macdh = _n(d.get("macd_dir")), _n(d.get("macdh_dir"))
    mm = ""
    if macd is not None and macdh is not None:
        mm = f"; MACD {'rising' if macd > 0 else 'falling'}, MACDH {'rising' if macdh > 0 else 'falling'}"
    if signal:
        why = explain_technical(d, bounce_note=False)   # the Trade-line warning already has its own stage line
        first = why.split(NL)[0] if why else ""
        act = _n(d.get("td_tn_bb_rr_action"))
        ok = True if act is not None and act > 0 else (False if act is not None and act < 0 else None)
        stages.append({"name": "Range position", "ok": ok,
                       "text": (first.replace(R, "").replace(G, "").replace(E, "") or f"A setup matched ({day_txt}; {where})")})
        return out
    stages.append({"name": "Range position", "ok": None,
                   "text": f"No buy or sell setup matched: {day_txt}; {where}{mm}"})
    if qe >= 3 and qj >= 2:
        cand = []
        for label, name, conds in _bull_setups(d):
            unmet = [need for ok, need in conds if not ok]
            if unmet and len(conds) - len(unmet) >= 1:
                cand.append((len(unmet), label, name, unmet))
        cand.sort(key=lambda c: c[0])
        out["flip"] = [{"label": lb, "name": nm, "missing": um} for _k, lb, nm, um in cand[:2]]
    return out
