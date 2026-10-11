# AGENT_WORK — Developer master pointer

Work the four specs in this order (119 → 118 → 120 → 121). 120 depends on
flags introduced by 118 and 119. Log everything in `DEV_HANDOFF.md`; write
`ALL_DONE` only when all four are done (or stop at a boundary and report
without the marker).

1. **`agent-tasks/TASK_119_stop_consistency.md`** — below-stop held rows get
   `stop_breached` flag, never show effective ADD/INCREASE, red STOP pill +
   chip. Small and independent — do first.
2. **`agent-tasks/TASK_118_sell_side_quality.md`** — `v_unproven_sell_rules` +
   `low_confidence` annotation on sell rows driven only by negative-edge
   rules; backtest S1–S3 sell-into-strength candidates into
   `docs/audit/sell_candidates_2026-07.md` (report only, don't activate).
3. **`agent-tasks/TASK_120_default_sort_dollar_edge.md`** — new default sort:
   stop breaches pinned, then dollar-weighted edge; fix `_agreementDir`
   semantics; buy-noise gate — unheld ADD/BMN rows whose Technical (QS) code
   is not BS/BM collapse into a "Watchlist (n)" band. Display layer only.
4. **`agent-tasks/TASK_121_inferred_actions_from_positions.md`** — infer user
   trades from CS/F position deltas into `drv_inferred_action`; stance
   (FOLLOWED/CONTRADICTED/NO_SIGNAL) + forward returns; repoint "Your
   actions" panel. No manual logging anywhere.

Ground rules (per docs/agent_handoff_workflow.md): no git commit, no tester
unless the user asks, BUY-side rules untouched, derives idempotent, tos_symbol
in all drv_*, SQL ≤ 965 bytes per command.
