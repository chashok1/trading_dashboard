"""Plain-English reason for a symbol's Technical signal (td_tn_bb_rr_action).

Follows the same decision order as etl/derive.py::_derive_trend_trade_rules_impl
(Pass 2):

    1. Trend/Trade read (trend_trade_rule QE):  bearish codes (-2, -1, 1) win outright;
       code 2 (between the lines) is neutral -> no signal; 3/4 are bullish -> continue.
    2. Bollinger band streak (bb_rng_strk_rule QJ): negative = bearish, wins.
    3. Range position (QM bull path when QJ >= 2, QN not-bull path when QJ in 0..1),
       with a broken LRR support (lrr_idx = -1) overriding both.

Pure function: takes a dict of the already-derived inputs, returns one sentence
(or None when there is no Technical signal to explain).
"""
from __future__ import annotations

from typing import Optional


def _n(v) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _usd(v) -> str:
    x = _n(v)
    return "?" if x is None else f"${x:,.2f}"


# bull path (QJ >= 2): bull_rr_rule codes
_BULL = {
    -1: "Down day (1 SD or more) with price below the range midpoint and the low still above LRR: bearish inside the bull zone",
    1:  "Price is at the range midpoint on an up/flat day",
    2:  "Down day with the low at LRR while the Trade line is positive",
    3:  "Up day, low stayed above LRR, price still below the midpoint, MACD histogram falling",
    4:  "Up day and today's low touched LRR",
    5:  "Down day while price is above the range midpoint",
    6:  "Up day, low stayed above LRR, price still below the midpoint, MACD histogram rising",
}
# not-bull path (QJ 0..1): nbull_rr_rule codes
_NBULL = {
    -1: "Price has reached TRR (the top of its range)",
    2:  "Up day, low stayed above LRR, price at/below the midpoint, MACD histogram falling",
    3:  "Down day with the low at LRR while price is above both Trade and Trend",
    4:  "Up day and today's low touched LRR",
    5:  "Up day, low stayed above LRR, price at/below the midpoint, MACD histogram rising",
}


def explain_technical(d: dict) -> Optional[str]:
    """Reason sentence for the Technical signal, or None if there is none.

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
        return (f"Price {_usd(last)} is below both the Trade line {_usd(trade)} and the "
                f"Trend line {_usd(trend)}: a bearish Trend/Trade read overrides every other check.")
    if qe == -1:
        return (f"The Trade line {_usd(trade)} is below the Trend line {_usd(trend)} and price "
                f"{_usd(last)} is less than 1 SD above it: a bearish Trend/Trade read overrides "
                f"every other check.")
    if qe == 1:
        return (f"Price {_usd(last)} is above the Trend line {_usd(trend)} but more than 1/4 SD "
                f"below the Trade line {_usd(trade)}: a bearish Trend/Trade read overrides the "
                f"range-position signal.")
    if qe == 2:
        return (f"Price {_usd(last)} is below the Trend line {_usd(trend)} but above the Trade "
                f"line {_usd(trade)}: neutral zone, no Technical signal.")

    # 2. Bollinger band streak
    qj = _n(d.get("bb_rng_strk_rule"))
    qj = 0 if qj is None else int(qj)
    if qj < 0:
        bb = d.get("bb_desc") or "bearish"
        return (f"Price is above both lines, but the Bollinger band streak is bearish ({bb}): "
                f"it overrides the range-position signal.")

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
        return (f"Support broke: price {_usd(last)} is more than 1/4 SD below LRR "
                f"{_usd(d.get('lrr'))}. A broken support forces SELL TO MIN even when "
                f"Trend, Trade and the band are bullish.")
    held = ""
    if raw is not None and int(raw) == -1:
        held = (f"Today's low {_usd(d.get('low'))} dipped below LRR {_usd(d.get('lrr'))} but price "
                f"{_usd(last)} recovered, so support held (treated as touching LRR). ")
    if qj >= 2:
        q = _n(d.get("bull_rr_action"))
        why = _BULL.get(int(q)) if q is not None else None
    else:
        q = _n(d.get("not_bull_rr_action"))
        why = _NBULL.get(int(q)) if q is not None else None
    if why:
        return (f"Above Trade and Trend, band not bearish. {held}Range position: {why}.")
    return (f"Above Trade and Trend, band not bearish. {held}"
            f"No range-position condition matched.")
