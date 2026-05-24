# Actionable Logic

Deep-dive on the outlook-action → actionable path. `CLAUDE.md` carries only a
one-line pointer to this file in its Lookup index; keep the detail here.

## Overview

Two idempotent derive stages (`DELETE WHERE as_of_date=D` then INSERT):

1. `etl/derive_outlook_action.py` — evaluates the 6 sources in
   `ref_outlook_source`, writes one row per (symbol, source) into
   `drv_outlook_action`. Only real signals are written; a `None` action row
   is skipped.
2. `etl/derive_actionable.py` — consolidates all per-source actions plus
   action-type rule-group fires into one row per symbol in `drv_actionable`:
   picks a winner, resolves the sizing category, computes
   `suggested_target_dollar`, and applies position-aware suppression.

`web/actionable.js` renders `drv_actionable`.

## Diagrams

- `docs/diagrams/1_actionable_data_flow.svg` — **data flow**: trigger sources
  to ETL load, the derive cascade, `drv_actionable`, the API, the Actionable
  screen, and the `user_action_log` feedback.
- `docs/diagrams/10_actionable_logic.svg` — **decision logic**: the 6 outlook
  sources to their 4 classifiers to `drv_outlook_action`, the consolidation
  winner sort, category/sizing/suppression, and `drv_actionable`.

Keep both diagrams in sync whenever this logic changes.

## Stage 1 — per-source action

`ref_outlook_source` (6 active: RR, CALL, ETF, II, SSS, PS) drives the loop.
`base_weight_method` selects the comparison window + classifier. Each source
runs inside its own SAVEPOINT so one failure doesn't abort the rest.

| Source | Method | Cadence / window | Classifier | Notes |
|---|---|---|---|---|
| RR | outlook_modifier | Dense — exact snapshot vs. prior snapshot | `_action_outlook_v2` | `loads_prior_day_data` shifts the compare date back 1 day |
| ETF | outlook_modifier | Weekly bundle, SUN anchor + intra-week `etfchg` patches | `_action_outlook_v2` | NEUTRAL outlook = removed from list |
| II | outlook_modifier | Weekly bundle, MON anchor + `iichg` patches | `_action_outlook_v2` | |
| CALL | outlook_modifier | Standing model — 30-day sparse window | `_action_call_standing` | see below |
| PS | rank | Weekly, FRI anchor; lower rank number = better | `_action_rank` | |
| SSS | rank_pct_delta | Weekly, MON anchor; driven by `pct_delta` | `_action_sss_pct_delta` | INCREASE/REDUCE informational only |

### Classifier rules

**`_action_outlook_v2`** (RR / ETF / II) — held-agnostic:

- new (no prior) & base > 2 → ADD; base ≤ 2 → silent
- dropped (no current) & prev > 0 → REMOVE; prev ≤ 0 → silent
- both present: (prev > 0 & base ≤ 0) or (prev ≥ 0 & base < 0) → REMOVE;
  base > 0 & base > prev → INCREASE; base > 0 & base < prev → REDUCE;
  else silent

**`_action_call_standing`** (CALL) — standing-recommendation model:

- Current = weight of the most recent row in the 30-day window. Prior =
  weight of the most recent *older* in-window row whose weight differs from
  current.
- current ≤ 0 → REMOVE if held, else silent
- current > 0 with a prior different weight > 0: higher → INCREASE;
  lower → REDUCE if held, else ADD
- current > 0 otherwise (flat all window, or prior ≤ 0) → ADD — a positive
  call is a standing ADD until acted on
- no CALL row in the 30-day window → silent

**`_action_rank`** (PS) — lower rank number is better:

- new → ADD; dropped → REMOVE if held, else silent
- both present, held: rank improved → INCREASE; degraded → REDUCE;
  same → HOLD
- both present, not held: rank improved → INCREASE; else ADD

**`_action_sss_pct_delta`** (SSS) — driven by `pct_delta` (% Delta Since
Initial); analyst rank is display-only:

- new → ADD; dropped → REMOVE if held, else silent
- on the list both weeks: pct_delta < 0 → REMOVE; rising → INCREASE;
  falling → REDUCE; steady → HOLD
- SSS INCREASE/REDUCE are demoted — they appear under Other Sources but
  never become the consolidated action.

## Stage 2 — consolidation (`derive_actionable.py`)

**Winner.** Every per-source action for the date, plus any fired action-type
rule groups (synthetic `RULES:<code>` candidates), compete in one sort:
`(-ACTION_RANK, priority ASC)`, where
`ACTION_RANK = REMOVE 4 · REDUCE 3 · INCREASE 2 · ADD 1 · HOLD 0`.
Most aggressive wins; ties broken by `investment_priority` /
rule-group `priority` (lower = stronger). SSS INCREASE/REDUCE are excluded
from this contest.

**Category.** PS/ETF/ETFCHG winners look up `ref_asset_allocation` by the
symbol's `asset_class`; other sources use `position_category`. That yields
`min_dollar`, `max_dollar`, `units`, `maintain_min_position`.

**Sizing — `suggested_target_dollar`:**

| Action | Sizing |
|---|---|
| REMOVE | target 0; suppressed "NOT HELD" if no position |
| ADD | target = MIN; if held ≥ MIN → suppressed "ALREADY ESTABLISHED", target = held |
| INCREASE | not held → `min(MIN + Units, MAX)` (catch-up); held ≥ MAX → suppressed "AT CEILING"; else `min(held + Units, MAX)` |
| REDUCE | `maintain_min` on & held ≤ MIN → suppressed "AT FLOOR"; else `max(MIN, held − Units)`; no maintain → `max(0, held − Units)` |
| HOLD / none | target = current held dollars |

Suppression keeps the action but records a `suppressed_reason`, so the user
still sees what the system would have recommended.

## Display (`web/actionable.js`)

AMT$ always shows the delta: ADD / INCREASE = target − position,
REMOVE / REDUCE = position − target, all clamped ≥ 0 (suppressed rows → 0).

## Re-derive

After editing this logic: `python rebuild_actionable.py` runs
`derive_outlook_action` then `derive_actionable` for the recent dates, then
restart the app.
