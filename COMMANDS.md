# Trading Dashboard — Command Reference

All commands should be run from the project root directory: `C:\Ashok\Invest\Projects\trading-dashboard\`

---

## Setup & Infrastructure

### One-time setup
```cmd
setup.bat
```
Installs Python dependencies and initializes the database schema. Run this once after cloning.

### Initialize/reset database (idempotent)
```cmd
python -m db.init_db
```
Runs all DDL files (`db/*.sql`) to create tables, views, and functions. Safe to run anytime—uses `IF NOT EXISTS`.

### Reset database (development only — deletes all data)
```cmd
python -m db.reset_db
```
Truncates all hist_*, drv_*, ref_*, and meta_* tables. Use only when you need a clean slate for testing.

---

## Data Loading (ETL)

### Load full Tickers workbook
```cmd
python -m etl.tickers_initial_load
```
One-time load: reads the complete `Tickers YYYY-MM-DD.xlsx` file (or the one in `Cluade\Cluade\`), loads all ref_* and hist_* tables, and derives all tables for the snapshot date in the filename.

**When to use:** Initial setup, or to reload everything from a fresh workbook.

### Load a single source file (manual one-off)
```cmd
python -m etl.etl_load "C:\Ashok\Investing\Stocks\PS\Archive\PS 2026-05-04.xlsx"
```
Loads one source file (e.g., PS, TL, Y) into the matching `hist_*` table and re-derives for that date.

**When to use:** Manual ingestion of a single file, or testing a new file type.

### Continuous folder watcher
```cmd
python -m etl.scheduler
```
Monitors all 17 source folders (defined in `ref_load_files`). When a new `*.xlsx` appears, automatically loads it (with dedup) and triggers derive for that date.

**When to use:** Leave this running during normal operations to auto-ingest new files.

### Refresh tunable reference data
```cmd
python -m etl.refresh_ref
```
Reloads all tunable reference tables (Trig rules, Parm thresholds, sector classifications, etc.) from the workbook. Uses `ON CONFLICT DO UPDATE` so edits propagate.

**Refresh a single table:**
```cmd
python -m etl.refresh_ref --table ref_trig_atomic_rule
```

**When to use:** After editing Trig rules, Parm values, sector mappings, or rule descriptions in the workbook.

---

## Maintenance

### Trim old data per retention policy
```cmd
python -m etl.cleanup --dry-run
```
Preview what rows will be deleted (based on `meta_cleanup_policy`). Doesn't make changes.

```cmd
python -m etl.cleanup
```
Actually delete rows older than the retention period. Uses the dry-run preview first if unsure.

**When to use:** Monthly, to keep database size under control. Never deletes data loaded in the current month.

---

## API & Dashboard

### Launch the web dashboard
```cmd
start.bat
```
Starts the FastAPI server on `127.0.0.1:8000` and opens the dashboard in your browser.

**Access points:**
- `/` — Dashboard (main view, donut + sector bar)
- `/cockpit` — Action Cockpit (log actions, view recommendations)
- `/rules` — Rules Manager (view atomic/composite rules)
- `/rule-performance` — Rule hit-rate tracker
- `/trace` — Symbol Trace (per-rule evaluation for one ticker)
- `/trig` — Trig Rules Analyzer (per-symbol triggered rules)
- `/explore` — Data Explorer (browse any table with filters)
- `/ref` — Ref Data maintenance (CRUD + Excel reload)

### Stop the API
`Ctrl+C` in the terminal where `start.bat` is running.

---

## Database Queries (Direct Access)

If you need to query the database directly, use pgAdmin, SQLTools (VS Code), or `psql`:

### List all tables
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY 1;
```

### Check row counts
```sql
SELECT table_name, (SELECT COUNT(*) FROM <table>) as row_count
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
ORDER BY table_name;
```

### View recent ETL runs
```sql
SELECT * FROM meta_etl_run
ORDER BY started_at DESC
LIMIT 20;
```

### View recent derived runs
```sql
SELECT * FROM meta_derived_run
ORDER BY started_at DESC
LIMIT 20;
```

### Check cleanup history
```sql
SELECT * FROM meta_cleanup_history
ORDER BY run_at DESC
LIMIT 10;
```

---

## Testing & Debugging

### Test one source file load
```cmd
python -m etl.etl_load "C:\path\to\file.xlsx"
```
Loads and derives for the date in the filename. Safe to repeat—dedup prevents double-loads.

### Test ref table fetch
```cmd
python test_ref_endpoint.py
```
Calls the `/api/ref/{table_name}` endpoint and prints the result.

### Check available dates
```cmd
python -m db.init_db
python -c "from sqlalchemy import create_engine, text; from config.settings import settings; engine = create_engine(settings.sqlalchemy_url); conn = engine.connect(); result = conn.execute(text('SELECT DISTINCT as_of_date FROM drv_ma ORDER BY 1 DESC LIMIT 10')); print('\n'.join(str(r[0]) for r in result))"
```
Lists the 10 most recent snapshot dates available in `drv_ma`.

---

## Quick Troubleshooting

| Issue | Command |
|-------|---------|
| Tables don't exist | `python -m db.init_db` |
| Old cached file keeps loading | Browser: `Ctrl+Shift+R` (hard refresh) |
| "File already processed" errors | Dedupe is working; safe to ignore unless file is genuinely new |
| "No atomic rules loaded" | `python -m etl.tickers_initial_load` (populates `ref_trig_atomic_rule`) |
| Data looks stale | `python -m etl.scheduler` (watches for new files) or manually load a file |
| Cleanup deleting too much | Edit `meta_cleanup_policy` table directly; defaults are 90-day retention |

---

## Environment

- **Database:** PostgreSQL 17 on `localhost:5432`, database `trading`
- **Credentials:** Stored in `.env` (gitignored; create from `.env.example`)
- **Python:** 3.11+ in venv
- **API:** FastAPI on `127.0.0.1:8000`
- **Browser:** Any modern browser (Chrome, Firefox, Edge)
