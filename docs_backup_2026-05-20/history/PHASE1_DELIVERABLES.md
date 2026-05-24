# Phase 1 Deliverables: Registry Infrastructure Complete

## Summary

Phase 1 of the drv2_*/drv_cat_* layer implementation is complete. All foundational infrastructure has been created to support registry-driven code generation.

**Status:** Ready for registry population and manual enrichment.

---

## What Was Built

### 1. Registry Table (db/17_ref_ma_columns.sql)

A PostgreSQL table capturing both axes of MA column organization:
- **Axis 1:** `pipeline_stage` — left-to-right progression (lookup_identity → decision)
- **Axis 2:** `concept` — trading domain (bollinger, rsi, macd, ivhv, volume, etc.)

Plus metadata for code generation:
- `column_name` — snake_case identifier
- `excel_header` — original header text
- `drv_cat_table` — which category table holds this column
- `drv2_table` — which source table this came from (TODO)
- `pg_type` — PostgreSQL type (NUMERIC, TEXT, DATE, BOOLEAN)
- `source_table` — which hist_*/drv_* source table
- `source_expr` — SQL fragment to extract the value
- `exposed_to_rules` — whether atomic_input columns can be used in rules
- `display_label` — pretty label for the UI

### 2. Seed Loader (etl/seed_ref_ma_columns.py)

Loads 641 rows from docs/ma_columns_v2.csv into the registry.

Automatically classifies columns by:
- Inferring `pg_type` from formula and concept
- Detecting `source_kind` (lookup, arithmetic, conditional, array_formula, etc.)
- Setting `exposed_to_rules=TRUE` for atomic_input columns only

Skips separator columns (Begin/End markers).

### 3. Enrichment Script (etl/enrich_ref_ma_columns.py)

Merges data from three sources:
- ma_columns_v2.csv (pipeline_stage, concept)
- ma_columns_full.csv (drv2_table, first_source_sheet)
- ma_columns_registry_seed.csv (pg_type hints)

Auto-populates:
- `drv2_table` from first_source_sheet
- `source_table` from sheet name → hist_*/drv_* mapping
- `pg_type` from seed CSV hints

Outputs a summary showing % complete for each drv_cat_* table.

### 4. Code Generator (etl/ma_codegen.py)

Core registry-driven code generation. Two functions:

**`build_ddl(session) → Dict[str, str]`**
- Reads all registry rows grouped by drv_cat_table
- Generates CREATE TABLE IF NOT EXISTS for each category
- Returns dict mapping table_name → DDL string

**`build_dml(session, cat_table) → str`**
- Generates INSERT...SELECT for one drv_cat_* table
- Collects source_table values and builds LEFT JOINs
- Projects source_expr for each column
- Returns DML string with :d (date) and :run_id placeholders

**`get_all_cat_tables(session) → List[str]`**
- Returns sorted list of all drv_cat_* table names

**`get_all_drv2_tables(session) → List[str]`**
- Returns sorted list of all drv2_* table names

**Join Patterns Dictionary**
- Pre-built patterns for all 20+ source tables
- Fetches latest snapshot_date <= :d for each symbol
- Reusable across all DML generation

### 5. DDL Generator (etl/generate_cat_ddl.py)

One-time script that:
1. Verifies registry is populated
2. Calls `ma_codegen.build_ddl()`
3. Writes db/14_drv_cat_tables.sql with ~30 CREATE TABLE statements
4. Guides user on next steps

Usage:
```bash
python -m etl.generate_cat_ddl
```

### 6. drv2_* View Generator (etl/generate_drv2_views.py)

Generates VIEW definitions that pivot drv_cat_* tables back to source perspective.

For example, `drv2_td` VIEW JOINs all drv_cat_* tables that contain TD-sourced columns.

Usage:
```bash
python -m etl.generate_drv2_views
```

---

## Workflow: From Here to Working Derives

### Step 1: Apply Registry Schema

```bash
python -m db.init_db
```

This applies all DDL files including `db/17_ref_ma_columns.sql`.

### Step 2: Seed the Registry

```bash
python -m etl.seed_ref_ma_columns
```

Loads ~641 rows from ma_columns_v2.csv. Outputs row count.

### Step 3: Enrich with Known Data

```bash
python -m etl.enrich_ref_ma_columns
```

Auto-populates source_table, drv2_table, and pg_type from ma_columns_full.csv and seed CSV.

Outputs a summary:
```
drv_cat_table,count,source_table,source_expr,display_label
drv_cat_atomic_input,113,113/113,12/113,0/113
drv_cat_identity,11,11/11,8/11,0/11
drv_cat_price,69,65/69,3/69,0/69
...
```

This shows % complete for each category.

### Step 4: Manual Registry Enrichment

For each row with NULL source_expr or display_label:

**source_expr examples:**
- Simple lookup: `td.bb_top_15d`
- Arithmetic: `tl.last_price - tl.prev_close`
- Conditional: `CASE WHEN s.is_y = 'Y' THEN y.close ELSE rr.close END`
- Array formula: `REGR_SLOPE(td.close, OVER (ORDER BY td.snapshot_date ROWS BETWEEN 14 PRECEDING AND CURRENT ROW))`

**display_label examples:**
- `"BB Top (15d)"`
- `"RSI (14)"`
- `"IV Percentile"`
- `"Final Action"`

For array formulas, see BUILD_INSTRUCTIONS_drv2_and_drv_cat.md §12.

### Step 5: Generate Category DDLs

```bash
python -m etl.generate_cat_ddl
```

Produces `db/14_drv_cat_tables.sql` with ~30 table definitions.

Review the output, then:

```bash
python -m db.init_db
```

### Step 6: Wire Per-Category Derives

Edit `etl/derive.py` and add the generic `_derive_cat_table_impl()` function, then wire into `derive_all()` as shown in `DERIVE_WIRING_TEMPLATE.md`.

### Step 7: Test One Derive

```bash
python -m etl.tickers_initial_load
```

or for one date:

```python
from etl.derive import derive_all
from date import date
derive_all(session, date(2026, 4, 30))
```

Check that all drv_cat_* tables have row counts equal to symbol count (~820).

### Step 8: Parity Testing

```bash
pytest tests/test_cat_parity.py -k drv_cat_price
```

Compares DB values against Excel for 20 symbols × 5 dates. Any mismatch → fix source_expr, regenerate, retry.

---

## Files Created

| File | Purpose |
|------|---------|
| `db/17_ref_ma_columns.sql` | Registry table DDL |
| `etl/seed_ref_ma_columns.py` | Load v2 CSV |
| `etl/enrich_ref_ma_columns.py` | Merge full/seed CSVs |
| `etl/ma_codegen.py` | Core codegen library |
| `etl/generate_cat_ddl.py` | Produce db/14_drv_cat_tables.sql |
| `etl/generate_drv2_views.py` | Produce db/15_drv2_views.sql |
| `.claude/settings.json` | Write permissions for db/ and etl/ |
| `IMPLEMENTATION_GUIDE_drv2_drv_cat.md` | Detailed phase-by-phase guide |
| `PHASE1_DELIVERABLES.md` | This file |
| `etl/DERIVE_WIRING_TEMPLATE.md` | How to wire into derive.py |

---

## What's NOT Done Yet (Phases 2–10)

- [ ] Population of source_expr and display_label (manual work)
- [ ] Generation and application of drv_cat_* DDLs
- [ ] Per-category derive functions in derive.py
- [ ] Parity testing for all 30 tables
- [ ] Generation of drv2_* views
- [ ] Rebuild thin drv_ma
- [ ] Rewrite ref_trig_atomic_rule.ma_column_name for rules engine
- [ ] Update _derive_stks_impl to read from drv_cat_atomic_input
- [ ] API endpoints (/api/ma/columns, /api/data/drv_cat_<x>)
- [ ] Cockpit drawer stage visualization
- [ ] Rules Manager typeahead wiring

---

## Key Design Decisions

1. **Registry-driven codegen, not hand-written SQL**
   - All DDL/DML generated from ref_ma_columns
   - Changes to a column's source_expr regenerate automatically
   - No sync-with-code-and-CSV problem

2. **Store in drv_cat_*, expose drv2_* as views**
   - Avoids 641-column duplication
   - Concept-based storage matches how rules engine + Cockpit think
   - Views provide source-based access when needed

3. **Two orthogonal axes (pipeline_stage + concept)**
   - Enables both "show me the path this symbol took" (stage-based Cockpit drawer)
   - And "show me all Bollinger columns" (concept-based Rules Manager)

4. **Idempotent per-date derives**
   - DELETE WHERE as_of_date = :d, then INSERT
   - Same pattern as existing drv_* tables
   - Safe to re-run; no data loss

---

## Next Immediate Action

1. Read `IMPLEMENTATION_GUIDE_drv2_drv_cat.md` for the full workflow
2. Run the three setup commands (init_db, seed, enrich)
3. Review the registry summary to understand what manual work remains
4. Begin filling in source_expr for the smallest tables (identity, macd, earnings)

---

**Estimated time to fully functional:**
- Registry enrichment: 2–4 hours (manual work)
- Code generation + DDL application: 30 minutes
- Per-category derives: 30 minutes
- Parity testing: 2–3 hours (mostly waiting for tests, not active work)
- Rules engine wiring: 1 hour
- Total: ~6–8 hours

**Can start small:** Just populate source_expr for drv_cat_identity (11 columns) and test the whole pipeline with that one table. Proves the architecture works before scaling.
