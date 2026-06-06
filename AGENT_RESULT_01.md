# AGENT_RESULT_01 — drv_trig composite-firing fix verification
Date run: 2026-06-05

---

## Step 1 — re-derive drv_trig (fresh process)

Command: `python agent_rederive_trig.py`

```
C:\Ashok\Invest\Projects\trading-dashboard\etl\db.py:98: SAWarning: Can't validate argument 'dialect_options'; can't locate any SQLAlchemy dialect named 'dialect'
  md.reflect(bind=get_engine())
atomic rule 118 ('End') has no resolvable ma column (ma_column_name='End') — will evaluate to 0
atomic rule 4 ('Begin') has no resolvable ma column (ma_column_name='Begin') — will evaluate to 0
drv_trig re-derived for 2026-06-04: 77487 rows
```

---

## Step 2 — comparison report (trigma_report.txt PHASE 2)

Command: `python compare_trigma.py`

Full output:

```
======================================================================
TrigMA vs DB Comparison Report
Date: 2026-06-04
======================================================================

Loading TrigMA.xlsx ...
Excel: 792 tradeable symbols loaded, 30 index/futures skipped

Querying DB drv_cat_atomic_input for 2026-06-04 ...
DB atomic: 884 symbols

Querying DB drv_trig for 2026-06-04 ...
DB composite: 1123 symbols, codes per sample: 69

──────────────────────────────────────────────────────────────────────
SYMBOL COVERAGE
──────────────────────────────────────────────────────────────────────
Excel tradeable symbols:         792
DB atomic symbols:               884
DB trig symbols:                 1123
Common (atomic compare):         792
Common (composite compare):      792

In DB but NOT in Excel (92): ['$COMP', '$DJI', '$DXY', '/6B[M26]', '/6C[M26]', '/6E[M26]', '/6J[M26]', '/BTC[M26]', '/BZ[Q26]', '/CL[N26]', '/GC[Q26]', '/HG[N26]', '/NG[N26]', '/NKD[M26]', '/SI[N26]', 'ADYEY', 'APLE', 'ASBFF', 'AWAY', 'BBBY', 'BBY', 'BHP', 'BRCB', 'BTC-USD', 'BUG', 'C', 'CALY', 'CAMT', 'CFRUY', 'CNXT', ...]

──────────────────────────────────────────────────────────────────────
PHASE 1: ATOMIC RULE COLUMNS (drv_cat_atomic_input)
──────────────────────────────────────────────────────────────────────
Comparing 113 columns across 792 symbols

Total cells compared:     88704
Total mismatches:         91
Match rate:               99.90%
Perfect-match symbols:    749/792

Mismatches by column (top 30):
  Column                                    Mismatch Count
  ──────────────────────────────────────── ───────────────
  current_price_sd_rule                                 20
  lrr_idx                                                8
  trade_cross_over                                       7
  trend_cross_over                                       6
  trr_idx                                                4
  brrpct_lrr2                                            3
  brrpct_trr                                             3
  brrpct_r2                                              2
  hvpercentile                                           2
  hvpercentile_puts                                      2
  200_dma_rule                                           2
  perf3wk_sd_rule                                        2
  3mn_outlook                                            2
  low_lrr                                                2
  high_trr                                               2
  trend_rule                                             2
  not_trend_rule                                         2
  trend_trade_dep_rule                                   2
  down_resistance                                        2
  3mn_high_rule                                          1
  3mn_high_days_rule                                     1
  perf_sd_rule                                           1
  not_perf_sd_rule                                       1
  ivhv                                                   1
  ivhv_puts                                              1
  brrtrade                                               1
  3wk_outlook                                            1
  not_3wk_ol                                             1
  perf3mn_sd_rule                                        1
  52_wk_high_rule                                        1

Top symbols by mismatch count (top 20):
  Symbol                 Mismatches
  ──────────────────── ────────────
  XTL                             7
  STKL                            6
  CFLT                            5
  EXAS                            5
  FYBR                            5
  K                               5
  MCW                             5
  MOH                             4
  TOKE                            4
  EYE                             3
  LFST                            3
  PAM                             3
  CRCL                            2
  EPD                             2
  EWA                             2
  HPP                             2
  WYFI                            2
  AFK                             1
  BTAL                            1
  BUXX                            1

──────────────────────────────────────────────────────────────────────
PHASE 2: COMPOSITE RULE SCORES (drv_trig)
──────────────────────────────────────────────────────────────────────
Excel composite codes:    61
DB composite codes:       69
Common codes:             61
Only in DB:               ['51-BS-TRADE-TREND', '52-BS-BRR', '92-BS-RSI-MACD-Vlme-IVHV-IVBRR', 'BASE-Bear-Context', 'BASE-Bull-Context', 'BASE-Bull-Trend', 'BASE-RR-Position', 'BASE-Vol-Regime']

Comparing 61 codes across 792 symbols
Total cells compared:     48312
Total mismatches:         1484
Match rate:               96.93%
Perfect-match symbols:    120/792

Mismatches by composite code (top 30):
  Code                                           Mismatch Count
  ───────────────────────────────────────────── ───────────────
  697-STM-Earnings-Date                                     564
  93-BW-LRRabvTD                                             86
  99-BS-Min                                                  70
  186-BR-Trend-CO                                            61
  791-STM-!Bull-HighAbvTRR                                   60
  395-BS-TN-TD-LRR                                           52
  397-B-TN-TD-LRR                                            52
  279-BS-BB-Streak-HiHi                                      48
  94-BW-UP-MACD                                              46
  396-BS-LRR-CloseToTrade                                    32
  788-SS-!Bull-TN-TD-TRR                                     31
  449-B-TN-TD-LRR-UP-MACD                                    29
  399-B-TN-TD-LRR-UP-MACD                                    29
  448-BS-TN-TD-LRR                                           28
  898-SA-Streak-VeryBad                                      27
  698-SS-Bull-HighAbvTRR                                     25
  96-BW-RSI-IVHV-Min                                         24
  398-B-TN-TD-LRR-UP-DAY                                     23
  196-BS-TN-LRR                                              21
  784-SS-Streak-GoingBad                                     21
  97-BW-TD-RSI-IV                                            21
  98-BW-TD-LRR-RSI                                           21
  899-SA-Trend-Breaks                                        20
  267-BS-Trade-CO                                            17
  198-BS-TN-LRR-UP-MACD                                      11
  893-SA-TRR-blw-TN                                          10
  95-BW-LowBelwLRR                                           10
  394-BS-TN-LRR                                               8
  188-BR-TNabvTD-UP-MACD-DAY                                  7
  268-BS-3M-HiHi                                              7

Top symbols by composite mismatch count (top 20):
  Symbol                 Mismatches
  ──────────────────── ────────────
  MAC                            16
  EXPD                           15
  BXP                            14
  HUM                            13
  INTC                           13
  IRM                            13
  MCHP                           13
  CSX                            12
  EWJV                           12
  NSA                            12
  OMF                            12
  PFG                            12
  CSCO                           11
  ELV                            11
  CNC                            10
  UNH                            10
  STKL                            9
  CHEF                            8
  K                               8
  ECPG                            7

Sample composite mismatches (first 15 of 1484):
  Symbol               Code                                            ExVal  ExFired  DBFired
  ──────────────────── ───────────────────────────────────────────── ─────── ──────── ────────
  AAAU                 99-BS-Min                                           2     True    False
  AAL                  395-BS-TN-TD-LRR                                    0     True    False
  AAL                  396-BS-LRR-CloseToTrade                             0     True    False
  AAL                  397-B-TN-TD-LRR                                     1     True    False
  AAL                  448-BS-TN-TD-LRR                                    0     True    False
  AAL                  697-STM-Earnings-Date                              10    False     True
  AAPL                 697-STM-Earnings-Date                              10    False     True
  ABBV                 697-STM-Earnings-Date                              10    False     True
  ABBV                 791-STM-!Bull-HighAbvTRR                            0     True    False
  ABNB                 449-B-TN-TD-LRR-UP-MACD                             1     True    False
  ABNB                 697-STM-Earnings-Date                              10    False     True
  ABR                  697-STM-Earnings-Date                              10    False     True
  ABR                  893-SA-TRR-blw-TN                                   0     True    False
  ABT                  697-STM-Earnings-Date                              10    False     True
  ABT                  791-STM-!Bull-HighAbvTRR                            0     True    False

======================================================================
SUMMARY
======================================================================
Phase 1 (atomic) :  99.90% match  (91 mismatches across 35 columns, 792 symbols)
Phase 2 (composite): 96.93% match  (1484 mismatches across 39 codes, 792 symbols)
```

---

## Step 3 — verification queries

Command: `python agent_queries.py`

```
3a. Overall fire-rate distribution
  triggered=False  count=72229
  triggered=True  count=5258

3b. AAAU / 186-BR-Trend-CO
  ['AAAU', '186-BR-Trend-CO', Decimal('82'), False, 10]

3c. AAAU triggered-composite count
  aaau_triggered=5
```

---

DONE
