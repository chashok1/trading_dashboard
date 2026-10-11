# AGENT_WORK — Developer pointer

## Active task — TASK_101 (reprocess + fix Actionable Hedgeye panel)

- **agent-tasks/TASK_101_hedgeye_panel_visibility.md** — Re-process the Hedgeye emails,
  then diagnose + fix why the Hedgeye panel on `/actionable` shows nothing despite data
  being loaded. **Likely root cause:** the panel queries by the screen's anchor date
  (`MAX(export_date)` from hist_td), but the Hedgeye data is dated NEWER than the anchor,
  so the endpoint's exact-date (alerts/flips) and `<= date` (top5/stance) filters return
  empty and the panel hides itself. Fix: show the most recent Hedgeye data rather than
  pinning to an older anchor (details + verify steps in the task). Then verify UI
  functionality across `/actionable`, `/symbol-hedgeye`, `/digest`, `/notes`.
- Log to `DEV_HANDOFF.md`, end `ALL_DONE`. The developer MAY edit code for this fix.

## Context — full Hedgeye enhancement set (coded by Cowork, dev-verified to load)

All endpoints/screens are in `COWORK_IMPL_LOG.md`. Feed catalog, Actionable Hedgeye
panel, Notes + rule-candidate builder, digests, Quad signal, dossier, LLM read endpoint,
and nav links across all main screens are in place. This task fixes the panel's
date-driven visibility after reprocessing.

## After TASK_101

Tester final batch round (`AGENT_TASK.md`) once Ashok asks.
