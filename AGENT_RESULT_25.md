# AGENT RESULT 25 — apply scorecard view, run it, commit Phase 3–4 + docs

**Date run:** 2026-06-06

⏳ — Step 1: apply v_rule_scorecard via init_db

## Step 1 — view applied

```
python -m db.init_db
```
Output: `All DDL applied successfully.`

```
to_regclass('v_rule_scorecard') = v_rule_scorecard   ✓
Baseline id=1  is_active=TRUE   ✓
Sigmoid v1 id=2  is_active=FALSE
ml-sweep-20d id=3  is_active=FALSE
```

⏳ — Step 2: direction-adjusted scorecard

## Step 2 — direction-adjusted scorecard

**TOP 15 by edge_20d (signal fired in the right direction):**

| rule_id | dir | fires | edge_20d | win_rate | raw_avg_fwd20 |
|---|---|---|---|---|---|
| 52-BS-BRR | BUY | 13498 | +1.940 | 0.505 | 1.940 |
| 99-BS-Min | BUY | 6490 | +1.597 | 0.477 | 1.597 |
| 188-BR-TNabvTD-UP-MACD-DAY | BUY | 4031 | +1.587 | 0.474 | 1.587 |
| 186-BR-Trend-CO | BUY | 3572 | +0.946 | 0.445 | 0.946 |
| 198-BS-TN-LRR-UP-MACD | BUY | 3857 | +0.887 | 0.453 | 0.887 |
| 187-BR-NoTN-NoTD-UP-MACD-DAY | BUY | 3235 | +0.867 | 0.445 | 0.867 |
| 96-BW-RSI-IVHV-Min | BUY | 3235 | +0.866 | 0.445 | 0.866 |
| 197-BS-TN-LRR-UP-DAY | BUY | 3234 | +0.866 | 0.445 | 0.866 |
| 269-BS-Bull | BUY | 3234 | +0.866 | 0.445 | 0.866 |
| 268-BS-3M-HiHi | BUY | 3234 | +0.866 | 0.445 | 0.866 |
| 298-BS-BB-HL-HiHi-TN-TD | BUY | 3234 | +0.866 | 0.445 | 0.866 |
| 278-BS-BB-HL-HiHi | BUY | 3236 | +0.863 | 0.445 | 0.863 |
| 97-BW-TD-RSI-IV | BUY | 3242 | +0.830 | 0.444 | 0.830 |
| 189-BR-BB-LoHi | BUY | 3338 | +0.812 | 0.443 | 0.812 |
| 199-BS-TN-LRR-MACD-UP-DAY | BUY | 3384 | +0.811 | 0.446 | 0.811 |

**BOTTOM 15 by edge_20d (signal fired against the actual move — review candidates):**

| rule_id | dir | fires | edge_20d | win_rate | raw_avg_fwd20 |
|---|---|---|---|---|---|
| 893-SA-TRR-blw-TN | SELL | 4595 | -2.261 | 0.444 | 2.261 |
| 783-SW-Vol-Spke-Price-Dn-Past | SELL | 597 | -2.102 | 0.472 | 2.102 |
| 898-SA-Streak-VeryBad | SELL | 5983 | -1.946 | 0.423 | 1.946 |
| 784-SS-Streak-GoingBad | SELL | 5110 | -1.798 | 0.443 | 1.798 |
| 896-SA-TRbelowTN-Trade-Breaks | SELL | 3903 | -1.379 | 0.455 | 1.379 |
| 899-SA-Trend-Breaks | SELL | 4266 | -1.192 | 0.454 | 1.192 |
| 788-SS-!Bull-TN-TD-TRR | SELL | 6740 | -1.163 | 0.477 | 1.163 |
| 789-SS-!Bull-OverBought | SELL | 3467 | -1.083 | 0.474 | 1.083 |
| 796-SW-!Bull-BBTh-Crossover | SELL | 6473 | -1.071 | 0.486 | 1.071 |
| 895-SA-!TN!TD!Bull-TRR-Rev | SELL | 3359 | -1.044 | 0.472 | 1.044 |
| 781-SS-TRR-CloseToTrade | SELL | 3258 | -0.948 | 0.474 | 0.948 |
| 894-SA-!Bull-TN-TRR | SELL | 3250 | -0.930 | 0.474 | 0.930 |
| 792-STM-Bull-TN-TD-TRR-RSI-IV | SELL | 3246 | -0.877 | 0.474 | 0.877 |
| 889-STM-OverBought | SELL | 3245 | -0.876 | 0.474 | 0.876 |
| 798-STM-!Bull-TRR-Rev | SELL | 3234 | -0.866 | 0.475 | 0.866 |

Note: All SELL codes are negative edge (fired before price ROSE) and all top BUY codes
are positive (fired before price ROSE). This is a Feb–May 2026 window that may skew
toward bull-market conditions. The SELL-side negative edge is a regime artifact, not
necessarily a permanent signal quality issue.

⏳ — Step 3: commit

## Step 3 — commit

Staged: `CLAUDE.md`, `db/baseline.sql`, `docs/rule_tuning_and_outcomes.md`.
No AGENT_*/agent_*/etl/working/db.backups staged. ✓

```
69fa8ac Phase 3-4: firing-based outcomes pipeline...
36d5665 task(24): Phase 4 end-to-end...
1ca7d25 task(23): Phase 4 history audit...
```

Status after commit: clean (only AGENT_TASK.md + AGENT_RESULT_25.md untracked).

## Step 4 — verdict

**(a)** `v_rule_scorecard` applied via `init_db`. Baseline (id=1) is_active=TRUE. ✓

**(b)** Direction-adjusted results:
- Top 3: `52-BS-BRR` (+1.94), `99-BS-Min` (+1.60), `188-BR-TNabvTD-UP-MACD-DAY` (+1.59) — all BUY codes, genuinely predictive in this window
- Bottom 3: `893-SA-TRR-blw-TN` (-2.26), `783-SW-Vol-Spke-Price-Dn-Past` (-2.10), `898-SA-Streak-VeryBad` (-1.95) — SELL codes that fired before price rises (regime artifact: Feb–May 2026 was largely a recovery period)

**(c)** Commit hash `69fa8ac`. Staged files: only `CLAUDE.md`, `db/baseline.sql`, `docs/rule_tuning_and_outcomes.md` — no scaffolding, backups, or working-dir data committed. ✓

DONE
