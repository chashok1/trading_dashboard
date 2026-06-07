# AGENT TASK 25 — apply scorecard view, run it, commit Phase 3–4 + docs

**You (VS Code agent), DB + Windows git.** Write to **`AGENT_RESULT_25.md`**.
Heartbeat: `⏳ HH:MM:SS — <step>` before each step. Do NOT run `rebuild_rules`.

## Step 1 — apply the new view
`db/baseline.sql` now defines `v_rule_scorecard` (direction-adjusted composite
efficacy). Apply it:
```
python -m db.init_db
```
Verify it exists:
```sql
SELECT to_regclass('v_rule_scorecard');
SELECT param_set_id,label,is_active FROM ref_trig_param_set ORDER BY 1;  -- Baseline id=1 must still be active
```
Paste. If init_db errors, instead apply just the view: copy the
`CREATE OR REPLACE VIEW v_rule_scorecard AS ...` block from baseline.sql and run it
via psql. Confirm Baseline (id=1) is still is_active=TRUE.

## Step 2 — run the direction-adjusted scorecard
```sql
-- best rules (signal was right on average)
SELECT rule_id, direction, fires, edge_20d, win_rate, raw_avg_fwd20
FROM v_rule_scorecard WHERE fires >= 30 ORDER BY edge_20d DESC LIMIT 15;
-- worst rules (fired before the wrong move — review candidates)
SELECT rule_id, direction, fires, edge_20d, win_rate, raw_avg_fwd20
FROM v_rule_scorecard WHERE fires >= 30 ORDER BY edge_20d ASC LIMIT 15;
```
Paste both tables. (edge_20d > 0 = good; this is the real ranking, vs the earlier
raw-return one that mixed up BUY/SELL direction.)

## Step 3 — commit the Phase 3–4 work + docs
Stage and commit these (use git add for each; DO NOT add AGENT_*/agent_* scaffolding,
db/backups, or etl/working):
- `etl/backfill_derives.py`, `etl/compute_firing_outcomes.py`  (new)
- `etl/ml_tune_thresholds.py`  (rid cast fix)
- `db/baseline.sql`  (drv_rule_outcome PK/column fix + v_rule_scorecard view)
- `docs/rule_tuning_and_outcomes.md`  (new)
- `CLAUDE.md`  (lookup rows + 2026-06-06 migration notes)

```
git add etl/backfill_derives.py etl/compute_firing_outcomes.py etl/ml_tune_thresholds.py db/baseline.sql docs/rule_tuning_and_outcomes.md CLAUDE.md
git status --porcelain
```
Paste the staged list and CONFIRM no AGENT_*/agent_*/etl/working/db.backups files are
staged. Then:
```
git commit -m "Phase 3-4: firing-based outcomes pipeline (backfill_derives, compute_firing_outcomes), v_rule_scorecard (direction-adjusted), drv_rule_outcome PK fix, ml tuner rid cast; docs/rule_tuning_and_outcomes.md + CLAUDE.md guide"
git log --oneline -3
git status --porcelain
```
Paste all three. Status should be clean except intentionally-untracked
(AGENT_*, agent_*, etl/working, db/backups, scheduled_tasks.lock).

## Step 4 — verdict
State: (a) view applied + Baseline still active; (b) top 3 / bottom 3 rules by
edge_20d; (c) commit hash + that only the intended files were committed.

Write `DONE` at the bottom of `AGENT_RESULT_25.md`.
