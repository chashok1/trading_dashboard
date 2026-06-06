# AGENT RESULT 10 — Phase 2 Base Rules: Score-Neutral Verify

**Date run:** 2026-06-06  
**Compare date:** 2026-06-05  
**Outcome: STOPPED AT GATE (Step 3) — firing changes detected, NOT applied.**

---

## Step 0 — Current live state (before)

### BASE-* composites already in DB:
```
BASE-Bear-Context
BASE-Bull-Context
BASE-Bull-Trend
BASE-RR-Position
BASE-Vol-Regime
```
(All 5 already existed — seeds were applied in a prior session.)

### Leaf composites already referencing a nested composite:
```
(none)
```

---

## Step 1 — Baseline snapshot

```sql
DROP TABLE IF EXISTS _p2_before;
CREATE TABLE _p2_before AS
SELECT composite_rule_code, tos_symbol
FROM drv_trig
WHERE as_of_date = '2026-06-05' AND triggered = TRUE;
```

**before_fired_pairs: 2568**

---

## Step 2 — Apply seeds_base_rules.sql

Command used:
```
psql -h localhost -p 5432 -U postgres -d trading -f db/seeds_base_rules.sql
```

Output:
```
BEGIN
DELETE 14
INSERT 0 14
NOTICE:  seeds_base_rules: 5 BASE composites, 14 members inserted
COMMIT
```

BASE-* re-confirmed after apply:
```
BASE-Bear-Context
BASE-Bull-Context
BASE-Bull-Trend
BASE-RR-Position
BASE-Vol-Regime
```

---

## Step 3 — DRY-RUN refactor_base_rules

Command:
```
python -m etl.refactor_base_rules --date 2026-06-05
```

### Proposed rewrites (25 leaves):

| Leaf composite | Members before → after | Bases nested |
|---|---|---|
| 186-BR-Trend-CO | 12 → 9 | BASE-Bear-Context(gate)←[47,81,112], BASE-Vol-Regime(watch)←[42,44] |
| 187-BR-NoTN-NoTD-UP-MACD-DAY | 13 → 10 | BASE-Bear-Context(watch)←[47,81,112], BASE-Vol-Regime(watch)←[42,44] |
| 188-BR-TNabvTD-UP-MACD-DAY | 12 → 9 | BASE-Bear-Context(gate)←[47,81,112], BASE-Vol-Regime(watch)←[42,44] |
| 189-BR-BB-LoHi | 14 → 11 | BASE-Bear-Context(watch)←[47,81,112], BASE-Vol-Regime(watch)←[42,44] |
| 196-BS-TN-LRR | 9 → 8 | BASE-Vol-Regime(watch)←[42,44] |
| 197-BS-TN-LRR-UP-DAY | 13 → 10 | BASE-Bull-Context(gate)←[58,60,112], BASE-Vol-Regime(watch)←[42,44] |
| 198-BS-TN-LRR-UP-MACD | 11 → 8 | BASE-Bull-Context(gate)←[58,60,112], BASE-Vol-Regime(watch)←[42,44] |
| 199-BS-TN-LRR-MACD-UP-DAY | 12 → 9 | BASE-Bull-Context(gate)←[58,60,112], BASE-Vol-Regime(watch)←[42,44] |
| 267-BS-Trade-CO | 10 → 7 | BASE-Bear-Context(watch)←[47,81,112], BASE-Vol-Regime(watch)←[42,44] |
| 268-BS-3M-HiHi | 15 → 10 | BASE-Bear-Context(watch)←[47,81,112], BASE-Bull-Trend(gate)←[5,12,15], BASE-Vol-Regime(watch)←[42,44] |
| 269-BS-Bull | 16 → 11 | BASE-Bear-Context(gate)←[47,81,112], BASE-Bull-Trend(gate)←[5,12,15], BASE-Vol-Regime(watch)←[42,44] |
| 277-BS-VS-LT | 6 → 5 | BASE-Vol-Regime(watch)←[42,44] |
| 278-BS-BB-HL-HiHi | 12 → 9 | BASE-Bear-Context(watch)←[47,81,112], BASE-Vol-Regime(watch)←[42,44] |
| 279-BS-BB-Streak-HiHi | 11 → 8 | BASE-Bear-Context(watch)←[47,81,112], BASE-Vol-Regime(watch)←[42,44] |
| 298-BS-BB-HL-HiHi-TN-TD | 14 → 9 | BASE-Bear-Context(watch)←[47,81,112], BASE-Bull-Trend(gate)←[5,12,15], BASE-Vol-Regime(watch)←[42,44] |
| 299-BS-BB-Streak-HiHi-TN-TD | 13 → 8 | BASE-Bear-Context(watch)←[47,81,112], BASE-Bull-Trend(gate)←[5,12,15], BASE-Vol-Regime(watch)←[42,44] |
| 397-B-TN-TD-LRR | 10 → 9 | BASE-Vol-Regime(watch)←[42,44] |
| 398-B-TN-TD-LRR-UP-DAY | 11 → 8 | BASE-Bull-Context(gate)←[58,60,112], BASE-Vol-Regime(watch)←[42,44] |
| 399-B-TN-TD-LRR-UP-MACD | 11 → 8 | BASE-Bull-Context(gate)←[58,60,112], BASE-Vol-Regime(watch)←[42,44] |
| 449-B-TN-TD-LRR-UP-MACD | 10 → 7 | BASE-Bull-Context(gate)←[58,60,112], BASE-Vol-Regime(watch)←[42,44] |
| 92-BS-RSI-MACD-Vlme-IVHV-IVBRR | 4 → 3 | BASE-Vol-Regime(gate)←[42,44] |
| 93-BW-LRRabvTD | 5 → 3 | BASE-Bull-Trend(gate)←[5,12,15] |
| 94-BW-UP-MACD | 12 → 10 | BASE-Bull-Context(gate)←[58,60,112] |
| 96-BW-RSI-IVHV-Min | 10 → 8 | BASE-Bear-Context(gate)←[47,81,112] |
| 99-BS-Min | 16 → 15 | BASE-Vol-Regime(watch)←[42,44] |

### Firing diff (drv_stks fire counts BEFORE vs AFTER):

| Composite | Before | After | Delta |
|---|---|---|---|
| 188-BR-TNabvTD-UP-MACD-DAY | 6 | 4 | **-2** |
| 198-BS-TN-LRR-UP-MACD | 3 | 12 | **+9** |
| 199-BS-TN-LRR-MACD-UP-DAY | 1 | 4 | **+3** |
| 279-BS-BB-Streak-HiHi | 34 | 40 | **+6** |
| 299-BS-BB-Streak-HiHi-TN-TD | 4 | 115 | **+111** |
| 398-B-TN-TD-LRR-UP-DAY | 0 | 1 | **+1** |
| 399-B-TN-TD-LRR-UP-MACD | 1 | 3 | **+2** |
| 449-B-TN-TD-LRR-UP-MACD | 4 | 120 | **+116** |
| 92-BS-RSI-MACD-Vlme-IVHV-IVBRR | 135 | 769 | **+634** |
| 93-BW-LRRabvTD | 69 | 449 | **+380** |
| 94-BW-UP-MACD | 7 | 16 | **+9** |

**11 composites changed fire counts — refactor is NOT score-neutral.**

---

## GATE — STOPPED

Per task gate condition: any predicted firing change → **STOP, do not apply.**

**Steps 4–7 were NOT executed.**

---

## Rollback path

The dry-run automatically rolls back (no commit). The backup JSON was written to:
```
db/backups/refactor_base_rules_20260606_150428.json
```
If `--apply` had been run and later needed reversal: `python -m etl.rebuild_rules` (reloads from Tickers workbook, replacing all composite members).

---

## Analysis of the firing changes

The large deltas (92, 93, 449, 299) suggest the BASE members' thresholds or operators in
`seeds_base_rules.sql` differ from the per-leaf thresholds the workbook originally set.
When the BASE atomic members are nested by reference, the BASE's threshold/operator values
are used instead of the leaf's per-member values — and those differ enough to fire
or suppress hundreds of extra symbols.

Likely root cause: `seeds_base_rules.sql` uses "dominant per-member value observed in the
workbook" (per file comment), but individual leaf composites have per-member thresholds
that vary. The nested BASE uses a single fixed threshold, not the leaf-specific one.

The refactor is **not score-neutral** with the current BASE thresholds. Needs design
review before applying.

---

## Summary

| Question | Answer |
|---|---|
| BASE-* existed before? | Yes, all 5 (prior session) |
| Seeds apply clean? | Yes (idempotent, 14 members) |
| before_fired_pairs | 2568 |
| Dry-run score-neutral? | **NO — 11 composites changed** |
| Applied? | **NO — stopped at gate** |
| Steps 4–7 run? | No |
