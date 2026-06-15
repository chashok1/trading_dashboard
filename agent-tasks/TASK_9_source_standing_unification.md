# TASK 9 — Unify per-source standing (`drv_source_standing`)

**You: VS Code developer agent, psql + browser.** Implement in the increments
below, in order. Log every change in `DEV_HANDOFF.md`; end it with `ALL_DONE`.
Hand verification to the tester via `AGENT_TASK.md` → `AGENT_RESULT_<n>.md`.
**DO NOT COMMIT/PUSH** — user commits from Windows after each increment passes.

Full design + rationale: **`docs/source_standing_logic.md`**. Read it first.

## Goal

Replace the two divergent "current list" computations (action path vs `drv_ma`
signal CTEs) with one canonical, `tos_symbol`-keyed table `drv_source_standing`,
built with one rule: **latest whole load ≤ D; absence = removed; no per-symbol
carry-forward** (CALL is the only exception, 30-day window). Both paths read it.
This also fixes the `ticker/symbol`→`tos_symbol` keying bug and the SSS NULL-signal
bug.

## The one rule (must hold for every source except CALL)

`snapshot_date = MAX(snapshot_date) WHERE snapshot_date ≤ D`; use ALL symbols in
that one load; a symbol absent from it gets NO standing row (removed). ETF/II add
`etfchg`/`iichg` patches dated after the base snapshot and ≤ D (bundle-cap, same
as today's `_state_etf_ii`). NEUTRAL/NULL outlook = not on list. CALL keeps its
30-day per-symbol window.

## Scope (files)

- `db/baseline.sql` — new `drv_source_standing` table (schema in design doc),
  index, cleanup policy `EXACT_MATCH` on `as_of_date`; later retire `drv_sss`.
- `etl/` new builder `derive_source_standing(session, D)` (own module or in
  `derive_v2.py`), wired into `derive_all()` BEFORE action + signal consumers.
  Reuse existing per-source formula logic (e.g. SSS math from
  `_derive_sss_v2_impl`); change only the row source (latest whole load ≤ D) and
  the key (`tos_symbol`).
- `etl/derive_outlook_action.py` — per-source classifiers read state from
  `drv_source_standing` (current = D, previous = prior load date) instead of
  re-querying `hist_*`. Delete dead `compute_standing_verdicts`.
- `etl/derive.py` — replace `ef`/`ii`/`sh`(/`cl`) CTEs in the `drv_ma`/`drv_outlooks`
  build with reads from `drv_source_standing`.
- `etl/derive_actionable.py` + `api/routers/dash.py` — re-key
  `asset_class_ps`/`asset_class_etf` (and PS/ETF drill-down lookups) on
  `tos_symbol`.
- `web/actionable.js` (+ `api/routers/dash.py` filter) — default view per Behavior
  rules below.

Out of scope: RR/SD/MACDH/MA technical indicators, AMT$ math, order execution,
edge-weighting/conviction-sizing (future tasks B1–B7 in
`docs/audit/actionable_business_review.md`).

## Behavior rules (acceptance, from user)

1. **SSS whole-snapshot:** dropped symbol = removed; never carried from an older
   load; `SSS_signal_sign` non-NULL for symbols on the latest load.
2. **SSS INCREASE/REDUCE stay demoted** from the consolidated headline (unchanged).
3. **PS drop emits REMOVE even when not held** (recorded as a per-source signal),
   but the **consolidated/final action ignores a not-held REMOVE**, and it must
   **not** erase a competing ADD on the same symbol.
4. **Default Actionable screen:** actionable symbols sorted by rank, **held
   REMOVE on top**; **not-held REMOVE hidden by default**, with a toggle to show.
5. **CALL** stays the 30-day window exception.

## Increments (commit each separately, after tester passes)

1. **SSS pilot** — table + builder for SSS only; wire SSS action input + SSS
   signal columns; behavior rules 1 & 2.
2. **ETF + II** — bundle-cap + patches into the builder; wire signal columns.
3. **PS** — rank into the builder; behavior rules 3 & 4 (REMOVE emit + screen).
4. **RR** — dense source into the builder.
5. **CALL** — window exception into the builder (rule 5).
6. **Cleanup** — delete `compute_standing_verdicts` + dead per-source state code;
   dedupe asset-class lookups; retire `drv_sss` (DDL + cleanup policy + `drv_ma`
   view).

## How to verify (tester — needs running Postgres + app)

Run after EACH increment; replace `:D` with `SELECT MAX(export_date) FROM hist_td`.

- **Table built, keyed right:** `SELECT source_code, COUNT(*) FROM
  drv_source_standing WHERE as_of_date=:D GROUP BY 1;` — every migrated source
  present; spot-check 3 rows have a real `tos_symbol` (not a raw ticker/symbol).
- **Whole-snapshot / removed:** pick a symbol present in the prior `hist_sss`
  load but absent from the latest load ≤ D → it has **no** `drv_source_standing`
  row for SSS at :D, and `drv_ma.SSS_signal_sign` is NULL for it. Pick a symbol
  on the latest load → `SSS_signal_sign` non-NULL.
- **tos_symbol bug fixed:** find a symbol whose `hist_ps.ticker ≠ tos_symbol` that
  you hold → `drv_outlook_action`/standing shows `held_today=TRUE` and the PS
  action resolves (no misfire).
- **PS REMOVE behavior:** a held PS-dropped symbol shows REMOVE on the default
  `/actionable` view, sorted with REMOVEs on top; a not-held PS-dropped symbol is
  hidden by default and appears when the toggle is on; confirm a competing ADD on
  a not-held symbol is NOT erased.
- **Action vs signal parity:** for one symbol, the SSS standing in
  `drv_source_standing` matches both what the action path used and the `drv_ma`
  SSS columns (no divergence).
- **Idempotent:** re-run `derive_all` for :D twice → identical
  `drv_source_standing` row counts/values.
- **Regression:** `pytest tests/`; `node --check` on changed JS; one live load
  cycle (`python -m etl.etl_load <file>`) → derive SUCCESS, screens update,
  consoles clean.

Write per-increment PASS/FAIL + evidence to `AGENT_RESULT_<n>.md`, ending `DONE`
or `FAILED: <increment>`.

## Constraints

- Follow `CLAUDE.md`. `tos_symbol` everywhere (convention #15). Derives idempotent
  (#2). Schema in `baseline.sql` (#5). SQL ≤ 965 bytes (#7). No commits (#17).
