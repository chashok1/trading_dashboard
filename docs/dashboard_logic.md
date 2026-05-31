# Dashboard Logic

Deep-dive on the Dashboard screen: snapshot-date resolution, every API endpoint,
the UI sections, the latest-prices toggle, Portfolio and Today's Gain, and
realized P&L. `CLAUDE.md` carries only a one-line pointer to this file in its
Lookup index; keep the detail here.

## Overview

The Dashboard landing screen (`/`) is the single-page entry point that renders
the TL master ticker list for a chosen snapshot date, a morning briefing card,
an outlook-flip banner, plus three side-panel feeds (quads, econ indicators,
earnings events). All ticker data flows from `drv_dash` via `v_dash(D)`. The
Portfolio screen (`/portfolio`) is a separate screen that reads from
`hist_f`/`hist_cs` and the `drv_*` gain tables.

## Diagrams

- `docs/diagrams/3_dashboard_data_flow.svg` — **data flow**: upstream pipeline
  condensed, three source-table groups, three API endpoint groups, and the seven
  UI regions of the dashboard.
- `docs/diagrams/11_dashboard_logic.svg` — **decision logic**: snapshot-date
  resolution, API call chain, SQL function chain, COALESCE price merge, JSON
  response, and UI rendering.

Keep both diagrams in sync whenever this logic changes.

## Snapshot-date model

```
user picks date D
  → GET /api/dash?date=D
    → SELECT * FROM v_dash(D)
        → SELECT * FROM drv_dash WHERE as_of_date=D ORDER BY section, symbol
            ← populated by derive_all(D) → _derive_dash_impl
                ← drv_ma (for price/brr/outlook fields)
                ← drv_ma ← hist_* snapshots WHERE snapshot_date <= D + drv_quote COALESCE
```

> **Note:** `drv_ma` is a **VIEW** (since 2026-05-31) joining the 5 component tables
> (`drv_symbols`, `drv_technicals`, `drv_fundamentals`, `drv_outlooks`, `drv_portfolio`).
> Every `SELECT ... FROM drv_ma` above works transparently against the VIEW.

`_resolve_date(date)` (in `api/_helpers.py`) maps `None` to
`MAX(as_of_date) FROM v_available_dates`, where `v_available_dates` is a
`UNION DISTINCT` of `drv_dash` and `drv_stks` as_of_dates.

`v_dash(D)` and `v_dash_summary(D)` are thin wrappers:

| SQL function | Body |
|---|---|
| `v_dash(D)` | `SELECT * FROM drv_dash WHERE as_of_date=D ORDER BY section, symbol` |
| `v_dash_summary(D)` | `SELECT * FROM drv_dash_summary WHERE as_of_date=D` |
| `v_stks(D)` | `SELECT * FROM drv_stks WHERE as_of_date=D ORDER BY symbol` |
| `v_ma(D)` | `SELECT * FROM drv_ma WHERE as_of_date=D ORDER BY symbol` |
| `v_symbol_history(sym)` | `SELECT * FROM drv_ma WHERE symbol=sym ORDER BY as_of_date DESC` |
| `v_available_dates` | View: `DISTINCT as_of_date FROM drv_dash UNION drv_stks` |

Re-running `derive_all` for date D is idempotent (`DELETE WHERE as_of_date=D`
then INSERT). Only date D's derivatives change; no other date is touched.

## drv_dash table

PK `(as_of_date, section, symbol)`. Columns populated by `_derive_dash_impl`:

| Column group | Key columns |
|---|---|
| Identity | `section`, `symbol`, `description`, `sector`, `asset_class` |
| Price / technicals | `last_price`, `a_trend_value`, `a_trade_value`, `pct_brr`, `rr_brr` |
| Outlooks | `rr_outlook`, `call_outlook` |
| Zone | `threshold_low`, `threshold_high`, `zone_signal` |

`last_price` comes from `drv_ma`, which COALESCEs `drv_quote.last_price`
(latest-loaded-wins merge across hist_y/hist_tl/hist_td) with `hist_tl.last_price`.

## API endpoints

### GET /api/dates

In `api/routers/health.py`. Returns distinct `as_of_date` list from
`v_available_dates` (DESC). Used by the date picker in the UI header.

### GET /api/dash

In `api/routers/dash.py`. Query params: `date` (optional, default = latest),
`section` (optional filter). Calls `SELECT * FROM v_dash(:d)` (+ optional
`WHERE section=:sec`). Returns `list[DashRow]` — one row per symbol in
`drv_dash` for date D.

### GET /api/dash/summary

In `api/routers/dash.py`. Query param: `date`. Calls
`SELECT * FROM v_dash_summary(:d)`. Returns `DashSummary` (or null) — the
single `drv_dash_summary` row for date D: counts of bullish/bearish/neutral,
avg BRR, n_in_zone, n_above_trend, next econ event, next holiday.

### GET /api/briefing

In `api/routers/dash.py`. Query param: `date`. Assembles four independent
blocks for the morning briefing card, each in its own try/except so one
failure does not abort the rest:

| Block | Source | Description |
|---|---|---|
| `yesterday_actions` | `user_action_log LEFT JOIN drv_rule_outcome` | Up to 50 actions in the last 7 days with forward 5d return if known |
| `outlook_flips` | `v_outlook_changes(D)` | Count of non-HOLD actions today; top 5 held flips |
| `allocation_drift` | `drv_actionable JOIN ref_asset_allocation` | Categories outside [min_dollar, max_dollar] |
| `load_failures` | `meta_etl_run` | Files with status='error' in the last 36 hours |

Returns a dict with those four arrays plus `warnings` (names of any block that
threw).

### GET /api/outlook/changes

In `api/routers/dash.py`. Query params: `date`, `held_only` (bool), `limit`
(1–1000). Calls `SELECT * FROM v_outlook_changes(:d)` (optionally
`WHERE held_today=TRUE`). Returns one row per symbol with a non-HOLD action in
`drv_outlook_action` on date D. Shape per row: `symbol`, `n_sources_changed`,
`sources[]`, `actions[]`, `dominant_action` (REMOVE > REDUCE > ADD > INCREASE),
`held_today`, `total_delta`, `reasons[]`.

### GET /api/stks

In `api/routers/dash.py`. Query params: `date`, `sector`, `asset_class`,
`min_brr`, `max_brr`, `outlook`, `limit`. Joins `drv_ma` with `drv_stks` for
the given date D, returning full analytical columns (MA, BRR, outlooks, RSI,
IV, earnings_days, composite_outlook, triggered rule IDs).

### GET /api/dashboard/econ-indicators

In `api/routers/health.py`. Reads `ref_econ_indicator` (singular) where
`show_on_dashboard='Y'` (or `incl='Y'`), filtered to
`indicator_date >= D - 7 days`, sorted by date ASC.

### GET /api/dashboard/earnings

In `api/routers/health.py`. Reads `ref_calendar_event` for events between D
and D + `days_ahead`, excluding categories that match entries in
`ref_econ_indicator` (to prevent duplication with the econ panel).

### GET /api/dashboard/quads

In `api/routers/health.py`. Reads `ref_quad_periods` for: current quarter
containing D, next quarter, and 4 monthly periods (current + next 3).

## UI sections (index.html + app.js)

| UI region | ID / element | Data source |
|---|---|---|
| Index bar | `#indexBar` | Derived client-side from `state.rows` — locates SPX/VIX, NDX/VXN, RUT/RVX, DJI/VXD by symbol aliases and computes `(last_price − a_trade_value) / a_trade_value` |
| Outlook banner | `#outlookBar` | `GET /api/outlook/changes` — shows flip counts and up to 10 symbol chips; each chip links to `/trace` for that symbol |
| Briefing card | `#briefingCard` | `GET /api/briefing` — hidden when all four blocks are empty |
| Ticker grid | `#tickerSections` | `GET /api/dash` — grouped into section blocks, two-column layout; sections: Index · Treasury · Commodity · FX (left), Volatility · Sector (right), Stock (split A/B when >12 rows) |
| Quads panel | `#quadsBody` | `GET /api/dashboard/quads` |
| Econ indicators panel | `#econBody` | `GET /api/dashboard/econ-indicators` |
| Earnings/events panel | `#earningsBody` | `GET /api/dashboard/earnings` |

All six feeds load in parallel via `Promise.all` on page load and on Refresh.
The date picker populates from `/api/dates`; changing the date re-triggers all
six loads.

### Ticker grid columns

`Sym · %Chg · HE (rr_outlook) · TrTn (call_outlook) · MQ · QQ · Last ·
Trend (a_trend_value) · Trade (a_trade_value) · %BRR · Lo (threshold_low) ·
Hi (threshold_high)`

`%Chg` is computed client-side as
`(last_price − a_trade_value) / a_trade_value × 100`. Clicking a symbol opens
the Portfolio Detail modal (via `portfolio-modal.js` → `GET /api/portfolio/{symbol}/detail`).

## Latest-prices toggle (Portfolio screen)

On `GET /api/portfolio?latest_prices=true`, the server re-prices each held
position after building the base result set:

1. Find `MAX(as_of_date) FROM drv_quote` (`latest_dq_date`).
2. For held symbols, look up `drv_quote.last_price` at that date.
3. Look up `hist_td.last_price` at the snapshot immediately before
   `latest_dq_date` — that is `prev_close`.
4. Override on each row: `last_price = lp`, `market_value = qty * lp`,
   `today_gain_dollar = (lp − prev_close) * qty`,
   `today_gain_pct = (lp − prev_close) / prev_close * 100`,
   `total_gain_dollar = market_value − cost_basis`,
   `total_gain_pct = (market_value − cost_basis) / cost_basis * 100`.

The client-side Portfolio screen has its own "Latest prices" toggle that calls
the endpoint with `latest_prices=true` vs. `false`.

## Portfolio API

`GET /api/portfolio` (in `api/routers/dash.py`) returns a unified position list
across Fidelity (`hist_f`) and Schwab (`hist_cs`) using
`MAX(snapshot_date) <= D` for each source.

Additional decorations applied server-side after the base UNION:
- `sector` from `drv_dash` (latest as_of_date <= D)
- `consolidated_action`, `winning_source`, `suggested_target_dollar`, `in_my_list`
  from `drv_actionable` (latest as_of_date <= D)
- `ytd_gain_dollar`, `mtd_gain_dollar` (total_gain_dollar minus the baseline at
  Jan 1 / 1st-of-month snapshots)
- `pct_of_tp` = `market_value / ref_param['Tot Amt'] * 100`
- Position-limit decoration from `ref_asset_allocation` (category resolved via
  `hist_ps.asset_class` for PS winner, `hist_etf.asset_class` for ETF/ETFCHG
  winner, or `ref_outlook_source.position_category` otherwise): `limit_min`,
  `limit_max`, `limit_units`, `limit_maintain_min`, `limit_status`
  (BELOW_MIN / WITHIN / ABOVE_MAX / AT_FLOOR / NO_LIMIT).

`consolidated=true` sums across accounts per symbol (weighted avg_cost,
SUM(qty/mv/gains)).

### Cash detection

| Source | Fragment | Condition |
|---|---|---|
| Fidelity | `F_IS_CASH` | symbol = 'SPAXX**' OR description LIKE '%HELD IN MONEY MARKET%' |
| Schwab (standalone) | `CS_IS_CASH` | symbol = 'Cash & Cash Investments' OR security_type = 'Cash and Money Market' |
| Schwab (aliased `c.`) | `CS_IS_CASH_C` | Same as CS_IS_CASH but prefixed `c.` for JOIN contexts |

`F_IS_NOT_CASH` / `CS_IS_NOT_CASH` / `CS_IS_NOT_CASH_C` are `NOT` inverses of
the above, used to exclude cash from P&L and market-value totals.

## Today's Gain (Schwab-style)

Computed in `GET /api/portfolio/summary`. The headline `today_gain_dollar` is:

```
SUM(hist_cs.day_chng_dollar for held non-cash positions)
+ SUM((sell_price - yesterday_close) * abs(qty) for sell events in hist_cst today)
+ SUM(amount for DIV/INT/REINV events in hist_cst today)
```

`yesterday_close` = `hist_cs.price` at the snapshot immediately before today's
CS snapshot. Fidelity positions add `today_gl_dollar` directly (Fidelity
already computes it). The per-account breakdown uses the same three-part formula
per CS account.

`realized_today_dollar` is read directly from `drv_cs_realized_gain` at the
current CS snapshot date, capturing sold-out positions that no longer appear in
`hist_cs`.

## Realized P&L

Two FIFO tables:

| Table | Source | Endpoint |
|---|---|---|
| `drv_realized_gain` | Fidelity (`hist_f`/`hist_ft`) | `GET /api/portfolio/realized` |
| `drv_cs_realized_gain` | Schwab (`hist_cs`/`hist_cst`) | Same endpoint; union handled internally |

`GET /api/portfolio/realized` supports three `group_by` shapes:

| `group_by` | Shape | Use |
|---|---|---|
| `symbol` (default) | One row per symbol: totals + YTD + MTD | Summary tab |
| `account` | One row per account: totals + YTD + MTD | Account rollup |
| `none` | Raw sell-event rows with `lots_consumed` | Per-sale drilldown |

YTD = `sell_date >= Jan 1 of anchor date`. MTD = `sell_date >= 1st of anchor month`.
`is_long_term` is set by the FIFO matcher when holding period > 365 days.

## Re-derive

After editing derive logic that affects dashboard columns:

```bash
python -m etl.derive      # re-derive for all affected dates
# or trigger via File Monitor "Run Missing Derives"
```

`derive_all` is idempotent — safe to re-run for any date.
