# Sell-into-strength candidates — backtest (TASK_118 Part B)

Diagnosis-only report. Numbers below are computed directly against the DB
(same forward-return convention as `etl/compute_firing_outcomes.py`:
`drv_ma.last_price`, `LEAD(last_price, 5|20)` per symbol, direction-adjusted
so a SELL candidate wants price to fall — `da = -fwd20`). **Report only — none
of S1/S2/S3 are wired into the live rules engine.** Universe:
`ref_my_stocks WHERE active='Y'` (1,170 symbols), whole history in
`drv_rr`/`drv_ma` (same span as `docs/audit/loss_diagnosis_2026-07.md`,
~2026-02 → 2026-07). Same one-regime caveat as that report applies.

## Candidates

- **S1 — At/above TRR**: `last_price >= trr` (`drv_rr.trr`, i.e. `hist_rr.sell_trade`
  carried forward) — the existing `>=T` condition, scored standalone.
- **S2 — TRR + momentum roll**: S1 AND `a_macdh_d_brr < 0` (`drv_technicals`,
  the same MACDH-falling condition used in the QM/QN RR decision paths).
- **S3 — RR band down-shift**: `drv_rr.trr` lowered vs the symbol's prior
  `drv_rr` snapshot by more than 2%, while price sits at/above the band
  midpoint (`mrr`) — upper half of the band.

## Results

| Candidate | fires (n) | edge_20d | edge_5d | win_rate | 95% CI (20d) |
|---|---|---|---|---|---|
| S1 — At/above TRR | 5,048 | **-0.65%** | +0.12% | 51.0% | [-1.10%, -0.21%] |
| S2 — S1 + MACDH falling | 89 | -0.34% | +3.37% | 37.1% | [-5.34%, +4.65%] |
| S3 — RR band down-shift >2%, upper half | 851 | **-2.99%** | -1.20% | 47.6% | [-4.31%, -1.68%] |

For comparison, the existing reactive SELL composites (`docs/audit/loss_diagnosis_2026-07.md`
§B) range from edge_20d **-1.19% to -2.71%** across 30 rules, all with
fires >= 20 and none "proven" (all CIs are entirely negative or straddle a
weak positive).

## Reading

- **S1** has a large sample (n=5,048) and a CI that excludes 0 (proven-sample
  size), but the edge is still **negative** — being at/above TRR does not,
  on its own, predict a subsequent 20d decline in this dataset. It is
  *less bad* than the worst existing reactive rules, but that's a low bar;
  it is not a usable standalone sell signal.
- **S2** (adding the MACDH-falling filter) is inconclusive: n drops to 89 and
  the 95% CI is wide and straddles zero (`[-5.34%, +4.65%]`). No signal here
  either way — too small a sample to draw a conclusion, and the point
  estimate isn't distinguishable from noise.
- **S3** (RR band lowered >2% while price holds the upper half) is the
  **worst** of the three, with edge_20d -2.99% (n=851, CI entirely negative)
  — comparable to or worse than the worst existing reactive rules
  (`699-SW-Resistance` at -2.71%). A falling top-of-band combined with price
  still up near it looks intuitively like exhaustion, but in this data it
  fires into recoveries just as badly as the existing streak/trend-break
  rules do.

None of S1/S2/S3 beat the existing reactive SELL rules; S1 and S3 replicate
the same negative-edge pattern documented in `loss_diagnosis_2026-07.md` §B,
and S2 simply lacks sample size to say anything. This is consistent with the
report's core finding: over this one regime (~5 months, no sustained
downtrend), SELL-direction signals of this general shape (price near/above a
resistance-like level) systematically fire near local tops that then keep
rising, not falling — the same pattern already seen in the streak/trend-break/
resistance composites.

## Recommendation

**Do not activate S1, S2, or S3 as live composites.** None demonstrates a
positive, well-sampled edge; S1 and S3 actively replicate the existing
reactive-SELL problem rather than solving it, and S2 has too few fires to
judge. If sell-into-strength is worth pursuing again, it needs either (a) a
different regime in the training window (a genuine downtrend, not just this
recovery-heavy stretch — same one-regime caveat as the main diagnosis), or
(b) a materially different formulation (e.g. combined with a broader-market
/ macro regime filter rather than single-symbol RR-band geometry alone).
Until then, per TASK_118 Part A, keep the existing unproven SELL rules
downweighted (`low_confidence` annotation) rather than adding new ones on
top of them.
