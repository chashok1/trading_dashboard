# AGENT_RESULT_02 — shared-firing refactor no-regression check
Date run: 2026-06-05

---

## Step 1 — re-derive full cascade (fresh process)

Command: `python agent_rederive_all.py`

```
hist_rr: 1 symbols not mapped to tos_symbol
C:\Ashok\Invest\Projects\trading-dashboard\etl\db.py:98: SAWarning: Can't validate argument 'dialect_options'; can't locate any SQLAlchemy dialect named 'dialect'
  md.reflect(bind=get_engine())
atomic rule 118 ('End') has no resolvable ma column (ma_column_name='End') — will evaluate to 0
atomic rule 4 ('Begin') has no resolvable ma column (ma_column_name='Begin') — will evaluate to 0
derive_actionable: PS asset_class '? Global Equities' for BUG has no ref_asset_allocation row; using fallback 'PS'
derive_actionable: PS asset_class '_ Foreign Currencies' for DBMF has no ref_asset_allocation row; using fallback 'PS'
derive_actionable: PS asset_class '_?_ International Equities' for NORW has no ref_asset_allocation row; using fallback 'PS'
derive_actionable: PS asset_class '_? Global Equities' for TAN has no ref_asset_allocation row; using fallback 'PS'
derive_actionable: PS asset_class '_ Foreign Currencies' for uuP has no ref_asset_allocation row; using fallback 'PS'
atomic rule 118 ('End') has no resolvable ma column (ma_column_name='End') — will evaluate to 0
atomic rule 4 ('Begin') has no resolvable ma column (ma_column_name='Begin') — will evaluate to 0
derive_all done for 2026-06-04
  drv_cat_atomic_input: 884
  drv_stks: 1123
  drv_trig: 77487
  drv_actionable: 1206
```

---

## Step 2 — comparison report

Command: `python compare_trigma.py`

### SUMMARY (bottom of trigma_report.txt)

```
Phase 1 (atomic) :  99.90% match  (91 mismatches across 35 columns, 792 symbols)
Phase 2 (composite): 96.93% match  (1484 mismatches across 39 codes, 792 symbols)
```

### Phase 2 — Mismatches by composite code (top 10)

```
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
```

---

## Step 3 — spot checks

Command: `python agent_queries2.py`

```
3a. AAAU / 186-BR-Trend-CO
  ['AAAU', '186-BR-Trend-CO', Decimal('82'), False, 10]

3b. Overall fire-rate distribution
  triggered=False  count=72229
  triggered=True  count=5258
```

---

## Verdict

No regression. All numbers match the prior run (AGENT_RESULT_01.md):
- Phase 1: 99.90% (unchanged)
- Phase 2: 96.93% (unchanged)
- AAAU/186-BR-Trend-CO: triggered=False (unchanged)
- Fire-rate: 5258 true / 72229 false (unchanged)

DONE
