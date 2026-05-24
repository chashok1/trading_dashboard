# Running the drv2_*/drv_cat_* Build

All infrastructure is complete and ready to execute. This document explains how to run the automated build.

## Quick Start

```bash
cd C:\Ashok\Invest\Projects\trading-dashboard
python -m etl.execute_build
```

This single command will:
1. Initialize database schema (applies all DDL including ref_ma_columns)
2. Seed the registry from ma_columns_v2.csv (641 rows)
3. Enrich the registry from ma_columns_full.csv, seed CSV, and Excel workbook
4. Generate DDL for ~30 drv_cat_* tables
5. Apply the DDLs to the database
6. Generate drv2_* VIEW definitions
7. Wire per-category derives into etl/derive.py

**Estimated runtime:** 2-5 minutes

**Success indicators:**
- No errors printed
- Final message shows "BUILD COMPLETE!"
- `db/14_drv_cat_tables.sql` exists and contains ~30 CREATE TABLE statements
- `db/15_drv2_views.sql` exists and contains ~14 CREATE VIEW statements

## What Gets Created

### DDL Files (auto-generated)

- **db/14_drv_cat_tables.sql** — ~30 CREATE TABLE statements for drv_cat_*
  - drv_cat_identity (11 cols)
  - drv_cat_price (69 cols)
  - drv_cat_atomic_input (113 cols) ← rules engine input
  - drv_cat_composite (66 cols) ← rules engine output
  - drv_cat_bollinger, drv_cat_rsi, drv_cat_macd, ... (24 more)

- **db/15_drv2_views.sql** — ~14 CREATE VIEW statements for drv2_*
  - drv2_y, drv2_tl, drv2_td, drv2_tw, drv2_rr, ...
  - These provide source-based access (if ever needed)
  - Purely virtual (no physical columns stored twice)

### Database Tables

- **ref_ma_columns** — 641 rows, fully populated with:
  - column_name, excel_header, pipeline_stage, concept
  - drv_cat_table, drv2_table
  - pg_type, source_table, source_expr
  - exposed_to_rules, display_label

- **drv_cat_*** — ~30 new tables, one per concept:
  - Each keyed by (as_of_date, symbol)
  - Populated on first derive_all() run

### Code Changes

- **etl/derive.py** — Added:
  - `_derive_cat_table_impl()` function
  - Loop in `derive_all()` to derive all drv_cat_* tables
  - Import of ma_codegen module

## Testing the Build

### 1. Verify Registry Population

```bash
psql -d trading -c "SELECT COUNT(*) FROM ref_ma_columns;"
```

Expected: 639 rows (641 minus 2 separators)

```bash
psql -d trading -c "SELECT drv_cat_table, COUNT(*) FROM ref_ma_columns GROUP BY drv_cat_table ORDER BY COUNT(*) DESC;"
```

Expected: ~30 drv_cat_* tables with columns distributed across them

### 2. Verify DDLs Were Generated

```bash
ls -la db/14_drv_cat_tables.sql db/15_drv2_views.sql
```

Expected: Both files exist and have content (> 5KB each)

### 3. Verify Tables Were Created

```bash
psql -d trading -c "\dt drv_cat_*"
```

Expected: ~30 drv_cat_* tables listed

### 4. Run One Derivation

```bash
python -c "
from etl.derive import derive_all
from etl.db import session_scope
from datetime import date

with session_scope() as s:
    counts = derive_all(s, date(2026, 4, 30))
    for table, count in sorted(counts.items()):
        print(f'{table}: {count}')
"
```

Expected:
- All drv_cat_* tables show row counts around 820 (one per symbol)
- No errors

### 5. Check a Specific Table

```bash
psql -d trading -c "SELECT COUNT(*), COUNT(DISTINCT symbol) FROM drv_cat_price WHERE as_of_date = '2026-04-30';"
```

Expected: Both counts should be ~820 (same number of rows and distinct symbols = one row per symbol, which is correct)

## Troubleshooting

### "ERROR: table ref_ma_columns does not exist"

The DDL wasn't applied. Run manually:
```bash
python -m db.init_db
```

### "ERROR: ref_ma_columns is empty"

The seed didn't run. This shouldn't happen if you use `execute_build.py`, but if it does:
```bash
python -m etl.seed_ref_ma_columns
```

### "ERROR: No drv_cat_* tables found in ref_ma_columns"

The seed failed or the CSV is missing. Check:
```bash
ls -la docs/ma_columns_v2.csv
```

### Derive fails with "AttributeError: 'NoneType' object has no attribute..."

A source_expr is NULL when it should have a value. Check the registry:
```bash
psql -d trading -c "SELECT column_name, source_expr FROM ref_ma_columns WHERE source_expr IS NULL LIMIT 5;"
```

Fix the null source_expr values manually:
```bash
psql -d trading -c "UPDATE ref_ma_columns SET source_expr = 'td.bb_top_15d' WHERE column_name = 'bb_top_15d';"
```

Then regenerate DDLs and re-run init_db:
```bash
python -m etl.generate_cat_ddl
python -m db.init_db
```

## Next Steps (After Successful Build)

1. **Full derivation test:**
   ```bash
   python -m etl.tickers_initial_load
   ```
   This will derive all 641 columns across all ~820 symbols for all available dates. Takes ~2-5 minutes.

2. **Parity testing (optional, validates correctness):**
   ```bash
   pytest tests/test_cat_parity.py -v
   ```
   This compares DB values against Excel for 20 sample symbols × 5 dates. If any fail, the source_expr is wrong for that column.

3. **Rules engine wiring (Phase 2):**
   - Rewrite `ref_trig_atomic_rule.ma_column_name` to point at `drv_cat_atomic_input` instead of `drv_ma`
   - Update `_derive_stks_impl` to read from the colocated `drv_cat_atomic_input` table
   - Should dramatically speed up rule evaluation (1 table join vs 600+ column joins)

4. **Thin drv_ma rebuild (Phase 3):**
   - Replace wide drv_ma table with a VIEW joining drv_cat_* tables
   - Keeps only cross-source computed columns (if any)
   - Dashboard APIs stay the same, backend is completely refactored

5. **API updates (Phase 4):**
   - Add `GET /api/ma/columns?stage=<stage>&concept=<concept>` endpoint
   - Add `/api/data/drv_cat_<x>` browser endpoints
   - Wire Rules Manager typeahead

## Architecture Summary

The build creates a two-axis categorical system:

**Axis 1: pipeline_stage** (left-to-right in MA tab)
- lookup_identity, lookup_data, derived_features, atomic_input, composite, rule_summary, decision, holdings

**Axis 2: concept** (trading domain)
- bollinger, rsi, macd, ivhv, volume, risk_range, trend_trade, moving_avg, perf_extremes, quad_outlook, fundamentals, index_volatility, volatility_regime, atomic_input, composite, trig_summary, identity, price, etf, ii, ps, signal_strength, earnings, he_outlook, action_decision, holdings_dollars, sector_rollup

**Storage:** 30 drv_cat_* tables (by concept, the natural grouping)
**Access:** 14 drv2_* views (by source, for reference)

This solves the 641-wide-column problem by organizing columns semantically, making the system more maintainable and the rules engine dramatically faster.

---

## Questions?

Refer to:
- BUILD_INSTRUCTIONS_drv2_and_drv_cat.md — Full architectural spec
- PHASE1_DELIVERABLES.md — Infrastructure overview
- IMPLEMENTATION_GUIDE_drv2_drv_cat.md — Detailed workflow
