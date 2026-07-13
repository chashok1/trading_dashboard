# Rule tuning & outcomes (Phases 3–4)

Practical guide to the profile/tuning system and the rule-performance pipeline.
Written to (a) let you USE this day to day and (b) let a future Claude session pick
it up and fix issues. Pairs with `docs/rule_engine_redesign.md` (the design) and
`docs/performance_logic.md` (the older feedback-loop doc).

---

## TL;DR — honest state (2026-06-06)

**In production, trustworthy (live now):**
- All correctness fixes from this round: anchor-date model, `earnings_days` decrement,
  the `drv_trig` double-eval fix (697), nested-composite gating + `drv_trig` nesting,
  Phase 2 base rules (firing-equivalent), `current_volume_rule` thresholds.
- The **Baseline** parameter profile = a frozen copy of your current rule numbers.
  It is the active profile. Atomic compare holds at 99.91% / 99.89%.

**Built and available, NOT to be trusted/activated yet (exploratory):**
- `Sigmoid v1` profile — smooth/learnable form of 71 rules. Untuned it changes a lot
  of signals (a 2-param sigmoid can't reproduce a 3-level jump rule). It's a scaffold
  for ML, not a drop-in.
- `ml-sweep-20d` profile — first ML tune. Overfit: it was fit on ~4 months of ONE
  market regime (a Feb–May 2026 bounce) and fires on almost everything. Do not activate.

**The genuinely useful new capability:** you can now measure whether a rule actually
predicts the right move — see `v_rule_scorecard` below. Use it as a diagnostic.

**The blunt take:** the high-value work this round is the correctness fixes (already
live) and the *ability to score rules against real forward returns*. The ML tuning is
premature until you have more history across different market conditions. Don't act on
tuned numbers yet; do use the scorecard to spot consistently good/bad rules.

---

## 1. The profile system (param sets) — how to change rules safely

Your rules (`ref_trig_atomic_rule`, `ref_trig_composite_mapping`) are never edited for
tuning. Instead, a **parameter set** overlays tunable values (thresholds, weights,
sigmoid k/x0) at scoring time. Exactly one set is active; with none active the engine
uses the raw rule rows.

```
ref_trig_param_set     -- one row per profile (label, provenance, is_active, notes)
ref_trig_param_value   -- (param_set_id, target_kind, target_id, param_name, param_value)
```
Overlay code: `etl/param_sets.py::apply_active_param_set`, consumed by
`etl/derive_cat_atomic_input.py::load_trig_rules`. (Note: it overlays brkeout_from/to,
wt_below/between/above, and sigmoid k/x0 — it does NOT overlay neg_brkeout_*.)

Current profiles:
| id | label | active | meaning |
|----|-------|--------|---------|
| 1 | Baseline 2026-06-05 | YES | frozen copy of current rule numbers (rollback anchor) |
| 2 | Sigmoid v1 | no | learnable sigmoid scaffold (exploratory) |
| 3 | ml-sweep-20d | no | first ML tune (overfit; exploratory) |

### Switch / roll back (one move, reversible)
Only one set may be active (partial unique index). Always two-step:
```sql
UPDATE ref_trig_param_set SET is_active = FALSE;
UPDATE ref_trig_param_set SET is_active = TRUE WHERE param_set_id = <id>;
```
then re-derive: `python agent_rederive_all.py` (or derive_all for the dates you care about).
**Roll back to current = activate id=1.** Production should stay on Baseline (id=1)
until a tuned profile is proven better.

### Make an experiment profile
Insert a `ref_trig_param_set` (is_active=FALSE), add `ref_trig_param_value` rows for the
params you want to change, activate, re-derive, compare, then revert. ML does exactly
this automatically (`etl/ml_tune_thresholds.py`).

---

## 2. The outcome pipeline — does a rule actually work?

Goal: validate each rule FIRING against how the stock then performed — independent of
what you did (we do NOT rely on `user_action_log`, which is empty/column-drifted).

### Scripts
- `etl/backfill_derives.py` — runs `derive_all` for historical dates missing from
  `drv_trig`. ADDITIVE (only missing dates; never touches current data or rules).
  ```
  python -m etl.backfill_derives             # all missing dates
  python -m etl.backfill_derives --limit 3   # smoke test
  ```
- `etl/compute_firing_outcomes.py` — computes 5d/20d forward returns from
  `drv_ma.last_price` and writes `drv_rule_outcome` for every composite firing and
  every atomic feature value. ADDITIVE (only writes drv_rule_outcome).
  ```
  python -m etl.compute_firing_outcomes --truncate
  ```
  Composite rows: `hit` is direction-aware (BUY wants up, SELL wants down). Atomic rows:
  one per (rule, symbol, date) with non-null feature, for the tuner to fit thresholds.

### Refresh cadence
Re-run both whenever you've loaded more history (more dates = better, less regime bias):
```
python -m etl.backfill_derives
python -m etl.compute_firing_outcomes --truncate
```
`fwd_20d_pct` only exists for dates ≥20 trading days old — recent dates won't have it
yet (correct).

---

## 3. The scorecard — read which rules predict the right move

`v_rule_scorecard` (in `db/baseline.sql`) ranks composite rules direction-adjusted:

```sql
SELECT * FROM v_rule_scorecard ORDER BY edge_20d DESC;
```
- `edge_20d` — average forward 20d return **in the rule's favor** (SELL sign flipped).
  **> 0 means the rule was right on average; higher is better.** Rank by this.
- `win_rate` — fraction of fires that "hit" (direction-aware).
- `raw_avg_fwd20` — unadjusted average (don't rank on this; it conflates BUY/SELL).
- `fires`, `first_seen`, `last_seen` — support + coverage.

**How to use it:** rules with a clearly negative `edge_20d` over many `fires` are firing
before the wrong move — candidates to review, demote, or retire (deliberately, by you).
Rules with strong positive `edge_20d` are your keepers. Do this manually for now; it's
more reliable than ML on this little history.

**Caveat (important):** the numbers reflect only the loaded window (~4 months, one
regime). Treat as directional evidence, not proof. Re-check as history grows.

---

## 4. ML tuning (Phase 4) — when it's ready

`etl/ml_tune_thresholds.py` reads `drv_rule_outcome` + features and writes a new
inactive `ml:` profile (it never edits rules or activates itself).
```
python -m etl.ml_tune_thresholds --method sweep --min-samples 100 --label-window 20
# review, then optionally: activate the set, re-derive, BACKTEST vs Baseline, keep or revert
```
- `--method sweep` (model-free, uses forward return) — current default; note it only
  scans `feature >= t`, so it implicitly assumes higher-feature = better (wrong for
  bearish rules). `--method logreg` needs scikit-learn.
- **Do not trust a tune until** you have history across multiple market regimes and you
  validate out-of-sample (train on one slice, test on another). The current
  `ml-sweep-20d` profile is overfit — leave it inactive.

---

## 5. Gotchas / how to fix later

- **`rebuild_rules` strips DB-only customizations.** It reloads `ref_trig_atomic_rule`
  from the workbook, which wipes values that live only in `baseline.sql` (e.g.
  `current_volume_rule` neg thresholds). `rebuild_rules.py` now re-applies that one;
  if you add other DB-only rule tweaks, add them to that re-apply block too. After a
  mapping-only refactor, prefer a plain re-derive over `rebuild_rules`.
- **Param-set overlay ignores `neg_brkeout_*`.** If you ever need to tune negative-side
  thresholds via a profile, extend `etl/param_sets.py::_SCALAR_PARAMS`.
- **Sigmoid can't match 3-level jump rules.** A 2-param sigmoid interpolates wt_below↔
  wt_above and ignores wt_between. Expect signal change when activating sigmoid profiles.
- **Outcome forward returns use row-offset LEAD** (5/20 rows ≈ trading days). Fine while
  the universe is present every date; gets noisier if symbols come and go.
- **`drv_rule_outcome` PK** is `(rule_id, as_of_date, tos_symbol)` and the symbol column
  is `tos_symbol` (fixed 2026-06-06; was `symbol` with a too-narrow PK).

---

## 6. Command cheat sheet

```cmd
:: refresh the whole outcome dataset (after loading more history)
python -m etl.backfill_derives
python -m etl.compute_firing_outcomes --truncate

:: read the scorecard
psql -d trading -c "SELECT * FROM v_rule_scorecard ORDER BY edge_20d DESC;"

:: tune (writes inactive profile), then review before doing anything
python -m etl.ml_tune_thresholds --method sweep --min-samples 100 --label-window 20

:: switch profile (two-step) + re-derive, and roll back to Baseline
psql -d trading -c "UPDATE ref_trig_param_set SET is_active=FALSE; UPDATE ref_trig_param_set SET is_active=TRUE WHERE param_set_id=1;"
python agent_rederive_all.py
```

---

## 7. Where this shows in the UI

- **Performance screen** (`/rule-performance`): two panels. "Rule scorecard" =
  `v_rule_scorecard` ranked by `edge_20d` (which rules predict the right move).
  "Your actions" (TASK_121, 2026-07-12) = `v_inferred_action_performance` /
  `drv_inferred_action` (`GET /api/rules/my-actions`): trades INFERRED from
  `hist_cs`/`hist_f` position-snapshot deltas (`etl/derive_inferred_actions.py`)
  — **not** manual ACT-button logging, which is effectively empty
  (`user_action_log`) — joined to the stock's forward return and a
  FOLLOWED/CONTRADICTED/NO_SIGNAL stance vs that date's recommendation. The
  panel shows a FOLLOWED-vs-CONTRADICTED headline above the table. The older
  transaction-log-based `v_user_action_performance`/`drv_position_action`
  (TASK_71, `hist_cst`/`hist_ft`) is left in the schema for comparison but no
  longer served by this endpoint.
- **Actionable screen** (`/actionable`): the action surface. The grid has a
  **"Rules (edge)"** column (after "Trig") listing each row's fired rules
  winning-first (highest firing score), each chip showing its historical edge
  (`52-BS-BRR +1.9`, green/red) — at-a-glance conviction while scanning. Open a
  symbol's detail for the full per-rule breakdown, where each fired-rule pill also
  shows the edge badge (`+1.9% · 50%`). Both read `/api/rules/scorecard` (cached in
  `state.scorecard`, loaded in `loadSources`; cell builder `firesCellHtml`).
  The default row sort (TASK_120) is dollar-weighted edge, not this raw firing
  score — see `web/actionable.js::_computePriority`.
- **Rule Flow** (`/rule-flow`): per-symbol firing chain; each composite shows the
  same edge badge.
- **Param Sets** (`/param-sets`): activate/deactivate profiles (Baseline / Sigmoid /
  ml). NOTE: activating only flips the flag — re-derive for it to take effect.

The edge badges read the live scorecard, so they refresh whenever you re-run the
outcome ETL. All of it stays diagnostic until history spans more than one regime.
