# TASK 67 — Data-fit bull-gate thresholds (revertible: original + calculated)

**You: VS Code developer agent, psql + code.** Log progress in `DEV_HANDOFF.md`; end with
`ALL_DONE`. **DO NOT COMMIT/PUSH.**

> **QUEUED — blocked by TASK 65 (and best after TASK 66).** TASK 65's per-rule edge
> tells you which rules are even worth re-fitting. Do not start until TASK 65 is
> `ALL_DONE`.

## Why (one line)
The bull-gate thresholds (`≥2`, `≥3`, etc. in `_bull_expr` and the related rule ladders)
are hand-typed Excel relics, never fit to data. Fit them to forward-return history — but
**keep the originals and make the switch fully revertible**. Background:
`docs/audit/bull_calc_analysis.md` §5 (P3).

## Hard requirement — never lose the originals
The threshold config must hold, per rule/cutoff, **three things side by side**:
- **`original_value`** — the current/Excel value, written once, **never overwritten**
  (mirrors convention #1).
- **`calculated_value`** — the latest data-fit value (nullable until fitting runs).
- **`active_source`** — which one is live: `'original'` | `'calculated'`.
Plus a **history** of every fitted version (value, fit date, train window, holdout
metric) so the user can roll back to any past calibration, not just the original.

Reverting = set `active_source='original'` (or pick a historical version). It is a
one-row config change — **no recompute, no code change, no data destroyed.**

## Scope

### 1. Config table(s) (db/baseline.sql)
- Extend the existing threshold config (the tunable `ref_*` the bull ladders read —
  likely `ref_trig_atomic_rule` / `ref_param_lookup`; confirm where `_bull_expr` and the
  RR ladders actually pull cutoffs) so each tunable cutoff carries
  `original_value`, `calculated_value`, `active_source`. If editing those tables is too
  invasive, add a side table `ref_threshold_override(rule_key, original_value,
  calculated_value, active_source, ...)` that the derive consults.
- Add `ref_threshold_fit_history(rule_key, fitted_value, fit_date, train_start,
  train_end, holdout_metric, n)`.
- **Backfill `original_value` once** from today's live values before anything is fit.

### 2. Fitting step (reuse `etl/ml_tune_thresholds.py`)
- Point it at the bull-gate cutoffs for rules TASK 65 marked as having edge
  (skip `unproven` rules — don't tune noise).
- Date-based train/holdout split (no look-ahead). Write results to
  `calculated_value` + append to `ref_threshold_fit_history`. **Do not auto-activate** —
  leave `active_source='original'` until the user flips it.
- Re-runnable: `python -m etl.ml_tune_thresholds --target bull-gate` (or similar).

### 3. Comparison the user can trust before flipping
- A report/query (or small endpoint) showing, per rule on the holdout window:
  original-threshold edge/win-rate vs calculated-threshold edge/win-rate, side by side.
  This is the "would the new cutoffs have made more money?" check. Only then does the
  user set `active_source='calculated'`.

### 4. Derive respects `active_source`
- The bull ladders read whichever value `active_source` points to. Default stays
  `original` so **behavior is unchanged until the user opts in**. Idempotent derive.

### 5. (Optional) tiny UI on the Rules/Param screen
- Show original vs calculated vs active per rule, with the holdout comparison, and a
  control to flip `active_source`. Read existing styles; no new palette.

## Non-negotiables
- Originals are write-once, never overwritten (convention #1).
- Default behavior unchanged until the user activates calculated values.
- No look-ahead in fitting; date-based split.
- Thresholds stay in tunable tables, not code (conventions #3/#5). SQL ≤ 965 bytes/stmt.

## Files expected to change (indicative)
- `db/baseline.sql` (config columns/side table + fit-history table; `python -m db.init_db`)
- `etl/ml_tune_thresholds.py` (fit + write calculated + history)
- the bull-ladder derive (`etl/derive_cat_atomic_input.py` / `etl/derive.py`) to read
  `active_source`
- optional `api/routers/rules.py` + `web/param_sets.*` or `web/rules.*` for the toggle

## How to verify (tester reference — only on request)
1. After `init_db`, every tunable bull cutoff has a populated `original_value` matching
   the pre-task live value; `active_source='original'` by default.
2. Run the fitter → `calculated_value` populated, a `ref_threshold_fit_history` row added
   with train window + holdout metric; `active_source` still `'original'`.
3. Derive output is **identical** to pre-task while `active_source='original'` (diff a
   few symbols' `bull`/gate values).
4. Flip one rule to `'calculated'`, re-derive → only that rule's gate changes; flip back
   → values return exactly to original (proves revert).
5. Comparison report shows original vs calculated edge/win-rate on the holdout.
6. Re-derive idempotent; SQL statements within length limit.
