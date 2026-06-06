# AGENT TASK 21 — finish the checkpoint: commit the remaining core work, heal web/ index

**You (VS Code agent), Windows git.** Write to **`AGENT_RESULT_21.md`**.
Heartbeat: append `⏳ HH:MM:SS — <step>` lines as you go.

The previous commit (1b8c4be) only captured a PARTIAL set. These core changes are
STILL uncommitted: etl/derive.py, etl/derive_cat_atomic_input.py, etl/etl_load.py,
etl/refactor_base_rules.py, db/baseline.sql, db/seeds_base_rules.sql, api/_helpers.py,
api/routers/{dash,health,monitor}.py, CLAUDE.md, docs/file_monitor_logic.md,
web/groups.html, web/rule_flow.{html,js}, plus the updated workbooks. Also the web/
index is flapping (trace.js/trig.*/warning_badge.js show as staged-deleted, plus a
malformed rename) — these files DO exist on disk; the index is just corrupted.

## Step 1 — reset the index to clear corruption (working tree untouched)
```
git reset
git status --porcelain
```
Paste status. Working-tree files are NOT changed by `git reset` — it only unstages.
After this, web/ files that exist on disk should show as normal modified/untracked,
NOT deleted.

## Step 2 — verify web/ real files are present on disk (sanity)
```
git ls-files web/ | findstr /i "warning_badge styles trace trig rules_health"
dir web\warning_badge.js web\styles.css web\trace.html web\trig.html
```
Confirm those files exist on disk. **If any real web/*.js/.html/.css is MISSING from
disk, STOP and report** (we'd restore from HEAD: `git checkout HEAD -- web/<file>`).

## Step 3 — stage disk reality
```
git add -A
git status --porcelain
```
Paste the staged list. It MUST include the core files listed above as modified, and
it must NOT show any real web file as deleted (D). `etl/working/*` should be absent
(gitignored). If a real web file still shows as deleted after `git add -A`, STOP and
restore it: `git checkout HEAD -- web/<file>` then `git add web/<file>`.

## Step 4 — remove the scaffolding backup dir (don't commit it)
If `_session_backup_20260606/` exists, delete it (it's a backup of throwaway files):
`rmdir /s /q _session_backup_20260606` (or rm -rf). Re-run `git status` — ensure it's
gone and not staged.

## Step 5 — commit
```
git commit -m "checkpoint (cont.): anchor-date model, earnings_days decrement, drv_trig double-eval + nested-composite gating + drv_trig nesting, Phase 2 strict base-rule refactor, seeds weight_override, api/docs/web updates; heal web/ index"
```

## Step 6 — verify clean
```
git status --porcelain
git log --oneline -3
git show --stat HEAD | head -40
```
Paste all three. Confirm: (a) status clean except intentionally-untracked items
(AGENT_TASK.md/AGENT_RESULT_21.md, etl/working data); (b) the new commit's file list
includes etl/derive.py, etl/derive_cat_atomic_input.py, db/baseline.sql,
db/seeds_base_rules.sql, api/*, docs/*, web/* ; (c) no real web file deleted.

Write `DONE` at the bottom of `AGENT_RESULT_21.md`.
