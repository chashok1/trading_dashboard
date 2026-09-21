# TASK_146 — Risk Dial: positioning gauges + freshness cap

## Context

Design Addendum H. All 31 gauges in `ref_risk_gauge` are price / vol /
macro-data reads; none reads Hedgeye's own list positioning. Needs TASK_143
(`drv_source_breadth`, `drv_theme_stance`) and TASK_144 (`drv_sss_breadth`).

## Goal

1. **Six new gauges** in `ref_risk_gauge` (`db/seeds_risk_gauge*.sql`),
   `category='positioning'` (last one `'self'`), computed in
   `etl/derive_risk_dial.py` in the same shape as the existing `_g_*`
   functions (one condition → `fired` + a detail line naming the numbers):

   | gauge_key | fires when | weight |
   |---|---|---|
   | `lists_derisking` | ≥3 of 4 lists (RR macro net, ETF net, PS count, SSS rows) down >25% vs 4 weeks ago | 3 |
   | `etf_net_short` | ETF longs − shorts ≤ 0 | 2 |
   | `sss_book_collapse` | SSS rows down ≥40% from 4-week high | 2 |
   | `rr_flip_day` | RR `flips_vs_prior` ≥ 9 within the last 3 sessions | 1 |
   | `lists_quad_conflict` | ≥4 themes with `quad_conflict` | 2 |
   | `exposed_bear_themes` | risk $ in bear-stance themes >15% of risk $ (`drv_category_perf` via `ref_symbol_theme`) | 1 |

   Thresholds go in `ref_settings` (`rd_lists_derisk_pct` 25, `rd_sss_collapse_pct`
   40, `rd_rr_flip_min` 9, `rd_conflict_min` 4, `rd_exposed_pct` 15) — the
   defaults are what this session's data showed, not tuned.

2. **Ship them `is_active = FALSE`.** Before activation, backfill the dial for
   the last 30 anchor dates twice — current gauges only, and with the six —
   and put both `risk_budget` series side by side in `DEV_HANDOFF.md`, with
   which new gauges fired on each date. The user sets weights/activation
   from that table (Addendum H rule 2). Do not activate in this task.

3. **Freshness cap (not a gauge).** When `daily_health_check`'s
   `_check_stale_analytics` (TASK_142) reports a breach on any table the
   dial reads, `drv_market_stat.risk_label` is unchanged but the API
   (`/api/cockpit/risk-dial`) returns `stale_as_of`, and `web/risk_dial*.js`
   suffixes the label ("CAUTION · edge data as of <date>"). The number never
   moves for staleness.

4. Gauge scorecard: extend the existing rule-scorecard convention with
   `v_risk_gauge_scorecard` — per gauge, did it fire in the 20 sessions
   before each SPX 20d drawdown ≥ 5% (hit) vs elsewhere (false alarm), over
   the available history. Report-only.

5. Docs: `docs/migrations.md`; `docs/dashboard_cockpit_design.md` §3.2 gauge
   table gains the six rows.

## Files expected to change

- `db/baseline.sql`, `db/seeds_risk_gauge*.sql`, `etl/derive_risk_dial.py`
- `api/routers/cockpit.py`, `web/risk_dial*.js` (whichever renders the label)
- `docs/migrations.md`, `docs/dashboard_cockpit_design.md`, `DEV_HANDOFF.md`

## How to verify

1. `python -m db.init_db` idempotent; six rows present, `is_active=FALSE`;
   `python -m etl.derive_risk_dial` output byte-identical to before for the
   anchor (inactive gauges don't touch the budget).
2. Force-activate in a session, re-derive 2026-09-21: `lists_derisking`,
   `etf_net_short`, `sss_book_collapse`, `rr_flip_day`, `lists_quad_conflict`
   fire; `exposed_bear_themes` quiet (~8%). Detail lines show the numbers
   (e.g. "ETF Pro 17 L / 20 S"). Deactivate again before `ALL_DONE`.
3. 30-date before/after budget table in the handoff.
4. Force a freshness breach (TASK_142 step 3 method) → dial label carries
   the suffix, `risk_budget` unchanged; clear it → suffix gone.
5. `v_risk_gauge_scorecard` returns a row per gauge with hit / false-alarm
   counts; note the SPX-drawdown sample size honestly (likely small).
