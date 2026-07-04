# Migration History

Append-only log of schema and behaviour changes. Most-recent first.

---

## 2026-07-04

- **Market panel consolidation, frontend (TASK_116).** Hybrid consolidation of the three
  market tapes into one mini-tape + the Actionable side rail (design:
  `docs/market_panel_consolidation_design.md`; backend superset payload was TASK_115).
  `web/market_bar.js`: `#rrTape2`/`#rrTape3` mounts deleted; `#rrTape1` now renders a
  curated `BAR_MINI` list (SPX/VIX/DXY/GC/WTI from `/api/marketbar`; 10Y/HY/BTC from
  `/api/rr-bar` Rates/Credit/Crypto groups) plus a right-aligned as-of time. `/api/marketbar`
  + `/api/rr-bar` calls unchanged server-side; mini-tape trims client-side. `web/macro_areas.js`:
  rail member rows gained a candle (`window.mtTip.candleSvg`, now exposed alongside
  `volRangeBar`) and a solid tape-style %chg chip (honors `member.inverted`); Volatility
  rows color the symbol name by zone (not outlook) and keep the 3-zone `volRangeBar` +
  trailing zone badge; new **Credit** rail section (HYG/LQD); section headers gained
  breadth (↑n/↓n) counts. `web/actionable.js`: side panel now pinned by default (missing
  `actSidePinned` key ⇒ pinned; explicit `'0'` stays unpinned) and auto-unpins below
  1200px viewport width (manual toggle wins for the session). No schema change; no
  server restart needed (frontend-only — static assets hot-reload).

---

## 2026-06-10

- **Cockpit retired (Task 7).** `/cockpit` now returns `301 Redirect → /actionable`. All nav menus updated (removed Cockpit link). `web/macro_band.js` Market-context band moved to `web/actionable.html` as a collapsible card above the toolbar (collapse state persists in `localStorage['macroCardOpen']`). `docs/macro_feed_logic.md` and `CLAUDE.md` lookup table updated.
- **EOD feed status warning (Task 2).** `GET /api/eod-feed-status` checks `hist_tl` for rows on the anchor date. Returns `{missing, date, message}`. `web/actionable.js` calls it on load/date-change/refresh and shows a red blocking banner (`#eodMissingBanner`) with dimmed rows (opacity 0.7) when missing. `/api/healthz/warnings` also surfaces the status.
- **Derive cascade status tracking (Task 3).** `meta_derived_run` gained `cascade_status TEXT` column. `derive_all()` tracks failed steps and writes a `target_table='_cascade'` summary row with `SUCCESS/PARTIAL/FAILED`. `/api/derive-cascade-status` endpoint returns latest cascade status for a date. `/api/healthz/warnings` surfaces PARTIAL/FAILED. `daily_health_check.py` includes derive health in its checks.
- **Intraday price tag in drv_quote (Task 4).** `drv_quote` gained columns `pct_brr`, `zone_signal` (Y/W/N), `dist_to_trend`, `dist_to_trade`, `is_intraday`. Actionable screen shows a blue "IDY" badge when `quote_is_intraday=true`. Apply: `python -m db.init_db` then re-derive.
- **Backfill pipeline unified (Task 5).** `etl/backfill_full.py` combines `backfill_derives.py` + `compute_firing_outcomes.py` into one command: inventory, derive missing dates, compute outcomes. Usage: `python -m etl.backfill_full [--inventory] [--limit N] [--skip-outcomes] [--from DATE] [--to DATE]`.
- **ML holdout validation (Task 6).** `ml_tune_thresholds.py` now does a chronological 70/30 train/holdout split, evaluates edge on both halves, and refuses to save (warns) if holdout edge <= 0 or < half of train edge (overfit guard, bypassable with `--no-holdout-gate`). Param set rows now store `train_edge`, `holdout_edge`, `holdout_n`, `validated=TRUE`. Legacy rows default to `validated=FALSE` (shown as "unvalidated" tag in the UI). Param Sets screen shows Train Edge and Holdout Edge columns side-by-side. Apply: `python -m db.init_db`.
- **Stop-level in drv_actionable (Task 8).** `drv_actionable` gained `stop_level NUMERIC`. Computed as `MAX(trade_line, price*(1-stop_pct))` using `ref_settings.stop_mode`/`stop_pct`. Shown below AMT$ in Actionable rows. `ref_settings` seeded with `stop_mode='trade_line_or_pct'` and `stop_pct='0.08'`. Apply: `python -m db.init_db` then re-derive.

---

## 2026-06-07

- **Macro feed (FRED) — data layer only (UI deferred).** New `ref_macro_series` (tunable catalog, seeded by `db/seeds_macro.sql`, ~20 series) + append-only `hist_macro` (PK `(series_id, obs_date)`, `ON CONFLICT DO NOTHING`) + `v_macro_latest` view (latest+prior+chg). `etl/fetch_macro.py` pulls from FRED via stdlib `urllib` (no new dependency) — the only **pull** ingest, NOT in `etl/scheduler.py`; run daily after close. `FRED_API_KEY` in `.env` → `settings.fred_api_key`. `GET /api/macro` (`api/routers/macro.py`, registered in `main.py`) returns grouped tiles for the planned cockpit band. Covers econ data AND EOD index levels (`SP500`/`NASDAQCOM`/`DJIA`/`RU2000PR`/`VIXCLS`) — no second API needed for an EOD workflow. Complementary to workbook-sourced `ref_econ_indicator`/`ref_calendar_event`. Apply: add key to `.env` → `python -m db.init_db` → `python -m etl.fetch_macro --full`. Full design: `docs/macro_feed_logic.md`.
- **Macro fetch throttle + manual refresh.** `etl/fetch_macro.py` is now throttled: skips (no FRED call) if a real run started within a window, logged to new `meta_macro_fetch`. Window tunable via `ref_settings.macro_fetch_min_interval_min` (seeded 360=6h; precedence: `--min-interval`/arg → ref_settings → code default); `--force` overrides. `GET /api/macro` returns a `last_fetch` block; `POST /api/macro/refresh` runs a throttled fetch for the (future) manual Refresh button — reads never call FRED so the screen is 0 requests. Apply: `python -m db.init_db`.
- **Cockpit "Market context" band LIVE.** `web/macro_band.js` (loaded by `web/cockpit.html`, route `/cockpit`) renders a Market-context card above the actions table: grouped macro tiles (Indexes/Rates/Inflation/Jobs/Risk/Dollar&commodities) from `GET /api/macro`, a "Refresh data" button → `POST /api/macro/refresh` (throttled; shows "Up to date" when skipped), plus `as of`/`updated` stamps. Self-contained file — doesn't touch existing cockpit.js logic. Static assets — just hard-refresh; no DB/restart needed.

---

## 2026-06-06

- **Phase 2 base rules LIVE (firing-equivalent).** 8 leaf composites nest `BASE-Bull-Context`/`BASE-Bull-Trend`. Engine fixes that made it score-neutral: nested-composite gating fires only when the child fired (`_derive_stks_impl`), `_derive_trig_impl` now scores nested members (two-pass), `seeds_base_rules.sql` gate members `weight_override=10`, `refactor_base_rules.py` only absorbs members identical in threshold/operator/role. `_derive_trig_impl` also no longer double-evaluates pre-scored atomics (fixed 697 over-fire).
- **Phase 3 profiles LIVE.** `ref_trig_param_set`/`_value` overlay (`etl/param_sets.py`). Profiles: id=1 **Baseline 2026-06-05** (active, frozen current numbers, rollback anchor), id=2 Sigmoid v1 (inactive scaffold), id=3 ml-sweep-20d (inactive, overfit). One active at a time; switch two-step then re-derive. Rollback = activate id=1.
- **Phase 4 outcomes + scorecard.** `etl/backfill_derives.py` (additive historical derive backfill) + `etl/compute_firing_outcomes.py` populate `drv_rule_outcome` from rule firings + forward returns (no `user_action_log`). `v_rule_scorecard` ranks composites by direction-adjusted `edge_20d`. `drv_rule_outcome` PK fixed to `(rule_id, as_of_date, tos_symbol)`; column `symbol`→`tos_symbol`. ML (`ml_tune_thresholds.py`) writes inactive `ml:` profiles. **Caveat: only ~4 months/one regime loaded — diagnostic only; don't activate tuned profiles yet.** Full guide: `docs/rule_tuning_and_outcomes.md`.
- **`rebuild_rules` durability.** Now re-applies `current_volume_rule` neg thresholds (25/50) that a workbook reload would otherwise strip. Keep DB-only rule tweaks in sync there + `baseline.sql`.
- **Rules made usable in the UI.** Performance screen (`/rule-performance`) now shows the direction-adjusted scorecard (`/api/rules/scorecard`) + a "Your actions" panel (`/api/rules/my-actions`). Actionable (`/actionable`) gained a "Rules (edge)" column (fired rules winning-first w/ edge) + edge badges in the row popup; Rule Flow composites show the same badge. `v_rule_performance_window` re-anchored to `MAX(as_of_date)` (was wall-clock `CURRENT_DATE` → blank screen). Full UI map: `docs/rule_tuning_and_outcomes.md` §7.

---

## 2026-06-05

- **Anchor-date derive model**: Derive date `D` is now `MAX(export_date) FROM hist_td` (TOSD), resolved by `etl/derive.py::get_anchor_date`. Only TOSD advances `D`; `etl/etl_load.py` derives the anchor (not the filename date) after every load. `snapshot_date` is informational; derivation keys off `export_date`. Daily-EOD sources (TOSL/TOSD/TOSW/Y, `ANCHOR_LOCKED_SOURCES`) read `export_date = D` exactly with max `sequence` per symbol — no per-symbol carry-forward. `drv_symbols` universe = daily-EOD sources (td/tl/tw/y) at `export_date = D` (exact, no carry-forward) UNION periodic feeds (etf/ii/call/rr) at `snapshot_date <= D` — so a stock missing from today's TOSD/TOSL is excluded, but non-TOSD symbols (e.g. ETFs in etf/ii feeds) still appear. Periodic feeds + positions keep `<= D` carry-forward. **Run Missing Derives** now enumerates TOSD market-close dates (`DISTINCT export_date FROM hist_td`) via `api/routers/monitor.py::_find_missing_derive_dates`. `drv_quote` may use a fresher intraday price on the anchor date (tagged `as_of_date=D`). Missing daily-EOD files surface via `warn_missing_eod_sources` → `meta_warning` (dashboard/actionable toolbars). **No schema change** to the derive logic; apply across history with File Monitor → Force Re-derive. Full design: `docs/derive_date_logic.md`.
- **Default screen date = anchor**: `v_available_dates` and `/api/actionable/dates` are capped at `MAX(export_date) FROM hist_td`, so every screen's default (`dates[0]`) and `_resolve_date(None)` resolve to the anchor (stray future-dated derives no longer show). View change → **`python -m db.init_db`** to apply.
- **"Data behind market close" warning + date highlight**: `GET /api/anchor-status` (request-time) compares the anchor to `api/_helpers.py::expected_market_close_date()` (most recent completed US trading session — weekday not in `ref_holiday` — past `ref_settings.market_close_cutoff` default `16:30` in `market_timezone` default `America/New_York`; Windows needs `tzdata`). `web/warning_badge.js` polls it and, when stale, raises an amber toolbar warning + adds `.date-stale` to `#datePicker`. Displayed date stays the actual anchor.

---

## 2026-06-03

- **Composite mapping surrogate PK**: `ref_trig_composite_mapping` PK was `(composite_rule_code, atomic_rule_id)`, which made `atomic_rule_id` implicitly NOT NULL and blocked `data` / nested-`composite` members. Replaced with surrogate `mapping_id BIGSERIAL` PK + NULL-permissive `UNIQUE (composite_rule_code, atomic_rule_id)` (index `uq_ctm_code_atomic`). The loader upsert now passes `conflict_cols=` to `etl/db.py::insert_skip_duplicates` (new param) to target that unique. Apply via `python -m db.init_db`. **Required for Phase 2 nesting / clone / data members.**
- **Gate/WATCH composite firing**: `ref_trig_composite_mapping.member_role` (`gate`|`watch`) + `evidence_cutoff`. Fire = all gates pass AND watch evidence ≥ cutoff (NULL = watch never blocks). Pure-watch falls back to all-hit. Default `gate` = zero change. `etl/derive.py` + `api/routers/trace.py` apply it; `web/composite_edit.*` + `web/rule_flow.*` show roles. Backfill: `db/migrate_member_watch_roles.sql` (weight_override=1 → watch). Full design: `docs/rule_engine_redesign.md`.
- **Per-member thresholds loaded**: `etl/load_raw.py` now stores the Trig threshold cell into `data_brkeout_from` (was discarded → members degraded to "value≠0"). Workbook reload refreshes weight/threshold/role via ON CONFLICT DO UPDATE.
- **BASE-* sub-composites (Phase 2)**: `db/seeds_base_rules.sql` (5 reusable bases); exempt from loader pruning. Refactor leaves via `etl/refactor_base_rules.py` (dry-run default).
- **Param sets (Phase 3)**: `ref_trig_param_set` + `ref_trig_param_value` overlay tunable thresholds/weights/k/x0 at scoring time via `etl/param_sets.py` (consumed by `load_trig_rules`). `db/migrate_sigmoid_learnable.sql` converts monotonic rules jump→sigmoid (+ rollback).
- **ML tuning (Phase 4)**: `etl/ml_tune_thresholds.py` fits thresholds from `drv_cat_atomic_input` + `drv_rule_outcome`, writes an inactive param set to backtest then activate.

---

## 2026-05-31

- **drv_ma → VIEW**: Now a JOIN VIEW over `drv_symbols`, `drv_technicals`, `drv_fundamentals`, `drv_outlooks`, `drv_portfolio`. Never INSERT into it. `python -m db.init_db` applies the migration on existing DBs.
- **derive_all cascade**: `derive_ma` removed; 5 component derives run in its place (after drv_quote/drv_rr, before drv_cat_atomic_input).
- **trig_action on drv_actionable**: Third action column (SA/STM/SS/BM). Computed from fired rule groups via `ref_param_lookup` buysell scores.
- **git lock gotcha**: `.git/index.lock` / `.git/HEAD.lock` may stick after agent commits on Windows-mounted repos. Delete from Explorer before next git op.

---

## 2026-05-29

- **tos_symbol**: All `drv_*` use `tos_symbol` exclusively. `symbol` kept in `hist_*` only.
- **RR loader**: `load_rr()` in `load_raw.py`, registered in `CUSTOM_HANDLERS['rr']`.
- **hist_ps**: Uses `ticker` column; mapped to `tos_symbol` via `_populate_ps_tos_symbol()` through `ref_rrt`.
- **Schema migration pattern**: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `baseline.sql`.
