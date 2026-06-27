# TASK_90 — Re-plumb USD correlation onto the DAILY-loaded dollar/price data (+ dollar reconciliation)

**Type: diagnostic + implementation. Supersedes TASK_88** (the SPX source question is
folded in here). Two problems to solve together:

1. **Freshness (root cause).** The correlation reads `hist_quote_daily` (source='yfinance'),
   which is filled ONLY by the standalone `etl/fetch_quotes.py` pull — NOT wired into the
   daily pipeline, so it silently lags (it sat at 6/18 while the rest of the system was at
   6/23). Meanwhile the dollar + all asset prices ARE loaded every day into **`hist_y`**
   (from the YFiles/Yahoo daily load) and **TOS `$DXY`** — current to 6/23 — but the
   correlation never reads them.
2. **Dollar source mismatch (SPX residual).** Provider's 6/23 dollar ≈ **101.63**; our
   feeds all say **101.39** (TOS `$DXY` = 101.390; YFiles `^NYICDX` = 101.387; RR prev-close
   = 101.26). A level offset doesn't move correlation, but a different daily *path* does —
   likely source of the leftover SPX 15D/30D gap after the freshness fix.

DB + data work is yours. Log to `DEV_HANDOFF.md`, end `ALL_DONE`. **No commit.**

## Context — the two parallel Yahoo pipelines (confirmed by Cowork)
- `hist_quote_daily` (source='yfinance'): written ONLY by `etl/fetch_quotes.py`; read by
  `etl/derive_usd_correlation.py`. Symbols: `DX-Y.NYB`, `^GSPC`, `BZ=F`, `DBC`, `GC=F`,
  `BTC-USD`.
- `hist_y`: written by the **daily YFiles load** (`etl/yahoo_fetch.py`, `INSERT INTO hist_y`).
  Carries the same instruments under TOS/Yahoo names: dollar = **`^NYICDX`**, S&P = **`^SPX`**,
  plus `BZ=F`, `GC=F`, `BTC-USD`, `GLD`, `UUP`, `DBC?`. Current to 6/23.
- TOS daily: `$DXY`, `SPY`, etc. in `hist_tl`/`hist_td`/`drv_quote` (current to 6/23).

## Step 1 — Reconcile the dollar (and SPX) series, all sources, last ~20 trading days

Print side-by-side daily closes ending 6/23 for the **dollar**:
`hist_y.^NYICDX`, TOS `$DXY` (hist_tl max-seq EOD), and `hist_quote_daily.DX-Y.NYB`
(what the correlation uses now). Report each series' 6/23 value and whether any equals
the provider's ~101.63. Do the same for **SPX**: `hist_y.^SPX`, TOS `SPY`/`$SPX`,
`hist_quote_daily.^GSPC`.
- State which dollar series is closest to the provider, and — more importantly — compare
  the **day-to-day path** (e.g., daily % changes) across the three dollar series to see
  which one's *shape* over 15–30 days best reproduces the provider's correlations.
- If none hits 101.63: report what 101.63 could be (different vendor / a 6/24 value / an
  intraday print) so the user can confirm the provider's exact dollar instrument.

## Step 2 — Recompute SPX w15/w30 with each dollar series (price-levels Pearson, anchor 6/23)

| Variant | Dollar series | SPX series |
|---|---|---|
| A (current) | `DX-Y.NYB` (yfinance pull) | `^GSPC` (yfinance pull) |
| B | **`^NYICDX`** (daily hist_y) | `^GSPC` |
| C | **TOS `$DXY`** (daily) | `^GSPC` |
| D | TOS `$DXY` | **`^SPX`** (daily hist_y) / TOS `SPY` |

Also re-run the best variant at a **1-day-lag window (ending 6/22)** in case the provider's
"yesterday close" offsets the window. Report each variant's SPX w15/w30 vs provider
(−0.27 / −0.41) and identify which dollar/SPX source best matches.

## Step 3 — Re-plumb the correlation to the daily-loaded sources (if it helps or ties)

Goal: the panel rides the data that already loads every day, so it can NEVER silently
freeze again, and uses the dollar series closest to the provider.
- Update `ref_corr_asset.source_spec` (in `db/seeds_corr.sql`) to prefer the daily sources:
  e.g. USD → `["tos:$DXY"]` or a new `hist_y:^NYICDX` spec; SPX → `["tos:SPY","yfinance:^GSPC"]`
  ordered so the daily source wins, yfinance only as historical fallback.
- If `hist_y` needs a new `source_spec` prefix (e.g. `"histy:^NYICDX"`), add minimal
  support in `etl/derive_usd_correlation.py::_load_price_series` to read `hist_y`
  (mirror the existing `yfinance:`/`tos:` branches; map close column). Keep it small.
- Re-derive 6/23; confirm `/api/correlations` + panel now use the daily dollar and the SPX
  15D/30D are as close to the provider as Step 2's best variant. Note any change to the
  other asset rows.
- Keep yfinance as the deep-history fallback so long windows (90/120/180) still populate.
- CRB stays the known DBC-proxy gap. No commit.

## Step 4 — Recommend the auto-refresh wiring (propose, don't implement)

Once the panel reads daily-loaded data, the separate `fetch_quotes` lag stops mattering for
freshness. Still, recommend where to trigger any remaining backfill (Option C from TASK_89:
end of each TOSD load) so deep-history yfinance also stays current. Propose only.

## How to verify (Tester — on request, via AGENT_TASK.md)

1. Dollar reconciliation table printed; the source the panel now uses is stated with its
   6/23 value, and how it compares to the provider's ~101.63.
2. `SELECT asset_key,w15,w30 FROM drv_usd_correlation WHERE as_of_date='2026-06-23'
   AND asset_key='spx'` — closer to −0.27 / −0.41 than the post-TASK_89 baseline
   (−0.43 / −0.20). Document the delta and which source achieved it.
3. Panel/`/api/correlations` read the daily-loaded dollar (not the standalone yfinance
   pull); `db/seeds_corr.sql` reflects the source_spec change; fresh derive from seed
   reproduces it.
4. Freshness can't regress: with `fetch_quotes` NOT run, a new TOSD load + derive still
   produces a current-dated window (because it now reads the daily `hist_y`/TOS data).
5. `pytest tests/` clean; re-derive twice → identical rows (idempotent).

End `ALL_DONE`.
