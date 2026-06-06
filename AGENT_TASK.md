# AGENT TASK 06 — verify drv_trig double-eval fix (697 over-firing)

**You (VS Code agent) have DB access.** Run in a **fresh process** (not the
running app). Write output to a NEW file **`AGENT_RESULT_06.md`**.

## What changed (code already edited)
`etl/derive.py::_derive_trig_impl` was re-applying `eval_atomic_rule()` to values
that are ALREADY pre-evaluated atomic weights in `drv_cat_atomic_input`. That
double-evaluated earnings (atomic 1 → re-eval 1<5 → -3), so the 697 gate
`atomic <= -3` passed for every non-null earnings → 564 false fires.
Fix: pass the value through directly (None preserved), mirroring
`_derive_stks_impl`. No more second `eval_atomic_rule` call.

## Step 1 — re-derive 2026-06-04 (fresh process)
```
python agent_rederive_all.py
```
Paste the counts.

## Step 2 — confirm 697 now fires ONLY for imminent earnings
```sql
SELECT a.tos_symbol, a.earnings AS atomic_earnings,
       t.triggered AS db_697_fired, t.score
FROM drv_cat_atomic_input a
JOIN drv_trig t
     ON t.tos_symbol = a.tos_symbol AND t.as_of_date = a.as_of_date
    AND t.composite_rule_code = '697-STM-Earnings-Date'
WHERE a.as_of_date = '2026-06-04'
  AND a.tos_symbol IN ('AAPL','AAL','NVDA','CRM','MSFT','ASO','ORCL','DOCU')
ORDER BY a.earnings, a.tos_symbol;
```
Expected: `db_697_fired = True` ONLY where `atomic_earnings = -3` (ASO, ORCL,
DOCU…); False for AAPL/NVDA/etc (atomic = 1).

## Step 3 — full regression compare
```
python compare_trigma.py > trigma_report.txt 2>&1
```
Paste the final summary (Phase 1 atomic %, Phase 2 composite %) and the top-10
composite mismatch table.

I expect Phase 2 to jump (697's 564 should mostly clear) and Phase 1 unchanged.
Flag any composite whose mismatch count went UP versus the prior run (697=564,
93-BW-LRRabvTD=86, 99-BS-Min=70, 186-BR-Trend-CO=61, 791=60, 395=52, 397=52,
279=48, 94-BW-UP-MACD=46, 396=32) — that would mean the pass-through change
regressed another composite and we need to look.

Write `DONE` at the bottom of `AGENT_RESULT_06.md`.
