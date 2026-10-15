"""Plain-English Technical reason for a symbol's Technical signal (td_tn_bb_rr_action).

Follows the same decision order as etl/derive.py::_derive_trend_trade_rules_impl
(Pass 2):

    1. Trend/Trade read (trend_trade_rule QE):  bearish codes (-2, -1, 1) win outright;
       code 2 (between the lines) is neutral -> no signal; 3/4 are bullish -> continue.
    2. Bollinger band streak (bb_rng_strk_rule QJ): negative = bearish, wins.
    3. Range position (QM bull path when QJ >= 2, QN not-bull path when QJ in 0..1),
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
    -1: "At TRR (top of range)",
    2:  "Up day, low above LRR, at/below midpoint, MACD rising but MACDH not rising",
    3:  "Down day, low at LRR, above Trade and Trend",
    4:  "Up day, low touched LRR, price at or below the midpoint",
    5:  "Up day, low above LRR, at/below midpoint, MACD rising and MACDH rising",
}


def explain_technical(d: dict) -> Optional[str]:
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

    # 1. Trend / Trade read
    if qe == -2:
        return _two(f"Price {_usd(last)} {R}below{E} Trade ({_usd(trade)}) and Trend ({_usd(trend)})",
                    "bearish, overrides all other checks")
    if qe == -1:
        return _two(f"Trade ({_usd(trade)}) {R}below{E} Trend ({_usd(trend)}), price {_usd(last)} "
                    f"above Trade by less than one typical daily move",
                    "bearish, overrides all other checks")
    if qe == 1:
        return _two(f"Price {_usd(last)} {R}below{E} Trade ({_usd(trade)}) by more than half a "
                    f"typical daily move, above Trend ({_usd(trend)})",
                    "bearish, overrides range position")
    if qe == 2:
        return _two(f"Price {_usd(last)} above Trade ({_usd(trade)}), {R}below{E} Trend ({_usd(trend)})",
                    "neutral zone, no signal")

    # 2. Bollinger band streak
    qj = _n(d.get("bb_rng_strk_rule"))
    qj = 0 if qj is None else int(qj)
    if qj < 0:
        bb = d.get("bb_desc") or "bearish"
        return _two(f"Price above Trade and Trend, but Bollinger streak is {R}bearish{E} ({bb})",
                    "bearish band, overrides range position")

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
                    f"one and a half typical daily moves",
                    "broken support overrides bullish Trend, Trade and band")
    held = ""
    if raw is not None and int(raw) == -1:
        lrr_v, last_v = _n(d.get("lrr")), _n(last)
        if lrr_v is not None and last_v is not None and last_v < lrr_v:
            # Shallow dip: still under LRR, but by less than the break depth -- these
            # usually bounce (past-data check, 2026-10-14), so watch rather than sell.
            held = (f"Low {_usd(d.get('low'))} dipped below LRR ({_usd(d.get('lrr'))}) and price "
                    f"{_usd(last)} is still just under it (less than one and a half typical "
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
    return _two(f"{held}{why or 'No range-position condition matched'}",
                "above Trade and Trend, band not bearish")
