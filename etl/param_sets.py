"""
Parameter-set overlay (Phase 3 — docs/rule_engine_redesign.md).

A parameter set (ref_trig_param_set + ref_trig_param_value) is a named, versioned
collection of tunable values — atomic thresholds, weights, and sigmoid k/x0 —
that overrides the values stored directly on ref_trig_atomic_rule. Exactly one
set can be active (is_active=TRUE). With no active set, the engine uses the base
values and behaves exactly as before (zero change).

This module is consumed by etl/derive_cat_atomic_input.load_trig_rules, the single
point where atomic-rule definitions are loaded for scoring, so an active set
flows through the entire engine without touching the canonical rule rows.

ML (etl/ml_tune_thresholds.py) writes a new set, you backtest, then activate it.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger("etl.param_sets")

# Scalar params that map directly onto a rule-dict key.
_SCALAR_PARAMS = {"brkeout_from", "brkeout_to", "wt_below", "wt_between", "wt_above"}
# Params that live inside the score_params JSON (sigmoid).
_SCORE_PARAMS = {"k", "x0"}


def get_active_param_set_id(session: Session) -> Optional[int]:
    """Return the active param_set_id, or None if the feature is unused/absent."""
    try:
        return session.execute(text(
            "SELECT param_set_id FROM ref_trig_param_set WHERE is_active = TRUE LIMIT 1"
        )).scalar()
    except Exception:
        # Table not present yet (pre-migration) — feature simply inactive.
        return None


def apply_active_param_set(session: Session, rules_by_name: dict) -> Optional[int]:
    """Overlay the active param set onto a {rule_name: rule_dict} map IN PLACE.

    Atomic param values key by atomic_rule_id (target_kind='atomic'); they are
    joined back to rule_name so they can be applied to the dict load_trig_rules
    builds. Returns the param_set_id applied, or None if no active set.
    """
    pid = get_active_param_set_id(session)
    if pid is None:
        return None
    try:
        rows = session.execute(text("""
            SELECT a.rule_name, pv.param_name, pv.param_value
            FROM ref_trig_param_value pv
            JOIN ref_trig_atomic_rule a
              ON a.atomic_rule_id::text = pv.target_id
            WHERE pv.param_set_id = :pid AND pv.target_kind = 'atomic'
              AND a.rule_name IS NOT NULL
        """), {"pid": pid}).mappings().all()
    except Exception as e:
        log.warning("param-set overlay skipped: %s", e)
        return None

    n = 0
    for r in rows:
        rule = rules_by_name.get(r["rule_name"])
        if rule is None or r["param_value"] is None:
            continue
        pname = r["param_name"]
        pval = float(r["param_value"])
        if pname in _SCALAR_PARAMS:
            rule[pname] = pval
            n += 1
        elif pname in _SCORE_PARAMS:
            sp = rule.get("score_params")
            if not isinstance(sp, dict):
                sp = {}
            sp[pname] = pval
            rule["score_params"] = sp
            # An active sigmoid param implies sigmoid scoring.
            if (rule.get("scoring_mode") or "jump") == "jump":
                rule["scoring_mode"] = "sigmoid"
            n += 1
    if n:
        log.info("param-set %s applied: %d overrides across %d rules", pid, n, len(rules_by_name))
    return pid
