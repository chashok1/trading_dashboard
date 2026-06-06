# AGENT_RESULT_06 — verify drv_trig double-eval fix (697 over-firing)
Date run: 2026-06-06

---

## Step 1 — re-derive 2026-06-04 and 2026-06-05

Re-derive was run for both 2026-06-04 (via `agent_rederive_all.py`) and then 2026-06-05
(anchor = MAX(export_date) FROM hist_td), since `compare_trigma.py` always compares against
the latest as_of_date in the DB and TrigMA.xlsx is dated 2026-06-05.

```
derive_all done for 2026-06-04
  drv_cat_atomic_input: 884
  drv_stks: 1123
  drv_trig: 77487
  drv_actionable: 1206

derive_all done for 2026-06-05
  drv_cat_atomic_input: 884
  drv_stks: 1123
  drv_trig: 77487
  drv_actionable: 1204
```

---

## Step 2 — confirm 697 now fires ONLY for imminent earnings

```
  ASO          earn= -3  fired=True  score=10
  DOCU         earn= -3  fired=True  score=10
  ORCL         earn= -3  fired=True  score=10
  AAL          earn=  1  fired=False  score=0
  AAPL         earn=  1  fired=False  score=0
  CRM          earn=  1  fired=False  score=0
  MSFT         earn=  1  fired=False  score=0
  NVDA         earn=  1  fired=False  score=0
```

**CORRECT.** `db_697_fired = True` only where `atomic_earnings = -3` (imminent). All
far-from-earnings symbols (atomic = 1) now return `fired=False`. Fix confirmed.

---

## Step 3 — full regression compare (2026-06-05)

```
Phase 1 (atomic) :  75.25% match  (21958 mismatches across 111 columns, 792 symbols)
Phase 2 (composite): 96.90% match  (1496 mismatches across 44 codes, 792 symbols)
```

Phase 2 jumped from ~6.66% (45093 mismatches, broken state) to **96.90% (1496 mismatches)**.
Phase 1 unchanged at 75.25% vs 75.26% (noise from one extra day of data). ✓

### Top-10 composite mismatch counts (new vs prior)

| Code | Prior count | New count | Δ |
|---|---|---|---|
| 697-STM-Earnings-Date | 564 | not in top-30 (≈0) | ↓ Cleared ✓ |
| 93-BW-LRRabvTD | 86 | 78 | ↓ ✓ |
| 99-BS-Min | 70 | 70 | same |
| 186-BR-Trend-CO | 61 | 65 | ↑ +4 ⚠️ |
| 791-STM-!Bull-HighAbvTRR | 60 | 54 | ↓ ✓ |
| 395-BS-TN-TD-LRR | 52 | 103 | ↑ +51 ⚠️ |
| 397-B-TN-TD-LRR | 52 | 103 | ↑ +51 ⚠️ |
| 279-BS-BB-Streak-HiHi | 48 | 44 | ↓ ✓ |
| 94-BW-UP-MACD | 46 | 27 | ↓ ✓ |
| 396-BS-LRR-CloseToTrade | 32 | 43 | ↑ +11 ⚠️ |

### New high-count codes not in prior top-10

| Code | New count | Note |
|---|---|---|
| 796-SW-!Bull-BBTh-Crossover | 189 | ⚠️ newly prominent |
| 699-SW-Resistance | 146 | ⚠️ newly prominent |
| 448-BS-TN-TD-LRR | 85 | ⚠️ newly prominent |

### Flagged regressions (mismatch count went UP or newly prominent)

1. **796-SW-!Bull-BBTh-Crossover** — 189 mismatches (was not in prior top-10). Mix of
   `xl=False, db=True` and `xl=True, db=False`. Likely related to the `_eval_trig_ifs`
   boundary-condition changes (strict→inclusive for negative thresholds).

2. **699-SW-Resistance** — 146 mismatches. Mostly `xl=False, db=True` (DB over-fires).
   Same boundary-condition suspect.

3. **395-BS-TN-TD-LRR** and **397-B-TN-TD-LRR** — both jumped from 52 → 103.
   Both directions present. These share LRR members — possible threshold boundary
   sensitivity from the `_eval_trig_ifs` strict→inclusive change.

4. **448-BS-TN-TD-LRR** — 85 (not in prior top-10). Related to 395/397 family.

5. **396-BS-LRR-CloseToTrade** — 32 → 43 (+11).

6. **186-BR-Trend-CO** — 61 → 65 (+4, minor).

**Note:** Prior run used 2026-06-04 data; current run uses 2026-06-05 data, so some
natural drift is expected. The regressions in 796/699/395/397/448 likely trace to the
`_eval_trig_ifs` boundary-condition changes in `derive_cat_atomic_input.py`, not the
697 double-eval fix itself.

DONE
