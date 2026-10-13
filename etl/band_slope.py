"""Bollinger-band steepness score (top and bottom band), computed from stored daily bands.

Replaces the TOS-exported A_BB_Top_Slope / A_BB_Bot_Slope in the Technical band reading
(etl/derive.py, bb_rng_strk_rule) -- the TOS script scored a rebound or a fresh rollover wrongly.

Score rules (2026-10-13, user):
  - positive only when the general direction (LOOKBACK bars) AND the last RECENT bars are both up;
  - negative only when both are down;
  - mixed or sideways = 0 (a slope under FLAT_ZONE x ATR per bar counts as sideways).
Size = slope / ATR x efficiency x recency x persistence x 45 (the original TOS recipe), so the
existing bb_slope_hi / bb_slope_lo thresholds (3 / 2) stay on the same scale.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional, Sequence

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

LOOKBACK = 10
RECENT = 5
SMOOTH = 3
FLAT_ZONE = 0.05
ATR_LEN = 14
MIN_POINTS = LOOKBACK + SMOOTH + 2     # smoothed series must hold LOOKBACK + 1 points


def wilder_atr(high: Sequence[float], low: Sequence[float], close: Sequence[float],
               n: int = ATR_LEN) -> Optional[float]:
    """Wilder ATR over daily bars (oldest first). None when fewer than n + 1 bars."""
    h, l, c = (np.asarray(v, float) for v in (high, low, close))
    if len(c) < n + 1:
        return None
    tr = np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))
    atr = tr[:n].mean()
    for t in tr[n:]:
        atr = (atr * (n - 1) + t) / n
    return float(atr)


def band_score(values: Sequence[float], atr: Optional[float]) -> Optional[float]:
    """Steepness score for one band series (oldest first). None when there is too little data."""
    if atr is None or atr <= 0:
        return None
    x = np.asarray([v for v in values if v is not None], float)
    if len(x) < MIN_POINTS:
        return None
    st = np.convolve(x, np.ones(SMOOTH) / SMOOTH, mode="valid")       # SMOOTH-bar average
    main = np.polyfit(np.arange(LOOKBACK), st[-LOOKBACK:], 1)[0]
    recent = np.polyfit(np.arange(RECENT), st[-RECENT:], 1)[0]
    tol = FLAT_ZONE * atr
    if not ((main > tol and recent > tol) or (main < -tol and recent < -tol)):
        return 0.0                                                    # mixed or sideways
    recency = min(1.5, abs(recent) / abs(main)) ** 1.2
    win = st[-LOOKBACK:]
    if np.std(win) == 0:
        return 0.0
    persistence = np.corrcoef(np.arange(LOOKBACK), win)[0, 1] ** 2
    path = np.abs(np.diff(st[-(LOOKBACK + 1):])).sum()
    net = st[-1] - st[-1 - LOOKBACK]
    efficiency = (abs(net) / path) ** 0.15 if path > 0 else 1.0
    return round(float(main / max(0.01, atr) * efficiency * recency * persistence * 45), 1)


def compute_band_slopes(session: Session, as_of_date: date) -> dict:
    """{tos_symbol: (top_score, bot_score)} from hist_td bands and hist_y daily bars <= as_of_date."""
    bands: dict = {}
    for sym, top, bot in session.execute(text("""
        SELECT tos_symbol, a_bb_top, a_bb_bottom FROM (
            SELECT DISTINCT ON (tos_symbol, export_date)
                   tos_symbol, export_date, a_bb_top, a_bb_bottom
            FROM hist_td
            WHERE export_date <= :d AND export_date >= :d - 60 AND tos_symbol IS NOT NULL
            ORDER BY tos_symbol, export_date, sequence DESC
        ) t ORDER BY tos_symbol, export_date
    """), {"d": as_of_date}):
        b = bands.setdefault(sym, ([], []))
        b[0].append(float(top) if top is not None else None)
        b[1].append(float(bot) if bot is not None else None)

    bars: dict = {}
    for sym, hi, lo, cl in session.execute(text("""
        SELECT tos_symbol, high_price, low_price, last_price FROM (
            SELECT DISTINCT ON (tos_symbol, export_date)
                   tos_symbol, export_date, high_price, low_price, last_price
            FROM hist_y
            WHERE export_date <= :d AND export_date >= :d - 90 AND tos_symbol IS NOT NULL
              AND high_price IS NOT NULL AND low_price IS NOT NULL AND last_price IS NOT NULL
            ORDER BY tos_symbol, export_date, sequence DESC
        ) t ORDER BY tos_symbol, export_date
    """), {"d": as_of_date}):
        b = bars.setdefault(sym, ([], [], []))
        b[0].append(float(hi)); b[1].append(float(lo)); b[2].append(float(cl))

    out: dict = {}
    for sym, (tops, bots) in bands.items():
        hlc = bars.get(sym)
        atr = wilder_atr(*hlc) if hlc else None
        t, b = band_score(tops, atr), band_score(bots, atr)
        if t is not None and b is not None:
            out[sym] = (t, b)
    return out


def load_band_slope_table(session: Session, as_of_date: date) -> int:
    """Fill temp table _band_slope for the Technical derive. Returns rows written."""
    session.execute(text(
        "CREATE TEMP TABLE IF NOT EXISTS _band_slope "
        "(tos_symbol text PRIMARY KEY, top_score numeric, bot_score numeric) ON COMMIT DROP"))
    session.execute(text("DELETE FROM _band_slope"))
    scores = compute_band_slopes(session, as_of_date)
    if scores:
        session.execute(
            text("INSERT INTO _band_slope (tos_symbol, top_score, bot_score) VALUES (:s, :t, :b)"),
            [{"s": s, "t": t, "b": b} for s, (t, b) in scores.items()])
    return len(scores)
