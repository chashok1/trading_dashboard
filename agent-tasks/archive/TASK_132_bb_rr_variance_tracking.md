# TASK_132 — daily BB-vs-hist_rr variance tracking + drift alert

## Goal

The TASK_128–131 calibration fit `TOS/BBTop.txt`/`BBBottom.txt` to the
Hedgeye risk ranges, but nothing monitors the match on an ongoing basis —
parameter fit will decay if the market regime or Hedgeye's model shifts,
and today that drift is invisible until someone manually reruns
`etl/calibrate_tos_rr.py`. Add a small derived table that records the
band-vs-RR variance **every day inside the normal derive cascade**, plus a
drift flag that acts as the "time to recalibrate" alarm.

**Why a stored table rather than a view:** both inputs do already live in
`hist_rr`/`hist_td`, so the raw variance is always recomputable — the table
was an explicit user decision (2026-07-20) because the daily flag evaluation
has to run somewhere anyway, rolling medians are awkward as a live SQL view,
storage is trivial (~55 rows/day), and it matches the existing `drv_*`
pattern (`drv_rr` similarly duplicates hist data for downstream use).

## 1. New table — `drv_bb_rr_gap`

```sql
CREATE TABLE IF NOT EXISTS drv_bb_rr_gap (
    as_of_date       DATE NOT NULL,
    tos_symbol       TEXT NOT NULL,
    bb_top           NUMERIC,   -- hist_td.a_bb_top (latest snapshot < D, EOD seq)
    bb_bottom        NUMERIC,
    rr_sell          NUMERIC,   -- hist_rr.sell_trade for D (reverse-scaled)
    rr_buy           NUMERIC,   -- hist_rr.buy_trade  for D (reverse-scaled)
    ape_top          NUMERIC,   -- |bb_top - rr_sell| / rr_sell   (NULL if either side missing)
    ape_bottom       NUMERIC,
    ape_top_med20    NUMERIC,   -- rolling 20-trading-day median of ape_top (per symbol)
    ape_bottom_med20 NUMERIC,
    drift_flag       TEXT,      -- NULL | 'WARN' | 'ALERT' (see §3)
    source_run_id    BIGINT,
    derived_at       TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of_date, tos_symbol)
);
```

Rows only for symbols present in **both** `hist_rr` (D) and `hist_td`
(< D) — same alignment and reverse-symbol scaling (`ref_rrt.reverse`,
`ref_settings.rr_reverse_scale`) as `etl/calibrate_tos_rr.py` /
`_derive_rr_impl`. Add to `db/baseline.sql` (idempotent `IF NOT EXISTS`).

## 2. Deriver — `etl/derive_bb_rr_gap.py`

- `_wrap`-style deriver like the others; idempotent DELETE-for-date +
  INSERT. Wire into `derive_all()` in `etl/derive.py` after `derive_rr`
  (needs nothing downstream; keep it late/cheap).
- Rolling 20d medians computed over the symbol's prior `drv_bb_rr_gap`
  rows (window includes D; min 5 obs before medians/flags are emitted).
- Backfill: one-off loop over the full `hist_rr` history (same idempotent
  pattern as prior drv_pvv backfills) so the trend starts populated.

## 3. Drift flag thresholds (constants in the deriver, tunable later)

Calibration reference (TASK_130/131 final): TOP median 0.70%, BOTTOM 0.84%.

- `WARN`: `ape_top_med20 > 1.4%` or `ape_bottom_med20 > 1.7%`
  (≈2× the calibrated medians).
- `ALERT`: `ape_top_med20 > 2.1%` or `ape_bottom_med20 > 2.5%` (≈3×), or
  ≥ 10 symbols simultaneously in WARN on the same date (universe-wide
  drift ⇒ regime shift, not a single-name event).
- Known structural outliers (`VIX`, `ORCL`, `NFLX` — documented in
  `docs/tos_rr_calibration.md`) get 2× thresholds so they don't
  permanently sit in WARN and drown real signal.

## 4. Surfacing

- `etl/daily_health_check.py`: add a check — count of WARN/ALERT symbols
  for the anchor date, log line + nonzero-ALERT warning (follow the file's
  existing check pattern).
- Dashboard (minimal): expose `drift_flag`/`ape_*_med20` via the existing
  actionable/monitor API row if a natural join point exists (developer's
  judgment — a tooltip field or small badge is enough; do NOT build a new
  screen for this).
- `docs/tos_rr_calibration.md`: short "ongoing monitoring" section — what
  the table tracks, thresholds, and the recalibration playbook (rerun
  `python -m etl.calibrate_tos_rr`, review, update TOS scripts + FITTED).

## How to verify (tester reference — run only on explicit request)

1. Fresh `derive_all()` for the anchor date populates `drv_bb_rr_gap` with
   one row per symbol in both `hist_rr` and `hist_td`; APEs match a hand
   check for 2 symbols (1 normal, 1 reverse='Y').
2. Backfill loop fills the full `hist_rr` history; rolling medians for a
   spot symbol match a pandas recomputation.
3. Thresholds: symbols with med20 above/below the WARN/ALERT lines carry
   the right flag; VIX/ORCL/NFLX use the doubled thresholds.
4. `daily_health_check` reports the WARN/ALERT counts.
5. Re-running the deriver for the same date is idempotent (row counts
   unchanged).

## Files expected to change

`db/baseline.sql` (new table), `etl/derive_bb_rr_gap.py` (new),
`etl/derive.py` (wire into `derive_all()`), `etl/daily_health_check.py`,
`docs/tos_rr_calibration.md`, optionally one API router + web file for the
minimal badge, `DEV_HANDOFF.md`. 

No commits — user commits from Windows.
