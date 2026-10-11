# AGENT_WORK — developer pointer

Implement **`agent-tasks/TASK_92_verify_actionable_refresh.md`**.

## Goal
Verification only (no code change unless a defect is found). Ashok loaded an
**intraday TOSL** file and wants DB-level proof that the Actionable pipeline
refreshed correctly for the current anchor `D = MAX(export_date) FROM hist_td`:

1. The load ran `derive_all(D)` (check `meta_derived_run` at/after the TOSL `loaded_at`).
2. `drv_quote` for `D` carries the fresh intraday price (`is_intraday = TRUE`, recent `loaded_at`).
3. Price-driven cells recomputed (RR indices KI/KJ/KK, trend_sd/trade_sd,
   `drv_tn_td_bb_rr.td_tn_bb_action_desc`, `drv_actionable.stop_level`).
4. `/api/actionable/freshness` returns `stale: false` for `D`.
5. EOD-anchored fields (Trend/Trade lines, RSI, MACD, weekly RVOL, Sources,
   P(↑20d), MACRO, side panels) are **unchanged** — this is correct intraday, NOT a failure.

## Scope
- Run the SQL + endpoint checks in TASK_92 §"Steps / queries".
- Spot-check 3 liquid held names (adjust symbols to ones actually held).
- Do NOT "fix" stale-looking EOD fields — intraday immobility is correct.
  Only flag a defect if a *price-driven* field failed to refresh or the cascade
  did not run.

## How to verify
See TASK_92 §"How to verify (pass criteria)". Record anchor `D`, the spot-check
before/after table, the freshness result, and endpoint responses in
`DEV_HANDOFF.md`; end `ALL_DONE`.

## Constraints / notes
- Follow CLAUDE.md + docs/agent_handoff_workflow.md. Cowork has no DB access.
- Context doc: `docs/actionable_dataflow_analysis.md`.
- No commit — Ashok commits from Windows. No tester round unless he asks.
- Column-name caveat: `drv_cat_atomic_input` index columns may be `trr_idx/mrr_idx/lrr_idx`
  or `KI/KJ/KK` — look up in `etl/derive_cat_atomic_input.py` if query D doesn't resolve.
