# AGENT_TASK — tester pointer

## ⏸ NO TEST ROUND IS PENDING.

**Do not run anything.** Stop here and report that there is nothing to verify.

The previous contents of this file (the end-of-project Hedgeye batch round covering
TASK_95/96/98/99 and the Cowork-built work) are **closed and superseded**. Do not run
that checklist.

---

## When a round is next requested

The only active task is `agent-tasks/TASK_133_dashboard_cockpit.md`.

Two gates, both required before any verification starts:

1. **The user has explicitly asked for a test round.** Testing never runs by default
   in this repo (`docs/agent_handoff_workflow.md` §3).
2. **`DEV_HANDOFF.md` ends with `ALL_DONE`.** If it ends `PHASE_<n>_DONE`, only
   phases 1…n are eligible — verify those and say so; do not test unbuilt phases.

Then run the **"How to verify"** section of `agent-tasks/TASK_133_dashboard_cockpit.md`,
plus each phase's own verification block. Write evidence to `AGENT_RESULT_133.md`,
ending `DONE` or `FAILED: <blocks>`.

### The three checks that matter most

Quote the offending rows on any failure.

1. **Realized-vol units** — `drv_market_stat.rv21` for SPX should sit roughly 8–25 in a
   normal regime. Three-digit or sub-1 values mean a units bug. Cross-check against
   `hist_macro` series `RVOL` (source `CBOE`) on the same dates.
2. **Time-weighted return** — for a category with no trades in the window, TWR must
   equal `V_end/V_start − 1` **exactly**.
3. **Portfolio reconciliation** — `drv_category_perf` `asset_class` axis market-value
   total must reconcile to `/api/portfolio/summary` (market + cash).

Plus: `python -m etl.derive` twice for the anchor date → all new `drv_*` tables
byte-identical (idempotence is non-negotiable), and `pytest tests/` with no new
failures against the known baseline.
