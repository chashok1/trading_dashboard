# AGENT_WORK — Developer master pointer

Current assignment: **`agent-tasks/TASK_103_actionable_bug_sweep.md`**

Scope: Actionable screen bug sweep — 5 confirmed bugs (snooze persistence,
dead popover close button, un-snooze DELETE, dead CSV Metric column, focus-card
action mismatch) + dead-code deletion in `web/actionable.js`. Background/context:
`docs/audit/actionable_screen_review.md`.

Instructions:
1. Work through TASK_103 item by item (items 1–6).
2. Log every change (files, decisions, risks) in `DEV_HANDOFF.md`; end the file
   with the literal marker `ALL_DONE` only when everything is complete.
3. After editing `web/actionable.js`, verify no truncation:
   `node --check web/actionable.js` and `tail -10 web/actionable.js`.
4. Do NOT commit or push — the user commits from Windows.
5. Do NOT hand off to the tester — stop at `ALL_DONE` and report.
