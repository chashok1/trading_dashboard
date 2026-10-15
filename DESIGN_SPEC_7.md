# Design Spec — DESIGN_WORK_7

## Goal
Check the 2026-10-15 analysis of Hedgeye risk ranges vs the TOS bands (`a_bb_top` / `a_bb_bottom`). Then recommend the best band a ThinkScript custom column can run. For the user, who relies on these columns. Hedgeye's range is the target; the TOS band is the stand-in.

## Design

### Bottom line
1. **The analysis paired each Hedgeye range with the wrong TOS day (one day too old).** In the database, `hist_rr.snapshot_date` is already the close date Hedgeye used. Proof: each RR file has a "Prev Close" column (the loader throws it away), and it matches the TOSD close on the **same** `export_date`. Median gap 0.19% on the same day, which is Hedgeye's rounding. On the day before, the gap is 0.94%. Your rule ("RR for morning D uses the D-1 close") is right. In database terms it means `hist_rr.snapshot_date = hist_td.export_date`, not "the trading day before".
2. With the right pairing, most of the conclusions change. **Hedgeye's range is, very closely, a 5-day average of price plus or minus a multiple of short-term volatility.** Two fitted numbers do it. The same settings came out of every training window.
3. **Recommended model ("R7"):** center = 5-day exponential average of the close. Volatility = 75% realized (10-day smooth of daily % moves) + 25% implied. Top = center × e^(1.75 × vol). Bottom = center × e^(−1.95 × vol).
4. **R7 beats the current scripts on every month and both sides.** Jun 1–Oct 14, walk-forward: typical miss top **0.58%** vs 0.71%, bottom **0.65%** vs 0.89%. Worst-10% top **2.49%** vs 3.26%, bottom **2.95%** vs 3.46%.
5. **Nothing else helps once R7 is in place.** I tested volume, rate of change of price, volume and IV, intraday highs/lows, 52-week and 3-month levels, earnings, VIX, PVV, Hedgeye outlook and Call list. Each gains 0.03 points or less. The rest is out of reach for a script. Knowing **yesterday's Hedgeye range** (which a script can't see) gives about 0.47% / 0.57%. R7 gets 0.60% / 0.64% on the same rows.

### Rule check: risk-range columns are never inputs
- **R7 and every test model use only these inputs:** close, open, high, low, volume, `imp_volatility`, historical-vol percentiles, `hist_tw` levels and earnings days, VIX/VVIX/SPX closes, `drv_pvv` signals, and the Hedgeye outlook and Call list. The last two were a ceiling test only.
- **Stored `a_bb_top` / `a_bb_bottom` were read only to score the current scripts.** They stay in separate benchmark columns (`bt`, `bb`, and my port `pt`, `pb`). These are on an explicit banned list in my scripts. `a_bb_streak`, `a_bb_high_low`, `a_bb_high_low_days`, `a_bb_top_slope` and `a_bb_bot_slope` were never loaded.
- **The reused scripts are clean too.** In `feat.py`, `wf.py` and `state.py`, `old_t` / `old_b` sit in the data table, but none of the feature lists (`S[...]`, `ALL`) includes them. They are benchmark-only, as the main session said.

### Claim-by-claim verdict
All numbers are my own (scripts in `...\scratchpad\v7\`). "Correct pairing" means same `export_date`.

| # | Claim | Verdict | My numbers |
|---|---|---|---|
| 1a | 164 TOSD days, Feb 2–Oct 14 | CONFIRMED | 164 days |
| 1b | 1.9% of rows have bad high/low; 561 in October, "getting worse" | Count CONFIRMED (1.86%); "worse" WRONG | 509 of October's 561 are one broken export, **10/07**: 93% of rows have open/high/low/volume = 0, but the closes are real. The other October days are normal. |
| 1c | 6,616 usable RR rows; 78% have an exact prior-day TOSD row | CONFIRMED | 6,616 rows, 49 symbols. 77.9% with prior-day pairing, 78.4% with correct pairing. The misses are January (726) plus `$SSEC` and SPCX (278). |
| 1d | Gap days "3/20–3/27, 4/17–4/24, 9/24–9/29" | Partly WRONG | Days actually missing: 3/23–3/26, 4/20–4/23, 9/25, 9/28, plus 5/01, 6/09, 7/07, 7/24. **Not mentioned:** whole-day **stale copies** on 4/07 (847 symbols = 4/06) and 9/16 (541 symbols = 9/15), and a stale Good Friday export on 4/03. I dropped all three. |
| 1e | Holiday list in `ds.py` | CONFIRMED for Jan–Oct 2026 | Add Nov 26 and Dec 25 before those dates. Hedgeye files carry holiday dates (1/01, 1/19, 2/16, 5/25, 6/19); pair those with the last trading day before. |
| 1f | `vA10` mean −0.69 means TL volume is partial-day | WRONG in general | The 16:30 TL volume is a full day (TL/TW ratio 1.000). The mean is dragged down by 10/07's junk volumes (e.g. LQD = 1 share, giving −17.5) and futures. The median is −0.13, which is normal. Two days really are partial: 5/01 and 6/22, where the last TL row is 11:47 / 10:30. `ds.py` keeps all three bad days. |
| 2 | Loose pairing (last row, however old) inflated misses | CONFIRMED | Aug 22+: stale rows 1.88% / 2.41% vs exact rows 0.76% / 0.80% |
| 3 | Current band: 0.69% / 0.80% typical, 3.54% worst-10% (Aug 22+); 1.31% / 1.19% (Mar–Jul) | Numbers CONFIRMED, but they use the wrong pairing | Correct pairing: Aug 22+ **0.64% / 0.78%**, worst-10% **2.92% / 2.75%**. Mar 10–Aug 21: **1.04% / 1.05%**. |
| 4 | New scripts behave like the old ones (port within ~0.3%) | CONFIRMED, closer than claimed | My port vs stored since Aug 22: median 0.02% / 0.03%. Before August, stored values came from older scripts (0.5–2.6% apart by month). |
| 5 | Even a tree with every input only matches the old script | Numbers CONFIRMED; conclusion WRONG | I rebuilt their 2,707-row set exactly (2,720 after the stale-day fix) and got the same results (ALL 0.84% / 0.78%). With correct pairing, the same tree gets 0.74% / 0.66% vs the current scripts' 0.71% / 0.89%. **Method faults:** (a) inputs one day stale; (b) target measured from today's close, not from a smooth center; (c) target in %, not in volatility units, so the tree must learn scale; (d) rows where the close fell outside Hedgeye's range were dropped (46 rows), a small bias. I found no leakage. |
| 6 | Only price rate of change matters; volume and vol rate of change add nothing | CONFIRMED (re-tested wider) | Also tested: 20/60-day ranks, z-scores, signed price×volume×IV combos, PVV-style buckets, `drv_pvv` signals. Each gains ≤ 0.03 on top of R7. Leftover-miss correlation with every input is ≤ 0.15. **Nuance for your view:** Hedgeye *does* react to change. The center moves about 1/3 of each day's price change (that is what a 5-day average does), and width follows the change in realized vol within ~10 days. It does not react to volume or to IV *change*. |
| 7 | Top depends on a decaying intraday high (TXG stuck near 100) | WRONG as a rule; TXG case CONFIRMED | Once the 5-day center is in, decaying highs add 0.00. After 21 other big down days, Hedgeye's top sat 0.5–1.2% *below* R7, the opposite of TXG. TXG's top stayed at 97.7–101 for 7 sessions while price ran 71–81. That is real, but one case. |
| 8 | Hedgeye's previous range predicts far better (0.58% / 0.57%); its range is a slow state | Partly WRONG | Correct pairing: yesterday's range scores 0.47% / 0.57%; R7 0.60% / 0.64%. Worst-10%: R7 2.48% / 3.01% vs 2.62% / 2.76%. **Update rule found:** the center moves 0.35 × today's price move (R² 0.35). That is an exponential average with weight 1/3 (5 days), not a threshold. "Unchanged" days (19% top, 17% bottom) are mostly Hedgeye's $1 rounding. Extra smoothing of R7 makes it worse (2-day average: 0.66%), and so do ratchets (0.61–0.64%). |
| 9 | Width tracks realized vol (0.80) more than IV (0.39); width change ≈ 0 vs IV change; center follows 0.47 per 1%, less on high-volume days | Mixed | Width vs realized vol: CONFIRMED (0.85, stocks/ETFs without VIX). Width vs IV: WRONG (0.81 on the same rows; 0.55 if VIX is included). Width change vs IV change ≈ 0: CONFIRMED (0.03–0.04). Center follow: WRONG, it is 0.28–0.36 per 1%. Volume effect: WRONG (0.37 on high-volume days, 0.37 on low). |
| 10 | Hurst / rescaled range doesn't beat plain vol | CONFIRMED | Width error 18.8% (Hurst) vs 17.4% (R7). Hurst vs leftover miss: correlation 0.07. |
| 11 | A mixed model isn't justified | CONFIRMED, and moot | R7 wins on every fold, so there is nothing to mix. |

### Other things found
- **Hedgeye rounds its numbers** (to $1 for most stocks, $0.01 for HYG/TXG). That alone costs a median 0.07%, but more for some names: NFLX 0.32%, IGV 0.23%, XLV 0.14%. No model can beat that floor.
- **Wider below than above.** The bottom needs 1.95 vol units and the top 1.75. This held in every window.
- **Per-ticker settings don't pay.** A per-symbol k with shrinkage gives the same typical miss (0.59% / 0.65%). It cuts the bottom's worst-10% from 3.00% to 2.80%, almost all from ORCL. Not worth the `GetSymbol()` table.
- **Earnings are the main leftover.** Within 3 days of earnings the misses are ~2% (n = 33). On the first day after earnings they reach 2–13% (n = 9), with no consistent direction. A script can't fix this.
- **Hedgeye's own trend call** shifts its range by about ±0.15 vol units (up when Bullish, down when Bearish). TOS can't see this. Adding it to a test model gained only 0.03 on the top.
- **Not tested on their own:** `hist_ps`, `hist_etf`, `hist_rta`, `hist_hedgeye_stance`. They are list-membership feeds like Call, which added nothing. They also mostly cover other symbols.

### Recommended ThinkScript (one script, saved twice as `a_bb_top` / `a_bb_bottom`)
```
input side = {default BOTTOM, TOP};
input anchorLen = 5;      # center = 5-day exponential average of close
input rvLen = 10;         # realized-vol smoothing (days)
input ivWeight = 0.25;    # share of implied vol in the blend
input kUp = 1.75;         # top distance, in vol units
input kDown = 1.95;       # bottom distance, in vol units
input minVol = 0.003;     # floor: 0.3% a day

def ret    = if IsNaN(close[1]) or close[1] <= 0 then 0 else Log(close / close[1]);
def rv     = Sqrt(ExpAverage(Sqr(ret), rvLen));
def ivRaw  = imp_volatility();
def ivD    = if IsNaN(ivRaw) or ivRaw <= 0 then Double.NaN else ivRaw / Sqrt(252);
def volRaw = if IsNaN(ivD) then rv else (1 - ivWeight) * rv + ivWeight * ivD;
def vol    = Max(minVol, volRaw);
def center = ExpAverage(close, anchorLen);
plot band  = if side == side.TOP then center * Exp(kUp * vol) else center * Exp(-kDown * vol);
```
- 6 settings, down from about 17. No VIX link, no volume terms, no per-ticker table.
- Every function is built in. The old trick of commenting lines in and out is gone.

### Test numbers (walk-forward)
Settings were fitted only on dates before each test month. 30 stocks, ETFs and indices. Futures, FX and foreign indices are excluded.

| Window | R7 top: typical / worst-10% | R7 bottom | Current scripts top | Current bottom |
|---|---|---|---|---|
| Jun 1–Oct 14 (n 1,458) | **0.58 / 2.49** | **0.65 / 2.95** | 0.71 / 3.26 | 0.89 / 3.46 |
| June | 0.83 / 2.83 | 0.72 / 2.74 | 0.84 / 3.69 | 1.23 / 4.07 |
| July | 0.57 / 2.76 | 0.73 / 3.41 | 0.71 / 3.20 | 0.92 / 3.57 |
| August | 0.57 / 2.29 | 0.63 / 3.53 | 0.68 / 3.03 | 0.84 / 4.02 |
| Sep–Oct 14 | 0.46 / 2.01 | 0.53 / 2.51 | 0.65 / 2.63 | 0.67 / 2.73 |
| Aug 22+ | 0.47 / 2.01 | 0.53 / 2.55 | 0.65 / 2.51 | 0.66 / 2.78 |
| ETFs + indices | 0.33 / 2.03 | 0.33 / 1.90 | 0.41 / 2.42 | 0.42 / 2.57 |
| Single stocks | 0.90 / 2.70 | 1.10 / 3.56 | 1.07 / 3.58 | 1.39 / 4.03 |

- **Share within 1%:** R7 66% / 63%, current 61% / 54%.
- **Share within 2%:** R7 86% / 81%, current 82% / 76%.
- **Settings chosen per window (Jun / Jul / Aug / Sep):** kUp 1.77 / 1.77 / 1.72 / 1.74, kDown 1.98 / 1.99 / 1.99 / 1.97. The center length (5, sometimes 4 for the top), the 10-day vol and the 25% IV weight were picked the same way every time.
- **Current scripts were scored from my port**, which matches the stored values to 0.02% since Aug 22. That lets them be scored on every month. They were calibrated on part of this period, which works in their favour.

**Named symbols, Jun–Oct (typical / worst-10%)**

| Symbol | R7 top | Current top | R7 bottom | Current bottom |
|---|---|---|---|---|
| META | 0.85 / 1.95 | 1.27 / 3.32 | 1.54 / 3.40 | 2.03 / 3.58 |
| NVDA | 0.99 / 2.48 | 1.02 / 2.42 | 0.81 / 2.19 | 1.09 / 2.58 |
| XLK | 0.87 / 1.90 | 0.60 / 1.83 | 0.63 / 2.00 | 1.01 / 2.92 |
| TXG (n 17) | 1.66 / 11.4 | 4.36 / 6.22 | 2.57 / 5.10 | 2.20 / 5.83 |

- **By symbol:** R7 is better by more than 0.3 points on 7 tops and 10 bottoms. It is worse by more than 0.3 on 1 top (XLE, n 8) and 2 bottoms (SNOW, n 8; TXG, n 17).
- **10/14:**
  - TXG top: R7 −13.8% (Hedgeye's top stuck near 98), current −5.8%.
  - TXG bottom: R7 −1.0%, current −9.0%.
  - NVDA bottom: R7 +3.2%, current +2.0%.
  - XLK bottom: +1.7% vs +0.9%.
  - META bottom: −1.1% vs +1.2%.
  - One day is noise; use the tables above.

### Against the Round 6 pass targets
- **Median ≤ 0.55%:** met from Aug 22 (0.47% / 0.53%). Not met over Jun–Oct (0.58% / 0.65%).
- **Worst-10% at least 20% lower:** top met (−24%). Bottom short (−15%).
- **No symbol worse by more than 0.3:** 3 small-sample exceptions (XLE, SNOW, TXG).
- **TXG median ≤ 3%:** met (1.66% / 2.57%).
- **Wins in both halves:** yes, every fold.
- **Verdict:** clearly better than the current scripts and much simpler. The missed targets are close to the ceiling (yesterday's Hedgeye range 0.47% / 0.57%).

### Can it be matched much better?
- **No, not from TOS data alone.** R7's leftover miss is unrelated to any input I could build (|ρ| ≤ 0.15). A tree model given everything on top of R7 gains 0.00 on the top and 0.05 on the bottom.
- **What is left:** Hedgeye's rounding, earnings days, Hedgeye's own trend call, and one-off cases like TXG's sticky top.

### Worth reconsidering
- **Two app parts use the same one-day-off pairing:** `etl/derive_bb_rr_gap.py` (TD `snapshot_date < D`) and `etl/calibrate_tos_rr.py`. Fix those before re-tuning anything else, or the drift monitor will keep reporting inflated gaps.
- **Store Hedgeye's "Prev Close".** The loader drops it for every symbol except UST2Y, and it is the one column that proves the pairing. Keeping it costs one column.

## Rules & numbers
- **Pairing:** a Hedgeye row dated D pairs with the TOSD row whose `export_date` = D. If D is a market holiday, use the last trading day before D. If that TOSD row is missing or stale, skip the row. Never carry an older row forward.
- **Bad data to drop:**
  - whole-day stale exports (more than 100 symbols identical to the day before: 4/07, 9/16, Good Friday 4/03);
  - 10/07 open/high/low/volume (keep the close);
  - TL volume on days whose last row is before 16:00 (5/01, 6/22);
  - high/low ≤ 0, or high below close.
- **Missing IV** (indices, some ETFs): realized vol only.
- **Missing prior close** (first bar): return counts as 0.
- **Vol floor:** 0.3% a day (GUESS) so the band never collapses onto price. Did not bind in the test data.
- **Where the numbers come from:**
  - kUp 1.75 and kDown 1.95: fitted on all data to Oct 14 (walk-forward windows gave 1.72–1.77 and 1.97–1.99).
  - Center length 5, vol length 10, IV weight 0.25: picked the same way in every training window from a grid of 480 options.
  - minVol: GUESS.
- **Fitting method:** volatility-weighted median of (log distance from center ÷ vol). This is the same as a least-absolute-error fit through zero.
- **Re-check after install:** put the script on a chart for SPY, XLU, NVDA, META and TXG for 2–3 days. It should match the Python numbers within 0.1%. Then reset the drift monitor's WARN/ALERT levels to about 2× and 3× the new medians (≈ 1.2% / 1.8%). Do this only after its pairing is fixed.
- **Targets on screen only.** No email.

## Files likely touched
- `TOS/BridgeBands_R7.txt` (new): the script above. Copy it into the `a_bb_top` / `a_bb_bottom` custom columns. Keep the old files as history.
- `etl/derive_bb_rr_gap.py`: pair on the same `export_date` (not `snapshot_date < D`), then new WARN/ALERT levels.
- `etl/calibrate_tos_rr.py`: same pairing fix, plus an R7 family and the walk-forward report.
- `etl/load_raw.py::load_rr` + `db/baseline.sql`: keep the "Prev Close" column for every symbol (e.g. a new `hist_rr.prev_close`). Today `last_price` is filled with `buy_trade` for everything except UST2Y.
- `docs/tos_rr_calibration.md`: new dated section with these results and the pairing correction.

## Open questions
- **Pairing rule wording:** confirm you accept that, in database terms, your rule means `hist_rr.snapshot_date = hist_td.export_date`. The evidence is the "Prev Close" match (0.19% same day vs 0.94% prior day, 374 rows over 12 files). Recommended: accept.
- **Install R7 now, or first fix the drift monitor's pairing and watch both for a week?** Recommended: fix the pairing first (small change), then install R7.
- **Bugs to note (not fixed; design only):**
  - one-day-off pairing in `derive_bb_rr_gap.py` / `calibrate_tos_rr.py`;
  - `hist_rr.last_price` holds `buy_trade`;
  - TOSD export on 10/07 has zero open/high/low/volume;
  - whole-day stale TOSD exports on 4/07 and 9/16;
  - TL end-of-day rows on 5/01 and 6/22 are intraday.

## Status
READY_FOR_DEV
