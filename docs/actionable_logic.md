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
| RR | outlook_modifier | Dense — exact snapshot vs. prior snapshot | `_action_standing` | `loads_prior_day_data` shifts the compare date back 1 day |
| ETF | outlook_modifier | Weekly bundle, SUN anchor + intra-week `etfchg` patches | `_action_standing` | NEUTRAL outlook = removed from list |
| II | outlook_modifier | Monthly bundle, latest snapshot ≤ D + intra-month `iichg` patches | `_action_standing` | NEUTRAL outlook = removed from list |
| CALL | outlook_modifier | Standing model — 30-day sparse window | `_action_call_standing` | see below |
| PS | rank | Weekly, FRI anchor; lower rank number = better | `_action_rank` | |
| SSS | rank_pct_delta | Weekly, MON anchor; driven by `pct_delta` | `_action_sss_pct_delta` | INCREASE/REDUCE informational only |

### Classifier rules

**`_action_standing`** (RR / ETF / II) — held-agnostic standing-list
classifier. Presence on the current list with a positive weight is a buy
verdict every period, not just on first appearance; held-vs-not is resolved
downstream by `derive_actionable` suppression:

- base > 0 → ADD (positive weight on the current list)
- base < 0 → REMOVE (negative weight on the current list)
- base absent & prev present → REMOVE (dropped from the list)
- base = 0, or absent in both snapshots → silent

It never emits INCREASE / REDUCE / HOLD — only ADD, REMOVE, or silent.

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
- both present, not held: rank improved → INCREASE; degraded → silent
  (weakening — don't initiate); unchanged → ADD (standing recommendation)

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

**Action labels.** The Action badge shows an instructional label, not the
raw code: ADD → `BUY→MIN`, INCREASE → `BUY +1U`, REDUCE → `SELL −1U`,
REMOVE → `SELL ALL`, HOLD → `HOLD`. When the held position exceeds the
category Max (`current_position_dollar > target_max_dollar`, REMOVE
excepted), the badge overlays `SELL→MAX` in REDUCE orange (so the sell
intent reads at a glance) and the original label is shown underneath in
small bold letters tinted with that action's own color ("was BUY +1U" in
INCREASE green, "was BUY→MIN" in ADD blue, etc.). The stored `consolidated_action`,
`winning_source`, Reason, chip count, and sort severity are all unchanged
— it's a pure display overlay, no derive change. Summary/filter chips use
the same instructional labels (SELL ALL, SELL −1U, BUY +1U, BUY→MIN, HOLD,
— for no-action; ALL stays "ALL"). A synthetic `SELL→MAX` chip counts and
filters over-allocation rows (any row where the overlay fires); those rows
are also counted in their underlying action chip.

**AMT$** shows the delta for actionable rows: ADD / INCREASE = target −
position, REMOVE / REDUCE = position − target, all clamped ≥ 0 (suppressed
rows → 0). HOLD / no-action rows show the current held dollars, not a delta.
When the position exceeds the category Max (REMOVE excepted), AMT$
overrides to `position − Max` — the trim back to the ceiling — paired with
the `SELL→MAX` badge overlay.

**Metric column.** A generic, sortable column showing the *selected*
source's decision metric — rank for PS, `pct_delta` for SSS, the outlook
weight for RR / ETF / II / CALL. The value is read from the row's
`source_actions[source]` entry and is blank when the Source filter is "All".
`/api/actionable/sources` supplies each source's `base_weight_method` so the
screen knows the metric's natural sort direction.

**Snapshot column.** Shows the winning source's effective snapshot date —
the date the underlying data record is for (`drv_outlook_action.as_of_date`,
carried into `source_actions.snapshot_date` by `derive_actionable.py`). The
per-source table and the comparison panel show the same date per source. All
snapshot dates render as MM/DD (no year). Grid column order: Metric, Symbol,
Action, AMT$, Source, Reason, Snapshot, Other Sources, then the sizing
columns.

**Per-source sort.** When a source is chosen in the Source filter:

- *Way 1 (default):* sort by action severity (REMOVE → HOLD), then by the
  Metric in its best-first direction — rank ascending (rank 1 tops each
  action group); outlook weight / pct descending.
- *Way 2:* clicking the Metric column header sorts purely by the Metric,
  first click in the best-first direction (rank 1 at the very top for PS).

Choosing a source clears any active column sort so Way 1 applies. The Source
filter matches a row when the chosen source is its winning source **or**
appears among its other sources; other-source pills are ordered by action
severity.

**Snooze toggle.** The first grid column is a per-row Snooze button. It
logs a `SKIPPED` user action for (snapshot date, symbol) via
`POST /api/actionable/{symbol}/action`; snoozed rows are hidden unless
"Show acted/snoozed" is on. The action is keyed to the snapshot date, so a
snooze applies only to that date — the next data load creates a new
snapshot date and the action shows again. When a snoozed row is visible
the button reads "Un-snooze" and clears the `SKIPPED` row (`DELETE` on the
same endpoint).

**Per-source inline comparison.** Each row of the drilldown's "Per-source
actions" table expands on click to a current-vs-previous record comparison
(`/api/actionable/comparison`). It is source-agnostic: every non-housekeeping
column of the source table is introspected and shown for both records with a
Δ column. A side whose `base_weight` / `prev_weight` is NULL (symbol not in
that bundle) renders blank — no stale pre-drop record is resurrected. Only
the classifier's decision-driving field(s) are highlighted — `pct_delta` for
SSS, `rank` for PS, `outlook` (+ `outlook_modifier`) for the outlook
sources — keyed off `base_weight_method`.

**Percentages.** `pct_delta` (SSS) is stored as a fraction and shown as a
percentage (× 100, `%` suffix) everywhere it surfaces — the Metric column,
comparison panel, per-source table and hover popover format it client-side;
the SSS action `reason` text (e.g. `pct_delta +5% -> +6.1% (rising)`) is
percentage-formatted in `_action_sss_pct_delta` via `_pct_str`. The stored
`hist_sss` value is never changed and the classifier keeps comparing the raw
fraction.

## Re-derive

After editing this logic: `python rebuild_actionable.py` runs
`derive_outlook_action` then `derive_actionable` for the recent dates, then
restart the app.
