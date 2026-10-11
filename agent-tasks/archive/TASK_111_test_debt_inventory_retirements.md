# TASK_111 — Test debt: inventory + mechanical retirements

Source: `docs/audit/test_debt_review.md` (2026-07-04). First of the test-debt
queue (111 → 112 → 113 → 114). Goal: capture ground truth, then delete the
tests that are wrong **by design** — no judgment calls in this task; anything
ambiguous is deferred to TASK_112/113.

Files expected to change: `tests/*.py` (retirements), `tests/conftest.py`
(guards), new `docs/audit/test_failure_inventory.txt`.

## Item 1 — Failure inventory (do FIRST, before any change)

Run the full suite and save the per-test line-level result:
`pytest tests/ -q --tb=line > docs/audit/test_failure_inventory.txt 2>&1`
(append a header line with date + counts). This is the ground-truth input for
TASK_112/113 — commit it as-is even though it's large.

## Item 2 — Category A retirements (implementation-snapshot pins)

Delete (replace each class with a short retirement comment, same style as the
TASK_110 retirements):
- `tests/test_agent_work_38.py` — ALL palette/inline-style/CSS-snapshot
  classes (the whole file is a June-2026 palette acceptance check). If
  `TestFileTails`/`TestNoLayoutChanges` currently pass and seem durable, they
  may be kept — implementer verifies from the Item 1 inventory.
- `tests/test_agent_work_39.py` — `TestBlockB_PaletteVars` (palette hexes),
  `TestBlockD_FileTails::test_baseline_sql_tail` (tail snapshot),
  `TestBlockA_ScorecardView` only if the view rename is confirmed (else
  leave for TASK_112).
- `tests/test_agent_work_18.py` — `TestNoGitCommit` (asserts git staging
  state), `TestPillRuleDirectionClasses` (compound `.pill-rule.rule-*` CSS
  never in styles.css).
- `tests/test_task_96_ingest_log.py::test_check36_handoff_references_agent_work_7`
  and `tests/test_task_98_ingest_log_screen.py::test_check43_references_agent_work_8`
  — rolling-handoff content pins (same pattern retired in TASK_110).

## Item 3 — Category B retirements (feature never implemented / superseded)

- `tests/test_agent_work_11.py::TestTask73QuadOutlookColumns` — entire class
  (~40 tests). The TASK_73 quad-columns feature was superseded by TASK_74
  MacroNet; `test_task74_macronet.py` explicitly asserts these artifacts are
  ABSENT. Keep the file's FRED tests (guarded in Item 4).
- `tests/test_agent_work_46.py::TestTileCSS` — `.mt-tile*` classes and 58px
  tape heights exist nowhere in styles.css (feature not implemented/reverted).
- `tests/test_agent_work_42.py::TestUIUnheldRemoveToggle`
  (`show_not_held_remove` — 0 matches in web/) and
  `TestAnchorDate` (asserts `MAX(export_date) == '2026-06-12'` — a
  point-in-time pin that is wrong every day since).

## Item 4 — Category E conftest guards

In `tests/conftest.py`:
1. `node_available` helper (`shutil.which('node')`) + auto-skip for tests
   that shell out to `node --check` (grep tests/ for `node --check` /
   `node_check` usages and apply the marker/skip consistently — at least
   test_task_85, test_task_86, and several test_agent_work_N files).
2. `network` marker for tests hitting live external APIs (the FRED tests in
   test_agent_work_11) with a short socket timeout + skip-on-failure, so the
   suite can't hang offline.

## Item 5 — After-count

Re-run `pytest tests/ -q --tb=no`, append the new totals as a footer to
`docs/audit/test_failure_inventory.txt` ("after TASK_111: X failed / Y
passed / Z skipped / E errors").

## Guardrails

- Tests + conftest + the inventory file only — no production code, no docs
  beyond the inventory.
- Retire = replace with a dated comment naming this task, not silent
  deletion, so history is greppable.
- Anything not explicitly listed above stays untouched, even if obviously
  broken — TASK_112/113 handle judgment calls.
- Log in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit; no tester.

## How to verify

1. `docs/audit/test_failure_inventory.txt` exists with header + footer counts.
2. `pytest tests/test_agent_work_38.py tests/test_agent_work_11.py -q` — no
   failures from the retired classes; retirement comments present.
3. On a machine without node on PATH (or with it renamed), the node-check
   tests skip instead of failing.
4. Failure count drops materially vs. the 396 baseline; ZERO previously
   passing tests newly fail (compare inventory before/after).
