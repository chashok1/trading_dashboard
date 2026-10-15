# DESIGN_WORK — Round 7: VERIFY the analysis of Hedgeye risk ranges vs TOS bands (do not trust it; re-check it)

## Goal
The user wants the TOS columns `a_bb_top` / `a_bb_bottom` to track Hedgeye's risk-range top/bottom
(`hist_rr.sell_trade` / `buy_trade`) as closely as possible, using price, volume and volatility and their rates
of change. The user said: "This is a complex script and most important to me. Don't cut corners. Whatever you
do, I want it verified by the designer." Another agent (the main Claude session) ran a long analysis on
2026-10-15. **Your job is to independently verify it: re-derive the key numbers yourself, find mistakes, and say
which conclusions hold.** Design and research only. Do not change application code or TOS script files. Read-only
SELECT queries are allowed (see your rules). Put throwaway scripts in your own scratchpad, not the project.

## Where the work is (read these, then rebuild your own version where noted)
Scripts (read-only for you; copy to your scratchpad if you want to modify):
`C:\Users\chash\AppData\Local\Temp\claude\C--Ashok-Invest-Projects-trading-dashboard\10f92af1-c1f2-4818-b401-24962a5f5c7f\scratchpad\`
- `audit.py`, `ds.py` (clean dataset + exact prior-trading-day pairing), `feat.py` (features), `wf.py`
  (walk-forward model comparison), `state.py` (memory/smoothing test). Older exploratory scripts: `ivw.py`,
  `pvw.py`, `quad.py`, `roc2.py`, `roc3.py`, `gbm.py`, `rs.py`, `anchor.py`, `tune*.py`, `mix.py`, `v3chk.py`.
- Spec from your Round 6: `DESIGN_SPEC_6.md`. TOS scripts: `TOS/BBTopNew.txt`, `TOS/BBBottomnew.txt`,
  `TOS/BBChart.txt`, `TOS/BridgeBands_v3_Chart.txt`.

## Pairing rule (fixed by the user — do not change)
Hedgeye computes RR(D) between 5 and 8 am on D from D-1's close. TOSD rows are exported after D-1's close. So pair
RR(D) with the TOSD row of the **exact prior trading day** (holidays removed). Do not use same-day matching.

## Claims to verify (check each; say CONFIRMED / WRONG / UNCLEAR with your own numbers)
Data quality
1. 164 TOSD days (2026-02-02 to 2026-10-14); 1.9% of end-of-day rows have zero/missing high or low (561 in
   October, worse than earlier months); `hist_rr` starts 2026-01-01 and has 6,616 usable rows (top>bottom,
   non-reversed, mapped); 78% have an exact prior-day TOSD row (the rest are mostly January, before TOSD starts,
   plus gap days 3/20-3/27, 4/17-4/24, 9/24-9/29 and two symbols TOSD doesn't carry). Is the exact-pairing and
   bad-high/low cleaning right? Is the holiday list in `ds.py` right for 2026? Is `vA10` (volume vs 10-day
   average, mean -0.69) suspicious, i.e. is the `hist_tl` end-of-day volume a partial-day snapshot?
2. My earlier comparisons (before the clean dataset) paired with the last available TOSD row even when it was
   stale. Confirm this inflated misses and quantify it.
Accuracy of the current scripts (stored `a_bb_*`, exact pairing)
3. Since 2026-08-22: typical miss top 0.69%, bottom 0.80%; worst-10% 3.54% both. Mar-Jul (older scripts) 1.31%/1.19%.
4. New scripts (`BBTopNew`, `BBBottomnew`) behave like the old ones (Python port within ~0.3% median).
What explains Hedgeye's ranges (walk-forward folds Jun, Jul, Aug, Sep-Oct, trained only on earlier dates, 30 stocks/ETFs,
2,707 rows; futures/indices excluded)
5. Typical miss, top / bottom: volatility only 1.07% / 1.09%; + intraday volatility 1.10% / 1.09%;
   + rate-of-change (price, volume, implied vol) 0.85% / 0.79%; + intraday highs/lows (position) 0.84% / 0.76%;
   everything 0.83% / 0.76%. Since Aug 22 the old script is 0.65% / 0.71% (typical) and 2.38% / 2.92% (worst-10%).
   So even a tree model with every input I could build only matches the old script. Is this a fair test? Is the model
   too weak, over-regularized or leaking? Try a different model class and check.
6. Of the three ROCs, only price ROC carries information; volume ROC (5 definitions incl. today vs prior 10-day
   average) and volatility ROC/percentiles (incl. the stored 0-100 `a_iv_percentile`) add ~nothing. Re-test; the user
   believes Hedgeye uses rate of change of all three. Try other definitions (e.g. rank/percentile over 10-60 days,
   z-scores, signed combinations like price-up-volume-up-vol-down, the PVV buckets in `docs/pvv_logic.md`).
7. The top relies most on a recency-decayed intraday high (`dhh_c`, 23%): Hedgeye's TXG top stayed near 100 for days
   after an intraday high of 102.81 on 10/6 (close 80.66). Confirm with other symbols and with the exact decay.
8. Hedgeye's own previous range predicts today's far better than all inputs: typical 0.58% top / 0.57% bottom vs
   0.88% / 0.76% for all inputs (n=1,455). Our own model smoothed by a 2-day exponential average: 0.80% / 0.73%
   (small gain). So Hedgeye's range looks like a slowly-updating state, not a fresh function of the day's data.
   Figure out the update rule: e.g. does Hedgeye's range move only when price/volume/vol cross a threshold, or
   change by a fraction of the gap to a target? Look at day-to-day changes in HE's top and bottom per symbol.
Other findings to check
9. Width: Hedgeye's width correlates 0.80 with recent realized volatility, 0.39 with implied volatility level; the
   day-to-day change in width has ~0 correlation with the change in implied volatility (n~3,900); price move:
   Hedgeye's midpoint follows price ~0.47 per 1%, and follows LESS on high-volume days (0.19-0.56) than low-volume
   days (0.52-0.93).
10. Rescaled range / Hurst (Mandelbrot) did not beat plain daily volatility (typical width error 29.6% for Hurst
    scaling vs 17.6% for smoothed daily vol).
11. A "mixed" model (old code for some cases, v3 for others) is not justified yet; v3 untuned lost almost everywhere.

## What to do
1. Re-run or re-derive claims 1-11 yourself (your own queries/scripts). List every claim as CONFIRMED / WRONG / UNCLEAR
   with your numbers, and list any mistake in the method (leakage, wrong pairing, wrong units, bad rows, survivorship,
   small sample, overfitting, fold design).
2. Use ALL data available: `hist_td` (OHLC, IV, HV, percentiles), `hist_tl`, `hist_tw` (52-week and 3-month highs/lows,
   days to earnings, since 2026-05-11), `hist_to`, `hist_y`, `hist_quote_daily` and `hist_macro` (index/futures closes,
   VIX/VVIX; long history for indices only), `drv_pvv`, `drv_outlooks`, `drv_market_stat`, the other Hedgeye feeds
   (`hist_call`, `hist_ps`, `hist_etf`, `hist_rta`, `hist_hedgeye_stance`). Say which of these add anything. Include
   earnings proximity (TXG is earnings-driven) and market-wide state (VIX level and change).
3. Study the Hedgeye series itself: how top and bottom evolve day to day per symbol (persistence, jumps, what triggers
   a big move, relation to the previous day's intraday high/low, to the 3-week trade window in `hist_tw`).
4. Recommend the best model that a ThinkScript custom column can run (no access to Hedgeye's values; recursive
   `CompoundValue`/`ExpAverage` state is allowed). Give formula, every input and default, and the test numbers on
   walk-forward folds against the current scripts (typical and worst-10% miss, by symbol, TXG/NVDA/XLK/META).
5. If you conclude the target cannot be matched much better than the current scripts, say so plainly with the evidence.

## Principles (from the user)
- Plain English. Short. Bottom line first. One recommendation, not a menu.
- Verify, do not assume. No email. Warnings show on screen.
