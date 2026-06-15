# TASK 5 — Backfill 12+ months history and re-run outcome validation

## Goal
~4 months of derive history means most rules have n<50 fires; edge numbers are
noise. Backfill at least 12 months of derives + firing outcomes so the scorecard
CIs (AGENT_WORK_37) have real samples.

## Scope
- Inventory FIRST: oldest export_date per hist_* source. If raw history itself
  doesn't go back 12 months, write what exists + what source files would be
  needed in DEV_HANDOFF.md, backfill whatever range IS available, and continue.
- `etl/backfill_derives.py` — extend/use to derive all available historical
  anchor dates; then `etl/compute_firing_outcomes.py` over the full range.
- Out of scope: loading new external data sources; touching rule definitions.

## Acceptance criteria
- DEV_HANDOFF.md report: date range derived, rows per drv_* family, scorecard
  before/after — how many rules cross n≥100, which rules' edge flipped sign.
- Derives remain idempotent; long batch run is fine (checkpoint progress notes).

## How to verify (combined test round)
- Spot-check 3 random historical dates: drv_actionable rows exist,
  meta_derived_run SUCCESS; v_rule_scorecard n_fires increased vs before;
  pytest passes.

## Constraints
- Follow CLAUDE.md. Run AFTER Tasks 3/4 so backfilled dates get the new status
  tracking and quote logic.
