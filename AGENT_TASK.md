# AGENT TASK 09 — PRMB: do Excel-fired and DB-fired match?

**You (VS Code agent) have DB access.** Write output to **`AGENT_RESULT_09.md`**.
Compare date = 2026-06-05 (current anchor; matches the fresh TrigMA.xlsx).

## Step 1 — per-composite fired comparison for PRMB
Using the same logic compare_trigma.py uses (Excel deficit < 10 = fired; DB =
drv_trig.triggered), list EVERY composite for PRMB where they DISAGREE, and also
report the totals. Easiest path: add a one-off symbol filter in compare_trigma.py
(or replicate its Phase-2 join) and print, for PRMB:

```
composite_rule_code | excel_deficit | excel_fired | db_triggered | db_score | match?
```
List all disagreements; then give the count of composites that match vs mismatch.

## Step 2 — PRMB atomic values (to explain any disagreement)
```sql
SELECT * FROM drv_cat_atomic_input
WHERE tos_symbol = 'PRMB' AND as_of_date = '2026-06-05';
```
Paste the row (or at least the non-null atomic columns). I mainly want the
atomic columns involved in any mismatched composite.

## Step 3 — does PRMB have full source data?
```sql
SELECT 'hist_td' t, COUNT(*) n FROM hist_td WHERE tos_symbol='PRMB' AND export_date='2026-06-05'
UNION ALL SELECT 'hist_tl', COUNT(*) FROM hist_tl WHERE tos_symbol='PRMB' AND export_date='2026-06-05'
UNION ALL SELECT 'hist_tw', COUNT(*) FROM hist_tw WHERE tos_symbol='PRMB' AND snapshot_date<='2026-06-05' AND snapshot_date>='2026-06-05'::date-14
UNION ALL SELECT 'drv_quote', COUNT(*) FROM drv_quote WHERE tos_symbol='PRMB' AND as_of_date='2026-06-05';
```
Paste it. Also note PRMB's td_high / td_low (for the crossover gap):
```sql
SELECT td_high, td_low, a_trend_value, a_trade_value, lrr, trr
FROM drv_cat_atomic_input WHERE tos_symbol='PRMB' AND as_of_date='2026-06-05';
```

## Step 4 — verdict
State plainly: for PRMB, do Excel-fired and DB-fired MATCH across all composites?
If not, list the mismatching composites and your best one-line cause for each
(e.g. "trend_cross_over NULL because td_high/td_low missing").

Write `DONE` at the bottom of `AGENT_RESULT_09.md`.
