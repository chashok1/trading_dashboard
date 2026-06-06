# AGENT RESULT 24 — Phase 4 end-to-end: backfill → outcomes → scorecard → tune → backtest

**Date run:** 2026-06-06

⏳ — pre-flight: schema + code fixes

## Pre-flight — fixes applied before running

**drv_rule_outcome schema:** PK was `(as_of_date, tos_symbol)` — wrong for multi-rule-per-date data. Also `baseline.sql` still named the column `symbol`. Fixed:
- `db/baseline.sql`: `symbol` → `tos_symbol` in CREATE TABLE + PRIMARY KEY
- Applied via ALTER TABLE: new PK = `(rule_id, as_of_date, tos_symbol)`

**backfill_derives.py:** `NULL` params typed ambiguously with psycopg v3. Fixed:
- `:f IS NULL OR` → `CAST(:f AS date) IS NULL OR` (and same for `:t`)

**The "1-line fix" in compute_firing_outcomes.py + ml_tune_thresholds.py:**
Both scripts join `ref_trig_atomic_rule.rule_name` to `ref_ma_columns.excel_header` — but `rule_name` is snake_case (`current_volume_rule`) while `excel_header` is display-case (`Current Volume Rule`). Zero atomic rules were resolving.
- Fixed: `c.excel_header = a.rule_name` → `c.column_name = a.rule_name`
- After fix: 98 atomic rules resolve correctly

⏳ — Step 1: smoke-test backfill

## Step 1 — smoke-test backfill (2 dates)

```
python -m etl.backfill_derives --limit 2
```
Output: `[1/2] 2026-02-02  cat=882 stks=1048 trig=72312 actionable=1171`
        `[2/2] 2026-02-03  cat=882 stks=1049 trig=72381 actionable=1183`
        `Backfill done: 2/2 dates derived.` ✓

⏳ — Step 2: full backfill (~55 dates)

## Step 2 — full backfill

```
python -m etl.backfill_derives
```
Backfilling 55 missing dates: 2026-02-04 .. 2026-05-05

First 3:
```
[1/55] 2026-02-04  cat=882 stks=1049 trig=72381 actionable=1183
[2/55] 2026-02-05  cat=847 stks=1047 trig=72243 actionable=1183
[3/55] 2026-02-06  cat=847 stks=1047 trig=72243 actionable=1183
```
Last 3:
```
[53/55] 2026-04-30  cat=859 stks=1086 trig=74934 actionable=1184
[54/55] 2026-05-04  cat=859 stks=1091 trig=75279 actionable=1185
[55/55] 2026-05-05  cat=859 stks=1091 trig=75279 actionable=1183
Backfill done: 55/55 dates derived.
```

Coverage verification:
```
drv_trig: 83 dates, 2025-01-01 → 2026-06-05
```
(83 = 1 stub + 57 backfilled + 25 pre-existing) ✓

⏳ — Step 3: compute firing outcomes

## Step 3 — build firing outcomes

```
python -m etl.compute_firing_outcomes --truncate
```
```
drv_rule_outcome truncated
_fwd built: 53292 rows with a 20d forward return
composite outcomes upserted: 342294
atomic rules resolved to feature columns: 98
atomic outcomes upserted: 4891103 rows across 98 rules
drv_rule_outcome now has 5233397 rows
```

Verification query:
```
rule_kind   rows       dates  has_fwd20
atomic      4891103    62     4891103
composite   342294     62     342294
```
All 5.2M rows have fwd_20d_pct (62 dates with ≥20d forward data). ✓

⏳ — Step 4: rule performance scorecard

## Step 4 — rule performance scorecard

68 composite codes with ≥30 fires.

**TOP 3 by avg 20d forward return:**
| rule_id | fires | avg_fwd20 | win_rate |
|---|---|---|---|
| 893-SA-TRR-blw-TN | 4595 | +2.26% | 0.444 |
| 783-SW-Vol-Spke-Price-Dn-Past | 597 | +2.10% | 0.472 |
| 898-SA-Streak-VeryBad | 5983 | +1.95% | 0.423 |

**BOTTOM 3 by avg 20d forward return:**
| rule_id | fires | avg_fwd20 | win_rate |
|---|---|---|---|
| 92-BS-RSI-MACD-Vlme-IVHV-IVBRR | 7748 | -0.06% | 0.405 |
| 93-BW-LRRabvTD | 7254 | -0.41% | 0.400 |
| BASE-Bull-Trend | 11851 | -0.42% | 0.532 |

Note: SA/SS (alert/sell) codes topping the list means these fired before subsequent
price RISES in this period — suggests the window (Feb–May 2026) captured a bounce
from a market downturn. BUY codes (BS/BW) showing near-zero or negative suggests
the opposite. These results should be interpreted against market-regime context.

⏳ — Step 5: ML tune

## Step 5 — ML tune (inactive profile)

```
python -m etl.ml_tune_thresholds --method sweep --min-samples 100 --label-window 20
```
```
Resolved 98 atomic rules to feature columns. Method=sweep
=== Tuned 96 rules ===
  [5]  macdh_direction   {"brkeout_from": 1.0}
  [6]  macd_direction    {"brkeout_from": -1.0}
  [7]  bb_direction      {"brkeout_from": 1.0}
  [8]  bb_threshold      {"brkeout_from": 0.0}
  [9]  bbthresh_co_days  {"brkeout_from": 3.0}
  ...  (96 rules total)
Param set 3 written (INACTIVE).
```

Param sets:
```
id=1  Baseline 2026-06-05  manual    is_active=TRUE   ← production
id=2  Sigmoid v1           manual    is_active=FALSE
id=3  ml-sweep-20d         ml:sweep  is_active=FALSE  ← new
```
Baseline (id=1) still active. ✓

⏳ — Step 6: backtest ml vs Baseline, then revert

## Step 6 — backtest + revert

Baseline snapshot on 2026-06-05: **2,856 triggered rows** → stored in `_ml_base`.

Activated ml-sweep-20d (id=3), re-derived 2026-06-05:
```
drv_cat_atomic_input: 884  drv_stks: 1123  drv_trig: 77487  drv_actionable: 1204
```

Signal diff (ml vs Baseline on 2026-06-05):
```
ml_newly_fires  = 2848
ml_stops_firing =  417
```
The ML sweep profile shifts ~2,848 codes to fire that Baseline didn't (tighter thresholds on some rules) and drops 417. Large positive shift — sweep optimised `brkeout_from` toward minimum-value thresholds in many rules, favouring recall. The scorecard context (Feb–May downturn) makes these tuned thresholds suspect for current market conditions.

**Reverted to Baseline (id=1) + re-derived.**

```
compare_trigma.py:
Phase 1 (atomic) :  99.91% match  (77 mismatches, 792 symbols)
Phase 2 (composite): 99.89% match  (55 mismatches, 792 symbols)
```
Baseline fully restored. ✓

## Step 7 — verdict

**(a) Backfill:** 55+2 = 57 historical dates derived (2026-02-02 → 2026-05-05), plus the 25 pre-existing (2026-05-06 → 2026-06-05). 83 total in drv_trig.

**(b) Outcome rows:** composite=342,294 / atomic=4,891,103 across 98 rules / total=5,233,397. All 62 eligible dates have fwd_20d_pct labels.

**(c) Top 3 composite codes by avg_fwd20:** 893-SA-TRR-blw-TN (+2.26%), 783-SW-Vol-Spke-Price-Dn-Past (+2.10%), 898-SA-Streak-VeryBad (+1.95%). Bottom 3: 92-BS-RSI-MACD-Vlme-IVHV-IVBRR (-0.06%), 93-BW-LRRabvTD (-0.41%), BASE-Bull-Trend (-0.42%).

**(d) ML profile:** param_set_id=3, label=`ml-sweep-20d`, 96 rules tuned, is_active=FALSE. Written INACTIVE — not in production.

**(e) Signal shift on 6/5:** +2,848 newly fire / -417 stop firing under ML sweep vs Baseline. Large positive shift driven by sweep lowering many `brkeout_from` thresholds; suspect until validated against a wider market-regime window.

**(f) Baseline restored:** Baseline (id=1) is_active=TRUE. Phase 1=99.91%, Phase 2=99.89% confirmed.

DONE
