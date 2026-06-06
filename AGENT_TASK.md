# AGENT TASK 22 — Phase 4 step 1: is there enough outcome data to tune on? (read-only)

**You (VS Code agent) have DB access.** READ-ONLY — change nothing. Write to
**`AGENT_RESULT_22.md`**. Heartbeat: append `⏳ HH:MM:SS — <step>` lines as you go.

The ML tuner (`etl/ml_tune_thresholds.py`) learns per-atomic-rule thresholds from
`drv_rule_outcome` (labels: `hit`, `fwd_5d_pct`, `fwd_20d_pct`) joined to
`drv_cat_atomic_input` (features). Default needs ≥50 samples per rule. Before we
run it, measure whether the data supports it.

## Q1 — overall volume + date range
```sql
SELECT COUNT(*) AS rows,
       MIN(as_of_date) AS first_date, MAX(as_of_date) AS last_date,
       COUNT(DISTINCT as_of_date) AS n_dates,
       COUNT(DISTINCT tos_symbol) AS n_symbols
FROM drv_rule_outcome;
```

## Q2 — label population (how many rows have usable labels)
```sql
SELECT rule_kind,
       COUNT(*) AS rows,
       COUNT(*) FILTER (WHERE hit IS NOT NULL)         AS has_hit,
       COUNT(*) FILTER (WHERE fwd_5d_pct IS NOT NULL)  AS has_fwd5,
       COUNT(*) FILTER (WHERE fwd_20d_pct IS NOT NULL) AS has_fwd20
FROM drv_rule_outcome
GROUP BY rule_kind ORDER BY rows DESC;
```

## Q3 — per-atomic-rule sample counts (the binding constraint: ≥50/rule)
Count usable (feature+label) samples per atomic rule, the way the tuner joins:
```sql
WITH feats AS (
  SELECT a.atomic_rule_id, a.rule_name, c.column_name AS col
  FROM ref_trig_atomic_rule a
  JOIN ref_ma_columns c ON c.excel_header = a.rule_name
       AND c.drv_cat_table = 'drv_cat_atomic_input'
  WHERE a.deprecated_at IS NULL
)
SELECT COUNT(*) AS atomic_rules_resolved,
       COUNT(*) FILTER (WHERE n >= 50)  AS rules_ge_50,
       COUNT(*) FILTER (WHERE n >= 100) AS rules_ge_100
FROM (
  SELECT ro.rule_id, COUNT(*) AS n
  FROM drv_rule_outcome ro
  WHERE ro.rule_kind='atomic' AND ro.fwd_20d_pct IS NOT NULL
  GROUP BY ro.rule_id
) c;
```
Also list the TOP 15 atomic rules by sample count (rule_id, n) so we see the best-covered rules:
```sql
SELECT ro.rule_id, COUNT(*) n
FROM drv_rule_outcome ro
WHERE ro.rule_kind='atomic' AND ro.fwd_20d_pct IS NOT NULL
GROUP BY ro.rule_id ORDER BY n DESC LIMIT 15;
```

## Q4 — how is the outcome table populated? (so we know if it'll grow)
Briefly: what writes `drv_rule_outcome` (grep etl/ for it — e.g. compute_outcomes.py),
and does `fwd_20d_pct` require 20 trading days to elapse (so only older dates have it)?
One or two sentences + the source file name.

## Verdict
State plainly:
1. Total outcome rows + date span (how many days of history).
2. How many atomic rules clear the ≥50-sample bar (and ≥100).
3. Is `fwd_20d_pct` populated, and for what fraction of dates?
4. Your read: is there enough to attempt a first ML tune now, or is the history too
   thin (and roughly how much more time/data would help)?

Write `DONE` at the bottom of `AGENT_RESULT_22.md`.
