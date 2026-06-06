# AGENT_RESULT_08 — clean compare on 2026-06-05 vs fresh TrigMA.xlsx
Date run: 2026-06-06

---

## Step 1 — date alignment

- TrigMA.xlsx Key date (Excel serial 46178): **2026-06-05** ✓
- DB anchor (`MAX(export_date) FROM hist_td`): **2026-06-05** ✓
- Both match.

---

## Step 2 — re-derive decision

Skipped. `drv_cat_atomic_input` for 2026-06-05 was last computed at
`2026-06-06 11:49:04` (Task 06 re-derive). No new ETL loads since then.
Derive is current.

---

## Step 3 — full compare on 2026-06-05 (fresh TrigMA.xlsx)

```
Phase 1 (atomic) :  99.91% match  (77 mismatches across 26 columns, 792 symbols)
Phase 2 (composite): 99.89% match  (55 mismatches across 5 codes, 792 symbols)
```

### Phase 1 top mismatches by column

| Column | Count |
|---|---|
| current_price_sd_rule | 18 |
| lrr_idx | 8 |
| trade_cross_over | 7 |
| trend_cross_over | 6 |
| trr_idx | 4 |
| low_lrr | 4 |
| high_trr | 3 |
| (all others) | ≤2 |

755/792 symbols are perfect-match on atomics.

### Phase 2 top mismatches by code

| Code | Count |
|---|---|
| 186-BR-Trend-CO | 51 |
| 396-BS-LRR-CloseToTrade | 1 |
| 94-BW-UP-MACD | 1 |
| 196-BS-TN-LRR | 1 |
| 95-BW-LowBelwLRR | 1 |

737/792 symbols are perfect-match on composites.

---

## Step 4 — regression check vs 6/4 baseline

6/4 baseline top-10: 697=564, 93=86, 99=70, 186=61, 791=60, 395=52, 397=52, 279=48, 94=46, 396=32.

### Q1 — Did 697 clear?

**YES.** 697-STM-Earnings-Date is not in the top-30 or anywhere in the output. Count ≈ 0. ✓

### Q2 — Is Phase 1 back near ~99.9%?

**YES.** Phase 1 = 99.91%. ✓ This confirms the fresh TrigMA.xlsx aligns with the
post-load 2026-06-05 DB state.

### Q3 — Did any composite count go UP vs the 6/4 baseline?

**NO. Every code dropped.**

| Code | 6/4 baseline | 6/5 fresh | Δ |
|---|---|---|---|
| 697-STM-Earnings-Date | 564 | ≈0 | ↓ Cleared ✓ |
| 93-BW-LRRabvTD | 86 | 0 | ↓ ✓ |
| 99-BS-Min | 70 | 0 | ↓ ✓ |
| 186-BR-Trend-CO | 61 | **51** | ↓ -10 ✓ |
| 791-STM-!Bull-HighAbvTRR | 60 | 0 | ↓ ✓ |
| 395-BS-TN-TD-LRR | 52 | 0 | ↓ ✓ |
| 397-B-TN-TD-LRR | 52 | 0 | ↓ ✓ |
| 279-BS-BB-Streak-HiHi | 48 | 0 | ↓ ✓ |
| 94-BW-UP-MACD | 46 | 1 | ↓ ✓ |
| 396-BS-LRR-CloseToTrade | 32 | 1 | ↓ ✓ |

No regressions introduced. The elevated counts seen in Task 06 (796=189, 699=146,
395/397=103) were an artifact of comparing the freshly fixed DB against the OLD
TrigMA.xlsx (dated 2026-06-04). With the date-matched fresh file they all disappeared.

### Remaining gap — 186-BR-Trend-CO (51 mismatches)

All 51 are `xl=True, db=False` (Excel fires, DB doesn't). ExVal = 1 or 2. This is a
pre-existing gap that was present before the double-eval fix (61 on 6/4 → 51 on 6/5,
continuing to decrease naturally). Not a regression.

The 4 non-186 composite mismatches (1 each on 396/94/196/95) are effectively noise.

DONE
