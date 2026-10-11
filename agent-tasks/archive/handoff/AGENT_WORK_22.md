# AGENT_WORK — Developer master pointer

Current assignment: **`agent-tasks/TASK_109_actionable_cleanup.md`**

Do ONLY this task (plus the carried-forward addendum below). Do not start the
next task until this pointer is updated.

## Addendum to TASK_109 (carried forward from TASK_107 review)

- Reconcile focus-mode Done logging: the focus card (button AND Enter/D key)
  logs literal 'DONE' while the grid's inline Done button logs the row's
  Final Call code (`doneBtn.dataset.fc || 'DONE'`). Make focus mode pass the
  row's Final Call code too (`r._fc_code || 'DONE'`) so both entry points
  record the same `action_code`.

Queue (one task at a time; Cowork re-points after each review):
1. TASK_104 — auto-refresh state preservation + search debounce  ✓ DONE (reviewed)
2. TASK_105 — grid density: column manager, top-N collapse, legend  ✓ DONE (reviewed)
3. TASK_106 — API efficiency: bulk endpoint, lazy macro detail, threshold  ✓ DONE (reviewed)
4. TASK_107 — keyboard + focus mode v2 (+ test addendum)  ✓ DONE (reviewed)
5. TASK_108 — Hedgeye panel CSS-grid layout + icon sync  ✓ DONE (reviewed)
6. → TASK_109 — cleanup: orphans, stop alert, CSV refresh (+ addendum)  ← CURRENT
7. TASK_110 — doc sync (last, so docs match the final screen)

(Also done earlier: TASK_103 — bug sweep.)

Instructions:
1. Implement the current task only; log changes in `DEV_HANDOFF.md` (files,
   decisions, risks); end with the literal marker `ALL_DONE` when complete.
2. After editing web/*.js files, verify on Windows: `node --check <file>` and
   `tail -10 <file>` (sandbox mirrors false-alarm — CLAUDE.md gotcha).
3. TASK_109 deletes `web/macro_band.js` + `web/cockpit.html` — grep for stray
   references first (`grep -rn "macro_band\|cockpit" api/ web/ tests/`) and
   fix any found (docs references are TASK_110's job).
4. Do NOT commit or push — the user commits from Windows after each task.
5. Do NOT hand off to the tester — stop at `ALL_DONE` and report.
