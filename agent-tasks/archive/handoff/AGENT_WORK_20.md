# AGENT_WORK — Developer master pointer

Current assignment: **`agent-tasks/TASK_107_actionable_keyboard_focus.md`**

Do ONLY this task (plus the one-line addendum below). Do not start the next
task until this pointer is updated.

## Addendum to TASK_107 (small, from TASK_105/106 review)

- Fix the stale test broken by TASK_105's MACRO sort change:
  `tests/test_task74_macronet.py::TestHTMLColumns::test_macro_th_has_data_key`
  asserts `data-key="macro_value"` in `web/actionable.html`; the header is now
  (correctly) `data-key="macronet" data-type="num"`. Update the assertion to
  match the new attributes.

Queue (one task at a time; Cowork re-points after each review):
1. TASK_104 — auto-refresh state preservation + search debounce  ✓ DONE (reviewed)
2. TASK_105 — grid density: column manager, top-N collapse, legend  ✓ DONE (reviewed)
3. TASK_106 — API efficiency: bulk endpoint, lazy macro detail, tunable threshold  ✓ DONE (reviewed)
4. → TASK_107 — keyboard + focus mode v2 (+ addendum above)  ← CURRENT
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
3. Do NOT commit or push — the user commits from Windows after each task.
4. Do NOT hand off to the tester — stop at `ALL_DONE` and report.
