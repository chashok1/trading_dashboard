# Rule Engine Redesign — Proposal

**Status:** Proposal (not yet implemented). Awaiting approval before any schema or
code change. Companion data: `docs/composite_member_map.csv` (every composite →
member → threshold → weight → proposed role → candidate base rule), generated
from `Tickers 2026-04-30.xlsx`.

This document proposes how to evolve the composite-rule tier from the flat
all-AND model inherited from the Excel `Trig` tab into a structure that is (a)
less brittle, (b) DRY via reusable base sub-composites, (c) easier to author, and
(d) ready for ML-based threshold tuning. The four are one coherent design, not
four separate ones.

---

## 1. The current model (recap)

A composite is a flat list of members. Each member is a single-indicator
threshold test. The composite **fires only when every member passes** —
`fired = (n_member_hit == n_total_members)` in `etl/derive.py:2163-2165`. Member
scores are summed but the firing decision is purely the AND count; the score is
not used as a soft signal. Direction comes from the rule-code prefix (BUY → `>=`,
SELL → `<=`), see `_composite_operator`.

This is faithful to the original `Trig` tab, where each composite is a column and
each populated row is a member with a `(threshold, weight)` pair.

---

## 2. What the 2026-04-30 workbook actually shows

Extracted from the `Trig` tab (65 composites with members, 499 member rows):

**Action mix:** BUY-family `B`(4) `BS`(20) `BR`(4) `BW`(6) = 34; SELL-family
`SA`(6) `SS`(12) `STM`(8) `SW`(4) = 30.

**A small core of members carries most signals** (count = composites using it):

| Member | Used in | Typical threshold | Typical weight |
|---|---|---|---|
| VS LT Outlook Rule | 34 | `0` (buy), `-2/-3` (sell) | 10 |
| Perf3D 1Off Rule | 28 | `3` | 10 |
| Trend-Rule | 27 | `2` (buy) | 10 |
| Trade-Rule | 25 | `0` (buy), `-1/-2` (sell) | 10 |
| IVHV Rule (modified) | 25 | `3` | **1** |
| MACDH_BRR Puts | 24 | `-2` | **1** |
| RSI Puts | 23 | `-2/-3` | 10 |
| IVRule | 21 | `0` | **1** |

Two facts drive the whole redesign:

1. **Thresholds are highly consistent per direction.** `VS LT Outlook = 0` in
   30 of 34 buy composites; `Perf3D = 3` in 27 of 28; `IVHV = 3` in 24 of 25;
   `IVRule = 0` in all 21. These are stable enough to fix once in a shared rule.
2. **Weight already encodes importance.** Members at weight **10** are
   must-haves; members at weight **1** (IVHV, IVRule, often RSI/MACDH_BRR) are
   corroboration. Today the engine ignores this and treats both as mandatory —
   a one-notch miss on a weight-1 indicator silences an otherwise-confirmed
   signal.

---

## 3. Proposal A — Gate / Evidence firing model

Split each composite's members into two roles:

- **Gate** — required. Strict AND, exactly like today. (the weight-10 members)
- **Evidence** — contributory. Sums toward an evidence score. (the weight-1 members)

**Firing rule becomes:** `all gates pass AND evidence_score >= evidence_cutoff`.

Worked example — `449-B-TN-TD-LRR-UP-MACD` (10 members today, all mandatory):

| Member | thr | wt | Proposed role |
|---|---|---|---|
| Trade-Rule | 0 | 10 | gate |
| Trend-Rule | 2 | 10 | gate |
| BRR% TRR Puts | -1 | 10 | gate |
| LRR above Trade | 1 | 10 | gate |
| Perf1D SD Rule | 0 | 10 | gate |
| Perf3D 1Off Rule | 3 | 10 | gate |
| VS LT Outlook Rule | 0 | 10 | gate |
| IVHV Rule (modified) | 3 | 1 | evidence |
| IVRule | 0 | 1 | evidence |
| RSI Rule | 2 | 1 | evidence |

With `evidence_cutoff = 2`, the buy fires when all seven gates pass and at least
2 of the 3 minor indicators agree — instead of dying when RSI is one notch off.

**Backward compatible:** set every member's role to `gate` and the rule is
identical to today. Migration can therefore default `member_role = 'gate'` for
all existing rows and selectively relabel weight-1 members as evidence — zero
behavior change until you opt in per rule.

**Schema delta** (additive, in `baseline.sql`):

```sql
ALTER TABLE ref_trig_composite_mapping
    ADD COLUMN IF NOT EXISTS member_role TEXT NOT NULL DEFAULT 'gate'
        CHECK (member_role IN ('gate','evidence'));
-- evidence cutoff lives once per composite; store on every member row like the
-- other shared metadata, or add a small header table (see §6).
ALTER TABLE ref_trig_composite_mapping
    ADD COLUMN IF NOT EXISTS evidence_cutoff NUMERIC;
```

**Eval delta** (`_derive_stks_impl`, the loop at `derive.py:2103-2172`): partition
members by `member_role`; compute `gates_pass = all(gate hits)` and
`evidence_score = sum(evidence weights that hit)`; fire on
`gates_pass and (evidence_cutoff is None or evidence_score >= evidence_cutoff)`.
Roughly 15 lines changed in one function. `drv_trig` / dryrun / outcome plumbing
all keep working.

---

## 4. Proposal B — Reusable base sub-composites (DRY)

The nesting machinery already exists (`member_kind='composite'`,
`nested_composite_code`, topo-sorted children-before-parents). It is simply
unused — which matches your note that you started some base rules but they aren't
referenced anywhere yet.

Define a handful of **base composites** (per-direction, because thresholds flip
sign by direction) and reference them from the leaf composites instead of
re-typing the same members. Proposed set, with coverage measured against the
workbook (composites sharing ≥2 of the base's members):

| Base rule | Members (threshold) | Role | Would be used by |
|---|---|---|---|
| `BASE-Bull-Context` | VS LT Outlook ≥0, Perf3D 1Off ≥3, Perf1D SD ≥0 | gate | **28** composites |
| `BASE-Bull-Trend` | Trade-Rule ≥0, Trend-Rule ≥2, MACDH Direction ≥1 | gate | **27** |
| `BASE-Bear-Context` | VS LT Outlook ≤-2, RSI Puts ≤-2, MACDH_BRR Puts ≤-2 | gate | **26** |
| `BASE-Vol-Regime` | IVHV ≥3, IVRule ≥0, IVPercentile, HVPercentile | evidence | **24** |
| `BASE-RR-Position` | BRR% LRR, BRR% TRR Puts, LRR above Trade, BRR% Rule | gate | 4 |

A leaf composite then shrinks dramatically. `449-B` above becomes, roughly:

```
449-B-TN-TD-LRR-UP-MACD =
    BASE-Bull-Context    (nested composite, gate)
  + BASE-Bull-Trend      (nested composite, gate)
  + BRR% TRR Puts ≤-1    (gate)
  + LRR above Trade ≥1   (gate)
  + BASE-Vol-Regime      (nested composite, evidence)
```

Five references instead of ten re-typed thresholds. Change a regime threshold
once and all 28 dependents update — versus editing 28 columns by hand today.

**Interaction with ML (§5):** shared base rules mean shared *parameters*. A base
threshold tuned by the model improves every dependent rule and is trained on the
pooled outcomes of all of them — fewer parameters, far more data per parameter.

The exact member lists are starting points reverse-engineered from the workbook;
review them against the base rules you already started. The full per-composite
breakdown with proposed gate/evidence roles and base tags is in
`docs/composite_member_map.csv`.

---

## 5. Proposal C — ML-ready foundations

The end goal is letting a model tune the jump thresholds. Two blockers and the
groundwork to remove them:

**Blocker 1 — jump thresholds are non-differentiable.** A step function has no
useful gradient, so gradient-based methods can't tune it. You already have the
escape hatch: `scoring_mode ∈ {jump, linear, sigmoid}` with `score_params` JSONB
holding `{k, x0}`. A `sigmoid` member is smooth and learnable — `x0` is the
threshold, `k` the sharpness. Recommendation: migrate learnable members from
`jump` → `sigmoid`. Behavior is near-identical at high `k`, but now tunable.

**Blocker 2 — structure and parameters are entangled.** Thresholds live inline on
the rule rows, so a model can't propose a parameter set without rewriting rules,
and you can't A/B or roll back. Introduce a parameter-set / version layer:

```sql
CREATE TABLE ref_trig_param_set (
    param_set_id   SERIAL PRIMARY KEY,
    label          TEXT,            -- 'hand-tuned-2026-04', 'ml-v1', ...
    created_at     TIMESTAMPTZ DEFAULT now(),
    is_active      BOOLEAN DEFAULT FALSE,
    provenance     TEXT             -- 'manual' | 'ml:<model>' | 'backtest'
);
CREATE TABLE ref_trig_param_value (
    param_set_id   INT REFERENCES ref_trig_param_set,
    target_kind    TEXT,            -- 'atomic' | 'composite_member' | 'composite'
    target_id      TEXT,            -- rule id / (code,member) key
    param_name     TEXT,            -- 'brkeout_from','x0','k','evidence_cutoff'
    param_value    NUMERIC,
    PRIMARY KEY (param_set_id, target_kind, target_id, param_name)
);
```

The derive cascade reads parameters from the active set; the hand-tuned values
become `param_set_id=1`. ML proposes a new set, you backtest it, flip
`is_active`, re-derive — and roll back instantly if it underperforms.

**You already have the training data.** No new pipeline needed:

- **Features** — `drv_cat_atomic_input` is a per-(symbol, date) wide matrix of
  indicator values. That is your feature store as-is.
- **Labels** — `drv_rule_outcome` already holds `fwd_5d_pct`, `fwd_20d_pct`, and
  `hit` per fired rule. That is your supervised target.
- **Aggregates** — `v_rule_performance` gives per-rule hit rate / false-positive
  rate to seed and evaluate any model.

So the ML path is: pick a rule (or base rule) → pull its feature columns from
`drv_cat_atomic_input` and outcomes from `drv_rule_outcome` → fit `x0,k` (and
evidence cutoffs/weights) to maximize forward return or hit rate → write a new
`ref_trig_param_set` → backtest → activate. The redesign exists to make every box
in that sentence already true.

---

## 6. Proposal D — Authoring screen changes

Current friction (from `web/composite_edit.js`, `rules.js`, `groups.html`):
adding an atomic member forces re-typing `data_brkeout_from` even though the
atomic rule defines it; no clone-composite; nesting is a blind code typeahead;
groups can't nest groups in the UI; preconditions are unvalidated freeform SQL.

Proposed, in priority order:

1. **Gate/Evidence toggle** per member + an `evidence_cutoff` field per composite
   (needed by §3). Small.
2. **Base-rule picker** — browse/preview nested composites with their member
   lists, so referencing `BASE-Bull-Context` is one click (enables §4).
3. **Threshold pre-fill** from the atomic rule definition when adding an atomic
   member (stop re-typing known thresholds).
4. **Clone composite** — duplicate an existing rule as a starting point.
5. **Param-set selector** (later, for §5) — view/compare rule output under
   different parameter sets.

A small per-composite header table would make (1) and the metadata duplication
cleaner. Today shared fields (`category`, `intent_text`, `precondition_expr`) are
copied onto every member row and kept in sync by the API; `evidence_cutoff` would
be one more such field. Optional: introduce `ref_trig_composite_rule` (one row
per code) to hold composite-level fields including `evidence_cutoff`. Deferrable —
the inline approach works for phase 1.

---

## 7. Suggested phasing

1. **Phase 0 — docs/cleanup.** Fix the doc defects (firing rule, `position_rules`,
   action vocab). Done alongside this proposal.
2. **Phase 1 — gate/evidence.** Add `member_role` + `evidence_cutoff`, default
   everything to `gate` (no behavior change), update the eval loop and UI toggle.
   Opt rules in incrementally.
3. **Phase 2 — base rules.** Author the `BASE-*` composites, refactor the highest-
   coverage leaf composites to reference them, verify via dryrun that scores are
   unchanged.
4. **Phase 3 — ML groundwork.** Add `ref_trig_param_set` / `_param_value`, route
   the derive cascade through the active set, migrate learnable members to
   `sigmoid`.
5. **Phase 4 — ML.** Fit parameters from `drv_cat_atomic_input` + `drv_rule_outcome`,
   propose param sets, backtest, activate.

Each phase is independently shippable and reversible.

---

## 8. Open decisions

1. **Gate/evidence:** adopt now (Phase 1) or base-rules-only first?
2. **Composite header table** (`ref_trig_composite_rule`) now, or keep shared
   fields inline for phase 1?
3. **Base-rule member lists:** use the reverse-engineered set in
   `composite_member_map.csv` as-is, or reconcile against the base rules you
   already started before authoring?
4. **Action vocab:** confirm the canonical action set
   (`SA, SW, STM, SS, B, BS, BR, BW, BM, BMN`) so docs and code agree.
