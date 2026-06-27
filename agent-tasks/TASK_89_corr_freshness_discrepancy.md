# TASK_89 — Why the USD-correlation panel doesn't match the provider TODAY (freshness first)

**Type: diagnostic + fix.** Today is **2026-06-24 (Wed)**. The provider's "Key $USD
Correlations" table pulled this morning is anchored **EOD 2026-06-23**. The app panel
does NOT match — and the prime suspect is **staleness**, not methodology. Cowork's
file-level evidence:

- App panel currently shows **SPX 15D −0.60 / 30D +0.02**, Brent −0.46/−0.64, Gold
  −0.67/−0.88, BTC −0.74/−0.84 — **identical to the values computed for the 6/18 anchor**
  in TASK_87/88. ⇒ the correlation window appears frozen at **6/18**, ~3 trading days
  behind (6/19 Juneteenth, 6/22, 6/23 absent from it).
- `/api/correlations` serves `MAX(as_of_date)` from `drv_usd_correlation`, and that derive
  reads prices from **`hist_quote_daily` (source='yfinance')** — the backfill pull, NOT the
  daily TOS drops. If that pull stopped after 6/18, every later derive still ends its
  window at 6/18.
- Confirmed interior gap: **TOSD + TOSL missing 2026-06-09** (Tue, normal trading day).
  6/19 missing = Juneteenth (expected).
- **SPX is the focus. Key tell in the data:**
  ```
            15D     30D     90D
  Provider -0.27   -0.41   -0.02
  App      -0.60   +0.02   -0.04
  ```
  The **90D matches** (−0.02 vs −0.04) while **15D/30D are way off** (30D even flips
  sign). That is the *signature of staleness*: a 90-point window barely moves when it's
  3 trading days stale (3/90 turnover), but a 15/30-point window changes a lot
  (3/15 = 20% turnover). So the data strongly indicates the app window ends ~6/18 while
  the provider's ends 6/23 — confirm this is the cause before chasing source/method.

DB + real-time data work is yours. **First report the WHY with concrete data points**
(see Step 1–3), then fix (Step 4), then re-compare (Step 5). Log to `DEV_HANDOFF.md`,
end `ALL_DONE`. **No commit.**

## Provider target — TODAY (EOD 2026-06-23)

```
asset     15D     30D     90D    120D    180D  | roll30: High   Low   %Pos  %Neg
SPX      -0.27   -0.41   -0.02   0.11    0.01  |        0.55  -0.91   33%   67%
Brent    -0.70   -0.76    0.11   0.44    0.24  |        0.95  -0.76   69%   31%
CRB       0.00    0.00    0.36   0.44    0.19  |        0.89  -0.87   31%   69%
Gold     -0.70   -0.87   -0.60  -0.69   -0.58  |        0.74  -0.90   17%   83%
Bitcoin  -0.33   -0.72   -0.55  -0.31   -0.04  |        0.75  -0.89   45%   55%
```

App panel now (for contrast — the 6/18 window): SPX −0.60/+0.02, Brent −0.46/−0.64,
CRB(proxy) −0.60/−0.70, Gold −0.67/−0.88, BTC −0.74/−0.84.

## Step 1 — Establish the three "latest dates" (data points)

Report all three, side by side:
1. `SELECT MAX(export_date) FROM hist_td` (the TOSD anchor / pipeline front edge).
2. `SELECT MAX(as_of_date) FROM drv_usd_correlation` (what the panel serves).
3. `SELECT symbol, MAX(obs_date) FROM hist_quote_daily WHERE source='yfinance'
   AND symbol IN ('^GSPC','DX-Y.NYB','BZ=F','DBC','GC=F','BTC-USD') GROUP BY symbol`
   (the price backfill front edge — the real limiter).

**Expected smoking gun:** (3) lags (1). State the gap in trading days.

## Step 2 — Prove the panel staleness

- For the latest `drv_usd_correlation` row, print `as_of_date` and SPX `w15/w30`.
- Print the **last 5 `obs_date`s** present for `^GSPC` and `DX-Y.NYB` in
  `hist_quote_daily` — confirm whether 6/19/6/22/6/23 exist. (6/19 won't for equities.)
- Confirm: is the panel's window actually ending 6/18 because the yfinance series stops
  there? Show the last common date between USD and `^GSPC`.

## Step 3 — Root-cause the freshness break (data points, not guesses)

- Is the yfinance/Stooq pull (`etl/fetch_quotes.py`) **scheduled and running**? When did
  it last insert into `hist_quote_daily`? Check `meta_*` (etl_run/file_processed) + logs.
- Did `derive_usd_correlation` actually run on the **6/22 and 6/23** derives, and did it
  **insert rows**? Check `meta_derived_run` for those dates; if it ran but inserted the
  same window, that confirms the limiter is the stale price backfill (not the derive).
- Confirm the **6/09 TOSD/TOSL** gap in the DB (`hist_td`/`hist_tl` have no 2026-06-09)
  and whether it affects the universe/any TOS-native series.

## Step 4 — Fix the data, re-derive to today

1. Run the quote backfill to pull **through 6/23** for all six symbols
   (`python -m etl.fetch_quotes --full` or the daily form); confirm `hist_quote_daily`
   now has 6/22 and 6/23 for `^GSPC`/`DX-Y.NYB`/etc. (6/19 only for FX/BTC).
2. Backfill the **6/09** gap where recoverable (yfinance side fills automatically; report
   if the TOS 6/09 export is unrecoverable).
3. Re-derive the correlation at the **current anchor (6/23)**; confirm
   `MAX(as_of_date) FROM drv_usd_correlation = 2026-06-23` and the window ends 6/23.

## Step 5 — Re-compare to the provider TODAY (the real test)

Now both sides are on the **6/23** window. Print the app table vs the provider target
above and the per-cell delta, focus on **15D/30D**. For SPX and one more asset, dump the
trailing-15 `(obs_date, usd_close, asset_close)` triples and hand-check Pearson == `w15`.

- State how much of the original mismatch was **pure staleness** (6/18→6/23) vs a
  **residual source/method difference**. If SPX 15D is still off after refresh, that's
  the real TASK_88 question (TOS `$DXY`/`$SPX` vs yfinance) — quantify the residual.
- If freshness was the whole story, recommend making the backfill + correlation re-derive
  run automatically each day (so the panel can't silently freeze again) — propose where
  (scheduler hook / daily job), but **do not implement** the scheduler change here.

## How to verify (Tester — on request, via AGENT_TASK.md)

1. `MAX(as_of_date) FROM drv_usd_correlation = 2026-06-23`; `hist_quote_daily` yfinance
   `^GSPC`/`DX-Y.NYB` have 6/22 + 6/23.
2. `/api/correlations` + panel show the 6/23 window (no longer the 6/18 numbers).
3. Per-asset 15D/30D delta vs the provider target documented; SPX hand-check `w15` ±0.01.
4. 6/09 gap status documented (filled or flagged unrecoverable on the TOS side).
5. `pytest tests/` clean; re-derive twice → identical rows (idempotent).

End `ALL_DONE`.
