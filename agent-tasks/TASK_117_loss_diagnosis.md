# TASK_117 — Loss diagnosis: where is the money going?

## Context

User is losing money and doesn't know why. Before redesigning the Actionable
screen (sort order, P&L columns, stop tiering — deferred to a later task), we
quantify where the losses actually come from. Three candidate causes:

1. **Signals are wrong** — rules/sources fire before the wrong move.
2. **Losers aren't cut** — sell signals / stop breaches exist but positions stay held.
3. **Over-allocation / buy bias** — the surface generates mostly buys; capital keeps deploying in a falling tape.

## Goal

A data report `docs/audit/loss_diagnosis_2026-07.md` answering, with numbers,
which of the three causes dominates. **Read-only + additive ETL only.** No rule
edits, no derive-logic changes, no schema changes. Use `tos_symbol` everywhere
except raw `hist_*`.

## Steps

### A. Refresh the outcome dataset (additive)

```cmd
python -m etl.backfill_derives
python -m etl.compute_firing_outcomes --truncate
```

Record row count of `drv_rule_outcome` and the date range covered.

### B. Rule scorecard — are the signals wrong?

```sql
SELECT * FROM v_rule_scorecard ORDER BY edge_20d ASC LIMIT 25;
SELECT * FROM v_rule_scorecard ORDER BY edge_20d DESC LIMIT 25;
```

Report: rules with `edge_20d < 0` and `fires >= 20` (the "firing before the
wrong move" list), and the strong positive keepers. Note the regime caveat
(~1 regime of history) in the report.

### C. Personal track record — is the user following signals?

```sql
SELECT * FROM v_user_action_performance;
SELECT count(*) FROM user_action_log;
```

If empty/near-empty, state that explicitly — it means the feedback loop is
open (nothing logged → system cannot attribute losses to user decisions).

### D. Position bleed — which held names are losing?

From the latest `hist_cs` snapshot per account (and `hist_f` if it carries
cost/gain columns — check its schema first; skip if not):

- Top 10 by `gain_dollar` ascending (biggest unrealized losers): symbol,
  market_value, cost_basis, gain_dollar, gain_pct.
- Portfolio totals: sum(market_value), sum(gain_dollar).

### E. Unheeded sell signals & stop breaches — are losers being cut?

1. Latest anchor date D (`etl/derive.py::get_anchor_date` logic — `MAX(export_date) FROM hist_td`):
   held rows in `drv_actionable` at D where quote `last_price < stop_level`.
   List symbol, position $, stop_level, last price.
2. For the past ~40 anchor dates: symbols whose `consolidated_action` was
   REMOVE/REDUCE while held. For each, forward 5d/20d return from
   `drv_ma.last_price`, and whether the symbol was STILL held 5/10 sessions
   later (`drv_portfolio`). Summarize: count of sell signals followed vs
   ignored, and the average forward return of the ignored ones (= estimated
   cost of not acting).
3. Buy-bias check: over the same window, counts of ADD/INCREASE vs
   REDUCE/REMOVE in `drv_actionable`, held vs not-held split.

### F. Verdict section

End the report with a short "Where the money is going" section ranking causes
1–3 by evidence, and the 2–3 highest-leverage fixes it implies (no
implementation — that's the follow-up design task).

## Files expected to change

- NEW `docs/audit/loss_diagnosis_2026-07.md` (the report)
- `drv_rule_outcome` repopulated (data only)
- `DEV_HANDOFF.md` (notes, ends `ALL_DONE`)

Nothing else. No code, no schema, no rule edits.

## Constraints

- SQL commands ≤ 965 bytes each (split queries if needed).
- Additive only; never delete/overwrite `hist_*`.
- If `user_action_log` has drifted columns (known possibility), report it —
  don't fix it here.

## How to verify

1. `docs/audit/loss_diagnosis_2026-07.md` exists with sections A–F populated
   (real numbers, not placeholders).
2. `SELECT count(*) FROM drv_rule_outcome;` > 0 and `MAX(as_of_date)` is
   within 5 days of the latest anchor.
3. `git status` shows only new/modified `.md` files — no code or SQL changes.
4. `DEV_HANDOFF.md` ends with `ALL_DONE`.
