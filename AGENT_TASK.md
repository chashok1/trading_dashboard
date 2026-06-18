# AGENT TASK -- Tester pointer

Tester agent: verify TASK 49 -- Held/not-held consolidation (revised spec).

Full verification steps are in:
agent-tasks/TASK_49_recency_first_consolidation.md -- section "How to verify" (7 checks)

Developer handoff: DEV_HANDOFF.md (AGENT_WORK_49)

Key behaviors to verify:
- Held symbols: winning_source is the earliest in SOURCE_ORDER (PS>ETF>RR>SSS>II>CALL)
- Not-held symbols: winning_source is the one with the most recent source_snapshot_date
- SSS INCREASE/REDUCE can now win (no demotion)
- CALL can win even when other sources present (ranks last by SOURCE_ORDER, not excluded)
- Not-held PS REMOVE: can win if freshest, but suppressed "NOT HELD" ($0, hidden by default)

Write results to AGENT_RESULT_49.md ending with DONE or FAILED: <checks>.
