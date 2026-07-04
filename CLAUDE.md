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
          hedgeye/  Hedgeye email ingest sub-package: source.py (Gmail IMAP) → classify.py → parsers.py → dispatch.py → emit.py. Feeds: hist_rta, hist_call, hist_call_top5, hist_etfchg, hist_rr, hist_sss_change, hist_msr, hist_hedgeye_stance, note_repo.
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
- `hist_*` — raw history, append-only (y, tl, td, tw, to, rr, call, call_top5, etf, etfchg, ii, iichg, sss, sss_change, ps, f, cs, cst, ft, rta, msr, hedgeye_stance, quote_daily, macro). PK `(snapshot_date, symbol[, sequence|account])`.
- `drv_*` — derived, idempotent (`DELETE WHERE as_of_date=D` → INSERT). Key tables:
  - **`drv_ma`** — **compatibility VIEW** (not a table as of 2026-05-31). JOINs the 5 component tables. Never INSERT into it.
  - `drv_symbols`, `drv_technicals`, `drv_fundamentals`, `drv_outlooks`, `drv_portfolio` — 5 component tables written by derive_all (replaced drv_ma).
  - `drv_dash`, `drv_stks`, `drv_dash_summary`, `drv_trig`, `drv_rule_outcome`, `drv_quote`, `drv_rr`, `drv_cat_atomic_input`, `drv_realized_gain`, `drv_cs_realized_gain`.
  - `drv_actionable` — final recommendation per symbol. Columns: `consolidated_action`, `trig_action` (SA/STM/SS/BM vocab), `triggered_group_ids` JSONB, `source_actions` JSONB.
- `meta_*` — operational (etl_run, file_processed, cleanup_policy, derived_run, scheduler_log, hedgeye_msg [raw Hedgeye emails before parsing], warning, macro_fetch).

Also: `user_action_log`, `ref_settings`, `ext_links` (external provider URLs keyed by `panel_key` — e.g. `early_look`, `call`, `etf_pro`; served by `GET /api/ext-links`), `v_rule_performance` view.

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
9. **Plan first → one-line description → wait for approval.** Excludes typo fixes and approved renames. Hard rule.
10. **`CLAUDE.md` is an index, not a detail doc.** Detail lives in `docs/<topic>_logic.md`. If tempted to write more than one line of detail here, stop — create or update the relevant `docs/` file and add one Lookup row instead.
11. **Read `docs/` files only when needed.** On session start, read only `CLAUDE.md`. Then ask the user which screen(s) or feature(s) they plan to work on. Read only the relevant `docs/` files based on that answer. Do NOT pre-emptively read all detail docs.
12. **Responses**: short Summary (only what user must act on) → Details → Notes (only if actionable) → Questions (only if real). No padding. Hard rule.
13. **Commit all code changes to git** with clear messages.
14. **Push back on wasteful requests.** State concern + better option under `### Worth reconsidering`. Use sparingly. Hard rule.
15. **tos_symbol in all drv_*.** Never use raw `symbol` in derive functions. `symbol` column exists in `hist_*` only. See `docs/tos_symbol_normalization.md`.
16. **tos_symbol fallback files at root** — `detailed_tos_groups.md` and `strategy_and_fallback_details.md` live at project root (not `docs/`); move them when convenient.
17. **Cowork defaults to hand-off, not editing.** By default in Cowork (desktop) sessions Claude is the orchestrator/architect: it investigates, plans, and authors task specs rather than editing code. Implementation normally goes to the VS Code **developer agent** via `agent-tasks/TASK_<n>.md`, with `AGENT_WORK.md` as the developer's master pointer (the file `/dev-cycle` reads) and `AGENT_TASK.md` as the tester's verification pointer; the developer logs `DEV_HANDOFF.md` (ends `ALL_DONE`) and hands verification to the **tester agent**, which writes `AGENT_RESULT_<n>.md` (ends `DONE`/`FAILED`). **Exception: if the user explicitly asks Claude to write or fix code, do it directly.** DB queries always go to the developer regardless — Cowork has no DB access (sandbox can't reach local Postgres). No agent commits/pushes — user commits from Windows (overrides #13 in this flow). Full workflow + file conventions: `docs/agent_handoff_workflow.md`.
18. **Test-debt policy.** Task-acceptance tests go in `tests/acceptance/` marked `@pytest.mark.acceptance`, excluded from the default run (`pytest.ini` `addopts = -m "not acceptance"`) and deletable after the task's commit. Anything kept in `tests/` asserts behavior or schema only — never palette hexes, inline styles, file tails, handoff content, or point-in-time DB values. See `docs/audit/test_debt_review.md` §2.

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
run_scheduler.bat                              :: keep-alive scheduler loop (auto-restarts on crash, 2 s delay)
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
| Section classifier | `etl/derive.py::_classify_section` (JS classifySymbolSection no longer exists) |
| Cash detection rules | `db/baseline.sql` `is_cash()` DB function (TASK_54); `api/routers/dash.py` for query usage |
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
| Unified ingest log (file + email) | `v_ingest_log` (db/baseline.sql); API `/api/ingest-log` |
| Feed catalog (one feed, file + email recognizers) | `v_feed_catalog` + `feed_code` on ref_load_files/ref_hedgeye_email_type (db/baseline.sql; seed db/seeds_feed_code.sql) |
| Hedgeye action panel (Top-5/alerts/RR flips/stance/ETF/SSS/positions/Early Look/MSR) on Actionable | `api/routers/hedgeye.py` (`/api/actionable/hedgeye`); `web/hedgeye_panel.js`. Panel sits above `.act-toolbar` in actionable.html. `effective_date = MAX(anchor, latest across hist_rta/hist_call_top5/hist_etfchg)` so intraday feeds surface immediately. |
| Hedgeye email pipeline | `etl/hedgeye/`: `source.py` (Gmail IMAP) → `classify.py` (email type) → `parsers.py` (extract rows) → `dispatch.py` (write feed file + ledger) → `emit.py` (push to DB). Config in `.env` + `etl/hedgeye/config.py`. Design: `docs/hedgeye_feeds_design.md`, `docs/hedgeye_loading_dataflow.md`. |
| External provider links per panel section | `ext_links` table (`panel_key`, `label`, `url`). `GET /api/ext-links` returns all; `PUT /api/ext-links/{panel_key}` updates. Panel headers show ↗ link when url is set. |
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
| Actionable Econ panel (FRED macro tiles) | `web/market_bar.js` (`#econPanel`, `[data-econ-toggle]` button); reads `/api/macro`; `/cockpit` 301-redirects to `/actionable` (macro_band.js/cockpit.html deleted, TASK_109) |
| Actionable bulk action + lazy MACRO detail + settings | `POST /api/actionable/bulk-action`, `GET /api/actionable/macro-detail`, `GET /api/actionable/settings` (api/routers/dash.py, TASK_106) |
| Quad regime → MACRO overlay (design, diagrams, MacroNet, band, precedence, single MACRO column) | `docs/quad_design.md` (+ `docs/diagrams/quad_*.svg`); spec `agent-tasks/TASK_74_quad_macro_overlay.md` |
| Full command reference + web endpoints + troubleshooting table | `COMMANDS.md` |
| Schema + behaviour migration history (all dated changes) | `docs/migrations.md` |
| Agent handoff workflow (Cowork → developer → tester; file naming, markers, no-commit) | `docs/agent_handoff_workflow.md` |
| Bull-calc analysis (two stacks, duplications, money-first improvements P1–P5) | `docs/audit/bull_calc_analysis.md` |
| Bull-calc rollout / how to enable + revert (TASK 65–69) — read after a break | `docs/bull_rollout_runbook.md` |
| Bull-calc logic + data-flow diagrams (feeds→stacks→Final Call; decision tree) | `docs/diagrams/bull_calc_data_flow.svg`, `docs/diagrams/bull_calc_decision_logic.svg` |

