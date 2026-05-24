# Phase 1 verification recipe

Steps to confirm each Phase 1 fix actually works on your Postgres + Excel data. Run from the project root with `.venv` activated.

Before anything else, apply the schema changes (new `ref_settings` rows):

```cmd
python -m db.init_db
```

That's idempotent and now preserves your audit/dedup history by default.

---

## #1 — Cockpit feedback path (resolve `ACTED`, score Actionable codes)

**What changed**
- `POST /api/actions` resolves `'ACTED'` → `drv_actionable.consolidated_action` (REMOVE / REDUCE / INCREASE / ADD / HOLD) before writing the row, and sets `user_action = 'DONE'` / `'SKIPPED'` for the audit trail.
- `compute_outcomes._determine_hit` now scores REMOVE/REDUCE as sell-direction and ADD/INCREASE as buy-direction. `ACTED` falls back to "did the symbol move meaningfully?" only if the upstream resolution couldn't find a recommendation.

**Verify**
1. In the app, open **Cockpit**, pick any symbol on a date that has an `drv_actionable` row, click **Took action**.
2. In psql:
   ```sql
   SELECT id, as_of_date, symbol, action_code, user_action, triggered_rules
   FROM user_action_log ORDER BY id DESC LIMIT 1;
   ```
   - `action_code` should be one of `REMOVE / REDUCE / INCREASE / ADD / HOLD` (not `'ACTED'`).
   - `user_action` should be `'DONE'`.
   - `triggered_rules` should be valid JSON, not Python `repr()` (look for `[{...}]`, not `[{'rule_id': ...}]` with single quotes).
3. Click **Skip** on another symbol and confirm `action_code='SKIP'`, `user_action='SKIPPED'`.
4. Wait 5+ trading days, then run `python -m etl.compute_outcomes`. Confirm:
   ```sql
   SELECT action_code, COUNT(*) FROM drv_rule_outcome
   GROUP BY action_code ORDER BY 1;
   ```
   You should see non-zero `hit=true` counts in REMOVE/ADD/etc., not just SKIP.

---

## #2 — Rules write-API (atomic-rule dry-run, type fix, dup detection)

**What changed**
- New `POST /api/rules/atomic/{id}/dryrun` — preview before-vs-after weight on a sample symbol, plus a count of how many symbols' fire-state would flip.
- `CompositeRuleCreateRequest.atomic_rule_ids` is now `list[int]` (was `list[str]`) — matches the `INTEGER` DB column.
- `POST /api/rules/composite` now returns **409** when the composite_rule_code already has any mapping rows (previously did `ON CONFLICT DO NOTHING` and silently no-op'd). It also validates each `atomic_rule_id` exists and isn't deprecated.

**Verify**
1. From the Rules page, edit an atomic rule and check the network panel for `/api/rules/atomic/{id}/dryrun` — or curl directly:
   ```cmd
   curl -X POST http://127.0.0.1:8000/api/rules/atomic/123/dryrun ^
     -H "Content-Type: application/json" ^
     -d "{\"brkeout_from\": 5, \"sample_symbol\": \"AAPL\"}"
   ```
   Expect `{before: {...}, after: {...}, affected_symbols_estimate: N, note: "..."}`.
2. Try POST `/api/rules/composite` with a `rule_code` that already exists — should now get HTTP 409 instead of a silent 201 with 0 rows written.
3. Try POST `/api/rules/composite` with an `atomic_rule_ids` containing a non-existent ID — should now get HTTP 400 listing the unknown id(s).

---

## #3 — precondition_expr (already implemented; aliases added)

**What changed**
The expression evaluator at `etl/derive.py::_eval_precondition` now exposes derived aliases so you can write more natural preconditions:
- `is_held` (truthy `held_today`)
- `is_etf` (sector or asset_class == 'ETF')
- `is_equity` (asset_class == 'Equity')
- `has_position` (`current_position_dollar` > 0)

**Verify**
1. On the Composite Editor for an existing composite, set `precondition_expr` to e.g. `is_equity and not is_held` and Save.
2. Re-derive for the latest date:
   ```cmd
   python -c "from etl.derive import derive_stks; from etl.db import session_scope; from datetime import date; import sys
   d = date.fromisoformat(sys.argv[1])
   with session_scope() as s: print(derive_stks(s, d, 0))" 2026-05-15
   ```
   (Replace the date with your latest snapshot_date.)
3. In psql, confirm the precondition gates apply:
   ```sql
   SELECT symbol, asset_class, held_today,
          (SELECT COUNT(*) FROM jsonb_array_elements(triggered_composite_ids)) AS n_fired
   FROM drv_stks
   WHERE as_of_date = '2026-05-15'
   ORDER BY symbol LIMIT 20;
   ```
   ETFs and currently-held names should show fewer fires on the gated composite.

---

## #4 — Unify rule scorer (drop legacy `_bucket_weight`)

**What changed**
- `_bucket_weight` (jump-only) has been removed. Both `_derive_stks_impl` and `_derive_trig_impl` already call `eval_atomic_rule`, which is the single source of truth for `jump | linear | sigmoid` scoring.

**Verify**
For any composite with at least one `scoring_mode != 'jump'` atomic, drv_trig and drv_stks must agree on the score:
```sql
WITH t AS (
  SELECT as_of_date, symbol, composite_rule_code, score
  FROM drv_trig WHERE as_of_date = '2026-05-15'
),
s AS (
  SELECT as_of_date, symbol,
         (c->>'rule_id')        AS composite_rule_code,
         (c->>'score')::numeric AS score
  FROM drv_stks,
       jsonb_array_elements(triggered_composite_ids) c
  WHERE as_of_date = '2026-05-15'
)
SELECT t.composite_rule_code, COUNT(*) AS mismatches
FROM t
JOIN s USING (as_of_date, symbol, composite_rule_code)
WHERE round(t.score, 4) <> round(s.score, 4)
GROUP BY 1 ORDER BY 2 DESC;
```
Should return zero rows.

---

## #5 — drv_dash thresholds + zone_signal

**What changed**
- `_derive_dash_impl` now reads `dash_threshold_low_pct` and `dash_threshold_high_pct` from `ref_settings` (defaults -10 / +10) and computes `zone_signal` from `pct_brr`:
  - `'Y'` (accumulate / below band) when `pct_brr ≤ threshold_low`
  - `'N'` (exit / above band) when `pct_brr ≥ threshold_high`
  - `'W'` (watch / between) otherwise
- Tune in `ref_settings` — no code change.

**Verify**
After `python -m db.init_db` (to seed the new rows), re-derive for any date and check:
```sql
SELECT zone_signal, COUNT(*),
       MIN(pct_brr) AS min_pct, MAX(pct_brr) AS max_pct
FROM drv_dash
WHERE as_of_date = '2026-05-15'
GROUP BY zone_signal ORDER BY 1;
```
Expect non-null `Y / N / W` rows where `pct_brr` is present, and the min/max ranges to respect the configured bands.

---

## #6 — init_db truncate gated (already shipped)

**What changed**
- `db/init_db.py` already gates the audit-table truncate behind `--reset-audit` and preserves dedup history by default. No code change needed for this Phase 1 item.

**Verify**
```cmd
python -m db.init_db
```
Output should end with `=== Audit tables preserved (use --reset-audit to clear) ===`. After this, `SELECT COUNT(*) FROM meta_file_processed` should still match what you had before.

---

## #7 — Nightly compute_outcomes

**What changed**
- `etl/scheduler.py` now ticks once a minute and, when the local hour is at or past `ref_settings.outcomes_compute_hour` (default 22) and today hasn't fired yet, runs `compute_outcomes(dry_run=False)`.
- State lives in `ETL_WORKING_DIR/scheduler_nightly_last.txt` (one date per line). Delete it to force a re-run.
- New CLI flag: `--no-nightly` disables the schedule (kept for one-off runs).

**Verify**
1. Restart the scheduler:
   ```cmd
   python -m etl.scheduler
   ```
   Look for the log line:
   ```
   nightly compute_outcomes scheduled (hour=22, state=...\scheduler_nightly_last.txt)
   ```
2. To test today without waiting until 22:00, temporarily lower the hour:
   ```sql
   UPDATE ref_settings SET setting_value = '0' WHERE setting_name = 'outcomes_compute_hour';
   ```
   Restart the scheduler. Within 60 seconds you should see:
   ```
   nightly: compute_outcomes starting
   nightly: compute_outcomes done: {'processed': N, 'errors': M}
   ```
3. Reset the hour:
   ```sql
   UPDATE ref_settings SET setting_value = '22' WHERE setting_name = 'outcomes_compute_hour';
   ```

---

## Smoke test — what to run after pulling these changes

```cmd
python -m db.init_db
python -c "from etl.derive import _eval_precondition; print(_eval_precondition('is_equity and not is_held', {'asset_class':'Equity','held_today':False}))"
:: expect: True
python -c "from etl.compute_outcomes import _determine_hit; print(_determine_hit('REDUCE', -1.0))"
:: expect: True
python -c "from etl.derive import eval_atomic_rule; print(eval_atomic_rule(7, {'brkeout_from':5,'brkeout_to':10,'wt_below':-1,'wt_between':1,'wt_above':2,'scoring_mode':'jump'}))"
:: expect: 1.0
```

If those three return the expected values, the fixes are wired correctly. Then re-run a normal load + derive cycle on your latest workbook and spot-check the Dashboard, Cockpit, and Rules pages.
