# AGENT_WORK — Developer master pointer

Current assignment: **`agent-tasks/TASK_106_actionable_api_efficiency.md`**

Do ONLY this task. The queue below is context — do not start the next task
until this pointer is updated.

Queue (one task at a time; Cowork re-points after each review):
1. TASK_104 — auto-refresh state preservation + search debounce  ✓ DONE (reviewed)
2. TASK_105 — grid density: column manager, top-N collapse, legend  ✓ DONE (reviewed)
3. → TASK_106 — API efficiency: bulk endpoint, lazy macro detail, tunable threshold  ← CURRENT
4. TASK_107 — keyboard + focus mode v2
5. TASK_108 — Hedgeye panel CSS-grid layout + icon sync
6. TASK_109 — cleanup: orphans, stop alert, CSV refresh
7. TASK_110 — doc sync (last, so docs match the final screen)

(Also done earlier: TASK_103 — bug sweep.)

Instructions:
1. Implement the current task only; log changes in `DEV_HANDOFF.md` (files,
   decisions, risks); end with the literal marker `ALL_DONE` when complete.
2. After editing any large web/*.js file, verify on Windows:
   `node --check <file>` and `tail -10 <file>` (sandbox mirrors false-alarm —
   CLAUDE.md gotcha).
3. This task touches `api/routers/dash.py` and seeds one `ref_settings` row —
   run `python -m db.init_db` (idempotent) and verify with
   `python -c "import ast; ast.parse(open('api/routers/dash.py').read())"`.
4. Do NOT commit or push — the user commits from Windows after each task.
5. Do NOT hand off to the tester — stop at `ALL_DONE` and report.
