# TASK 6 — Hold-out validation for param sets (anti-overfit gate)

## Goal
`ml_tune_thresholds.py` profiles (e.g. ml-sweep-20d) are tuned on the same data
they're scored on. Add a chronological train/hold-out split so no param set can
be activated without out-of-sample evidence. DEPENDS ON TASK 5 (needs history).

## Scope
- `etl/ml_tune_thresholds.py` — split firing-outcome dates chronologically
  (first ~70% train / last ~30% hold-out); tune on train only; report edge on
  hold-out; refuse (warn) to save a profile whose hold-out edge ≤ 0 or ≤ half
  its train edge.
- `api/routers/rules.py` + `web/param_sets.js` — show train vs hold-out edge
  side by side on the param-set screen; "unvalidated" tag for legacy profiles.
- Out of scope: new ML methods; auto-activation.

## Acceptance criteria
- Tuning output shows both numbers; an intentionally overfit run gets flagged.
- Existing profiles marked unvalidated until re-run.

## How to verify (combined test round)
- Run a tune on real data; confirm split is chronological (not random); check
  the param-set screen; pytest.

## Constraints
- Follow CLAUDE.md, docs/rule_tuning_and_outcomes.md, docs/rule_engine_redesign.md.
