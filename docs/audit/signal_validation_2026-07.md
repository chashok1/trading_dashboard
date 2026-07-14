# Signal validation scorecards — bull gate, Final Call, sources, thresholds (TASK_123)

Read-only + additive report. Numbers below are computed directly against the
live DB via three new analyst views added to `db/baseline.sql`
(`v_bull_gate_scorecard`, `v_final_call_scorecard`, `v_source_edge_scorecard`)
plus an aggregate over the existing `drv_inferred_action` (TASK_121). **No
rule/threshold/derive/UI changes were made.** Same one-regime caveat as
`docs/audit/loss_diagnosis_2026-07.md` and `sell_candidates_2026-07.md`
applies throughout: **~4-5 months of data, one market regime (a bounce)** —
every number below could be a regime artifact rather than a durable edge.

## Prep — outcome dataset refresh

```
python -m etl.backfill_derives            # 0 missing dates (drv_trig already
                                           # covers every hist_td date through
                                           # the anchor, 2026-07-10) — no-op
python -m etl.compute_firing_outcomes --truncate
```

`drv_rule_outcome` after the refresh: **7,924,452 rows**, `as_of_date` range
**2026-02-02 → 2026-06-11** (composite: 1,164,078 rows; atomic: 6,760,374
rows across 98 resolved feature columns). The max `as_of_date` is ~4.5 weeks
behind the 2026-07-10 anchor — this is *expected*, not stale: a 20-trading-day
forward return needs 20 future trading days of `drv_ma.last_price`, so no
row can have a non-null `fwd_20d_pct` for a date closer than ~20 trading days
(~4-5 calendar weeks) to the most recent price. This lag is a property of
`etl/compute_firing_outcomes.py`'s own `_fwd` CTE (unchanged by this task),
not a bug.

**Forward-return mechanism for the new views:** each view builds its own
`LEAD(last_price, 5)` / `LEAD(last_price, 20)` window over `drv_ma`, keyed by
`(tos_symbol, as_of_date)` — the same row-offset convention
`compute_firing_outcomes.py` and `v_user_action_performance` already use.
This was chosen over joining `drv_rule_outcome` directly (which already has
`fwd_5d_pct`/`fwd_20d_pct` per rule firing) because `drv_rule_outcome` only
has a row where *some* rule fired that day — bucketing by `bull`,
`final_code`, or `source_code x action` needs a return for every
`(tos_symbol, as_of_date)` that has a bucket value, not only the subset where
a composite/atomic rule happened to also fire. Verified against the schema
with `\d` equivalents before writing (`drv_cat_atomic_input.bull`,
`drv_tn_td_bb_rr.rr_bull_bear`, `drv_actionable.final_code/fc_confidence/
final_side`, `drv_outlook_action.source_code/action` all confirmed present
via `information_schema.columns`).

---

## A. Bull-gate scorecard (assumption A1)

`SELECT * FROM v_bull_gate_scorecard;`

**`bull_ladder` (MQ ladder, drv_cat_atomic_input.bull, -3..+3):**

| bull_bucket | n | avg_fwd_5d | avg_fwd_20d | median_fwd_20d | win_rate_20d |
|---|---|---|---|---|---|
| -3 | 2 | 1.085 | 1.488 | 1.488 | 0.500 |
| -2 | 2,163 | 1.210 | **4.850** | 1.985 | 0.588 |
| 0 | 57,156 | 0.515 | 1.628 | 0.206 | 0.513 |
| 2 | 3,362 | -0.198 | **-1.454** | -1.111 | 0.414 |
| 3 | 8,378 | -0.129 | **-0.896** | -1.451 | 0.421 |

(`bull` only ever takes -3/-2/0/2/3 in this dataset — the ±1 rungs of the
ladder are unused.)

**`rr_bull_bear` (QP, drv_tn_td_bb_rr.rr_bull_bear, 'B'/'!B'):**

| bull_bucket | n | avg_fwd_5d | avg_fwd_20d | median_fwd_20d | win_rate_20d |
|---|---|---|---|---|---|
| !B | 57,710 | 0.257 | 1.003 | 0.000 | 0.480 |
| B | 7,064 | 0.976 | **2.594** | 1.058 | 0.554 |

**Does +3 out-return +2?** No — +3 (avg_fwd_20d -0.896%) is *slightly better*
than +2 (-1.454%) but both are **negative**, and both are dramatically worse
than -2 (+4.850%). **The MQ ladder is inverted over this regime**: the
*more bullish* the label, the *worse* the actual forward 20d return, and
vice versa (-2 is the best-performing bucket by a wide margin, +2/+3 are the
worst). n is large enough in every populated bucket except -3 (n=2, ignore)
to trust the sign: -2 (n=2,163), 0 (n=57,156), 2 (n=3,362), 3 (n=8,378).

**Does 'B' vs '!B' separate outcomes?** Yes, in the expected direction: B
(bullish) avg_fwd_20d = +2.594% vs !B (bearish) = +1.003%, win_rate 55.4% vs
48.0% — a real, correctly-signed, non-trivial gap on a large sample
(n=7,064 vs 57,710).

**Conclusion:** the RR-derived `rr_bull_bear` (QP) flag is doing real,
correctly-directed work; the MQ `bull` ladder (-3..+3) is not just noise, it
is **inverted** — using it as a playbook switch in its current form would
point the wrong way over this regime. This directly confirms the concern in
`docs/audit/bull_calc_analysis.md` (P1, still open).

---

## B. Final Call scorecard (assumptions A2, A3)

`SELECT * FROM v_final_call_scorecard ORDER BY final_code, fc_confidence;`

| final_code | fc_confidence | n | avg_fwd_5d | raw_avg_fwd_20d | edge_20d (dir-adj) | median_fwd_20d | win_rate_20d |
|---|---|---|---|---|---|---|---|
| BM | high | 98 | 1.405 | 3.213 | **3.213** | 4.496 | 0.633 |
| BMN | gate | 340 | 0.647 | 3.211 | **3.211** | 2.448 | 0.671 |
| BMN | high | 160 | 0.434 | 2.121 | **2.121** | 2.147 | 0.700 |
| BS | high | 2 | -7.819 | -15.947 | -15.947 | -15.947 | 0.000 |
| HOLD | gate | 655 | 0.266 | 1.653 | 1.653 | 1.528 | 0.583 |
| HOLD | mixed | 646 | 11.933 | 12.211 | 12.211 | 1.340 | 0.573 |
| HOLD | none | 5,638 | 0.598 | 1.971 | 1.971 | 1.236 | 0.563 |
| SA | gate | 32 | -1.556 | -5.104 | **5.104** | -6.828 | 0.719 |
| SO | gate | 33 | -0.240 | -1.206 | **1.206** | -0.451 | 0.606 |
| SS | high | 59 | 3.788 | 5.032 | **-5.032** | 1.607 | 0.373 |
| SS | mixed | 58 | -0.230 | -0.730 | **0.730** | -0.647 | 0.534 |

**Does BM beat BS in adjusted fwd return?** BM/high edge_20d = +3.213%
(n=98) is the strongest positive buy-side result in the table. BS/high has
only n=2 (-15.947% — noise, ignore for direction). No usable BS sample
exists to compare — **can't validate BM > BS**, only that BM (and BMN) show a
real, decent-sample positive edge.

**Does `fc_confidence='high'` beat `'mixed'` on the buy side?** There's no
buy-side `mixed` row at all (the only `mixed` rows are HOLD and SS) — so this
specific comparison is untestable from this data. On the sell side, SS/high
(edge -5.032%, i.e. price *rose* 5.03% after a "high confidence" SELL SOME —
**wrong direction**, win_rate only 37.3%) is *worse* than SS/mixed (edge
+0.730%, correctly signed, win_rate 53.4%) — the opposite of what "high >
mixed" would predict. SS/high is a red flag: 59 fires, systematically wrong
direction.

**For mixed rows, is the discarded disagreement flat or informative?**
HOLD/mixed's raw_avg_fwd_20d (+12.211%) is dominated by extreme outliers
(`TNX:CGI`/`TYX:CGI`-style low-priced/index symbols with >800% swings) — the
**median** (1.340%) is a fairer read and is close to HOLD/gate's (1.528%).
But looking at **dispersion directly** (median absolute 20d move, robust to
the same outliers): HOLD/mixed = **7.101%** vs HOLD/gate = 5.235% and
HOLD/none = 5.915% — mixed rows move about **20-35% more**, in either
direction, than clean-signal HOLD rows. **Verdict: disagreement is
informative (higher-movement), not flat/safe** — collapsing it to HOLD
discards real signal about which symbols are about to move, even though it
doesn't say which way.

---

## C. Per-source edge scorecard (assumption A4)

`SELECT * FROM v_source_edge_scorecard ORDER BY source_code, action;` (full
table has 21 rows — one per source_code x action; n-weighted buy-family
(ADD+INCREASE) and sell-family (REDUCE+REMOVE) rollup below.)

| source_code | n (buy-fam) | edge_20d (buy-fam) | n (sell-fam) | edge_20d (sell-fam) |
|---|---|---|---|---|
| RR | 1,888 | **+2.838** | 1,166 | -2.671 |
| SSS | 302 | **+2.325** | 136 | -1.593 |
| CALL | 7,945 | +0.518 | 82 | **+5.261** |
| II | 170 | -1.418 | 77 | +2.026 |
| PS | 106 | -2.066 | 29 | +1.574 |
| ETF | 51 | -3.396 | 38 | -0.626 |

**Current fixed `SOURCE_ORDER`:** PS=1 · ETF=2 · RR=3 · SSS=4 · II=5 · CALL=6
(lower number = higher precedence).

**Empirical ranking by buy-family edge_20d (best to worst):** RR (+2.838,
n=1,888) > SSS (+2.325, n=302) > CALL (+0.518, n=7,945) > II (-1.418, n=170)
> PS (-2.066, n=106) > ETF (-3.396, n=51).

**This is close to the *reverse* of the fixed order.** The two sources given
top precedence (PS, ETF) have the **worst** empirical buy-side edge in the
dataset (both negative, n=106/51 — small but past the "promising" n≥30
threshold used elsewhere in this codebase); the two sources ranked lowest
precedence (RR, SSS) have the **best** edge, and RR in particular has both a
large sample (n=1,888) and the best sell-family edge too (buy-family +2.838%,
sell-family -2.671% — correctly signed and large in both directions). CALL
has by far the largest sample (n=7,945 buy-family) but only a modest positive
edge (+0.518%) — high volume, low individual conviction, consistent with it
being the standing-list flooder identified in `docs/audit/loss_diagnosis_
2026-07.md` (E.3).

**Does the data justify `SOURCE_ORDER`?** No — on this regime's evidence, the
order should run closer to RR/SSS first, CALL middling, PS/ETF/II last, not
PS/ETF first.

---

## D. Inferred-action aggregate — who loses the money?

Aggregated from `drv_inferred_action` (TASK_121), restricted to rows with a
computed `fwd_20d_pct` (i.e. old enough to have a full 20-trading-day
lookforward — excludes the most recent ~4-5 weeks of inferred trades, same
lag as drv_rule_outcome above). `est_dollar` **is** available on the table,
so a dollar-weighted average is reported alongside the plain mean.

| stance | n (with fwd_20d) | avg_fwd_5d | avg_fwd_20d | $-weighted avg_fwd_20d |
|---|---|---|---|---|
| NO_SIGNAL | 525 | -0.260% | -0.875% | +1.027% |
| CONTRADICTED | 364 | -0.183% | -2.948% | -3.275% |
| FOLLOWED | 474 | -0.722% | **-3.567%** | **-3.634%** |

(Unfiltered — including rows too recent for a 20d return yet — the full
table has 5,466 rows total across all three stances, per TASK_121's original
backfill; the 1,363 rows above are the subset old enough to score.)

**FOLLOWED trades average -3.567% (20d, $-weighted -3.634%), CONTRADICTED
trades average -2.948% (20d, $-weighted -3.275%) → the system is the larger
loss source.** Following the system's own recommendation performed *worse*
than going against it, on both the plain and dollar-weighted view, over this
window. NO_SIGNAL trades (no active recommendation either way) lost the
least on a dollar-weighted basis (+1.027%) and only mildly on a plain
average (-0.875%) — trades made with no system signal at all outperformed
trades made *with* the system's blessing.

---

## E. Hit-threshold sensitivity (assumption A6)

Report-only — no `ref_settings` change. Recomputed win-rate at the current
threshold (±0.5%, matching `outcome_hit_threshold_buy`/`_sell` in
`ref_settings`) vs a stricter ±2% threshold, directly from
`drv_rule_outcome.fwd_20d_pct` (composite rules only, `fires >= 100` for
stability; the optional std-dev-unit threshold was skipped — `hist_tw`'s
`std_dev`/AC join wasn't convenient enough to justify given ±2% is the
mandatory comparison and already answers the question).

**Top 10 by current (±0.5%) win rate, compared to ±2%:**

| rule_id | n | win_rate (±0.5%) | win_rate (±2%) |
|---|---|---|---|
| 52-BS-BRR | 27,477 | 0.503 | 0.425 |
| 188-BR-TNabvTD-UP-MACD-DAY | 16,258 | 0.487 | 0.406 |
| 99-BS-Min | 19,165 | 0.483 | 0.403 |
| 268-BS-3M-HiHi | 15,506 | 0.482 | 0.400 |
| 299-BS-BB-Streak-HiHi-TN-TD | 15,582 | 0.482 | 0.399 |
| 198-BS-TN-LRR-UP-MACD | 16,112 | 0.481 | 0.399 |
| 197-BS-TN-LRR-UP-DAY | 15,376 | 0.481 | 0.399 |
| 298-BS-BB-HL-HiHi-TN-TD | 15,375 | 0.481 | 0.399 |
| 269-BS-Bull | 15,383 | 0.481 | 0.399 |
| 187-BR-NoTN-NoTD-UP-MACD-DAY | 15,376 | 0.481 | 0.399 |

**Bottom 10 by current (±0.5%) win rate, compared to ±2%:**

| rule_id | n | win_rate (±0.5%) | win_rate (±2%) |
|---|---|---|---|
| 699-SW-Resistance | 1,239 | 0.350 | 0.278 |
| 897-SW-Vlm-Spike-Price-Dn | 484 | 0.397 | 0.343 |
| 783-SW-Vol-Spke-Price-Dn-Past | 993 | 0.419 | 0.362 |
| 898-SA-Streak-VeryBad | 18,431 | 0.430 | 0.346 |
| 784-SS-Streak-GoingBad | 17,581 | 0.435 | 0.350 |
| 893-SA-TRR-blw-TN | 16,828 | 0.436 | 0.353 |
| 899-SA-Trend-Breaks | 16,634 | 0.437 | 0.352 |
| 896-SA-TRbelowTN-Trade-Breaks | 16,227 | 0.437 | 0.353 |
| 782-SS-3mnHigh | 15,749 | 0.441 | 0.356 |
| 787-SS-Bull-TRR-Rev | 15,418 | 0.441 | 0.355 |

**Does the ranking materially reorder?** Across all 64 composite rules with
`fires >= 100`: mean absolute rank shift = 1.84 positions, max shift = 22
positions; top-10 overlap 7/10, bottom-10 overlap 8/10. Win rates uniformly
drop ~8-10 points at the stricter threshold (expected — fewer moves clear a
2% bar than a 0.5% bar) but the **relative** ordering of rules is mostly
preserved; a handful of rules move substantially (up to 22 spots).

**Verdict: weak, not fully broken.** ±0.5% is clearly "below noise" in the
absolute sense (win rates read ~48-50% either way, i.e. barely better than a
coin flip at the current threshold, and even lower at ±2%) — so A6's
underlying worry (thresholds don't mean much on their own) holds. But
because the *relative* ranking across rules is fairly stable between the two
thresholds, existing rule tuning/rankings built on the current threshold
aren't wholesale wrong — they're just not meaningfully "hits" in an absolute
sense. A recalibration would mainly help by re-scaling the reported win-rate
number, not by re-ordering which rules look good vs bad.

---

## F. Verdicts

| # | Assumption | Verdict | Evidence | Top implied changes (not implemented — follow-up design) |
|---|---|---|---|---|
| A1 | Bull gate ladder (-3..+3) correctly switches the RR playbook | **broken** | `bull` is inverted over this regime: -2 avg_fwd_20d +4.85% vs +3 at -0.90% (§A) | Stop gating the RR playbook on `bull`; if kept, re-derive/re-sign the ladder from measured edge, not the Excel port |
| A2 | `_FC_SCALE` strengths (BM > BS > …) reflect real conviction | **untestable here** | No usable BS sample (n=2) to compare against BM (n=98, edge +3.213%) this regime (§B) | Needs more history/regimes before BM vs BS can be ranked with confidence |
| A3 | Disagreement → HOLD ("mixed") is safe | **weak/broken** | mixed rows move ~20-35% more (median |fwd20|) than clean-signal HOLD rows; SS/high is directionally wrong (edge -5.03%) while SS/mixed is correct (+0.73%) (§B) | Score disagreement instead of discarding it; investigate why "high confidence" SS underperforms "mixed" SS |
| A4 | Fixed source precedence (PS>ETF>RR>SSS>II>CALL) reflects real edge | **broken** | Empirical buy-edge ranking is close to the reverse: RR/SSS best, PS/ETF worst (§C) | Re-rank SOURCE_ORDER off measured edge_20d, weighted by n for stability |
| A5 | Scorecard edges generalize beyond this dataset | **not addressed by this task — standing caveat** | ~4-5 months, one regime (a bounce), applies to every number in this report | Re-run this whole report once a second regime (a drawdown/chop period) is in the data |
| A6 | Hit thresholds ±0.5%/±2% are meaningful cutoffs | **weak** | Absolute win rates near 45-50% either way (below-noise in the literal sense); relative rule ranking mostly holds (mean rank shift 1.84/64, top10 overlap 7/10) (§E) | Recalibrate the reported win-rate scale, not the rule ranking itself |

**Standing regime caveat:** every result in this report spans ~2026-02-02 →
2026-07-10 (the `drv_rule_outcome`-scored window ends 2026-06-11 due to the
20-trading-day forward-return lag) — one continuous market regime (a
bounce), ~4-5 months. None of these findings have been tested against a
drawdown or chop period; A1/A4's inversions in particular could flip again
in a different regime and should be re-checked once one is available.
