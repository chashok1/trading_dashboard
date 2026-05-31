# File Monitor Logic

Deep-dive on the scheduler folder-watch, ETL load pipeline, derive trigger,
schedule-status computation, and the File Monitor screen. `CLAUDE.md` carries
only a one-line pointer to this file in its Lookup index; keep the detail here.

## Overview

The File Monitor screen (`/file-monitor`, `web/file_monitor.html` +
`web/file_monitor.js`) gives real-time visibility into the full ETL pipeline:
which files are expected today, which have landed, what the scheduler is doing
right now, how the derive cascade is progressing, and any gaps that need
remediation.

Three subsystems feed it:

1. `etl/scheduler.py` — a long-running watchdog process that watches the
   source directories listed in `ref_load_files` and fires `load_one_file`
   whenever a new `.xlsx` or `.csv` appears.
2. `etl/etl_load.py` — the single-file loader: hash-checks, copies to working
   dir, dispatches to a mapping or custom handler, commits per-1000-row batch,
   records `meta_etl_run` + `meta_file_processed`, then triggers the derive
   cascade in-process.
3. `api/routers/monitor.py` — FastAPI endpoints queried by the UI plus a live
   SSE stream that pushes running-job state every 5 seconds.

## Diagrams

- `docs/diagrams/12_file_monitor_data_flow.svg` — **data flow**: source
  folders through the watchdog, `load_one_file`, the hist tables and meta
  bookkeeping, the derive cascade, the monitor API, and the File Monitor UI
  with its live SSE feed.
- `docs/diagrams/13_file_monitor_logic.svg` — **decision logic**: the
  schedule-status computation for each `ref_load_files` slot (LATERAL joins
  keyed by `processed_at::time >= file_time`), the five possible status
  values, and the missing-derive detection path.

Keep both diagrams in sync whenever this logic changes.

## Scheduler folder-watch (`etl/scheduler.py`)

On startup `main()` acquires an exclusive OS-level byte-range lock on
`etl_working_dir/scheduler.lock`. If the lock is already held by another
process the scheduler exits immediately, enforcing single-instance operation.
The API's `/api/monitor/scheduler` probes the same lock non-destructively to
report running/stopped status.

`get_watch_dirs()` reads `SELECT DISTINCT source_dir FROM ref_load_files WHERE
enabled = TRUE`. An `Observer` (watchdog) is attached to every directory that
exists; missing directories are logged at WARNING level but do not abort.

Before the watchdog starts, `scan_initial()` walks each directory and
processes any `.xlsx` / `.csv` file whose `file_mtime` does not match a row in
`meta_file_processed` (integer-seconds comparison, 2-second tolerance to
account for REAL column precision loss). This catches files that arrived while
the scheduler was offline.

The `XlsxHandler` class debounces events: the same file path is ignored for
`DEBOUNCE_SECS` (30 s) after first seen. Each accepted event calls
`quiesce_then_load()`, which polls `stat()` every 0.5 s until mtime and size
are stable for `QUIESCE_SECS` (2 s), then waits for the file to be readable
(up to 60 s for Windows sharing-lock release), then calls `load_one_file`.

A nightly loop (configurable hour via `ref_settings.outcomes_compute_hour`,
default 22) fires `etl/compute_outcomes.py` once per calendar day to score
logged user actions against forward price moves.

## ETL load path (`etl/etl_load.py` — `load_one_file`)

`load_one_file(file_path, file_type=None, do_derive=True, force=False)` is the
single entry point for every file load, whether triggered by the watchdog, the
Reprocess button, or the CLI.

**Step 1 — already-processed check.** Reads `meta_file_processed` by
`file_path` (case-insensitive). If `file_mtime` matches (within 2 s) and
`force=False`, returns `{"status": "skipped"}` immediately.

**Step 2 — file-type dispatch.** CSV files are checked first by name pattern
before the generic XLSX path:

| Pattern | file_type | Target table |
|---|---|---|
| `_Transactions_` or `CST ` prefix | CST | `hist_cst` |
| `accounts_history` or `FT ` prefix | FT | `hist_ft` |
| `CS ` prefix (positions) | CS | `hist_cs` |
| `.xlsx` / `.xlsm` — generic path | inferred from filename | per `ref_load_files` |

**Step 3 — target tab lookup.** `lookup_target_tab()` queries `ref_load_files`
for the `target_tab` matching the file_type (case-insensitive). If not found,
returns error.

**Step 4 — copy + open run.** The source file is copied to
`ETL_WORKING_DIR/<basename>` (source is never moved or deleted). `open_run()`
inserts a `meta_etl_run` row with `status='running'`.

**Step 5 — handler dispatch.**

- `CUSTOM_HANDLERS` is checked first (keyed by `target_tab.lower()`): `etf`,
  `etfchg`, `iichg`, `ref_tickers`.
- Otherwise `HIST_MAPS` is scanned for an entry whose `sheet` matches
  `target_tab` (case-insensitive) and `load_one_tab` is called.

`load_one_tab` streams the workbook sheet in 1000-row batches. Each batch
is committed independently; progress is printed as:
`[Table] batch X/Y (pct%) cumulative: N inserted, M skipped`.
Rows that conflict on the PK are silently skipped (`ON CONFLICT DO NOTHING`).

**Step 6 — bookkeeping.** `close_run()` updates `meta_etl_run` with final
counts and status. `mark_processed()` upserts `meta_file_processed`. For
position files (F / CS), `mark_cs_sales` / `mark_f_sales` detects symbols
absent from the current snapshot and marks them sold.

## In-process derive trigger

Immediately after a successful load, `load_one_file` calls `derive_all(session,
file_dt)` in-process (skippable via `--no-derive` / `do_derive=False`):

- `derive_all` runs the full cascade for date `file_dt`: drv_quote/drv_rr →
  drv_symbols/technicals/fundamentals/outlooks/portfolio (the 5 tables the
  `drv_ma` VIEW joins — `drv_ma` itself is not materialized) → drv_cat_atomic_input
  → drv_dash → drv_stks → drv_outlook_action → drv_actionable → drv_trig. Each step
  is idempotent (`DELETE WHERE as_of_date=D` then INSERT). Results are recorded in
  `meta_derived_run`.

After the primary derive, a **forward re-derive** runs automatically for any
date already in `drv_dash` with `as_of_date > file_dt`. This handles
backfilled or out-of-order files: since each derive reads hist sources with a
"latest snapshot <= D" window, a newly-arrived older row can change every
later date's derived output. The forward re-derive rebuilds those dates
oldest-to-newest, continuing past individual failures.

For CST and FT transaction files, instead of `derive_all`, only the realized-
gain derives are triggered: `derive_cs_realized_gain` for the affected trade
dates, then `derive_realized_gain` (FIFO across both brokerages).

## Monitor API endpoints (`api/routers/monitor.py`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/monitor/summary` | GET | KPI tiles: scheduled today, processed, running, errors, derives ok/total, last file at |
| `/api/monitor/schedule` | GET | Per-slot schedule status (see Schedule status below) |
| `/api/monitor/etl-runs` | GET | Recent `meta_etl_run` rows; optional `file_type` filter; `limit` 25–250 |
| `/api/monitor/derive-runs` | GET | `meta_derived_run` rows for a given date (defaults to today) |
| `/api/monitor/live` | GET (SSE) | Server-Sent Events; polls `meta_etl_run WHERE status='running'` every 5 s |
| `/api/monitor/scheduler` | GET | Running/stopped (OS lock probe) |
| `/api/monitor/scheduler/start` | POST | Launch scheduler via temp `.bat` in a detached Windows process |
| `/api/monitor/scheduler/stop` | POST | Write `scheduler_stop.txt` flag; SIGKILL fallback after 8 s |
| `/api/monitor/scheduler/output` | GET | Last N rows from `meta_scheduler_log`; filterable by `level` and `file_type` |
| `/api/monitor/scheduler/levels` | GET | Hard-coded level list (DEBUG/INFO/WARNING/ERROR/CRITICAL) |
| `/api/monitor/startup` | GET | Whether Windows Startup-folder launchers are registered |
| `/api/monitor/startup/register` | POST | Write launcher bat files into Windows Startup folder |
| `/api/monitor/startup/unregister` | POST | Remove Startup-folder launchers |
| `/api/monitor/reprocess` | POST | Call `load_one_file(force=True, do_derive=True)` for a given file path |
| `/api/monitor/derive-missing` | GET | Preview dates that need derives (gap or force mode) |
| `/api/monitor/derive-missing/run` | POST | Run `derive_all` oldest-to-newest for missing or force-rederive dates |

The SSE stream was slowed to a 5-second poll interval (from 500 ms) to avoid
exceeding PostgreSQL connection limits when multiple browser tabs are open.

## Schedule-status computation

`ref_load_files` has a composite primary key `(file_type, week_day, file_time)`
supporting multiple schedule slots per file_type (e.g. a file expected at both
16:00 and 17:00). The schedule query in `/api/monitor/schedule` must not let a
file processed for the 16:00 slot satisfy the 17:00 slot, while still allowing
the last slot of the day to claim a file that arrives overnight or early the
next morning.

The query resolves this with an `r_slots` CTE that augments `ref_load_files`
with `next_file_time = LEAD(file_time) OVER (PARTITION BY file_type, week_day
ORDER BY file_time)`. `next_file_time` is `NULL` for the last (or only) slot
in each `(file_type, week_day)` group.

Two `LEFT JOIN LATERAL` subqueries then use this:

- **`fp` (today)**: selects the latest `meta_file_processed` row for today
  whose `processed_at::time` falls in `[r.file_time, r.next_file_time)`. When
  `r.next_file_time IS NULL` (last/only slot), the time-of-day filter is
  dropped entirely so a file processed at 01:57 AM still satisfies, say, a
  16:35 slot. For multi-slot file_types like TOSL (16:00 + 17:00), the 16:05
  file falls in `[16:00, 17:00)` and so satisfies the 16:00 slot but not the
  17:00 slot.
- **`lp` (any date)**: same range constraint applied to all historical
  `meta_file_processed` rows, used to determine if the most recent occurrence
  of a weekly/monthly file landed within its expected window.

A `window_start` CTE computes the most-recent expected calendar date for each
`(file_type, week_day)` pair. For specific days (MON–SUN) the formula is
`CURRENT_DATE - ((DOW_current - DOW_scheduled + 7) % 7)`. For `WKDAY` it is
today if today is a weekday, otherwise the most recent Friday.

Status values, in priority order:

| Status | Condition |
|---|---|
| `running` | `meta_etl_run.status = 'running'` for this file_type |
| `error` | Most recent ETL run ended with `status = 'error'` |
| `overdue` | File is expected today, `file_time` has passed, no in-window file found |
| `pending` | File is expected today, `file_time` has not yet passed (or `file_time` is NULL) |
| `done` | A qualifying `meta_file_processed` row exists (today's file, or in-window via `lp`) |
| `optional` | `ref_load_files.optional = TRUE` and no file received |
| `not today` | `week_day` does not match today's day-of-week |

The sort order mirrors the status priority: errors first, then running, then
overdue, pending, done, optional, not-today. Within each band, today's files
sort before others; within today, by `file_time`.

History dots in the schedule grid show the last 5 expected occurrences of each
file type. For daily files (`WKDAY` / `ALL`) an exact date match is required;
for weekly files any `file_date` within the 7-day window following the expected
date counts as received.

## Reprocess button

The per-row "Re" button in the schedule grid calls `POST /api/monitor/reprocess`
with `file_path` and `file_type`. This invokes `load_one_file(force=True,
do_derive=True)`, bypassing the already-processed check. Because `hist_*`
inserts use `ON CONFLICT DO NOTHING`, re-running is always safe; it will insert
only genuinely new rows and rerun the derive cascade.

After a successful reprocess the UI refreshes the schedule grid and the KPI
summary.

## "Run Missing Derives"

The status bar contains two derive-remediation buttons driven by a day-count
selector (1, 3, 7, 14, 30, 60, 90 days):

**Run Missing Derives** (`force=False`): calls `GET /api/monitor/derive-missing`
to preview, then `POST /api/monitor/derive-missing/run`. The server-side
`_find_missing_derive_dates()` queries:

```sql
WITH hist_dates AS (
    SELECT DISTINCT snapshot_date AS d FROM hist_cs
    UNION SELECT DISTINCT snapshot_date FROM hist_f
    UNION SELECT DISTINCT snapshot_date FROM hist_tl
    UNION SELECT DISTINCT snapshot_date FROM hist_td
),
done AS (
    SELECT DISTINCT as_of_date AS d FROM meta_derived_run WHERE status = 'success'
)
SELECT d FROM hist_dates WHERE d NOT IN (SELECT d FROM done)
  [AND d >= CURRENT_DATE - :ndays]
ORDER BY d ASC
```

Dates are derived oldest-to-newest. Per-date failures are caught and logged;
the loop continues to the next date.

**Force Re-derive** (`force=True`): uses `_find_dates_to_rederive()` instead,
which returns every date that already has a successful `meta_derived_run` row.
This is the tool for applying derive-code changes retroactively across the
history.

The UI shows a confirmation dialog with the oldest and newest dates before
running. After completion, the derive-runs panel and the KPI summary are
refreshed.

## Scheduler output log

`meta_scheduler_log` (`log_id`, `logged_at`, `message`, `log_level`,
`file_name`) captures structured log output from the scheduler process. The
`/api/monitor/scheduler/output` endpoint returns the last N rows (default 500)
with optional filters by `log_level` and `file_name` (ILIKE prefix match).

The Scheduler Output panel in the UI displays logs colour-coded by level
(ERROR = red, WARNING = amber, INFO = neutral). Clicking a file name cell in
the schedule grid opens a popup showing logs filtered to that file_type.

## Auto-start launchers

`/api/monitor/startup` reports whether the two Windows Startup-folder bat
files (`TradingDashboard-ETLScheduler.bat` and `TradingDashboard-TradingApp.bat`)
exist. `POST /api/monitor/startup/register` writes them; `POST
/api/monitor/startup/unregister` removes them. The launchers call
`run_scheduler.bat` and `start.bat` in the project root respectively — they
are rewritten on every register call so project-level changes to those scripts
are always picked up.
