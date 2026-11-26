"""Buy / sell amounts, ONE ACCOUNT AT A TIME (2026-11-25, user).

Rule: minimum, maximum, unit and suggested amounts apply to a single account and are never added across accounts.
Holdings may be added only in summaries. docs/actionable_logic.md (2026-11-25).

  Buy      follows the sources' action for that account: ADD fills up to the account minimum; INCREASE adds one unit
           (a new position starts at minimum + one unit), never past the maximum.
  Sell     SELL ALL sells everything the account holds. SELL SOME sells one unit and stops at the minimum.
           SELL TO MIN sells down to the minimum.

Pure functions, no DB.
"""
from __future__ import annotations

from typing import Iterable, Optional

BUY_CODES = ("BM", "BS", "BMN")
SELL_CODES = ("SA", "SS", "STM")


def target_holding(consolidated: Optional[str], held: float, mn: float, mx: float, unit: float) -> float:
    """What this account should end up holding under the sources' action (held = no change)."""
    ca = (consolidated or "").upper()
    if ca == "REMOVE":
        return 0.0
    if ca == "ADD":
        return held if (mn > 0 and held >= mn) else max(held, mn)
    if ca == "INCREASE":
        if held <= 0:
            return min(mn + unit, mx) if mx > 0 else mn + unit
        if mx > 0 and held >= mx:
            return held
        return min(held + unit, mx) if mx > 0 else held + unit
    if ca == "REDUCE":
        return held if held <= mn else max(mn, held - unit)
    return held


def account_trade(final_code: Optional[str], consolidated: Optional[str], held: float, mn: float, mx: float,
                  unit: float) -> tuple[float, float, Optional[str]]:
    """(buy $, sell $, note) for one account under the stock's Final Call. note says why a call has no amount."""
    code = (final_code or "").upper()
    held, mn, mx, unit = (float(v or 0) for v in (held, mn, mx, unit))
    if code in SELL_CODES:
        if held <= 0:
            return 0.0, 0.0, "not held"
        if code == "SA":
            return 0.0, held, None
        above_min = max(0.0, held - mn)
        sell = min(unit, above_min) if code == "SS" else above_min
        if sell <= 0:
            return 0.0, 0.0, "at or below minimum" if above_min <= 0 else "no unit size"
        return 0.0, sell, None
    if code in BUY_CODES:
        buy = max(0.0, target_holding(consolidated, held, mn, mx, unit) - held)
        if buy > 0:
            return buy, 0.0, None
        if mx > 0 and held >= mx:
            return 0.0, 0.0, "at maximum"
        if (consolidated or "").upper() == "ADD" and mn > 0 and held >= mn:
            return 0.0, 0.0, "already at minimum or more"
        return 0.0, 0.0, "no amount"
    return 0.0, 0.0, None


def stock_suppression(consolidated: Optional[str], held_anywhere: bool, accounts: Iterable[dict]) -> Optional[str]:
    """Stock-level "nothing to do" reason: only when EVERY account says so. accounts = [{held, min, max}, ...]."""
    ca = (consolidated or "").upper()
    accts = list(accounts)
    if not accts or not held_anywhere:
        return None
    if ca == "ADD" and all(a["min"] > 0 and a["held"] >= a["min"] for a in accts):
        return "ALREADY ESTABLISHED — every account is at its minimum or more"
    if ca == "INCREASE" and all(a["max"] > 0 and a["held"] >= a["max"] for a in accts):
        return "AT CEILING — every account is at its maximum"
    if ca == "REDUCE" and all(a["held"] <= a["min"] for a in accts):
        return "AT FLOOR — no account holds more than its minimum"
    return None
