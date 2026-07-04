# Test-Debt Review — 2026-07-04

Trigger: the TASK_110 full-suite run — **396 failed / 2593 passed / 23 skipped
/ 35 errors** — none caused by TASK_103–110. This review triages the debt via
static analysis (test assertions vs. current code; no DB in the Cowork
sandbox) of the top-offender files (~200 of the 396 failures) plus the
suite-wide patterns. Per-class evidence gathered by codebase search; DB-state
claims are marked VERIFY-DB and need one dev run to confirm.

Suite shape: 74 files, ~33,400 lines. ~45 are `test_agent_work_N.py` and ~12
are `test_task_NN_*.py` — **one-time acceptance checks for historical agent
tasks**, not regression tests. The durable core (hedgeye parsers, rule
evaluators, classifier, cat-parity, comprehensive) is a minority of files but
the majority of the value.

---

## 1. Root-cause taxonomy

| Cat | Cause | Examples | Disposition |
|---|---|---|---|
| A | **Implementation-snapshot pins** — hex palettes, inline-style strings, file-tail snapshots, `DEV_HANDOFF.md` content, `git status` checks | `test_agent_work_38.py` (all ~33: June-2026 palette hexes), `_39` palette/file-tail classes, `_1`/`test_task_96`/`test_task_98` handoff-content, `_18::TestNoGitCommit` | **RETIRE** — will break on any legitimate change, forever |
| B | **Features never implemented or superseded** | `test_agent_work_11::TestTask73QuadOutlookColumns` (~40 tests — quad-columns superseded by TASK_74 MacroNet; `test_task74_macronet.py` asserts their *absence*), `_46::TestTileCSS` (`.mt-tile*` never in styles.css), `_42::TestUIUnheldRemoveToggle`, `_18::TestPillRuleDirectionClasses` | **RETIRE** — aspirational specs with nothing to map onto |
| C | **Feature exists, assertions drifted** | `test_agent_work_27` (Sources column behavior — code present, details moved), `_18` core classes, `_22` popup classes, `_9`/`test_market_bar_ui` script-tag parity (page count grew) | **REWRITE** — update to current behavior; these become durable tests |
| D | **Live DB/API state hardcoded** | `test_agent_work_42` (SSS/PS behavior on live rows, `anchor == 2026-06-12`!), `test_comprehensive` majority, `TestDBState`/`TestApiMacro` classes, `test_cat_parity` (15 *errors*) | **VERIFY-DB** — need a dev run; fix = assert schema/shape, not point-in-time data |
| E | **Environment gaps** | `node --check` tests hard-fail without Node on PATH (no skip), FRED tests hit the live API with no timeout/skip | **FIX conftest** — skip-if-no-node marker, network guards |

Special note on `test_cat_parity.py`: this is the gold-standard data-integrity
test (Excel↔DB parity) with proper skip mechanics — its 15 **errors** are
likely fixture-level (workbook path / stale schema), not logic. Worth
repairing, not retiring.

## 2. The systemic problem

Every agent task ships a `test_agent_work_N.py` that pins that task's exact
implementation (colors, markup, handoff text). These are **acceptance checks**
— valid the week they're written, guaranteed-stale afterward. Accumulated
result: a suite where 396 red tests hide any real regression.

**Policy fix (adopt as convention):**
1. Task acceptance tests go in `tests/acceptance/` marked
   `@pytest.mark.acceptance` (excluded from the default run); they may be
   deleted after the task's commit.
2. Anything kept in `tests/` must assert **behavior or schema**, never
   palette hexes, inline-style strings, file tails, handoff content, or
   point-in-time DB values (no hardcoded dates/counts).
3. `conftest.py` gains: skip-if-no-node for `node --check` tests, and a
   network marker for live-API (FRED) tests.

## 3. Per-file dispositions (top offenders)

| File | Failing | Disposition |
|---|---|---|
| test_agent_work_38 | 33 | RETIRE wholesale (Cat A: palette snapshot) |
| test_agent_work_11 | ~22 | RETIRE `TestTask73QuadOutlookColumns` (Cat B); keep/guard FRED tests (Cat E) |
| test_comprehensive | 27 | Keep — VERIFY-DB majority; fix data-pinned assertions (Cat D), it's a real regression suite |
| test_task_86_regime_band_factors | 24 | Keep — feature exists; failures likely Cat E (node) + drift; REWRITE |
| test_agent_work_46 | 21 | RETIRE `TestTileCSS` (Cat B); rest VERIFY-DB/REWRITE |
| test_agent_work_27 | 20 | REWRITE — behavioral, code exists (Cat C) |
| test_agent_work_42 | 17 | RETIRE `TestUIUnheldRemoveToggle` + the hardcoded-anchor-date test; rest VERIFY-DB |
| test_task_85_macro_rail | 16 | Keep — feature complete; Cat E + drift; REWRITE |
| test_agent_work_18 | 15 | RETIRE `TestNoGitCommit`, `TestPillRuleDirectionClasses`; REWRITE rest |
| test_cat_parity | 15 err | REPAIR fixtures (Cat D/E) — highest-value test in the suite |
| test_agent_work_9 / test_market_bar_ui / _39 / _22 remainder | ~29 | REWRITE parity/markup classes to current pages (Cat C) |
| ~40 more files, 1–14 each (~340 total incl. above) | — | Same taxonomy; triage from the TASK_111 inventory |

## 4. Execution plan (one task at a time, TASK_111 → 114)

1. **TASK_111 — inventory + mechanical retirements.** Save a full
   `pytest --tb=line -q` inventory to `docs/audit/test_failure_inventory.txt`;
   retire every Cat A/B item named above; add conftest node/network guards
   (Cat E). Expected: roughly halves the failure count with zero judgment
   calls.
2. **TASK_112 — rewrite drifted behavioral tests** (Cat C): _27, _18, _22,
   _9, market_bar_ui, task_85, task_86 + inventory-guided others.
3. **TASK_113 — DB-dependent repair** (Cat D): repair test_cat_parity
   fixtures; convert point-in-time data assertions in test_comprehensive/_42
   and friends to schema/shape assertions; classify anything still red as a
   real bug and report.
4. **TASK_114 — policy adoption**: `tests/acceptance/` + marker, conftest
   conventions, one-line CLAUDE.md convention row, move-don't-delete for any
   acceptance tests worth keeping.

Target end-state: full suite green (or explicitly-skipped) so it can act as a
regression net again; real bugs surfaced by TASK_113 get their own specs.

---

## 5. Close-out (TASK_111 → 114), 2026-07-04

**TASK_111** (prior pass): ground-truth inventory saved to
`docs/audit/test_failure_inventory.txt`; mechanical Cat A/B retirements +
Cat E conftest guards landed. Failure count: 392 → 309.

**TASK_112** (this pass, no DB): worked through the full inventory file by
file. Rewrote assertion drift to current behavior in ~35 files (examples:
`_srcSubLineHtml()` → `_srcReasonsHtml()` across _24/_27/_28/_33/_36/_50;
finalCall() confidence tier redesign `high/med/mixed` → `gate/high/mixed`
across _17/_25/_29/_31; `-fill`→`-tint` badge exception in _34;
`renderGrid()`/`_func_body()` fixed-`max_len` truncation-window bugs in
_22/_23/test_task_85/_86 replaced with brace-matching; macro-rail single-
section → multi-panel restructure in test_task_85; band-factor pill-strip
removal + MacroNet-tooltip repurposing in test_task_86; hedgeye winner-pick
recency-first/SOURCE_ORDER redesign in _48/_49). Retired further Cat A/B
items (DEV_HANDOFF.md content pins across ~15 files; git-status/git-diff
pins; a few genuinely-superseded aspirational specs). **Discovered and
documented a real bug** (not fixed, per guardrails): 8 `web/*.html` files
were truncated on disk mid-`<script>` tag — this was fixed **externally**
during the batch (commit `7d7f692`), confirmed and comments updated
in-place. Also fixed a mechanical `.read_text()` platform-encoding bug
(missing `encoding='utf-8-sig'`) that was masquerading as ~20 unrelated
test failures across `test_comprehensive.py`.

**TASK_113** (DB, live Postgres): repaired `test_cat_parity.py` — two
fixture bugs, not real parity mismatches: (1) a `NOT IN :skip` bind without
`bindparam(expanding=True)` broke every query; (2) the fixture queried
`SELECT symbol` against `drv_cat_*` tables that use `tos_symbol` (per
CLAUDE.md convention #15), which raised `UndefinedColumn` and was masked as
"table not loaded" for all 12 categories. After both fixes, the real,
now-running parity check **passes** for `drv_cat_atomic_input`. Fixed a
real fixture bug in `tests/conftest.py`'s `db_session` fixture
(`etl.db._engine` is a cache variable, not callable — must call
`get_engine()`). De-pinned point-in-time data assertions in
`test_comprehensive.py`, `test_agent_work_42.py`, `test_agent_work_11.py`,
`test_agent_work_15.py`, `test_marketbar.py`, `test_market_bar_ui.py` to
dynamic-symbol-discovery / floor / shape checks instead of frozen
2026-06-12-era values, counts, and symbol names.

**TASK_114** (policy): registered the `acceptance` marker + `network`/`db`
markers in `tests/conftest.py`; added `pytest.ini` (`addopts = -m "not
acceptance"` — first pytest config file in the repo); moved 4 wholly
one-time acceptance files (`test_agent_work_89.py`, `test_task_87_corr_
rematch.py`, `test_task_90_histy_corr.py`, `test_task_102_emit_race_fix.py`
— all pinned to a single historical re-derive/incident date with no
durable regression value) to `tests/acceptance/`, marked
`@pytest.mark.acceptance`; retired one isolated point-in-time straggler in
an otherwise-durable file (`test_task101_hedgeye_panel.py`) rather than
moving that whole file. Added the one-line Conventions row to `CLAUDE.md`
(#18).

### Real bugs found (residual — need their own specs)

1. **`ref_ma_columns` registry is 92% empty.** All 98 rows are for
   `drv_cat_atomic_input`; the other 11 `drv_cat_*` tables (identity,
   price, bollinger, rsi, macd, ivhv, volume, risk_range, trend_trade,
   moving_avg, perf_extremes) have **zero** registry rows, so
   `test_parity_for_cat_table` skips ("no registry rows") for 11 of 12
   categories — the Excel↔DB parity net has real coverage for only 1
   category today. Needs a re-run of the registry-seeding build step
   (`seed_ref_ma_columns.py` / `enrich_ref_ma_columns.py` /
   `auto_enrich_registry.py`) for the missing categories.
2. **Dead code reintroducing "stray" action hex.** `actionable.js` defines
   an unused `ACTION_CODE_COLOR` map + `_actionCodeColor()` helper
   hardcoding `#2f9e2f`/`#d83a3a`/`#e07c1a` — the exact hex values
   AGENT_WORK_19 eliminated in favor of CSS custom properties. Confirmed
   never called anywhere; cosmetic/hygiene cleanup, not a live-UI bug.
3. **`.act-badge.*-fill` badges use hardcoded hex, not `var(--act-*)`.**
   The Final Call / calibrated-Final-Call badges (`_finalCallHtml()`,
   `_finalCallCalHtml()`) intentionally use `-fill` (not `-tint`) to match
   the Hedgeye panel, but do so via literal hex in `styles.css`
   (`#d83a3a`/`#e07c1a`/`#2f9e2f`) rather than the `--act-*` custom
   properties (which now hold *different* values, `#9e3636` etc.) — a
   cosmetic inconsistency between the two color mechanisms, not a
   functional bug.
4. **Two `test_agent_work_10.py` / `test_agent_work_12.py` tests reference
   a removed `buildTapeHtml()` in `web/market_bar.js`.** This is fallout
   from the concurrent, explicitly out-of-scope TASK_115/116 market-panel
   consolidation track (see `AGENT_WORK.md`: "Market-panel queue TASK_115→
   116: specced, NOT in this batch — separate track") — left untouched
   here; that track's own developer pass should update/retire these tests
   since it owns `market_bar.js`.

All other previously-flagged Cat D items (`test_agent_work_89.py`,
`test_task_87_corr_rematch.py`, `test_task_90_histy_corr.py`,
`test_task_102_emit_race_fix.py`) were one-time acceptance snapshots, not
real bugs — moved to `tests/acceptance/` per TASK_114 rather than reported
here.

### Final numbers

`pytest tests/` (default, DB up): **10 failed, 2579 passed, 30 skipped, 111
deselected (acceptance bucket)** — down from 392 failed / 2605 passed / 23
skipped / 35 errors at the TASK_111 starting point. All 10 residual
failures map 1:1 to the 4 real-bug findings above (items 1–4); none are
test debt.
