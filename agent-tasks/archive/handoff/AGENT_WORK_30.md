# AGENT_WORK — Developer master pointer

## Task queue (in order)

1. **`agent-tasks/TASK_122_technical_first_gate.md`** — finish first if not
   already complete (`DEV_HANDOFF.md` does not yet end `ALL_DONE`).
   Technical-first buy gate + tier restructure: delete TASK_120's
   new-arrival bypass; gate unheld ADD/BMN purely on Technical BS/BM; NEW
   pill inside the Watchlist band; tier order stops → credible held sells →
   buys ranked by 3-way agreement → holds. Display layer only
   (`web/actionable.js`).

2. **`agent-tasks/TASK_123_signal_validation_scorecards.md`** — measure the
   unvalidated calibration (playbook A1–A6): new views
   `v_bull_gate_scorecard`, `v_final_call_scorecard`,
   `v_source_edge_scorecard` (additive, `db/baseline.sql`), inferred-action
   FOLLOWED-vs-CONTRADICTED aggregate, hit-threshold sensitivity, and the
   report `docs/audit/signal_validation_2026-07.md` with A1–A6 verdicts.
   Read-only + additive; no rule/threshold/derive/UI changes.

Append progress to `DEV_HANDOFF.md`; write `ALL_DONE` only when the whole
queue is finished. No commit, no tester handoff.
