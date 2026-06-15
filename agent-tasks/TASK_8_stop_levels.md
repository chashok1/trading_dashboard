# TASK 8 — Risk layer: stop/exit levels per actionable row

## Goal
Sizing exists (AMT$); exits don't. Add a suggested stop level per
held/BUY-family symbol, plus an "unproven rule" marker on AMT$ when the driving
rule's confidence (from AGENT_WORK_37) is 'unproven'.

## Risk-policy defaults (user-tunable — do NOT block on questions)
Implement with these defaults, ALL as ref_settings knobs, and list them
prominently in DEV_HANDOFF.md for the user to review/change:
- `stop_mode` = 'trade_line_or_pct' — stop = MAX(a_trade_value,
  last_price × (1 − stop_pct)); if a_trade_value is NULL use the pct leg only.
- `stop_pct` = 0.08 (8% below current price).
- For SELL-family rows: stop column shows the same level annotated as
  "exit below" (no separate logic).
Document the formula in docs/actionable_logic.md (one section + CLAUDE.md
Lookup row).

## Scope
- `etl/derive_actionable.py` + db/baseline.sql — `stop_level` column on
  drv_actionable, derived per above. Idempotent.
- `ref_settings` seeds for the knobs (db/seeds_*.sql pattern).
- `web/actionable.js` — show stop next to AMT$ (muted, e.g. "stop 70.40");
  low-confidence marker on AMT$ where driving rule is 'unproven'.
- Out of scope: changing AMT$ math, order execution, alerts, portfolio-level
  constraints.

## Acceptance criteria
- Every held/BUY-family row shows a stop level; knobs editable via ref_settings
  (+ /ref screen) and a re-derive picks them up.
- Defaults + formula listed in DEV_HANDOFF.md for user review.

## How to verify (combined test round)
- Recompute stop by hand for 2 symbols (one with a_trade_value, one without);
  change stop_pct in ref_settings, re-derive, confirm the change; pytest.

## Constraints
- Follow CLAUDE.md. tos_symbol everywhere. SQL ≤965 bytes.
