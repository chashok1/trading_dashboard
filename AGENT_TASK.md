# AGENT TASK 24 — Phase 4 end-to-end (backfill → outcomes → scorecard → tune → backtest)

**You (VS Code agent) have DB + Windows git.** Write to **`AGENT_RESULT_24.md`**.
**HEARTBEAT:** before each step and each long command, append
`⏳ HH:MM:SS — <step>`. Long steps (backfill, atomic outcomes) log per-item — paste
periodic progress. Write `DONE` only at the very end.

This is additive and safe: it derives MISSING historical dates, fills a new
outcomes table, and writes a NEW inactive `ml:` profile. It NEVER edits your rules
or the Baseline profile (id=1), which stays the active production profile. Two new
scripts back this: `etl/backfill_derives.py`, `etl/compute_firing_outcomes.py`
(plus a 1-line fix in `etl/ml_tune_thresholds.py`). If ANY step errors, STOP and
paste the full traceback.

## Step 1 — smoke-test the backfill (2 dates)
```
python -m etl.backfill_derives --limit 2
```
Paste output. Confirm it derived 2 dates without error. If it errors, STOP.

## Step 2 — full backfill of all missing dates (LONG — ~50 dates)
```
python -m etl.backfill_derives
```
This loops `derive_all` over every hist_td date missing from drv_trig (Feb–May).
Paste the first few and last few per-date lines + the final "Backfill done: N/N".
Then confirm coverage:
```sql
SELECT COUNT(DISTINCT as_of_date) AS derived_dates,
       MIN(as_of_date) lo, MAX(as_of_date) hi FROM drv_trig;
```
Expect ~79 dates, 2026-02-02 → 2026-06-05.

## Step 3 — build firing outcomes
```
python -m etl.compute_firing_outcomes --truncate
```
Paste the log (composite + atomic upsert counts, final row count). Then:
```sql
SELECT rule_kind, COUNT(*) rows, COUNT(DISTINCT as_of_date) dates,
       COUNT(*) FILTER (WHERE fwd_20d_pct IS NOT NULL) has_fwd20
FROM drv_rule_outcome GROUP BY rule_kind;
```

## Step 4 — RULE PERFORMANCE SCORECARD (the key deliverable)
For composite rules, how did firings actually perform forward? Paste both:
```sql
-- best & worst composites by mean 20d forward return (min 30 fires)
SELECT rule_id, COUNT(*) fires, ROUND(AVG(fwd_20d_pct)::numeric,2) avg_fwd20,
       ROUND(AVG(hit::int)::numeric,3) win_rate
FROM drv_rule_outcome WHERE rule_kind='composite' AND fwd_20d_pct IS NOT NULL
GROUP BY rule_id HAVING COUNT(*) >= 30
ORDER BY avg_fwd20 DESC;
```
(Top of the list = rules whose firings preceded the best moves; bottom = rules that
fired before poor/adverse moves — candidates to review. Note: BUY codes want high
avg_fwd20, SELL codes want low/negative.)

## Step 5 — ML tune (exploratory; writes INACTIVE profile)
```
python -m etl.ml_tune_thresholds --method sweep --min-samples 100 --label-window 20
```
Paste: how many rules tuned + 5 example (rule, new brkeout_from). Confirm it printed
"INACTIVE" and did NOT activate. Verify:
```sql
SELECT param_set_id, label, provenance, is_active FROM ref_trig_param_set ORDER BY 1;
```
Baseline (id=1) must still be is_active=TRUE; the new ml set is_active=FALSE.

## Step 6 — backtest the ml profile vs Baseline (reversible), then revert
Snapshot Baseline firing on 2026-06-05, activate ml set, re-derive, diff, REVERT.
```sql
DROP TABLE IF EXISTS _ml_base;
CREATE TABLE _ml_base AS
SELECT composite_rule_code code, tos_symbol FROM drv_trig
WHERE as_of_date='2026-06-05' AND triggered=TRUE;
-- activate ml set (two-step: clear then set, to satisfy one-active constraint)
UPDATE ref_trig_param_set SET is_active=FALSE;
UPDATE ref_trig_param_set SET is_active=TRUE WHERE provenance LIKE 'ml:%';
```
```
python agent_rederive_all.py
```
```sql
SELECT
 (SELECT COUNT(*) FROM drv_trig t WHERE as_of_date='2026-06-05' AND triggered
    AND (composite_rule_code,tos_symbol) NOT IN (SELECT code,tos_symbol FROM _ml_base)) AS ml_newly_fires,
 (SELECT COUNT(*) FROM _ml_base b WHERE (b.code,b.tos_symbol) NOT IN
    (SELECT composite_rule_code,tos_symbol FROM drv_trig WHERE as_of_date='2026-06-05' AND triggered)) AS ml_stops_firing;
```
Paste the two counts (how much the tuned profile shifts signals vs Baseline).
**Then REVERT to Baseline and re-derive so production is unchanged:**
```sql
UPDATE ref_trig_param_set SET is_active=FALSE;
UPDATE ref_trig_param_set SET is_active=TRUE WHERE param_set_id=1;
```
```
python agent_rederive_all.py
python compare_trigma.py
```
Confirm Baseline restored: Phase 1 ~99.91%, Phase 2 ~99.89%.

## Step 7 — verdict
State: (a) backfill date count; (b) outcome row counts (composite/atomic);
(c) top 3 and bottom 3 composites by avg_fwd20 from the scorecard; (d) ml profile
id + #rules tuned + that it's INACTIVE; (e) how many signals the ml profile shifts
on 6/5; (f) Baseline restored as active (99.91/99.89). 

Write `DONE` at the bottom of `AGENT_RESULT_24.md`.
