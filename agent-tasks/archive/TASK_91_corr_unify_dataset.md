# TASK_91 — Put ALL correlation assets on the same daily dataset (hist_y)

**Type: implementation + verification.** TASK_90 moved USD + SPX to `histy:` but left
Brent/CRB/Gold/Bitcoin on the separate `yfinance:` pull — so each of those is correlated
against a **dollar from a different dataset/snapshot time than itself**, injecting noise
(this is why Gold 15D regressed while SPX, now both-legs-hist_y, snapped to the provider).
A correlation is only clean when both legs are the **same source at the same timestamp**.
The provider uses one consistent EOD dataset for the whole table; we should too. Cowork
confirmed the daily YFiles load (`hist_y`, 16:30 EOD) carries **`BZ=F`, `GC=F`, `BTC-USD`**
(and `GLD`, `^NYICDX`, `^SPX`) — all present on 6/23. Only `DBC` (CRB proxy) is absent.

DB + data work is yours. Anchor 2026-06-23. Log to `DEV_HANDOFF.md`, end `ALL_DONE`.
**No commit.**

## Change — `db/seeds_corr.sql` source_spec (prefer histy, yfinance as history fallback)

```sql
('usd',     '$USD Index', '["histy:^NYICDX","yfinance:DX-Y.NYB"]',  TRUE,  0,  TRUE),
('spx',     'S&P 500',    '["histy:^SPX","yfinance:^GSPC"]',        FALSE, 10, TRUE),
('brent',   'Brent Oil',  '["histy:BZ=F","yfinance:BZ=F"]',         FALSE, 20, TRUE),
('crb',     'CRB (proxy)','["yfinance:DBC","tos:DBC"]',             FALSE, 30, TRUE),  -- unchanged: DBC not in YFiles
('gold',    'Gold',       '["histy:GC=F","yfinance:GC=F"]',         FALSE, 40, TRUE),
('bitcoin', 'Bitcoin',    '["histy:BTC-USD","yfinance:BTC-USD"]',   FALSE, 50, TRUE),
```

(The `histy:` read branch already exists in `derive_usd_correlation.py::_load_price_series`
from TASK_90 — no new code needed. Confirm it handles these symbols.)

## Step 1 — Confirm hist_y coverage for each asset

For `BZ=F`, `GC=F`, `BTC-USD` (and `^NYICDX`,`^SPX`): print `MIN/MAX(export_date)`, row
count, and the last ~20 daily closes from `hist_y`. Verify enough history for w15/w30
ending 6/23 with no interior gaps; note where the yfinance fallback takes over for the
older part of the 90/120/180 windows. Flag any weekend/holiday rows (the `histy:` branch
already filters Sat/Sun).

## Step 2 — Re-derive 6/23 and compare the FULL table to the provider

Re-derive and print all five assets w15/w30/w90 vs the provider target:

```
asset     15D     30D     90D
SPX      -0.27   -0.41   -0.02
Brent    -0.70   -0.76    0.11
CRB       0.00    0.00    0.36   (proxy placeholder — ignore short windows)
Gold     -0.70   -0.87   -0.60
Bitcoin  -0.33   -0.72   -0.55
```

Report per-cell delta. **Key question: does unifying on hist_y recover Gold 15D**
(TASK_90 left it at −0.51 vs −0.70) **and hold/improve Brent + Bitcoin, without
regressing SPX** (−0.26 vs −0.27)? Show before (TASK_90) vs after (TASK_91) for all five.

## Step 3 — Verdict + remaining residuals

- State which assets now match within ~0.10 at 15D/30D and which don't.
- For any residual, attribute it: provider dollar instrument (the unexplained ~101.63 ICE
  USDX-futures-vs-NYICDX-spot question), CRB proxy, or hist_y history depth.
- Confirm freshness still holds: every asset now rides the daily YFiles load → the panel
  cannot silently freeze and is internally consistent (all legs same 16:30 EOD dataset).
- yfinance remains the deep-history fallback for long windows. CRB unchanged. No commit.

## How to verify (Tester — on request, via AGENT_TASK.md)

1. `SELECT asset_key, source_spec FROM ref_corr_asset ORDER BY sort_order` — USD/SPX/Brent/
   Gold/Bitcoin all `histy:` first; CRB still `yfinance:DBC`.
2. `SELECT asset_key,w15,w30,w90 FROM drv_usd_correlation WHERE as_of_date='2026-06-23'`
   — SPX still ≈ provider (−0.27/−0.41 region, w15 within ~0.03); Gold 15D recovered toward
   −0.70 vs the TASK_90 −0.51; Brent/Bitcoin not regressed. Document the full before/after.
3. Hand-check: Gold `w15` = Pearson of trailing-15 `hist_y ^NYICDX` vs `hist_y GC=F` (±0.01)
   — confirming both legs are now same-source.
4. Freshness: without running `fetch_quotes`, a new TOSD + derive still yields a
   current-dated, all-hist_y window.
5. `pytest tests/` — update/supersede the TASK_87 protected-file tests for the new
   source_spec; no real regressions; re-derive twice → identical rows.

End `ALL_DONE`.
