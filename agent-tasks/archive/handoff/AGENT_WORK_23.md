# AGENT_WORK — Developer master pointer

Current assignment: **`agent-tasks/TASK_111_test_debt_inventory_retirements.md`**

Do ONLY this task. The queue below is context — later tasks will be specced
after each review (one task at a time).

Test-debt queue (source: `docs/audit/test_debt_review.md`):
1. → TASK_111 — failure inventory + mechanical retirements (Cat A/B) + conftest guards  ← CURRENT
2. TASK_112 — rewrite drifted behavioral tests (Cat C) — spec to follow
3. TASK_113 — DB-dependent repair: cat_parity fixtures, de-pin data assertions (Cat D) — spec to follow
4. TASK_114 — acceptance-test policy adoption — spec to follow

(Actionable screen queue TASK_103–110: complete and reviewed.)

Instructions:
1. Implement the current task only; log changes in `DEV_HANDOFF.md` (files,
   decisions, risks); end with the literal marker `ALL_DONE` when complete.
2. Item 1 (inventory) MUST run before any test file is touched.
3. Retirements are comments-in-place, not silent deletions.
4. Do NOT commit or push — the user commits from Windows after each task.
5. Do NOT hand off to the tester — stop at `ALL_DONE` and report.
