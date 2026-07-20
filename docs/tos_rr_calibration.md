# TOS BB band calibration vs hist_rr (TASK_128)

Calibrates the TOS `BBTop`/`BBBottom` custom-column ThinkScripts (exported
into `hist_td.a_bb_top` / `a_bb_bottom`, mapped via
`etl/mappings.py::HIST_MAPS['TD']`) against the Hedgeye risk ranges published
in `hist_rr` (`sell_trade` / `buy_trade`). Builder + grid search:
`etl/calibrate_tos_rr.py` (`python -m etl.calibrate_tos_rr [--start ...]
[--end ...] [--report]`).

## Date alignment

`hist_rr(D)` is published pre-open using **D-1's close** (RR xlsx "Prev
Close" / "RR Date" = D-1). Every feature here is anchored on the latest
`hist_td` close **strictly before D** — `pandas.merge_asof(direction=
"backward", allow_exact_matches=False)` — the same semantics as
`etl/derive.py::_derive_rr_impl`'s BB-fallback lateral
(`hist_td.snapshot_date < :d`). Reverse-quoted symbols (`ref_rrt.reverse=
'Y'`, e.g. `TNX:CGI`) have their `hist_rr` yield-% targets scaled by
`ref_settings.rr_reverse_scale` (default 10) before computing error, matching
`_derive_rr_impl`.

## Scope

Only tickers present in **both** `hist_rr` and `hist_td` can be calibrated —
the TOS BB columns are computed from `hist_td` close/OHLC data, so futures/
FX/commodity tickers that only appear in `hist_rr` (`/6B /6C /6E /6J /BTC
/BZ /CL /GC /HG /NG /SI`, plus `$SSEC`, `DGS2:FRED`, `SPCX`) have no close
series to fit against and are excluded — same exclusion the BB fallback in
`derive.py` already has. Calibration set: **31 tickers**, `hist_rr` history
2026-01-01 → 2026-07-17 (≈2,033 ticker-day rows with a valid ≥26-day close
history), 14 most recent days held out as the CV test window.

## Baseline (current `a_bb_top` / `a_bb_bottom`)

| Band | Median APE | % within 2% |
|---|---|---|
| TOP (`a_bb_top` vs `sell_trade`) | 1.244% | 65.1% |
| BOTTOM (`a_bb_bottom` vs `buy_trade`) | 1.217% | 63.7% |

Diagnostics: BB range width is ~31% wider than the RR range (median ratio
1.31), but the midpoint is barely offset (median +0.08%) — the old
"BridgeBands" formula (WMA(15)±2·StDev blended with a hurst-weighted trend
extrapolation) already centers correctly but over-widens the bands, which
explains why point-wise APE (1.2%) already looks close-ish while the range
itself is oversized.

## Fit — family comparison (grid-searched on train, i.e. all but the last 14
days; `n ∈ {10,15,20,21,26}`, `k` swept 0.3–4.0, mid ∈ {SMA, EMA}, `c` swept
for the vol-scaled family)

| Family | TOP best (train) | BOTTOM best (train) |
|---|---|---|
| A — classic BB: `mid(n) ± k·StDev(n)` | EMA(10), k=1.72 → med 1.00%, 71.3%≤2% | EMA(10), k=1.86 → med 1.17%, 63.1%≤2% |
| B — Donchian blend: `mid(Highest/Lowest(n)) ± k·StDev(m)` | n=m=10, k=1.80 → med 0.96%, 71.2%≤2% | n=m=10, k=2.10 → med 1.11%, 63.8%≤2% |
| C — vol-scaled: `mid(n) ± k·(1+c·(iv/hv-1))·StDev(n)` | EMA(10), c=-0.25, k=1.88 → med 0.96%, 71.4%≤2% | EMA(10), c=0.50, k=1.76 → med 1.18%, 64.3%≤2% |

All three families land within ~1pp of each other on every metric — the IV
term (family C) and the Highest/Lowest midpoint (family B) don't add
meaningful signal here because at `n=10` the rolling window is already short
enough that SMA/EMA and Donchian midpoints nearly coincide, and the vol-scale
correction only matters materially for the handful of tickers with regime
shifts (below), which a global `c` can't fix.

**Chosen: Family A (classic Bollinger Band)** — ties or beats B/C, and is
the simplest to express as a standalone TOS custom column (native
`ExpAverage`/`StDev`, no `Highest`/`Lowest`/`imp_volatility()` NaN-guard
needed).

## Final fitted params

| Param | Value |
|---|---|
| `length` (EMA + StDev window) | 10 |
| `k_top` (`TOS/BBTop.txt`) | 1.72 |
| `k_bot` (`TOS/BBBottom.txt`) | 1.86 |

`mid = ExpAverage(close, 10)`, `StDev` = sample stdev (`÷(length-1)`, same
`StDev_Sample` script as the original BridgeBands file). `k_top`≠`k_bot`
because the Hedgeye ranges are asymmetric around price (per the task
background), same as before.

## Final error — overall

| Split | n | TOP median APE | TOP %≤2% | BOTTOM median APE | BOTTOM %≤2% |
|---|---|---|---|---|---|
| Train | 1,812 | 1.00% | 71.3% | 1.17% | 63.1% |
| Test (last 14d, held out) | 221 | 0.67% | 78.7% | 0.86% | 70.1% |
| **All (full hist_rr history)** | **2,033** | **0.97%** | **72.1%** | **1.14%** | **63.8%** |

## Success target vs achieved

Target: median APE ≤1.5% per band, ≥70% of ticker-days within 2%.

- **TOP: PASS** — median 0.97% (target ≤1.5%), 72.1% within 2% (target ≥70%).
- **BOTTOM: median PASS, tail MISS** — median 1.14% (target ≤1.5%, comfortably
  met), but only 63.8% within 2% (target ≥70%). Worst 5 tickers (median APE,
  full history, fitted params):

  | Ticker | TOP med APE | BOTTOM med APE |
  |---|---|---|
  | ORCL | 4.55% | 3.75% |
  | VIX | 3.25% | 3.77% |
  | TSLA | 2.66% | 1.99% |
  | N225:JP | 1.24% | 2.62% |
  | META | 2.56% | 1.50% |

  `ORCL` had a real ~50% drawdown over ~6 weeks (190→126) after a huge
  earnings gap up to 248 — no fixed-window rolling band tracks a move that
  size without multi-week lag. `VIX` is mean-reverting/vol-of-vol and
  structurally doesn't fit a price-based BB. Per-ticker `k` overrides were
  tried for these (and `N225:JP`/`XLV`/`XTL`): even the **locally
  re-optimized** `k` for `VIX`/`ORCL`/`N225:JP` only gets median APE down to
  ~2.1–3.6% (`etl/calibrate_tos_rr.py`, ad hoc per-ticker grid, not wired
  in) — a global-`k` band formula structurally can't track these regime
  shifts, so no per-ticker override table was added (would add complexity
  for ≤3pp of overall gain). This is a documented residual limitation, not a
  missed calibration opportunity.

## Re-running

```
python -m etl.calibrate_tos_rr --report     # rescore FITTED params only (fast)
python -m etl.calibrate_tos_rr              # full grid search across families A/B/C + report
python -m etl.calibrate_tos_rr --start 2026-05-01 --end 2026-07-17
```

No change to `drv_rr`, `etl/derive.py`, or schema — this task only changes
the two standalone TOS custom-column scripts and adds the calibration
tooling/docs.
