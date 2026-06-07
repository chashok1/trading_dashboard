---
description: Run the Developer -> Tester loop on the task in AGENT_WORK.md. Optional arg = max iterations (default 3).
---

You are the **orchestrator** for a Developer/Tester workflow. Subagents cannot call each other, so you drive the whole cycle from this top-level session.

Max iterations: `$ARGUMENTS` if a number was given, otherwise **3**.

Run this loop:

1. **Pre-flight.** Confirm `AGENT_WORK.md` exists in the project root. If not, tell the user there's no delegated task and stop.

2. **Developer pass.** Invoke the **developer** subagent (via the Task tool, `subagent_type: developer`). Let it implement the task, archive `AGENT_WORK.md` to `AGENT_WORK_N.md`, and write `DEV_HANDOFF.md`. Capture the N it reports.

3. **Tester pass.** Invoke the **tester** subagent (`subagent_type: tester`). It reads `DEV_HANDOFF.md`, runs the checks, and returns a structured report. Persist that report verbatim to `TEST_REPORT_<N>.md` in the project root.

4. **Decide.**
   - If the Tester's verdict is **PASS** (or PASS_WITH_CONCERNS that you judge acceptable): stop. Summarize for the user: what was built, the archived `AGENT_WORK_<N>.md`, the `TEST_REPORT_<N>.md` verdict, and whether it was committed.
   - If the verdict is **FAIL / SEND BACK TO DEVELOPER** and iterations remain: write a fresh `AGENT_WORK.md` whose task is "Fix the issues from TEST_REPORT_<N>.md" with the Tester's specific findings pasted in, then go back to step 2. Increment the iteration counter.
   - If iterations are exhausted, stop and report the outstanding failures to the user — do not loop forever.

5. **Final summary** (concise): iterations used, final verdict, files changed, and the names of the `AGENT_WORK_*.md` / `TEST_REPORT_*.md` artifacts produced.

Rules: never skip the Tester. Never let the Developer mark its own work as passing. Keep each subagent focused on its single role.
