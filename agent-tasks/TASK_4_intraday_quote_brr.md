# TASK 4 — Intraday quote vs stale technicals: fresh BRR/zone on live price

## Goal
After an intraday/post-market quote lands, `drv_quote.last_price` is fresh but
BRR/zone/trend-trade values in drv_technicals are EOD-stale — screens mix
timeframes on every price-relative signal. Recompute the price-relative fields
against the live quote.

## Scope
- `etl/derive.py::_derive_quote_impl` — extend drv_quote (columns in
  db/baseline.sql) with live-recomputed `pct_brr`, zone signal, distance to
  a_trend_value/a_trade_value (lines themselves stay EOD — only the price side
  is live). Reuse the zone classifier from `_derive_technicals_impl`; factor
  shared logic into `_derive_common.py`, do not duplicate.
- `api/routers/dash.py` + consuming JS (`web/actionable.js`, `web/app.js`) —
  prefer live drv_quote values when present; show a small "intraday" marker
  next to values computed off the live price.
- Out of scope: recomputing trend/trade lines intraday; rules-engine re-fire on
  intraday prices.

## Acceptance criteria
- After a Y/TOSL intraday load, drv_quote carries fresh pct_brr/zone consistent
  with the live price; screens label intraday-derived values.
- EOD-only days behave exactly as before (values match drv_technicals).

## How to verify (combined test round)
- Load an intraday Y file on a test date; compare drv_quote vs drv_technicals;
  hand-check pct_brr math for one symbol; screens + console clean; pytest.

## Constraints
- Follow CLAUDE.md (docs/derive_date_logic.md + dashboard_logic.md first).
  tos_symbol everywhere (rule 15). Idempotent derive.
