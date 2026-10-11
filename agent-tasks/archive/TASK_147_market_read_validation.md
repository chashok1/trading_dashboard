# TASK_147 — Validation: does theme stance predict anything?

## Context

Standing rule (Addendum E3): nothing from Market Read may influence an
action until its own forward-return scorecard is positive on ≥ 30 samples.
This task builds that scorecard. Report-only; nothing ships to the decision
path. Needs TASK_143/144.

## Goal

1. **`v_theme_stance_scorecard`** (`db/baseline.sql`): per theme × stance
   (B/S) × source cell (RR, ETF, PS, SSS, CALL, Price, and the combined
   `stance`), direction-adjusted forward 5d/20d return of the theme's proxy
   ETF (`ref_symbol_theme` → the ETF-side symbol; e.g. Small caps → IWM,
   Credit → HYG, Energy → XLE), `n`, win rate, 95% CI — same conventions as
   `v_source_edge_scorecard`. Also by `agree_n` bucket (1 / 2 / 3–4) and by
   `quad_conflict` (true/false): does agreement help, does conflict hurt.
2. **`v_sss_sector_scorecard`**: per sector, does a 4-week change in `n_rows`
   and in `book_size` (separately) predict the sector proxy ETF's forward
   20d return; and does `divergence` (rows down, book flat/up) predict
   anything.
3. **`v_source_breadth_scorecard`**: does each list's breadth turning (net
   crossing 0, rows −25% in 4 wk, RR flip-day) precede SPX 20d drawdowns.
4. **Report** `docs/audit/market_read_validation_2026-09.md`, same shape as
   `signal_validation_2026-09.md`: every table with `n`, HELD / THIN
   verdicts, and — for each of the 22 themes — one line: which source cell
   (if any) has a positive, ≥30-sample edge. Where history is < 30 samples
   (most weekly series will be), say so; the report's job is to establish
   the baseline the nightly refresh grows from.
5. Wire all three views' underlying forward-return refresh into
   `run_nightly_outcomes()` (same pattern as TASK_138), so the numbers stay
   current without a manual step; add freshness contract rows.

## Files expected to change

- `db/baseline.sql`, `etl/scheduler.py`
- `docs/audit/market_read_validation_2026-09.md` (new)
- `docs/migrations.md`, `DEV_HANDOFF.md`

## How to verify

1. Views exist and return rows for every theme with a proxy ETF; themes
   without one (Volatility, Breadth) are listed as excluded, not silently
   missing.
2. Report present with `n` on every table; no verdict rests on n < 30.
3. Nightly job log shows the refresh step; `daily_health_check` shows the
   contract rows.
4. Nothing in `derive_actionable.py`, `ref_trig_*`, `ref_settings` decision
   switches, or `ref_risk_gauge.is_active` changed (diff the files).
