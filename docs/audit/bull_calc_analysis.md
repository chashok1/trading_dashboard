# Bull / Non-Bull Calculation Audit

**Date:** 2026-06-20 · **Lens:** make money, not just compute scores · **Scope:** every place a bull/bullish/bear value is computed or interpreted (ETL, SQL, API, JS).

---

## TL;DR (what you must act on)

1. **The two stacks DO combine — but only as a hand-coded action merge, not a calibrated score.** A *sentiment* stack (analyst/source outlooks → `consolidated_action`) and a *technical* stack (MA/Bollinger, the `bull`/`MQ` gate → `rr_action`) are reconciled by `_compute_final_call` (`etl/derive_actionable.py`) into the Actionable screen's Final Call. **Correction to an earlier draft of this doc:** they are not "uncombined." The real gap is *how* they combine: a precedence decision-tree that outputs an action word (BUY SOME) plus a strength from a **fixed hand-typed table** (`_FC_SCALE`: BM=+2, SS=−2…) never fit to forward returns; and when the stacks disagree it collapses to HOLD with `fc_confidence="mixed"` — discarding the split instead of measuring whether mixed setups pay. So you get *what to do*, not *how likely it is to work*, and you can't size off "how bullish, with what confidence."
2. **The bull gate that drives your buy/sell interpretation is never validated against forward returns.** `_bull_expr` thresholds (`≥2`, `≥3`, `≤-2`…) are hardcoded ports from the old Excel sheet. `v_rule_scorecard` measures *composite rules*, but the bull gate itself (and `bull_rr_action` vs `not_bull_rr_action`) has no edge measurement. You are trusting an arbitrary threshold to decide which playbook to run.
3. **At least 6 real duplications** — same bull/bear logic maintained in 2–4 places (Python+SQL, backend+JS). These don't lose money directly but guarantee drift: two color palettes, four hand-typed action-code lists, the RR "decision path" re-implemented in JS, the ETF/II bundle logic written twice.

The fix that makes money: **keep the existing Final Call, but add a calibrated bull-probability beside it** — replace `_FC_SCALE`'s typed-in strengths with weights fit to forward returns, and turn the "mixed" dodge into a measured edge. Run it alongside the current final call so you can compare before trusting it. Everything else is cleanup.

---

## 1. What "bull" means in this system

You were right in your framing: the bull value is a **regime gate** — it decides *how the same downstream data gets interpreted*. The clearest example: the risk-range (RR) data is read through `bull_rr_action` when the gate says bull, and through `not_bull_rr_action` when it doesn't (`etl/derive.py::_derive_trend_trade_rules_impl`, columns `QM`/`QN`/`QP`). So a wrong gate flips the entire RR playbook for a name.

There are **four independently-computed bull/bear notions**, plus the action-resolution layer that turns them into SA/STM/SS/BM vocab:

| # | Notion | Where | Type |
|---|---|---|---|
| 1 | Source outlook text (BULLISH/Bullish/…) | `drv_rr.outlook` ← vendor feed | raw string, weighted by `ref_param sheet='outlook'` (BULLISH=+3 / BEARISH=−3 / NEUTRAL=0) |
| 2 | Composite ensemble label | `etl/derive.py::_composite_outlook` → `drv_stks.composite_label` | ±1 vote over 5 sources, sign → BULLISH/BEARISH/NEUTRAL |
| 3 | Technical bull gate | `etl/derive_cat_atomic_input.py::_bull_expr` → `bull`/`not_bull` (`MQ`/`MR`) | integer −3..+3 from MA/Bollinger rules |
| 4 | Rule direction (BUY vs SELL) | `db/baseline.sql::v_rule_scorecard` | regex on `rule_id` prefix |

---

## 2. The two stacks (full inventory)

### Stack A — Sentiment (analyst/source outlooks)
- **Weight map** `_derive_common.py::_load_outlook_weights/_outlook_to_weight`: BULLISH=+3, BEARISH=−3, NEUTRAL=0 (tunable via `ref_param`, but **hardcoded fallbacks** in code). `'bench'` modifier de-rates by ÷3.
- **change_str → token** (`LONG→BULLISH, SHORT→BEARISH`): implemented **twice** — `derive_source_standing._normalize_change_str` (Python) and `derive_outlook_action._normalize_change_str_sql` (SQL).
- **ETF/II effective state (bundle-cap)**: canonical `derive_source_standing._build_etf_ii` (live) **and** a second full copy `derive_outlook_action._state_etf_ii` / `_state_etf_ii_tos` (legacy, kept for prev-period compare).
- **ETF fallback from BRR sign** (`derive.py`): `brr>0→BULLISH, <0→BEARISH` — same threshold reused in `_composite_outlook`.
- **Composite ensemble** `_composite_outlook`: each of `rr_brr, call/etf/ii_outlook, sss_signal_sign` votes ±1; sign of sum → label.
- **RR text from technicals** `_derive_rr_outlook_from_qe`: maps Stack-B's `trend_trade_rule` (−2..4) → "Bullish/Mild Bullish/…" — the *only* bridge between the two stacks, and it's one-directional text glue.
- **Dashboard counts** `_derive_dash_summary_impl`: `n_bullish/n_bearish/n_neutral` (aggregation only).

### Stack B — Technical (MA / Bollinger Excel ports, all thresholds hardcoded)
- **`bull` (MQ)** `_bull_expr`: from trade_rule, trend_rule, trade_trend_sd_rule, bblowdays/bbhighdays, lrr_above_trade. Ladder: `+3 / +2 / −2 / −3 / else 0`.
- **`perforbull` (MS)**: blends perf_sd_rule with `bull`.
- **`bb_bull_rule` (LW)** + `bb_bull_puts`: from Bollinger streak rules.
- **`short_term_outlook_if_lt_bullish / _bearish` (NN/NO)**: one function, two output columns differing only in the tail branch.
- **`bull_rr_action`/`not_bull_rr_action` (QM/QN)** and **`rr_bull_bear` (QP, 'B'/'!B')**: the gate that switches RR interpretation; final `QR` = "bearish wins, else BB, else RR decides."

### Action resolution (scores → vocab)
- **`trig_action`** `derive_actionable._derive_actionable_impl`: "most bearish wins, else most bullish" over fired groups using `ref_param_lookup` buysell scores (SA=−10…BM=+10).
- **`fc_strength`** `_FC_SCALE` (−3..+2) → `final_code/final_side`.
- **`v_rule_scorecard`**: direction-adjusts forward returns (`edge_20d = AVG(BUY ? fwd : −fwd)`), confidence = proven/promising/unproven.

---

## 3. Duplications (concrete — each is a drift risk)

| # | Concept | Copies | Risk |
|---|---|---|---|
| D1 | change_str → BULLISH/BEARISH | Python `_normalize_change_str` + SQL `_normalize_change_str_sql` | edit one, forget the other |
| D2 | ETF/II bundle-cap state | `_build_etf_ii` (live) + `_state_etf_ii`/`_state_etf_ii_tos` (legacy) | two algorithms claiming to be the same |
| D3 | Outlook → color | `actions.js::outlookColor` **and** `market_bar.js::outlookBg` re-derives with **different hex** (`#2f9e2f`/`#d83a3a` vs `#16a34a`/`#ef4444`) | same name shows two greens |
| D4 | RR "decision path" (QF<0/QK<0/QO) | backend `_derive_trend_trade_rules_impl` (QR) **and** `_common.js::renderRRAnalysis` re-implements it in JS from raw scores | UI can disagree with stored action |
| D5 | Action code → buy/sell side | 4 hand-typed lists: `v_rule_scorecard` regex, `_common.js isBull/isBear`, `rule_flow.js buysellColor`+`_compSide`, `actionable.js _RULE_EXTRA` | lists already diverge (`BC`,`BRW`,`SWW`,`SN` exist in some, not others) → wrong direction/edge shown |
| D6 | finalCall reconciliation | server `derive_actionable.py` **and** full JS reimpl `actionable.js::finalCall` (fallback) | large duplicated decision surface |
| D7 | brr>0/<0 sign threshold | `_composite_outlook` + `etf_outlook` COALESCE | same magic threshold in 2 spots |

Also: three different bull verdicts (per-source weights, ensemble label, counts) are computed from the **same** upstream sources with no shared code, and the SSS bucket math (`>0.5/>0.25/>0`) appears in both `_build_sss` and `derive_v2`.

---

## 4. Money-making assessment

**Where there is real edge machinery:** `v_rule_scorecard` is the right idea — direction-adjusted forward return, win rate, confidence tiers. That's the only part of the system that actually asks "does this signal make money?"

**Where money leaks:**

1. **The gate is unmeasured.** `bull`/`not_bull` and `bull_rr_action`/`not_bull_rr_action` decide which playbook runs, but no view scores the gate's own forward edge. You can't answer "when the gate says +3, what's the 20-day return vs +2?" → thresholds are faith-based.
2. **The stacks combine, but with no probability.** `_compute_final_call` reconciles sentiment (`consolidated_action`) and technical (`rr_action`) into the Final Call — so they *are* combined. But the combination uses fixed `_FC_SCALE` strengths, and sentiment-bull + technical-bear (a common, *informative* disagreement — often the highest-edge or highest-risk setups) collapses to HOLD/`fc_confidence="mixed"`, i.e. the split is sidestepped, never scored. You get an action, not a "P(up)=0.6, low agreement" number you can size on.
3. **Hardcoded Excel thresholds.** `≥2/≥3` etc. were tuned by hand in a spreadsheet years of regime ago. None are fit to your actual forward-return data, even though you now *have* that data (`drv_rule_outcome`).
4. **Direction by regex is fragile.** `v_rule_scorecard` infers BUY/SELL from `rule_id` text; the JS side lists diverge (D5). A mislabeled direction flips the sign of `edge_20d` — you could be trusting a "winning" rule that's actually a loser.
5. **Equal-weight votes.** `_composite_outlook` gives RR, call, ETF, II, SSS one vote each. If ETF outlook has 3× the edge of II, you're diluting your best source.

---

## 5. Recommendations (money-first, prioritized)

**P1 — Validate the gate before trusting it (cheap, high value).**
Add a `v_bull_gate_scorecard` view: bucket `bull` (−3..+3) × forward 5/20-day return, win rate, n. If `+3` doesn't out-return `+2`, the ladder is noise and you stop sizing on it. Same for `bull_rr_action` vs `not_bull_rr_action` — prove the regime switch actually changes outcomes.

**P2 — One calibrated bull-probability.**
Replace the equal-weight ensemble with a single model (start simple: logistic regression / weighted sum) over the *components of both stacks* → `P(up_20d)` per symbol, plus an agreement/dispersion measure. Weights learned from `drv_rule_outcome`, refreshed periodically. This is the number you size on. Keep the two stacks as inputs, not as two separate verdicts.

**P3 — Fit the thresholds to data.** You already have `etl/ml_tune_thresholds.py`. Point it at the bull-gate ladder so `≥2/≥3` become data-derived, regime-aware cutoffs instead of Excel relics.

**P4 — Kill the duplications (one source of truth each):**
- D5: one canonical `action_code → side/edge` map in the DB (or one JS module), imported everywhere. Delete the other three lists.
- D4 & D6: JS should *read* the backend's QR/finalCall result, not recompute it. Remove the JS re-derivations (keep only as explicit, tested fallback if truly needed).
- D3: `market_bar.js` uses `outlookColor()` only; delete the second palette.
- D1/D7: single helper for change_str→token and for the brr-sign rule.
- D2: delete `_state_etf_ii` legacy copy; have prev-period read from `drv_source_standing` snapshots.

**P5 — Make disagreement a feature.** Surface "sentiment vs technical agreement" as its own column. High-agreement-bull = size up; split = either best risk/reward or a trap — and now you can *measure* which, because P1 gives you the forward returns.

---

## Worth reconsidering

Before building new models (P2), spend an hour on P1. If the existing `bull` gate already has no measurable edge over a coin flip, that tells you the whole MA/Bollinger Excel port may not be worth maintaining — and the cheapest money-making move is deleting Stack B, not improving it. Measure first.

## 6. Implementation status — P1–P5 mapped to tasks

Each recommendation is specced as a developer task (`agent-tasks/TASK_<n>_*.md`) and
queued in `AGENT_WORK_7.md`. How to enable/revert without losing the current structure:
`docs/bull_rollout_runbook.md`.

| Rec | Task | What it does | Screen placement | Enable / revert |
|---|---|---|---|---|
| **P1** | **TASK 65** | Grade each *individual* atomic rule by its own forward-return edge (data already in `drv_rule_outcome` where `rule_kind='atomic'`) | **Performance** screen — new panel beside composite scorecard (trust/research view, NOT Actionable) | Always-on report; nothing to switch |
| **P2** | **TASK 66** | One calibrated `bull_prob = P(up_20d)` per symbol, weighting signals by measured edge, + `bull_agreement` | **Actionable** screen — sortable column + top filter (the money screen); `bull_prob` per-symbol on Rule Flow | Additive column; "enable" = sort/filter & trade by it. Ignoring it changes nothing |
| **P3** | **TASK 67** | Fit bull-gate thresholds to data, but keep **original + calculated + active** side by side with fit-history | **Rules/Param** screen — original vs calculated + "would it have made more?" comparison | The one real switch: `active_source='calculated'` to enable; `='original'` to revert (one row, instant). Defaults to original |
| **P4** | **TASK 68** | Collapse duplicated bull/bear logic (D1–D7) to one source of truth each | Invisible (behavior-preserving) | Always-on cleanup; nothing to switch |
| **P5** | **TASK 69** | Classify agree-bull / agree-bear / split, validate each bucket's forward edge | **Actionable** badge beside `bull_prob` (+ filter); validation report on **Performance** | Additive; reuses TASK 66's agreement inputs (no duplicate calc) |

**Build order (in `AGENT_WORK_7.md`):** 65 → 66 → 67 → 69 in sequence (66/67/69 need 65's
edge numbers); 68 runs in parallel. **Safety:** everything is additive or revertible —
money-affecting switches (trusting `bull_prob`, activating calculated thresholds) are
manual, so the current working structure is never lost until the user opts in.

*Sources: `etl/derive.py`, `etl/derive_cat_atomic_input.py`, `etl/derive_outlook_action.py`, `etl/derive_source_standing.py`, `etl/_derive_common.py`, `etl/derive_actionable.py`, `db/baseline.sql` (`v_rule_scorecard`), `api/routers/{dash,marketbar,rules,trace}.py`, `web/{actions,_common,market_bar,actionable,rule_flow}.js`.*
