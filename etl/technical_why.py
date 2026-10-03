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
    3:  "Up day, low above LRR, below midpoint, MACD falling",
    4:  "Up day, low touched LRR",
    5:  "Down day, above midpoint",
    6:  "Up day, low above LRR, below midpoint, MACD rising",
}
# not-bull path (QJ 0..1): nbull_rr_rule codes
_NBULL = {
    -1: "At TRR (top of range)",
    2:  "Up day, low above LRR, at/below midpoint, MACD falling",
    3:  "Down day, low at LRR, above Trade and Trend",
    4:  "Up day, low touched LRR",
    5:  "Up day, low above LRR, at/below midpoint, MACD rising",
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
        return _two(f"Price {_usd(last)} below Trade ({_usd(trade)}) and Trend ({_usd(trend)})",
                    "bearish, overrides all other checks")
    if qe == -1:
        return _two(f"Trade ({_usd(trade)}) below Trend ({_usd(trend)}), price {_usd(last)} "
                    f"less than 1 SD above Trade",
                    "bearish, overrides all other checks")
    if qe == 1:
        return _two(f"Price {_usd(last)} above Trend ({_usd(trend)}), more than 1/2 SD below "
                    f"Trade ({_usd(trade)})",
                    "bearish, overrides range position")
    if qe == 2:
        return _two(f"Price {_usd(last)} above Trade ({_usd(trade)}), below Trend ({_usd(trend)})",
                    "neutral zone, no signal")

    # 2. Bollinger band streak
    qj = _n(d.get("bb_rng_strk_rule"))
    qj = 0 if qj is None else int(qj)
    if qj < 0:
        bb = d.get("bb_desc") or "bearish"
        return _two(f"Price above Trade and Trend, but Bollinger streak is bearish ({bb})",
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
        return _two(f"Price {_usd(last)} more than 1/2 SD below LRR ({_usd(d.get('lrr'))})",
                    "broken support overrides bullish Trend, Trade and band")
    held = ""
    if raw is not None and int(raw) == -1:
        held = (f"Low {_usd(d.get('low'))} dipped below LRR ({_usd(d.get('lrr'))}) but price "
                f"{_usd(last)} recovered: support held. ")
    if qj >= 2:
        q = _n(d.get("bull_rr_action"))
        why = _BULL.get(int(q)) if q is not None else None
    else:
        q = _n(d.get("not_bull_rr_action"))
        why = _NBULL.get(int(q)) if q is not None else None
    return _two(f"{held}{why or 'No range-position condition matched'}",
                "above Trade and Trend, band not bearish")
