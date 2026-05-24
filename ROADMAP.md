# Trading Dashboard — Roadmap & Screen Status

Forward-looking companion to `CLAUDE.md`. Inventory of every screen with what it does today and what's missing, then a phased plan to take the project from "running locally" to "trustworthy daily decision tool", plus improvement proposals.

Last updated: 2026-05-17.

---

## 1. Screen inventory

Twelve top-nav screens, plus two non-nav pages (composite editor, trig analyzer). Status is a quick read: 🟢 working / 🟡 partial / 🔴 broken-or-stub.

### 1.1 Dashboard `/` — 🟢 main view
Sectioned ticker grid (volatility / index / sector / single names), Quad regime line, econ-indicators side table, upcoming calendar events. KPI banner at top. Date picker drives every query.
**Gap:** sparse visual cues for what's new vs. day-over-day; no inline outlook-change badges; KPI banner is text-only (no sparklines).

### 1.2 Cockpit `/cockpit` — 🟡 action review
Drawer-based per-symbol view with triggered rules and a "Log action" button that writes to `user_action_log`.
**Gap:** the logged `action_code` is `'ACTED'/'SKIP'` strings, but `compute_outcomes._determine_hit` only scores `SA/STM/SS/BM/HOLD/SKIP` — so every cockpit-logged row currently records `hit=False`. Also `POST /api/actions` writes Python `repr()` into the JSONB column instead of JSON. **Fix before relying on the feedback loop.**

### 1.3 Actionable `/actionable` — 🟢 new
Filterable list of stocks with a recommended action (REMOVE / REDUCE / INCREASE / ADD / HOLD), with category + held-only + show-acted filters. Backed by `drv_actionable` + `derive_actionable.py`.
**Gap:** no bulk "act on selected" workflow; suppression rules are ad-hoc; no link from a row back to the contributing rules.

### 1.4 Portfolio `/portfolio` — 🟢 new
Consolidated/per-account positions with KPI strip, source/account/limit-status filters, search, sortable grid. Click-through opens a modal with shares/value/gain, YTD/MTD, performance chart, account breakdown, price history.
**Gap:** "limit status" depends on `ref_asset_allocation`; allocation gaps and alerts aren't surfaced on the main dashboard. No options-position view yet (only stocks).

### 1.5 Rules `/rules` — 🔴 read-only UI vs. write API
Atomic + composite rules manager (search, edit, deprecate).
**Gap:** UI calls `POST/PUT/DELETE /api/rules/atomic` (and composite equivalents), but only the `GET` endpoints exist in `api/routers/rules.py`. **Edits and deprecations fail at runtime.** Add the missing handlers (with optimistic concurrency on `updated_at`) and a dry-run preview.

### 1.6 Rule Groups `/groups` — 🟡 new
Named bundles of atomic/composite rules with set operators (AND/OR), test-runner box, hierarchy display.
**Gap:** groups don't yet feed any downstream scoring; they're standalone collections. Wiring them into `drv_stks` or `drv_actionable` is the obvious next step.

### 1.7 Performance `/rule-performance` — 🟡 sparse data
Hit-rate table from `v_rule_performance` (rolling 180d).
**Gap:** denominator is small because outcomes computation is incomplete (see Cockpit gap above). Also no per-category breakdown, no time-window selector, no significance test.

### 1.8 Trace `/trace` — 🟡 new
Per-symbol diagnostic: KPI strip + composite rules grid + raw atomic results, with a symbol input for switching.
**Gap:** doesn't yet show outlook-change diff vs. previous date (the explicit project goal); no link back to the source `hist_*` row.

### 1.9 Explore `/explore` — 🟢 generic browser
Pick any non-reference table, pick a date, see paginated rows with keyword highlighting. Useful for debugging.
**Gap:** read-only; can't easily export selected rows; no column filter besides date.

### 1.10 File Monitor `/file-monitor` — 🟢 ops
Live view of ETL schedule, last load per source, derive status. Viewport-locked layout (no page scroll).
**Gap:** no manual "re-derive date" button surfaced here; no inline error detail when a load fails.

### 1.11 Ref Data `/ref` — 🟢 maintenance
CRUD for `ref_*` tables: upload Excel sheet, validate headers, inline edit with PK collision (409) prevention, row copy/insert.
**Gap:** no diff view ("what changes if I apply this upload?"); no audit log of who-edited-what.

### 1.12 DB Stats `/dbstats` — 🟢 ops
Counts per table for selected date, missing-symbols list, copy-to-clipboard.
**Gap:** doesn't compare to expected counts (so an empty table looks the same as a successful load); no per-source recency timestamps.

### 1.13 Composite Editor `/composite-edit` — 🟡 not in nav
Standalone editor for a single composite rule (preconditions, atomic members, weights).
**Gap:** not linked from top nav; precondition expression accepts text but the engine never evaluates it (`derive.py` ~line 928 has `# TODO: implement proper precondition_expr evaluation`).

### 1.14 Trig Analyzer `/trig` — 🟡 not in nav
Per-symbol atomic + composite results in long form, useful for rule debugging.
**Gap:** scoring is via legacy `_bucket_weight` (jump only) while `drv_stks` uses `eval_atomic_rule` (jump | linear | sigmoid) — same composite can produce different scores across the two views. Reconcile by routing both through the same evaluator.

---

## 2. What's left to "complete" the project

Three phases. Phase 1 makes today's app trustworthy; Phase 2 turns the rules engine from a calculator into a learning loop; Phase 3 is the polish that justifies daily use.

### Phase 1 — Make the existing surfaces honest (~2 weeks)

1. **Fix Cockpit feedback path.** Switch `POST /api/actions` to `json.dumps` (drop the `repr()`); update `compute_outcomes._determine_hit` to handle `ACTED`/`SKIP`, or have the UI submit the actual action codes (SA/STM/SS/BM). Have `_determine_hit` consult `ref_settings` instead of hard-coded ±0.5% / ±1.0% thresholds.
2. **Wire the Rules write-API.** Implement `POST/PUT/DELETE` for atomic + composite rules in `api/routers/rules.py`, with dry-run preview returning the count of impacted symbols.
3. **Implement composite `precondition_expr`.** The `# TODO` at `etl/derive.py:~928` — start with a safe whitelist evaluator (`sector`, `asset_class`, `is_held`, basic comparison + boolean ops).
4. **Unify the rule scorer.** Route `drv_trig` through `eval_atomic_rule` so `scoring_mode != 'jump'` produces identical results across `drv_trig` and `drv_stks`.
5. **Populate `drv_dash.threshold_low/high/zone_signal`.** Wired into the schema, never filled.
6. **Stop truncating dedup history.** `db/init_db.py` wipes `meta_etl_run`, `meta_file_processed`, `meta_cleanup_history`, `meta_derived_run` on every run — turn that off by default behind a `--reset-meta` flag.
7. **Nightly scheduler integration for `compute_outcomes.py`.** It exists but isn't scheduled; have `etl/scheduler.py` (or a Windows Task Scheduler entry) invoke it nightly with a 5d/20d horizon.

### Phase 2 — Close the outlook + actions loop (~3 weeks)

8. **Outlook-change detection** — the stated project goal. Add `drv_outlook_change(as_of_date, symbol, prev_outlook, curr_outlook, source)` and surface as a Dashboard banner ("12 symbols flipped outlook today") with click-through to a date-range diff view.
9. **Action recommendations driven by rule groups.** Tie `rule_groups` into `drv_actionable` so an action requires a group of rules firing, not a single atomic.
10. **Trace shows outlook diff + rule-attribution.** Per-symbol, "why is this on the action list" — which rules fired, what the previous-period outlook was, what changed in the raw data.
11. **Position-aware suppression.** Use `position_rules.py` (already exists) so "INCREASE" doesn't show for symbols already at allocation limit, "ADD" doesn't show for already-held symbols above the held-threshold, etc.
12. **Outcomes window selector.** Performance page: pick 5d/20d/60d horizon and date range; show hit-rate + median return + n.

### Phase 3 — Daily-driver polish (~2 weeks)

13. **Daily morning briefing.** A landing card on Dashboard: "Yesterday's actions and what happened", "New outlook flips", "Allocation drift > 3%", "Files that didn't load".
14. **Notifications.** Optional: when scheduler finishes loading or a critical rule fires, fire a Windows toast / email (config in `.env`).
15. **Backtest harness.** Replay the rules engine over the last N months on the same historical `hist_*` data; produce a per-rule equity curve. (No live trading; just signals vs. forward returns.)
16. **Health/observability.** Persistent error log surfaced on File Monitor; `meta_*` retention sweep (`DELETE FROM meta_etl_run WHERE started_at < now() - interval '90 days'`); Postgres pg_stat dashboard panel on DB Stats.
17. **Tests.** Smallest viable pytest suite: one round-trip ingest of a tiny fixture workbook, one derive, one rule firing. Currently zero tests.

---

## 3. Improvement proposals (beyond completion)

### 3.1 Data & ETL
- **Move file dedupe out of init_db's truncate path.** Treat `meta_file_processed` as durable; only `reset_db.py` should wipe it.
- **Parquet snapshot** of `drv_ma` per date. Same data, 10× smaller, instant pandas reads — useful for the backtest harness.
- **Single-source outlook table.** Today, "outlook" lives in three places (`drv_call`, `drv_etf`, `drv_ii`). Unify into `drv_outlook(as_of_date, symbol, source, outlook, weight)` so outlook-change detection has one table to diff.

### 3.2 Rules engine
- **Versioned rules.** Adding an `effective_from` / `effective_to` to `ref_trig_atomic_rule` so the backtest knows which rule set was live on date D. Today, edits silently overwrite history.
- **Significance & confidence on hit-rate.** Wilson interval + minimum-n badge; otherwise a 60%-hit rule with n=5 looks identical to 60% with n=200.
- **Rule provenance.** Auto-record `created_by`, `created_at`, `last_edited_at`. Cheap, big debugging payoff.

### 3.3 UX
- **Sticky symbol selector across screens.** Pick AAPL on Dashboard → it carries to Trace, Cockpit, Composite Editor.
- **Saved views.** Filter combinations on Actionable / Portfolio / Explore stored locally and shown as chips.
- **Dark mode + density toggle.** The CSS is already a single tokenized file (`web/styles.css`); a `[data-theme]` toggle is half a day's work.
- **Keyboard navigation.** `/` focuses search, `j/k` moves row selection, `?` opens shortcut help.

### 3.4 Analytics
- **Outlook-change calendar heatmap.** Date × source grid, cell color = number of flips. Single screen tells you the regime story.
- **Per-sector concentration vs. target.** Bar of current vs. `ref_asset_allocation` min/max, with drift % and rebalance suggestions.
- **Rule-fire frequency vs. hit-rate scatter.** Spots overfit rules (high frequency, low hit-rate).

### 3.5 Ops & packaging
- **One-command "start fresh".** A `reset_and_seed.bat` that drops the DB, re-creates it, runs `init_db`, loads the latest workbook, and opens the browser.
- **Single-binary distribution.** `pyinstaller` bundling uvicorn + the app + the web dir as one `.exe`, so it survives `.venv` drift.
- **DB backup hook.** Daily `pg_dump trading > backups/trading_YYYY-MM-DD.dump`; rotate weekly. Recovering from a bad refresh would otherwise be painful.
- **Switch from `init_db` truncate-on-run to a real migrations tool** (Alembic) once the schema stabilizes.

### 3.6 Documentation
- **Inline help on each screen** ("?" icon → 1-paragraph what-this-does + which DB tables it reads).
- **Regenerate `docs/Design_Document.docx` from this code state.** It dates to 2026-05-08 and predates Actionable, Portfolio, Groups, Trace, Composite Editor.

---

## 4. Suggested order of attack

If you can only pick three things to do this week:

1. **Phase 1 #1 + #2** — fix the action-logging round-trip and the rules write-API. Without them, Cockpit and Rules are misleading rather than useful.
2. **Phase 2 #8 — outlook-change detection.** It's the explicit goal in `CLAUDE.md`'s "Current focus" line.
3. **Phase 3 #17 — a minimum test suite.** Ten tests cost a day and make every later change safer.

Everything else is genuinely additive: pick from §3 by what hurts most in your daily use.
