# Trading Dashboard — Claude Reference

Index file only. Detail lives in `docs/`. See Lookup index below.

---

## What it is

Local single-user web app + PostgreSQL that replaces `Tickers YYYY-MM-DD.xlsx`. 17 source feeds → derived tables → atomic + composite rules engine → action recommendations + outcome tracking.

---

## Stack

Python 3.11 / FastAPI + uvicorn (`127.0.0.1:8000`) / PostgreSQL 17 (`trading` db, `localhost:5432`) / SQLAlchemy 2 + psycopg v3 / pandas + openpyxl / vanilla JS + Chart.js (CDN)

---

## Top-level layout (settled — extend, don't rearrange)

```
trading-dashboard/
  setup.bat / start.bat
  config/settings.py
  api/    main.py, _helpers.py, models.py, routers/{health,dash,monitor,ref,rules,trace,pages}.py
  db/     baseline.sql (schema + migrations), seeds_*.sql, init_db.py
  etl/    LIVE ingest+derive (imported by entrypoints):
            scheduler.py, etl_load.py, load_raw.py, excel_io.py, casters.py,
            mappings.py, refresh_ref.py, cleanup.py, daily_health_check.py,
            tickers_initial_load.py, db.py, _logging.py, warnings.py, notify.py,
            derive.py, derive_v2.py, _derive_common.py, derive_cat_atomic_input.py,
            derive_outlook_action.py, derive_actionable.py, derive_realized.py,
            derive_freshness.py, rule_groups.py, rebuild_rules.py,
            compute_outcomes.py, mark_sales.py, ma_codegen.py
          BUILD/CODEGEN one-offs (run manually via `python -m`, not in runtime path):
            execute_build.py, auto_enrich_registry.py, seed_ref_ma_columns.py,
            enrich_ref_ma_columns.py, generate_cat_ddl.py, generate_drv2_views.py,
            build_drv_cat_layers.py, gen_data_flow_doc.py,
            check_null_columns(_v2).py, check_hist_to_nulls.py
          UNUSED (no importer; safe to delete): position_rules.py
          working/  runtime ingest dir (source files + scheduler lock/logs — not code)
  web/    per-screen .html + .js, shared styles.css + _common.js
  docs/   design docs (+ docs/diagrams/*.svg, docs/audit/*.md)
```
> Root-level loose scripts (`check_*`, `debug_*`, `fix_*`, `test_*`, `verify_*`,
> `_trash_2026-05-12/`, `docs_backup_2026-05-20/`, `*.log`) are throwaway/cruft, not part
> of the settled layout. See `docs/audit/unused_code_report.md`.

---

## Database — 4 table families

- `ref_*` — reference/lookup. Tunable tables refresh via `etl/refresh_ref.py`.
- `hist_*` — raw history, append-only (y, tl, td, tw, to, rr, call, etf, etfchg, ii, iichg, ssh, ps, f, cs, cst, ft). PK `(snapshot_date, symbol[, sequence|account])`.
- `drv_*` — derived, idempotent (`DELETE WHERE as_of_date=D` → INSERT). Key tables:
  - **`drv_ma`** — **compatibility VIEW** (not a table as of 2026-05-31). JOINs the 5 component tables. Never INSERT into it.
  - `drv_symbols`, `drv_technicals`, `drv_fundamentals`, `drv_outlooks`, `drv_portfolio` — 5 component tables written by derive_all (replaced drv_ma).
  - `drv_dash`, `drv_stks`, `drv_dash_summary`, `drv_trig`, `drv_rule_outcome`, `drv_quote`, `drv_rr`, `drv_cat_atomic_input`, `drv_realized_gain`, `drv_cs_realized_gain`.
  - `drv_actionable` — final recommendation per symbol. Columns: `consolidated_action`, `trig_action` (SA/STM/SS/BM vocab), `triggered_group_ids` JSONB, `source_actions` JSONB.
- `meta_*` — operational (etl_run, file_processed, cleanup_policy, derived_run, scheduler_log).

Also: `user_action_log`, `ref_settings`, `v_rule_performance` view.

---

## Snapshot-date mental model

```
user picks date D → /api/dash?date=D → SELECT * FROM v_dash(D)
  ← drv_dash WHERE as_of_date=D
  ← drv_ma VIEW (drv_symbols + drv_technicals + drv_fundamentals + drv_outlooks + drv_portfolio)
    ← each component table populated from latest hist_* (snapshot_date ≤ D) + drv_quote
  ← hist_* loaded from Excel (ON CONFLICT DO NOTHING)
```

Re-running derive for date D is idempotent. No date is ever silently overwritten.

---

## ETL & rules pipeline

- **Loader**: `etl/scheduler.py` watches 17 source dirs (`ref_load_files`). File events → `etl_load.py::load_one_file` → `mappings.py::HIST_MAPS` or `load_raw.py::CUSTOM_HANDLERS`. Batches 1000 rows; `meta_etl_run` updated live.
- **Derive cascade**: `derive_all(session, D)` order: drv_quote/drv_rr → drv_symbols → drv_technicals/drv_fundamentals/drv_outlooks/drv_portfolio → drv_cat_atomic_input → drv_dash → drv_stks → drv_outlook_action → drv_actionable → drv_trig. All idempotent. `derive_v2.py` overrides v1 for derive_tw/etf/ii/ssh/ps/sss.
- **Actionable**: `derive_outlook_action.py` → per-source actions; `derive_actionable.py` consolidates + rule-group fires → `drv_actionable`. See `docs/actionable_logic.md`.
- **Derive trigger**: every load re-derives its date + any later dates it invalidated. Skip with `--no-derive`.

---

## Rules engine

Three tiers: atomic rules (`ref_trig_atomic_rule`) → composite rules (`ref_trig_composite_mapping`) → rule groups (`ref_trig_rule_group` + `ref_trig_group_member`). Fired groups feed into `drv_actionable` as synthetic action candidates. Rebuild after edits: `python -m etl.rebuild_rules`. Full logic: `docs/rules_logic.md`, `docs/rule_groups_logic.md`.

---

## Conventions (enforced)

1. **Never delete/overwrite raw hist_*.** `ON CONFLICT DO NOTHING` on all loads. Only `etl/cleanup.py` deletes (via `meta_cleanup_policy`).
2. **Derives are idempotent.** `DELETE WHERE as_of_date=D` then INSERT.
3. **Secrets in `.env` only.** `PG_PASSWORD`. `.env` is gitignored.
4. **Case-insensitive file/sheet matching** everywhere. Use `get_sheet_case_insensitive()` in `load_raw.py`.
5. **Schema changes in `db/baseline.sql`** (consolidated migrations). New seeds → `db/seeds_*.sql`.
6. **DB access via SQLAlchemy + psycopg v3 only.** No other drivers.
7. **SQL command length ≤ 965 bytes.**
8. **Top-level layout is settled** — extend, don't rearrange.
9. **Plan first → ask permission** (unless user explicitly says to proceed). Hard rule.
10. **`CLAUDE.md` is an index, not a detail doc.** Detail lives in `docs/<topic>_logic.md`. If tempted to write more than one line of detail here, stop — create or update the relevant `docs/` file and add one Lookup row instead.
11. **Read `docs/` files only when needed.** On session start, read only `CLAUDE.md`. Then ask the user which screen(s) or feature(s) they plan to work on. Read only the relevant `docs/` files based on that answer. Do NOT pre-emptively read all detail docs.
12. **Responses**: short Summary (only what user must act on) → Details → Notes (only if actionable) → Questions (only if real). No padding. Hard rule.
13. **Commit all code changes to git** with clear messages.
14. **Push back on wasteful requests.** State concern + better option under `### Worth reconsidering`. Use sparingly. Hard rule.
15. **tos_symbol in all drv_*.** Never use raw `symbol` in derive functions. `symbol` column exists in `hist_*` only. See `docs/tos_symbol_normalization.md`.
16. **Brief description + permission for DB or non-trivial logic changes.** One line, wait for approval. Excludes typo fixes and approved renames.

---

## Cheat sheet

```cmd
setup.bat                                      :: one-time
python -m etl.tickers_initial_load             :: bootstrap full workbook
python -m etl.etl_load "PATH\TO\FILE.xlsx"     :: manual single file
python -m etl.scheduler                        :: continuous folder watcher (loads + derives)
python -m etl.refresh_ref [--table NAME]       :: refresh tunable ref tables
python -m etl.rebuild_rules                    :: recompile rules after trig workbook edits
python -m etl.cleanup [--dry-run]              :: retention sweep
python -m db.init_db [--reset-audit]           :: idempotent DDL apply
start.bat                                      :: launch app (opens browser after 5 s)
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir api
pytest tests/                                  :: all tests (DB tests auto-skip if Postgres absent)
pytest tests/test_FILE.py -k test_name        :: single test; pure-Python tests never need DB
```

---

## Adding a new source-file type

1. Add row to `LoadFiles.xlsx` (`source_dir | file_type | tab | weekday | time`).
2. `python -m etl.tickers_initial_load`.
3. Generic mapping → `mappings.py::HIST_MAPS['XYZ']`. Custom → `load_raw.py` + `CUSTOM_HANDLERS`.
4. Add `hist_xyz` to `baseline.sql`. If derived: add `_derive_xyz_impl` + `derive_xyz = _wrap(...)` in `derive.py`, wire into `derive_all()`.
5. `python -m db.init_db`.

---

## File-truncation warning

Large edits can land **truncated** on disk even when the tool reports success. Always verify after any non-trivial edit:

```bash
python3 -c "import ast; ast.parse(open('PATH').read())" || echo TRUNCATED   # Python
node --check PATH || echo TRUNCATED                                          # JS
tail -10 PATH                                                                # always
```

If truncated, **don't re-Edit** — append the missing tail via bash heredoc. Smaller edits truncate less.

---

## Gotchas

- **Always `--reload-dir api`** with uvicorn — without it, `etl/working/` heartbeat writes trigger constant reloads on Windows.
- **`init_db` swallows DO blocks** — for DO-block migrations, also provide a `migrate_X.py`. Template: `migrate_ref_load_files_pk.py`.
- **git lock files on Windows mount** — `.git/index.lock` / `.git/HEAD.lock` can stick after agent-based commits. Delete from Windows Explorer before next git op.
- **Mount staleness** — `stat`/`wc` can lag on the sandbox mount. Use `cat`/`tail -c N`.
- **Composite PKs in /ref UI** — `web/ref.js` renders PK columns read-only. Prefer single-col PK + UNIQUE.

---

## Common errors

- `relation "drv_*" does not exist` → `python -m db.init_db`
- `password authentication failed` → fix `PG_PASSWORD` in `.env`
- `0 read 0 inserted 0 skipped` → header mismatch → fix `etl/mappings.py`
- Workbook edits to tunable refs not propagating → `python -m etl.refresh_ref`
- `derive_trig: no atomic rules loaded` → `ref_trig_atomic_rule` empty; reload workbook Trig tab
- Re-run reprocesses already-loaded files → only after `init_db --reset-audit`
- Scheduler "watched dir missing" → create dir or update `LoadFiles.xlsx`

---

## Lookup index

| Need | Look in |
|---|---|
| TL tab column map | `etl/mappings.py::HIST_MAPS['TL']` |
| drv_ma component table derive functions | `etl/derive.py::_derive_symbols/technicals/fundamentals/outlooks/portfolio_impl` |
| Vlm projection formula | `etl/derive.py::_derive_technicals_impl` |
| Outlook → weight mapping | `ref_param` where `sheet='outlook'` |
| Atomic rules feeding a composite | `ref_trig_composite_mapping WHERE composite_rule_code=...` |
| Why a load skipped a row | `meta_etl_run.rows_skipped` |
| Why a derive looks wrong | `meta_derived_run` then `drv_ma` VIEW for that symbol/date |
| Last successful file load | `meta_file_processed.processed_at` |
| FastAPI endpoints | `api/routers/*.py` |
| Section classifier | `etl/derive.py::_classify_section` + `web/app.js::classifySymbolSection` |
| Cash detection rules | `api/routers/dash.py` (`F_IS_CASH`, `CS_IS_CASH_C` SQL fragments) |
| Actionable / outlook-action logic | `docs/actionable_logic.md` |
| Actionable screen 3 action columns | `docs/actionable_logic.md` (consolidated_action, TrTnBBRskRng, Trig) |
| trig_action computation (BuySell vocab) | `etl/derive_actionable.py::_derive_actionable_impl` (buysell_scores block) |
| Atomic-input column derivation (JF..NP + QE..QT) | `docs/drv_cat_atomic_input_logic.md` |
| Dashboard single-cell scalars (Dash!$X$Y) | `ref_param sheet='dash'`; `etl/derive_cat_atomic_input.py::get_dash_scalar` |
| TOS composite-field decoding (a_bb_streak, a_bb_high_low, a_volume_spike) | `etl/derive_cat_atomic_input.py::compute_intermediates` |
| Dashboard / snapshot-date logic | `docs/dashboard_logic.md` |
| File Monitor logic | `docs/file_monitor_logic.md` |
| Rules engine logic | `docs/rules_logic.md` |
| Rule groups logic | `docs/rule_groups_logic.md` |
| Performance / feedback-loop logic | `docs/performance_logic.md` |
| Symbol normalization (tos_symbol) | `docs/tos_symbol_normalization.md` |
| tos_symbol population — 4 groups (detail) | `detailed_tos_groups.md` |
| tos_symbol fallback/strategy (Groups 2–4) | `strategy_and_fallback_details.md` |
| Screen overview, data-flow, column lineage | `docs/Screen_and_DataFlow_Reference.md` |
| Flow diagrams (pipeline, derive cascade, rules) | `docs/diagrams/*.svg`, `docs/audit/architecture_flow.md` |
| Unused DB tables/columns audit | `docs/audit/unused_db_report.md` |
| Unused/cruft code files audit | `docs/audit/unused_code_report.md` |
| Full command reference + web endpoints + troubleshooting table | `COMMANDS.md` |

---

## Recent Migrations (2026-05-31)

- **drv_ma → VIEW**: Now a JOIN VIEW over `drv_symbols`, `drv_technicals`, `drv_fundamentals`, `drv_outlooks`, `drv_portfolio`. Never INSERT into it. `python -m db.init_db` applies the migration on existing DBs.
- **derive_all cascade**: `derive_ma` removed; 5 component derives run in its place (after drv_quote/drv_rr, before drv_cat_atomic_input).
- **trig_action on drv_actionable**: Third action column (SA/STM/SS/BM). Computed from fired rule groups via `ref_param_lookup` buysell scores.
- **git lock gotcha**: `.git/index.lock` / `.git/HEAD.lock` may stick after agent commits on Windows-mounted repos. Delete from Explorer before next git op.

## Recent Migrations (2026-05-29)

- **tos_symbol**: All `drv_*` use `tos_symbol` exclusively. `symbol` kept in `hist_*` only.
- **RR loader**: `load_rr()` in `load_raw.py`, registered in `CUSTOM_HANDLERS['rr']`.
- **hist_ps**: Uses `ticker` column; mapped to `tos_symbol` via `_populate_ps_tos_symbol()` through `ref_rrt`.
- **Schema migration pattern**: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `baseline.sql`.
