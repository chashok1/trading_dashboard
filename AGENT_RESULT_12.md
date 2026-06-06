# AGENT RESULT 12 — Phase 2: engine edits no-op + strict refactor gate check

**Date run:** 2026-06-06  
**Compare date:** 2026-06-05

---

## Step 1 — Baseline snapshot

```sql
DROP TABLE IF EXISTS _eng_before;
CREATE TABLE _eng_before AS
SELECT 'trig' src, composite_rule_code, tos_symbol FROM drv_trig
WHERE as_of_date='2026-06-05' AND triggered=TRUE
UNION ALL
SELECT 'stks', t->>'rule_id', tos_symbol
FROM drv_stks, jsonb_array_elements(triggered_composite_ids) t
WHERE as_of_date='2026-06-05';
```

| src  | count |
|------|-------|
| stks | 2568  |
| trig | 2568  |

---

## Step 2 — Re-derive with new engine code

```
python agent_rederive_all.py
```

```
derive_all done for 2026-06-05
  drv_cat_atomic_input: 884
  drv_stks: 1123
  drv_trig: 77487
  drv_actionable: 1204
```

---

## Step 3 — Engine edits no-op confirmation

**trig diff rows: 0**  
**stks diff rows: 0**

Both diffs empty. Engine edits 1 (nested gate fix in drv_stks) and 2 (two-pass in drv_trig) are confirmed no-op — no live leaf currently nests a BASE composite.

---

## Step 4 — DRY-RUN strict refactor

```
python -m etl.refactor_base_rules --date 2026-06-05
```

### Proposed rewrites (8 leaves — down from 25 in task 10):

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

### Firing diff (drv_stks):

| Composite | Before | After | Delta |
|---|---|---|---|
| 198-BS-TN-LRR-UP-MACD | 3 | 0 | **-3** |
| 199-BS-TN-LRR-MACD-UP-DAY | 1 | 0 | **-1** |
| 399-B-TN-TD-LRR-UP-MACD | 1 | 0 | **-1** |
| 449-B-TN-TD-LRR-UP-MACD | 4 | 1 | **-3** |
| 94-BW-UP-MACD | 7 | 0 | **-7** |

**5 composites changed (all decreases). Refactor is NOT score-neutral.**

---

## GATE — STOPPED

Step 3 is clean. Step 4 has 5 firing changes. **Do not proceed to Step 5.**

---

## Root cause analysis

All 5 changes are caused by the **same single atom: atom 112** (`vs_lt_outlook_rule`, thr=0, op='>=', override=NULL in BASE-Bull-Context).

**The problem:**  
`_member_equiv` explicitly ignores `weight_override`, reasoning "weight affects score, not gate/watch firing decision." This holds when `val != 0`. It **breaks** when `val = 0` with `thr = 0` and `op = '>='`:

- **Flat leaf** (override=10): `condition_met = (0 >= 0)` = True → `_atomic_member_weight` returns `float(10)` → gate check `hit = (w != 0)` = **True** → gate passes.
- **BASE-Bull-Context** (override=NULL): `condition_met = True` → returns `val = 0.0` → gate check `hit = (0.0 != 0.0)` = **False** → gate fails → BASE doesn't fire → leaf gate fails.

Verified: all 3 symbols firing 198-BS (`EBAY`, `TYX:CGI`, `V`) have `vs_lt_outlook_rule = 0` exactly. For 449 and 94, the same pattern applies (the 1 symbol that still fires in 449 has `vs_lt_outlook_rule != 0`).

**Why 93-BW-LRRabvTD (BASE-Bull-Trend, atom 12 thr=0) showed no change:**  
Atom 12 is `trade_rule`. For the symbols currently firing 93, `trade_rule > 0` (none have exactly 0). The latent weight_override mismatch exists but doesn't manifest in today's data. With different data it would.

---

## Recommended fix

**One-line change to `_member_equiv` in `etl/refactor_base_rules.py`:** include `weight_override` in the equivalence check.

Since all leaf atoms involved have `weight_override=10` and all BASE members have `weight_override=NULL`, they are not identical — and the absorption should be rejected. This would reduce the 8 proposed rewrites to fewer (possibly to 93-BW-LRRabvTD only if atom 12 never has val=0 in practice, or to zero if override is included strictly).

A more principled alternative: change `_composite_fire`'s gate hit check from `hit = (w != 0)` to a separate `condition_met` boolean propagated from `_atomic_member_weight`. This removes the ambiguity between "condition met but value is zero" vs "condition not met". But it's a larger change touching the core engine.

The targeted fix for Phase 2 score-neutrality: **add override to `_member_equiv`**.

---

## Steps 5–7 — NOT executed (gate failed)

---

## Summary

| Check | Result |
|---|---|
| Engine edit 1 (drv_stks nested gate) no-op? | **YES** — 0 trig changes, 0 stks changes |
| Engine edit 2 (drv_trig two-pass) no-op? | **YES** — 0 changes |
| Strict refactor score-neutral? | **NO** — 5 composites changed (all -) |
| Root cause | `_member_equiv` ignores weight_override; val=0 with thr=0 op>= passes in leaf (override=10→returns 10) but fails in BASE (override=NULL→returns 0) |
| Affected atom | 112 (vs_lt_outlook_rule), val=0 for affected symbols |
| Steps 5–7 run? | No |
