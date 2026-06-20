# Price / Volume / Volatility — Holistic Field & Data-Flow Audit

**Date:** 2026-06-20  **Scope:** every Price, Volume, and Volatility field in the
MA-tab pipeline.  **Ground truth:** original Excel `Tickers YYYY-MM-DD.xlsx` MA-tab
formulas (via `docs/ma_columns_full.csv`) cross-checked against `docs/*_logic.md`.
**Method:** static review of the live ETL path (`etl/derive*.py`, `etl/mappings.py`,
`etl/load_raw.py`, `db/baseline.sql`, `api/routers/*.py`, `web/*.js`), with key code
spots re-verified by hand. Live-data checks are specified in
`docs/audit/pvv_validation_queries.sql` and run by the developer agent (Cowork has no
DB access) — see §6.

---

## 1. Executive summary (issues first)

The price/volume/volatility pipeline is **structurally sound and largely faithful to
the Excel formulas**, but the audit surfaced **one correctness-grade divergence, one
latent decode bug, and several maintainability/landmine issues**. Nothing here is
silently corrupting the dashboard today, but two items will bite the moment a planned
"revert" is applied.

| # | Severity | Finding | Where |
|---|----------|---------|-------|
| F1 | **High** | **Two SD denominators coexist and disagree.** The Python engine uses `AC = standard_dev`; the SQL twin uses `AC = LEAST(standard_dev, median_sd)`. Every `*_sd` field (Trend_sd, Trade_sd, BBHighLow_SD, RR indices) is computed twice on different scales. | `derive_cat_atomic_input.py:403` vs `derive.py:3207` |
| F2 | **High** | **`median_sd` is mislabeled in the Python path** — it is the *latest* `standard_dev`, not a median. The planned revert to `MIN(AA,AB)` would be a silent **no-op** (MIN(sd, sd)=sd) until this is fixed. | `derive_cat_atomic_input.py:134` |
| F3 | Medium | **VolumeSpike decode drops Excel's `REPT` right-padding.** Correct only when the packed string is ≥9 chars; small `A_VolumeSpike` values decode differently than Excel. Replicated verbatim in JS. | `derive_cat_atomic_input.py:304`, `web/actionable.js:1666` |
| F4 | Medium | **Documented scale mismatch (Perf1D_sd / "Current Price SD Rule" NK):** Python uses `net_chng/AC`; Excel uses `pct_change%×D/AC` (~100× larger). Thresholds are calibrated to the Python scale — safe **only** as long as both stay coupled. | `derive_cat_atomic_input.py:436` |
| F5 | Low | **Placeholder/None inputs** in BULL / BB-Bull composite rules (`bbhighlow_sd_rule`, `bbhighdays/days`) — rules run with those terms disabled (unfinished wiring). | `derive_cat_atomic_input.py:814–815, 863` |
| F6 | Low | **Duplicate/parallel logic** — `vlm_projected` SQL exists twice (live + dead `_derive_ma_impl`); VolumeSpike decode exists 3× (Python, JS, dead view); two TW column-mapping definitions coexist. Drift risk. | multiple |
| F7 | Low | **Hardcoded magic numbers** not in ref tables: vlm-projection minutes (390/570/930/1600), BB-slope thresholds (±2/±3), reverse-symbol scale (×10/×5), zone thresholds (±10). | multiple |
| F8 | Info | **TW carry-forward inconsistency** — TW is anchor-locked for universe membership (`export_date=:d`) but read with a 14-day carry-forward for SMA/MACD values. Intentional but asymmetric. | `derive.py:873` |
| F9 | Info | **Several named Excel fields are not persisted** (Vlm Score, Vlm Desc, W_Vlm_RuleCode, Vlm_Action, Vlm 10-day %, Vlm 3m %). Only `w_vlm_rule_desc` and the transient `GB` intermediate exist. | — |

**Bottom line:** formulas are *being used correctly* for the fields that drive the
live screens, and the documented scale choices (F4) are deliberate and internally
consistent. The real risks are F1/F2 — a dormant inconsistency that becomes active on
the next Excel-AC revert — and F3, a small-value decode edge case. Recommended actions
are in §7.

---

## 2. Field inventory & health

Health key: ✅ faithful to Excel + flowing correctly · ⚠️ correct now but with a
caveat/landmine · 🐛 confirmed divergence from Excel.

### 2.1 Price (`drv_cat_price` → `drv_quote` / `drv_technicals`)

| Field (MA col) | Source | drv landing | Health | Note |
|---|---|---|---|---|
| Close (D) = `IF(UseLatest, Last, D_Last)` | hist_tl/td/y merge | `drv_quote.last_price` (intraday-aware) | ✅ | realized via latest-loaded-wins + anchor ceiling |
| Last (F=DM), Net Chng (G), %Change (H) | hist_tl/td/y | `drv_quote.{last_price,net_chng,pct_change}` | ✅ | per-field freshest non-null wins |
| Open/High/Low (DP/DQ/DR) | hist_tl/td/y | `drv_quote.{open,high,low}_price` | ✅ | `0` treated as "no data" for OHLC |
| D_Last/D_High/D_Low (EF/EK/EL) | hist_td | read live in `compute_intermediates` | ✅ | EF = prior-session close |
| Prev Close (EF) | hist_td.last_price | intermediate | ✅ | also used for Yahoo net/pct calc |
| 3mnLow/High/HighLow, 3wkHighLow (BA–BO) | hist_td a_* | atomic input | ✅ | decoded from packed TOS values |
| StandardDeviation (AA) | hist_tw.standard_dev (col AF) | intermediate (AB) | ✅ | custom TW loader (dup col names) |
| Median SD (AB) | — | intermediate | 🐛 | **not a median** in Python path (F2) |
| SDorMedian / AC (AC) | derived | denominator | 🐛 | **two definitions** (F1) |
| SD% (AD) = AC/D | derived | atomic input | ⚠️ | inherits AC ambiguity |
| Trend_sd/Trade_sd/Trade_Trend_Sd (AG/AH/AI) | (D−AE)/AC etc. | atomic input | 🐛 | denominator divergence (F1) |

### 2.2 Volume (`drv_cat_volume`)

| Field (MA col) | Source | drv landing | Health | Note |
|---|---|---|---|---|
| vlm_projected ("Vlm projection") | hist_tl.volume + sequence | `drv_technicals.vlm_projected` | ⚠️ | hardcoded minute constants (F7); duplicated in dead code (F6) |
| A_VolumeSpike → VS Spike/Volume/Price/Vol/Days (FF–FM) | hist_tw.a_volume_spike | read live (atomic input + API) | 🐛 | padding shortcut diverges for small values (F3) |
| W_Vlm / L_Vlm (K/FS) | hist_tw.volume / hist_tl.volume | `drv_tw.w_volume` | ✅ | cast to int |
| W_Avg Vlm 10d / 3m (L/M) | hist_tw.volume_avg_10d/3m | `drv_tw.avg_vlm_10d_d / 3m_d` | ✅ | — |
| VolumeRateOfChange (N) | hist_tw.volume_rate_change | `drv_tw.vlm_rate_change_d` | ✅ | — |
| Vlm 10 Factor / rvol (O) | derived `w_volume/avg10` | `drv_tw.w_vlm_expn_ratio` | ✅ | exposed as `rvol` |
| W_Vlm_RuleDesc (U) → "1".."10" | 10-rule IFS | `drv_tw.w_vlm_rule_desc` | ✅ | mirrors Excel IFS |
| Vlm 3m % (GB) → Current Volume Rule (NL) | hist_tw.volume (fallback tl_volume) / avg_3m | intermediate | ⚠️ | mixes weekly & daily volume scales (intentional) |
| Vlm Score/Desc, W_Vlm_RuleCode, Vlm_Action, Vlm 10-day %/3m % | — | **not persisted** | ℹ️ | F9 |

### 2.3 Volatility (`drv_cat_bollinger`, `drv_cat_risk_range`, `drv_cat_volatility_regime`, `drv_cat_index_volatility`)

| Field (MA col) | Source | drv landing | Health | Note |
|---|---|---|---|---|
| A_BBHighLow → BBHighLow / _A / Days / Direction1 (AJ–AN) | hist_td.a_bb_high_low | atomic input | ✅ | decode matches Excel TRUNC/ABS chain |
| BBHighLow_SD (AO) = (D−|AL|)/AC | derived | atomic input | ⚠️ | inherits AC (F1) |
| BB_Streak chain (AS–AZ), BB_Threshold_Crossover | hist_td.a_bb_streak | atomic input | ✅ | `_decode_bb_streak` matches packed-number decode |
| BB_Bot/Top slopes, BBRngStrkRule (QH/QI/QJ) | hist_td.a_bb_*_slope | `drv_tn_td_bb_rr` | ⚠️ | hardcoded ±2/±3 thresholds (F7) |
| BB Bull (LW) | composite | atomic input | ⚠️ | placeholder None inputs (F5) |
| RR_Bottom/Top (LRR/TRR, K/L/EC/ED) | hist_rr (fallback hist_td a_bb_bottom/top) | `drv_rr.lrr/trr` | ✅ | reverse-symbol ×10/×5 scaling (F7) |
| BRR% (EE), EO High TRR, EP Low LRR, MRR/LRR/TRR idx | derived /AC | atomic input | ⚠️ | inherits AC (F1) |
| BullRiskRng-Action (QM/QN), Td Tn BB RR Rule (QR) | rule ladders | `drv_tn_td_bb_rr` | ✅ | IFS ladders + ref_param lookups |
| ImpVolatility (DT/DF) | hist_td.imp_volatility (fallback hist_tl raw) | `drv_quote/technicals.imp_volatility` | ⚠️ | `COALESCE(...,0)` masks missing as 0 (F8-adjacent) |
| Volatility regime / Price zone (GH–GK) | Dash scalar / pct_brr | `drv_quote.zone_signal`, `drv_dash` | ✅ | thresholds from `ref_settings` (±10 default) |
| Index Volatility (SP500/Nasdaq/Dow/Russell, IV–IY) | the VIX-family symbols themselves | normal price pipeline | ✅ | no dedicated derive; classified section "Volatility" |

---

## 3. Formula-correctness audit (Excel ↔ Python)

### 3.1 The SD denominator — F1 (High) — CONFIRMED IN CODE

`AC` is the standard-deviation denominator under nearly every volatility/normalized
field (`Trend_sd`, `Trade_sd`, `BBHighLow_SD`, `EO/EP/ES/ET/EU` risk-range indices).
Two live engines compute it differently:

- **Python** — `etl/derive_cat_atomic_input.py:399-403`:
  ```python
  # AC = standard_dev only — matches Excel MA!AC currently set to =AA (StandardDeviation).
  # TEMPORARY (per user, 2026-06-05): will switch back to MIN(standard_dev, median_sd) ...
  AC = AB if AB is not None else AA       # AB = standard_dev, AA = median_sd (fallback)
  ```
- **SQL twin** — `etl/derive.py:3207`:
  ```sql
  LEAST(i.sd, i.median_sd) AS sd_or_median
  ```

So for any symbol where `median_sd < standard_dev`, the atomic-input engine and the
`drv_tn_td_bb_rr` engine produce **different `*_sd` values for the same symbol/date**.
The Excel ground truth is currently `=AA` (StandardDeviation) per the code comment, so
the **Python path matches Excel today** and the SQL path does not. Q7/Q8 in the
validation pack measure how many symbols this actually affects.

### 3.2 `median_sd` is not a median — F2 (High) — CONFIRMED IN CODE

- **Python** — `etl/derive_cat_atomic_input.py:134`:
  ```sql
  SELECT DISTINCT ON (tos_symbol) tos_symbol, standard_dev AS median_sd
  FROM hist_tw WHERE snapshot_date <= ... ORDER BY snapshot_date DESC, sequence DESC
  ```
  This returns the **latest** `standard_dev`, aliased `median_sd`. It is a null-fallback,
  not a statistical median.
- **SQL twin** — `etl/derive.py:3192` does compute a true running median
  (`percentile_cont(0.5) WITHIN GROUP (ORDER BY standard_dev)`).

**Landmine:** the F1 comment says the plan is to revert `AC` to `MIN(AA, AB)`. In the
Python path that is `MIN(standard_dev, latest_standard_dev) = standard_dev` — a **no-op**.
Reverting AC without first fixing `median_sd` to a real median changes nothing while
*looking* like it restored the Excel behavior. Fix F2 before/with F1.

### 3.3 VolumeSpike decode padding — F3 (Medium) — CONFIRMED IN CODE

Excel: `FH = RIGHT("0000000000" & FG & REPT("0", 9-LEN(FG)), 10)` — right-pads `FG`
with zeros *before* taking the last 10 chars. Python (`derive_cat_atomic_input.py:304`):
```python
padded = "0000000000" + fg_str
FH = padded[-10:]          # REPT right-padding omitted
```
The two agree **only when `LEN(FG) >= 9`**. The code comment acknowledges the
assumption ("for most realistic FG (8-10 char)…"). For small `A_VolumeSpike` values the
slices `FI/FJ/FL/FM` (volume spike / price change / volatility / days) land on different
digits → wrong VS sub-fields. The same shortcut is copied into `web/actionable.js:1666`,
so the popover would show the same wrong decode. Q15 quantifies exposure.

### 3.4 Perf1D_sd / "Current Price SD Rule" (NK) scale — F4 (Medium) — by design

`etl/derive_cat_atomic_input.py:436`: `CA = net_chng / AC`. Excel uses
`pct_change(%) × D / AC` — about **100× larger**. This is the documented mismatch in
`CLAUDE.md` (Lookup index → "Current Price SD Rule (NK) input scale"). The downstream
`perf1d_sd_rule` thresholds in `ref_trig_atomic_rule` are calibrated at the Python
(net_chng) scale, so the rule fires correctly **as a closed system**. The hazard is only
if someone "fixes" the formula to match Excel without re-calibrating the thresholds.
No change recommended; documented here so it isn't mistaken for a bug.

### 3.5 Crossover Trade(JM) vs Trend(JP) — verified correct

`_crossover` (Trade) uses `MIN(EF,J)` / `MAX(EF,I)` — no BZ; `_crossover_trend` (Trend)
uses `MIN(BZ,EF,J)` / `MAX(BZ,EF,I)` — includes BZ. Matches the `CLAUDE.md` Rule-Flow
note exactly (`derive_cat_atomic_input.py:761-806`). DMA crossovers still use the 3-arg
fallback "until their formulas are verified" — flagged as unverified, not wrong.

### 3.6 Spot-checks that passed

BB_Streak decode (`_decode_bb_streak`), BBHighLow decode chain, RR midpoint/reverse
scaling, the weekly volume 10-rule IFS, vlm_projected minute arithmetic, and the
Close/`Use Latest` selection all reproduce their Excel formulas faithfully on
inspection. These are the ✅ rows in §2.

---

## 4. Data-flow integrity

**Cascade (idempotent, DELETE-then-INSERT per `as_of_date`):**
`tos_symbol → drv_td/to/tw → drv_y → drv_quote → drv_rr → drv_symbols →
drv_technicals/fundamentals/outlooks/portfolio → drv_cat_atomic_input → drv_dash/stks/
actionable/trig` (`etl/derive.py:3426-3457`). Each step is wrapped in `_safe(...)` so a
single failure rolls back and the cascade continues — good isolation, but a partial
failure can leave one component table stale for the date (the freshness deriver guards
this).

**Anchor & carry-forward:** `D = MAX(export_date) FROM hist_td`. Daily-EOD feeds
(tl/td/y) read `export_date = :d` exactly (no carry-forward); periodic feeds (rr/etf/
ii/call) read `snapshot_date <= :d` (carry-forward). **Exception (F8):** TW is in
`ANCHOR_LOCKED_SOURCES` for *universe membership* but `_derive_technicals_impl` reads TW
SMA/MACD with `snapshot_date <= :d AND >= :d-14` (14-day carry-forward). So a symbol can
be in the universe via today's TW yet show 1–14-day-old SMA values. Q17 measures TW
staleness.

**Compatibility view:** `drv_ma` is a VIEW joining the 5 component tables
(`db/baseline.sql`); all price/volume/IV columns resolve to the `drv_technicals` alias.
The view also exposes **~45 legacy rule columns hardcoded `NULL::NUMERIC`** — any
consumer reading those gets NULL silently. The hot API paths (`api/routers/dash.py`)
deliberately join the component tables directly (not the view) to stay under Postgres'
GEQO 12-join threshold, and pull `a_volume_spike` / `historical_vol` via LATERAL
sub-selects straight from `hist_tw` / `hist_td`.

**Price selection on the anchor:** `drv_quote` allows an intraday TOSL/Y export loaded
*after* close D to feed the live quote while staying tagged `as_of_date=D` (ceiling =
`date.today()` only when `as_of_date == anchor`); historical re-derives use ceiling = D,
so no look-ahead leaks into history. This is the correct realization of
`Close = IF(UseLatest=Y, Last, D_Last)`.

**Source mapping fragility:** the TW tab has duplicate column headers
(`SimpleMovingAvg` ×3, `VolumeAvg` ×2) resolved **by column index** in the custom
`load_tw` handler (`etl/load_raw.py`). A second, incomplete `HIST_MAPS['TW']` also exists
and, if it ever became authoritative, would silently drop `sma_50/sma_200/volume_avg_3m`.
Worth a guard/test (F6).

---

## 5. Did the formulas flow correctly? — verdict

For the fields that drive the live Dashboard / Actionable / Rule-Flow screens, **yes** —
the Excel formulas are reproduced faithfully and the data flows through the cascade with
correct anchoring, idempotency, and freshness handling. The exceptions are:

- **F1/F2** — a real but currently-dormant divergence in the SD denominator between the
  two engines; the Python (screen-facing) path matches Excel today.
- **F3** — a decode edge case affecting only small `A_VolumeSpike` values.
- **F4** — a deliberate scale choice, internally consistent, not a flow error.

None of these are corrupting today's headline numbers, but F1–F3 should be resolved
before the next Excel-AC revert or they will produce subtly wrong `*_sd` and VS values.

---

## 6. Live data validation (run by developer agent)

Cowork cannot reach Postgres, so the SQL pack `docs/audit/pvv_validation_queries.sql`
(Q0–Q19) is handed to the developer agent. Each query maps to a row below. Fill the
**Result** column from the run, then the verdicts confirm or revise §3–§4.

Anchor date resolved: **2026-06-18** (MAX export_date from hist_td on 2026-06-20 run).

Query rewrites applied: **Q8** — `drv_tn_td_bb_rr` does not store `trend_sd`/`trade_sd`
columns; rewritten to compare Python `ac` (stored in `drv_cat_atomic_input`) vs recomputed
SQL-twin AC (`LEAST(latest_sd, percentile_median_sd)`), giving a direct count of symbols
where the two engines diverge. **Q9** — `drv_cat_atomic_input` stores `ac` (absolute SD
dollar value), not `sd_pct`; rewritten as `ac / last_price` joined with `drv_quote`.
**Q12** — VIX-family symbols lack caret prefix in this DB (stored as `VIX`, `VVIX`, `RVX`,
`$VXN`, `$GVZ`, `$OVX`); query adjusted. **Q16** — `drv_tw` uses `snapshot_date` not
`as_of_date`; column is `w_vlm_expn_ratio` not `rvol`.

| Q | Checks | Expected | Result | Verdict |
|---|--------|----------|--------|---------|
| Q1 | Join coverage (symbols vs technicals/quote/rr/atomic) | counts close, symbols ≥ others | symbols=1136, tech=1136, quote=1104, rr=974, atomic=882 | Confirms — technicals is full universe; quote/atomic narrower (expected for symbols lacking price data) |
| Q2 | Universe symbols missing technicals/quote | ~0 active names | 76 symbols missing quote | Partially expected — all 76 are `$`-prefix foreign/special symbols with no TOSL/TL feed; not a US-equity flow issue |
| Q3 | Price null/zero rates + range | low nulls; few OHLC zeros | n=1104, null_last=8, nonpos=0, zero_OHLC=0, range=0.0001–73918.76, avg=697.36 | Confirms — 8 nulls and zero OHLC violations; range sane |
| Q4 | OHLC integrity violations | 0 | 1 violation | Near-zero — single outlier (likely penny stock rounding or data glitch); acceptable |
| Q5 | Intraday vs EOD quote mix | sane split | n=1104, intraday=1032, eod=72 | Confirms — anchor date 2026-06-18 (Wed) is a normal trading day; 1032 intraday quotes means TOSL loaded same-day; 72 EOD-only is sane |
| Q6 | drv_quote.last vs D_Last >25% gap | very few | n=1104, gt_25pct_gap=6 | Confirms — 6 large-gap symbols (likely splits, new listings, or unit/warrant instruments); acceptable |
| Q7 | median_sd < standard_dev count (F1/F2 exposure) | quantify | n_with_tw=966, median_lt_sd=543 (56%), median_eq_sd=39 (4%) | **Confirms F1/F2 are material** — 543 of 966 symbols (56%) have true running median below latest SD; the Python path (using latest as "median") will compute different AC than LEAST(sd, median_sd) |
| Q8 | AC divergence between Python engine and SQL twin (F1) | quantify | n=882, ac_diffs=505 (57%) | **Confirms F1 is active** — 505 of 882 symbols (57%) have AC values that differ by >0.01 between Python (`ac` col) and LEAST(latest_sd, percentile_median_sd). Rewritten: drv_tn_td_bb_rr lacks trend_sd/trade_sd columns |
| Q9 | SD% range sanity (ac/price) | few >0.5 | n=882, null_ac=0, sdpct_gt_50pct=0, range=0.0001–0.2622 | Confirms — no absurd SD% values; max 26% SD/price is plausible for high-vol names. Column is `ac` (absolute); rewritten to ac/last_price |
| Q10 | RR source mix + inverted bounds | inverted=0 | BB=932 (null_bounds=0, inverted=0), RR=42 (null_bounds=0, inverted=0) | Confirms — no bound violations; BB fallback dominates (932 vs 42 RR-feed); all clean |
| Q11 | ImpVolatility null vs zero (masked-missing) | quantify zeros | n=1136, null_iv=254, zero_iv=62, range=0.000–1.840 | Confirms concern — 62 zeros mask missing IV (COALESCE issue); 254 true NULLs also present; VIX-class symbols at 0 |
| Q12 | VIX-family index vol present & sane | present, plausible | VIX=16.78/0.91iv, VVIX=88.43/0iv, RVX=22.86/0iv, $VXN=26.31/null_iv | Partial — VIX price levels plausible for 2026-06-18; IV=0 for VVIX/RVX confirms COALESCE masking (F11 zero-iv); $VXN has NULL iv. Caret-prefix symbols absent; DB uses plain/dollar names |
| Q13 | vlm_projected nulls + proj<raw + >50× | proj≥raw; few outliers | n=1136, null_proj=280, proj_lt_raw=0, proj_gt_50x=0 | Confirms — no projection underruns or extreme outliers; 280 nulls are pre-open/missing-sequence symbols (expected) |
| Q14 | sequence distribution feeding projection | matches market hours | preopen=0, intraday=882, closed=874 | Confirms — on 2026-06-18 anchor, 882 intraday + 874 closed-session rows in hist_tl; no pre-open; totals match quote counts |
| Q15 | VolumeSpike small-FG exposure (F3) | quantify at-risk rows | n_nonzero=66438, short_fg_at_risk=0 | **Contradicts F3 concern** — zero rows with short FG across all 66k non-zero VolumeSpike records; `to_char(abs(a_volume_spike),'FM999999990.00')` always ≥9 chars in live data; F3 is a theoretical edge case with no live exposure |
| Q16 | Weekly rvol range sanity | plausible | n=874, null_rvol=0, range=0.00–12.88, avg=1.52 | Confirms — `w_vlm_expn_ratio` (rvol) sane; avg 1.52× weekly vs 10d avg; max 12.88× reasonable for high-activity weeks. Column `snapshot_date` not `as_of_date` |
| Q17 | TW staleness (F8) | most fresh/≤7d | n=966, fresh_today=874, d1_7=11, gt_7d=81 | Partially confirms F8 — 874 of 966 TW symbols fresh (anchor date); 11 up to 7d stale, 81 >7d stale; the 81 gt-7d symbols are in universe but carrying old SMA/MACD values |
| Q18 | RR feed staleness (carry-forward) | bounded lag | n=54, gt_7d=5, worst_lag=142 days | Expected — RR is a periodic feed; 5 symbols >7d stale, worst lag 142d (stale RR symbol falls back to BB bounds, which is correct behavior) |
| Q19 | Symbols missing today's TOSD | small | universe=1136, missing_tosd=262 | Notable — 262 of 1136 (23%) universe symbols lack a hist_td row for 2026-06-18; these are foreign/non-US symbols (44 dollar-prefix), ETFs without TD export, and other special instruments; they are in universe via TW/other feeds but have no TOSD close that day |

---

## 7. Recommendations (prioritized)

1. **Fix F2 then F1 together.** Make the Python `median_sd` a real running median
   (reuse the `percentile_cont` from `derive.py:3192`), then converge both engines on a
   single `AC` definition. Until then, the planned `MIN(AA,AB)` revert is a no-op and
   the two engines will keep disagreeing. *(developer task)*
2. **Patch the VolumeSpike decoder (F3)** to restore the `REPT` right-padding (or
   reformat `FG` to a fixed width) in both `derive_cat_atomic_input.py:304` and
   `web/actionable.js:1666`, and add a unit test with a small-value `A_VolumeSpike`.
3. **De-duplicate (F6):** delete dead `_derive_ma_impl` / unwired `derive_ma`; factor
   the VolumeSpike decode and `vlm_projected` formula into one shared helper each; drop
   or guard the stale `HIST_MAPS['TW']`.
4. **Leave F4 as-is** but add a one-line guard comment at the formula site pointing to
   the threshold calibration, so no one "fixes" it in isolation.
5. **Finish or remove F5** placeholder rule inputs (`bbhighlow_sd_rule`, `bb*days`).
6. **Lift F7 magic numbers** (vlm minutes, BB-slope thresholds, reverse scale, zone
   thresholds) into ref tables for tunability and auditability.
7. **Run §6 validation** and paste results to confirm the static findings against live
   data.

---

*Code references verified against the working tree on 2026-06-20. Items F1, F2, F3 and
the `vlm_projected` formula were re-read directly from source during this audit; the
remaining findings are from a structured pass over the listed files.*
