# Phase 2 + 3 verification recipe

Run these after `python -m db.init_db` to confirm each Phase 2 / 3 fix is wired correctly. Same conventions as `PHASE1_VERIFICATION.md` — code-only changes, you verify against your real Postgres + workbook.

---

## #8 — Outlook-change detection (banner + API + SQL function)

**What changed**
- New SQL function `v_outlook_changes(date)` rolls up `drv_outlook_action` per-symbol with `dominant_action` (REMOVE > REDUCE > ADD > INCREASE).
- New endpoint `GET /api/outlook/changes?date=&held_only=&limit=`.
- New Dashboard banner (`#outlookBar`) that shows the count + top 10 chips, with click-through to Trace.

**Verify**
1. ```sql
   SELECT * FROM v_outlook_changes(CURRENT_DATE) LIMIT 5;
   ```
   Should return one row per symbol with at least one non-HOLD action today.
2. `curl http://127.0.0.1:8000/api/outlook/changes?limit=5` returns JSON with `dominant_action`.
3. Open Dashboard. If any symbols flipped today you should see a yellow banner like *"7 outlook flips today: 3 REMOVE 2 ADD …"* with chips. Held symbols are marked ★.

---

## #9 — Rule-groups drive `drv_actionable`

**What changed**
- New JSONB column `drv_actionable.triggered_group_ids` (added via `ALTER TABLE IF NOT EXISTS`).
- `_derive_actionable_impl` now evaluates every `group_type='action'` rule group against each symbol's fired composites and folds the result into the action competition. Group action+priority compete with outlook-source action+priority — *lowest priority wins* on tie.

**Verify**
1. ```cmd
   python -m db.init_db
   ```
2. Create a test action group (e.g. on the Groups page): one group named `TEST-SELL` with `group_type='action'`, `action_label='REMOVE'`, `priority=1`, members = one composite you know fires for at least one symbol.
3. Re-derive `drv_actionable` for that date:
   ```sql
   SELECT symbol, consolidated_action, winning_source, triggered_group_ids
   FROM drv_actionable
   WHERE as_of_date = '2026-05-15'
     AND triggered_group_ids IS NOT NULL
   LIMIT 10;
   ```
   You should see `winning_source = 'RULES:TEST-SELL'` for the symbols where the group fired, with the group action overriding any weaker outlook signal.

---

## #10 — Trace shows outlook diff + attribution

**What changed**
- `GET /api/trace/{sym}` response now includes `outlook` (per-source change rows + `changed` boolean + `n_sources_changed`) and `actionable` (the consolidated decision for that symbol).
- `web/trace.js` renders a new "Outlook attribution" section above the composites grid.

**Verify**
1. Open `/trace?symbol=AAPL` (or any symbol that has rows in `drv_outlook_action`).
2. Look for the new section labeled *Outlook attribution*. It should show:
   - A yellow chip *"N source(s) flipped outlook today"* (or grey *"No outlook changes today"*).
   - The current consolidated action with the winning source.
   - A table of per-source rows with prev_wt → curr_wt → Δ + reason.
3. API check:
   ```cmd
   curl http://127.0.0.1:8000/api/trace/AAPL | python -m json.tool | head -50
   ```
   Look for the `"outlook"` and `"actionable"` keys.

---

## #11 — Position-aware suppression

**What changed**
- `_derive_actionable_impl` now suppresses (sets `suppressed_reason`) on four edge cases:
  - REMOVE for non-held → `"NOT HELD — nothing to remove"`
  - ADD when already at/above category floor → `"ALREADY ESTABLISHED — held $X ≥ floor $Y"`
  - INCREASE when at/above ceiling → `"AT CEILING — held $X ≥ max $Y"`
  - REDUCE when at/below floor (with maintain_min) → `"AT FLOOR — held $X ≤ min $Y"`
- The action stays in `consolidated_action`; only `suppressed_reason` is populated, so the Actionable page can grey out / mark these.

**Verify**
After re-deriving `drv_actionable`:
```sql
SELECT consolidated_action, suppressed_reason, COUNT(*)
FROM drv_actionable
WHERE as_of_date = CURRENT_DATE - INTERVAL '1 day'
  AND suppressed_reason IS NOT NULL
GROUP BY 1, 2 ORDER BY 1;
```
Should show non-zero counts in NOT HELD / AT CEILING / etc. depending on your data.

---

## #12 — Performance window selector

**What changed**
- New SQL function `v_rule_performance_window(window_days, from_date, to_date)` — adds `median_fwd_5d` / `median_fwd_20d` and accepts explicit date bounds.
- `GET /api/rules/performance` now accepts `?window=N&from=YYYY-MM-DD&to=YYYY-MM-DD&min_n=K`.
- Old `v_rule_performance` view is kept for backward compat.

**Verify**
```cmd
curl "http://127.0.0.1:8000/api/rules/performance?window=20&min_n=5&sort_by=median_fwd_5d" | head
```
Response items should include `median_fwd_5d`, `median_fwd_20d`, `first_seen`, `last_seen`.

To use the explicit date bounds:
```cmd
curl "http://127.0.0.1:8000/api/rules/performance?from=2026-01-01&to=2026-03-31"
```

---

## #13 — Daily morning briefing

**What changed**
- New endpoint `GET /api/briefing?date=…` returns four blocks: `yesterday_actions`, `outlook_flips`, `allocation_drift`, `load_failures`.
- New card on the Dashboard (`#briefingCard`) shows only when there's something to report. Tiles flip red when there's an issue (drift / load fail).

**Verify**
1. ```cmd
   curl http://127.0.0.1:8000/api/briefing | python -m json.tool
   ```
   Confirm all four keys are present + a `warnings` array (empty unless one sub-query failed).
2. Open Dashboard. If you've logged any actions, have allocation drift, or any load_failures in the past 36 hours, the card appears under the outlook banner.

---

## #14 — Notifications

**What changed**
- New module `etl/notify.py` with a single public function `notify(title, msg, level)`.
- Two channels, both off unless `.env` enables them:
  ```
  NOTIFY_TOAST=1            # Windows toast (needs winotify or win10toast pkg)
  NOTIFY_EMAIL=1
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=you@gmail.com
  SMTP_PASSWORD=app_password
  NOTIFY_EMAIL_TO=alerts@example.com
  ```
- `etl/scheduler.py` calls `notify(...)` on (a) load errors and (b) nightly compute_outcomes completion / crash. All wrapped in try/except — a notification failure never crashes the scheduler.

**Verify**
1. Without enabling anything, the scheduler should run unchanged.
2. To smoke-test toast (if you have `winotify` installed): add `NOTIFY_TOAST=1` to `.env`, restart scheduler, drop a malformed `.xlsx` into a watched dir → expect a Windows toast.
3. To smoke-test from the REPL:
   ```cmd
   python -c "from etl.notify import notify; notify('Test', 'Hello', 'info')"
   ```

---

## #15 — Backtest harness

**What changed**
- New CLI `python -m etl.backtest [--rule-code X | --rule-id N] [--from … --to …] [--window 5 --window 20] [--threshold 0.5] [--json out.json]`.
- Replays rule fires from `drv_trig` / `drv_stks.triggered_atomic_ids`, computes forward returns from `drv_ma`, aggregates per rule: fire count, hit rate, avg / median forward return.
- Direction (bull/bear) is inferred from category text — heuristic, see `_direction_for_rule`. Override by editing the categorization.

**Verify**
```cmd
python -m etl.backtest --from 2026-01-01 --to 2026-05-15
```
Should print a table sorted by `hit5d` descending. Each row is one rule with fires, hit rates, avg returns.

For a single rule:
```cmd
python -m etl.backtest --rule-code BM-Momentum-Up --window 5 --window 20 --window 60
```

JSON output for programmatic consumers:
```cmd
python -m etl.backtest --rule-code BM-Momentum-Up --json bt_BM.json
```

---

## #16 — Health & observability

**What changed**
- `etl/cleanup.py` gained `--meta`, `--meta-only`, and `--retention-days` flags. `cleanup_meta_tables()` prunes `meta_etl_run`, `meta_derived_run`, `meta_cleanup_history` rows older than 90 days (default).
- Existing `hist_*` policy-driven cleanup is unchanged.

**Verify**
```cmd
python -m etl.cleanup --meta --dry-run
```
Should report how many rows in each meta_* table would be pruned. Then run for real:
```cmd
python -m etl.cleanup --meta-only
```

Recommended cadence: weekly. Add a Windows Task Scheduler entry, or just run it from the same nightly job as `compute_outcomes`.

---

## #17 — Minimal pytest suite

**What changed**
- `tests/conftest.py` adds two fixtures: `db_available` (boolean) and `db_session` (transactional, rolls back).
- Four new test files:
  - `tests/test_eval_atomic_rule.py` — scoring modes + edges (pure Python)
  - `tests/test_precondition_expr.py` — SQL synonyms + derived aliases + fails-open (pure Python)
  - `tests/test_determine_hit.py` — every action code branch (pure Python)
  - `tests/test_outlook_changes_view.py` — DB-dependent, skips automatically if no Postgres reachable

**Verify**
```cmd
pip install pytest
pytest tests/ -v
```
- Pure-Python tests run without any setup.
- `test_outlook_changes_view.py::test_dominant_action_priority` is the only DB-touching new test; skipped if no DB.
- Existing tests (`test_action_classifier.py`, `test_cat_parity.py`) should still pass.

---

## Combined smoke test after pulling Phase 2 + 3

```cmd
python -m db.init_db
pytest tests/ -v -k "not db"
curl http://127.0.0.1:8000/api/outlook/changes
curl http://127.0.0.1:8000/api/briefing
curl "http://127.0.0.1:8000/api/rules/performance?window=20&min_n=1"
python -m etl.backtest --from 2026-01-01 --to 2026-05-15 | head -10
python -m etl.cleanup --meta --dry-run
```

If all of those return without errors and the dashboard renders the new banner + briefing card, Phase 2 and Phase 3 are wired correctly.

---

## What I deliberately did NOT do

- **No schema-versioning / Alembic.** The `ALTER TABLE IF EXISTS … ADD COLUMN IF NOT EXISTS` pattern in `baseline.sql` is enough for the current single-user pace; introducing migrations is its own project.
- **No DB pg_stat panel on DB Stats.** The roadmap mentioned it; left out to keep this pass focused. Easy to add later by extending the existing `/api/stats/tables` endpoint.
- **Backtest direction heuristic is text-based.** If you want exact direction-per-rule, add an `action_label` column to `ref_trig_atomic_rule` / `ref_trig_composite_mapping` and look that up instead of grepping the rule_id / category strings.
- **Notifications module is stdlib + optional packages.** `winotify` / `win10toast` are NOT added to `requirements.txt` — install them only if you want toast. SMTP works with stdlib alone.
