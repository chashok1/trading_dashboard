# Design Spec — DESIGN_WORK_6

## Goal
Make the TOS columns `a_bb_top` / `a_bb_bottom` track Hedgeye's risk-range top and bottom (`hist_rr.sell_trade` / `buy_trade`) more closely, using price, volume and volatility, in a model a ThinkScript custom column can run. Used by the user, and by the app wherever it falls back to the TOS band.

## Design

### Bottom line
Rebuild the band as **"today's price, plus or minus a percent width set by volatility, shifted by where price sits in its recent move."** Measure volatility from **daily price changes** (not from the spread of price levels), blend in implied volatility, cap implied volatility when it runs far above realized (earnings, TXG), and dampen very high volatility. One script makes both columns. The 3-day rate-of-change test (§3 step 9, run 2026-10-15) found that rate of change does **not** explain the big misses, so those terms ship switched off (set to 0). About 8 active settings instead of about 17 today.

### 1. What the current scripts get wrong
1. **They measure volatility the wrong way.** `sigma` is the spread of the last 10 *closing prices*. That is not how much a stock moves each day. A stock trending steadily up gets a wide band even when its daily moves are small. A flat but choppy stock gets a narrow one.
2. **The band jumps when an old day drops out.** A big gap day sits inside the 10-day window, then falls out all at once 10 days later. The band then jumps. This fits "the miss flips sign from day to day". Hedgeye's ranges move smoothly: yesterday's range predicts today's within about 0.4% (see `docs/audit/tos_rr_realignment_2026-10.md`).
3. **Dollars and percents are mixed.** Width is in dollars, the IV leg is a percent turned into dollars, and the tilts are dollars again. So a setting that works for a $50 ETF doesn't carry over to a high-flying stock. ETFs already fit well (about 0.2-0.3%). Single stocks don't (about 0.7-1.0%).
4. **Center and width are tangled.** Each band has its own midpoint and its own width settings. When the refit pushed the volume tilt one way on the top and the other way on the bottom, volume was really acting as a hidden width setting. The two bands fight each other, and that invites overfitting.
5. **IV gets too little weight, and the wrong IV.** The refit wanted about 45% weight on IV, up from 25%. That is the data telling us the price-level spread is a poor volatility measure. But raw TOS IV also includes earnings jumps that Hedgeye's range ignores. TXG at about 106% IV is the extreme case.
6. **Width grows in a straight line with volatility.** Hedgeye's ranges on very volatile names are narrower than a straight-line rule would give. One global setting can't fit both XLU and TXG.
7. **The midpoint lags.** EMA(10) plus tilts sits behind fast moves. The 5-day price change still links to the top-band miss (ρ ≈ −0.27, audit addendum).
8. Small point: `BBTopNew.txt` uses 15.87 and `BBBottomnew.txt` uses Sqrt(252) for the same constant.

### 2. Recommended model ("Vol-unit range", v3)
In plain words:
- **How much it moves:** daily volatility = a blend of (a) a smooth average of recent daily % moves and (b) implied volatility, with implied volatility held to no more than 1.5× the realized number.
- **Very volatile names:** above a normal level (2% a day), volatility counts for less than a straight line would give. This keeps TXG-type ranges from blowing out.
- **How wide:** half-width (%) = a multiplier × that volatility. The top and bottom get their own multiplier, because Hedgeye's ranges are not even around price.
- **Where price sits in the range:** if price has run up fast versus its 10-day average (measured in volatility units), price sits near the top. If it has dropped fast, it sits near the bottom. Strong volume on the move pushes that harder. A steady longer trend lifts the whole range in the trend's direction.
- **Price** gives the anchor and the stretch, **volume** confirms the stretch, and **volatility** sets the width. All three legs are used.

Formula (all in log/percent terms):
```
ret      = Log(close / close[1])
rv       = Sqrt(ExpAverage(Sqr(ret), rvLen))                 # realized daily vol, smooth (no window cliff)
ivD      = imp_volatility() / Sqrt(252)                       # implied daily vol
ivD_s    = ExpAverage(ivD, ivSmoothLen)                       # smooth one-day IV spikes
ivUsed   = Min(ivD_s, ivCapRatio * rv)                        # earnings / TXG guard
volRaw   = if IsNaN(ivD) then rv else (1 - ivWeight) * rv + ivWeight * ivUsed
vol      = volRef * Power(volRaw / volRef, volPower)          # compress very high vol

relVol   = Min(2, Max(0.5, Average(volume, 3) / Average(volume, 15)))   # 1 if missing
stretch  = Log(close / ExpAverage(close, 10)) / vol           # how far price ran, in vol units
trend    = Log(ExpAverage(close, 8) / ExpAverage(close, 26)) / vol
# --- rate of change (user's view: Hedgeye reacts to CHANGE, not just level) ---
pRoc     = Log(close / close[rocLen]) / (vol * Sqrt(rocLen))  # price change over rocLen days, in vol units
vRoc     = Log(Max(0.25, Min(4, Average(volume, rocLen) / Average(volume[rocLen], rocLen))))  # volume now vs the prior rocLen days; 0 if missing
ivRoc    = Log(ivD_s / ivD_s[rocLen])                         # IV change over rocLen days; 0 if IV missing
skew     = Min(0.8, Max(-0.8, cStretch * stretch * (1 + cVolume * (relVol - 1))
                                - cTrend * trend
                                + cPRoc * pRoc * (1 + cVRoc * vRoc)))
widthMul = Min(1.5, Max(0.67, Exp(cIvRoc * ivRoc)))           # range widens when IV is rising, narrows when falling

center   = close * Exp(-skew * vol)                            # price sits high in range when skew > 0
TOP      = center * Exp(kUp   * widthMul * vol)
BOTTOM   = center * Exp(-kDown * widthMul * vol)
```

**Rate of change: tested, shipped off.** The user's view is that Hedgeye's ranges react to how fast price, volume and IV are *changing*. The formula keeps three rate-of-change terms over `rocLen` = 3 days, wired up for later tests:
- **Price change** pulls price toward one edge of the range.
- **Volume change** makes that pull stronger.
- **IV change** widens or narrows the range.

All three default to **0**, because the step 9 test (§3) showed they don't help. The data points the other way: Hedgeye's ranges follow a fast 3-day move **less** than our band does, not more. That slow behavior is already in v3 through `stretch`, which measures distance from a 10-day average. When fitting, also try a slower average (15 or 20 days) for `stretch`.

Inputs and defaults (starting values; final values come from the fit):

| Input | Default | Meaning | Source |
|---|---|---|---|
| side | BOTTOM | which column this copy plots | — |
| rvLen | 20 | days in the smooth realized-vol average | GUESS (common choice) |
| ivSmoothLen | 5 | days to smooth IV | GUESS |
| ivWeight | 0.45 | share of IV in the blend | from the 10/15 refit (wanted ~45%) |
| ivCapRatio | 1.5 | IV may be at most 1.5× realized | GUESS |
| volRef | 0.02 | "normal" daily vol (2% a day, about 32% a year) | GUESS |
| volPower | 0.8 | below 1 = very volatile names get relatively narrower ranges | GUESS |
| kUp | 1.5 | top width, in vol units | GUESS (rough check: SPY/NVDA ranges) |
| kDown | 1.6 | bottom width, in vol units | GUESS |
| cStretch | 0.3 | how much a fast run moves price toward the edge | GUESS |
| cVolume | 0.3 | how much high volume strengthens that | GUESS |
| cTrend | 0.3 | how much the longer trend lifts the range | GUESS |
| rocLen | 3 | days for the rate-of-change terms (also try 2 and 5) | GUESS |
| cPRoc | 0 | pull from a fast 3-day price move (off; step 9) | tested 2026-10-15 |
| cVRoc | 0 | how much rising volume strengthens that pull (off) | tested 2026-10-15 |
| cIvRoc | 0 | width change per unit of IV change (off) | tested 2026-10-15 |
| kManual / useTickerKOverrides | 0 / yes | keep today's test hooks | existing |

ThinkScript notes:
- Every function used (`Log`, `Exp`, `Power`, `Sqr`, `Sqrt`, `ExpAverage`, `Average`, `imp_volatility`, `Min`, `Max`, `IsNaN`, `GetSymbol`) is built in. No lookup tables.
- One script with a `side` input, saved twice as `a_bb_top` and `a_bb_bottom`. That is the same pattern as `BBBottomnew.txt`.
- Remove the VIX link (`close("VIX")`), the vol-level term, the IV/HV width term and the per-ticker k table to start. The audit found they do not hold up out of sample. Add a ticker back only by the rule in §4.

Diagram (one name, one day):
```
 BOTTOM ........ center ........ TOP
   |<-- kDown*vol -->|<-- kUp*vol -->|
                  ^ price sits right of center when it has run up (skew > 0)
```

### 3. How to test it before installing
1. **Pairing (fixed rule):** Hedgeye computes its range dated D between 5 and 8 am on D, using D-1's close. TOSD rows are exported after D-1's close. So pair RR(D) with the TOSD row from the **prior trading day, strictly before D**. This is what `etl/calibrate_tos_rr.py` and `etl/derive_bb_rr_gap.py` already do; keep it. Build the Python model inputs (close, IV, volume) on the same prior-day row.
2. **Inputs:** build the model in Python from `hist_td` close and `imp_volatility` plus `hist_tl` volume. Do not use stored `a_bb_*` values for the new model. Use the same formula as the script, with no extra inputs the script can't see.
3. **Universe:** the 34 stocks and ETFs with TOSD band values. Report stocks and ETFs separately, plus each symbol on its own.
4. **Time split (walk-forward):** train on Mar 10 to Jul 6, pick settings on Jul 7 to Aug 21, test once on Aug 22 to Oct 14. Do not touch the test window until the end.
5. **Fit target:** mean of log(1 + miss% / 0.5). This keeps a few huge misses from steering the fit.
6. **Compare against three things on the same rows:** (a) the current scripts (Family E), (b) `TOS/BridgeBands_Combined_v2_PROPOSED.txt`, (c) the floor, "yesterday's Hedgeye range" (about 0.4%). Score all three with the prior-day pairing in step 1. The v2 proposal's settings were fitted on same-day pairing, so re-score it (and refit it if it's close) under prior-day pairing before comparing.
7. **Measures, per band:** median miss, share within 1% and 2%, 90th-percentile miss, each symbol's median miss, the worst symbol, and how much the band moves day to day compared with Hedgeye's.
8. **Before installing:** put the new script on a TOS chart for 5 symbols (SPY, XLU, NVDA, META, TXG) for 2-3 days. Check that it matches the Python numbers within 0.1%.
9. **Do the rate-of-change terms explain the big misses?** Take every row where the current band misses by more than 3%, plus the 10/14 cases: TXG bottom −7.4% and top −4.8%, NVDA bottom +5.1%, XLK bottom +4.0%, META bottom +3.0%. For each row, show:
   - the 3-day change in price, volume and IV, and the IV level
   - the miss under the current scripts, v3 without the rate-of-change terms, and v3 with them
   - which term moved the band most (price, volume or IV change)

   Then check the share of the big misses that shrink by at least half once the rate-of-change terms are added. **Keep the terms only if** that happens on most big-miss rows (GUESS: ≥ 50%) in **both** the settings and test windows, and the median does not get worse by more than 0.02 points. Also check direction. If NVDA's bottom sat 5% too high after a fast drop on rising IV, the IV term should widen the bottom and the price term should lower it. If the terms push the wrong way on these rows, that is strong evidence against them, whatever the median says.

   **Result (run 2026-10-15, read-only queries, prior-day pairing):**
   - **Data:** 28 stocks/ETFs that have both a Hedgeye range and a stored TOS band, 2,223 rows, Mar 10 to Oct 14. The "current" band is the stored `a_bb_*`. The 10/14 misses match the brief exactly (TXG −4.83 / −7.38, NVDA bottom +5.10, XLK +4.04, META +2.98).
   - **Old dates aren't a fair test.** Misses fell sharply in August (median about 1.3% through July, about 0.7% from August). The stored band before then came from older scripts. So the fair test uses Aug 22 to Oct 14 only, split in two halves: A = Aug 22 to Sep 21, B = Sep 22 to Oct 14.
   - **Test:** add price, volume and IV change on top of the current band. Fit the terms on one half, score them on the other.
     - Fit on A, score on B: the median miss barely moved (top 0.68 → 0.68%, bottom 0.72 → 0.70%), and so did the 90th percentile (bottom 3.33 → 3.24%).
     - Fit on B, score on A: worse (top 0.64 → 0.71%, bottom 0.75 → 0.79%).
     - The IV term changed sign between the two halves. A term that flips sign is noise.
   - **Big misses (over 3%):** **0 of 95** were cut in half by the rate-of-change terms (needed: at least 50%). Most moved by a few tenths of a point.
   - **10/14 cases, current miss → with the terms (fit on A):**

     | Case | Current miss | With terms |
     |---|---|---|
     | TXG top | −4.83% | −4.45% |
     | TXG bottom | −7.38% | −7.01% |
     | NVDA bottom | +5.10% | +5.15% |
     | XLK bottom | +4.04% | +4.09% |
     | META bottom | +2.98% | +2.57% |

   - **Direction check:**
     - **META** rose fast (+1.2 vol units in 3 days), yet Hedgeye's range sat about 2% *below* our band.
     - **TXG** fell (−0.65), yet Hedgeye's range sat about 6% *above* it. Its IV rose 11%, but Hedgeye's range was *narrower*, not wider.
     - **XLK** needed a wider downside while its IV fell.
     - **NVDA** needed a downside 2.7% wider, with almost no change in price, volume or IV.
     - On the recent big misses, the needed shift runs *against* the 3-day price move (correlation −0.33). Hedgeye lags the move; it does not chase it. Volume change shows no link (0.06).
   - **What the big misses really are:**
     - Half are shifts, where both bands are off the same way. That is Hedgeye's range staying put while price moves.
     - The other half are width, mostly a **downside wider than ours** (NVDA, XLK, TSLA, AMZN bottom too high).
     - The repeat offenders are NFLX, TXG, TSLA, NVDA and META.
   - **What it means for v3:** keep the rate-of-change terms at 0. Fix the big misses with a slower center (`stretch`) and a separate, wider `kDown`, then test those in the full fit.
   - **Data note:** 329 Hedgeye rows share a TOSD row with another Hedgeye date (missing TOSD days, e.g. META and NFLX from 9/25 to 9/29). The fit should drop Hedgeye rows whose TOSD row is more than one trading day old.

What counts as better (test window, both bands; all thresholds are GUESS targets):
- Median miss **≤ 0.55%** on stocks + ETFs (today about 0.7-0.9%), and at least 0.05 points better than the v2 proposal.
- **90th-percentile miss at least 20% lower** than the current scripts.
- **No symbol worse by more than 0.3 points** of median miss than it is today.
- **At most 3 symbols** with a median miss above 2%. TXG's median miss **≤ 3%**.
- It wins on **both** the settings window and the test window. A win on only one counts as noise.
- If it misses these targets, keep the current scripts.

### 4. Very volatile names (TXG and similar)
1. **Fix it in the model, not per ticker.** The IV cap (≤ 1.5× realized) handles earnings-driven IV. The vol damping (`volPower` < 1) handles names that are just volatile. Both apply to every symbol.
2. **Per-ticker override only as a last resort.** Add a `GetSymbol()` line only if a per-symbol `kUp`/`kDown` cuts that symbol's median miss by at least 0.5 points on **both** the settings and test windows. Limit: 5 symbols.
3. **Show low trust on screen.** The TrTnBBRskRng tooltip already shows the drift flag. Add one more bullet when the band is shown instead of a real Hedgeye range and the name's IV is above 80% (GUESS), or its 20-day median miss is above 2%:
   - "TOS band is rough for this name (very volatile). Use with care."
   It shows on screen only. No email.
4. **Keep perspective.** TXG has a real Hedgeye range, so the app already uses it. The band matters mainly for names Hedgeye doesn't cover. Don't spend more time tuning TXG than the gain is worth.

### Worth reconsidering
The band matters mainly as a fallback for symbols with **no** Hedgeye range. Fitting it ever more closely on the 34 covered names has a ceiling: yesterday's Hedgeye range alone gets about 0.4%. Run the cheap big-miss test (§3 step 9) and the v3 fit, and stop tuning once v3 clears the targets in §3.

## Rules & numbers
- **Missing IV** (indices, some ETFs): use realized vol only (`ivWeight` treated as 0).
- **Missing volume:** relVol = 1, so volume has no effect.
- **Rate-of-change terms:** if IV is missing, the IV-change term is 0. If volume is missing, the volume-change term is 0. If there are fewer than `rocLen` earlier bars, the price-change term is 0. An earnings gap is a real price change, so don't filter it out; the IV cap and smoothing stop IV from overreacting.
- **Too little history** (fewer than about 26 bars, or no prior close): no value. Leave the column empty rather than guess.
- **Zero or tiny realized vol** (halted or stale symbol): set a floor on `vol` of 0.3% a day (GUESS), so the band never shrinks to the price.
- **IV far above realized** (earnings week): capped at 1.5× realized (GUESS).
- **Skew limit:** ±0.8, so price always stays inside its own band at the moment it's computed.
- **Stale data:** the column runs on TOS's live data. If TOSD is late, the app's existing "data behind market close" warning covers it.
- **Ties / exact edges:** not relevant; the output is a number.
- **Where the numbers come from:** ivWeight 0.45 is from the 10/15 refit. The rest are starting guesses (marked GUESS) for the fit to settle. Pass targets come from today's 0.7-0.9% median, the v2 proposal's test results (stocks 0.74 / 0.55) and the 0.4% floor.
- **Drift monitor thresholds** (`drv_bb_rr_gap`: WARN 1.4/1.7%, ALERT 2.1/2.5%) were set against the old fit. Reset them to about 2× and 3× the new test medians after install.

## Files likely touched
- `TOS/BridgeBands_v3.txt` (new) — the v3 script with a `side` input. Then copy it into the `a_bb_top` / `a_bb_bottom` custom columns. Leave the old files as history.
- `etl/calibrate_tos_rr.py` — add the v3 family, the walk-forward split above, and the per-symbol and 90th-percentile report. Keep the existing prior-day pairing.
- `docs/tos_rr_calibration.md` — new dated section with the v3 results and the final settings.
- `etl/derive_bb_rr_gap.py` — new WARN/ALERT levels only (pairing unchanged).
- `web/actionable.js` — one extra tooltip bullet for "TOS band is rough" (bump the `?v=` in `web/actionable.html`).

## Open questions
- **Rate of change:** tested, and it does not explain the big misses (see §3 step 9 result). v3 ships with those terms off. Do you accept that, or do you want a longer test once more of the current-script history builds up? (Recommended: accept, and re-check in about 3 months.)
- **v2 proposal:** `TOS/BridgeBands_Combined_v2_PROPOSED.txt` was never installed. Test v3 against it as planned (recommended), or install v2 first as a quick step?

## Status
READY_FOR_DEV
