# drv2_* and drv_cat_* Layer Implementation Guide

## Status: Phase 1 Complete (Registry Infrastructure)

This guide walks through the implementation of the new derivation layers per BUILD_INSTRUCTIONS_drv2_and_drv_cat.md §9.

### Phase 1: Registry Infrastructure ✅

Files created:
- `db/17_ref_ma_columns.sql` — Registry table DDL
- `etl/seed_ref_ma_columns.py` — Seed from ma_columns_v2.csv
- `etl/ma_codegen.py` — Registry-driven code generation (build_ddl, build_dml)
- `etl/generate_cat_ddl.py` — Generates db/14_drv_cat_tables.sql
- `etl/enrich_ref_ma_columns.py` — Enriches registry from full/seed CSVs

### Phase 2: Registry Population (Next)

Run these in order:

```bash
# Apply the registry DDL
python -m db.init_db

# Seed the registry from ma_columns_v2.csv
python -m etl.seed_ref_ma_columns

# Enrich with data from ma_columns_full.csv and ma_columns_registry_seed.csv
python -m etl.enrich_ref_ma_columns
```

### Phase 3: Registry Detail Work (Manual)

After running the above, you'll have ~80% of the registry populated. The remaining 20% requires manual work:

1. **source_expr** (~300 entries needed): SQL expressions to extract each column
   - For simple lookups: `hist_td.bb_top_15d` 
   - For arithmetic: `hist_tl.last_price - hist_tl.prev_close`
   - For conditionals: `CASE WHEN ... END`
   - Most are extracted from Excel formulas; some require translation to SQL

2. **display_label** (~300 entries): Pretty labels for the UI
   - Examples: "BB Top (15d)", "RSI (14)", "IV Percentile", "Final Action"

3. **pg_type verification**: Ensure inferred types are correct

4. **Array formulas** (208 columns): Translate 208 array-formula columns to window functions
   - Most are linear regression (REGR_SLOPE) or standard deviation (STDDEV_SAMP)
   - Requires opening MA tab in Excel and reading formula bar

**Tools to help:**
- Open `C:\Ashok\Invest\Projects\Cluade\Tickers 2026-04-30.xlsx`, tab MA
- Hover over cells in JG..NO range to see formulas
- Compare with existing `etl/derive.py` implementations (e.g., `_derive_td_impl`) for patterns

### Phase 4: DDL Generation

Once the registry is ~95% complete:

```bash
python -m etl.generate_cat_ddl
```

This generates `db/14_drv_cat_tables.sql` with ~30 CREATE TABLE statements.

Review the DDL, then apply:

```bash
python -m db.init_db
```

### Phase 5: Per-Category Derive Functions

Add to `etl/derive.py`:

```python
def _derive_cat_table_impl(session, as_of_date, run_id, cat_table: str) -> int:
    """Generic per-category derive function."""
    session.execute(text(f"DELETE FROM {cat_table} WHERE as_of_date = :d"), {"d": as_of_date})
    
    dml = ma_codegen.build_dml(session, cat_table)
    if not dml:
        return 0
    
    result = session.execute(text(dml), {"d": as_of_date, "run_id": run_id})
    return result.rowcount

# Wire into derive_all() in the same location as derive_tw, derive_etf, etc.:
for cat_table in ma_codegen.get_all_cat_tables(session):
    counts[cat_table] = _wrap(cat_table, 
        lambda s, d, rid, c=cat_table: _derive_cat_table_impl(s, d, rid, c)
    )(session, as_of_date, run_id)
```

### Phase 6: Parity Testing (§10)

After each drv_cat_* table is complete, run parity tests:

```bash
pytest tests/test_cat_parity.py -k drv_cat_price
```

This compares DB values against Excel for 20 representative symbols × 5 dates.

Any divergence = bug in source_expr or source_table join. Fix the registry, regenerate, re-run.

### Phase 7: drv2_* Views (§6)

Once all drv_cat_* tables are seeded, generate drv2_* views:

```bash
python -m etl.generate_drv2_views
```

Creates `db/15_drv2_views.sql` with ~14 VIEWs that pivot the drv_cat_* tables back by source.

### Phase 8: Thin drv_ma Rebuild (§7)

Replace the wide drv_ma with a thin VIEW or materialized table:

```sql
CREATE OR REPLACE VIEW drv_ma AS
SELECT  i.as_of_date, i.symbol, i.description, i.sector,
        p.last_price, p.prev_close, ...
FROM drv_cat_identity i
LEFT JOIN drv_cat_price p USING (as_of_date, symbol)
LEFT JOIN drv_cat_risk_range rr USING (as_of_date, symbol)
...
```

### Phase 9: Rules Engine Wiring (§8)

Rewrite ref_trig_atomic_rule.ma_column_name:
- From: `'drv_ma.rsi'`
- To: `'drv_cat_atomic_input.rsi'`

Update `_derive_stks_impl` to read from drv_cat_atomic_input directly (1 table join vs 600+ columns).

### Phase 10: API & UI Updates (§10)

- Add `GET /api/ma/columns?stage=<stage>&concept=<concept>` endpoint
- Add `/api/data/drv_cat_<x>` browser endpoints
- Wire Rules Manager typeahead to use registry
- Add stage-based Cockpit drawer visualization

---

## Quick Reference: Files and Responsibilities

| File | Purpose |
|------|---------|
| `db/17_ref_ma_columns.sql` | Registry table |
| `etl/seed_ref_ma_columns.py` | Load v2 CSV → registry |
| `etl/enrich_ref_ma_columns.py` | Merge full/seed CSVs → registry |
| `etl/ma_codegen.py` | DDL/DML generators (core) |
| `etl/generate_cat_ddl.py` | Produce db/14_drv_cat_tables.sql |
| `etl/generate_drv2_views.py` | Produce db/15_drv2_views.sql (TODO) |
| `db/14_drv_cat_tables.sql` | Generated DDL (auto-created) |
| `db/15_drv2_views.sql` | Generated VIEW definitions (auto-created) |
| `db/16_thin_drv_ma.sql` | Thin drv_ma VIEW (manual) |
| `etl/derive.py` | Add per-cat functions + wire into derive_all() |
| `tests/test_cat_parity.py` | Parity testing (per-table) |

## Command Cheatsheet

```bash
# Full one-time setup
python -m db.init_db                      # Create schema
python -m etl.seed_ref_ma_columns         # Populate registry
python -m etl.enrich_ref_ma_columns       # Add full/seed data

# After manual registry work
python -m etl.generate_cat_ddl            # Create db/14_drv_cat_tables.sql
python -m db.init_db                      # Apply DDLs

# Per-category testing
pytest tests/test_cat_parity.py -k drv_cat_price   # Parity test

# Full derivation run
python -m etl.tickers_initial_load        # Re-derive latest date
```

---

## Common Issues & Fixes

### "ref_ma_columns is empty"
Run `python -m etl.seed_ref_ma_columns` first.

### "No drv_cat_* tables found"
The registry is empty or the query is wrong. Check `SELECT COUNT(*) FROM ref_ma_columns WHERE drv_cat_table != 'drv_cat_separator'`.

### Parity test failures
1. Check the source_expr in the registry for that column
2. Verify the source_table is correct
3. Look at the Excel formula and try to understand what it's computing
4. Update source_expr and regenerate DDL/DML

### "table drv_cat_bollinger does not exist"
Run `python -m db.init_db` to apply the generated DDLs.

---

## Next: Manual Registry Work

The registry infrastructure is in place. The next step is to manually enrich ~300 entries with source_expr and display_label. 

Start with the smallest drv_cat_* tables (drv_cat_identity, drv_cat_macd, drv_cat_earnings) to get familiar with the pattern, then scale up.

See BUILD_INSTRUCTIONS_drv2_and_drv_cat.md §12 for array-formula translation guidance.
