# TASK_114 — Test-debt cleanup, part 4 of 4: acceptance-test policy adoption

Source: `docs/audit/test_debt_review.md` (§2 policy fix, §4 item 4). Prereq:
TASK_112 + TASK_113 done (suite is green-or-skipped except reported real bugs).

**Batched with TASK_112 and TASK_113 — final step (112 → 113 → 114), one
developer pass.** Same `DEV_HANDOFF.md`, end the whole batch with the single
literal marker `ALL_DONE`. No commit; no tester.

Goal: adopt the convention that stops the debt from re-accumulating — separate
one-time task-acceptance checks from durable regression tests so future
`test_agent_work_N.py` files can't silently rot the suite.

## Items

1. **Acceptance bucket.** Create `tests/acceptance/` with an `__init__.py` (if
   the suite uses packages) and register an `acceptance` marker in
   `tests/conftest.py` via `pytest_configure` (alongside the `network` marker
   TASK_111 added). Exclude it from the default run: add
   `addopts = -m "not acceptance"` (or extend existing addopts) in the pytest
   config (`pytest.ini` / `pyproject.toml` / `setup.cfg` — use whichever the
   repo already has; don't introduce a second config file).
2. **Move, don't delete, the acceptance checks worth keeping.** For the
   surviving `test_agent_work_N.py` / `test_task_NN_*.py` acceptance checks that
   are still meaningful as a record but are NOT durable regression tests, move
   them into `tests/acceptance/` and mark the module/classes
   `@pytest.mark.acceptance`. Genuinely durable behavioral tests stay in
   `tests/` (TASK_112 already rewrote those) — do not sweep them into
   acceptance. Judgment call per file; state the rule you applied in the
   handoff. (Truly dead ones were already retired in TASK_111/112 — don't
   re-litigate those.)
3. **Convention doc.** Add ONE row to the `CLAUDE.md` Conventions list (it's an
   index — one line, detail lives here): task-acceptance tests go in
   `tests/acceptance/` marked `@pytest.mark.acceptance`, excluded from the
   default run and deletable after the task's commit; anything kept in `tests/`
   asserts behavior or schema only (no palette hexes, inline styles, file
   tails, handoff content, or point-in-time DB values). Cross-reference
   `docs/audit/test_debt_review.md` §2.
4. **Close-out.** Append a short summary to `docs/audit/test_debt_review.md`
   (or a dated note in `docs/migrations.md` per its convention) recording the
   111→114 outcome: what was retired, rewritten, repaired, and the residual
   real-bug list from TASK_113 that still needs its own specs.

## Guardrails

- After the config change, the **default** `pytest tests/` run must not collect
  the acceptance bucket; `pytest -m acceptance` must collect exactly the moved
  files. Verify both.
- `python -c "import ast; ast.parse(...)"` + `tail -10` on every touched file;
  moved files must still import (fix relative-path/import breakage from the
  move).
- Tests + config + docs only; no production code.

## How to verify

1. `pytest tests/` (default): green-or-skipped, acceptance bucket NOT collected,
   failure count = the residual real-bug set only.
2. `pytest -m acceptance`: collects exactly the moved acceptance files; they run
   (pass/skip) without collection errors.
3. `CLAUDE.md` has the new one-line convention row; `test_debt_review.md` /
   `migrations.md` has the 111–114 close-out with the residual real-bug list.
4. Batch-level: `DEV_HANDOFF.md` covers all three tasks (112 rewrites, 113
   repairs + `## Real bugs found`, 114 policy) and ends `ALL_DONE`.
