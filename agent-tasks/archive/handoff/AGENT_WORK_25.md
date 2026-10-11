# AGENT_WORK — Developer master pointer

Current assignment: **`agent-tasks/TASK_116_market_panel_frontend.md`**

Do ONLY this task. TASK_112–114 (test-debt batch) are running separately in
parallel — do not touch tests/*.py or docs in this task, stay in web/.

TASK_115 (backend) is done and reviewed — its payload superset is live.
Preflight instrument identifiers recorded by TASK_115 (use verbatim, do not
re-derive):
- SPX/VIX/DXY/GC/WTI → `metric_key` in `/api/marketbar`
- 10Y → tos_symbol `TNX:CGI`, `/api/rr-bar` Rates group
- HY → tos_symbol `HYG`, `/api/rr-bar` Credit group
- BTC → tos_symbol `/BTC`, `/api/rr-bar` Crypto group

Market-panel queue (source: `docs/market_panel_consolidation_design.md`):
1. TASK_115 — market panel consolidation, backend payload ✓ DONE (reviewed,
   AGENT_WORK_24)
2. → TASK_116 — market panel consolidation, frontend merge  ← CURRENT

(Actionable screen queue TASK_103–110: complete and reviewed.)
(Test-debt queue TASK_111: done. TASK_112–114: running separately in
background — do not interact with that work.)

Instructions:
1. Implement TASK_116 only; log changes in `DEV_HANDOFF.md` (files,
   decisions, risks); end with the literal marker `ALL_DONE` when complete.
2. `node --check` every touched `web/*.js` on Windows + `tail -10`.
3. Do NOT commit or push — the user commits from Windows after each task.
4. Do NOT hand off to the tester — stop at `ALL_DONE` and report.
