"""SPX vs the hand-entered GEX flip line (hist_msr.spx_flip_line).

Above the flip dealers calm the market; below it they make moves bigger. Display/annotation only.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text

NEAR_PCT = 0.3  # within this % of the flip = "near flip" (user-approved 2026-10-21)


def flip_status(session, flip: Optional[float], as_of_date) -> Optional[dict]:
    """None when no flip or no SPX price. 'crossed' = the prior close was on the other side of the flip."""
    if flip is None:
        return None
    rows = session.execute(text(
        "SELECT last_price FROM drv_quote WHERE tos_symbol = 'SPX' AND as_of_date <= :d "
        "AND last_price IS NOT NULL ORDER BY as_of_date DESC LIMIT 2"
    ), {"d": as_of_date}).all()
    if not rows:
        return None
    spx = float(rows[0][0])
    prev = float(rows[1][0]) if len(rows) > 1 else None
    diff = spx - flip
    pct = diff / flip * 100.0
    return {
        "spx": spx,
        "flip": flip,
        "diff": diff,
        "pct": pct,
        "side": "above" if diff >= 0 else "below",
        "near": abs(pct) <= NEAR_PCT,
        "crossed": prev is not None and (prev - flip >= 0) != (diff >= 0),
    }
