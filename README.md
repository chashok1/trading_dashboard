# Trading Dashboard

A local single-user web app + PostgreSQL database that replaces manual trading workbook management. Ingests 17 source feeds, derives analytical tables, runs a rules engine over ticker data, and tracks user actions for outcome feedback.

**Owner**: Ashok (chashok@yahoo.com)

## Stack

- **Backend**: Python 3.11+, FastAPI + uvicorn (`127.0.0.1:8000`)
- **Database**: PostgreSQL 17 (`localhost:5432`, db: `trading`)
- **ORM**: SQLAlchemy 2 + psycopg v3
- **Data**: pandas + openpyxl (Excel ingestion)
- **Config**: pydantic-settings (`.env` file)
- **Monitoring**: watchdog (folder-watch ETL trigger)
- **Frontend**: Vanilla JS + Chart.js (CDN, no build step)

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 17 (running on `localhost:5432`)
- `.env` file with `PG_PASSWORD` set

### Setup

```bash
# One-time setup
setup.bat

# Verify database is ready
python -m db.init_db

# Bootstrap with full workbook (first run only)
python -m etl.tickers_initial_load

# Start the app
start.bat
```

The app runs on `http://127.0.0.1:8000`

## Architecture

### Database: 4 table families

- **`ref_*`** — Reference/lookup tables (~17 tables). Loaded with `ON CONFLICT DO NOTHING`.
- **`hist_*`** — Raw history, append-only (~15 tables). PK: `(snapshot_date, symbol, ...)`.
- **`drv_*`** — Derived tables (idempotent). Central: `drv_ma`, `drv_dash`, `drv_stks`, `drv_trig`, `drv_actionable`.
- **`meta_*`** — Operational metadata: `meta_etl_run`, `meta_file_processed`, `meta_derived_run`, etc.

### Core Pipelines

1. **Loader** (`etl/scheduler.py`): Watches 17 source directories, dispatches file loads to `etl_load.py`.
2. **Derive Cascade** (`etl/derive.py`): Runs idempotent derivations for each date (quote → ma → dash → stks → trig → actionable).
3. **Rules Engine**: Atomic predicates → Composite rules → Rule groups → User actions.
4. **Feedback Loop** (`etl/compute_outcomes.py`): Tracks rule performance via `v_rule_performance`.

### File Layout

```
trading-dashboard/
  setup.bat / start.bat
  config/settings.py
  api/      FastAPI routes (health, dash, monitor, ref, rules, trace, pages)
  db/       baseline.sql (schema), init_db.py
  etl/      loaders, derivations, rules, scheduler
  web/      HTML + JS per-screen, shared styles
  docs/     design docs (actionable, dashboard, rules, etc.)
```

## Common Commands

```bash
# Continuous folder watcher + auto-derive
python -m etl.scheduler

# Manual single-file load
python -m etl.etl_load "PATH\TO\FILE.xlsx"

# Refresh tunable reference tables
python -m etl.refresh_ref [--table NAME]

# Data retention cleanup
python -m etl.cleanup [--dry-run]

# Apply schema migrations
python -m db.init_db [--reset-audit]

# Rebuild rules after workbook edits
python -m etl.rebuild_rules
```

## Key Conventions

1. **Never delete raw data** — Only `etl/cleanup.py` deletes (driven by `meta_cleanup_policy`).
2. **Never overwrite raw data** — All `hist_*` inserts use `ON CONFLICT DO NOTHING`.
3. **Derives are idempotent** — Each re-run for date D produces identical results.
4. **Secrets in `.env` only** — `.env` is gitignored; set `PG_PASSWORD` there.
5. **Case-insensitive matching** — File and sheet names use case-insensitive comparison.
6. **One-time setup** — Run `setup.bat` once; subsequent starts use `start.bat`.

## Development

For architecture & logic details, see `docs/`:
- `docs/dashboard_logic.md` — Snapshot-date & dashboard view model
- `docs/rules_logic.md` — Rules engine (atomic, composite, groups)
- `docs/actionable_logic.md` — Outlook → actionable consolidation
- `docs/file_monitor_logic.md` — File Monitor endpoints & scheduling
- `docs/performance_logic.md` — Feedback loop & rule performance tracking

## License

Private. For personal use only.
