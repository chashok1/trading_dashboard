# AGENT TASK 20 — checkpoint: fix web/ git state, clean scaffolding, commit

**You (VS Code agent) run git on Windows (clean).** Write output to
**`AGENT_RESULT_20.md`**. Heartbeat: append `⏳ HH:MM:SS — <step>` lines as you go.

Goal: lock in this session's work as one clean commit, after fixing a git-index
anomaly and removing temp scaffolding. Go carefully; STOP and report if anything
looks unexpected.

## Step 1 — show state first (no changes)
```
git rev-parse --abbrev-ref HEAD
git status --porcelain
```
Paste it.

## Step 2 — fix the web/ anomaly (accidental staged-deletions + FUSE junk)
Several web/ files (styles.css, warning_badge.js, trig.*, trace.*, rules.js,
rules_health.html, test_results.html) show as staged-deleted (D) but exist on
disk — accidental index corruption from the mount. Restore them to match disk,
and untrack the FUSE artifacts:
```
git add web/
git rm --cached web/.fuse_hidden*
```
Then delete the FUSE files from disk (Windows): `del web\.fuse_hidden*` (or rm).
Re-run `git status --porcelain | findstr web/` and paste — confirm NO web/*.js/.html/.css
shows as deleted anymore (styles.css, warning_badge.js, trig.*, trace.* should be
tracked/normal). **If any real web file is still marked deleted, STOP and report.**

## Step 3 — remove dead scaffolding (one-off diagnostics + logs)
Delete these (use `git rm` for tracked ones, plain delete for untracked):
- All `AGENT_RESULT_*.md`
- `agent_colcheck.py`, `agent_queries.py`, `agent_queries2.py`, `agent_queries3.py`,
  `agent_queries4.py`, `agent_rederive_trig.py`
- `check_trigma_comparison.py`, `check_trigma_equity.py`, `check_trigma_final.py`,
  `check_trigma_v2.py`, `check_vol_rule.py`
- `compare_trigma2.py`
- `compare_trigma_out.txt`, `compare_trigma_out2.txt`, `compare_trigma_out4.txt`,
  `trigma_report_new.txt`
- `gen_updated_formulas.py`, `run_task17.py`, `run_task18.py`, `run_task19.py`,
  `updated_formulas.xlsx`

KEEP (do not delete): `compare_trigma.py` (the comparison tool), `agent_rederive_all.py`
(still needed for Phase 4), `AGENT_TASK.md`, `db/backups/*.json` (rollback artifacts).

## Step 4 — do NOT commit runtime data
Do not stage `etl/working/*` (source CSVs, logs, scheduler_nightly_last.txt). If
`etl/working/scheduler_nightly_last.txt` is modified/tracked, leave it unstaged.
If there's no .gitignore rule for `etl/working/`, add one line `etl/working/` to
`.gitignore` and stage the .gitignore.

## Step 5 — stage the real work + commit
Stage: the modified code/docs/SQL (etl/derive.py, etl/derive_cat_atomic_input.py,
etl/etl_load.py, etl/rebuild_rules.py, etl/refactor_base_rules.py, db/baseline.sql,
db/seeds_base_rules.sql, api/_helpers.py, api/routers/{dash,health,monitor}.py,
CLAUDE.md, docs/*, web/* restored, compare_trigma.py), plus the updated workbooks
(`Tickers 2026-04-30.xlsx`, `TrigMA.xlsx`) which were intentionally refreshed.
Then commit:
```
git commit -m "checkpoint: anchor-date model, earnings_days decrement, drv_trig double-eval fix, nested-composite gating + drv_trig nesting, Phase 2 base rules (strict firing-equivalent refactor), rebuild_rules durability for current_volume_rule; restore web/ index state + drop FUSE artifacts; remove session scaffolding"
```

## Step 6 — report
Paste `git status --porcelain` (should be clean except intentionally-untracked
etl/working data) and `git log --oneline -3`. Confirm: web/ files intact, scaffolding
gone, one new commit.

> Note on Phase 3 state: the Baseline (id=1, active) and Sigmoid v1 (id=2, inactive)
> param sets live in the DB (ref_trig_param_set/value), not in git — that's expected;
> they're data, not code. No action.

Write `DONE` at the bottom of `AGENT_RESULT_20.md`.
