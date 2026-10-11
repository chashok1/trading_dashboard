# TASK_112 — Test-debt cleanup, part 2 of 4: rewrite drifted behavioral tests

Source: `docs/audit/test_debt_review.md` (§1 Cat C, §3, §4 item 2). Prereq:
TASK_111 done (inventory saved to `docs/audit/test_failure_inventory.txt`;
Cat A/B retired; conftest node/network guards added).

**Batched with TASK_113 and TASK_114 — do them in order, 112 → 113 → 114, in
one developer pass.** Log all three in the same `DEV_HANDOFF.md`, end with the
single literal marker `ALL_DONE`. No commit; no tester.

Goal: for tests where the **feature still exists but the assertion drifted**
(Cat C), rewrite the assertion to current behavior so it becomes a durable
regression test. Rewrite — do not retire, do not pin to a fresh snapshot.

Scope: static / no-DB only. Anything that needs live DB or API state is
TASK_113 — if a failing assertion here turns out to be data-pinned, move it to
the TASK_113 list and note it, don't fix it here.

## Items

Work from `docs/audit/test_failure_inventory.txt` as the ground truth of what
is still red after TASK_111. The named classes below are the known Cat C
offenders; the inventory will list more of the same pattern — treat them the
same way.

1. **TASK_111 deferrals (do first — they're already triaged).**
   - `test_agent_work_38.py::TestNoLayoutChanges` — update the expected column
     set to include the current `'Pos $'` header (drifted, not a palette pin).
   - `test_agent_work_38.py::TestFileTails` — update to the current file-tail
     expectation (the TradingView-widget string) **or**, if it's a pure
     file-tail snapshot with no behavioral meaning, retire it comments-in-place
     per the Cat A rule and say so. Judgment call — state which and why.
   - `test_agent_work_39.py::TestBlockA_ScorecardView` — the view is NOT
     renamed; it's `CREATE VIEW v_rule_scorecard` without `OR REPLACE`. Rewrite
     the assertion to accept the current DDL (assert the view exists / its
     shape, not the exact `CREATE OR REPLACE` string).
2. **Behavioral rewrites (code exists, details moved):**
   - `test_agent_work_27.py` — Sources-column behavior: rewrite to the current
     Sources rendering (code present, details relocated).
   - `test_agent_work_18.py` — core classes surviving TASK_111 (it retired
     `TestNoGitCommit` + `TestPillRuleDirectionClasses`): rewrite the rest to
     current markup.
   - `test_agent_work_22.py` — popup classes: rewrite to current popup markup.
   - `test_agent_work_9.py` + `test_market_bar_ui.py` — script-tag / page-count
     parity: the page set grew; rewrite to assert the current page inventory
     (assert presence of required scripts, not an exact count frozen in time).
   - `test_task_85_macro_rail.py` — feature complete; failures are Cat E (node,
     now guarded by TASK_111 conftest) + drift. Rewrite the drifted assertions.
   - `test_task_86_regime_band_factors.py` — same: feature exists; rewrite
     drift after the node guard.
3. **Inventory-guided remainder.** For every other still-red test whose feature
   demonstrably exists in `web/` / `api/` / `db/` (grep to confirm) and whose
   failure is assertion drift, rewrite it to current behavior. If the feature
   does NOT exist (missed Cat B), retire comments-in-place and note it. If it
   needs DB, defer to TASK_113.

## Rewrite rules (hard)

- Assert **behavior or schema**, never palette hexes, inline-style strings,
  file tails, handoff content, or point-in-time DB values (no hardcoded dates
  or row counts). A rewrite that re-pins a fresh snapshot is a failed rewrite.
- Prefer presence/shape assertions (element/class/route/column exists) over
  exact-string equality.
- Keep each rewritten test in `tests/` (these are the durable core). Do not
  move them to `tests/acceptance/` — that's TASK_114's job for the acceptance
  checks, not for genuine behavioral tests.

## Guardrails

- `node --check` is not applicable (test files are Python) — run
  `python -c "import ast; ast.parse(open('PATH').read())"` on every touched
  file + `tail -10` (mirror false-alarm gotcha).
- No production code changes. Tests and (if a genuinely wrong expectation is
  found) test fixtures only.
- Do not touch the Cat D / DB-dependent files (`test_cat_parity`,
  `test_comprehensive` data assertions, `test_agent_work_42` live-row tests) —
  those are TASK_113.

## How to verify

1. Re-run each touched file; the rewritten tests **pass** (not skip) in the
   no-DB sandbox, or are explicitly skipped only for the documented Cat E
   (node/network) reason.
2. Diff the failure list against `docs/audit/test_failure_inventory.txt`: the
   rewritten classes leave the failure set; zero NEW failures introduced.
3. In `DEV_HANDOFF.md`, list every class rewritten, every one retired-instead
   (with the missing-feature grep evidence), and every one punted to TASK_113
   (with why it needs DB).
