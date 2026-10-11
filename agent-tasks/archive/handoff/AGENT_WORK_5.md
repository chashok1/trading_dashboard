# AGENT_WORK — Developer pointer

`/dev-cycle` starts here. Implement the task spec below, log to `DEV_HANDOFF.md`,
end with `ALL_DONE`. No commits — Ashok commits from Windows.

## Active task

- **agent-tasks/TASK_94_hedgeye_macro_week_summary.md** — Reclassify the lone
  UNKNOWN email ("Macro Week Summary Notes", new weekly Friday product) into
  `note_repo` as email_type `macro_week_summary`. Classifier code + seed row were
  already written by Cowork in the prior session; this round is DB-side: re-seed
  the router table, clear the logged `unknown`, re-run `--backfill 2026-06-26`,
  and verify. See the task file for steps + "How to verify."

## Context

Follows TASK_93 (Hedgeye email pipeline — shipped & verified clean end-to-end).
The UNKNOWN was the system working as designed (surfaced a new product instead of
dropping it), not a bug.
