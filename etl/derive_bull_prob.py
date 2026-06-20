"""
Phase C — score bull_prob and bull_agreement at derive time.

Reads the active ref_bull_model row (is_active=TRUE) + drv_cat_atomic_input
for the current date, then UPDATEs drv_actionable.bull_prob and
drv_actionable.bull_agreement in place.

bull_prob:       logistic probability the symbol is up 20d from today.
bull_agreement:  fraction of contributing signals that are > 0 (bullish).

Idempotent: clears the two columns for as_of_date=D before computing.
Called from derive_all() after derive_actionable().
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.derive_bull_prob")


def _sigmoid(z: float) -> float:
    if z > 500:
        return 1.0
    if z < -500:
        return 0.0
    return 1.0 / (1.0 + math.exp(-z))


def _load_active_model(s: Session) -> Optional[dict]:
    """Return the active ref_bull_model row as a dict, or None."""
    try:
        row = s.execute(text("""
            SELECT model_id, feature_names, coefficients, intercept
            FROM ref_bull_model
            WHERE is_active = TRUE
            LIMIT 1
        """)).mappings().first()
    except Exception as e:
        log.debug("ref_bull_model not found (%s) — skip bull_prob scoring", e)
        return None
    if row is None:
        log.debug("No active ref_bull_model — skip bull_prob scoring")
        return None
    feat = row["feature_names"]
    coef = row["coefficients"]
    if isinstance(feat, str):
        feat = json.loads(feat)
    if isinstance(coef, str):
        coef = json.loads(coef)
    return {
        "model_id":     row["model_id"],
        "feature_names": feat,
        "coefficients":  coef,
        "intercept":     float(row["intercept"]),
    }


def derive_bull_prob(session: Session, as_of_date: date,
                     parent_run_id: Optional[int] = None) -> int:
    """Score bull_prob + bull_agreement for every symbol in drv_actionable
    for as_of_date.  Returns number of rows updated."""

    model = _load_active_model(session)
    if model is None:
        log.info("derive_bull_prob: no active model — columns remain NULL")
        return 0

    features = model["feature_names"]
    coef_map = model["coefficients"]
    intercept = model["intercept"]

    if not features:
        log.warning("derive_bull_prob: active model has empty feature_names")
        return 0

    coefs = [float(coef_map.get(f, 0.0)) for f in features]

    # Clear existing values for this date
    session.execute(text("""
        UPDATE drv_actionable
           SET bull_prob = NULL, bull_agreement = NULL
         WHERE as_of_date = :d
    """), {"d": as_of_date})

    # Fetch current feature values from drv_cat_atomic_input
    # Build column list; use tos_symbol (convention #15)
    col_parts = ", ".join(f'COALESCE(ci."{f}"::float, 0)' for f in features)
    sql = text(f"""
        SELECT ci.tos_symbol,
               {col_parts}
        FROM drv_cat_atomic_input ci
        WHERE ci.as_of_date = :d
          AND ci.tos_symbol IS NOT NULL
    """)
    rows = session.execute(sql, {"d": as_of_date}).fetchall()

    if not rows:
        log.info("derive_bull_prob: no drv_cat_atomic_input rows for %s", as_of_date)
        return 0

    batch = []
    n_feat = len(features)
    for row in rows:
        sym = row[0]
        feat_vals = [float(v) if v is not None else 0.0 for v in row[1:n_feat + 1]]

        # Logistic probability
        z = intercept + sum(c * x for c, x in zip(coefs, feat_vals))
        prob = _sigmoid(z)

        # Agreement: fraction of features with positive coefficient * positive value
        # A signal "points bullish" when coef > 0 and value > 0, or coef < 0 and value <= 0.
        # We report the share of signals that are bullish-pointing.
        n_contributing = sum(1 for c in coefs if abs(c) > 1e-9)
        if n_contributing > 0:
            n_bullish = sum(
                1 for c, x in zip(coefs, feat_vals)
                if abs(c) > 1e-9 and (
                    (c > 0 and x > 0) or (c < 0 and x <= 0)
                )
            )
            agreement = round(n_bullish / n_contributing, 3)
        else:
            agreement = None

        batch.append({
            "sym":  sym,
            "prob": round(prob, 4),
            "agr":  agreement,
            "d":    as_of_date,
        })

    if not batch:
        return 0

    # Update drv_actionable rows — only where a match exists
    session.execute(text("""
        UPDATE drv_actionable
           SET bull_prob      = :prob,
               bull_agreement = :agr
         WHERE as_of_date = :d
           AND tos_symbol  = :sym
    """), batch)

    # TASK_69: derive agreement_class from bull_prob direction vs
    # consolidated_action direction.  Same signals, no second calc.
    # tech_bull: bull_prob >= 0.5; tech_bear: bull_prob < 0.5
    # sent_bull: consolidated_action in buy family; sent_bear: sell family
    _BUY_FAMILY  = {"INCREASE","ADD","BS","BM","BMN","BW","BSW","BR","BC","BRW","B"}
    _SELL_FAMILY = {"REMOVE","REDUCE","SS","STM","SA","SO","SW","SWW","S"}

    prob_map = {row["sym"]: row["prob"] for row in batch}

    # Load consolidated_action for this date
    ca_rows = session.execute(text("""
        SELECT tos_symbol, consolidated_action
        FROM drv_actionable
        WHERE as_of_date = :d
          AND tos_symbol IS NOT NULL
    """), {"d": as_of_date}).fetchall()

    agr_batch = []
    for ca_row in ca_rows:
        sym = ca_row[0]
        ca  = (ca_row[1] or "").upper().strip()
        prob = prob_map.get(sym)
        if prob is None:
            agr_batch.append({"sym": sym, "d": as_of_date, "cls": None})
            continue
        tech_bull = prob >= 0.5
        sent_bull = ca in _BUY_FAMILY
        sent_bear = ca in _SELL_FAMILY
        if tech_bull and sent_bull:
            cls = "agree_bull"
        elif (not tech_bull) and sent_bear:
            cls = "agree_bear"
        elif tech_bull and sent_bear:
            cls = "split_tech_bull"
        elif (not tech_bull) and sent_bull:
            cls = "split_tech_bear"
        else:
            cls = "neutral"
        agr_batch.append({"sym": sym, "d": as_of_date, "cls": cls})

    if agr_batch:
        session.execute(text("""
            UPDATE drv_actionable
               SET agreement_class = :cls
             WHERE as_of_date = :d
               AND tos_symbol  = :sym
        """), agr_batch)

    n = len(batch)
    log.info("derive_bull_prob: scored %d symbols for %s (model_id=%d)",
             n, as_of_date, model["model_id"])
    return n
