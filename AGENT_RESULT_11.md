# AGENT RESULT 11 — Why does the base-rule refactor change firing? (diagnostic)

**Date run:** 2026-06-06  
**Mode:** READ-ONLY — no changes applied.

---

## Q1 — BASE member definitions

| BASE | atom_id | thr | op | role | wt_override | ecut |
|---|---|---|---|---|---|---|
| BASE-Bear-Context | 47 | -2 | <= | gate | NULL | NULL |
| BASE-Bear-Context | 81 | -2 | <= | gate | NULL | NULL |
| BASE-Bear-Context | 112 | -2 | <= | gate | NULL | NULL |
| BASE-Bull-Context | 58 | 0 | >= | gate | NULL | NULL |
| BASE-Bull-Context | 60 | 3 | >= | gate | NULL | NULL |
| BASE-Bull-Context | 112 | 0 | >= | gate | NULL | NULL |
| BASE-Bull-Trend | 5 | 1 | >= | gate | NULL | NULL |
| BASE-Bull-Trend | 12 | 0 | >= | gate | NULL | NULL |
| BASE-Bull-Trend | 15 | 2 | >= | gate | NULL | NULL |
| BASE-RR-Position | 22 | 3 | >= | gate | NULL | NULL |
| BASE-RR-Position | 27 | -1 | <= | gate | NULL | NULL |
| BASE-RR-Position | 32 | 1 | >= | gate | NULL | NULL |
| BASE-Vol-Regime | 42 | 3 | >= | gate | NULL | NULL |
| BASE-Vol-Regime | 44 | 0 | >= | gate | NULL | NULL |

---

## Q2 — Leaf members for the absorbed atoms (the leaf's own values)

| leaf | atom_id | thr | op | role | wt_override | ecut |
|---|---|---|---|---|---|---|
| 198-BS-TN-LRR-UP-MACD | 15 | 2 | >= | gate | 10 | NULL |
| 198-BS-TN-LRR-UP-MACD | 42 | 3 | >= | **watch** | 1 | NULL |
| 198-BS-TN-LRR-UP-MACD | 44 | 0 | >= | **watch** | 1 | NULL |
| 198-BS-TN-LRR-UP-MACD | 58 | 0 | >= | gate | 10 | NULL |
| 198-BS-TN-LRR-UP-MACD | 60 | 3 | >= | gate | 10 | NULL |
| 198-BS-TN-LRR-UP-MACD | 81 | -2 | **>=** | watch | 1 | NULL |
| 198-BS-TN-LRR-UP-MACD | 112 | 0 | >= | gate | 10 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 5 | 1 | >= | gate | 10 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 12 | 0 | >= | gate | 10 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 15 | **3** | >= | gate | 10 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 42 | 3 | >= | **watch** | 1 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 44 | 0 | >= | **watch** | 1 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 47 | -2 | **>=** | gate | 10 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 60 | 3 | >= | gate | 10 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 81 | -2 | **>=** | **watch** | 1 | NULL |
| 299-BS-BB-Streak-HiHi-TN-TD | 112 | 0 | **>=** | gate | 10 | NULL |
| 449-B-TN-TD-LRR-UP-MACD | 12 | 0 | >= | gate | 10 | NULL |
| 449-B-TN-TD-LRR-UP-MACD | 15 | 2 | >= | gate | 10 | NULL |
| 449-B-TN-TD-LRR-UP-MACD | 42 | 3 | >= | **watch** | 1 | NULL |
| 449-B-TN-TD-LRR-UP-MACD | 44 | 0 | >= | **watch** | 1 | NULL |
| 449-B-TN-TD-LRR-UP-MACD | 58 | 0 | >= | gate | 10 | NULL |
| 449-B-TN-TD-LRR-UP-MACD | 60 | 3 | >= | gate | 10 | NULL |
| 449-B-TN-TD-LRR-UP-MACD | 112 | 0 | >= | gate | 10 | NULL |
| 92-BS-RSI-MACD-Vlme-IVHV-IVBRR | 42 | **2** | >= | gate | 10 | NULL |
| 92-BS-RSI-MACD-Vlme-IVHV-IVBRR | 44 | 0 | >= | gate | 10 | NULL |
| 92-BS-RSI-MACD-Vlme-IVHV-IVBRR | 112 | 0 | >= | gate | 10 | NULL |
| 93-BW-LRRabvTD | 5 | 1 | >= | gate | 10 | NULL |
| 93-BW-LRRabvTD | 12 | 0 | >= | gate | 10 | NULL |
| 93-BW-LRRabvTD | 15 | **2** | >= | gate | 10 | NULL |
| 93-BW-LRRabvTD | 112 | 0 | >= | gate | 10 | NULL |

---

## Q3 — Leaf vs BASE per-atom diff table

### 92-BS-RSI-MACD-Vlme-IVHV-IVBRR (BASE-Vol-Regime absorbs [42,44], nested as gate)

| atom | leaf thr/op/role/wt | BASE thr/op/role/wt | Verdict |
|---|---|---|---|
| 42 | 2 / >= / gate / **10** | **3** / >= / gate / NULL | **DIFF** — thr 2→3 (stricter in BASE); wt 10→NULL |
| 44 | 0 / >= / gate / **10** | 0 / >= / gate / NULL | DIFF — wt only (10→NULL) |

### 93-BW-LRRabvTD (BASE-Bull-Trend absorbs [5,12,15], nested as gate)

| atom | leaf thr/op/role/wt | BASE thr/op/role/wt | Verdict |
|---|---|---|---|
| 5 | 1 / >= / gate / **10** | 1 / >= / gate / NULL | DIFF — wt only |
| 12 | 0 / >= / gate / **10** | 0 / >= / gate / NULL | DIFF — wt only |
| 15 | **2** / >= / gate / **10** | **2** / >= / gate / NULL | DIFF — wt only (thr matches) |

### 449-B-TN-TD-LRR-UP-MACD (BASE-Bull-Context absorbs [58,60,112] as gate; BASE-Vol-Regime absorbs [42,44] as watch)

| atom | leaf thr/op/role/wt | BASE thr/op/role/wt | Verdict |
|---|---|---|---|
| 58 | 0 / >= / gate / **10** | 0 / >= / gate / NULL | DIFF — wt only |
| 60 | 3 / >= / gate / **10** | 3 / >= / gate / NULL | DIFF — wt only |
| 112 | 0 / >= / gate / **10** | 0 / >= / gate / NULL | DIFF — wt only |
| 42 | 3 / >= / **watch** / **1** | 3 / >= / **gate** / NULL | **DIFF** — role watch→gate inside BASE; nested BASE member is watch |
| 44 | 0 / >= / **watch** / **1** | 0 / >= / **gate** / NULL | **DIFF** — role watch→gate inside BASE; nested BASE member is watch |

### 299-BS-BB-Streak-HiHi-TN-TD (BASE-Bear-Context absorbs [47,81,112] as watch; BASE-Bull-Trend absorbs [5,12,15] as gate; BASE-Vol-Regime absorbs [42,44] as watch)

| atom | leaf thr/op/role/wt | BASE thr/op/role/wt | Verdict |
|---|---|---|---|
| 47 | -2 / **>=** / gate / 10 | -2 / **<=** / gate / NULL | **DIFF** — **OPERATOR INVERTED** (>= in leaf, <= in BASE) |
| 81 | -2 / **>=** / **watch** / 1 | -2 / **<=** / **gate** / NULL | **DIFF** — operator inverted + role watch→gate inside BASE |
| 112 | 0 / **>=** / gate / 10 | **-2** / **<=** / gate / NULL | **DIFF** — thr 0≠-2 AND operator inverted; totally different condition |
| 5 | 1 / >= / gate / 10 | 1 / >= / gate / NULL | DIFF — wt only |
| 12 | 0 / >= / gate / 10 | 0 / >= / gate / NULL | DIFF — wt only |
| 15 | **3** / >= / gate / 10 | **2** / >= / gate / NULL | **DIFF** — thr 3→2 (leaf stricter); wt 10→NULL |
| 42 | 3 / >= / **watch** / 1 | 3 / >= / **gate** / NULL | DIFF — role watch→gate inside BASE |
| 44 | 0 / >= / **watch** / 1 | 0 / >= / **gate** / NULL | DIFF — role watch→gate inside BASE |

### 198-BS-TN-LRR-UP-MACD (BASE-Bull-Context absorbs [58,60,112] as gate; BASE-Vol-Regime absorbs [42,44] as watch)

| atom | leaf thr/op/role/wt | BASE thr/op/role/wt | Verdict |
|---|---|---|---|
| 58 | 0 / >= / gate / 10 | 0 / >= / gate / NULL | DIFF — wt only |
| 60 | 3 / >= / gate / 10 | 3 / >= / gate / NULL | DIFF — wt only |
| 112 | 0 / >= / gate / 10 | 0 / >= / gate / NULL | DIFF — wt only |
| 42 | 3 / >= / **watch** / 1 | 3 / >= / **gate** / NULL | **DIFF** — role watch→gate inside BASE; nested BASE member is watch |
| 44 | 0 / >= / **watch** / 1 | 0 / >= / **gate** / NULL | **DIFF** — role watch→gate inside BASE |

---

## Q4 — Nested BASE role in each leaf and evidence_cutoff

All BASE composites have `evidence_cutoff = NULL`.

| Leaf | Nested BASE | Role given to nested member | How role was chosen |
|---|---|---|---|
| 92-BS-RSI-MACD-Vlme-IVHV-IVBRR | BASE-Vol-Regime | **gate** | All absorbed atoms (42,44) were gate in leaf |
| 93-BW-LRRabvTD | BASE-Bull-Trend | **gate** | All absorbed atoms (5,12,15) were gate in leaf |
| 449-B-TN-TD-LRR-UP-MACD | BASE-Bull-Context | **gate** | All of (58,60,112) were gate in leaf |
| 449-B-TN-TD-LRR-UP-MACD | BASE-Vol-Regime | **watch** | Atoms (42,44) were both watch in leaf → not all-gate → watch |
| 299-BS-BB-Streak-HiHi-TN-TD | BASE-Bear-Context | **watch** | Atoms (47,81,112): atom 81 was watch → not all-gate → watch |
| 299-BS-BB-Streak-HiHi-TN-TD | BASE-Bull-Trend | **gate** | All of (5,12,15) were gate in leaf |
| 299-BS-BB-Streak-HiHi-TN-TD | BASE-Vol-Regime | **watch** | Atoms (42,44) both watch → watch |
| 198-BS-TN-LRR-UP-MACD | BASE-Bull-Context | **gate** | All of (58,60,112) were gate in leaf |
| 198-BS-TN-LRR-UP-MACD | BASE-Vol-Regime | **watch** | Atoms (42,44) both watch → watch |

---

## Verdict

Three distinct causes drive the firing changes. Listed in order of impact:

### Cause (c) — DOMINANT: AND→OR algebra bug in `derive_stks` nested composite evaluation

**This is the primary cause of the large increases (+634, +380, +116, +111).**

`_derive_stks_impl` stores `composite_scores[code] = float(score)` where `score = sum of ALL member weights` — this is non-zero if ANY member contributes, even when the composite did **not** fire (i.e., when a gate failed). When a parent leaf evaluates a `composite`-kind member, it uses `w = composite_scores.get(child)`. The gate-pass check is `hit = (w != 0)`. So the leaf's gate for the nested BASE passes whenever **any** BASE member scored — regardless of whether the BASE actually triggered (all its own gates passed).

**Concrete example (92-BS):** BASE-Vol-Regime has gate(42, thr=3) and gate(44, thr=0). If atom 44 scores 5 but atom 42 scores 0 (fails gate), BASE's score = 0 + 5 = 5, triggered = False. But `composite_scores['BASE-Vol-Regime'] = 5.0`, so the leaf sees `w = 5.0` → gate passes → leaf fires. Before the refactor, both gates 42 AND 44 had to pass independently. After nesting, either passing is enough.

**Fix:** in the `composite` kind branch, gate on the triggered flag:
```python
w = child_score if composite_results.get(child, False) else 0.0
```

### Cause (a) — SEED BUG: operator inversions and threshold mismatches

**Worst in composite 299-BS-BB-Streak-HiHi-TN-TD.** This leaf uses atoms 47, 81, 112 with op=`>=` (the leaf treats them as bullish/positive-direction conditions). BASE-Bear-Context defines the same atoms with op=`<=` (bearish/negative-direction). The refactor matches purely by `atomic_rule_id`, not by semantic direction — so it absorbs atoms where the BASE condition is the **opposite polarity** of the leaf's intent. Even if the algebra bug were fixed, these operator inversions would cause massive firing changes.

Also: atom 42 in leaf 92 has thr=2; BASE-Vol-Regime uses thr=3. Atom 15 in leaf 299 has thr=3; BASE-Bull-Trend uses thr=2. These threshold mismatches would remain after the bug fix.

### Cause (b) — SEED BUG: role mismatch (watch in leaf → gate inside BASE)

Atoms 42 and 44 are `watch` members in leaves 198, 299, 449 (with weight_override=1, meaning they contribute corroborating evidence rather than hard gates). Inside BASE-Vol-Regime they are defined as `gate` members. The refactor sets the nested BASE member's role to `watch` (since the absorbed atoms were all-watch), which partially compensates at the leaf level. But the BASE internally evaluates them as gates, so BASE fires only when BOTH pass — while the originals independently contributed watch score regardless of the other's result. This changes the watch evidence arithmetic.

---

## Summary table

| Worst offender | Firing change | Primary cause | Fixable to score-neutral? |
|---|---|---|---|
| 92-BS-RSI-MACD-Vlme-IVHV-IVBRR | 135→769 (+634) | (c) AND→OR bug | Yes, with derive_stks fix + thr correction on atom 42 |
| 93-BW-LRRabvTD | 69→449 (+380) | (c) AND→OR bug | Yes, with derive_stks fix (thr/op all match) |
| 449-B-TN-TD-LRR-UP-MACD | 4→120 (+116) | (c) AND→OR bug | Yes, with derive_stks fix (thr/op match for Bull-Context; watch role handled) |
| 299-BS-BB-Streak-HiHi-TN-TD | 4→115 (+111) | (a) operator inversion AND (c) bug | Requires both derive_stks fix AND redesigning how Bear-Context is matched |
| 198-BS-TN-LRR-UP-MACD | 3→12 (+9) | (c) AND→OR bug | Yes, with derive_stks fix |

---

## Recommended fixes (in priority order)

1. **Fix `derive_stks` nested composite weight** (fixes all 5, eliminates ~90% of the delta):
   In `_derive_stks_impl`, change the `composite` kind branch from:
   ```python
   w = float(mult) * child_score if mult is not None else child_score
   ```
   to:
   ```python
   if composite_results.get(child, False):
       w = float(mult) * child_score if mult is not None else child_score
   else:
       w = 0.0
   ```

2. **Fix `refactor_base_rules._plan_leaf`** to verify that each candidate atom's `(threshold, condition_operator)` in the leaf MATCHES the BASE's values before absorbing it — reject the match (don't absorb) if they differ.

3. **Fix BASE-Bear-Context seed** — the composites it would absorb into (299 etc.) use those atoms with `>=` (bullish direction). BASE-Bear-Context is inappropriate for those leaves; the refactor tool should detect this via cause (2) above.

DONE
