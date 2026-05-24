# Trash — 2026-05-12

Files moved here by the cleanup pass on 2026-05-12. Nothing was deleted outright.
Restore by moving a file back to its original path. If everything still works after
a few days, this directory can be deleted.

## Contents

### `web/` — old app.js variants
The canonical file is `web/app.js`. These variants were left behind by an earlier
refactor. Confirmed: only `web/app.js` is referenced from `web/index.html`.

- `app.js.clean`   (14,686 bytes, May 11 00:27)
- `app.js.fixed`   (17,252 bytes, May 11 00:40)
- `app.js.head`    (11,559 bytes, May 10 23:58)
- `app.js.new`     (13,654 bytes, May 11 00:38)
- `index.html.clean` (0 bytes)

### `api/`
- `main.py.bak.trace` (74 KB) — stale backup of api/main.py.

### `db/`
- `15_drv2_views.sql.bak` (25 KB) — stale backup of a migration that no longer exists at that number.
- `fix_source_expr_typos.sql` — unnumbered orphan SQL, not referenced by any code.

### Root
- `drv_formulas_reference - Copy.xlsx` — Windows "Copy" accidental duplicate of the live reference workbook.

### `root_scripts/` — finished one-off scripts that lived at the project root
These were used once during the drv2 / migration cleanup phase and are not part of
the production code path. `run_migrations.py` was *kept* at the project root
because it is the generic migration runner.

- `cleanup_and_apply.py`        — finished drv2 cleanup
- `run_schema_and_derive.py`    — hardcoded to db/15_drv2_tables.sql
- `run_sql_file.py`             — hardcoded to db/20_data_filter_logic.sql
- `remove_legacy_cols.py`       — finished xlsx column strip
- `debug_api.py`                — ad-hoc debug
- `query_null_source_expr.py`   — ad-hoc diagnostic
- `summary_null_source_expr.py` — ad-hoc diagnostic
- `show_atomic_input_missing.py`— ad-hoc diagnostic

## Files moved but NOT trashed
Three urllib smoke scripts at the project root (`test_api.py`,
`test_ref_endpoint.py`, `test_stats.py`) were moved to `scripts/smoke/` rather than
trashed — they hit a live :8000 server and are still occasionally useful.

## 2026-05-12 — Migration consolidation pass

### `db/migrations_consolidated_into_baseline/`
The 33 numbered migration files `db/01_*.sql` through `db/35_*.sql` (with gaps
at 08 and 17). Their effects are folded into `db/baseline.sql`. Restored only
if you need to apply incremental upgrades to a database that hasn't yet
absorbed the consolidation.

### `root_scripts/run_migrations.py`
Was at the project root. Audit initially classified it as a generic migration
runner (based on its docstring "Run database migrations in order"), but it
turned out to be hardcoded to migrations 26/27/28. Now obsolete.

### Related code changes (not files moved, just edits)
- `db/init_db.py` docstring updated to reference `baseline.sql`.
- `etl/execute_build.py`, `etl/generate_cat_ddl.py`, `etl/ma_codegen.py`:
  output redirected from `db/14_drv_cat_tables.sql` to `db/drv_cat_tables.sql`
  (un-numbered, auto-discovered by `init_db.py`'s glob).
- Inline comments in `api/main.py`, `etl/derive.py`, and `CLAUDE.md` that
  referenced specific numbered migrations now point at `db/baseline.sql`.
