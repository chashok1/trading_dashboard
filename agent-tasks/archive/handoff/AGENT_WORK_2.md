# AGENT_WORK — developer pointer

Implement **`agent-tasks/TASK_91_corr_unify_dataset.md`**.

## Goal
Make the WHOLE USD-correlation table use ONE consistent daily dataset. TASK_90 moved only
USD+SPX to `histy:` (daily YFiles, 16:30 EOD); Brent/Gold/Bitcoin still read the separate
`yfinance:` pull, so they're correlated against a dollar from a different dataset/snapshot —
noise that regressed Gold 15D. Move Brent/Gold/Bitcoin to `histy:` too (symbols `BZ=F`,
`GC=F`, `BTC-USD` are all in the daily YFiles load, confirmed). CRB stays yfinance (`DBC`
not in YFiles — known proxy gap). Anchor 2026-06-23.

## Scope
- `db/seeds_corr.sql`: brent/gold/bitcoin → `["histy:<sym>","yfinance:<sym>"]` (histy primary,
  yfinance history fallback). USD/SPX already done. CRB unchanged.
- No new code — the `histy:` branch in `derive_usd_correlation.py::_load_price_series` exists.
- Re-derive 6/23; compare the full 5-asset table to the provider; confirm Gold 15D recovers
  toward −0.70 (from TASK_90's −0.51) and SPX/Brent/Bitcoin don't regress.
- Out of scope: CRB proxy, scheduler automation (recommend only), commit.

## Why this is the fix
A correlation is only clean when both legs are the same source at the same timestamp.
SPX snapped to the provider precisely because USD+SPX are both hist_y now; Gold slipped
because it's still yfinance vs a hist_y dollar. The provider uses one EOD dataset for the
whole table — unifying on hist_y matches that and keeps everything fresh on the daily load.

## How to verify (hints for Tester — see TASK_91 §"How to verify")
- All source_specs `histy:` first (except CRB); SPX still matches; Gold 15D recovered;
  Brent/Bitcoin not regressed; Gold w15 hand-check = same-source Pearson; freshness holds;
  pytest updated for new source_spec, idempotent.

## Constraints / notes
- Follow CLAUDE.md + docs/agent_handoff_workflow.md. Cowork has no DB access. Log every step
  + the full before/after table in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit — user commits
  from Windows. NOTE: `etl/` changes need a server restart before re-derive.
