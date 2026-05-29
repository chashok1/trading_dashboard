# Trading Dashboard — Claude Reference

Minimal context for any future Claude session. Functionality and conventions only — no UI/layout detail.

---

## What it is

Local single-user web app + PostgreSQL DB that replaces the `Tickers YYYY-MM-DD.xlsx` workbook. Ingests 17 source feeds, derives ~15 analytical tables, runs an atomic + composite rules engine over the TL master ticker list, surfaces actions to the user, and tracks user actions for an outcome-feedback loop.

Owner: Ashok (chashok@yahoo.com).

---

## Stack

- Python 3.11+, FastAPI + uvicorn on `127.0.0.1:8000`
- PostgreSQL 17, db `trading` on `localhost:5432`
- SQLAlchemy 2 + psycopg v3 (`postgresql+psycopg://`)
- pandas + openpyxl for Excel ingestion
- pydantic + pydantic-settings (config in `.env`, secret = `PG_PASSWORD`)
- watchdog for folder-watch ETL trigger
- Front end: vanilla JS + Chart.js (CDN), no build step

---

## Top-level layout (settled — extend, don't rearrange)

```
trading-dashboard/
  setup.bat / start.bat
  config/settings.py
  api/    main.py, _helpers.py, routers/{health,dash,monitor,ref,rules,trace,pages}.py
  db/     baseline.sql (consolidated schema + migrations), seeds_*.sql, init_db.py
  etl/    load_raw.py, etl_load.py, refresh_ref.py, mappings.py,
          derive.py, derive_v2.py, _derive_common.py,
          derive_outlook_action.py, derive_actionable.py,
          position_rules.py, rule_groups.py, compute_outcomes.py,
          scheduler.py, daily_health_check.py, cleanup.py,
          tickers_initial_load.py
  web/    per-screen .html + .js, shared styles.css + _common.js
  docs/   design docs
```

---

## Database — 4 table families

- `ref_*` — reference/lookup (~17 tables). Loaded with `ON CONFLICT DO NOTHING`; tunable tables refresh via `etl/refresh_ref.py` (`DO UPDATE`).
- `hist_*` — raw history, append-only (~15 tables: y, tl, td, tw, to, rr, call, etf, etfchg, ii, iichg, ssh, ps, f, cs, cst, ft). PK `(snapshot_date, symbol[, sequence|account])`.
- `drv_*` — derived, **idempotent** (`DELETE WHERE as_of_date=D` → INSERT). Central tables: `drv_ma` (master aggregate, replaces 641-col MA tab), `drv_dash`, `drv_stks`, `drv_dash_summary`, `drv_trig`, `drv_rule_outcome`, `drv_actionable`, `drv_quote` (latest-loaded-wins quote merge across y/tl/td), `drv_realized_gain` (FIFO), `drv_cs_realized_gain`.
- `meta_*` — operational: `meta_etl_run`, `meta_file_processed`, `meta_cleanup_policy`, `meta_cleanup_history`, `meta_derived_run`, `meta_scheduler_log`.

Rule-engine v2 also has: `user_action_log`, `ref_settings`, view `v_rule_performance`, JSONB `triggered_atomic_ids`/`triggered_composite_ids` on `drv_stks`.

SQL functions in `baseline.sql`: `v_dash(d)`, `v_stks(d)`, `v_ma(d)`, `v_dash_summary(d)`, `v_available_dates`, `v_symbol_history(symbol)`, `v_rule_performance_window(...)`.

---

## Snapshot-date mental model

```
user picks date D → /api/dash?date=D → SELECT * FROM v_dash(D)
  ← drv_dash WHERE as_of_date=D
  ← drv_ma(D) joins latest hist_* (snapshot_date ≤ D) + drv_td/tw + drv_quote (COALESCE for price/rsi/imp_volatility; hist_tl quote + vlm_projected read inline in the `tl` CTE)
  ← hist_* rows loaded from Excel via etl/etl_load.py (ON CONFLICT DO NOTHING)
```

Re-running derive for date D is idempotent: same numbers; only date D's derivatives change. No date is ever silently overwritten.

---

## ETL & rules pipeline

- **Loader path**: `etl/scheduler.py` watches the 17 source dirs (driven by `ref_load_files`). On a file event it calls `etl/etl_load.py::load_one_file`, which dispatches by file_type to a generic mapping in `etl/mappings.py::HIST_MAPS` or a custom handler in `etl/load_raw.py::CUSTOM_HANDLERS`. Commits per 1000-row batch; `meta_etl_run` updated live.
- **Derive cascade**: `etl/derive.py::derive_all(session, D)` runs every `derive_*` function (drv_quote → drv_cat_* → drv_ma → drv_dash → drv_stks → drv_trig → drv_rule_outcome → drv_actionable etc.). Each is idempotent. `derive_v2.py` overrides v1 implementations of `derive_tw/etf/ii/ssh/ps/sss` at module load.
- **Outlook + actionable layer**: `derive_outlook_action.py` → per-source actions; `derive_actionable.py` consolidates them + rule-group fires into `drv_actionable`. Full logic: `docs/actionable_logic.md`.
- **Feedback loop**: `etl/compute_outcomes.py` joins `user_action_log` against subsequent price moves to feed `v_rule_performance` (per-rule hit rate, avg P&L).
- **Derive trigger**: every load runs the full derive cascade in-process — `derive_all` for the file's date, then a forward re-derive of any later dates the load invalidated (`etl/etl_load.py::load_one_file`). Skip with `--no-derive` (bulk loads). The File Monitor's "Reprocess" and "Run Missing Derives" buttons derive too.

---

## Rules engine

- **Atomic rules** live in `ref_trig_atomic_rule` — single-condition predicates (e.g. RSI > X). Evaluated per (symbol, date) into `drv_trig`.
- **Composite rules** in `ref_trig_composite_rule` + mapping table `ref_trig_composite_mapping` — boolean expressions over atomic rule outcomes. A composite "fires" when its expression evaluates true.
- **Position rules** (`etl/position_rules.py`) apply atomic suppressions based on whether the symbol is held / in IRA / cash / etc.
- **Rule groups** (`etl/rule_groups.py`) bundle composites into actionable "groups" with preconditions; the winning group per symbol drives `drv_actionable.consolidated_action`.
- **Trace screen** (`api/routers/trace.py`) shows per-rule fire status, computed value, applied flag, and per-rule didn't-fire reason for a symbol+date.
- **Performance**: `v_rule_performance` reports historical accuracy. `etl/rebuild_rules.py` runs a one-command rebuild after a workbook edit.

---

## Portfolio + quotes

- `drv_quote` is a per-snapshot latest-loaded-wins merge across hist_y / hist_tl / hist_td for 8 quote fields (last_price, net_chng, pct_change, open, high, low, rsi, imp_volatility). Priority: latest loaded_at, then sequence desc.
- `drv_ma` reads price/rsi/imp_volatility via `COALESCE(drv_quote.X, tl.X)`.
- **Portfolio API** (`api/routers/dash.py::/api/portfolio`) returns held positions across F (Fidelity) + CS (Schwab) sources. Cash detection: F = `SPAXX**` or description contains "HELD IN MONEY MARKET"; CS = `Cash & Cash Investments` or `security_type='Cash and Money Market'`. SQL fragments `F_IS_CASH / F_IS_NOT_CASH / CS_IS_CASH_C / CS_IS_NOT_CASH_C` (the `_C` variants prefix `c.` for queries joining hist_cs).
- **Latest-prices toggle** re-prices held positions via drv_quote.last_price with prev_close from hist_td. Client side recomputes tiles from `state.filtered`, splitting cash vs. non-cash rows.
- **Today's Gain** (Schwab-style) = held day_change + intraday-on-sold + DIV/INT settled.
- **Realized P&L**: FIFO matching of buys vs. sells lives in `drv_realized_gain` (F) and `drv_cs_realized_gain` (CS).

---

## File Monitor

- Endpoints in `api/routers/monitor.py`: summary, schedule, etl-runs, derive-runs, live (SSE), scheduler control, startup (Windows task scheduler), reprocess, derive-missing + derive-missing/run.
- `ref_load_files` has composite PK `(file_type, week_day, file_time)` allowing multi-slot schedules per file_type. Status logic uses an `r_slots` CTE with `LEAD(file_time)` and LATERAL joins matching files in `[file_time, next_file_time)` — last/only slot accepts any time-of-day so overnight loads still register.
- "Run Missing Derives" accepts `last_n_days` (1, 3, 7, 14, 30, 60, 90); finds snapshot_dates with hist_* data but no successful `meta_derived_run` row, runs `derive_all` oldest→newest.

---

## Conventions (enforced)

1. **Never delete raw data via ETL.** Only `etl/cleanup.py` deletes, driven by `meta_cleanup_policy`. (The Explore screen also exposes ad-hoc deletes on any table — admin path; use with care.)
2. **Never overwrite raw data via ETL.** All `hist_*` inserts use `ON CONFLICT DO NOTHING`. (The Explore screen also permits ad-hoc cell edits and row inserts on any table.)
3. **Derives are idempotent.** Each `derive_*` does `DELETE WHERE as_of_date=D` then INSERT.
4. **Secrets only in `.env`.** `PG_PASSWORD` is the main one. `.env` is gitignored.
5. **File and sheet name matching is case-insensitive everywhere.** Use `get_sheet_case_insensitive()` in `load_raw.py`; file-type matching in `etl_load.py` is also case-insensitive.
6. **Schema changes live in `db/baseline.sql`** (migrations consolidated). New seeds → `db/seeds_*.sql`.
7. **DB access goes through SQLAlchemy + psycopg v3** — don't introduce other drivers.
8. **SQL command length must stay ≤ 965 bytes.**
9. **Top-level layout is settled** — extend, don't rearrange.
10. **ETL loads commit per 1000-row batch**; progress prints `[Table] batch X/Y (pct%) cumulative: N inserted, M skipped`.
11. **Plan first → ask permission** (unless the user explicitly says to do it). This is a hard rule from the user.
12. **Per-screen / per-feature deep-dive docs live in `docs/`.** One file per topic (`docs/<topic>_logic.md`). `CLAUDE.md` carries only a one-line pointer in the Lookup index — never the full detail. To request one, say "document the X screen/logic" and Claude creates/updates `docs/X_logic.md` plus the index row.
13. **Responses use a structured format.** Lead with a short **Summary** — ONLY what the user must act on or pay attention to. Problems Claude both caused and fixed itself (e.g. file-truncation-on-write and its splice recovery) must NOT appear in the Summary — move them to **Details** under a subheading, or omit them entirely. Then **Details**. Include a **Notes** section ONLY when there is a precise, actionable point to make — omit the section entirely when there is none; never pad it. End with **Questions** only if there are real questions. Keep every section to the minimum detail required — not verbose. Skip the scaffolding for trivial one-line answers. Hard rule from the user.
14. **Manage code changes through git.** All code modifications must be committed to the repository with clear commit messages. This creates a complete audit trail and enables rollback if needed. Claude will create commits for code changes going forward.
15. **Push back on wasteful or unnecessary requests.** When a request is genuinely wasteful, redundant, or there is a materially better approach, say so instead of just complying — raise it as a subsection under **Notes** (e.g. a `### Worth reconsidering` subheading) stating the concern and the better option. Use this sparingly: only when it genuinely matters, never as routine commentary on ordinary requests. Hard rule from the user.
16. **Symbol normalization: use tos_symbol in all derives.** All `hist_*` tables have a `tos_symbol` column populated during the ETL load/populate phase. All derive functions (`drv_*`) must use `tos_symbol` as the primary symbol key, never raw `symbol`. This includes: symbol universe CTEs, joins between tables, GROUP BY clauses, and output rows. The populate phase guarantees 100% population of `tos_symbol`, so no `COALESCE(tos_symbol, symbol)` is needed. See `docs/tos_symbol_normalization.md` for details.

---

## Cheat sheet

```cmd
setup.bat                                      :: one-time
python -m etl.tickers_initial_load             :: bootstrap full workbook
python -m etl.etl_load "PATH\TO\FILE.xlsx"     :: manual single file
python -m etl.scheduler                        :: continuous folder watcher (loads + derives)
python -m etl.refresh_ref [--table NAME]       :: refresh tunable ref tables
python -m etl.cleanup [--dry-run]              :: retention sweep
python -m db.init_db [--reset-audit]           :: idempotent DDL apply
start.bat                                      :: launch app
```

---

## Adding a new source-file type

1. Add a row to `LoadFiles.xlsx` (`source_dir | file_type | tab | weekday | time`).
2. Run `python -m etl.tickers_initial_load` to absorb the LoadFiles edit.
3. Generic mapping → `etl/mappings.py::HIST_MAPS['XYZ']`. Custom → write `load_xyz()` in `etl/load_raw.py` and register in `etl/etl_load.py::CUSTOM_HANDLERS`.
4. Add `hist_xyz` (and optional `drv_xyz`) to `db/baseline.sql`. If derived, add `_derive_xyz_impl` + `derive_xyz = _wrap(...)` in `etl/derive.py` and wire into `derive_all()`.
5. `python -m db.init_db`. Scheduler picks up the new folder automatically.

---

## File-truncation pattern — VERIFY AFTER EVERY LARGE WRITE

Large `Edit`/`Write` operations occasionally land **truncated** on the Windows disk even though the harness reports success. The Read tool shows the harness-cached intended content; `bash cat` shows the truncated state. Symptoms: parse errors at the very end of a file ("unterminated string", "expected indented block", "Unexpected end of input"). Always cuts off mid-line / mid-statement.

Files repeatedly affected: `api/routers/{rules,trace,pages,monitor,ref}.py`, `etl/scheduler.py`, `etl/derive.py`, `web/{trace,trig,file_monitor,portfolio}.{js,html}`.

**Mandatory verification after any non-trivial Edit/Write:**

```bash
python3 -c "import ast; ast.parse(open('PATH').read())" || echo TRUNCATED   # Python
node --check PATH || echo TRUNCATED                                          # JS
tail -10 PATH                                                                # always
```

Also strip trailing null bytes — the harness sometimes pads with NULs:

```bash
python3 -c "
with open('PATH','rb') as f: d=f.read()
s=d.rstrip(b'\\x00')
if len(s)!=len(d):
    with open('PATH','wb') as f: f.write(s)
    print('stripped',len(d)-len(s))
"
```

If truncated, **don't re-`Edit`** — rewrite the tail via bash heredoc. Smaller, more frequent edits truncate less often than one big rewrite.

---

## Other gotchas

- **Mount staleness for `stat` / `wc` but not `cat`**: bash sandbox directory metadata can lag. Trust `cat` / `tail -c N`.
- **`init_db` swallows `DO` blocks**: if a migration depends on a DO block, also provide a standalone `migrate_X.py` running that block via `session.execute(text(...))`. Template: `migrate_ref_load_files_pk.py`.
- **Composite PKs break inline editing in `/ref`**: `web/ref.js` renders any `is_pk` column read-only. Prefer single-column PK + `UNIQUE` on the secondary tuple when possible.
- **Boolean coercion in /ref API**: UI sends `'true'`/`'false'` strings; `api/routers/ref.py::_coerce_row_types` converts to bool for BOOLEAN columns + empty-string → NULL.
- **`ref.py` has module-level DEBUG prints** that call `discover_data_tables()` at import time — these hit the DB at startup. Don't remove without checking they're not load-bearing for cache warming.
- **`pytest --json-report --json-report-summary` suppresses per-test entries** for the `/test-results` screen; drop `--json-report-summary` to keep detail rows.

---

## Common errors (quick fixes)

- `relation "drv_*" does not exist` → `python -m db.init_db`.
- `password authentication failed for user "postgres"` → fix `PG_PASSWORD` in `.env`.
- Re-run reprocesses already-loaded files → only after `init_db --reset-audit`. Default preserves `meta_file_processed`.
- Loader reports `0 read 0 inserted 0 skipped` → header mismatch; fix `etl/mappings.py` (case-insensitive).
- Workbook edits to tunable refs don't propagate → `python -m etl.refresh_ref`, not `tickers_initial_load`.
- `derive_trig: no atomic rules loaded; skipping` → `ref_trig_atomic_rule` empty; reload workbook with populated Trig tab.
- Scheduler "watched dir missing" → folder not on this machine; create it or update `LoadFiles.xlsx`.

---

## Lookup index

| Need | Look in |
|---|---|
| TL tab column map | `etl/mappings.py::HIST_MAPS['TL']` |
| Vlm projection formula | `etl/derive.py::_derive_ma_impl` (inline `tl` CTE; drv_tl retired 2026-05-20) |
| Outlook → weight mapping | `ref_param` where `sheet='outlook'` |
| Atomic rules feeding a composite | `ref_trig_composite_mapping WHERE composite_rule_code=...` |
| Why a load skipped a row | `meta_etl_run.rows_skipped` |
| Why a derive looks wrong | `meta_derived_run` then `drv_ma` for that symbol/date |
| Last successful load of a file | `meta_file_processed.processed_at` |
| FastAPI endpoints | `api/routers/*.py` |
| Section classifier | `etl/derive.py::_classify_section` + `web/app.js::classifySymbolSection` |
| Cash detection rules | `api/routers/dash.py` (`F_IS_CASH`, `CS_IS_CASH_C` SQL fragments) |
| Actionable / outlook-action logic | `docs/actionable_logic.md` |
| Atomic-input column derivation (JF..NP + QE..QT) | `docs/drv_cat_atomic_input_logic.md` |
| Dashboard single-cell scalars (Dash!$X$Y) | `ref_param sheet='dash'`; helper `etl/derive_cat_atomic_input.py::get_dash_scalar`; seeds in `db/baseline.sql` 2026-05-27 v3 block |
| TOS composite-field decoding (a_bb_streak, a_bb_high_low, a_volume_spike) | `etl/derive_cat_atomic_input.py::compute_intermediates` + `_decode_bb_streak` / `_decode_vs` / `_days_from_frac` |
| Dashboard / snapshot-date logic | `docs/dashboard_logic.md` |
| File Monitor logic | `docs/file_monitor_logic.md` |
| Rules engine logic | `docs/rules_logic.md` |
| Rule groups logic | `docs/rule_groups_logic.md` |
| Performance / feedback-loop logic | `docs/performance_logic.md` |
| Symbol normalization strategy (tos_symbol) | `docs/tos_symbol_normalization.md` |

---

## Recent Migrations (2026-05-29)

- **tos_symbol migration completed**: All `hist_*` and `drv_*` tables now use `tos_symbol` exclusively. Raw `symbol` columns remain in `hist_*` for reference only. Populate functions: `_populate_y_tos_symbol`, `_populate_rr_tos_symbol`, `_populate_ps_tos_symbol`, `_populate_tos_table_tos_symbol`, `_populate_generic_tos_symbol` (handles event_date for etfchg/iichg).
- **RR file loader**: `load_rr()` in `etl/load_raw.py` loads Treasury/Index recommendations from RR tab. Registered in `CUSTOM_HANDLERS['rr']`.
- **hist_ps special case**: Uses `ticker` column instead of `symbol`. Has `tos_symbol` populated via `_populate_ps_tos_symbol()` which maps ticker → tos_symbol via ref_rrt.
- **hist_etfchg / hist_iichg**: Now have `tos_symbol` columns (added via ALTER TABLE in baseline.sql). Populated via `_populate_generic_tos_symbol()` with event_date date column.
- **ETFChange loader**: `load_etfchg()` skips test/dummy rows (symbol in DUMMY, TEST, TEMPLATE) to prevent placeholder data from being loaded.
- **Schema migration pattern**: For adding columns to existing tables, use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in baseline.sql (after CREATE TABLE ... IF NOT EXISTS blocks).
- **replace_for_date atomic fix**: Added `session.flush()` after DELETE to ensure deletion is committed before INSERT. Prevents duplicate key errors when function called multiple times in rapid succession.
- **API: derive-runs endpoint**: Defaults to latest available `as_of_date` (from meta_derived_run.MAX) instead of calendar today. File Monitor derive grid now shows recent runs correctly.
