# AGENT_WORK — developer pointer

Implement **`agent-tasks/TASK_90_corr_use_daily_sources.md`** (supersedes TASK_88).

## Goal
Make the USD-correlation panel (1) ride the **daily-loaded** dollar/price data so it can't
silently freeze, and (2) use the dollar series whose daily path best matches the provider,
to close the residual SPX 15D/30D gap. Anchor 2026-06-23.

## The two facts driving this
- **Two parallel Yahoo pipelines.** `hist_quote_daily` (read by the correlation) is filled
  ONLY by the standalone `etl/fetch_quotes.py` — not wired to the daily run, so it lagged at
  6/18. The dollar (`^NYICDX`) + prices ARE loaded daily into **`hist_y`** (and TOS `$DXY`),
  current to 6/23, but the correlation never reads them.
- **Dollar mismatch.** Provider 6/23 dollar ≈ 101.63; ours all ≈ 101.39 (TOS `$DXY` 101.390,
  YFiles `^NYICDX` 101.387, RR prev-close 101.26). Level doesn't move correlation — the daily
  *path* does — so reconcile the series and test which dollar source matches.

## Scope
- Steps 1–2: reconcile dollar + SPX across `hist_y`/TOS/`hist_quote_daily`; recompute SPX
  w15/w30 per dollar source (+ 1-day-lag window).
- Step 3: re-plumb `ref_corr_asset.source_spec` (`db/seeds_corr.sql`) to prefer daily sources
  (TOS `$DXY`, `hist_y:^NYICDX`/`^SPX`); add a small `hist_y` read branch in
  `derive_usd_correlation.py::_load_price_series` if needed. Keep yfinance as history
  fallback. Re-derive 6/23, re-pull `/api/correlations`.
- Out of scope: CRB proxy, scheduler automation (recommend only), commit.

## How to verify (hints for Tester — see TASK_90 §"How to verify")
- Dollar reconciliation printed; panel now reads the daily dollar; SPX w15/w30 closer to
  −0.27/−0.41 than the −0.43/−0.20 post-TASK_89 baseline; freshness can't regress without
  fetch_quotes; seeds reflect the change; pytest clean, idempotent.

## Constraints / notes
- Follow CLAUDE.md + docs/agent_handoff_workflow.md. Cowork has no DB access. Log every step
  + data point in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit — user commits from Windows.
