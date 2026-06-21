# TASK 66 — Single calibrated bull-probability  P(up_20d)

**You: VS Code developer agent, psql + code.** Log progress in `DEV_HANDOFF.md`; end with
`ALL_DONE`. **DO NOT COMMIT/PUSH.**

> **QUEUED — blocked by TASK 65.** Do NOT start until TASK 65 is `ALL_DONE`. TASK 65's
> per-rule edge numbers are the raw material that decides which signals are worth
> weighting here. Starting before that means weighting noise.

## Why (one line)
The two stacks already combine in `_compute_final_call` (`etl/derive_actionable.py`), but
via a hand-coded precedence tree with **fixed `_FC_SCALE` strengths** never fit to
returns, and disagreements collapse to HOLD/`fc_confidence="mixed"`. Add **one calibrated
number per symbol: P(stock up over next 20 days)**, weighted by how predictive each signal
has actually been — running *beside* the existing Final Call for comparison, not replacing
it. Background: `docs/audit/bull_calc_analysis.md` §1, §4–5 (P2).

**Compare, don't rip out:** keep `_compute_final_call` and its output intact. The new
`bull_prob` is a parallel column so the user can judge calibrated-probability vs the
current rule-based Final Call before trusting it. The eventual goal is to let `bull_prob`
inform `_FC_SCALE`'s strengths, but that is a later task — not this one.

## The idea in one breath
Today `_composite_outlook` gives every source one equal vote. Instead: learn each
signal's weight from its real forward-return history, sum the weighted signals, squash to
a 0–1 probability, and also emit an **agreement** measure (how much the signals concur).
Existing labels/gates stay; this is a **new, additive output** watched in parallel before
anyone trusts it.

## Scope — three phases, keep it simple

### Phase A — Training feature table (offline build)
Assemble one row per `(tos_symbol, as_of_date)` with:
- The candidate signal values (start with what already exists): the Stack-B atomic
  scores from `drv_cat_atomic_input` (e.g. `bull`, `trade_rule`, `trend_rule`,
  `bb_bull_rule`, perf/vol/SD rules) and the Stack-A source signals (rr_brr,
  call/etf/ii outlook → numeric via the existing outlook weights, sss_signal_sign).
- The label: realized `fwd_20d_pct > 0` (reuse `drv_rule_outcome` / the same forward-
  return source `compute_firing_outcomes.py` uses — do not invent a new return calc).
- **Restrict the feature set to signals TASK 65 showed have edge** (e.g. confidence ≠
  `unproven`). Drop the dead-weight ones. Record which were kept.

### Phase B — Fit + validate (use existing ML infra)
- Fit a **logistic regression** (simple, interpretable) of P(up_20d) on those features.
  Reuse `etl/ml_tune_thresholds.py` patterns / sklearn if already a dependency.
- **Train/test split by DATE, not random** (no look-ahead): fit on older dates, test on
  newer. Report on the holdout: AUC, and a **calibration check** — when the model says
  60%, does ~60% actually happen? (bucket predicted prob vs realized hit-rate). A model
  that isn't calibrated is not shippable for sizing.
- Store the fitted coefficients + feature list + train window + holdout metrics in a
  **ref table** (e.g. `ref_bull_model`, one active row + history), NOT hardcoded. This
  keeps it tunable/refreshable per convention #3/#5.

### Phase C — Score at derive time (additive, non-breaking)
- New derive step computes, per symbol on date D: `bull_prob` (0–1) from current feature
  values × stored coefficients, and `signal_agreement` (e.g. share of contributing
  signals pointing the same direction, or 1 − normalized dispersion).
- Write to a **new column / small new table** (e.g. `drv_actionable.bull_prob`,
  `bull_agreement`) — **do not alter or replace** `composite_label`, `bull`, the RR
  gate, `trig_action`, or any existing column. Idempotent (`DELETE WHERE as_of_date=D`).
- Expose via API (extend an existing actionable/rules endpoint) and add a **read-only
  column** to the Actionable screen showing prob + agreement. Existing columns untouched.

**Screen placement (intent) — this is the money screen.** The Actionable screen is where
the user decides each day, so the two tradeable outputs go here, next to the final call:
- `bull_prob` as a **sortable column** (rank the universe, strongest first) — this is the
  sizing dial.
- `bull_agreement` as a small badge beside it (agree / split).
- Add a top-of-screen **filter** ("prob ≥ X and favorable agreement") so the filtered,
  sorted list becomes the user's daily buy-candidate list. That filtered list IS the
  money loop. Per-symbol, also show `bull_prob` on the Rule Flow screen for drill-down.
  Do not duplicate the per-rule scorecard here (that lives on Performance, TASK 65).

## Refresh
Make Phase B re-runnable on command (`python -m etl.fit_bull_model` or similar) so
weights can be refreshed periodically as new outcomes accumulate. Not wired into the
live scheduler in this task — manual run is fine for now.

## Non-negotiables
- **Additive only.** Nothing existing changes behavior. The probability runs *beside*
  the current system so you can compare for a few weeks before relying on it.
- No look-ahead: features for date D must use only data available at D; label is the
  future return. Date-based split.
- Coefficients live in a ref table, not in code.
- SQL ≤ 965 bytes/stmt; tos_symbol everywhere (conventions #7, #15).

## Files expected to change (indicative)
- `etl/fit_bull_model.py` (new — Phase A+B)
- `db/baseline.sql` (new `ref_bull_model`; new `bull_prob`/`bull_agreement` columns or
  table; apply via `python -m db.init_db`)
- `etl/derive_actionable.py` or a new `etl/derive_bull_prob.py` (Phase C scoring; wire
  into `derive_all`)
- `api/routers/{actionable or rules}.py` (expose) + `web/actionable.*` (display column)

## How to verify (tester reference — only on request)
1. `python -m etl.fit_bull_model` produces a `ref_bull_model` active row with
   coefficients, feature list, and holdout AUC + calibration table; logs the train/test
   date split.
2. Holdout calibration: predicted-prob buckets roughly match realized hit-rates (report
   the table; flag if wildly off).
3. After a derive, `bull_prob` is populated for the anchor date, in [0,1], for all
   symbols in `drv_symbols`; `bull_agreement` populated.
4. Regression check: `composite_label`, `bull`, RR gate, `trig_action`, and existing
   screens are **unchanged** vs before the task (diff a few symbols).
5. Re-running derive for the same date is idempotent (no dupes, same values).
6. Actionable screen shows the new prob/agreement column; no console errors; existing
   columns intact.
