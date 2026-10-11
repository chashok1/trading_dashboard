# TASK_142 — Freshness contracts for computed analytics (stop silent staleness)

## Context

`drv_rule_outcome` sat un-refreshed from 2026-07-12 until TASK_138 — while the
numbers derived from it (edge badges, LOW CONF, the default dollar-edge sort)
carried on rendering as if current. **Nothing anywhere noticed.**

This is the third instance of the same failure, each fixed individually:

| Date | Table | Code comment |
|---|---|---|
| 2026-08-15 | `ref_vlm_intraday_curve` | *"you have to schedule it or do something. i forget to run it."* |
| 2026-09-13 | `drv_inferred_action` | *"scoring silently stalled (found stale for 3+ months)"* |
| 2026-09-20 | `drv_rule_outcome` | never scheduled at all (TASK_138) |

The existing safety net is good but points the wrong way. `daily_health_check.py`'s
six checks — `_check_hist_gap`, `_check_stale_ref`, `_check_source_missing`,
`_check_scheduler_idle`, `_check_derive_health`, `_check_bb_rr_drift` — plus
`derive_freshness.py` and the stale banner all watch **inputs**: did the files
arrive, are there gaps in raw history, did the cascade run. **Nothing watches
whether a computed analytics output is still current.**

The root failure mode: **a stale number renders identically to a fresh one.**
A July edge score looks exactly like today's, in the same badge, in the same
sort. There is no visual difference at the point of decision.

**Prerequisite: TASK_138 complete** (else this task's first alarm is one
TASK_138 is already fixing).

## Goal

Every computed table that feeds a decision screen declares its own freshness
contract; a breach raises a warning through the existing `meta_warning` pipe
**and** is visible on the screen where the number is used.

### 1. `ref_freshness_contract` (new, `db/baseline.sql`)

| column | meaning |
|---|---|
| `table_name TEXT PK` | the computed table |
| `date_column TEXT NOT NULL` | which column to take `MAX()` of |
| `max_lag_days INT NOT NULL` | how far behind the anchor it may fall before breach |
| `maturity_lag_days INT NOT NULL DEFAULT 0` | *expected* structural lag (see below) |
| `refreshed_by TEXT NOT NULL` | the job that keeps it current, e.g. `scheduler.run_nightly_outcomes` |
| `screen TEXT` | where a breach should surface (`actionable`, `rule-performance`, …) |
| `severity TEXT NOT NULL DEFAULT 'warning'` | `warning` \| `critical` |
| `is_active BOOLEAN NOT NULL DEFAULT TRUE` | |

**`maturity_lag_days` is essential, not decoration.** `drv_rule_outcome` can
*never* be closer than ~20 trading days to the anchor — a 20-day forward return
needs 20 future days of prices. Without this column the check would fire every
single day, and an alarm that always fires is an alarm nobody reads. Breach
condition:

```
(anchor_date - MAX(date_column)) > (maturity_lag_days + max_lag_days)
```

Seed (`db/seeds_freshness_contract.sql`) with at least:

| table | date_column | maturity | max_lag | refreshed_by |
|---|---|---|---|---|
| `drv_rule_outcome` | `as_of_date` | 30 | 3 | `scheduler.run_nightly_outcomes` |
| `drv_factor_snapshot` | `as_of_date` | 30 | 3 | `scheduler.run_nightly_outcomes` |
| `drv_inferred_action` | `as_of_date` | 30 | 3 | `scheduler.run_nightly_outcomes` |
| `ref_vlm_intraday_curve` | *(see note)* | 0 | 7 | `scheduler.run_nightly_outcomes` |
| `drv_market_stat` | `as_of_date` | 0 | 2 | `derive_all` |
| `drv_pvv` | `as_of_date` | 0 | 3 | `derive_all` |

Developer: confirm each `date_column` exists before seeding; if
`ref_vlm_intraday_curve` has no natural date column, use its `loaded_at`/
`updated_at` and note the substitution. Add `ref_bull_model` (fitted-at age)
only if the table carries a timestamp — do not invent one.

### 2. `_check_stale_analytics` — the seventh health check

Add to `etl/daily_health_check.py`, same return shape as the existing six
(`{"id", "title", "ok", "detail", "items"}`), appended to `CHECKS`.

- Reads active `ref_freshness_contract` rows, computes the breach condition
  against the anchor (`etl/derive.py::get_anchor_date`).
- Each breach becomes one item: table, expected-by date, actual `MAX`, days
  over, and **`refreshed_by`** — so the message says *which job to look at*,
  not just "something is old".
- Writes each breach to `meta_warning` using the existing columns
  (`screen`, `severity`, `code='stale_analytics'`, `message`), so it rides
  `/api/healthz/warnings` and the toolbar badges already in place. Don't build
  a new notification path.
- A table with **zero rows** is a breach, not a pass — that's the cold-start
  case this whole task exists to catch.

### 3. Show the age at the point of decision — the part that matters most

Points 1 and 2 are an alarm; this is the part that survives the alarm breaking.

- `GET /api/rules/scorecard`, `/api/rules/factor-scorecard` and the Actionable
  payload each return the `as_of` date and `stale: true|false` of the table
  behind them.
- **Actionable:** when the edge data is stale, the "Rules (edge)" pills render
  greyed with a tooltip "edge data as of <date> — stale"; the header shows one
  amber chip "EDGE DATA <date>".
- **Performance screen:** an "as of <date>" stamp on the scorecard and factor
  cards; amber-bordered when stale.
- **File Monitor:** a "Stale analytics" list beside the existing "Stale
  derives" list — same visual treatment.
- Do **not** hide or blank a stale number. The user must still see it, marked
  as old — silently removing data creates a different confusion.

### 4. Close the loop on the process

Add to `docs/agent_handoff_workflow.md`, in the "How to verify" requirements:

> Any task that adds a computed table feeding a decision screen must answer two
> questions in its spec: **what job schedules it**, and **what alerts if it
> stops**. A new computed table ships with its `ref_freshness_contract` row in
> the same task, or the task is not done.

This is the actual prevention — the previous three incidents each shipped a
correct table with no answer to those two questions.

## Files expected to change

- `db/baseline.sql`, `db/seeds_freshness_contract.sql` (new)
- `etl/daily_health_check.py`
- `api/routers/rules.py`, `api/routers/dash.py`, `api/routers/monitor.py`
- `web/actionable.js`, `web/rule_performance.js`, `web/file_monitor.js`
  (+ `web/styles.css` if needed)
- `docs/agent_handoff_workflow.md`, `docs/migrations.md`
- `DEV_HANDOFF.md`

Purely additive — no derive logic, no rule, no threshold, nothing on the
decision path changes. This task only makes existing staleness *visible*.

## How to verify

1. `python -m db.init_db` idempotent; contract table seeded; every
   `date_column` named in a seed row actually exists on its table.
2. With TASK_138's nightly job having run: `python -m etl.daily_health_check`
   → the new check passes, and its detail line shows each table's actual lag
   so a near-breach is visible before it breaches.
3. **Force a breach:** temporarily set `drv_rule_outcome`'s `max_lag_days` to
   `-999`. The check fails, a `meta_warning` row appears with
   `code='stale_analytics'`, the message names `run_nightly_outcomes`, the
   Actionable edge pills grey out with the as-of date, and the Performance
   cards show the amber stamp. Restore the value.
4. **Cold start:** point a contract row at an empty table — reported as a
   breach, not a pass.
5. **No false alarm:** `drv_rule_outcome` sitting at its normal ~20-trading-day
   maturity lag does **not** breach. Run the check on 5 consecutive days'
   anchors and confirm zero false positives — a check that cries wolf is worse
   than no check.
6. The six existing checks are unchanged and still pass.
7. `docs/agent_handoff_workflow.md` carries the two-question requirement.
