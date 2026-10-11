# QA Report — Actionable Screen Batch (TASK_103 – TASK_110)

## Verdict
**PASS_WITH_CONCERNS**

The batch's core behavioral claims are all verified correct in the current code. No functional regressions were found. However, the batch's cumulative growth of `renderGrid()` (new columns from TASK_105/106) silently broke 3 additional pre-existing tests that DEV_HANDOFF's "no new failures" claim missed, and two more pre-existing test files (not part of TASK_110's 6-file cleanup) are permanently red because of TASK_103's approved dead-code deletion. Neither issue is a product bug — both are test-suite hygiene gaps.

## What I ran
- `pytest tests/test_agent_work_1.py tests/test_agent_work_11.py tests/test_agent_work_22.py tests/test_agent_work_39.py tests/test_agent_work_9.py tests/test_market_bar_ui.py -q` → 51 failed, 309 passed (matches DEV_HANDOFF's claimed 51; confirmed the 4 originally-stale items are gone/passing).
- `pytest tests/ -q` (full suite) → 392 failed, 2597 passed, 23 skipped, 35 errors (DEV_HANDOFF baseline: 396/2593/23/35 — within normal DB-state variance, no blow-up).
- `pytest tests/test_inline_act_fix.py tests/test_task_71_position_action.py -q` → 30 passed / 103 passed, 2 failed (both pre-existing, unrelated — DEV_HANDOFF.md rolling-content pinning + an unrelated `rule_performance.html` check).
- `pytest tests/test_agent_work_23.py tests/test_agent_work_24.py -q` → 13 failed, 52 passed, 10 errors — **new finding**, see below.
- New test file `tests/test_actionable_task103_110_qa.py` (8 tests, live Postgres via `TestClient`) → **8 passed**.
- `node --check web/actionable.js` / `node --check web/hedgeye_panel.js` → both clean.
- Manual code reads: `api/routers/dash.py` (snooze hide/show logic, bulk-action, macro-detail, settings, clear-action, INSERT statement), `web/actionable.js` (~15 targeted regions), `web/hedgeye_panel.js`, `api/routers/pages.py`, `db/baseline.sql` (user_action_log symbol→tos_symbol migration).
- Git archaeology: diffed current `web/actionable.js` against pre-TASK_103 commit `4c327ab` (via `git show`, read-only — no working-tree changes) to distinguish new vs. pre-existing test breakage.

## Evidence
- **TASK_103 Item 1/3 (snooze)** — `api/routers/dash.py:1148` hides `SNOOZED` when `snooze is None or snooze >= d`; client mirror at `web/actionable.js:1367`. `clear_actionable_action` (`dash.py:1607`) now does `user_action IN ('SKIPPED','SNOOZED')`. New test suite exercises both live against Postgres and passes.
- **TASK_106 dropped-`symbol`-column bug** — `db/baseline.sql:4417-4419` confirms `symbol` was dropped from `user_action_log`; the `INSERT INTO user_action_log` in `_log_actionable_action` (`dash.py:1493-1512`) references only `tos_symbol`, no `symbol`. Bulk-action integration test confirms no 500s.
- **TASK_106 bulk-action** — one `session_scope()`/transaction, per-symbol try/except (`dash.py:1569-1591`), respects the ≤965-byte SQL convention (loops the same parametrized single-row INSERT). Verified live: 3-symbol batch → one HTTP call → 3 DB rows → all 3 hidden from the grid.
- **TASK_106 lazy macro-detail / conviction settings / priority scale** — `GET /api/actionable/macro-detail`, `GET /api/actionable/settings` (`conviction_proven_edge_min`, default 0.5, seeded via `db/seeds_conviction_threshold.sql`), and `_computePriority`'s `seq*1e6+amt` (`web/actionable.js:2221-2241`) all match spec exactly; `get_actionable()` pops `macro_detail`/`macro_howto` (`dash.py:1174-1175`).
- **TASK_104 refresh etiquette / debounce** — `loadActionable({preserveState:true})` skips the sort reset, `applyClientFilter({preserveSelection:true})` re-intersects `state.selected`; symbol search debounced 150ms (`actionable.js:4183-4190`).
- **TASK_105 grid density** — column manager (`act_cols_v1`, default-hidden `['calc','bullprob','agree']`), Top-N=15 collapse, H column gated on `show_hidden`, MACRO `<th data-key="macronet">` (numeric sort) all present and match spec.
- **TASK_107 keyboard/focus** — single delegated `keydown` listener; Esc layering is strictly atomic-popover → modal → focus-card (`actionable.js:4033-4046`); Enter/D/S/Z/arrows wired and target-tag-guarded; Prev button + updated hint text present in `actionable.html:991-992`.
- **TASK_108 hedgeye grid layout** — `GRID_ROW1`/`GRID_ROW_MACRO`/`GRID_ROW2` use `display:grid; grid-template-columns: minmax(...)`, no more hand-tuned flex-basis; toggle chevron synced on every `render()` call, consistent semantics with the click handler.
- **TASK_109 cleanup** — `toggleSuppress` confirmed 0 occurrences; `web/macro_band.js` and `web/cockpit.html` confirmed deleted; `/cockpit` route is a bare 301, doesn't try to serve the deleted file; stop-level alert renders red/bold with the correct tooltip when `last_price < stop_level`; `exportCsv()` mirrors column visibility, includes Final Call/MACRO/CALC/P(↑20d)/Agree/stop_level/RVOL/IVP/IV/HV/MACD/MACDH/RSI, and **excludes** Trig.
- **TASK_110 test cleanup** — verified all 6 named stale-test retirements/rewrites are correct and the `TestTask7_CockpitRetirement` class is 7/7 passing.

## Failures & gaps
- **New regression (test-harness, not functional) — TASK_105/106, `tests/test_agent_work_22.py`.** `TestActActionCell` (3 tests: `test_act_action_cell_class_in_render_grid`, `test_data_sym_on_action_cell`, `test_cursor_help_on_action_cell`) now fail because `renderGrid()` grew past the test's hardcoded `_func_body(src, "renderGrid", max_len=6000)` char-offset window. Verified via `git show 4c327ab:web/actionable.js`: the `act-action-cell` marker sat at offset **5379** before this batch (test passed) and now sits at offset **6662** (test fails) — pushed over the line by the new CALC/bullprob/agree/MACD/MACDH/RSI columns added in TASK_105/106. `web/actionable.js:3029` shows the feature (`class="act-action-cell" data-sym="..." style="...cursor:help;"`) is fully intact — this is a test-tooling fragility issue, not a product bug. **DEV_HANDOFF.md's characterization is inaccurate**: it attributes this to "a later UI change apparently altered/removed this popup feature," but the feature was never altered — the test's fixed-length substring extraction just lost coverage of it. `test_fires_cell_html_still_in_render_grid` in the same class was already broken pre-batch (offset 7950 at commit `4c327ab`, already >6000) — that one genuinely is pre-existing, unlike the other three.
- **Pre-existing test debt not flagged by TASK_110, but directly related to TASK_103.** `tests/test_agent_work_23.py::TestActBadgeSmCallSites::test_act_badge_sm_in_render_other_sources` and `tests/test_agent_work_24.py` (`TestFunctionExists`, `TestCallSite`, `TestFileIntegrity`) assert the existence/behavior of `_renderOtherSources` and `_srcSubLineHtml` — both **intentionally deleted** by TASK_103 Item 6 as confirmed-dead code (verified absent via `grep`, present in pre-batch `git show 4c327ab`). This is expected fallout from an approved spec item, not a bug, but DEV_HANDOFF's blanket statement "[the ~340 additional pre-existing failures]... none of which mention or relate to TASK_103–110" is incorrect for these two files — they directly reference functions this batch deleted. TASK_110's 6-file cleanup scope simply didn't reach them.
- **Minor orphan, not required by any task spec.** `web/cockpit.js` still exists on disk and is unreferenced by any page (its only consumer, `cockpit.html`, was deleted in TASK_109). Not a regression — TASK_109 was only scoped to delete `macro_band.js`/`cockpit.html` — but worth a follow-up cleanup ticket.
- **Missing test coverage (now filled).** Neither the bulk-action endpoint nor the snooze/un-snooze DB round-trip had any real integration test before this review — both were explicitly flagged as previously-broken-in-production. Added `tests/test_actionable_task103_110_qa.py` (8 tests, all passing, self-cleaning against the live DB).

## Acceptance criteria check
- TASK_103 (snooze, un-snooze, popover ×, CSV Metric/sort dead code, focus-card Final Call, dead-code deletion) — met, yes. Verified in code + new integration tests.
- TASK_104 (preserve sort/selection on auto-poll, 150ms debounce) — met, yes.
- TASK_105 (column manager, Rules width/cap, Top-N collapse, H column gating, legend, Conv label, copy toast, empty states, MACRO numeric sort) — met, yes.
- TASK_106 (bulk-action endpoint, lazy macro-detail, conviction threshold, priority scale, `symbol`-column bug fix) — met, yes, confirmed via live DB tests.
- TASK_107 (Esc layering, focus-mode keys, Prev button, hint text) — met, yes.
- TASK_108 (CSS-grid hedgeye layout, toggle icon sync) — met, yes.
- TASK_109 (dead-code deletion, file deletions, stop alert, CSV refresh) — met, yes.
- TASK_110 (test cleanup of 6 named files) — met, yes, but scope was narrower than the "no new failures" claim implies (see Failures & gaps).
- "No regressions from the batch" — **partially met**: no functional/product regressions found; 3 test-only false failures were newly introduced by cumulative column growth (test_agent_work_22.py), mischaracterized in DEV_HANDOFF as unrelated.

## Recommendation
**SHIP** — the actual Actionable screen behavior is correct and matches every TASK_103–110 spec item; no product-facing bug found. Before closing the loop, send back two small, low-risk documentation/test-debt fixes to the developer (not blocking, can be a follow-up ticket rather than re-opening this batch):
1. Correct the `test_agent_work_22.py::TestActActionCell` root-cause note in whatever log supersedes this DEV_HANDOFF — it's a `max_len=6000` truncation artifact from `renderGrid()` growth, not a removed feature (no code fix needed, only a documentation correction, or bump the test's `max_len`/switch to brace-matching extraction).
2. Fold `test_agent_work_23.py`/`test_agent_work_24.py`'s stale assertions on `_renderOtherSources`/`_srcSubLineHtml` into a future stale-test cleanup pass, same pattern as TASK_110.

## Files
- New test coverage: `C:\Ashok\Invest\Projects\trading-dashboard\tests\test_actionable_task103_110_qa.py`
- Key files read/verified: `C:\Ashok\Invest\Projects\trading-dashboard\api\routers\dash.py`, `C:\Ashok\Invest\Projects\trading-dashboard\web\actionable.js`, `C:\Ashok\Invest\Projects\trading-dashboard\web\actionable.html`, `C:\Ashok\Invest\Projects\trading-dashboard\web\hedgeye_panel.js`, `C:\Ashok\Invest\Projects\trading-dashboard\api\routers\pages.py`, `C:\Ashok\Invest\Projects\trading-dashboard\db\baseline.sql`
- Task specs read: `C:\Ashok\Invest\Projects\trading-dashboard\agent-tasks\TASK_103_actionable_bug_sweep.md` through `TASK_110_actionable_doc_sync.md`
- DEV_HANDOFF reviewed: `C:\Ashok\Invest\Projects\trading-dashboard\DEV_HANDOFF.md`
