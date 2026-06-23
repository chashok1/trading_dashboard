"""
TASK_70 — Calibrated Final Call (parallel, evaluation-only).

Derives final_action_cal / final_code_cal / final_side_cal / fc_strength_cal
from bull_prob probability bands, written to drv_actionable.

Probability → action mapping (same _FC_SCALE vocab as the existing final_call):
  bull_prob >= 0.65  → strong buy  (BM,  strength +2)
  0.55 <= prob < 0.65 → buy        (BS,  strength +2)
  0.45 <= prob < 0.55 → hold       (HOLD, strength  0)
  0.35 <= prob < 0.45 → reduce     (SS,  strength -2)
  prob < 0.35         → sell all   (SA,  strength -3)

Feasibility gates (read-only from drv_actionable, NOT from _compute_final_call):
  - If consolidated_action is 'REMOVE'/'SA' for a HELD symbol → force SA.
  - If symbol is NOT held and calibrated call is not a buy family → force HOLD
    (same don't-initiate guard as the existing final call).
  - If over category max (current_position_dollar > target_max_dollar)
    and cal says buy → force HOLD.

NULL-safe: if bull_prob is NULL the four *_cal columns remain NULL.
Idempotent: clears the four columns before computing (UPDATE … SET … = NULL).
Non-critical: any exception inside this function is caught by derive_all().
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_final_call_cal")

# Same _FC_SCALE as derive_actionable.py (mirrored here for self-containment).
_FC_SCALE: dict[str, int] = {
    "SA": -3, "REMOVE": -3,
    "SS": -2, "STM": -2, "REDUCE": -2,
    "OVER_MAX": -1,
    "HOLD": 0, "NONE": 0,
    "BS": 2, "INCREASE": 2, "BMN": 2, "ADD": 2, "BM": 2,
}

# Probability thresholds → (label, code, side, strength)
_PROB_BANDS: list[tuple[float, str, str, str, int]] = [
    # (min_prob, label, code, side, strength)
    (0.65, "BUY MORE",  "BM",   "buy",     2),
    (0.55, "BUY SOME",  "BS",   "buy",     2),
    (0.45, "HOLD",      "HOLD", "neutral", 0),
    (0.35, "SELL SOME", "SS",   "sell",   -2),
    (0.00, "SELL ALL",  "SA",   "sell",   -3),
]

# BUY family codes (same as derive_bull_prob.py _BUY_FAMILY)
_BUY_CODES = {"INCREASE", "ADD", "BS", "BM", "BMN"}

# SELL-exit codes (REMOVE / SA) — treated the same as the existing gate
_EXIT_CODES = {"REMOVE", "SA"}


def _prob_to_raw(prob: float) -> tuple[str, str, str, int]:
    """Map a probability to (label, code, side, strength) via bands."""
    for min_p, lbl, code, side, strength in _PROB_BANDS:
        if prob >= min_p:
            return lbl, code, side, strength
    # Fallback (should not happen — last band covers 0.0+)
    return "HOLD", "HOLD", "neutral", 0


def derive_final_call_cal(
    session: Session,
    as_of_date: date,
    parent_run_id: Optional[int] = None,
) -> int:
    """Compute calibrated Final Call columns for as_of_date.

    Returns number of rows updated (0 when no active model / no bull_prob values).
    """
    # Step 1: check whether any bull_prob values exist for this date.
    has_prob = session.execute(text("""
        SELECT 1 FROM drv_actionable
        WHERE as_of_date = :d AND bull_prob IS NOT NULL
        LIMIT 1
    """), {"d": as_of_date}).first()

    if not has_prob:
        log.info(
            "derive_final_call_cal: no bull_prob for %s — *_cal columns stay NULL",
            as_of_date,
        )
        return 0

    # Step 2: clear existing *_cal values for idempotency.
    session.execute(text("""
        UPDATE drv_actionable
           SET final_action_cal = NULL,
               final_code_cal   = NULL,
               final_side_cal   = NULL,
               fc_strength_cal  = NULL
         WHERE as_of_date = :d
    """), {"d": as_of_date})

    # Step 3: load the inputs — bull_prob + gating fields from drv_actionable.
    rows = session.execute(text("""
        SELECT tos_symbol, bull_prob,
               consolidated_action,
               held_today,
               current_position_dollar,
               target_max_dollar
        FROM drv_actionable
        WHERE as_of_date = :d
          AND bull_prob IS NOT NULL
          AND tos_symbol IS NOT NULL
    """), {"d": as_of_date}).fetchall()

    if not rows:
        return 0

    batch: list[dict] = []
    for row in rows:
        sym      = row[0]
        prob     = float(row[1])
        ca       = (row[2] or "").upper().strip()
        held     = bool(row[3]) if row[3] is not None else False
        curr_pos = float(row[4] or 0)
        tgt_max  = float(row[5]) if row[5] is not None else None

        # Raw mapping from probability bands
        lbl, code, side, strength = _prob_to_raw(prob)

        # ── Gate 1: strategic exit (REMOVE/SA on held symbol) ──────────────
        # If the outlook sources say REMOVE on a held symbol, honour that
        # regardless of bull_prob (same logic as _compute_final_call gate 1).
        if ca in _EXIT_CODES and held:
            lbl, code, side = "SELL ALL", "SA", "sell"
            strength = _FC_SCALE["SA"]

        # ── Gate 2: don't-initiate guard ───────────────────────────────────
        # Symbol not currently held and cal call is not a buy → hold.
        elif not held and code not in _BUY_CODES:
            lbl, code, side = "HOLD", "HOLD", "neutral"
            strength = 0

        # ── Gate 3: over-max guard ──────────────────────────────────────────
        # Cal says buy but position already exceeds the category ceiling → hold.
        elif (
            code in _BUY_CODES
            and tgt_max is not None
            and tgt_max > 0
            and curr_pos > tgt_max
        ):
            lbl, code, side = "HOLD", "HOLD", "neutral"
            strength = 0

        batch.append({
            "sym":      sym,
            "d":        as_of_date,
            "f_action": lbl,
            "f_code":   code,
            "f_side":   side,
            "f_str":    strength,
        })

    if not batch:
        return 0

    session.execute(text("""
        UPDATE drv_actionable
           SET final_action_cal = :f_action,
               final_code_cal   = :f_code,
               final_side_cal   = :f_side,
               fc_strength_cal  = :f_str
         WHERE as_of_date = :d
           AND tos_symbol  = :sym
    """), batch)

    n = len(batch)
    log.info(
        "derive_final_call_cal: updated %d rows for %s", n, as_of_date
    )
    return n
