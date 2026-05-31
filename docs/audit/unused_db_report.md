# Unused Database Tables & Columns — Audit

**Date:** 2026-05-31 · **Method:** static analysis only — parsed `db/baseline.sql` +
`db/seeds_*.sql` for DDL, then grepped **live code only** (`api/`, `etl/`, `db/`, `config/`,
`tests/`, `web/`) for every table/column name. Root-level loose scripts, `_trash_*`,
`docs_backup_*`, and `*.log` were excluded (touching a table from a throwaway script does
not count as "used"). No live DB connection was available, so column-level findings are
candidates to confirm against the running DB, not proof.

---

## Headline

**No fully unused tables.** All 67 tables/views defined in the schema are referenced by
live code. The schema is tightly coupled to the app. The real cleanup opportunity is at the
**column** and **retired-table-stub** level, not whole live tables.

---

## Table inventory (67 total)

| Family | Count | Status |
|---|---|---|
| `ref_*` (lookup / tunable) | 23 | all referenced |
| `hist_*` (raw, append-only) | 17 | all referenced |
| `drv_*` (derived, incl. `drv_ma` VIEW) | 22 + 5 component tables | all referenced |
| `meta_*` (run audit) | 7 | all referenced |
| other (`user_action_log`, `ref_settings`, functions/views `v_dash`, `v_stks`, `v_ma`, `v_rule_performance`, `v_available_dates`, `v_outlook_changes`) | — | all referenced |

Most-referenced (sanity check): `hist_cs`, `drv_cat_atomic_input`, `drv_ma`, `ref_ma_columns`.
Least-referenced but still live: `ref_my_stocks` (3), `drv_dash_summary` (4), `ref_fed_blackout` (4).

---

## 1. Retired tables still stubbed in `baseline.sql` (remove candidates)

These were dropped from the pipeline but their DDL / comments may still linger in
`baseline.sql`. They are **not** written by any current derive:

No stub tables remain — `drv_tl` and `drv_ssh` were fully removed (2026-05-31).

---

## 2. `drv_ma` is no longer a wide table (already correct in schema)

The former ~98-column materialized `drv_ma` (of which ~42 columns were permanently NULL) was
replaced 2026-05-31 by a **VIEW** over `drv_symbols`, `drv_technicals`, `drv_fundamentals`,
`drv_outlooks`, `drv_portfolio`. The historical "42 dead columns" problem is therefore
**resolved** — each component table declares only what it populates. No action needed; docs
that still described the dead columns have been corrected.

---

## 3. Candidate dead/under-populated columns — resolved 2026-05-31

Live DB checks confirmed:

| Candidate | Finding | Action taken |
|---|---|---|
| `drv_quote.export_date/time/loaded_at` | 79,528 / 79,554 rows populated (99.97%) | None — in active use |
| `drv_cat_atomic_input` `not_*` / `c_*` columns | All 27 exist as real columns, all populated (confirmed via AAPL trace), accessed via `ref_ma_columns` name resolution by atomic rules | None — in active use |
| `drv_dash_summary.n_below_trend` | Populated with real values; the "typo" note is a logic question, not dead code | Separate investigation if needed |
| `ref_ma_columns` rows where `drv_cat_table='drv_cat_separator'` | 519 Excel cell-reference artifacts (`=Trig!AA1`, …) from a retired table with no DDL, no live table, and 0 atomic rule references | **Deleted** — `seed_ref_ma_columns.py` already skips these on re-seed |

---

## 4. Tables referenced in code but missing from DDL

**None found.** Every table the live code touches is defined in `db/*.sql`.

---

## Method caveats

1. Dynamic `SELECT *` + `row.get(name)` access (heavy in `trace.py`, `derive_cat_atomic_input.py`)
   defeats column-level grep — hence column findings are candidates only.
2. No live DB introspection — populated-vs-empty can only be confirmed with the `count(*) FILTER`
   queries suggested above.
3. Intermediate derive tables consumed only by another deriver can look "lightly referenced"
   but are still live.
