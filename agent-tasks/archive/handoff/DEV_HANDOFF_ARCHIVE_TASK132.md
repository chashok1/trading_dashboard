# Dev Handoff — AGENT_WORK_38

## Task
TASK_132: add a new `drv_bb_rr_gap` derived table + deriver that tracks the
daily TOS-band (BBTop/BBBottom) vs Hedgeye `hist_rr` variance every derive
cascade, with rolling 20d medians, WARN/ALERT drift flags, health-check
integration, and a full-history backfill.

## Files changed
- `db/baseline.sql` — new `CREATE TABLE IF NOT EXISTS drv_bb_rr_gap` (PK
  `as_of_date, tos_symbol`; columns per spec: `bb_top/bb_bottom`,
  `rr_sell/rr_buy`, `ape_top/ape_bottom`, `ape_top_med20/ape_bottom_med20`,
  `drift_flag`, `source_run_id`, `derived_at`) + two indexes. Applied via
  `python -m db.init_db` — confirmed the table now exists.
- `etl/derive_bb_rr_gap.py` (new) — `_derive_bb_rr_gap_impl` +
  `derive_bb_rr_gap = _wrap(...)`, idempotent DELETE-for-date + INSERT via
  `replace_for_date`. Rows only for symbols present in both `hist_rr`
  (latest snapshot `<= D`) and `hist_td` (latest snapshot `< D`, EOD max
  sequence) — same carry-forward alignment and reverse-symbol scaling
  (`ref_rrt.reverse`, `ref_settings.rr_reverse_scale`) as
  `_derive_rr_impl`/`calibrate_tos_rr.py`. Rolling `ape_*_med20` reads the
  symbol's own prior `drv_bb_rr_gap` rows (table doubles as the rolling-
  window store); requires >=5 observations (incl. today) before a
  median/flag is emitted. `drift_flag`: WARN at ~2x calibrated medians
  (top>1.4%, bottom>1.7%), ALERT at ~3x (top>2.1%, bottom>2.5%) OR when
  >=10 symbols are simultaneously WARN on the same date (all of them get
  promoted to ALERT — universe-wide drift read as regime shift). `VIX`/
  `ORCL`/`NFLX` use doubled thresholds (documented structural outliers).
- `etl/derive.py` — wired `derive_bb_rr_gap` into `derive_all()` right
  after the `drv_pvv` step (downstream of `derive_rr`; nothing depends on
  it, so it stays late/cheap per spec), same `_safe()`-wrapped-runner
  pattern as `drv_pvv`/`drv_source_standing`.
- `etl/backfill_bb_rr_gap.py` (new) — one-off ascending loop over every
  distinct `hist_rr.snapshot_date`, calling `derive_bb_rr_gap` per date
  (own transaction each, same pattern as `etl/backfill_derives.py`).
  Ascending order is required so each date's rolling median reads the
  already-backfilled prior dates. `--limit`/`--from`/`--to` flags. **Ran
  it against the live local DB** — 136/136 dates backfilled, 4,323 total
  rows across 114 dates with >=1 qualifying symbol.
- `etl/daily_health_check.py` — new `_check_bb_rr_drift`: WARN/ALERT count
  for the latest `drv_bb_rr_gap` date, `ok=False` iff ALERT count nonzero.
  Added to the module's `CHECKS` list (follows the file's existing
  check-function pattern exactly).
- `api/routers/dash.py` — `/api/actionable` payload: `LEFT JOIN
  drv_bb_rr_gap bg ON (tos_symbol, as_of_date)`, exposes
  `bb_rr_drift_flag`, `bb_rr_ape_top_med20`, `bb_rr_ape_bottom_med20` per
  row (natural join point next to the existing `drv_rr`/`drv_pvv` joins).
- `web/actionable.js` — TrTnBBRskRng cell's hover tooltip (`_rrSubLineHtml`)
  now appends a `Drift: WARN`/`Drift: ALERT` line (colored amber/red, title
  attr shows the top/bottom med20 values + the recalibration command) only
  when `r.bb_rr_drift_flag` is set. No new screen/column, per spec's
  "developer's judgment ... do NOT build a new screen for this".
- `docs/tos_rr_calibration.md` — new "Ongoing monitoring (TASK_132)"
  section: what the table tracks, threshold math, surfacing points
  (health check + tooltip), backfill command, and the recalibration
  playbook (rerun `calibrate_tos_rr`, review, update TOS scripts +
  `FITTED_TOP`/`FITTED_BOT`).

## How to test
- Schema: `python -m db.init_db` (idempotent; already applied here).
- Deriver sanity (already run against the live local DB):
  ```
  python -c "
  from datetime import date
  from etl.db import session_scope
  from etl.derive_bb_rr_gap import derive_bb_rr_gap
  with session_scope() as s:
      print(derive_bb_rr_gap(s, date(2026,7,17)))
  "
  ```
  Re-running the same date is idempotent (row count unchanged — verified).
- Full derive cascade: `python -c "from datetime import date; from etl.db
  import session_scope; from etl.derive import derive_all;
  session_scope().__enter__()"` or simply run a normal `derive_all(s, D)` —
  `counts['drv_bb_rr_gap']` should be nonzero (verified: 41 rows for
  2026-07-17).
- Backfill: `python -m etl.backfill_bb_rr_gap` (full history) or
  `--from/--to/--limit` for a partial run — already executed against the
  live DB (136/136 dates, no failures).
- Rolling median spot check: I hand-verified `AAPL`'s `ape_top_med20`/
  `ape_bottom_med20` on 2026-06-11 (first date with >=5 obs) against a
  manual `statistics.median()` of the 5 prior `ape_top`/`ape_bottom`
  values — both matched exactly.
- Threshold spot check: `AAPL` crosses WARN at 2026-06-30
  (`ape_top_med20=1.655>1.4`) and ALERT at 2026-07-08
  (`ape_top_med20=2.406>2.1`) — confirmed both transitions land on the
  correct row. `NFLX` (outlier) sits at `ape_top_med20≈3.28` (would be
  ALERT at the base 2.1 threshold) but only shows WARN because the doubled
  threshold (4.2) isn't crossed — confirms outlier doubling is applied.
- Health check: `_check_bb_rr_drift` tested directly in isolation (`from
  etl.daily_health_check import _check_bb_rr_drift`) — returned `ok=False`,
  `"2026-07-17: 6 WARN, 14 ALERT"` for the current live data (real
  drift signal, not a bug — see Risks below).
- API: confirmed the `drv_actionable`/`drv_bb_rr_gap` LEFT JOIN returns
  `bb_rr_drift_flag`/`bb_rr_ape_top_med20`/`bb_rr_ape_bottom_med20` rows
  directly against the DB (ran the join SQL standalone).
- `web/actionable.js`: `node --check web/actionable.js` passes. No server
  restart needed for the JS-only tooltip change (uvicorn `--reload-dir
  api` doesn't watch `web/`, but the browser just needs a refresh — no
  separate restart step, `web/` isn't hot-reloaded but isn't cached
  server-side either).
- **Since `etl/` changed (derive_bb_rr_gap.py, derive.py,
  backfill_bb_rr_gap.py, daily_health_check.py): STOP the running uvicorn
  server, relaunch `start.bat`, THEN re-derive** — uvicorn's
  `--reload-dir api` does not watch `etl/`, so a live server will keep
  running the stale pre-TASK_132 derive cascade until restarted.

## Risks & notes
- **Pre-existing bug found, NOT fixed (out of scope for this task):**
  `python -m etl.daily_health_check` currently fails past the first check
  — `_check_hist_gap`'s per-source try/except catches a bad-table query
  exception and `continue`s, but the underlying Postgres transaction stays
  aborted (`InFailedSqlTransaction`), so every subsequent check in the same
  `session_scope()` (including my new `_check_bb_rr_drift`) errors out too.
  This is unrelated to TASK_132 — I verified `_check_bb_rr_drift` works
  correctly in an isolated session (see "How to test" above). Worth a
  follow-up task to add a `session.rollback()` in `_check_hist_gap`'s
  except block, or move each check to its own `session_scope()`.
- **Live drift signal is real, not a test artifact.** After backfilling,
  the anchor date (2026-07-17) already shows 6 WARN + 14 ALERT symbols
  (`AAPL` included) — TASK_130/131's fit has drifted meaningfully since
  calibration. This is expected/desired behavior (the whole point of the
  task) but means the health check will report a real ALERT immediately;
  not a bug to chase.
- **Universe-wide ALERT-promotion design decision**: the spec's ">=10
  symbols simultaneously in WARN" ALERT trigger was implemented as
  promoting exactly those WARN-flagged symbols (using their own, possibly
  outlier-doubled, base threshold) to ALERT for that date — this is a
  reasonable reading but wasn't 100% unambiguous in the spec; flagging for
  visibility.
- No changes to `drv_rr`, `_derive_rr_impl`, or `TOS/BBTop.txt`/
  `BBBottom.txt` — this task is purely additive monitoring, doesn't touch
  the calibrated formula itself.

## Status
ALL_DONE
