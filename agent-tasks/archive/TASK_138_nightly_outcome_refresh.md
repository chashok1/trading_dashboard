# TASK_138 — Schedule the outcome ETL nightly (stop the scorecards going stale)

## Context

`drv_rule_outcome` is the table behind **every** edge number the user sees:
`v_rule_scorecard`, `v_unproven_sell_rules` (the LOW CONF flag),
`v_source_edge_scorecard` (the nightly weak-buy-source recompute), the
Actionable "Rules (edge)" pills, and **the default dollar-weighted edge sort
(TASK_120)** — i.e. which rows the user triages each morning.

`etl/compute_firing_outcomes.py` is **not scheduled anywhere**: not in
`etl/scheduler.py::run_nightly_outcomes()`, not in `register_startup_tasks.bat`,
not in any `.bat`/`.ps1`. It only ever runs when someone types it by hand.
Last documented run: **2026-07-12** (`docs/audit/signal_validation_2026-07.md`).

Consequence today: the morning sort order, the edge badges and the LOW CONF
annotation are all scoring on a ~10-week-old window. This is the same class of
bug already fixed for `drv_inferred_action` on 2026-09-13
(`backfill_maturing_forward_returns`, in the same nightly job).

Note `etl/derive_source_edge.py::recompute_weak_buy_sources` already runs
nightly — it reads `v_source_edge_scorecard`, which reads stale data. Ordering
matters (see step 2).

## Goal

`drv_rule_outcome` refreshes itself every night, incrementally, with no manual
step and no 8-million-row rebuild.

1. **`etl/scheduler.py::run_nightly_outcomes()`** — add a step that runs
   *before* the existing "weak-buy-sources recompute" block (that block consumes
   what this produces):

   - call `etl.backfill_derives` (its existing no-op-if-nothing-missing path) to
     make sure every `hist_td` date through the anchor has a `drv_trig` row;
   - then call `compute_firing_outcomes` **without `--truncate`** — incremental,
     so it only fills rows that have newly matured a 5d/20d forward label.
   - Wrap in the same `try/except log.exception(...)` pattern every other step
     in that function uses. A failure must not break the rest of the nightly job.

2. **Ordering inside `run_nightly_outcomes()`:** this new step must come before
   `recompute_weak_buy_sources` and before `refresh_factor_outcomes`, so both
   read the refreshed table on the same night rather than the previous night's.

3. **Cost guard.** Incremental mode still walks a large table. Log
   `rows_written` + elapsed seconds at INFO (same shape as the other nightly
   steps) so a regression in runtime is visible in the scheduler log. If the
   incremental path turns out to rewrite everything regardless of `--truncate`
   (verify this before wiring — read `compute_firing_outcomes.py`'s insert
   path), add a `--since DATE` argument that limits the recompute to
   `as_of_date >= (anchor - 45 days)`, which comfortably covers the
   20-trading-day maturation lag, and use that from the scheduler.

4. **Do NOT** add a `--truncate` full rebuild to the nightly job. A full
   rebuild stays a manual/weekly operation
   (`python -m etl.backfill_full`), documented in the playbook.

5. **Docs:** one row in `docs/migrations.md`; update
   `docs/rule_tuning_and_outcomes.md` and `docs/actionable_playbook.md` §6 where
   they currently tell the user to run these two commands by hand — the weekly
   manual refresh becomes optional, not required.

## Files expected to change

- `etl/scheduler.py` (primary)
- `etl/compute_firing_outcomes.py` (only if a `--since` guard is needed per step 3)
- `docs/migrations.md`, `docs/rule_tuning_and_outcomes.md`,
  `docs/actionable_playbook.md`
- `DEV_HANDOFF.md`

No schema change. No derive-logic change. Nothing on the decision path moves.

## How to verify

1. `SELECT MAX(as_of_date), COUNT(*) FROM drv_rule_outcome;` — record before.
2. Trigger the nightly job (or call `run_nightly_outcomes()` directly).
3. Re-run the query: `MAX(as_of_date)` advances to roughly
   `anchor - 20 trading days`; row count grows rather than resetting.
4. `SELECT * FROM v_rule_scorecard ORDER BY fires DESC LIMIT 5;` — `fires`
   counts are higher than the 2026-07 figures in
   `docs/audit/loss_diagnosis_2026-07.md` §B.
5. Scheduler log shows the new step, its row count, its elapsed time, and shows
   it running **before** "weak-buy-sources recompute".
6. Kill the step mid-run (or force an exception) — the rest of
   `run_nightly_outcomes()` still completes.
7. Run the nightly job twice in a row — second run is cheap and does not
   duplicate rows (PK `(rule_id, as_of_date, tos_symbol)` holds).
