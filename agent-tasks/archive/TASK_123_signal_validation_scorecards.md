# TASK_123 — Signal validation scorecards: bull gate, Final Call, sources, thresholds

## Context

`docs/actionable_playbook.md` §5 lists the system's unvalidated assumptions
(A1–A6). TASK_117 diagnosed where losses come from; TASK_118–122 fixed
sell-quality, stops, and sort. What remains unmeasured is the **core
calibration**: the bull gate ladder, the Final Call strength table, the
source precedence order, and the hit thresholds. This task measures all of
them against real forward returns.

**Read-only + additive only.** New SQL views + a report. No rule edits, no
threshold changes, no derive-logic changes, no UI changes. `tos_symbol`
everywhere except raw `hist_*`.

## Prep — refresh the outcome dataset (additive)

```cmd
python -m etl.backfill_derives
python -m etl.compute_firing_outcomes --truncate
```

Record `drv_rule_outcome` row count and date range in the report.

**Forward-return mechanism for the new views:** reuse the row-offset LEAD
pattern from `etl/compute_firing_outcomes.py` (5/20 rows over ordered
`as_of_date` per symbol ≈ trading days), reading `last_price` from
`drv_technicals` (or through the `drv_ma` view). State the chosen mechanism
in the report. Verify actual column names with `\d` before writing views —
docs may drift from schema.

## A. Bull-gate scorecard (assumption A1)

New view `v_bull_gate_scorecard` in `db/baseline.sql`:

- Bucket by `drv_cat_atomic_input.bull` (MQ ladder, −3..+3) per
  (as_of_date, tos_symbol).
- Columns: `bull_bucket, n, avg_fwd_5d, avg_fwd_20d, median_fwd_20d,
  win_rate_20d` (fraction with fwd_20d > 0).
- Second breakdown (same view or a sibling): `rr_bull_bear` (QP: 'B' / '!B').

Questions to answer in the report: does +3 out-return +2? Do −2/−3
under-return? Does 'B' vs '!B' actually separate outcomes? If not, the
gate ladder is noise and the RR playbook switch is unfounded.

## B. Final Call scorecard (assumptions A2, A3)

New view `v_final_call_scorecard`:

- Bucket `drv_actionable.final_code × fc_confidence` per (as_of_date,
  tos_symbol); same forward-return columns as A.
- Direction-adjust: sell-family codes (SA/STM/SS…) want negative fwd; report
  both raw and direction-adjusted means (mirror `v_rule_scorecard`'s
  `edge_20d` convention).

Questions: does BM beat BS beat HOLD in adjusted fwd return? Does
`fc_confidence='high'` beat `'mixed'`? For mixed rows specifically, report
avg |fwd_20d| — is the discarded disagreement actually flat (safe to HOLD)
or high-movement (informative, currently wasted)?

## C. Per-source edge scorecard (assumption A4)

New view `v_source_edge_scorecard`:

- From `drv_outlook_action`: per `source_code × action`
  (ADD/INCREASE/REDUCE/REMOVE/HOLD): n, direction-adjusted avg fwd 5/20d,
  win rate. Buy-family wants up, sell-family wants down.

Question: does the data justify `SOURCE_ORDER` (PS=1 · ETF=2 · RR=3 · SSS=4
· II=5 · CALL=6)? Report the empirical ordering by adjusted edge_20d with n,
side by side with the current fixed order.

## D. Inferred-action aggregate — who loses the money?

No new view needed — aggregate `v_inferred_action_performance` /
`drv_inferred_action` (TASK_121):

- Per stance (FOLLOWED / CONTRADICTED / NO_SIGNAL): trade count, avg fwd_5d,
  avg fwd_20d, and dollar-weighted avg fwd_20d if trade-size dollars are
  available in the view (check; skip weighting if not, and say so).

End with one verdict line: *"FOLLOWED trades average X%, CONTRADICTED Y% →
the system / the operator is the larger loss source."*

## E. Hit-threshold sensitivity (assumption A6)

Report-only (no `ref_settings` change): recompute win-rate-style metrics for
composite fires at three hit definitions — current (±0.5% buy/sell), ±2%,
and |fwd_20d| ≥ 1 std-dev-unit if `hist_tw.std_dev`/AC is convenient to join
(optional; ±2% mandatory). Show the top/bottom 10 rules under current vs ±2%
— does the ranking materially reorder? If yes, A6 is confirmed (thresholds
below noise) and a follow-up task should recalibrate them.

## F. Report + verdicts

NEW `docs/audit/signal_validation_2026-07.md`, sections A–E with real
numbers, plus a final table giving each assumption **A1–A6** a verdict:
`validated / weak / broken`, one line of evidence each, and the top-3
implied changes (no implementation — that's follow-up design work). Include
the standing regime caveat (~4–5 months, one regime).

## Files expected to change

- `db/baseline.sql` — 3 new views (additive; then `python -m db.init_db`)
- NEW `docs/audit/signal_validation_2026-07.md`
- `drv_rule_outcome` repopulated (data only)
- `DEV_HANDOFF.md` (append; end `ALL_DONE`)

Nothing else. No rule/threshold/derive/UI edits.

## Constraints

- SQL commands ≤ 965 bytes each — split long DDL/queries.
- Additive only; never delete/overwrite `hist_*`.
- Views must not slow the runtime path: they are analyst views, not joined
  into `/api/actionable`.

## How to verify

1. `SELECT * FROM v_bull_gate_scorecard LIMIT 5;` (and the other two views)
   return rows with non-null forward returns.
2. `docs/audit/signal_validation_2026-07.md` exists, sections A–E populated
   with real numbers, A1–A6 verdict table present.
3. `git status`: only `db/baseline.sql`, new `.md` files, and
   `DEV_HANDOFF.md` changed — `git diff db/baseline.sql` shows only view
   additions (no edits to `ref_trig_*` seeds, functions, or existing objects).
4. `SELECT count(*) FROM drv_rule_outcome;` > 0 with `MAX(as_of_date)`
   within 5 days of the latest anchor.
5. `DEV_HANDOFF.md` ends with `ALL_DONE`.
