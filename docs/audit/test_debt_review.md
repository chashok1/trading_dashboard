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
