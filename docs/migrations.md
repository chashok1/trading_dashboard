# Migration History

Append-only log of schema and behaviour changes. Most-recent first.

---

## 2026-09-21

- **Market Read grid + macro rail panels moved to the top of the middle
  column.** Both (`#quadRotationPanel` then `#macroRailsWrap`) moved from
  below the graphs panel/above Hedgeye (their original slot) to above the
  accounts filter bar — user: "move them to the top above the filter bar."
  Their relative order to each other is unchanged (grid first, then the
  rail panels). Removed an orphaned 2026-08-24 historical comment that had
  documented the rail panels' old position and no longer applied. Also:
  theme grid split into 2 columns (Macro + Commodities & real assets on the
  left, Equity factors + International on the right,
  `web/market_read.js::_themeGridColHtml`); all `.mr-*` font sizes/padding
  trimmed twice over (user: "reduce the sizes so i can see more", then
  "reduce the font by 1 point and size accordingly"); "Lists say" and
  "Agree" column headers shortened to "Lists"/"Ag".

- **Market Read theme grid: CALL column dropped.** User: "it doesn't have
  any data" — confirmed, not a rendering bug: `ref_symbol_theme`'s ~80
  hand-curated symbols were drawn from the four original headline lists
  (RR/ETF/PS/SSS), and CALL's much broader daily list barely overlaps that
  set, so its per-theme vote was empty on nearly every row. Removed the
  `<th>`/`<td>` from `web/market_read.js` (colspan 15→14) and the
  now-unused `.mr-muted-cell` CSS rule. Backend (`etl/derive_market_read.py`,
  `drv_theme_stance.call`) untouched — display-only change.

- **Market Read's 9 macro rail panels reverted to always-visible.** TASK_145
  (below) shipped Volatility/Rates/Credit/Major Markets/USD/Country ETFs
  collapsed by default behind `#macroRailsWrap`, revealed only by clicking a
  Market Read theme row. User noticed the panels had disappeared ("What
  happened to all my panels in the middle column?") — reverted to always
  visible, same as pre-TASK_145. `web/market_read.js::_mrExpandRail` keeps
  the scroll-to-and-highlight behavior on a theme-row click, it just no
  longer needs a show/hide step first. Follow-up: TASK_145 had also pulled
  the Sectors panel out of the rail row into its own standalone
  always-visible band (the reason no longer applied once the row itself
  stopped being collapsible) — moved back into its original column-2 slot,
  right after Major Markets, per "move the sectors back into its place as
  before." Same ids throughout (`#macroSectorEtfsBand`/`#macroRailSectorEtfs`),
  so no script changes needed either time. Second follow-up: the whole
  `#macroRailsWrap` block moved from *before* the Market Read grid
  (`#quadRotationPanel`) to *after* it — summary first, detail below (a
  raw data panel shouldn't precede its own synthesis), which also matches
  the direction `_mrExpandRail`'s scroll-to-and-highlight already goes
  (down into the panels, not up). Pure DOM reorder, no id/script changes.
  Docs: `docs/market_state_factor_sss_design.md` Addendum G.

- **Yahoo-fetch: auto-refresh when stale + last-fetch-time label.** On
  Actionable/Portfolio, the main-toolbar quote-refresh icon now
  auto-triggers once (no retry) if the newest quote is >30 min stale and the
  tab is visible — spins while in flight, shows a persistent `!` on
  failure/skip until a real fresh quote lands. Guaranteed no more than one
  auto-triggered call per 30 min **server-side** (`ref_settings.
  yahoo_auto_trigger_last_at`, `etl/yahoo_fetch.py::auto_trigger_on_cooldown`
  / `mark_auto_trigger_now`), not just client-side, so it holds across every
  browser tab and survives API `--reload-dir api` restarts. Manual clicks
  are unaffected by the cooldown. A small last-fetch-time label (12-hour
  format) now shows under the icon on those two pages. `web/market_bar.js`,
  `api/routers/dash.py` (`/api/yahoo-fetch/quotes-now?auto=1`).

- **Market Read (TASK_143/144/145/146/147)** — display + measurement layer
  reading the four Hedgeye lists (RR/ETF/PS/SSS) + CALL over time, mapped to
  22 hand-curated themes. Design: `docs/market_state_factor_sss_design.md`
  (Addendum A-H). Nothing here touches `derive_actionable.py`, `ref_trig_*`,
  `SOURCE_ORDER`, or `ref_settings` decision switches.
  - New tables (`db/baseline.sql`): `ref_symbol_theme` (seeded ~80 rows,
    `db/seeds_symbol_theme.sql`), `drv_source_breadth`, `drv_theme_stance`,
    `drv_sss_breadth`. All idempotent per `as_of_date`, freshness-contract
    rows added. `etl/derive_market_read.py` (source breadth + theme votes,
    reuses `api/_helpers.py::compute_quad_monthly_stance` — same monthly-
    weighted quad algorithm `GET /api/quad/band-factors` uses, factored out
    so "the quad" is never hard-coded); `etl/derive_sss_breadth.py` (SSS
    sector rows+books, `_normalize_sss_sector` fuzzy-matches the raw
    `hist_sss.sector` text — confirmed NOT clean, ~18% of rows are OCR/
    header-leak noise, see the module docstring). Both wired into
    `derive_all()` after `drv_category_perf`, non-critical.
  - New endpoints (`api/routers/cockpit.py`): `GET /api/market-read`,
    `GET /api/market-read/sectors`.
  - New UI: `web/market_read.js` (replaces the retired `web/
    quad_rotation_panel.js` in the same `#quadRotationPanel` slot, middle
    column of `/`) — breadth strip + theme grid + sector cards (into
    `#macroRailSectorEtfs`, pulled out of the collapsible `#macroRailsWrap`
    since Sector cards are an always-visible Market Read band, not a
    drill-down rail) + headline sentence appended into `#regimeLineBand`.
    `web/macro_areas.js`'s dead `renderLegacyCard`/`injectLegacyCard` (never
    mounted) removed. New CSS tokens `--mr-bull/--mr-bear/--mr-neu`
    (deuteranopia-safe pair, Addendum E4) in `web/styles.css`.
  - Risk Dial: 6 new `category='positioning'`/`'self'` gauges in
    `ref_risk_gauge`, shipped `is_active=FALSE` (predicates in
    `etl/derive_risk_dial.py`; thresholds in `ref_settings` `rd_*`).
    Freshness CAP (not a gauge): `GET /api/cockpit/risk-dial` returns
    `stale_as_of` when the positioning tables breach their freshness
    contract; `web/app.js` suffixes the risk-dial label, the number itself
    never moves for staleness. `v_risk_gauge_scorecard` (report-only).
  - Validation: `v_theme_stance_scorecard`, `v_sss_sector_scorecard`,
    `v_source_breadth_scorecard` + CALL long/short `side` split on
    `v_source_edge_scorecard` (reproduces the July CALL-short-leg finding,
    +6.30% n=75 vs the pooled series' +0.48%). Report:
    `docs/audit/market_read_validation_2026-09.md`. Refresh wired into
    `etl/scheduler.py::run_nightly_outcomes`.
- **SSS/SSSCHG merged into one candidate per symbol, resolved by recency.**
  User: these are not two independently-weighted sources — SSSCHG is the
  daily added/removed-only categorization of the SSS feed, SSS is the same
  feed's full-list reprocess (done weekly). The old fixed `SOURCE_ORDER`
  (SSSCHG=3 always beats SSS=7) meant a held row's winner sort — which
  ignores date entirely, unlike the not-held path — could show a stale
  SSSCHG event over a fresher SSS read. `etl/derive_actionable.py` now
  drops the older of the two (by `source_snapshot_date`/`as_of_date`)
  right after `by_sym` is built, before either reaches `src_actions`/
  `candidates` — so winner selection, the popover's driven-by list, and
  `source_actions` all see a single merged candidate. Every other source's
  `SOURCE_ORDER` position is unaffected. Docs: `docs/actionable_logic.md`.

- **Freshness contracts for computed analytics (TASK_142).** New
  `ref_freshness_contract` (`db/baseline.sql`, seeded by
  `db/seeds_freshness_contract.sql`) lets a computed table declare its own
  staleness contract: `date_column`, `max_lag_days`, `maturity_lag_days`
  (the *expected* structural lag, e.g. drv_rule_outcome can never be closer
  than ~20 trading days to the anchor), and `refreshed_by` (the job that
  keeps it current). `etl/analytics_freshness.py::check_all` evaluates every
  active contract against the anchor; a breach = `(anchor - MAX(date_column))
  > maturity_lag_days + max_lag_days`, and a zero-row table is always a
  breach. Wired into a new seventh `daily_health_check.py` check
  (`_check_stale_analytics`), which writes breaches to `meta_warning`
  (`code='stale_analytics'`) so they ride the existing `/api/warnings`
  toolbar badge. `api/_helpers.py::set_freshness_headers` stamps
  `X-Analytics-As-Of` / `X-Analytics-Stale` response headers (not the JSON
  body, to keep existing list-shaped responses byte-identical) on
  `/api/rules/scorecard` and `/api/rules/factor-scorecard`; Actionable
  reads the scorecard headers to grey the "Rules (edge)" pills and show an
  amber "EDGE DATA `<date>`" header chip (`web/actionable.js`); the
  Performance screen shows an "as of `<date>`" stamp + amber border on the
  scorecard/factor cards (`web/rule_performance.js`); File Monitor gets a
  read-only "Stale analytics" status beside the existing "Stale Derives"
  button (`GET /api/monitor/stale-analytics`). Purely additive — no derive
  logic, rule, or threshold on the decision path changed. Seeded tables:
  `drv_rule_outcome`, `drv_factor_snapshot`, `drv_inferred_action`,
  `ref_vlm_intraday_curve` (all `refreshed_by='scheduler.run_nightly_outcomes'`),
  `drv_market_stat`, `drv_pvv` (`refreshed_by='derive_all'`). Prevention
  process change: `docs/agent_handoff_workflow.md` now requires any task
  adding a computed table feeding a decision screen to answer "what
  schedules it" / "what alerts if it stops" and ship the contract row in
  the same task. Also fixed two unrelated pre-existing bugs found while
  verifying this task's own health check: `_check_hist_gap` left a bad
  `ref_outlook_source.source_table` row (`hist_pk`, no longer a real table)
  poisoning the shared session's transaction for every check that ran after
  it, and `_check_scheduler_idle` read a `meta_file_processed.loaded_at`
  column that no longer exists (renamed to `processed_at`, already fixed in
  `api/routers/health.py`'s copy of this check but not this CLI's).

- **Enforce unproven SELL rules (TASK_141).** New
  `ref_settings.unproven_sell_mode` (`'annotate'` default / `'suppress'`) +
  `drv_actionable.unproven_sell_suppressed`. Reuses the existing
  `low_confidence` condition (TASK_118) — no second classifier. Under
  `'suppress'`, `etl/derive_actionable.py` excludes a `low_confidence` row's
  REMOVE/REDUCE `group_candidates` from the winner contest before the sort
  (falls to the next candidate or HOLD, never a synthesized action);
  `_compute_final_call` (+ JS mirror `finalCall()` in `web/actionable.js`)
  downgrades a sell call that would render `fc_confidence='high'` to
  `'mixed'` when `low_confidence` and the mode is `'suppress'`. Verified
  byte-identical in default `'annotate'` mode (zero
  `consolidated_action`/`final_code`/`fc_confidence`/`suppressed_reason`
  changes on a full anchor re-derive). **Finding:** on the current
  `ref_trig_rule_group` configuration, zero active action-type groups carry
  a REMOVE/REDUCE `action_label`, so `low_confidence` has never once
  co-occurred with a sell-family `consolidated_action` in this table's
  history — `'suppress'` mode produced **zero** suppressions on the test
  derive. Both Part A (candidate filter) and Part B (confidence downgrade)
  verified correct via direct isolated function calls instead. Mode left
  `'annotate'` after verification. Released by TASK_139 (SELL-side HELD
  across two windows). Docs: `docs/actionable_logic.md`
  "Unproven-sell enforcement", `docs/actionable_playbook.md` §5.

- **Source ranking by measured edge (TASK_140).** New `ref_source_precedence`
  (`db/baseline.sql`, seeded by `db/seeds_source_precedence.sql` with today's
  `SOURCE_ORDER` values as `static_rank` — the rollback anchor) +
  `ref_settings.source_order_mode` (`'static'` default / `'measured'`).
  `etl/derive_source_edge.py::recompute_source_precedence` (nightly, via
  `scheduler.run_nightly_outcomes`) ranks the six outlook sources
  (RR/SSS/CALL/II/PS/ETF) by n-weighted buy-family `edge_20d`
  (`v_source_edge_scorecard`), `measured_rank` NULL when n<30.
  `etl/derive_actionable.py::_order()` resolves via
  `COALESCE(measured_rank, static_rank)` under `'measured'`;
  `RTA`/`TOP5`/`SSSCHG`/`RTAINFO`/`MACROSHOW` unaffected by either mode. The
  not-held sort also becomes `(rank, -latest_update)` under `'measured'`
  (was `(-latest_update, rank)`, which structurally favoured CALL).
  `drv_actionable.winning_source_rank`/`winning_source_edge` persist what
  won and its measured edge. Verified byte-identical in default `'static'`
  mode (zero `consolidated_action`/`winning_source`/`winning_priority`
  changes on a full anchor re-derive); `'measured'` mode changed 29/1,078
  winning sources and 16 `consolidated_action`s on the same test derive.
  Mode left `'static'` after verification. Released by TASK_139 (A4 HELD
  across two windows). Docs: `docs/actionable_logic.md`,
  `docs/actionable_playbook.md` §5.

- **Second-regime signal revalidation (TASK_139).** Re-ran the July
  signal-validation report (`docs/audit/signal_validation_2026-07.md`) over
  the full Feb→Sep dataset (`python -m etl.backfill_full`, drv_rule_outcome
  now 12,406,349 rows through 2026-08-20), split into the original window
  (2026-02-02→06-11, regression check) and the new independent half
  (2026-06-12→latest). New report: `docs/audit/signal_validation_2026-09.md`.
  Measurement only — no view/derive/rule/threshold changes. Gate outcome:
  **A4 (source ranking) HELD → released TASK_140; SELL-side (unproven sell
  rules) HELD → released TASK_141.** Two non-gating assumptions FLIPPED
  without a regime change: `rr_bull_bear` (B/!B) no longer separates
  outcomes correctly, and the `SS`/high vs `SS`/mixed confidence direction
  reversed — both retired as trustworthy signals in
  `docs/actionable_playbook.md` §3.3/§5. The new period (SPX +3.0%, VIX avg
  16.5) is a calmer continuation of the same up-trend, not a drawdown/chop —
  A5 (edges generalize across regimes) remains formally unproven.

---

## 2026-09-20

- **Outcome ETL (`drv_rule_outcome`) scheduled nightly (TASK_138).**
  `etl/compute_firing_outcomes.py` was never wired into anything automatic —
  every edge number on screen (scorecard, LOW CONF flag, weak-buy-source
  recompute, the default dollar-weighted edge sort) had been scoring off a
  window last refreshed by hand on 2026-07-12.
  `etl/scheduler.py::run_nightly_outcomes()` now runs a missing-dates
  `derive_all` backfill (no-op if nothing missing) followed by
  `compute_firing_outcomes.run_incremental(since=anchor - 45 days)` every
  night, before the weak-buy-sources recompute and the factor-outcomes
  refresh (both consume this table). New `run_incremental()` +
  `--since DATE` CLI option added to `compute_firing_outcomes.py` — without
  it, the script rescans the *full* history in `drv_trig`/
  `drv_cat_atomic_input` on every call, even without `--truncate`; `--since`
  caps that to the tail of history (still idempotent via the existing
  `(rule_id, as_of_date, tos_symbol)` PK upsert). No `--truncate` in the
  nightly path — a full rebuild stays manual (`backfill_derives` +
  `compute_firing_outcomes --truncate`). No schema change, no derive-logic
  change on the decision path. Docs: `docs/rule_tuning_and_outcomes.md`,
  `docs/actionable_playbook.md` §0/§6.

---

## 2026-09-02

- **Universe screen — "By Source" view + "All My Stocks" button.** Third
  top-level hierarchy (Source → Asset Class → Sector → Symbol) rooted at
  the outlook source(s) that flagged a symbol (`drv_actionable.source_actions`,
  new `sources` field on `/api/universe`'s symbol rows) — a symbol can
  carry more than one, so it can land under several source tiles, same as
  Style tags. "All My Stocks" is an orthogonal toggle (not a 4th view):
  every held symbol across every account as flat tiles, no Account/Source/
  Asset Class/Sector grouping — a symbol held in several accounts combines
  into one tile (`current_position_dollar` is already the cross-account
  total on a `drv_actionable` row). `web/universe.js`/`web/universe.html`.
- **Actionable screen — 3W column removed.** The "3-Way Agreement" ▼3/▲3
  grid column is gone (dead `_agree3`/`_agree3Score` plumbing removed with
  it); `_threeWayAgreement()` itself stays, still feeding the "3-Way" row
  in the Final-Call side panel checklist.
- **Actionable screen — %Chg column Hi/Lo readout.** Tiny-font day
  High/Low under the price, each with its % distance from `last_price` in
  parens (e.g. "H $100 (+4%)"). Column widened 62px→98px, candle-to-price
  gap widened 4px→9px.
- **Watch/notify (🔔 column).** New `ref_watch` table — same-day price/
  level alert, separate from the standing `ref_conviction_hold` thesis.
  Trigger on a % move, or a genuine crossing (vs. a baseline reading taken
  at watch-creation, see `etl/derive_watch.py::_crossed`) of LRR/TRR/Trade
  line/Trend line/a $ target, or no condition at all (a plain
  "remind me regardless" reminder, triggered immediately). Live
  `LEFT JOIN LATERAL` in `get_actionable` (not baked into `drv_actionable`
  — this is ephemeral, not a historical annotation); `GET/POST/PATCH/DELETE
  /api/actionable/watch`. `etl/scheduler.py`'s `maybe_check_watches`
  (every ~minute, idempotent) flips `triggered_at`/`triggered_reason`;
  `maybe_send_watch_digest` (once/day, `ref_settings.watch_digest_hour`,
  default 15 = 3pm) emails ONE combined message of everything still
  triggered-and-unreviewed via `etl/notify.py::send_email` — skipped
  entirely if nothing qualifies, which is also how reviewing a watch
  in-app before the digest runs suppresses its email. Grid badge +
  quick-add popover + toolbar "Watching" panel in `web/actionable.js`/
  `web/actionable.html`.

---

## 2026-08-01

- **Dashboard cockpit (TASK_133, full build).** Replaces the `/` ticker-grid
  landing screen with a six-band daily risk cockpit. Design:
  `docs/dashboard_cockpit_design.md` (supersedes and deletes
  `docs/dashboard_attention_panel_design.md`).
  - **New tables** (`db/baseline.sql`): `ref_risk_gauge`, `ref_level_watch`,
    `ref_gauge_transmission`, `ref_market_pattern` (Phase 2 tuning surfaces);
    `drv_market_stat` (Phase 3: Yang–Zhang realized vol/VRP/breadth/
    participation + the 14/15-gauge Risk Dial, `etl/derive_risk_dial.py`);
    `drv_market_event` (Phase 6: range breaks/trend flips/z-scores/8 seeded
    patterns/calendar, `etl/derive_market_event.py`); `drv_category_perf`
    (Phase 5: time-weighted sector/asset_class/style returns vs proxy
    benchmark vs quad stance, `etl/derive_category_perf.py`);
    `hist_internals` (Phase 4.1: ToS `$ADVN`/`$DECN`/`$UVOL`/`$DVOL`/`$TRIN`,
    feed not yet flowing pending a user-side watchlist/LoadFiles.xlsx change).
  - **New feeds**: KOSPI complex (`^KS11`/`005930.KS`/`000660.KS`/`EWY` via
    Yahoo → `hist_macro`), Cboe VVIX/RVOL free CSVs (`etl/fetch_cboe.py`),
    `HYOAS` real credit-spread metric (was showing the `HYG` ETF price under
    a misleading `HY` label — relabeled), `T2S10` (2s10s curve) switched on.
  - **Bug fixes**: MOVE marketbar zone badge (`MOVE`→`MOVE:GIF` vol-threshold
    key mismatch); `/api/macro-areas` now sends server-canonical `hot_pct`/
    `cold_pct` (was silently falling back to a stale JS default).
  - **New API**: `api/routers/cockpit.py` — `GET /api/cockpit/risk-dial`,
    `/events`, `/factor-scorecard?axis=`, `/shortlist` (reuses the existing
    `/api/actionable` high-conviction filter, no new ranking logic).
  - **`derive_all()` cascade order**: `drv_market_stat` → (existing steps) →
    `drv_macro_score` → `drv_category_perf` → `drv_market_event`. The last
    two run later than their Phase headers originally said, because
    `drv_category_perf.quad_stance` needs `drv_macro_score`'s live
    per-membership stance and `drv_market_event`'s exposure block needs
    `drv_category_perf.market_value` — both are non-critical steps (a
    failure doesn't fail the cascade).
  - **Round 2 fix (position-swap / flow-gap detection, Part A):**
    `etl/derive_category_perf.py::_build_series` now detects a symbol's
    qty changing between two reported snapshots with **zero matching row
    in hist_cst/hist_ft (any action, not just Buy/Sell)** and forces that
    day's `r_t=0` + `flows_confidence='suspect'`, with the offending
    symbols recorded in `detail.windows.<w>.gap_days` — closing a gap the
    original 25%-magnitude-only guard missed whenever the untracked swap
    was small relative to the category's total value. Root cause: a Schwab
    transaction feed (`hist_cst`) for one account stopped loading
    2026-06-02 while its positions (`hist_cs`) kept updating, and a
    Fidelity account's positions (`hist_f`) have never had a single
    matching `hist_ft` row, ever — both real, ongoing feed gaps. See
    `DEV_HANDOFF.md` (archived as `DEV_HANDOFF.md` at the time, TASK_133
    round 2) for the full investigation.
  - **Frontend (Phase 7)**: `web/index.html` + `web/app.js` rebuilt — the
    `.dash-grid`/`#tickerSections`/section-chip ticker grid and the 3
    standalone side-stack cards (quads/econ/earnings) retired; six new
    bands render via `/api/cockpit/*` + the existing `/api/quad-window`,
    `/api/quad/band-factors`, `/api/anchor-status`. `styles.css`:
    `.dash-grid`/`.sections-grid`/`.ticker-col`/`.section-block`/
    `.ticker-grid` removed (verified dashboard-only); `.mini-grid`/
    `.side-scroll`/`.quad-mini`/`.side-stack` kept (reused by
    `web/actionable.html`).
  - **New tests**: `tests/test_yang_zhang.py`, `tests/test_risk_dial.py`,
    `tests/test_twr.py`, `tests/test_market_patterns.py` (pure-Python, no
    DB); `tests/acceptance/test_cockpit.py` (marked `@pytest.mark.acceptance`).

---

## 2026-07-15

- **MACRO: sliding look-ahead window over the monthly quad calendar
  (TASK_126).** Replaces the month now/next ramp + quarterly one-hot blend
  in `etl/derive_macro.py` with a sliding window `[D, D+H)` (`H` =
  `quad_lookahead_days`, default 60 calendar days) projected onto
  `ref_quad_periods` monthly rows; overlap-day weights (optional decay via
  `quad_lookahead_decay_hl`) blend the months' distributions into one
  effective distribution feeding the unchanged Stage 1–2 membership calc.
  Quarterly leg simplifies to current-quarter-only (no next-quarter blend)
  and its combine weight drops 0.20 → **0.05** (`quad_horizon_weight_qtr`).
  `quad_month_ramp_begin_days` / `quad_month_lead_days` /
  `quad_qtr_ramp_begin_days` / `quad_qtr_lead_days` / `quad_horizon_weight_mo`
  retired (reads deleted; rows left in `ref_settings` harmless). Sign-agreement
  override redefined on **near** (nearest window month's stance) vs **far**
  (weight-renormalized stance of the rest of the window) instead of
  month/quarter. Thresholds recalibrated: `macro_thr_bm` 0.62→1.25,
  `macro_thr_bs` 0.276→1.05, `macro_thr_stm` -0.736→-0.15, `macro_thr_sa`
  -0.88→-0.6 (live split: BM 2.4% / BS 17.3% / HOLD 65.0% / STM 8.3% / SA
  6.9%, n=1152 on 2026-07-14). `drv_macro_score` gained `detail JSONB`
  (`{h, coverage_pct, fallback, months[], eff{}, near_vs_far{}, tracking}`);
  `month_now_net`/`month_next_net`/`month_weight`/`qtr_next_net`/`qtr_weight`
  deprecated (columns kept, NULL going forward); `monthly_score` now stores
  `M_window`. This UPDATE also folds in a pre-existing drift fix: the
  2026-07-06 threshold/weight recalibration (0.65/0.35→0.80/0.20,
  thresholds 1.5/0.5/-0.5/-1.5→0.62/0.276/-0.736/-0.88) had only ever been
  applied by hand to the live DB, never migrated into `db/baseline.sql` — a
  fresh `db/init_db` before this change would silently get the stale 2026
  values. New API: `GET /api/quad-window` (aggregate, symbol-independent
  window mix for the regime band). `GET /api/actionable/macro-detail`
  layers `drv_macro_score.detail` onto the still-live Stage 1–2 membership
  resolution instead of recomputing the ramp/blend. `web/actionable.js`:
  `loadMacroBand()` regime band shows the window mix + dominant forward
  quad (was Month) with Quarter shown small/de-emphasized;
  `_macroTooltip()`/`_buildMacroPopHtml()` show the per-month window table +
  tracking tag instead of Month/Quarter ramp blocks; `macro_turn` (ramp
  alert) retired, `macro_conf` now the nearest window month's weight. Apply:
  `python -m db.init_db` then re-derive (restart the app first if it was
  already running — `etl/` changes need a fresh process, see CLAUDE.md).
  Full design: `docs/quad_design.md` (Stage 3).

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
