# AGENT RESULT 13 — Phase 2: weight-matched seeds + strict refactor (verify + apply)

**Date run:** 2026-06-06  
**Compare date:** 2026-06-05  
**Status: Steps 1–3 complete. Gate PASSED. Awaiting approval to execute Steps 4–6.**

---

## Step 1 — Seed re-applied (weight_override=10)

```
psql -h localhost -p 5432 -U postgres -d trading -f db/seeds_base_rules.sql
```
```
BEGIN
DELETE 14
INSERT 0 14
NOTICE:  seeds_base_rules: 5 BASE composites, 14 members inserted
COMMIT
```

BASE-Bull-Context confirmation (`SELECT atomic_rule_id, weight_override ... WHERE composite_rule_code='BASE-Bull-Context'`):

| atomic_rule_id | weight_override |
|---|---|
| 58 | **10** |
| 60 | **10** |
| 112 | **10** |

All 10. ✓

---

## Step 2 — Re-derive + leaf baseline snapshot

```
python agent_rederive_all.py
```
```
derive_all done for 2026-06-05
  drv_cat_atomic_input: 884
  drv_stks:             1123
  drv_trig:             77487
  drv_actionable:       1204
```

Leaf baseline (excluding BASE-* codes):

| src  | count |
|------|-------|
| stks | 2255  |
| trig | 2255  |

**compare_trigma.py (pre-refactor baseline):**

| Phase | Match rate | Mismatches | Perfect symbols |
|---|---|---|---|
| Phase 1 (atomic) | **99.91%** | 77 | 755/792 |
| Phase 2 (composite) | **99.89%** | 55 | 737/792 |

Top-10 composite mismatches: 186-BR-Trend-CO (51), 396-BS-LRR-CloseToTrade (1), 94-BW-UP-MACD (1), 196-BS-TN-LRR (1), 95-BW-LowBelwLRR (1). All pre-existing. 697 codes cleared (61 compared, 55 mismatches across 5 codes). ✓

Seed weight change alone did not alter leaf firing — confirmed no-op for leaves (BASE-* have no leaf referencing them yet).

---

## Step 3 — DRY-RUN strict refactor

```
python -m etl.refactor_base_rules --date 2026-06-05
```

### Proposed rewrites (8 leaves):

| Leaf | Before → After | Bases nested |
|---|---|---|
| 197-BS-TN-LRR-UP-DAY | 13 → 11 | BASE-Bull-Context(gate)←[58,60,112] |
| 198-BS-TN-LRR-UP-MACD | 11 → 9 | BASE-Bull-Context(gate)←[58,60,112] |
| 199-BS-TN-LRR-MACD-UP-DAY | 12 → 10 | BASE-Bull-Context(gate)←[58,60,112] |
| 398-B-TN-TD-LRR-UP-DAY | 11 → 9 | BASE-Bull-Context(gate)←[58,60,112] |
| 399-B-TN-TD-LRR-UP-MACD | 11 → 9 | BASE-Bull-Context(gate)←[58,60,112] |
| 449-B-TN-TD-LRR-UP-MACD | 10 → 8 | BASE-Bull-Context(gate)←[58,60,112] |
| 93-BW-LRRabvTD | 5 → 3 | BASE-Bull-Trend(gate)←[5,12,15] |
| 94-BW-UP-MACD | 12 → 10 | BASE-Bull-Context(gate)←[58,60,112] |

### Firing diff:
```
No change in fire counts — refactor is firing-equivalent. ✓
```

**GATE PASSED.** ✓

---

## Steps 4–6 — PENDING APPROVAL

The gate passed. Waiting for explicit approval to run:
```
python -m etl.refactor_base_rules --date 2026-06-05 --apply
python agent_rederive_all.py
python -m etl.rebuild_rules
python agent_rederive_all.py
```
Rollback: `python -m etl.rebuild_rules` (reloads all composite members from Tickers workbook).
