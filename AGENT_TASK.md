# AGENT_TASK — tester pointer

## ⏸ NO TEST ROUND IS PENDING.

**Do not run anything.** Stop here and report that there is nothing to verify.

The previous contents of this file (the TASK_133 cockpit round, and a briefly
staged TASK_138 round that the user cancelled on 2026-09-21) are **closed and
superseded**. Do not run either checklist.

---

## When a round is next requested

Active work is the TASK_139–142 batch — see `AGENT_WORK.md`.

Two gates, both required before any verification starts:

1. **The user has explicitly asked for a test round.** Testing never runs by
   default in this repo (`docs/agent_handoff_workflow.md` §3).
2. **`DEV_HANDOFF.md` ends with `ALL_DONE`.** If it ends `PARTIAL: <tasks>`,
   only those tasks are eligible — verify those and say so; do not test
   unbuilt work. If it ends `STOPPED_AT_139_GATE: ...`, that task was
   deliberately not implemented — nothing to verify there.

Then run the **"How to verify"** section of each completed
`agent-tasks/TASK_<n>_*.md` in the round, write evidence to
`AGENT_RESULT_<n>.md`, and end with `DONE` or `FAILED: <blocks>`.

**If a round covering TASK_138 is ever requested**, include this check, which
is not in that task's own spec: the developer added a `--since` filter to
`compute_firing_outcomes.py` on the reasoning that `_fwd`'s `LEAD()` only
looks forward. Prove it — run `--since <anchor − 45d>` and a full run over the
same window and confirm `fwd_5d_pct` / `fwd_20d_pct` match exactly on the
overlap. A silent difference there would corrupt every edge number in the
system.

No commits or pushes — the user commits from Windows.
