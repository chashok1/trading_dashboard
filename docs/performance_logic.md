# Performance Screen Logic

Deep-dive on the user-decision feedback loop, outcome scoring, and the
Performance screen. `CLAUDE.md` carries only a one-line pointer to this file
in its Lookup index; keep the detail here.

## Overview

The performance feedback loop closes the rule-engine cycle in three stages:

1. **Capture** — when the user marks a Cockpit or Actionable recommendation as
   acted-on or skipped, the system writes a forensic row to `user_action_log`
   and snapshots every rule that was firing at that moment.
2. **Score** — nightly, `etl/compute_outcomes.py` picks up unprocessed log
   entries whose decision date is at least 5 days old, fetches forward price
   returns from `drv_ma` (a VIEW since 2026-05-31; price lookups resolve through
   the `drv_technicals`/`drv_quote` components), and writes one `drv_rule_outcome`
   row per triggered rule.
3. **Aggregate** — `v_rule_performance_window` (and its compat alias
   `v_rule_performance`) groups `drv_rule_outcome` by rule to produce hit rate,
   false-positive rate, and avg/median 5d and 20d returns. The Performance
   screen (`/rule-performance`) renders this table so weak rules can be
   identified and edited.

## Diagrams

- `docs/diagrams/6_performance_data_flow.svg` — **data flow**: Cockpit /
  Actionable screens through `user_action_log`, `compute_outcomes.py`,
  `drv_rule_outcome`, `v_rule_performance_window`, the API, and the Performance
  screen, closing with the rule-edit feedback arrow.
- `docs/diagrams/15_performance_logic.svg` — **decision logic**: the two
  entry points into `user_action_log`, the five-day hold-off guard,
  `_determine_hit` action-code grouping, per-rule outcome rows, and
  `v_rule_performance_window` aggregation.

Keep both diagrams in sync whenever this logic changes.

## user_action_log — what is captured

Every POST to `/api/actions` (Cockpit) or POST to `/api/actions/{symbol}`
(Actionable) inserts one row. The schema records two distinct layers:

| Column group | Columns | Purpose |
|---|---|---|
| Identity | `id`, `user_id`, `acted_at`, `as_of_date`, `symbol` | When and for which ticker |
| Decision | `action_code`, `user_action`, `user_action_target`, `snooze_until`, `user_notes` | What the user chose |
| Snapshot | `consolidated_action`, `winning_source`, `winning_priority`, `position_category`, `suggested_target_dollar`, `held_at_action`, `position_dollar_at_action`, `in_my_list` | State of `drv_actionable` at decision time |
| Rules | `triggered_rules` JSONB | Array of `{rule_id, kind}` objects for every atomic and composite rule that was firing; read from `drv_stks.triggered_atomic_ids` + `triggered_composite_ids` |
| Sources | `source_actions` JSONB, `rules_engine_fires` JSONB | Per-source action array and rule-group fires from `drv_actionable` |
| Forensic | `source_raw_snapshot` JSONB | Most-recent hist_* row per active `ref_outlook_source` at decision time; supports replay |

`user_action` is constrained to `DONE / SKIPPED / SNOOZED / OVERRIDDEN`.

### Cockpit path (`/api/actions`)

The Cockpit submits raw meta-codes `ACTED` or `SKIP`. The handler in
`api/routers/trace.py::log_user_action` resolves them before storing:

- `ACTED` → looks up `drv_actionable.consolidated_action` for that
  (symbol, date); stores that as `action_code`, stores `DONE` as
  `user_action`. If no actionable row exists, stores `ACTED` — handled
  by a dedicated scoring branch in `_determine_hit`.
- `SKIP` → stores `action_code = 'SKIP'`, `user_action = 'SKIPPED'`.

The triggered rules are snapped from `drv_stks.triggered_atomic_ids` and
`triggered_composite_ids` at call time.

### Actionable path (`/api/actions/{symbol}`)

The handler in `api/routers/dash.py` accepts an explicit `user_action`
(`DONE / SKIPPED / SNOOZED / OVERRIDDEN`) and snapshots the full
`drv_actionable` row plus all `ref_outlook_source` hist_* rows into the
JSONB columns.

## compute_outcomes.py — outcome scoring

`etl/compute_outcomes.py::compute_outcomes(dry_run)` runs nightly via
`etl/scheduler.py::run_nightly_outcomes`. The hour is configurable via
`ref_settings.outcomes_compute_hour` (default 22).

### Processing loop

1. Selects unprocessed `user_action_log` rows where
   `as_of_date <= CURRENT_DATE - 5 days` and the log `id` is not yet in
   `drv_rule_outcome`. Up to 1 000 rows per run.
2. For each log row:
   - Calls `_get_forward_return(session, symbol, as_of_date, 5)` and `…(20)`.
   - Each looks up `drv_ma.last_price` on `as_of_date` (start) and on the
     trading-day N days later (found via `MAX(snapshot_date) FROM drv_ma WHERE
     snapshot_date > start LIMIT N`). Returns `((end − start) / start) × 100`.
   - Calls `_determine_hit(action_code, fwd_5d_pct, settings)` to classify
     the outcome.
   - For each `{rule_id, kind}` entry in `triggered_rules`, upserts one row
     into `drv_rule_outcome` (`ON CONFLICT (rule_id, as_of_date, symbol) DO
     UPDATE`).

### _determine_hit — hit classification

Thresholds come from `ref_settings` and default to 0.5 % (buy/sell) and
1.0 % (hold).

| action_code group | Hit condition |
|---|---|
| `SA, STM, SS, REMOVE, REDUCE` | `fwd_return ≤ outcome_hit_threshold_sell` (default −0.5 %) |
| `BM, ADD, INCREASE` | `fwd_return ≥ outcome_hit_threshold_buy` (default +0.5 %) |
| `HOLD, SKIP` | `|fwd_return| < outcome_hold_threshold` (default 1.0 %) |
| `ACTED` (unresolved) | `|fwd_return| ≥ min(|sell threshold|, buy threshold)` — symbol moved meaningfully |
| anything else / null return | `False` |

### drv_rule_outcome schema

| Column | Type | Notes |
|---|---|---|
| `rule_id` | TEXT | Atomic or composite rule code |
| `rule_kind` | TEXT | `'atomic'` or `'composite'` |
| `as_of_date` | DATE | Decision date from `user_action_log` |
| `symbol` | TEXT | Ticker |
| `action_code` | TEXT | Resolved action code |
| `fwd_5d_pct` | NUMERIC | % return 5 trading days forward |
| `fwd_20d_pct` | NUMERIC | % return 20 trading days forward |
| `hit` | BOOLEAN | True if direction was correct |
| `computed_at` | TIMESTAMPTZ | When the row was written |

PK is `(rule_id, as_of_date, symbol)`.

## v_rule_performance and v_rule_performance_window

Two aggregation objects live in `db/baseline.sql`:

**`v_rule_performance`** (view) — rolling 180-day window, fixed. Retained for
backward compatibility; new code should call `v_rule_performance_window`.

**`v_rule_performance_window(p_window_days, p_from, p_to)`** (function) —
flexible window. Either bounds can be NULL: `p_from` defaults to
`CURRENT_DATE − p_window_days` days; `p_to` defaults to today.

Both return the same column shape:

| Column | Meaning |
|---|---|
| `rule_id`, `rule_kind` | Rule identifier and type |
| `sample_size` | Count of scored outcomes in the window |
| `hit_rate` | Fraction of outcomes where `hit = true` |
| `false_positive_rate` | Fraction where `hit = false` |
| `avg_fwd_5d`, `avg_fwd_20d` | Mean forward returns |
| `median_fwd_5d`, `median_fwd_20d` | Median forward returns (`window` only) |
| `first_seen`, `last_seen` | Date range of scored outcomes |

## Performance screen API and UI

**Endpoint:** `GET /api/rules/performance` (served by
`api/routers/rules.py::get_rule_performance`).

Query parameters:

| Parameter | Default | Notes |
|---|---|---|
| `sort_by` | `hit_rate` | Any of: `hit_rate`, `sample_size`, `rule_id`, `avg_fwd_5d`, `avg_fwd_20d`, `median_fwd_5d`, `median_fwd_20d` |
| `limit` | 500 | 1–5 000 |
| `window` | 180 | Rolling days; ignored when `from` is set |
| `from` | (none) | YYYY-MM-DD; overrides `window` |
| `to` | today | YYYY-MM-DD |
| `min_n` | 0 | Filter rules with fewer than this many scored outcomes |

The handler calls `v_rule_performance_window(:w, :fd, :td)`, filters by
`sample_size >= min_n`, orders by the sort column descending, and returns a
list of dicts.

**UI** (`web/rule_performance.html` + `web/rule_performance.js`):

- On load, fetches `/api/rules/performance?sort=hit_rate&limit=500`.
- Renders a sortable table: Rule ID, Kind, Sample Size, Hit Rate (color-coded
  green ≥ 60 %, amber 40–60 %, red < 40 %), False Positive Rate, Avg 5D
  Return, Avg 20D Return, Last Seen.
- Column headers are clickable to toggle ascending/descending client-side sort.
- A "Sort by" dropdown re-fetches or re-renders; row click logs to console
  (detail panel noted as planned).

## How this informs rule edits

A rule with consistently low hit rate or negative average forward returns is a
candidate for threshold adjustment or retirement. The workflow is:

1. Review the Performance screen sorted by `hit_rate` ascending or
   `avg_fwd_5d` ascending.
2. Navigate to the Rules screen (`/rules`) to inspect or edit the atomic rule's
   thresholds (`brkeout_from`, `brkeout_to`, `wt_below`, `wt_between`,
   `wt_above`) or disable it (`is_active = false`).
3. Re-derive affected dates: `python -m etl.rebuild_rules` or use the File
   Monitor "Run Missing Derives" button.
4. After sufficient new decisions accumulate, the Performance screen will
   reflect the updated rule behavior.

## Re-running outcome scoring

`compute_outcomes` is idempotent per `(rule_id, as_of_date, symbol)` —
repeated runs update rather than duplicate. To force a full rescore:

```sql
DELETE FROM drv_rule_outcome;
```

Then run the scheduler (or `python -m etl.compute_outcomes` directly) to
repopulate from `user_action_log`.
