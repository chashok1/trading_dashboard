"""TASK_155 (2026-10-25): the Technical rules, Step 1 (Trade / Trend lines) and Step 3 (LRR-TRR range), in ONE place.

Pure functions, no DB. The same classifier is used by
  * etl/derive.py::_derive_trend_trade_rules_impl  (today's stocks -> td_tn_bb_rr_action), and
  * etl/derive_signal_winrate.py                    (all history -> win % per rule),
so the rule the popup shows and the rule the win % was measured on can never drift apart.
Wording of every rule: etl/technical_why.py::RULE_HELP. Picture: web/technical_rules_map.html. Logic: docs/actionable_logic.md (2026-10-25).

Input: a DataFrame with one row per stock-day and these columns (missing / NaN = condition not met):
    qe          trend_trade_rule (-2..5; 3/4 = above Trade and Trend, 0 = rising dip, 5 = neutral dip, 1 = below Trade, 2 = between lines)
    qj          bb_rng_strk_rule (>= 2 rising, 0..1 flat, < 0 falling)
    bx          bounce exception (qe 1 that skips the below-Trade sell)
    px, hi, lo  latest price, day high, day low
    lrr, trr    risk range
    up          up day (price above the previous close)
    below5      price below the lowest of the PREVIOUS five Trade lines (today not included)
    fell3       price was at/above that day's Trade line on one of the 2 days before today (the last 3 days = today + those 2)
    zone_recent the day's low reached the LRR zone on one of the previous three days
    trr_up5     TRR today is at least 1.02 x TRR five trading days earlier
    brk         support broken (price more than the LRR-break ATR multiple below LRR)
Output columns: s1_id, s1_code, s3_id, s3_code, flag ('above'|'below'), code (final td_tn_bb_rr_action, NaN = no signal).
Action codes (ref_param_lookup td_tn_bb_rr_action): SA -10, STM -9, SS -8, BMN 8, BS 9, BM 10.
"Buy Min" and "Buy To Min" are the same existing code BMN; "Do nothing" / Hold = NaN.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

SA, STM, SS, BMN, BS, BM = -10.0, -9.0, -8.0, 8.0, 9.0, 10.0
POS_LO, POS_HI, POS_TOP = 25.0, 60.0, 90.0   # % of the LRR-TRR range
LRR_ZONE = 0.25                              # bottom share of the range = "LRR zone" (ref_settings range_lrr_zone_pct)

# Every step id this module can produce, with the side of its action (+1 buy, -1 sell) for the win %. Per-flag side: (above, below).
STEP_SIDE = {
    "S1-a": (-1, -1), "S1-b": (-1, -1), "S1-c": (-1, -1), "S1-d": (0, 0),
    "1a": (0, 0), "1b": (1, 1), "1d": (0, 0), "1e": (0, 0),
    "3a": (-1, -1), "3x": (1, 1), "3f": (1, 0), "3h": (1, 0), "3k": (-1, 0), "3p": (-1, 0), "tr": (0, -1),
}


def _b(s) -> pd.Series:
    return s.fillna(False).astype(bool)


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce")
    return pd.Series(np.nan, index=df.index)


def _flag(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return _b(df[col])
    return pd.Series(False, index=df.index)


def _first_match(index, rules):
    """rules = [(mask, id, code)] in priority order; the first matching rule gives the row its id and code (code may be a Series)."""
    ids = pd.Series([None] * len(index), index=index, dtype=object)
    codes = pd.Series(np.nan, index=index, dtype=float)
    left = pd.Series(True, index=index)
    for mask, sid, code in rules:
        m = mask & left
        if m.any():
            ids[m] = sid
            codes[m] = code[m] if isinstance(code, pd.Series) else code
        left &= ~m
    return ids, codes


def classify(df: pd.DataFrame, lrr_zone: float = LRR_ZONE) -> pd.DataFrame:
    ix = df.index
    qe, qj = _num(df, "qe"), _num(df, "qj").fillna(0)
    px, hi, lo, lrr, trr = (_num(df, c) for c in ("px", "hi", "lo", "lrr", "trr"))
    bx, up, brk = _flag(df, "bx"), _flag(df, "up"), _flag(df, "brk")
    below5, fell3, zone_recent, trr_up5 = (_flag(df, c) for c in ("below5", "fell3", "zone_recent", "trr_up5"))

    rng = trr - lrr
    ok = (rng > 0) & px.notna()
    pos = (px - lrr) / rng * 100.0
    hpos = (hi - lrr) / rng * 100.0
    zone_today = ok & _b(lo <= lrr + lrr_zone * rng)
    zone_any = zone_today | (ok & zone_recent)
    above = qe.isin([3, 4])
    rising, fall = qj >= 2, qj < 0
    flat = ~rising & ~fall
    top = ok & (_b(pos > POS_TOP) | _b(hpos > POS_TOP))
    mid_band = ok & _b(pos >= POS_LO) & _b(pos <= POS_HI)

    # Step 1 (first match wins). 0 = rising dip (Buy Some), 5 = neutral dip (no signal): unchanged from before.
    q1 = qe == 1
    s1_id, s1_code = _first_match(ix, [
        (q1 & ~bx & below5, "S1-a", SA),
        (qe.isin([-2, -1]), "S1-b", SA),
        (q1 & ~bx & fell3, "S1-c", SS),
        (q1 & ~bx, "S1-d", np.nan),
        (q1 & bx, "1d", np.nan),
        (qe == 0, "1b", BS),
        (qe == 2, "1e", np.nan),
        (above, "1a", np.nan),
    ])

    # Step 3 (runs for every stock except the two dip codes), first match wins inside each band group.
    run3 = ok & qe.notna() & ~qe.isin([0, 5])
    buy_x = pd.Series(np.where(above, np.where(fall, BS, BM), np.where(fall, np.nan, BMN)), index=ix)
    buy_min = pd.Series(np.where(above, BMN, np.nan), index=ix)
    sell_a = pd.Series(np.where(above, STM, SA), index=ix)
    rules = [
        (run3 & brk, "3a", sell_a),
        (run3 & zone_any & mid_band, "3x", buy_x),
        (run3 & ~fall & zone_today & _b(px > lrr) & _b(pos < POS_LO), "3f", buy_min),
        (run3 & ~fall & up & mid_band & (~rising | trr_up5), "3h", buy_min),
        (run3 & flat & above & top, "3k", SS),
        (run3 & fall & above & top, "3p", SS),
        (run3 & fall & ~above, "tr", SA),
    ]
    s3_id, s3_code = _first_match(ix, rules)

    # Final: a Step 3 buy wins over every Step 1 sell; otherwise the stronger sell of the two; otherwise no signal.
    # Rising dip (qe 0) keeps its old call (Buy Some, or Sell To Min when support is broken); neutral dip / no read = no signal.
    sell1 = s1_code.where(s1_code < 0)
    sell3 = s3_code.where(s3_code < 0)
    worst = pd.concat([sell1, sell3], axis=1).min(axis=1, skipna=True)
    final = s3_code.where(s3_code > 0, worst)
    final = final.where(qe != 0, pd.Series(np.where(brk, STM, BS), index=ix))
    final = final.where(qe.notna() & (qe != 5))
    return pd.DataFrame({"s1_id": s1_id, "s1_code": s1_code, "s3_id": s3_id, "s3_code": s3_code,
                         "flag": np.where(above, "above", "below"), "code": final}, index=ix)
