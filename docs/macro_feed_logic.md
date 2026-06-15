# Macro feed (FRED) — logic

Economic data + end-of-day index levels, pulled from the **FRED API**
(Federal Reserve Economic Data, St. Louis Fed). This is the macro/regime
context layer — distinct from the per-symbol pipeline. It powers the cockpit's
market-context band (`GET /api/macro`).

## Why it's separate

The 17 source feeds are all *stock-level*. Indexes and economic data aren't in
any of them. FRED fills that gap with one free API key, and for an EOD workflow
it covers **both** halves: it carries economic series *and* EOD equity index
levels (`SP500`, `NASDAQCOM`, `DJIA`, `RU2000PR`, `VIXCLS`). Index levels lag
~1 day and have no intraday — fine for regime context off EOD TOS exports.

It is also the only **pull** ingest (not a watched file drop), so it is **not**
wired into `etl/scheduler.py`. Run it on a daily schedule after the US close.

## Relationship to existing econ tables

`ref_econ_indicator` / `ref_calendar_event` are workbook-sourced and hold
*which* events/indicators and their *expected* values. `hist_macro` holds the
actual *observed* time series from FRED. Complementary, not overlapping. A
future enhancement could map `ref_macro_series.series_id` to those labels.

## Schema (db/baseline.sql)

- `ref_macro_series` — tunable catalog: `series_id` (PK, FRED id), `label`,
  `grp` (`rates|inflation|jobs|risk|index|fx_cmdty`), `unit`, `sort_order`,
  `enabled`. Seeded by `db/seeds_macro.sql` (~20 series). Edit + re-run
  `python -m db.init_db` to change which series are pulled / how they display.
- `hist_macro` — raw observations, append-only. PK `(series_id, obs_date)`.
  `value` is `NULL` when FRED reports `"."`. Loaded with `ON CONFLICT DO
  NOTHING` (convention 1) — FRED revisions to past dates are intentionally not
  overwritten; the displayed "latest" is always the newest `obs_date`, freshly
  inserted each run. (Point-in-time vintages would need FRED's ALFRED — not
  used here.)
- `v_macro_latest` — view: latest + prior non-null observation per enabled
  series with `chg_abs` and `chg_pct`. Consumed by the API.

## Ingest (etl/fetch_macro.py)

Reads enabled rows from `ref_macro_series`, calls the FRED observations
endpoint per series (stdlib `urllib`, no new dependency), upserts into
`hist_macro`.

```cmd
python -m etl.fetch_macro                 :: latest ~120 obs per enabled series (throttled)
python -m etl.fetch_macro --full          :: full history (first backfill)
python -m etl.fetch_macro --force         :: ignore the throttle and fetch now
python -m etl.fetch_macro --limit 5       :: just the most recent few
python -m etl.fetch_macro --series DGS10  :: one series only
```

Requires `FRED_API_KEY` in `.env` (free key:
https://fred.stlouisfed.org/docs/api/api_key.html). `config/settings.py` exposes
it as `settings.fred_api_key`.

## API (api/routers/macro.py)

`GET /api/macro` → `{ "as_of": <newest obs date>, "groups": { <grp>: [ {series_id,
label, unit, latest_value, latest_date, prior_value, prior_date, chg_abs,
chg_pct}, ... ] } }`. Groups ordered index → rates → inflation → jobs → risk →
fx_cmdty. Registered in `api/main.py`.

## Rate-limit protection (throttle)

FRED allows 120 requests/minute; a full fetch is only ~19 (one per enabled
series), so the limit is hard to hit — but to stop accidental repeated runs from
stacking up, `fetch_macro` is **throttled**:

- Every real run is logged to `meta_macro_fetch` (operational; skipped/throttled
  runs are NOT logged). The throttle reads the last `started_at` from it.
- If the last real run started within the throttle **window**, the call is a
  no-op returning `{"skipped": true, "reason": "throttled", "age_min": N}`.
  `--force` (CLI) overrides.
- The window is tunable via `ref_settings.macro_fetch_min_interval_min`
  (default seeded at **360** = 6h). Change without code edits:
  `UPDATE ref_settings SET setting_value='120' WHERE setting_name='macro_fetch_min_interval_min';`
  Precedence: explicit `min_interval_min` arg / `--min-interval` → ref_settings →
  code default (`DEFAULT_MIN_INTERVAL_MIN`).

### Reads never call FRED

`GET /api/macro` only queries `v_macro_latest` (the DB) — opening/refreshing the
screen is **zero** FRED requests, regardless of frequency. Fresh data only enters
via a `fetch_macro` run.

### Manual refresh button

`POST /api/macro/refresh` runs a **throttled** fetch (trigger `api`, not forced),
so repeated clicks cannot stack up requests — within the window it just returns
the skipped/throttled status. `GET /api/macro` also returns a `last_fetch` block
(started_at, status, rows_inserted, ...) for a "last fetched" stamp next to the
button.

## UI — Actionable "Market context" band

`web/macro_band.js` (loaded by `web/actionable.html`) renders a collapsible
"Market context" card at the top of the Actionable screen (`/actionable`), above
the toolbar. It is self-contained (own file, inits on DOMContentLoaded) so it
can't disturb the actionable logic. (The `/cockpit` route now 301-redirects to
`/actionable`.)

- Reads `GET /api/macro` and renders one section per group (Indexes, Rates &
  curve, Inflation, Jobs, Risk, Dollar & commodities), each a grid of tiles
  (label, value formatted by unit, change, observation date).
- Change shown as absolute points for `%` series (yields/unemployment/spreads)
  and percent for the rest; green up / red down.
- "Refresh data" button → `POST /api/macro/refresh` (throttled). If the server
  returns `skipped`, the stamp shows "Up to date (fetched Nm ago)"; otherwise
  the band reloads with fresh values. The header also shows `as of <date>` and
  an "updated <relative>" stamp from `last_fetch`. Reads never hit FRED.

## What FRED does NOT provide

- Live (intraday / sub-second) index prices — add a quotes API later if wanted.
- A forward economic *calendar* (release date/times) — `ref_calendar_event`
  partially covers this from the workbook.

## First-run checklist

1. Add `FRED_API_KEY=...` to `.env`.
2. `python -m db.init_db`  (creates tables/view + seeds the catalog).
3. `python -m etl.fetch_macro --full`  (backfill), then daily `python -m etl.fetch_macro`.
4. Check `GET /api/macro`.
