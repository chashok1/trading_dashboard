# AGENT_WORK — Developer master pointer

Current assignment: **`agent-tasks/TASK_104_actionable_refresh_etiquette.md`**

Do ONLY this task. The queue below is context — do not start the next task
until this pointer is updated.

Queue (one task at a time; Cowork re-points after each review):
1. → TASK_104 — auto-refresh state preservation + search debounce  ← CURRENT
2. TASK_105 — grid density: column manager, top-N collapse, legend
3. TASK_106 — API efficiency: bulk endpoint, lazy macro detail, tunable threshold
4. TASK_107 — keyboard + focus mode v2
5. TASK_108 — Hedgeye panel CSS-grid layout + icon sync
6. TASK_109 — cleanup: orphans, stop alert, CSV refresh
7. TASK_110 — doc sync (last, so docs match the final screen)

(Done: TASK_103 — bug sweep, reviewed, awaiting user commit.)

Instructions:
1. Implement the current task only; log changes in `DEV_HANDOFF.md` (files,
   decisions, risks); end with the literal marker `ALL_DONE` when complete.
2. After editing any large web/*.js file, verify on Windows:
   `node --check <file>` and `tail -10 <file>` (sandbox mirrors false-alarm —
   CLAUDE.md gotcha).
3. Do NOT commit or push — the user commits from Windows after each task.
4. Do NOT hand off to the tester — stop at `ALL_DONE` and report.
