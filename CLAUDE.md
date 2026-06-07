# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Trading Dashboard — Claude Reference

Index file only. Detail lives in `docs/`. See Lookup index below.

> **Session start (token-efficient init):** This file auto-loads — that is the
> whole context backbone. Do NOT read other docs, scan the tree, or "review the
> project" up front. Read only this `CLAUDE.md`, then ask which screen/feature
> the user is working on and open just the one matching `docs/*_logic.md` from
> the Lookup index. Use `/clear` between unrelated tasks so a fresh session
> reloads only this lean index. (Rules 10–11 enforce this.)

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

**Derive date `D` is the ANCHOR = `MAX(export_date) FROM hist_td` (TOSD).** Only a
TOSD load advances `D`; every other load (intraday TOSL/Y, periodic feeds, positions)
re-derives the current anchor. `snapshot_date` is **informational** — derivation keys off
`export_date`. Daily-EOD sources (TOSL/TOSD/TOSW/Y) match `export_date = D` exactly, max
`sequence` per symbol (no per-symbol carry-forward; a symbol missing from D's TOSD export is
excluded everywhere via `drv_symbols`). Periodic feeds (RR/CALL/ETF/II/SSS/PS) and positions
(CS/F) keep carry-forward `<= D`. Full detail: `docs/derive_date_logic.md`.

```
load lands → D = get_anchor_date()   [MAX(export_date) in hist_td]
  → /api/dash?date=D → SELECT * FROM v_dash(D)
  ← drv_dash WHERE as_of_date=D
  ← drv_ma VIEW (drv_symbols + drv_technicals + drv_fundamentals + drv_outlooks + drv_portfolio)
    ← drv_symbols = symbols in hist_td WHERE export_date=D   (the universe; missing → excluded)
    ← daily-EOD tl/td/tw/y: export_date=D exact, max(sequence) per symbol
    ← periodic rr/call/etf/ii/sss/ps + positions cs/f: latest snapshot ≤ D
    ← drv_quote: latest price (intraday OK on the anchor date), tagged as_of_date=D
  ← hist_* loaded from Excel (ON CONFLICT DO NOTHING)
```

Re-running derive for date D is idempotent. No date is ever silently overwritten.

---

## ETL & rules pipeline

- **Loader**: `etl/scheduler.py` watches 17 source dirs (`ref_load_files`). File events → `etl_load.py::load_one_file` → `mappings.py::HIST_MAPS` or `load_raw.py::CUSTOM_HANDLERS`. Batches 1000 rows; `meta_etl_run` updated live.
- **Derive cascade**: `derive_all(session, D)` order: drv_quote/drv_rr → drv_symbols → drv_technicals/drv_fundamentals/drv_outlooks/drv_portfolio → drv_cat_atomic_input → drv_dash → drv_stks → drv_outlook_action → drv_actionable → drv_trig. All idempotent. `derive_v2.py` overrides v1 for derive_tw/etf/ii/ps/sss.
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
- **Mount staleness (agent sessions) — KNOWN FALSE ALARM, do NOT investigate** — when Claude edits an existing file, the Linux sandbox mirror often freezes on a *stale/truncated* copy of that file for the rest of the session. `wc`/`cat`/`tail`/`dd`/`git diff`/`python ast.parse` run **in the sandbox** will then show the file cut off mid-line. This is cosmetic: the real Windows file is complete and correct (newly-created files mirror fine; only in-session-edited files go stale). **Response:** trust the editor's own Read as ground truth, do NOT chase it or "repair" the file, and do NOT `git commit` from the sandbox (it would stage the truncated mirror) — commit from Windows, or verify there with `python -c "import ast; ast.parse(open(r'PATH').read())"`. (Plain lag where `cat`/`tail -c N` helps is the milder, separate case.)
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
| Rule Flow formula source — MA tab formulas | Read directly from `Tickers YYYY-MM-DD.xlsx` MA sheet; comments in code may be stale. Use `openpyxl data_only=False` on row 2 to get formula strings. ArrayFormula objects have `.text` attribute. |
| Rule Flow Data Flow panel | `GET /api/rule-flow/{sym}/intermediates` → `etl/derive_cat_atomic_input.py::get_symbol_intermediates`. Chain map + labels in `web/rule_flow.js::_CHAIN/_KEY_LABEL`. |
| Rule Flow crossover formulas — Trade(JM) vs Trend(JP) | Trade: `IFS(D>AF AND AF>MIN(EF,J),1, MAX(EF,I)>AF AND AF>D,-1, 0)` — no BZ. Trend: same but `MIN(BZ,EF,J)` / `MAX(BZ,EF,I)` — includes BZ. DMA crossovers: BZ only. |
| Current Price SD Rule (NK) input scale | Python uses `net_chng/AC`; Excel uses `pct_change(%)×D/AC` (100× larger). Thresholds in `ref_trig_atomic_rule` calibrated at Python scale — do not change formula without also updating thresholds. |
| Dashboard / snapshot-date logic | `docs/dashboard_logic.md` |
| Derive date / anchor logic (export_date, TOSD, per-source rules) | `docs/derive_date_logic.md`; `etl/derive.py::get_anchor_date` / `ANCHOR_LOCKED_SOURCES` |
| Default screen date = anchor (capped dates list) | `db/baseline.sql` `v_available_dates`; `api/_helpers.py::_resolve_date`; `/api/actionable/dates` |
| "Data behind market close" warning + date highlight | `/api/anchor-status`; `api/_helpers.py::expected_market_close_date`; `web/warning_badge.js` (`.date-stale`) |
| File Monitor logic | `docs/file_monitor_logic.md` |
| Rules engine logic | `docs/rules_logic.md` |
| Rule groups logic | `docs/rule_groups_logic.md` |
| Rule engine redesign (gate/WATCH, BASE rules, param sets, ML) | `docs/rule_engine_redesign.md` |
| Gate/WATCH firing rule | `etl/derive.py::_derive_stks_impl` (gate/watch partition) |
| Composite member→base map (from Excel) | `docs/composite_member_map.csv` |
| Param-set overlay | `etl/param_sets.py` → consumed by `etl/derive_cat_atomic_input.py::load_trig_rules` |
| ML threshold tuning | `etl/ml_tune_thresholds.py` |
| Param-set management screen | `web/param_sets.*` → `/param-sets`; API `api/routers/rules.py` (`/api/rules/param-sets*`) |
| Composite editor (clone, threshold pre-fill, BASE picker) | `web/composite_edit.*`; API `/api/rules/composite/{id}/clone`, `/api/rules/base-composites` |
| Group-of-groups nesting | `web/groups.html` (`memberOptionsHTML`/`memberTypeFor`) |
| Rule Flow screen logic (live trace, data flow panel, trig_action calc) | `docs/rule_flow_logic.md` |
| Performance / feedback-loop logic | `docs/performance_logic.md` |
| Rule tuning, profiles (param sets), outcomes & scorecard — USE & FIX guide | `docs/rule_tuning_and_outcomes.md` |
| Firing-based outcomes ETL (validate rules vs forward returns) | `etl/compute_firing_outcomes.py` (+ `etl/backfill_derives.py`) → `drv_rule_outcome` |
| Direction-adjusted rule scorecard (which rules predict the right move) | `v_rule_scorecard` (db/baseline.sql); `SELECT * FROM v_rule_scorecard ORDER BY edge_20d DESC` |
| Rule-edge in the UI (badges + Actionable "Rules (edge)" column) | `web/actionable.js` (`firesCellHtml`, `ruleEdgeBadge`), `web/rule_flow.js` (`compEdgeBadge`) ← `/api/rules/scorecard` |
| Personal action track record ("Your actions" panel) | `v_user_action_performance` (db/baseline.sql) → `/api/rules/my-actions` → `web/rule_performance.*` |
| Performance screen (scorecard + Your actions panels) | `web/rule_performance.*`; endpoints `/api/rules/scorecard`, `/api/rules/my-actions`, `/api/rules/performance` |
| Symbol normalization (tos_symbol) | `docs/tos_symbol_normalization.md` |
| tos_symbol population — 4 groups (detail) | `detailed_tos_groups.md` |
| tos_symbol fallback/strategy (Groups 2–4) | `strategy_and_fallback_details.md` |
| Screen overview, data-flow, column lineage | `docs/Screen_and_DataFlow_Reference.md` |
| Flow diagrams (pipeline, derive cascade, rules) | `docs/diagrams/*.svg`, `docs/audit/architecture_flow.md` |
| Unused DB tables/columns audit | `docs/audit/unused_db_report.md` |
| Unused/cruft code files audit | `docs/audit/unused_code_report.md` |
| Macro feed (FRED) — econ data + EOD index levels | `docs/macro_feed_logic.md`; `etl/fetch_macro.py`; `ref_macro_series`/`hist_macro`/`v_macro_latest`; `/api/macro` |
| Cockpit Market-context band (macro tiles + Refresh) | `web/macro_band.js` (loaded by `web/cockpit.html`, `/cockpit`); reads `/api/macro`, `POST /api/macro/refresh` |
| Full command reference + web endpoints + troubleshooting table | `COMMANDS.md` |

---

## Recent Migrations (2026-06-07)

- **Macro feed (FRED) — data layer only (UI deferred).** New `ref_macro_series` (tunable catalog, seeded by `db/seeds_macro.sql`, ~20 series) + append-only `hist_macro` (PK `(series_id, obs_date)`, `ON CONFLICT DO NOTHING`) + `v_macro_latest` view (latest+prior+chg). `etl/fetch_macro.py` pulls from FRED via stdlib `urllib` (no new dependency) — the only **pull** ingest, NOT in `etl/scheduler.py`; run daily after close. `FRED_API_KEY` in `.env` → `settings.fred_api_key`. `GET /api/macro` (`api/routers/macro.py`, registered in `main.py`) returns grouped tiles for the planned cockpit band. Covers econ data AND EOD index levels (`SP500`/`NASDAQCOM`/`DJIA`/`RU2000PR`/`VIXCLS`) — no second API needed for an EOD workflow. Complementary to workbook-sourced `ref_econ_indicator`/`ref_calendar_event`. Apply: add key to `.env` → `python -m db.init_db` → `python -m etl.fetch_macro --full`. Cockpit UI band still TODO. Full design: `docs/macro_feed_logic.md`.
- **Macro fetch throttle + manual refresh.** `etl/fetch_macro.py` is now throttled: skips (no FRED call) if a real run started within a window, logged to new `meta_macro_fetch`. Window tunable via `ref_settings.macro_fetch_min_interval_min` (seeded 360=6h; precedence: `--min-interval`/arg → ref_settings → code default); `--force` overrides. `GET /api/macro` returns a `last_fetch` block; `POST /api/macro/refresh` runs a throttled fetch for the (future) manual Refresh button — reads never call FRED so the screen is 0 requests. Apply: `python -m db.init_db`.
- **Cockpit "Market context" band LIVE.** `web/macro_band.js` (loaded by `web/cockpit.html`, route `/cockpit`) renders a Market-context card above the actions table: grouped macro tiles (Indexes/Rates/Inflation/Jobs/Risk/Dollar&commodities) from `GET /api/macro`, a "Refresh data" button → `POST /api/macro/refresh` (throttled; shows "Up to date" when skipped), plus `as of`/`updated` stamps. Self-contained file — doesn't touch existing cockpit.js logic. Static assets — just hard-refresh; no DB/restart needed.

## Recent Migrations (2026-06-06)

- **Phase 2 base rules LIVE (firing-equivalent).** 8 leaf composites nest `BASE-Bull-Context`/`BASE-Bull-Trend`. Engine fixes that made it score-neutral: nested-composite gating fires only when the child fired (`_derive_stks_impl`), `_derive_trig_impl` now scores nested members (two-pass), `seeds_base_rules.sql` gate members `weight_override=10`, `refactor_base_rules.py` only absorbs members identical in threshold/operator/role. `_derive_trig_impl` also no longer double-evaluates pre-scored atomics (fixed 697 over-fire).
- **Phase 3 profiles LIVE.** `ref_trig_param_set`/`_value` overlay (`etl/param_sets.py`). Profiles: id=1 **Baseline 2026-06-05** (active, frozen current numbers, rollback anchor), id=2 Sigmoid v1 (inactive scaffold), id=3 ml-sweep-20d (inactive, overfit). One active at a time; switch two-step then re-derive. Rollback = activate id=1.
- **Phase 4 outcomes + scorecard.** `etl/backfill_derives.py` (additive historical derive backfill) + `etl/compute_firing_outcomes.py` populate `drv_rule_outcome` from rule firings + forward returns (no `user_action_log`). `v_rule_scorecard` ranks composites by direction-adjusted `edge_20d`. `drv_rule_outcome` PK fixed to `(rule_id, as_of_date, tos_symbol)`; column `symbol`→`tos_symbol`. ML (`ml_tune_thresholds.py`) writes inactive `ml:` profiles. **Caveat: only ~4 months/one regime loaded — diagnostic only; don't activate tuned profiles yet.** Full guide: `docs/rule_tuning_and_outcomes.md`.
- **`rebuild_rules` durability.** Now re-applies `current_volume_rule` neg thresholds (25/50) that a workbook reload would otherwise strip. Keep DB-only rule tweaks in sync there + `baseline.sql`.
- **Rules made usable in the UI.** Performance screen (`/rule-performance`) now shows the direction-adjusted scorecard (`/api/rules/scorecard`) + a "Your actions" panel (`/api/rules/my-actions`). Actionable (`/actionable`) gained a "Rules (edge)" column (fired rules winning-first w/ edge) + edge badges in the row popup; Rule Flow composites show the same badge. `v_rule_performance_window` re-anchored to `MAX(as_of_date)` (was wall-clock `CURRENT_DATE` → blank screen). Full UI map: `docs/rule_tuning_and_outcomes.md` §7.

## Recent Migrations (2026-06-05)

- **Anchor-date derive model**: Derive date `D` is now `MAX(export_date) FROM hist_td` (TOSD), resolved by `etl/derive.py::get_anchor_date`. Only TOSD advances `D`; `etl/etl_load.py` derives the anchor (not the filename date) after every load. `snapshot_date` is informational; derivation keys off `export_date`. Daily-EOD sources (TOSL/TOSD/TOSW/Y, `ANCHOR_LOCKED_SOURCES`) read `export_date = D` exactly with max `sequence` per symbol — no per-symbol carry-forward. `drv_symbols` universe = daily-EOD sources (td/tl/tw/y) at `export_date = D` (exact, no carry-forward) UNION periodic feeds (etf/ii/call/rr) at `snapshot_date <= D` — so a stock missing from today's TOSD/TOSL is excluded, but non-TOSD symbols (e.g. ETFs in etf/ii feeds) still appear. Periodic feeds + positions keep `<= D` carry-forward. **Run Missing Derives** now enumerates TOSD market-close dates (`DISTINCT export_date FROM hist_td`) via `api/routers/monitor.py::_find_missing_derive_dates`. `drv_quote` may use a fresher intraday price on the anchor date (tagged `as_of_date=D`). Missing daily-EOD files surface via `warn_missing_eod_sources` → `meta_warning` (dashboard/actionable toolbars). **No schema change** to the derive logic; apply across history with File Monitor → Force Re-derive. Full design: `docs/derive_date_logic.md`.
- **Default screen date = anchor**: `v_available_dates` and `/api/actionable/dates` are capped at `MAX(export_date) FROM hist_td`, so every screen's default (`dates[0]`) and `_resolve_date(None)` resolve to the anchor (stray future-dated derives no longer show). View change → **`python -m db.init_db`** to apply.
- **"Data behind market close" warning + date highlight**: `GET /api/anchor-status` (request-time) compares the anchor to `api/_helpers.py::expected_market_close_date()` (most recent completed US trading session — weekday not in `ref_holiday` — past `ref_settings.market_close_cutoff` default `16:30` in `market_timezone` default `America/New_York`; Windows needs `tzdata`). `web/warning_badge.js` polls it and, when stale, raises an amber toolbar warning + adds `.date-stale` to `#datePicker`. Displayed date stays the actual anchor.

## Recent Migrations (2026-06-03)

- **Composite mapping surrogate PK**: `ref_trig_composite_mapping` PK was `(composite_rule_code, atomic_rule_id)`, which made `atomic_rule_id` implicitly NOT NULL and blocked `data` / nested-`composite` members. Replaced with surrogate `mapping_id BIGSERIAL` PK + NULL-permissive `UNIQUE (composite_rule_code, atomic_rule_id)` (index `uq_ctm_code_atomic`). The loader upsert now passes `conflict_cols=` to `etl/db.py::insert_skip_duplicates` (new param) to target that unique. Apply via `python -m db.init_db`. **Required for Phase 2 nesting / clone / data members.**
- **Gate/WATCH composite firing**: `ref_trig_composite_mapping.member_role` (`gate`|`watch`) + `evidence_cutoff`. Fire = all gates pass AND watch evidence ≥ cutoff (NULL = watch never blocks). Pure-watch falls back to all-hit. Default `gate` = zero change. `etl/derive.py` + `api/routers/trace.py` apply it; `web/composite_edit.*` + `web/rule_flow.*` show roles. Backfill: `db/migrate_member_watch_roles.sql` (weight_override=1 → watch). Full design: `docs/rule_engine_redesign.md`.
- **Per-member thresholds loaded**: `etl/load_raw.py` now stores the Trig threshold cell into `data_brkeout_from` (was discarded → members degraded to "value≠0"). Workbook reload refreshes weight/threshold/role via ON CONFLICT DO UPDATE.
- **BASE-* sub-composites (Phase 2)**: `db/seeds_base_rules.sql` (5 reusable bases); exempt from loader pruning. Refactor leaves via `etl/refactor_base_rules.py` (dry-run default).
- **Param sets (Phase 3)**: `ref_trig_param_set` + `ref_trig_param_value` overlay tunable thresholds/weights/k/x0 at scoring time via `etl/param_sets.py` (consumed by `load_trig_rules`). `db/migrate_sigmoid_learnable.sql` converts monotonic rules jump→sigmoid (+ rollback).
- **ML tuning (Phase 4)**: `etl/ml_tune_thresholds.py` fits thresholds from `drv_cat_atomic_input` + `drv_rule_outcome`, writes an inactive param set to backtest then activate.

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
