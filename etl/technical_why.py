"""Plain-English Technical reason for a symbol's Technical signal (td_tn_bb_rr_action).

TASK_155 (2026-10-25): rewritten for the redesigned rules (etl/technical_rules.py -- the SAME classifier that makes the call):

    Step 1  Trade / Trend lines   S1-a, S1-b, S1-c (sells), S1-d / 1a / 1d / 1e (no Step 1 sell, go to Step 3), 1b (rising dip, Buy Some)
    Step 2  Bollinger bands       2a..2f -- rising -> 3A, flat -> 3B, falling -> 3C (a falling band is a warning only)
    Step 3  LRR-TRR range         3a, 3x, 3f, 3h, 3k, 3p, tr -- runs for EVERY stock, with an Above / Below flag
                                  (Above = above Trade AND Trend, Below = anything else). A Step 3 buy beats the Step 1 sells.

RULE_HELP below is the ONE place the wording of every rule lives; the popup (tooltip, graph caption), the card and
web/technical_rules_map.html all repeat it, so edit it here first.

Pure functions: take a dict of the already-derived inputs. explain_technical -> two lines joined by a newline (line 1 = the situation
"Why", line 2 = the short verdict); the popup shows them as "Why <line 1>" / "Call <action>: <line 2>". technical_trail -> the stage trail.
"""
from __future__ import annotations

from typing import Optional

NL = chr(10)
# Highlight markers, rendered by web/actionable.js::_whyHtml (red / green).
# Stripped to plain text anywhere the text can't carry markup.
R, G, E = "{r}", "{g}", "{/}"

# Plain-English wording of every rule (same sentences as web/technical_rules_map.html). "above" / "below" = the action for a stock
# Above Trade and Trend / Below Trade or below Trend. Step 1 rules only apply to a stock under a line, so "above" is n/a.
_NA1 = "n/a (this rule only applies to a stock under a Trade or Trend line)"
RULE_HELP = {
    "S1-a": {"name": "Below the lowest of the last 5 Trade lines", "when": "Price is below the lowest of the last 5 Trade lines (still above Trend).",
             "above": _NA1, "below": "Sell All"},
    "S1-b": {"name": "Below both lines", "when": "Price is below both lines, or the Trade line is below the Trend line and price is less than 1 ATR (14-day) above the Trade line.",
             "above": _NA1, "below": "Sell All"},
    "S1-c": {"name": "Just fell below Trade", "when": "Price fell below Trade in the last 3 days, counting today (it was at or above Trade on one of the 2 days before today), is still below it, and is above Trend.",
             "above": _NA1, "below": "Sell Some"},
    "S1-d": {"name": "Below Trade, no fresh fall", "when": "Price is below Trade (above Trend) but did not just fall through it and is not under the lowest of the last 5 Trade lines: no Step 1 sell.",
             "above": _NA1, "below": "No Step 1 sell: Step 3 decides with the Below flag"},
    "1a": {"name": "Above both lines", "when": "Price is above Trade and above Trend.",
           "above": "No Step 1 sell: Step 3 decides with the Above flag", "below": "n/a"},
    "1b": {"name": "Rising dip", "when": "Price is under Trade by less than 1 SD but rising (up day, MACDH rising), above Trend, and not under the lowest of the last 5 Trade lines.",
           "above": "n/a", "below": "Buy Some"},
    "1d": {"name": "Bounce exception", "when": "Price is below Trade but closed up 2 days in a row, trades above yesterday's high, and LRR held: the Trade-line sell is skipped.",
           "above": "n/a", "below": "No Step 1 sell: Step 3 decides with the Below flag"},
    "1e": {"name": "Between the lines", "when": "Price is above Trade but below Trend.",
           "above": "n/a", "below": "No Step 1 sell: Step 3 decides with the Below flag"},
    "2a": {"name": "Bands rising strongly", "when": "Both Bollinger bands are rising steeply.", "above": "the rising-band range rules", "below": "the rising-band range rules"},
    "2b": {"name": "Bands rising", "when": "The top band is rising steeply and is above the bottom band's slope.", "above": "the rising-band range rules", "below": "the rising-band range rules"},
    "2c": {"name": "Bands flat, bottom rising", "when": "The bottom band is rising but the top band is not.", "above": "the flat-band range rules", "below": "the flat-band range rules"},
    "2d": {"name": "Bands flat", "when": "Neither band is rising or falling enough to count.", "above": "the flat-band range rules", "below": "the flat-band range rules"},
    "2e": {"name": "Bands falling a little", "when": "The top band is falling while the bottom band is not.", "above": "the falling-band range rules", "below": "the falling-band range rules"},
    "2f": {"name": "Bands falling", "when": "Both bands are falling, or the bottom band is falling faster than the top.", "above": "the falling-band range rules", "below": "the falling-band range rules"},
    "3a": {"name": "Support broken", "when": "Support broken: price is well below LRR.", "above": "Sell to Min", "below": "Sell All"},
    "3x": {"name": "Bounce at LRR", "when": "The day's low reached the LRR zone today or in the last 3 days, and price is 25% to 60% of the way up the range.",
           "above": "Buy More (falling bands: Buy Some)", "below": "Buy To Min (falling bands: Do nothing)"},
    "3f": {"name": "Fresh touch of LRR", "when": "The day's low reached the LRR zone today, and price is above LRR but under 25% of the range.",
           "above": "Buy Min", "below": "Do nothing"},
    "3h": {"name": "Up day, lower half", "when": "Up day and price is 25% to 60% of the range (rising bands: TRR also up 2% or more over 5 days).",
           "above": "Buy Min", "below": "Do nothing"},
    "3k": {"name": "Near the top of the range", "when": "Price or the day's high reached 90% of the range.", "above": "Sell Some", "below": "n/a"},
    "3p": {"name": "Near the top, bands falling", "when": "Price or the day's high reached 90% of the range.", "above": "Sell Some", "below": "n/a"},
    "tr": {"name": "Falling bands, under a line", "when": "Bands are falling and price is below Trade or below Trend.", "above": "n/a", "below": "Sell All"},
}

def _rname(sid) -> str:
    """Plain-English name of a rule (never show the internal id like 3x or S1-c to the user)."""
    return str((RULE_HELP.get(sid) or {}).get("name") or sid)


_CODE_LABEL = {-10:"Sell All", -9: "Sell to Min", -8: "Sell Some", 8: "Buy To Min", 9: "Buy Some", 10: "Buy More"}
# Step 1 result per rule id (what the rule says by itself, before Step 3). 1b is a buy.
_S1_CODE = {"S1-a": -10, "S1-b": -10, "S1-c": -8, "1b": 9}


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


def _label(code, sid: Optional[str] = None) -> Optional[str]:
    c = _n(code)
    if c is None:
        return None
    if int(c) == 8 and sid in ("3f", "3h"):
        return "Buy Min"
    return _CODE_LABEL.get(int(c))


def _dir(code) -> int:
    c = _n(code)
    return 0 if c is None or c == 0 else (1 if c > 0 else -1)


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
    return (f"Price {_usd(d.get('last'))} is below Trade ({_usd(d.get('trade_line'))}){_below_trade_pct(d)}: the Trade-line sell was skipped because "
            f"the stock closed up 2 days in a row, is above yesterday's high and LRR held. "
            f"The sell returns on a down day, a fall back under yesterday's high or an LRR break")


def _pos(d: dict) -> Optional[int]:
    last, lrr, trr = _n(d.get("last")), _n(d.get("lrr")), _n(d.get("trr"))
    if None in (last, lrr, trr) or trr <= lrr:
        return None
    return round((last - lrr) / (trr - lrr) * 100)


def _hpos(d: dict) -> Optional[int]:
    high, lrr, trr = _n(d.get("high")), _n(d.get("lrr")), _n(d.get("trr"))
    if None in (high, lrr, trr) or trr <= lrr:
        return None
    return round((high - lrr) / (trr - lrr) * 100)


def _band_word(qj: int) -> str:
    return "rising" if qj >= 2 else ("falling" if qj < 0 else "flat")


def _trr_chg(d: dict) -> str:
    trr, t5 = _n(d.get("trr")), _n(d.get("trr_5d_ago"))
    if trr is None or not t5:
        return ""
    return f"{(trr / t5 - 1) * 100:+.1f}%"


def _step1_why(sid: str, d: dict) -> str:
    last, trade, trend = d.get("last"), d.get("trade_line"), d.get("trend_line")
    qe = int(_n(d.get("trend_trade_rule")) or 0)
    if sid == "S1-a":
        return (f"Price {_usd(last)} is {R}below{E} the lowest of the last 5 Trade lines ({_usd(d.get('min_trade5_prev'))}); "
                f"Trade is {_usd(trade)}, Trend {_usd(trend)}")
    if sid == "S1-b":
        if qe == -2:
            return f"Price {_usd(last)} is {R}below{E} Trade ({_usd(trade)}) and Trend ({_usd(trend)})"
        return f"Trade ({_usd(trade)}) is {R}below{E} Trend ({_usd(trend)}) and price {_usd(last)} is less than 1 ATR above Trade"
    if sid == "S1-c":
        return (f"Price {_usd(last)} fell {R}below{E} Trade ({_usd(trade)}) within the last 3 days and is still under it"
                f"{_below_trade_pct(d)}; it is above Trend ({_usd(trend)})")
    if sid == "S1-d":
        return (f"Price {_usd(last)} is below Trade ({_usd(trade)}){_below_trade_pct(d)}, above Trend ({_usd(trend)}); it did not just fall through Trade "
                f"and is not under the lowest of the last 5 Trade lines ({_usd(d.get('min_trade5_prev'))}), so Step 1 does not sell")
    if sid == "1d":
        return _bounce_note(d)
    if sid == "1e":
        return f"Price {_usd(last)} is above Trade ({_usd(trade)}) but {R}below{E} Trend ({_usd(trend)})"
    if sid == "1b":
        return (f"Price {_usd(last)} is under Trade ({_usd(trade)}) by less than one SD but rising (up day, MACDH up), above Trend ({_usd(trend)}) "
                f"and not under the lowest Trade line of the last 5 days")
    ext = " and extended (more than 2 daily SDs away)" if qe == 4 else ""
    return f"Price {_usd(last)} is above Trade ({_usd(trade)}) and Trend ({_usd(trend)}){ext}"


def _step3_why(sid: str, d: dict) -> str:
    last, lrr, trr = d.get("last"), d.get("lrr"), d.get("trr")
    pos, hpos = _pos(d), _hpos(d)
    where = f"price {_usd(last)} is {pos}% of the way up its range ({_usd(lrr)} to {_usd(trr)})" if pos is not None else "range position unknown"
    if sid == "3a":
        return f"Price {_usd(last)} is {R}below{E} LRR ({_usd(lrr)}) by more than {_tol_txt(d)} typical daily moves: support broken"
    if sid == "3x":
        low, lo_, tr_ = _n(d.get("low")), _n(lrr), _n(trr)
        today = low is not None and lo_ is not None and tr_ is not None and low <= lo_ + (_n(d.get("lrr_zone")) or 0.25) * (tr_ - lo_)
        recent = "today" if today else "in the last 3 days"
        return f"The day's low reached the LRR zone {recent}, and {where}"
    if sid == "3f":
        return f"The day's low {_usd(d.get('low'))} reached the LRR zone today and {where}, under 25% and above LRR"
    if sid == "3h":
        extra = f"; TRR is {_trr_chg(d)} over 5 days" if _trr_chg(d) else ""
        return f"Up day and {where}{extra}"
    if sid in ("3k", "3p"):
        if pos is not None and pos > 90:
            return f"Price {_usd(last)} is in the top 10% of its range ({pos}%)"
        return f"The day's high {_usd(d.get('high'))} reached the top 10% of the range ({hpos}%); price {_usd(last)} is {pos}%"
    if sid == "tr":
        return f"Bands are falling and price {_usd(last)} is {R}below{E} Trade ({_usd(d.get('trade_line'))}) or Trend ({_usd(d.get('trend_line'))})"
    return where


def _infer_s1(qe: int, d: dict) -> Optional[str]:
    """Step 1 rule id from the base category alone (fallback when the stored id is missing)."""
    if qe == 0:
        return "1b"
    if qe in (3, 4):
        return "1a"
    if qe == 2:
        return "1e"
    if qe in (-2, -1):
        return "S1-b"
    if qe == 1:
        return "1d" if d.get("bounce_exempt") else "S1-d"
    return None


def _action_flag_txt(flag: Optional[str]) -> str:
    return "above Trade and Trend" if flag == "above" else "below Trade or Trend"


def _decider(d: dict):
    """(step id, kind) of the rule that made the Technical call. kind = 'step1' or 'step3'. (None, None) when there is no call."""
    act = _n(d.get("td_tn_bb_rr_action"))
    if act is None:
        return None, None
    s1, s3, z = d.get("step1_id"), d.get("step3_id"), _n(d.get("rr_zone_score"))
    if s1 == "1b":
        return "1b", "step1"
    if s3 and z is not None and z == act:
        return s3, "step3"
    if s1 in _S1_CODE:
        return s1, "step1"
    return (s3, "step3") if s3 else (s1, "step1")


def explain_technical(d: dict, bounce_note: bool = True) -> Optional[str]:
    """Why line + verdict line (newline-separated) for the Technical signal, or None.

    Keys used: trend_trade_rule, bb_rng_strk_rule, td_tn_bb_rr_action (None = no signal), rr_zone_score, step1_id, step3_id, tech_flag,
    last, high, low, lrr, trr, trade_line, trend_line, min_trade5_prev, trr_5d_ago, lrr_idx_eff, bounce_exempt, reclaim_buy.
    """
    qe = _n(d.get("trend_trade_rule"))
    if _n(d.get("td_tn_bb_rr_action")) is None or qe is None:
        return None
    last, trend = d.get("last"), d.get("trend_line")
    if d.get("reclaim_buy"):
        # 2026-10-21 reclaim buy (etl/derive.py Pass 2b): fill-only, low confidence.
        return _two(f"Price {_usd(last)} is back above a recent Trade line ({_usd(d.get('reclaim_line'))}, one of the last 3) after closing below it "
                    f"2 days ago, on an up day; Trade is well above Trend ({_usd(trend)}) and no other Technical setup matched",
                    "reclaim buy: BUY SOME, low confidence")
    if not d.get("step1_id"):
        d = dict(d, step1_id=_infer_s1(int(qe), d))   # rows saved before TASK_155 carry no rule ids
    sid, kind = _decider(d)
    if sid is None:
        return None
    flag = d.get("tech_flag") or ("above" if int(qe) in (3, 4) else "below")
    if int(qe) == 0 and _n(d.get("td_tn_bb_rr_action")) < 0:
        return _two(f"Price {_usd(last)} {R}below{E} LRR ({_usd(d.get('lrr'))}) by more than {_tol_txt(d)} typical daily moves",
                    "broken support overrides the rising-dip buy")
    why = _step1_why(sid, d) if kind == "step1" else _step3_why(sid, d)
    act = _label(d.get("td_tn_bb_rr_action"), sid) or ""
    if kind == "step1":
        verdict = f"{_rname(sid)}: {act}" if sid != "1b" else "rising dip under Trade: BUY SOME"
        s3 = d.get("step3_id")
        if s3 and _n(d.get("rr_zone_score")) is None and s3 in ("3x", "3f", "3h", "3p", "3k"):
            verdict += f" (the range rule \"{_rname(s3)}\" says do nothing for a stock {_action_flag_txt(flag)})"
    else:
        s1 = d.get("step1_id")
        verdict = f"{_rname(sid)} ({_action_flag_txt(flag)}): {act}"
        if s1 in ("S1-a", "S1-b", "S1-c") and _n(d.get("td_tn_bb_rr_action")) > 0:
            verdict += f"; this buy beats the Trade/Trend sell (\"{_rname(s1)}\")"
    return _two(why, verdict)


# ---------------------------------------------------------------------------
# Stage-by-stage trail of the Technical read + "what would change it" hints.
# Mirrors etl/technical_rules.py. Pure function. Stored as drv_tn_td_bb_rr.tech_trail and read by etl/why_card.py.
# ---------------------------------------------------------------------------
def _day_word(perf: Optional[float]) -> str:
    if perf is None:
        return "day"
    return "up day" if perf > 0 else ("down day" if perf < 0 else "flat day")


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


def step_ids(d: dict) -> dict:
    """{'trend': 'S1-a'|None, 'bands': '2a'|None, 'range': '3x'|None} -- the rule id of each Technical stage (read from the stored result)."""
    qj = _n(d.get("bb_rng_strk_rule"))
    out = {"trend": d.get("step1_id"), "bands": None, "range": d.get("step3_id")}
    qe = _n(d.get("trend_trade_rule"))
    if qe is None or qe in (0, 5):
        return out          # no read, rising dip or neutral dip: the bands / range stages are not part of the call
    qj = 0 if qj is None else int(qj)
    out["bands"] = "2a" if qj >= 3 else "2b" if qj == 2 else "2c" if qj == 1 else "2d" if qj == 0 else "2e" if qj == -1 else "2f"
    return out


def technical_trail(d: dict) -> dict:
    """Same as _technical_trail_core, plus a warning-only 'Bollinger bands' line when the top or bottom band is falling, and the
    rule id / action / help text on every stage the popup draws (step, action, dir, flag, help)."""
    out = _technical_trail_core(d)
    fall = _bb_falling_txt(d)
    if fall:
        msg = f"A band is falling ({fall}): warning only, not counted as a sell"
        bb_st = next((s for s in out["stages"] if s.get("name") == "Bollinger bands"), None)
        if bb_st is None:
            out["stages"].append({"name": "Bollinger bands", "ok": None, "warn": True, "text": msg})
        elif not bb_st.get("warn"):
            bb_st.update({"warn": True, "text": bb_st["text"] + "; " + msg})
    ids = step_ids(d)
    for st in out["stages"]:
        sid = ids["trend"] if st.get("name") == "Trend & Trade" else ids["bands"] if st.get("name") == "Bollinger bands" \
            else ids["range"] if st.get("name") == "Range position" else None
        if sid:
            st["step"] = sid
            if sid in RULE_HELP:
                st["help"] = RULE_HELP[sid]
    return out


def _flip_candidates(d: dict) -> list:
    """No buy/sell call: the closest Step 3 buy rules and what each still needs, as [{'label','name','missing'}]."""
    last, high = _n(d.get("last")), _n(d.get("high"))
    lrr, trr = _n(d.get("lrr")), _n(d.get("trr"))
    if None in (last, lrr, trr) or trr <= lrr:
        return []
    low = _n(d.get("low"))
    zl = _n(d.get("lrr_zone")) or 0.25
    pos = (last - lrr) / (trr - lrr) * 100.0
    zone_today = low is not None and low <= lrr + zl * (trr - lrr)
    zone_any = zone_today or bool(d.get("zone_recent"))
    perf = _n(d.get("perf1d"))
    up = perf is not None and perf > 0
    qj = _n(d.get("bb_rng_strk_rule")) or 0
    above = int(_n(d.get("trend_trade_rule")) or 0) in (3, 4)
    mid = 25 <= pos <= 60
    lab_x = ("BUY MORE" if above else "BUY TO MIN") if qj >= 0 else ("BUY SOME" if above else None)
    lab_m = "BUY TO MIN" if above else None
    cand = []
    if lab_x:
        cand.append((lab_x, "bounce at LRR", [(zone_any, "the day's low to reach the LRR zone (today or in the last 3 days)"),
                                                 (mid, f"price 25% to 60% of the range (now {round(pos)}%)")]))
    if qj >= 0 and lab_m:
        cand.append((lab_m, "fresh touch of LRR", [(zone_today, "the day's low to reach the LRR zone today"),
                                                       (last > lrr and pos < 25, f"price above LRR but under 25% of the range (now {round(pos)}%)")]))
        t5 = _n(d.get("trr_5d_ago"))
        extra = [(t5 is not None and trr >= 1.02 * t5, "TRR up 2% or more over 5 days")]
        cand.append((lab_m, "up day in the lower half", [(up, "an up day"), (mid, f"price 25% to 60% of the range (now {round(pos)}%)")] + (extra if qj >= 2 else [])))
    res = []
    for label, name, conds in cand:
        unmet = [need for ok, need in conds if not ok]
        if unmet and len(conds) - len(unmet) >= 1:
            res.append((len(unmet), label, name, unmet))
    res.sort(key=lambda c: c[0])
    return [{"label": lb, "name": nm, "missing": um} for _k, lb, nm, um in res[:2]]


def _stage(name: str, ok, text: str, sid: Optional[str] = None, code=None, flag: Optional[str] = None, **kw) -> dict:
    st = {"name": name, "ok": ok, "text": text}
    st.update(kw)
    if code is not None or sid in _S1_CODE:
        c = code if code is not None else _S1_CODE.get(sid)
        st["action"] = _label(c, sid)
        st["dir"] = _dir(c)
        st["score"] = c
    if flag:
        st["flag"] = flag
    return st


def _technical_trail_core(d: dict) -> dict:
    """{'signal': bool, 'stages': [{'name', 'ok': True|False|None, 'text', 'action', 'dir', 'flag'}], 'flip': [{'label','name','missing':[...]}]}.

    Stages: 1 Trend & Trade, 2 Bollinger bands, 3 Range position. ok=None means neutral / not evaluated.
    Step 3 runs for every stock except the two dip codes (0 rising dip = Buy Some, 5 neutral dip = no signal).
    """
    act = _n(d.get("td_tn_bb_rr_action"))
    signal = act is not None
    qe, qj = _n(d.get("trend_trade_rule")), _n(d.get("bb_rng_strk_rule"))
    last, trade, trend = d.get("last"), d.get("trade_line"), d.get("trend_line")
    stages: list = []
    out = {"signal": signal, "stages": stages, "flip": []}
    if qe is None:
        stages.append({"name": "Trend & Trade", "ok": None, "text": "No Trend/Trade data for this stock"})
        return out
    qe = int(qe)
    flag = d.get("tech_flag") or ("above" if qe in (3, 4) else "below")
    s1 = d.get("step1_id")
    if qe == 5:
        # 2026-10-23, user: same dip as code 0 but the MACD histogram is not rising -> neutral, no signal
        stages.append(_stage("Trend & Trade", None,
                             f"Price {_usd(last)} is under Trade ({_usd(trade)}) by less than one SD, up on the day, above Trend ({_usd(trend)}) "
                             f"and not under the lowest Trade line of the last 5 days, but MACDH is not rising: neutral, no signal"))
        return out
    if qe == 0:
        # 2026-10-23, user (SNOW): a rising dip under Trade is BUY SOME, not a sell (a broken LRR support still sells)
        broke = act is not None and act < 0
        stages.append(_stage("Trend & Trade", not broke, _step1_why("1b", d) + (": rising dip, buy some" if not broke else ""), "1b", code=act if broke else None))
        return out

    # 1 Trend & Trade
    if s1 is None:
        s1 = _infer_s1(qe, d) or "S1-d"
    sell1 = s1 in ("S1-a", "S1-b", "S1-c")
    if s1 == "1d":
        stages.append(_stage("Trend & Trade", None, "⚠ " + _bounce_note(d), s1, warn=True))
    else:
        stages.append(_stage("Trend & Trade", False if sell1 else (True if s1 == "1a" else None),
                             _step1_why(s1, d) + (": " + (_label(_S1_CODE[s1]) or "") if sell1 else ""), s1))
    # 2 Bollinger bands
    qj = 0 if qj is None else int(qj)
    bb = d.get("bb_desc") or ""
    bb_txt = (" (" + bb + ")") if bb else ""
    if qj >= 2:
        stages.append({"name": "Bollinger bands", "ok": True, "text": "Bands are rising" + bb_txt + ": the rising-band range rules"})
    elif qj >= 0:
        stages.append({"name": "Bollinger bands", "ok": None, "text": "Bands are flat" + bb_txt + ": the flat-band range rules"})
    else:
        # 2026-10-20: a falling band is a warning only (no sell on its own); Step 3C has its own rules.
        stages.append({"name": "Bollinger bands", "ok": None, "warn": True,
                       "text": "Bands are falling" + bb_txt + ": the falling-band range rules; a falling band alone is a warning, not a sell"})
    # 3 Range position
    if d.get("reclaim_buy") and signal:
        # 2026-10-21 reclaim buy (etl/derive.py Pass 2b): fill-only, low confidence
        stages.append({"name": "Range position", "ok": True, "text": (explain_technical(d, bounce_note=False) or "").split(NL)[0]})
        return out
    s3, z = d.get("step3_id"), _n(d.get("rr_zone_score"))
    chg = _n(d.get("pct_change"))
    day_txt = _day_word(_n(d.get("perf1d"))) + ((" (" + format(chg, "+.1f") + "%)") if chg is not None else "")
    if s3:
        txt = _step3_why(s3, d)
        if z is None:
            txt += f": Do nothing for a stock {_action_flag_txt(flag)}"
        else:
            txt += f": {_label(z, s3)} ({_action_flag_txt(flag)})"
            if z > 0 and sell1:
                txt += f"; this buy beats the Trade/Trend sell (\"{_rname(s1)}\")"
        stages.append(_stage("Range position", True if z is not None and z > 0 else (False if z is not None and z < 0 else None), txt, s3, code=z, flag=flag))
        if z is None and not signal:
            out["flip"] = _flip_candidates(d)
        return out
    where = _step3_why("", d)
    stages.append({"name": "Range position", "ok": None,
                   "text": f"No Step 3 rule matched ({day_txt}; {where}): Hold"})
    if not signal:
        out["flip"] = _flip_candidates(d)
    return out
