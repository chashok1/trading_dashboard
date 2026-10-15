# VERIFY_SPEC_7 - independent check of DESIGN_SPEC_7.md

## Bottom line
The pairing fix is real, and R7 is better than the current band on typical misses. But it is a smaller win than the spec says. It is NOT better "in every month, both sides", and since Aug 22 the current band is slightly better in the worst-10% tail on the top. Do not build the script as written: it has a likely compile error (`vol` is a reserved name). Fix that, then it is safe to try.

## Results
All numbers are mine (read-only queries, my own Python in the scratchpad). I could not reproduce the designer's exact universe: I used 32 plain-letter tickers in `hist_rr`, which gave 27-29 symbols and 1,400 test rows (1,286 with a stored band). The designer used 30 symbols. I scored the current scripts with the stored `a_bb_top` / `a_bb_bottom`. The designer used their own port of the scripts, which I did not have. Stored values from before about Aug 22 came from older scripts, which flatters R7 in June and July.

| # | Check | Verdict | My numbers |
|---|---|---|---|
| 1 | Pairing: `hist_rr.snapshot_date` = `hist_td.export_date` | CONFIRMED | 187 RR rows with a real "Prev Close", 11 files on disk (stocks and ETFs, stale days removed). Prev Close vs TOSD close, same `export_date`: median gap 0.05%, 91% within 0.5%. Vs the day before: median 0.91%, 34% within 0.5%. The same date is closer in 94% of rows. 154 more rows have Prev Close = 0 (ETFs); I left them out. The file named "RR 2026-09-29" carries "RR Date" 9/28 = its `snapshot_date`. `loaded_at` for snapshot 10/14 is 2026-10-15 08:14. |
| 1b | Stored band accuracy by pairing, Aug 22 - Oct 14 | CONFIRMED (smaller than claimed) | Same date (n 453): typical miss 0.60% top / 0.75% bottom, worst-10% 1.80% / 2.50%. Prior day (n 440): 0.67% / 0.75%, worst-10% 2.60% / 3.20%. The designer says 0.64 / 0.78 for the correct pairing. The gap is mostly in the tails. |
| 2 | R7 walk-forward, Jun 1 - Oct 14 | Mostly CONFIRMED | All test rows (n 1,400): top 0.56 / 2.38, bottom 0.64 / 2.71. On the rows that also have a stored band (n 1,286): R7 0.62 / 2.45 and 0.69 / 2.78. Stored band on the same rows: 0.77 / 3.87 and 0.87 / 3.50. Designer's R7 is 0.58 / 2.49 and 0.65 / 2.95, so I am close. Designer's current scripts are 0.71 / 3.26 and 0.89 / 3.46. Mine is a bit worse in the top tail (the old script version). |
| 2b | Month by month, typical / worst-10%, R7 top, then stored top | PARTLY WRONG | Jun 0.85 / 3.00 vs 1.13 / 5.49. Jul 0.55 / 2.41 vs 0.90 / 5.30. Aug 0.61 / 2.47 vs 0.71 / 2.54. Sep-Oct 0.52 / 2.08 vs 0.59 / **1.85**. Aug 22+ 0.52 / 1.98 vs 0.60 / **1.80**. So R7 loses the top worst-10% tail in Sep-Oct. Bottom: R7 wins everywhere (Sep-Oct 0.62 / 2.51 vs 0.74 / 2.41, so the bottom tail is also roughly even there). |
| 2c | Within 1% / within 2% | CONFIRMED | R7 65% / 61% (1%), 85% / 82% (2%). Current 59% / 54% and 78% / 76%. Designer: 66 / 63 and 86 / 81 vs 61 / 54 and 82 / 76. |
| 3 | Leakage | CONFIRMED (none in the walk-forward) | I re-fitted the settings myself using only dates before each test month, grid of 150 combos. Picks: center 4 days, vol smoothing 8 or 10, IV weight 0.35 or 0.25, kUp 1.58-1.63, kDown 1.99-2.02. Only the final deployment values (1.75 / 1.95) were fitted on all data, which is fine for production but not part of the test. My own all-data fit gives 1.68 / 2.01. |
| 3b | Sensitivity | CONFIRMED robust, with one catch | Multipliers are flat: top 1.55-1.95 and bottom 1.75-2.15 move the typical miss by 0.1 at most. IV weight 0 to 0.5 and vol window 5-20 days barely matter (0.56-0.62 top). **Center length matters:** 3-6 days is fine, 8 days gives 0.78 / 0.69 and 10 days gives 0.89 / 0.89. The spec's 5 is right. |
| 3c | Per-symbol: R7 worse by more than 0.3 | CONFIRMED | Top worse: XHB (+0.68, n 13), XTL (+1.24, n 8), XLRE (+0.49, n 16), XLE (+0.33, n 8). Bottom worse: SNOW (+2.47, n 8), TXG (+0.71, n 17). More names than the spec lists, but all small samples. Better by more than 0.3: 7 tops, 8 bottoms. |
| 3d | Named symbols, Jun-Oct, typical / worst-10%, R7 vs stored | CONFIRMED in direction | TXG top 1.36 / 13.0 vs 4.06 / 6.31, bottom 2.75 / 6.19 vs 2.04 / 5.66. NVDA 0.78 / 2.49 and 0.77 / 2.32 vs 1.06 / 3.10 and 1.01 / 2.62. XLK top 0.72 / 2.40 vs 0.90 / 1.91 (worse tail), bottom 0.65 / 2.19 vs 0.83 / 2.10. META 0.70 / 1.83 and 1.62 / 3.13 vs 1.24 / 3.62 and 1.73 / 4.07. AAPL 0.57 / 0.60 vs 0.81 / 1.06. MSFT 0.85 / 0.89 vs 0.99 / 1.20. Note TXG top worst-10% is 13%, worse than the stored band. The spec's "met" claim for TXG rests on the median only. |
| 4 | ThinkScript | WRONG as written (see below) | Likely compile error plus a few watch-outs. |
| 5a | 10/07 has zero open/high/low | CONFIRMED | 546 symbols, 93% with open = 0. 509 of the 561 October bad-high/low rows. Total bad high/low rows 2,412 = 1.86%. |
| 5b | Stale whole-day exports | CONFIRMED | 4/07: 859 of 859 closes identical to 4/06. 9/16: 547 of 547 identical to 9/15. Also 4/03: 843 of 859 identical (Good Friday). |
| 5c | `hist_rr.last_price` holds `buy_trade` | CONFIRMED | 99.45% of 9,651 rows. The exceptions are UST2Y (16) and a few single rows. |
| 5d | Usable Hedgeye rows | UNCLEAR | I count 7,208 rows with both prices and a `tos_symbol`, 52 symbols (6,452 since 2026-02-02). The spec says 6,616 over 49. The filter is not described well enough to reproduce. |
| 5e | 10/07 volume zero, TL partial days | UNCLEAR | `hist_td` has no volume column, so I could not check volume. The close prices on 10/07 are real in my data (R7 uses only closes and IV, so it is not hurt). |
| 1d | Gap-day lists | Not checked | Not material to the verdict. |

## ThinkScript review
- **`def vol = ...` will most likely not compile.** `vol` is a built-in alias for `volume`. Rename it (for example `volat`). This is the one blocker.
- `side.TOP` after `input side = {default BOTTOM, TOP}` is valid. `Sqr`, `Sqrt`, `Log` (natural log), `Exp`, `Max`, `IsNaN`, `Double.NaN` and `ExpAverage` all exist.
- `ExpAverage` uses weight 2/(n+1) and starts from the first value; my Python (`ewm(span=n, adjust=False)`) matches that. The first bar has ret = 0, which biases `rv` low for the first few bars only. Using just the last 40 bars changes vol by 0.01%, the last 15 bars by 2.5% median (7.4% max). A watchlist column with a short history is fine at 40+ bars.
- `imp_volatility()` is a fraction (0.43 = 43%) in `hist_td`, so `/ Sqrt(252)` is right. The stored IV is rounded to 2 decimals, but the live column is not; small difference.
- The spec does not set the aggregation period. The column must be Daily, or `close` and `imp_volatility()` will be on a different bar size. Say so in the install notes.
- `imp_volatility()` has gaps or short history for some symbols; the script falls back to realized vol alone when it is NaN, which is correct. Indices (SPX, VIX) have no stored `a_bb`, so they cannot be scored.
- No VIX use, so the `close("VIX")` risk does not apply.
- The `minVol` floor 0.003 is a guess and did not bind in my data.

## Other findings
- The drift monitor and calibrator use the same wrong pairing (spec says so; I did not open the files beyond the docstring, which states `hist_td snapshot_date < D`). Agreed this should be fixed first.
- Spec table headline "R7 wins every month and side" should be reworded to "wins typical miss in every month; the top tail is slightly worse than the latest script since Sep".
- The spec's "current scripts" numbers come from a port I could not inspect. Against the real stored values, R7's edge over Aug 22+ is smaller than the spec says: typical 0.52 vs 0.60 (top) and 0.62 vs 0.75 (bottom), versus the spec's 0.47 vs 0.65 and 0.53 vs 0.66.
- Test windows are short (about 87 trading days) and one regime. Treat gains under 0.1 points as noise.

## Verdict
R7 is better than the current scripts on typical misses by about 0.1 to 0.2 points on each side (roughly 15-20%), and it is simpler. Over the longer test it also clearly helps the tails, but that is mostly because older script versions were poor in June and July. Since Aug 22 the top tail is not better. Recommendation: fix the `vol` name, set the column to Daily, run it beside the old columns for a few days, then switch. Not a game changer, but safe to build after the rename.

ALL_DONE
