# AGENT_RESULT_09 — PRMB: do Excel-fired and DB-fired match?
Date run: 2026-06-06

---

## Step 1 — per-composite fired comparison for PRMB

```
composite_rule_code          | excel_deficit | excel_fired | db_triggered | db_score | match?
-----------------------------|---------------|-------------|--------------|----------|--------
186-BR-Trend-CO              | 41            | False       | False        | 51       | ✓
187-BR-NoTN-NoTD-UP-MACD-DAY | 61            | False       | False        | 33       | ✓
188-BR-TNabvTD-UP-MACD-DAY   | 32            | False       | False        | 61       | ✓
189-BR-BB-LoHi               | 51            | False       | False        | 53       | ✓
196-BS-TN-LRR                | 11            | False       | False        | 43       | ✓
197-BS-TN-LRR-UP-DAY         | 41            | False       | False        | 53       | ✓
198-BS-TN-LRR-UP-MACD        | 31            | False       | False        | 43       | ✓
199-BS-TN-LRR-MACD-UP-DAY    | 41            | False       | False        | 43       | ✓
267-BS-Trade-CO              | 31            | False       | False        | 51       | ✓
268-BS-3M-HiHi               | 41            | False       | False        | 82       | ✓
269-BS-Bull                  | 61            | False       | False        | 90       | ✓
277-BS-VS-LT                 | 21            | False       | False        | 30       | ✓
278-BS-BB-HL-HiHi            | 41            | False       | False        | 52       | ✓
279-BS-BB-Streak-HiHi        | 21            | False       | False        | 44       | ✓
298-BS-BB-HL-HiHi-TN-TD      | 51            | False       | False        | 62       | ✓
299-BS-BB-Streak-HiHi-TN-TD  | 31            | False       | False        | 54       | ✓
394-BS-TN-LRR                | 10            | False       | False        | 60       | ✓
395-BS-TN-TD-LRR             | 0             | True        | True         | 60       | ✓
396-BS-LRR-CloseToTrade      | 0             | True        | True         | 50       | ✓
397-B-TN-TD-LRR              | 1             | True        | True         | 90       | ✓
398-B-TN-TD-LRR-UP-DAY       | 21            | False       | False        | 53       | ✓
399-B-TN-TD-LRR-UP-MACD      | 21            | False       | False        | 53       | ✓
448-BS-TN-TD-LRR             | 0             | True        | True         | 70       | ✓
449-B-TN-TD-LRR-UP-MACD      | 11            | False       | False        | 62       | ✓
697-STM-Earnings-Date        | 10            | False       | False        | 0        | ✓
698-SS-Bull-HighAbvTRR       | 20            | False       | False        | 0        | ✓
699-SW-Resistance            | 10            | False       | False        | 0        | ✓
781-SS-TRR-CloseToTrade      | 20            | False       | False        | 0        | ✓
782-SS-3mnHigh               | 40            | False       | False        | 0        | ✓
783-SW-Vol-Spke-Price-Dn-Past | 10           | False       | False        | 0        | ✓
784-SS-Streak-GoingBad       | 20            | False       | False        | 40       | ✓
785-SS-Trade-Breaks          | 10            | False       | False        | 40       | ✓
786-SS-Bull-OverBought       | 70            | False       | False        | 0        | ✓
787-SS-Bull-TRR-Rev          | 50            | False       | False        | 30       | ✓
788-SS-!Bull-TN-TD-TRR       | 30            | False       | False        | 20       | ✓
789-SS-!Bull-OverBought      | 50            | False       | False        | 20       | ✓
791-STM-!Bull-HighAbvTRR     | 10            | False       | False        | 10       | ✓
792-STM-Bull-TN-TD-TRR-RSI-IV | 50          | False       | False        | 30       | ✓
793-STM-!TD!Bull-TRR-Rev     | 30            | False       | False        | 50       | ✓
796-SW-!Bull-BBTh-Crossover  | 20            | False       | False        | 10       | ✓
798-STM-!Bull-TRR-Rev        | 40            | False       | False        | 50       | ✓
857-SS-BBTh-Crossover-RSIOnly | 20           | False       | False        | 0        | ✓
858-SS-Bull-BBTh-Crossover-RSI-IV | 50       | False       | False        | 0        | ✓
859-SS-Bull-BBTh-Crossover-RSI-IVHV | 50     | False       | False        | 10       | ✓
887-STM-!Bull--BBTh-Crossover-RSI-IV | 40    | False       | False        | 10       | ✓
888-STM-!Bull-BBTh-Crossover-RSI-IVHV | 40  | False       | False        | 20       | ✓
889-STM-OverBought           | 60            | False       | False        | 10       | ✓
893-SA-TRR-blw-TN            | 50            | False       | False        | 0        | ✓
894-SA-!Bull-TN-TRR          | 30            | False       | False        | 10       | ✓
895-SA-!TN!TD!Bull-TRR-Rev   | 40            | False       | False        | 40       | ✓
896-SA-TRbelowTN-Trade-Breaks | 20           | False       | False        | 20       | ✓
897-SW-Vlm-Spike-Price-Dn    | 10            | False       | False        | 0        | ✓
898-SA-Streak-VeryBad        | 20            | False       | False        | 40       | ✓
899-SA-Trend-Breaks          | 20            | False       | False        | 20       | ✓
93-BW-LRRabvTD               | 10            | False       | False        | 40       | ✓
94-BW-UP-MACD                | 21            | False       | False        | 54       | ✓
95-BW-LowBelwLRR             | 20            | False       | False        | 30       | ✓
96-BW-RSI-IVHV-Min           | 40            | False       | False        | 60       | ✓
97-BW-TD-RSI-IV              | 20            | False       | False        | 60       | ✓
98-BW-TD-LRR-RSI             | 10            | False       | False        | 70       | ✓
99-BS-Min                    | 31            | False       | False        | 75       | ✓
```

**Summary: 61 common codes, 61 matches, 0 mismatches.**

Excel fired (4): 395, 396, 397, 448. DB triggered=True for same 4. Perfect agreement.

DB-only triggered codes (not in Excel comparison set): 51-BS-TRADE-TREND, 52-BS-BRR,
92-BS-RSI-MACD-Vlme-IVHV-IVBRR, BASE-RR-Position.

---

## Step 2 — PRMB atomic values (non-null, 2026-06-05)

```
macdh_direction: -1        macd_direction: -1         bb_direction: -1
bb_threshold: 0            bbthresh_co_days: 1        bbthresh_co_days2: 2
trade_cross_over: 0        trade_rule: 2              not_trade_rule: -2
trend_cross_over: 0        trend_rule: 2              not_trend_rule: -2
trend_trade_dep_rule: 2    trtn_relation: 1           not_trtn_relation: -1
trade_trend_sd_rule: 1     brrpct_rule: 3             brrpct_lrr: 3
brrpct_r2: 3               brrpct_lrr2: 3             brrpct_trr: 1
brrpct_puts: -1            brrpct_trr_puts: -1        brrpct_dir: -1
high_trr: 3                low_lrr: 2                 trend_below_trr: 0
lrr_above_trade: 1         trr_idx: -1                mrr_idx: -1
lrr_idx: 0                 hvabsolute: 3              ivabsolute: 1
ivpercentile: 2            ivpercentile_puts: -1      hvpercentile: 2
hvpercentile_puts: -2      ivhv: 2                    ivhv_puts: -2
ivrule: 2                  rsi_rule: 2                rsi_top: 1
rsi_puts: -1               3m_low_rule: 3             3m_low_days_rule: 3
3mn_high_rule: -2          3mn_high_days_rule: 3      3m_long: 3
perf3mn_sd_rule: 1         perf2m_sd_rule: 2          perf3wk_sd_rule: 1
perf2wk_sd_rule: -1        perf3d_sd_rule: -3         perf1d_sd_rule: -1
not_perf1d_sd: 1           perf3d_sd_1off: 3          perf_sd_rule: 1
not_perf_sd_rule: -1       not_perf3d_rule: 3         bbhighlow_sd_rule: -2
bbhighlow_days_rule: 2     bbstreak_rule: -1          bbstreakrule1: -3
bbstreak_rule2: 1          bbstreak_days_rule: 3      bbstreak_days_rule2: 1
bbstreak_days_rule3: 3     bbstreak_days_rule4: 1     bb_bull_rule: -2
bb_bull_puts: 2            bbhighdays: 1              bblowdays: 3
macd_rule: 2               macdh_rule: 2              macd_and_h_rule: 2
macd_brr_puts: -2          macdh_brr_puts: -1         macd_and_h_rule_puts: -2
macdh_days: -3             macdh_days2: -1            overbought: 0
not_overbought: 0          3mn_outlook: -1            3mn_outlook_days: -1
3wk_outlook: -2            3wk_outlook_days: -2       not_3wk_ol: 2
not_3wk_ol_days: 2         bull: 0                    not_bull: 0
50_dma_rule: 2             50_dma_crossover: 0        200_dma_rule: 2
200_dma_crossover: 0       52_wk_low_rule: 3          52_wk_high_rule: -3
brrtrade: 1                trrtrade: 0                down_resistance: 0.5
earnings: 1                current_price_sd_rule: -1  current_volume_rule: -1
current_volatility_rule: 2 ac: 0.82
```

Notable: `trade_cross_over=0`, `trend_cross_over=0` (no active crossover signal).
`bull=0` (neutral). `3wk_outlook=-2` (bearish). `bbstreak=-1`, `bbstreakrule1=-3`.

---

## Step 3 — PRMB source data

```
hist_td  : 1   (export_date = 2026-06-05) ✓
hist_tl  : 1   (export_date = 2026-06-05) ✓
hist_tw  : 10  (snapshot_date within 14 days of 2026-06-05) ✓
drv_quote: 1   (as_of_date = 2026-06-05) ✓
```

Full source data present.

Key values from hist_td and derived tables:
```
hist_td  high_price: 23.39    low_price: 22.825
drv_technicals a_trend_value: 20.11    a_trade_value: 22.06    last_price: 22.95
drv_rr         lrr: 22.36    trr: 25.58    mrr: 23.97
```

Note: `td_high` / `td_low` don't exist as column names — the actual columns in `hist_td`
are `high_price` / `low_price`; the task query used Excel-style names.

Crossover context: last_price (22.95) > a_trade_value (22.06) > lrr (22.36)?
No — a_trade_value (22.06) < lrr (22.36), so price is above trade but trade is below LRR.
`trade_cross_over=0` and `trend_cross_over=0` are consistent with this positioning.

---

## Step 4 — verdict

**PRMB: Excel-fired and DB-fired MATCH across all 61 common composites.**

- 4 fire in both Excel and DB: **395-BS-TN-TD-LRR, 396-BS-LRR-CloseToTrade,
  397-B-TN-TD-LRR, 448-BS-TN-TD-LRR**
- 57 codes: neither Excel nor DB fires — all agree
- Zero disagreements

No cause analysis needed — there are no mismatches.

DONE
