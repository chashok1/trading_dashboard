# TASK_113 — Test-debt cleanup, part 3 of 4: DB-dependent repair

Source: `docs/audit/test_debt_review.md` (§1 Cat D, special note on
`test_cat_parity`, §4 item 3). Prereq: TASK_112 done (Cat C rewrites landed;
data-pinned tests it punted are listed in `DEV_HANDOFF.md`).

**Batched with TASK_112 and TASK_114 — this is the middle step (112 → 113 →
114), one developer pass.** Continue the same `DEV_HANDOFF.md`. This is the
**only** task of the three that needs the live DB + running app — run it on
Windows against Postgres, not in a sandbox.

Goal: get the DB-dependent tests to green-or-skipped by repairing fixtures and
converting point-in-time data assertions to schema/shape assertions, and
surface anything still red as a candidate real bug.

## Items

1. **Repair `test_cat_parity.py` (highest-value test in the suite).** Its 15
   are **errors**, not failures — likely fixture-level (workbook path or stale
   schema), not logic. Fix the fixture so the Excel↔DB parity check runs:
   confirm the workbook path it points at exists / is current, refresh the
   expected schema if columns moved, keep its existing skip mechanics. Do NOT
   weaken the parity assertions themselves — this test's strictness is the
   point. If a parity mismatch is real (DB genuinely disagrees with the
   workbook), that's a real bug → report per item 4, don't paper over it.
2. **De-pin point-in-time data assertions (Cat D).** Convert hardcoded
   live-state expectations to schema/shape:
   - `test_comprehensive.py` — the majority are VERIFY-DB. Keep it (it's a real
     regression suite); change assertions that pin exact dates/counts/rows to
     assert structure (column presence, types, non-empty, invariants), not
     today's values.
   - `test_agent_work_42.py` — remaining live-row SSS/PS tests (TASK_111
     already retired its hardcoded-anchor test + the dead UI toggle). Re-express
     against shape, not the frozen `anchor == 2026-06-12` world.
   - `TestDBState` / `TestApiMacro` classes and any other still-red data pins
     the TASK_112 handoff punted here — same treatment.
3. **Idempotency / environment.** These tests must skip cleanly (not error)
   when the DB is absent, using the existing skip fixtures — verify that path
   still works so the Cowork sandbox and CI without Postgres stay green.

## Real-bug reporting (do not silently fix product code)

After repair, anything still red falls in two buckets:
- **Test still wrong** → finish converting it to shape/schema.
- **Product genuinely wrong** (DB/API disagrees with a correct expectation) →
  do NOT fix production code in this task. Record it in `DEV_HANDOFF.md` under
  a clear `## Real bugs found` heading (test, symptom, suspected cause). Per the
  review doc, "real bugs surfaced by TASK_113 get their own specs" — Cowork will
  spec follow-ups from that list.

## Guardrails

- Run against the live DB + app on Windows (`start.bat` / `uvicorn`). Cowork
  cannot run this — it's assigned to the developer with DB access.
- `python -c "import ast; ast.parse(...)"` + `tail -10` on every touched file.
- Tests + fixtures only; NO production code changes (real bugs are reported,
  not fixed, here).
- SQL in any new fixture ≤ 965 bytes/statement; SQLAlchemy + psycopg only.

## How to verify

1. `pytest tests/test_cat_parity.py` runs with the DB up: 0 errors; passes, or
   fails only on a genuine parity mismatch that is written up as a real bug.
2. `test_comprehensive` / `_42` / DB-state classes: pass against the live DB,
   or skip cleanly with no DB; no hardcoded date/count remains (grep for the
   old pinned values shows zero).
3. Full suite with DB up: failure count drops to the residual "real bug" set
   only; that set is enumerated in `DEV_HANDOFF.md`.
4. Full suite with DB **down**: the DB-dependent tests skip, not error.
