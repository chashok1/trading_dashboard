# IV / HV spike state (`drv_vol_spike`)

Informational. Never changes `consolidated_action` / the Final Call.

## What it is
The user's TOS studies **A_IV_Spikes(63, 1.15, 1, 4, 5)** and **A_HV_Spike(63, 1.15, 0.95, 3, 5)**, translated line for line in
`etl/vol_spike.py::spike_series` (inputs: length, spike threshold, normalize threshold, smoothing, excluded days).
Grey line = smoothed series; white dashed = average x normalize threshold; red dashed = average x 1.15; the average is the
"pre-spike" average (excludes the last 5 days) until a spike prints, then the full average until the ratio falls back below the
normalize threshold. Up arrow = spike, down arrow = normalized.

Series come from `hist_td` (`imp_volatility`, `historical_vol`, `last_price`, one row per export day). A day missing from the
export carries the previous value forward (the 63-day averages need gap-free data). `hist_td` starts 2026-02-02, so real
signals start ~mid-May 2026 (about 72 trading days of warm-up).

## Table
`drv_vol_spike(as_of_date, tos_symbol, iv, iv_ratio, iv_spiked, iv_event, iv_spike_days_ago, iv_norm_days_ago, hv, hv_ratio,
hv_spiked, hv_event, hv_spike_days_ago, px_chg_5d, stress)`. Idempotent (`DELETE WHERE as_of_date` -> INSERT).
The study is causal, so a one-pass history backfill gives the right as-of value for every past day.

## Stress
`stress` = IV spiked (state active, or a fresh spike arrow within 5 trading days) **and** price down >= 3% over 5 trading days.
Tunables in `VOL_SPIKE_CONFIG`.

## Where it shows
* Actionable grid, **IV** column: chip `IV STRESS` / `IV SPIKE 5d` / `HV SPIKE 14d` / `IV NORM 3d` (bulleted tooltip incl. the
  app's own history). Header sort + filter funnel on the spike state.
* Action popup studies panels (right side): same code (`api/routers/dash.py::get_studies` imports `etl/vol_spike`).
* Watch alert: a **held** symbol with a fresh IV spike arrow or fresh stress gets an auto-created, already-triggered `ref_watch`
  row (note `Auto: IV spike|stress <date>`), picked up by the existing Watch email digest. Only on the live anchor day; never on
  backfill/re-derive of older dates; skipped if the symbol already has an ACTIVE watch (the user's own watch is left alone) or
  the same event was already alerted.

## Commands
```
python -m etl.vol_spike --backfill 2026-02-02   # rebuild history (no alerts)
python -m etl.vol_spike --date 2026-10-28       # one date (no alerts)
python -m etl.compute_factor_outcomes            # refresh drv_factor_snapshot -> v_factor_scorecard (factors 'IV spike state', 'HV spike state')
```

## Test result (2026-10-29, 2026-05-26..2026-10-28, ~43k-4k symbol-days per bucket, 20-day forward return)
| bucket | n | avg 20d | win rate |
|---|---|---|---|
| No IV spike | 43,195 | +0.82% | 51.7% |
| IV spiked (active) | 4,448 | -0.01% | 48.4% |
| IV just normalized (<=5d) | 1,865 | +0.04% | 49.2% |
| IV spike + price falling (stress) | 1,685 | +1.55% | 52.0% |
| No HV spike | 42,705 | +0.99% | 51.5% |
| HV spiked (active) | 13,139 | +0.60% | 49.8% |

Reading: an active IV spike was followed by weaker returns than no spike; **stress (spike + falling price) was followed by a
bounce, not further weakness** -- so it is a "volatility event" flag, not a sell signal. Caveats: ~5 months, one market regime,
consecutive days overlap (20-day windows), so the confidence bands are optimistic. Re-check as history grows before letting
any of this drive a rule.
