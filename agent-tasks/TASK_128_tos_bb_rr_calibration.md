# TASK_128 — Calibrate TOS BB scripts to hist_rr risk ranges

## Goal

Make the TOS ThinkScript band formulas (`TOS/BBTop.txt`, `TOS/BBBottom.txt`
→ exported as `hist_td.a_bb_top` / `a_bb_bottom`) produce values **close to
the Hedgeye risk ranges stored in `hist_rr`** (`sell_trade` / `buy_trade`),
for the tickers present in `hist_rr` only. The bands are the price/volume/
volatility-based BB fallback in `drv_rr`; today they drift too far from the
published RR values.

**Success target:** per-band median absolute % error ≤ 1.5% vs `hist_rr`,
and ≥ 70% of ticker-days within 2%, measured across the full `hist_rr`
history (≈ 48 tickers, daily since 2026-05).

## Background / constraints

- `hist_rr` rows for snapshot D are published **pre-open using D-1's close**
  (RR xlsx "Prev Close" / "RR Date" = D-1). So compare `hist_rr(D)` against
  bands computed from data **through D-1 only** — same semantics as
  `_derive_rr_impl`'s BB-fallback lateral (`hist_td.snapshot_date < :d`),
  see `etl/derive.py`.
- Yield-quoted symbols (`ref_rrt.reverse = 'Y'`, e.g. TNX:CGI): `hist_rr`
  stores yield %, TOS displays yield × `rr_reverse_scale` (ref_settings,
  default 10). Scale targets before computing error.
- `TOS/BBBottom.txt` and `TOS/BBTop.txt` are currently **empty (0 bytes)** —
  content was lost on save. The user is re-saving them; if still empty when
  you start, don't block: the current formula's *outputs* already exist as
  `hist_td.a_bb_top` / `a_bb_bottom`, which is enough for the baseline.
- The fitted formula must be computable inside a TOS chart study/custom
  column: daily OHLCV, `stdev`, `Average`/`ExpAverage`, `ATR`,
  `Highest`/`Lowest`, `imp_volatility()` (guard NaN). No cross-sectional or
  DB data.

## 1. Calibration dataset (SQL → CSV or DataFrame)

For every `(snapshot_date D, tos_symbol)` in `hist_rr` with
`tos_symbol IS NOT NULL` and non-zero `buy_trade`/`sell_trade`:

- **Targets:** `buy_trade`, `sell_trade` (× rr_reverse_scale when
  reverse='Y').
- **Features (history ≤ D-1, EOD = max sequence per day):** `hist_td`
  `last_price` series, `historical_vol`, `imp_volatility`, current
  `a_bb_top`/`a_bb_bottom`; `hist_tl` `volume` series. Note `hist_td` has no
  OHLC — closes only; formula families below must work from close series
  (the ThinkScript may still use `high`/`low` via ATR only if fitted from a
  close-based proxy, so prefer close/stdev families).

Persist the builder as `etl/calibrate_tos_rr.py` (re-runnable CLI:
`python -m etl.calibrate_tos_rr --start ... --end ...`).

## 2. Baseline

Report current error of `a_bb_top` vs `sell_trade` and `a_bb_bottom` vs
`buy_trade`: overall + per-ticker median APE, plus two diagnostics —
range-width ratio `(top-bot)_BB / (top-bot)_RR` and midpoint offset % —
so we know whether the miss is width, center, or both.

## 3. Fit — small model families, grid search

Grid-search global parameters per family, score by cross-validated median
APE (leave-last-2-weeks-out). Families (all ThinkScript-expressible):

- **A. Classic BB:** `mid(n) ± k · StDev(close, n)`, mid ∈ {SMA, EMA},
  n ∈ {10, 15, 20, 21, 26}, separate `k_top`, `k_bot` (Hedgeye ranges are
  asymmetric around price).
- **B. Donchian blend:** midpoint of `Highest/Lowest(close, n)`
  `± k · StDev(close, m)`.
- **C. Vol-scaled variant of A:** k multiplied by an IV term, e.g.
  `k · (1 + c · (imp_volatility / historical_vol - 1))`, IV NaN → term = 1.

Pick the family/params with the best CV score. Global params first; only if
the target is missed, add a small per-ticker override table (report which).
Trend/volume tilt of the midpoint (e.g. shift center by a fraction of
`(EMA_fast - EMA_slow)`) is allowed as a refinement if it clearly helps.

## 4. Deliverables

- `TOS/BBTop.txt`, `TOS/BBBottom.txt` — updated ThinkScript, fitted
  parameters as `input`s with defaults, plot/column name unchanged so the
  TOS export keeps landing in `a_bb_top`/`a_bb_bottom`. Keep the two files
  standalone (each is pasted into its own TOS custom column).
- `etl/calibrate_tos_rr.py` — dataset builder + grid search + report.
- `docs/tos_rr_calibration.md` — chosen family/params, baseline vs final
  error table (overall + worst 5 tickers), date-alignment note.
- `DEV_HANDOFF.md` — progress log, end `ALL_DONE`.

## How to verify (tester reference — run only on explicit request)

1. `python -m etl.calibrate_tos_rr --report` reruns scoring from stored
   params; printed final metrics meet the success target (or the handoff
   documents why not and the best achieved).
2. `psql`: for 3 spot tickers (1 equity ETF, 1 index, 1 reverse='Y'),
   recompute the fitted formula for the latest `hist_rr` date from
   `hist_td` closes and confirm it matches the reported band values to
   4 s.f., and sits within the reported error of `buy_trade`/`sell_trade`.
3. `TOS/BBTop.txt` / `BBBottom.txt` are non-empty, parse as ThinkScript
   (visual check), and their constants equal the fitted params in
   `docs/tos_rr_calibration.md`.
4. No change to `drv_rr` derive logic or schema in this task.

## Files expected to change

`TOS/BBTop.txt`, `TOS/BBBottom.txt`, `etl/calibrate_tos_rr.py` (new),
`docs/tos_rr_calibration.md` (new), `DEV_HANDOFF.md`. No schema change, no
edits to `etl/derive.py`.

No commits — user commits from Windows.
