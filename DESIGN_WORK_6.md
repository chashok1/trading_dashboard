# DESIGN_WORK — Round 6: TOS Bridge Band scripts (a_bb_top / a_bb_bottom) vs Hedgeye risk ranges

## Goal
The user wants the TOS custom columns `a_bb_top` and `a_bb_bottom` to track Hedgeye's risk-range top and
bottom (hist_rr `sell_trade` / `buy_trade`) as closely as possible. Hedgeye's ranges use **price, volume and
volatility**. The user says the designer has a better model than the one in the current scripts. Review the
scripts and give the model you recommend. **Design and research only. Do not change application code or the
TOS script files.**

## Files to read
- `TOS/BBTopNew.txt` (top, lean v2) and `TOS/BBBottomnew.txt` (combined top + bottom, `side` input). Old
  versions: `TOS/BBTop.txt`, `TOS/BBBottom.txt`.
- `docs/tos_rr_calibration.md`, `etl/calibrate_tos_rr.py` (earlier grid-search fits, TASK_128-131).
- Data: `hist_rr` (target), `hist_td` (close, imp_volatility, stored a_bb_top/a_bb_bottom), `hist_tl` (volume).

## What is already known (from the user's session on 2026-10-15)
- Python port of the new scripts matches the old stored values (median diff well under 0.3%), so the new
  scripts behave like the old ones.
- Against Hedgeye (34 stocks/ETFs, Mar-Oct 2026): median miss about 0.7-0.9% on both bands. Mean miss about
  5.7% on recent dates, driven by a few big misses.
- Worst cases on 10/14: TXG bottom -7.4% and top -4.8% (very volatile, IV about 106%), NVDA bottom +5.1%,
  XLK bottom +4.0%, META bottom +3.0%. Gaps flip sign day to day, so it is not a steady bias.
- A gradient refit of the existing inputs only moved the test-period median from 0.94 to 0.79 (top) and 0.87 to
  0.83 (bottom). The fit wanted about 45% weight on implied volatility instead of 25%, and the volume tilt
  moved the other way for top vs bottom. Remaining error is not fixable by retuning the current inputs.
- Current model: EMA(10) midpoint tilted by RelVol and momentum, width = k x sigma, where sigma blends 10-day
  price stdev with IV-implied move. Bottom also has a VIX term and a vol-level term.
- Futures, FX and indices have no usable TOSD band values; out of scope. OIH and RSP have no RR ranges.

## What to do
1. Say what the current scripts get structurally wrong for Hedgeye's way of building ranges (price, volume,
   volatility). Use the data above and anything you find in the repo.
2. Recommend a better model for the TOS scripts, in plain words plus the formula and every input/default.
   It must be computable in a ThinkScript custom column (no lookup tables; per-ticker overrides only through
   `GetSymbol()` checks).
3. Say how to validate it against hist_rr on a time-split holdout, and what accuracy would count as better
   (median and worst-case, by symbol), so we can test it before installing.
4. Say what to do about very volatile names like TXG.

## Principles (from the user)
- Plain English. Short. Bottom line first. One recommendation, not a menu.
- No email. Warnings show on screen.
