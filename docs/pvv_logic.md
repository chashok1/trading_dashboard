# PVV — Price/Volume/Volatility multi-bucket signal (TASK_125, decision layer TASK_127)

Informational v1: `drv_pvv` computes a Price/Volume/Volatility (PVV,
Hedgeye-style ROC) signal in 4 time buckets per symbol (TASK_125, unchanged),
then consolidates into one decision (`BUY`, `BUY_DIP`, `REDUCE`, `AVOID`,
`SELL`, `TRIM`, `WATCH`) via RR outlook × `sig_today` (TASK_127 — see §4;
`sig_5d`/`sig_3w`/`sig_3m` are now display-only context, not decision
inputs). Surfaced as a new **PVV** column on the Actionable screen with a
rich hover tooltip. **Not wired into `consolidated_action` / `drv_actionable`
scoring** — a later task may do so once the signal has been validated.

Code: `etl/derive_pvv.py` (deriver + pure classification functions),
wired into `derive_all()` in `etl/derive.py`. Runs after `trend_trade_rules`
and `drv_rr_outlook_from_qe` (2026-08-15 — moved from right after the 5
`drv_ma` component tables; see §4's now-fixed BB-fallback note) since it
needs both `drv_technicals` (`vlm_projected`/SMAs) and a *resolved*
`drv_rr.outlook`, and before `drv_dash`. API: `api/routers/dash.py`
(`/api/actionable`, LEFT JOIN on
`drv_pvv`). UI: `web/actionable.js` / `web/actionable.html` (PVV column,
`_pvvCellHtml`, `_buildPvvPopHtml`, `data-pvvpop` hover mechanism). Table:
`drv_pvv` in `db/baseline.sql`. Tests: `tests/test_pvv_classify.py` (pure
Python), `tests/acceptance/test_task_125_pvv_buckets.py`.

---

## 1. Table

```sql
CREATE TABLE IF NOT EXISTS drv_pvv (
    as_of_date  DATE NOT NULL,
    tos_symbol  TEXT NOT NULL,
    sig_today   TEXT,        -- signal code per bucket (see §3)
    sig_5d      TEXT,
    sig_3w      TEXT,
    sig_3m      TEXT,
    decision    TEXT,        -- consolidated (see §4)
    detail      JSONB,       -- per-bucket inputs for the tooltip (see §5)
    derived_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (as_of_date, tos_symbol)
);
```

Idempotent derive: `DELETE WHERE as_of_date=D` → INSERT. `tos_symbol` only,
never raw `symbol`. Universe = `drv_symbols` for D.

## 2. Bucket inputs (per tos_symbol, anchor date D)

| Bucket | Price ROC | Volume ROC | Volatility ROC | Flat band |
|---|---|---|---|---|
| `today` | live price vs prior settled TD close (or, once today's own TD close has loaded — see below — that close vs the day before) | drv_technicals.vlm_projected vs 20d avg EOD volume | live IV vs prior settled TD IV (same today/settled split as price) | **1.0σ** (alert-only, wide) |
| `5d` | 5d ROC of hist_td last_price | 5d ROC of EOD volume | 5d ROC of hist_td imp_volatility | 0.5σ |
| `3w` | 15d ROC of hist_td last_price | 15d ROC of EOD volume | 15d ROC of imp_volatility | 0.5σ |
| `3m` | structure, not ROC (see below) | none (skip) | iv_percentile level | n/a |

- **`today` price/IV, two cases (2026-08-15 fix)**: D is *defined* as
  `MAX(export_date) FROM hist_td`, so once today's TOSD (EOD) file has
  loaded there's always a settled TD row for D itself — at that point
  there's no fresher live price/IV left to compare against, so the window
  shifts back one day (D's close vs D-1's) instead of comparing D's close
  to itself. **Still intraday** (D's TOSD row hasn't loaded yet, so the
  most recent TD row is genuinely yesterday's close): unchanged, live
  price/IV (`drv_technicals`, same source as `drv_quote.pct_change` on the
  Actionable grid) vs that settled close — the normal case while actively
  trading. Before this fix, the settled case always produced a false 0%
  ROC (comparing D's close to itself), not a "flat trading" reading — see
  `etl/derive_pvv.py::_today_rocs`.
- **EOD volume** = hist_tl volume at max(sequence) per export_date per
  symbol (hist_td has no volume column). Built via `_fetch_daily_tl_volume`.
  Missing days fall back to the nearest value within a 3-calendar-day
  tolerance (`_series_value_near`); if fewer than `min_window_pts` (3)
  usable points exist in a window, the bucket signal is `NA`.
- **`vlm_projected` intraday curve (2026-08-15 fix)**: `drv_technicals.vlm_projected`
  (the "today" volume ROC's numerator) used to assume a flat, constant
  trading pace all day (`volume_so_far × 390 ÷ minutes_elapsed`). User:
  "if the volume is doubled in a few minutes then intraday calc will not be
  correct... I need proper values otherwise no point in using it." Measured
  against this system's own history (55,487 symbol-days, 52 distinct days):
  only ~67% of a day's eventual total volume has typically happened with 30
  minutes left in the session — the closing auction alone is roughly a
  third of a typical day — so the flat assumption chronically
  **under**-projected the full-day total at every point in the day, not
  just near the close (backtested median error: **-27.3%**, i.e. a
  systematic low bias, not noise). Replaced with a lookup against
  `ref_vlm_intraday_curve` — a 30-minute-bucket empirical "typical % of the
  day's volume done by now" curve computed from `hist_tl` history
  (`etl/derive_vlm_intraday_curve.py` — periodic tunable-table refresh, not
  part of the daily `derive_all()` cascade, same spirit as
  `etl/refresh_ref.py`). Runs automatically once a day via
  `etl/scheduler.py`'s nightly job whenever the scheduler is running; can
  also be run by hand (`python -m etl.derive_vlm_intraday_curve`).
  Backtested median error after the fix: **-0.7%** (effectively unbiased —
  expected, since the curve is literally built from the median of this same
  data). Individual symbol-days still vary (p25/p75 roughly -26%/+32%,
  vs -45%/-3% before) — that's real day-to-day variance, not something a
  single number can eliminate, but the systematic downward bias is gone.
  No calibration data exists for the first ~30 minutes after the 9:30 open
  (`ref_vlm_intraday_curve` has no bucket that early) — `vlm_projected`
  stays `NULL` there, same "insufficient data" convention as elsewhere,
  rather than guessing. This also improves the "Proj Volume" tooltip value
  shown elsewhere on the Actionable grid's Vlm column, since both read the
  same `drv_technicals.vlm_projected` column.
- **Flat band**: `|ROC| < k × σ`, where σ is the trailing standard deviation
  of that symbol's own rolling-ROC(horizon) series (up to `sigma_window`=60
  trailing daily observations, minimum `sigma_min_obs`=20). When a symbol
  doesn't have enough own history, σ falls back to the **cross-sectional**
  stdev of that day's raw ROC values across the whole universe for the same
  bucket/leg (computed in a first pass, then applied in a second pass —
  see `_derive_pvv_impl`'s two-pass design). If neither is available, the
  band is 0 (direction resolves on sign only, never `flat`).
- **IV null fallback** (futures/indices with no `imp_volatility`): use
  `historical_vol` for that leg; `detail.<bucket>.vol_src` records `"iv"` or
  `"hv"` accordingly. The 3m bucket falls back to `hv_percentile` when
  `iv_percentile` is null.
- **3m bucket**: price direction = ↑ if `last_price > sma_50 AND sma_50 >
  sma_200`; ↓ if `last_price < sma_50 AND sma_50 < sma_200`; else Flat. Vol
  direction = ↑ if `iv_percentile ≥ 70`, ↓ if `≤ 30`, else Flat.

### 3w gate

After classifying 3w, `_apply_3w_gate` demotes one notch toward NEUTRAL when
price hasn't confirmed `a_trend_value`: bullish but `last_price <
a_trend_value` → `STRONG_BULL→WEAK_BULL`, `WEAK_BULL→NEUTRAL`; mirror for
bearish above `a_trend_value` (`STRONG_BEAR→MILD_BEAR`,
`MILD_BEAR→NEUTRAL`). `OVEREXT_BULL`/`BEAR_LEAN`/`BEAR_DIV` are not demoted.
`detail.w3.gated` records whether the demotion fired.

## 3. Per-bucket signal table

| Price | Volume | Vol | Code |
|---|---|---|---|
| ↑ | ↑ | ↓ | `STRONG_BULL` |
| ↑ | ↑ | ↑ | `OVEREXT_BULL` |
| ↑ | ↓ | ↓ | `WEAK_BULL` |
| ↑ | ↓ | ↑ | `BEAR_DIV` |
| ↓ | ↑ | ↑ | `STRONG_BEAR` |
| ↓ | ↑ | ↓ | `MILD_BEAR` |
| ↓ | ↓ | ↓ | `DRIFT` |
| ↓ | ↓ | ↑ | `BEAR_LEAN` |
| Flat price | any | any | `NEUTRAL` |
| insufficient data | | | `NA` |

Volume Flat resolves toward ↓ (unconfirmed); Vol Flat resolves toward ↓
(calm). 3m bucket has no volume leg — classified on Price/Vol only:
↑ + vol↓ = `STRONG_BULL`, ↑ + vol↑ = `OVEREXT_BULL`, ↓ + vol↑ =
`STRONG_BEAR`, ↓ + vol↓ = `DRIFT`, Flat = `NEUTRAL`.

Pure functions (unit-testable, no DB): `classify_pvv(p_dir, v_dir, vol_dir)`
and `classify_pvv_3m(p_dir, vol_dir)` in `etl/derive_pvv.py`.

## 4. Consolidated decision — RR outlook × sig_today (TASK_127)

As of TASK_127, `decide_pvv(sig_today, outlook)` is a straight 9×3 lookup:
**RR outlook decides WHAT** (direction), **sig_today decides WHEN**
(timing). `sig_5d`/`sig_3w`/`sig_3m` no longer feed the decision — they
remain display-only context in `detail` and the tooltip. This replaced the
prior 5d/3w/3m bucket-alignment matrix (TASK_125) entirely.

**Outlook input**: `drv_rr.outlook` for `(as_of_date=D, tos_symbol)` —
`'Bullish'`/`'Bearish'`/`'Neutral'` (case-insensitive, trimmed). `NULL`
(missing row) and any unrecognized string (e.g. a `source='BB'` gradation
like `'Light Bullish'`/`'Mild Bearish'` — see below) both resolve to "no
outlook", which behaves identically to `Neutral`.

**BB-fallback outlook timing (fixed 2026-08-15)**: `derive_pvv` used to run
*before* `_derive_rr_outlook_from_qe`'s second-pass UPDATE (`etl/derive.py`),
so every `source='BB'` row was still `outlook=NULL` at read time — not an
edge case, the normal daily result (measured: 73% of that day's `WATCH`
rows). `derive_pvv` now runs in `derive_all()` *after*
`_derive_rr_outlook_from_qe`, so BB-fallback rows see their filled-in
outlook the same as everything else. A **standalone** re-derive of
`drv_pvv` alone (e.g. a drv_pvv-only backfill loop, outside the full
cascade) still just reads whatever `drv_rr.outlook` is *currently* stored
for that date — fine as long as it's run after a full cascade has already
filled it in. `_normalize_outlook()` treats a BB gradation the same either
way: exact (trimmed, case-insensitive) `'Bullish'`/`'Bearish'`/`'Neutral'`
match; anything else (including `'Light Bullish'`) → no outlook → `WATCH`
column.

| sig_today ↓ \ outlook → | **Bullish** | **Bearish** | Neutral / NULL |
|---|---|---|---|
| `STRONG_BULL` | `BUY` | `TRIM` | `WATCH` |
| `WEAK_BULL` | `BUY` | `TRIM` | `WATCH` |
| `OVEREXT_BULL` | `TRIM` | `TRIM` | `WATCH` |
| `BEAR_DIV` | `WATCH` | `TRIM` | `WATCH` |
| `NEUTRAL` / `NA` | `WATCH` | `AVOID` | `WATCH` |
| `DRIFT` | `BUY_DIP` | `AVOID` | `WATCH` |
| `MILD_BEAR` | `BUY_DIP` | `REDUCE` | `WATCH` |
| `BEAR_LEAN` | `BUY_DIP` | `REDUCE` | `WATCH` |
| `STRONG_BEAR` | `WATCH` *(knife guard)* | `SELL` | `WATCH` |

Notes:
- **Knife guard**: bullish outlook + `STRONG_BEAR` sig_today (a heavy-
  volume selloff day) deliberately does **not** fire `BUY_DIP` — it waits
  at `WATCH` rather than trying to catch a falling knife.
- **Sell the rip**: bearish outlook + any up-tape sig_today
  (`STRONG_BULL`/`WEAK_BULL`/`OVEREXT_BULL`/`BEAR_DIV`) consolidates to
  `TRIM`.
- `TRIM` and `WATCH` each map from multiple matrix cells (see table); `BUY`
  and `BUY_DIP` are Bullish-outlook-only; `SELL`/`REDUCE`/`AVOID` are
  Bearish-outlook-only.
- Decision vocab unchanged from TASK_125 (`BUY`, `BUY_DIP`, `TRIM`, `WATCH`,
  `AVOID`, `REDUCE`, `SELL`) — no badge/sort-rank changes needed.

Pure functions in `etl/derive_pvv.py`: `_normalize_outlook(outlook)` (case-
insensitive/trim → `'Bullish'`/`'Bearish'`/`'Neutral'`/`None`) and
`decide_pvv(sig_today, outlook)` (the matrix lookup above, via
`_PVV_DECISION_MATRIX`).

## 5. `detail` JSONB shape (drives the tooltip)

```json
{"today": {"sig":"MILD_BEAR","p_roc":-0.012,"v_roc":0.35,"vol_roc":-0.04,
           "p_dir":"down","v_dir":"up","vol_dir":"down","vol_src":"iv"},
 "d5":    {...}, "w3": {..., "gated": false}, "m3": {"sig":"STRONG_BULL",
           "price_vs_sma50": 1.03, "sma50_vs_sma200": 1.02, "iv_pctile": 22},
 "outlook": {"value": "Bullish", "source": "RR"}}
```

`detail.outlook.value` is `"Bullish"`/`"Bearish"`/`"Neutral"`/`null`
(normalized display label — see §4); `detail.outlook.source` is
`"RR"`/`"BB"`/`null` (from `drv_rr.source`, `null` when there's no
`drv_rr` row for the symbol at all).

## 6. API

`GET /api/actionable` LEFT JOINs `drv_pvv` on `(tos_symbol, as_of_date)` and
adds `pvv_decision` (= `drv_pvv.decision`) and `pvv_detail` (=
`drv_pvv.detail`, JSONB) to each row. NULL-safe when a symbol has no
`drv_pvv` row yet (e.g. insufficient history).

## 7. UI

New **PVV** column (toggleable via the gear menu, visible by default) shows
a colored decision badge (`_pvvCellHtml`), reusing the existing
`.act-badge` tint classes: `BUY`→act-buy-strong-tint, `BUY_DIP`→
act-buy-tint, `SELL`→act-sell-strong-tint, `REDUCE`→act-sell-tint,
`TRIM`/`AVOID`→act-sell-weak-tint (amber), `WATCH`→act-neutral-tint (gray).
Hover (`data-pvvpop` + `_showDataPop`, same mechanism as the MACRO/Vol/IV
popovers) shows a 4-row table (Today/5d/3w/3m) with the signal code, P/V/Vol
arrows, and ROC percentages from `pvv_detail`; gated 3w rows show
`(gated)`; HV-fallback legs show `[hv]`.

Sortable by `_pvv_rank` (ascending = most actionable first): `BUY_DIP`(0) <
`BUY`(1) < `SELL`(2) < `REDUCE`(3) < `TRIM`(4) < `AVOID`(5) < `WATCH`(6) <
no-row(7).

## 8. Config

All thresholds live in `etl/derive_pvv.py::PVV_CONFIG` (module-level
constants for v1 — a later task may move them to `ref_param` for
tunability without a code deploy): flat-band multipliers per bucket, the
60-obs/20-min sigma window, iv_percentile 70/30 thresholds for the 3m
bucket, the minimum-window-points NA guard, the 180-day history lookback,
and the 20-day EOD-volume averaging window for `today`.
