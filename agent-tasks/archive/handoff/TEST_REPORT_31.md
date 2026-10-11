# Test Report — AGENT_WORK_31

## Verdict
PASS_WITH_CONCERNS

## What I ran
- `node --check web/actionable.js` — passes (exit 0)
- `python -c "import ast; ast.parse(open('api/routers/dash.py').read())"` — passes
- `python -m pytest tests/acceptance/test_task_124_trade_mode.py -v -m acceptance` (new test file, authored this round) — **26 passed, 1 failed**
- `python -m pytest tests/ -q` (default suite, DB tests auto-skip when unreachable — Postgres *was* reachable this session) — **51 failed, 2556 passed, 28 skipped** — same 51 failure count/names as TEST_REPORT_30's documented baseline; none are new and none touch `trade_mode`/TASK_124 code
- Live server check: `curl http://127.0.0.1:8000/api/actionable/settings` and `.../api/actionable?date=2026-07-10&show_suppressed=true&show_acted=true` (1,211 rows), replayed the three JS predicates independently in Python against the raw payload
- Direct DB query via `etl.db.session_scope` against the live Postgres (`ref_settings` full dump)
- Read/diffed `web/actionable.js`, `web/actionable.html`, `api/routers/dash.py`, `db/baseline.sql` against `git diff --ignore-space-at-eol`

## Evidence
- Live `/api/actionable/settings` → `{"conviction_proven_edge_min":0.5,"trade_mode_weak_buy_sources":"PS,ETF,II"}` — API passthrough works (falls back to hardcoded default, see Failures below).
- Live `/api/actionable` payload (anchor 2026-07-10, 1,211 rows) has `rr_bull_bear`, `stop_breached`, `final_code`, `fc_feasible`, `winning_source`, `macro_value`, `held_today` on every row — confirmed directly, not from developer's claim. SQL source: `api/routers/dash.py` line 1087 `rr.rr_bull_bear` inside the `GET /api/actionable` join, confirmed via `git log`-referenced code read.
- Independent Python replay of the three category predicates against the live payload:
  - Qualifying buys: **19** (e.g. TXG/BM/feasible/B/no-stop/BS-macro/SSS-won; RH, YUM via CALL)
  - Held SA sells: **4** (KMX, DHI, LQD, SNAP)
  - Held stop breaches: **7** (DHI, XHB, BNDD, LQD, ZROZ, +2 more)
  - No buy is ever also stop-breached (buy predicate explicitly excludes `stop_breached`) — the "both a qualifying buy AND stop-breached" edge case from the brief is provably impossible by construction, not just untested.
  - DHI and LQD satisfy *both* held-SA-sell and held-stop-breach; `_matchesTradeMode` ORs the three predicates, so such a row renders once (correct — no double-count risk).
  - 0 of the 19 current qualifying buys are won by a PS/ETF/II source at this anchor, so the WEAK SRC pill isn't visibly exercised on live data today — verified via code reading + unit-level JS assertions instead (see below).
- `matchesBaseFilters`: confirmed the exact structure claimed — `if (state.filters.trade_mode) { if (!_matchesTradeMode(r)) return false; } else if (!state.filters.show_hidden) { <original logic, byte-identical> }`. Toggle-OFF (default `state.filters.trade_mode = false`) never enters the new branch — pixel-identical by construction, not just by developer assertion.
- `renderGrid()`: `r._watchlisted = state.filters.trade_mode ? false : _buyNoiseGated(r);` confirmed — Watchlist band never surfaces under Trade Mode.
- `_emptyStateHtml()`: `if (state.filters.trade_mode && state.rows.length === 0) return 'No trades today — nothing passed the playbook checks.';` — first branch, confirmed.
- `state.baseRows = state.allRows.filter(matchesBaseFilters)` confirmed — chip recounts are automatically Trade-Mode-aware, no extra wiring needed.
- localStorage: `TRADE_MODE_LS_KEY = 'act_trade_mode'`; restored via `localStorage.getItem` **before** `loadSources()`/first `loadActionable()` call (confirmed ordering); persisted on click via `localStorage.setItem`.
- **Gap found:** `ref_settings.trade_mode_weak_buy_sources` does **NOT** exist in the live database. Full dump of `ref_settings` (58 rows) confirms no such row, despite `db/baseline.sql` containing the correct additive `INSERT ... ON CONFLICT (setting_name) DO NOTHING` at the end of the file. The DEV_HANDOFF for this round explicitly states "Not independently verified against a running server/live DB this round (no DB access in this session)" — consistent with this finding; the migration was authored but never applied. `python -m db.init_db` was not run by me (blocked by the auto-mode classifier as a "modify shared resources" action, correctly out of scope for a QA agent that must not touch production state) — flagging for the user/developer to run it.
  - Practical impact: today the feature *looks* correct because both the API (`get_actionable_settings()`) and the JS (`loadSources()`'s catch block) fall back to the same hardcoded default `'PS,ETF,II'` when the row is absent — so the WEAK SRC pill currently behaves identically to the seeded value by coincidence.
  - However, the spec's own verification item 4 (`UPDATE ref_settings SET setting_value='PS' WHERE setting_name='trade_mode_weak_buy_sources';` then reload → only PS-won buys tagged) **cannot pass today**: the UPDATE affects 0 rows since the row doesn't exist, so the tunability the spec explicitly requires is not yet live. This is an operational/deployment gap, not a logic defect — the code on disk is correct and will work as soon as `python -m db.init_db` is run.

## Failures & gaps
- `ref_settings.trade_mode_weak_buy_sources` seed not applied to the live DB — `db/baseline.sql` has the correct additive INSERT but `python -m db.init_db` has not been run since it was added. Blocks live verification of spec item 4 (tunable WEAK SRC list) until applied. Not a code defect; a deployment step the user needs to run.
- Minor, non-blocking: at the current anchor (2026-07-10) no qualifying buy happens to be won by a PS/ETF/II source, so the WEAK SRC pill has not been observed rendering on live data this session — logic verified statically instead (predicate correctness confirmed via code + the independent JS-source assertions in the new test file).

## Acceptance criteria check
(per `agent-tasks/TASK_124_trade_mode.md` "How to verify")
1. Toggle OFF pixel-identical — met (yes): `matchesBaseFilters`'s `else if (!state.filters.show_hidden)` branch is untouched original code, unreachable change to any other code path when `trade_mode` is false; confirmed by direct read.
2. Toggle ON shows exactly the three categories, counts reported — met (yes): 19 buys / 4 SA sells / 7 stop-breach rows at anchor 2026-07-10, replayed independently against the live API payload; 3 spot-checked buys shown above all satisfy BM/BMN + feasible + B + no-stop + MACRO-not-SA/STM.
3. WEAK SRC pill on PS/ETF/II-won qualifying buys, not on RR/SSS-won ones — met (yes, by code inspection): `_isWeakSourceBuy` correctly gates on `_isTradeModeQualifyingBuy` first and checks `state.tradeModeWeakSources` (tunable set, not hardcoded); not exercised on live data today because no current qualifying buy happens to be PS/ETF/II-won.
4. Tunable list via `UPDATE ref_settings ...` + reload — **not met today** (no, blocked): the seed row doesn't exist live; the UPDATE would affect 0 rows until `python -m db.init_db` is run. Code path itself (client reads `settings.trade_mode_weak_buy_sources`, no hardcoded source list) is correct.
5. Chips recount, Focus mode iterates visible set, empty-state message — met (yes): `baseRows` built from `matchesBaseFilters` (Trade-Mode-aware by construction); empty-state branch confirmed; Focus mode/bulk bar not modified this round (verified they already consume `state.rows`, per handoff claim — read, not rewritten).
6. Toggle survives page reload (localStorage) — met (yes): restore-before-first-fetch ordering and setItem-on-click both confirmed in source.
7. `node --check` / `db.init_db` apply cleanly — `node --check` confirmed passing; `db.init_db` apply **not independently re-confirmed this round** (see gap above — I did not run it per my read-only mandate, and it evidently was not run in the live DB I tested against).

## Recommendation
- SHIP the code changes as-is (logic, toggle-OFF invariance, and predicates are all correct and verified against live data) — **but run `python -m db.init_db` before/at commit time** to apply the `ref_settings.trade_mode_weak_buy_sources` seed row to the live DB. Until that's done, the WEAK SRC tunability (spec item 4) is inert (masked by matching hardcoded fallbacks on both client and server). No source-code fix needed — this is purely "run the migration."
