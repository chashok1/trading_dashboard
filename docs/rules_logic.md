# Rules Engine Logic

Deep-dive on atomic rules, composite rules, rule groups, position-rule
suppressions, drv_trig / drv_stks / drv_rule_outcome, and the Rules authoring
screen + dryrun preview. `CLAUDE.md` carries only a one-line pointer to this
file in its Lookup index; keep the detail here.

## Overview

Three tiers of authoring, one evaluation cascade per (symbol, date):

1. **Atomic rules** (`ref_trig_atomic_rule`) — single-condition predicates that
   score a measured indicator value into a weight via one of three curves.
   Evaluated per symbol by `eval_atomic_rule()` in `etl/derive.py`.
2. **Composite rules** (`ref_trig_composite_mapping`) — named collections of
   members (atomic, inline-data, or nested-composite) whose contributions are
   summed to a score. A composite "fires" when any member contributes (score ≠ 0
   on at least one member), subject to an optional precondition gate.
   Scores written to `drv_trig` (atomic members only) and the authoritative
   `drv_stks.triggered_composite_ids` JSONB (all member kinds).
3. **Rule groups** (`ref_trig_rule_group` + `ref_trig_group_member`) — AND/OR
   boolean expressions over composite codes that produce an `action_label` (ADD,
   REMOVE, etc.) and a priority. Fired groups are injected as synthetic
   candidates into `derive_actionable`.

All three tiers are read-only during the derive cascade; edits take effect only
after a re-derive. The Rules screen and composite editor provide a dryrun
preview that runs on live data without writing anything.

## Diagrams

- `docs/diagrams/7_rules_engine_logic.svg` — **evaluation pipeline**: indicator
  inputs through atomic scoring, composite scoring, rule groups, `drv_stks`,
  and `drv_actionable`.
- `docs/diagrams/4_rules_authoring_data_flow.svg` — **authoring data flow**:
  the Rules and Rule Groups screens through the CRUD API into the `ref_trig_*`
  tables, the dryrun branch, the dormancy gate, and the re-derive step.

Keep these diagrams in sync whenever this logic changes.

## Atomic rules

### Storage — `ref_trig_atomic_rule`

| Column | Type | Purpose |
|---|---|---|
| `atomic_rule_id` | INTEGER PK | Stable numeric ID referenced by composite mappings |
| `rule_name` | TEXT | Human name; also the `excel_header` key for column resolution via `ref_ma_columns` |
| `ma_column_name` | TEXT | Fallback FQN (`drv_ma.col` or `drv_cat_atomic_input.col`) when `rule_name` lookup fails |
| `brkeout_from` / `brkeout_to` | NUMERIC | Zone boundaries `[lo, hi]` |
| `wt_below` / `wt_between` / `wt_above` | NUMERIC | Weight returned when `value < lo`, `lo ≤ value ≤ hi`, or `value > hi` |
| `scoring_mode` | TEXT | `jump` (default) · `linear` · `sigmoid` |
| `score_params` | JSONB | `{"k": float, "x0": float}` for sigmoid |
| `category` | TEXT | Grouping label shown in the UI (Trend, Momentum, Volatility, Sentiment) |
| `intent_text` | TEXT | Human description of what the rule measures |
| `deprecated_at` | TIMESTAMPTZ | Soft-delete; `NULL` = active |

### Column resolution

`_resolve_atomic_input_column(session)` in `etl/derive.py` builds a map
`{atomic_rule_id → (table_name, column_name)}` in six-step priority order:

1. `ref_ma_columns` lookup by `rule_name` where `drv_cat_table = 'drv_cat_atomic_input'`
2. `ref_ma_columns` lookup by `rule_name` (any `drv_cat_table`)
3. Legacy `_MA_COL_MAP` dict keyed on `rule_name`
4. `ma_column_name` parsed as FQN `table.column`
5. `ref_ma_columns` lookup by `ma_column_name` as bare key
6. Legacy `_MA_COL_MAP` keyed on `ma_column_name`

Unresolved rules evaluate to 0 and a warning is logged. The Rules Health page
(`/rules-health`) reports unresolved count via `GET /api/rules/health`.

### Scoring modes — `eval_atomic_rule(value, rule)`

All atomic-rule scoring flows through one function, used consistently by the
derive cascade, dryrun preview, and the health endpoint.

| Mode | Behaviour |
|---|---|
| `jump` | Step function: `wt_below` if `v < lo`; `wt_between` if `lo ≤ v ≤ hi`; `wt_above` if `v > hi` |
| `linear` | Linear interpolation: clamped to `wt_below` / `wt_above` at the boundary, `wt_below + t*(wt_above - wt_below)` for `t = (v-lo)/(hi-lo)` inside |
| `sigmoid` | S-curve: `wt_below + σ*(wt_above - wt_below)` where `σ = 1/(1+exp(-k*(v-x0)))`, `k` and `x0` from `score_params` (defaults: `k=0.1`, `x0=(lo+hi)/2`) |

`value = None` always returns 0.0. Text values that cannot be cast to float
also return 0.0.

### Input data

Atomic rules read from a wide row that is a `drv_ma LEFT JOIN drv_cat_atomic_input`
joined by `(as_of_date, symbol)`. `_fetch_eval_rows()` constructs the exact
SELECT list from the column map so no unnecessary columns are pulled. Columns
from `drv_cat_atomic_input` are prefixed `ai_` in the Python dict to avoid
name collisions; `_read_atomic_value()` handles the routing transparently.

`drv_cat_atomic_input` is the sole surviving `drv_cat_*` table (migrations 33
and 34 collapsed the others). It holds pre-computed indicator values such as
`bb_direction`, `trade_cross_over`, `trend_rule`, etc.

## Composite rules

### Storage — `ref_trig_composite_mapping`

There is no separate `ref_trig_composite_rule` header table. A composite rule
is identified by its `composite_rule_code` (TEXT) and is fully represented by
its one-or-more rows in the mapping table. Shared metadata (`category`,
`intent_text`, `precondition_expr`) is stored on every member row and must be
kept consistent; the API writes it to all rows atomically.

Each mapping row has a `member_kind` of `'atomic'`, `'data'`, or `'composite'`,
enforced by a check constraint:

| Kind | Key columns | Meaning |
|---|---|---|
| `atomic` | `atomic_rule_id` | References a row in `ref_trig_atomic_rule`; inherits that rule's full scoring definition |
| `data` | `data_column`, `data_brkeout_from/to`, `data_wt_*`, `data_scoring_mode`, `data_score_params` | Inline scoring rule — no shared atomic rule definition; column resolved the same way as atomic |
| `composite` | `nested_composite_code` | Pulls the already-scored child composite's numeric score; `member_multiplier` scales it |

`weight_override` applies to all three kinds: if a member fires (`w ≠ 0`) and
`weight_override` is set, that value replaces the computed weight before
summation.

Soft-delete: `deprecated_at IS NOT NULL` excludes the rule from all derives.

### Precondition gate — `_eval_precondition(expr, row)`

Before scoring any members, the engine evaluates `precondition_expr` against the
symbol's `drv_ma` row (extended with derived aliases). If the expression returns
false, the composite score is set to `NULL` (not 0) in `composite_scores` and
the code is skipped — child composites see `None` for that parent. If no
precondition is set, or if the expression fails to parse, the gate passes
(fails-open design).

Supported syntax: column names from `drv_ma`, derived aliases (`is_held`,
`is_etf`, `is_equity`, `has_position`), literals, comparisons (`==`, `!=`, `<`,
`<=`, `>`, `>=`, `in`, `not in`, `is None`, `is not None`), and boolean
operators (`and`, `or`, `not`). SQL synonyms (`=`, `<>`, `AND`, `OR`, `NOT`,
`IS NULL`, `IS NOT NULL`) are translated automatically.

### Evaluation order and firing rule

Composites are evaluated in topological order (children before parents) so
nested-composite members have their child scores ready. A topological sort with
cycle detection runs once at the start of `_derive_stks_impl`. Cycles are logged
and broken by defaulting the offending composite to unscored.

A composite **fires** when `n_member_hit > 0` (any member contributed a non-zero
weight), not when the net score is non-zero. This means a composite with
offsetting `+1` and `-1` members still counts as fired. This matches the
semantics of `drv_trig` post the 2026-05-17 fix.

## drv_trig

`drv_trig` holds per-`(as_of_date, symbol, composite_rule_code)` rows with:

| Column | Meaning |
|---|---|
| `score` | Sum of contributing atomic-member weights for this composite |
| `triggered` | `n_atomic_hit > 0` |
| `n_atomic_hit` | Count of atomic members that contributed a non-zero weight |

Note: `drv_trig` only accounts for `kind='atomic'` members (it reads the
`atomic_rule_id IS NOT NULL` subset of `ref_trig_composite_mapping`). The
authoritative composite score including `data` and nested-`composite` members
lives in `drv_stks.triggered_composite_ids` (JSONB array). Both are idempotent
(`DELETE WHERE as_of_date=D` then INSERT).

The Trace screen reads `drv_trig` to show per-rule fire status, computed value,
and didn't-fire reason for a symbol + date.

## drv_stks

`_derive_stks_impl` in `etl/derive.py` produces one row per `(as_of_date,
symbol)` with three JSONB columns:

| JSONB column | Shape | Written by |
|---|---|---|
| `triggered_atomic_ids` | `[{"rule_id": int, "weight": float, "value": float|null, "applied": bool}]` | Atomic evaluation loop |
| `triggered_composite_ids` | `[{"rule_id": str, "score": float, "n_member_hit": int}]` | Composite evaluation loop |
| `triggered_group_ids` | `[{"rule_group_code": str, "action": str, "priority": int}]` | Group evaluation loop |

`composite_label` (`BULLISH` / `BEARISH` / `NEUTRAL`) is a simple sign-of-score
composite outlook derived from `_composite_outlook()` over five outlook fields.
The derive is idempotent via `replace_for_date()`.

## Rule groups

Rule groups are defined in `ref_trig_rule_group` (one row per group) with
members in `ref_trig_group_member`. A group is either `group_type='action'`
(has an `action_label` such as `ADD`, `REMOVE`) or `group_type='logical'`
(no action label; used for nested composition only).

Each member row references a `member_code` (a composite rule code or another
group code) and a `logic_operator` (`AND` or `OR`). The sequence column
determines evaluation order.

The in-memory evaluator `_eval_group_inline()` walks the group tree with
cycle detection. Composite members look up `composite_results[member_code]`
(a bool). Nested group members recurse. An `AND` chain short-circuits on the
first false; `OR` evaluates all. Cycle nodes default to `False`.

Fired groups are appended to `drv_stks.triggered_group_ids` and injected as
`RULES:<group_code>` candidates in `derive_actionable` so they compete with
outlook-sourced actions.

## Position rules — `etl/position_rules.py`

Position rules are not trigger suppression in the ETL sense; they are sizing
and suppression guards applied during `derive_actionable`. They resolve the
correct `ref_asset_allocation` row for each symbol and constrain the
`suggested_target_dollar`.

Resolution path (three functions):

1. `_winning_source(session, symbol, as_of_date)` — finds the lowest-
   `investment_priority` source in `ref_outlook_source` that has data for the
   symbol on or before the date. Prefers the cached answer from
   `drv_actionable.winning_source` when available.
2. `resolve_symbol_category(session, symbol, as_of_date)` — for PS, ETF, and
   ETFCHG sources, reads the per-symbol `asset_class` from `hist_ps` /
   `hist_etf`; for all other sources uses the source's `position_category`
   from `ref_outlook_source`.
3. `resolve_position_rule(session, symbol, as_of_date)` — looks up
   `ref_asset_allocation` by the resolved category and returns
   `{min_dollar, max_dollar, units, maintain_min_position, winning_source,
   asset_class_source}`.

`classify_position_status(current_dollar, rule)` maps the current held dollar
amount to one of `BELOW_MIN`, `WITHIN`, `ABOVE_MAX`, `AT_FLOOR`, or
`NO_LIMIT`. The Actionable and Portfolio screens use this classification for
display. The sizing logic itself lives in `derive_actionable.py` (see
`docs/actionable_logic.md` for the REMOVE / ADD / INCREASE / REDUCE matrix).

## drv_rule_outcome and performance tracking

`drv_rule_outcome` records per-`(rule_id, as_of_date, symbol)` forward returns:

| Column | Meaning |
|---|---|
| `rule_kind` | `'atomic'` or `'composite'` |
| `action_code` | The action the user logged in `user_action_log` |
| `fwd_5d_pct` / `fwd_20d_pct` | Forward price return at 5 and 20 trading days |
| `hit` | Boolean — whether the trade moved in the predicted direction |

`etl/compute_outcomes.py::compute_outcomes()` reads `user_action_log` entries
older than 5 trading days, joins against subsequent `drv_ma` prices, and
populates `drv_rule_outcome`. It is called by the scheduler at a configurable
hour (`outcomes_compute_hour` in `ref_settings`).

`v_rule_performance` (backward-compat view) and `v_rule_performance_window()`
(parameterised function) aggregate `drv_rule_outcome` into per-rule hit rate,
false-positive rate, average 5d/20d return, and median return. The Rule
Performance screen (`/rule-performance`) calls `GET /api/rules/performance`
with optional `?window=N&from=YYYY-MM-DD&to=YYYY-MM-DD&min_n=M` parameters.

## Rules authoring screen

The Rules screen (`/rules`, `web/rules.html` + `web/rules.js`) has three tabs:

| Tab | Content |
|---|---|
| Derived Indicators | `ref_ma_columns` — calculated fields that feed atomic rules |
| Atomic Rules | `ref_trig_atomic_rule` — full CRUD via modal (edit category, scoring mode, thresholds, weights) |
| Composite Rules | `ref_trig_composite_mapping` — list view; "Open Editor" links to `/composite-edit` |

The composite editor (`web/composite_edit.html` + `web/composite_edit.js`)
provides a full member editor supporting all three kinds (atomic, data, nested
composite) with a symbol-scoped dryrun preview.

### CRUD API (`api/routers/rules.py`)

| Method + Path | Action |
|---|---|
| `GET /api/rules/atomic` | List active atomic rules (filterable by category) |
| `POST /api/rules/atomic` | Create atomic rule |
| `PUT /api/rules/atomic/{id}` | Update atomic rule fields |
| `DELETE /api/rules/atomic/{id}` | Soft-deprecate (`deprecated_at = now()`) |
| `POST /api/rules/atomic/{id}/dryrun` | Preview before/after for a sample symbol, count fire-state flips across all symbols |
| `GET /api/rules/composite` | List active composite rules (distinct by code) |
| `PUT /api/rules/composite/{id}` | Update metadata on all mapping rows |
| `PUT /api/rules/composite/{id}/members` | Replace full member list (transactional hard-delete + re-insert) |
| `DELETE /api/rules/composite/{id}` | Soft-deprecate all mapping rows |
| `POST /api/rules/composite/{id}/dryrun` | Preview composite score before/after proposed members for a sample symbol |
| `GET /api/rules/groups` | List all rule groups with members |
| `POST /api/rules/groups` | Create rule group |
| `PUT /api/rules/groups/{code}` | Update metadata + replace members |
| `DELETE /api/rules/groups/{code}` | Soft-deprecate |
| `GET /api/rules/groups/{code}/test` | Evaluate a group against a snapshot date |
| `GET /api/rules/performance` | Query `v_rule_performance_window` |
| `GET /api/rules/health` | Full health check: counts, orphan check, column resolution, fire counts vs. 30d baseline |

### Dryrun preview

Atomic dryrun (`POST /api/rules/atomic/{id}/dryrun`): reads the indicator
value from `drv_ma` / `drv_cat_atomic_input` for a sample symbol and date,
calls `eval_atomic_rule()` twice (current rule, proposed overrides), reports
`before`/`after` weight and fire status, and counts fire-state flips across all
symbols for the snapshot date. No `ref_trig_*` row is written.

Composite dryrun (`POST /api/rules/composite/{id}/dryrun`): reads the existing
composite's score from `drv_stks.triggered_composite_ids` for `before`, then
re-evaluates the proposed member list in-process (same logic as
`_derive_stks_impl`) for `after`, including all three member kinds and the
precondition gate. Reports score, fire status, member-hit count, and a
per-kind breakdown (`{"atomic": float, "data": float, "composite": float}`).

### Edits stay dormant until re-derive

Writing to `ref_trig_*` tables does not immediately change what the Cockpit,
Actionable, Dashboard, or Trace screens show. The cached `drv_trig`, `drv_stks`,
and `drv_actionable` rows remain from the previous derive until re-derived. To
propagate changes:

```cmd
python -m etl.rebuild_rules                 :: re-derive latest snapshot
python -m etl.rebuild_rules --date YYYY-MM-DD
python -m etl.rebuild_rules --no-refresh    :: skip ref reload, just re-derive
```

The scheduler also runs the full derive cascade on every file load when
`TD_RUN_DERIVE=1` (the default).

## Health check

`GET /api/rules/health` (used by the `/rules-health` page) runs seven
independent diagnostics and returns a single `status` field (`"healthy"` or
`"degraded"`) plus an `issues` list:

1. Atomic rule counts (total, active, with weights)
2. Composite mapping counts (total, active, mapping rows)
3. Orphaned composite members (reference deprecated/missing atomic rules)
4. Latest snapshot date + `drv_cat_atomic_input` and `drv_ma` row counts
5. Last 12 `meta_derived_run` entries (status, rows_built, error_msg)
6. Fire counts on the latest date vs. 30-day baseline (n_atomic, n_composite,
   n_bull, n_bear)
7. Column resolution audit (resolved vs. unresolved atomic rules)
