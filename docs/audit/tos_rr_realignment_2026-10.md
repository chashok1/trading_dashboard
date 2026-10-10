# TOS bands vs RR risk ranges — re-alignment + re-fit (2026-10-09)

Goal: make the TOS `a_bb_bottom` / `a_bb_top` columns match Hedgeye RR LRR / TRR as closely as possible.
Proposed script: `TOS/BridgeBands_Combined_v2_PROPOSED.txt` (NOT deployed). Scratch code was throwaway; the
calibration framework used is `etl/calibrate_tos_rr.py` (features + predict) with the changes below.

## Findings
1. **Day alignment was off by one.** `hist_rr.snapshot_date` S is loaded on S+1 pre-open and describes the close of S.
   It pairs best with the TOS close of S (same `snapshot_date`), not the close before it (what
   `calibrate_tos_rr.anchor_merge(allow_exact_matches=False)` and the `derive.py` BB fallback use).
   Median |error| of the live `a_bb_*` vs RR by lag (TOS days before S): 0 → 0.99/0.95%, 1 → 1.14/1.23%, 2 → 1.45/1.51%.
   (Not changed in code yet.)
2. **Fit variable ≠ script variable.** The calibration's IV/HV ratio used TOS's `historical_vol` column; the
   ThinkScript uses `hvAnn = StDev/close*Sqrt(252)`. Using the script's proxy shrinks the gap between the Python
   replica and the live export from 0.31/0.22% to 0.06/0.11% (median), and the fitted IV/HV coefficient changes
   sign (old −0.5/−0.25, new +0.51/+0.58 — sensible: wider when IV is high vs realized).
3. **VIX coupling and per-ticker k overrides do not generalize.** Dropping them costs nothing out-of-sample.
4. **No help from:** price ROC midpoint term, volume ROC, IV ROC, vol-of-vol, Parkinson range sigma, mean reversion,
   EMA smoothing of the bands, per-class / per-symbol k (valid-gated). Volume and volatility *rates of change* have
   ~0 correlation with the band-vs-RR error (|ρ| ≤ 0.07); 5-day price change has a weak link (ρ≈−0.27 on TRR error).
5. **Floor:** yesterday's RR as the forecast of today's RR has median APE 0.41% (LRR) / 0.38% (TRR), 73–75% within 1%.

## Method
RR (`hist_rr`, reverse symbols scaled, rows with 0/NULL ranges dropped) paired with TOS `hist_td` close + `hist_tl`
volume of the same snapshot_date. 47 symbols (13 stocks, 6 ETFs, 6 indices/FX, 10 futures, VIX, 2 yields), 4,714 rows,
2026-03-10 → 2026-10-08. Walk-forward split: train → 07-06 (2,642), valid → 08-21 (1,098), test → 10-08 (974).
Parameters fit by Powell on mean log1p(APE/0.5); structure chosen on **valid**; **test** untouched until reporting.
Metric: APE = |model − RR| / RR.

## Result (test window, new = train-only fit)
| class | LRR old → new (median %, ≤1%) | TRR old → new |
|---|---|---|
| ALL (974) | 0.66→0.53, 63→69% | 0.61→0.47, 66→74% |
| stocks | 0.99→0.74, 50→63% | 0.82→0.55, 59→74% |
| ETFs | 0.28→0.21, 96→92% | 0.33→0.25, 92→88% |
| indices/FX | 0.28→0.33, 88→94% | 0.26→0.21, 94→97% |
| yields | 0.69→0.57, 69→88% | 0.41→0.55, 81→89% |
| futures | 0.93→0.94, 52→53% | 0.96→0.77, 51→58% |
| VIX (1 symbol) | 2.79→2.20, 12→25% | 3.48→3.06, 3→9% |
"old" = currently deployed parameters evaluated with the script-consistent HV proxy, without the VIX/ORCL/NFLX k overrides.

## Final parameters (fit on all data, rounded; in the proposed script)
TOP: tilt .31, mom .24, volW −.16, ivhvW +.51, levelW −.27, k 1.48. BOTTOM: tilt .28, mom .27, volW +.09, ivhvW +.58,
levelW −.39, k 1.69. Both: n=10, RelVol 3/15, momentum EMA 8/26, vol-level window 20, sigma = realized StDev (w=1).
Rounding changes nothing (all-data median 0.533/0.630 vs 0.532/0.632 unrounded).

## Caveats
- Volume in the fit is the last `hist_tl` snapshot of the day (may not be the final volume); live TOS uses true volume.
- RR universe is ~49 comparable symbols; VIX and futures stay weak (VIX needs its own treatment; futures rolls differ).
- Single-day check (2026-10-08, 20 symbols): new LRR error 0.31% vs live 0.48%, but new TRR 0.47% vs live 0.27% — one day is noise;
  the 974-row test window is the evidence.
- Not yet run in live TOS. Recommended: dual-run as extra custom columns for 1–2 weeks before replacing a_bb_*.

## Addendum — systematic rate-of-change test (2026-10-09)
Tested 84 price / volume / volatility rate-of-change features on top of the proposed model, each as a midpoint tilt and
as a width multiplier, per band:
- price: 1/2/3/5/10/20-day change (raw and vol-scaled), EMA slope, abs-move-vs-normal; RSI level and change.
- volume: 1/2/3/5/10-day change, today and 3-day avg vs 5/10/20/30/60-day avg, directional (sign of price move),
  TOS 10-day vs 3-month averages and their change, TOS volume_rate_change.
- volatility: IV, IV/HV, realized-vol and TOS HV 1/3/5/10-day change, IV and HV percentile level/change, VIX change.
Screening: coefficient fit on earlier data, scored on the next unseen fold (two folds). Result: gains <= 0.007 in
loss (~1%), unstable in sign across folds for almost all. Two-lever combos refit jointly and scored on the untouched test
window did not help (TOP median APE 0.474 -> 0.489; BOTTOM 0.524 -> 0.528). A ridge model and boosted trees given ALL
features moved test median APE by only -0.02..+0.02 with mixed sign. Conclusion: no rate-of-change input
available in the data adds usable information beyond the proposed script; the remaining error is RR-side behaviour.
