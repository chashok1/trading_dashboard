# How to Wire drv_cat_* Derives into derive.py

This template shows where and how to add the per-category derive functions.

## Location in derive.py

Add this code in the `derive_all()` function, after the existing `derive_tw`, `derive_etf`, `derive_ii`, `derive_ssh`, `derive_sss`, `derive_ps` calls and before the return statement.

### Step 1: Import at the top of derive.py

```python
from etl import ma_codegen
```

### Step 2: Add the generic per-category function

Add this function anywhere in the module (e.g., before `derive_all()`):

```python
def _derive_cat_table_impl(session, as_of_date: date, run_id: int, cat_table: str) -> int:
    """Generic per-category table deriver (registry-driven).
    
    All drv_cat_* tables use the same pattern:
    1. DELETE existing rows for this as_of_date
    2. Generate INSERT...SELECT from registry
    3. Execute and return row count
    """
    session.execute(
        text(f"DELETE FROM {cat_table} WHERE as_of_date = :d"),
        {"d": as_of_date}
    )

    dml = ma_codegen.build_dml(session, cat_table)
    if not dml:
        # No columns for this table (shouldn't happen)
        return 0

    result = session.execute(
        text(dml),
        {"d": as_of_date, "run_id": run_id}
    )
    
    rowcount = result.rowcount or 0
    return rowcount
```

### Step 3: Wire into derive_all()

In the `derive_all()` function, after the line `counts['drv_sss'] = _wrap(...)`:

```python
    # Derive all drv_cat_* tables from the registry
    # These organize MA columns by concept (bollinger, rsi, macd, etc.)
    # rather than by source (Y, TL, TD, etc.)
    for cat_table in ma_codegen.get_all_cat_tables(session):
        # Create a closure to capture cat_table for the lambda
        def make_deriver(table_name: str):
            return lambda s, d, rid: _derive_cat_table_impl(s, d, rid, table_name)
        
        counts[cat_table] = _wrap(cat_table, make_deriver(cat_table))(
            session, as_of_date, run_id
        )
```

### Full Example

Here's what the code looks like in context:

```python
def derive_all(session: Session, as_of_date: date, run_id: int = None) -> dict:
    """Rebuild all derived tables for one snapshot date.
    
    Order matters: later stages read earlier stages.
    Returns dict of {table_name: row_count}.
    """
    if not run_id:
        run_id = _new_run_id(session)

    counts = {}

    # Existing derives (unchanged)
    counts["drv_tl"] = _wrap("drv_tl", lambda s, d, rid: _derive_tl_impl(s, d))(
        session, as_of_date, run_id
    )
    counts["drv_td"] = _wrap("drv_td", lambda s, d, rid: _derive_td_impl(s, d))(
        session, as_of_date, run_id
    )
    # ... (rest of existing derives: tw, call, etf, ii, ssh, ssl, sss, ps)

    # NEW: drv_cat_* tables (category-organized columns)
    print(f"\n→ Deriving drv_cat_* tables (registry-driven)...")
    for cat_table in sorted(ma_codegen.get_all_cat_tables(session)):
        def make_deriver(table_name: str):
            return lambda s, d, rid: _derive_cat_table_impl(s, d, rid, table_name)

        rowcount = _wrap(cat_table, make_deriver(cat_table))(
            session, as_of_date, run_id
        )
        counts[cat_table] = rowcount

    # Existing downstream tables (drv_ma, drv_dash, drv_dash_summary, drv_trig, drv_missing_symbols)
    # These will need to be updated to read from drv_cat_* instead of drv_*
    # That's Phase 8-9 of the implementation
    
    print(f"\n✓ Derive complete: {as_of_date} ({sum(counts.values())} rows)")
    return counts
```

## Testing

After adding the wiring, test it:

```bash
python -m etl.derive_all 2026-04-30
```

This should derive all drv_cat_* tables for April 30, 2026. Check that row counts are correct (should equal symbol count for most tables, since (as_of_date, symbol) is the PK).

## Debugging

If a drv_cat_* derive fails:

1. Check that the registry has been seeded: `SELECT COUNT(*) FROM ref_ma_columns`
2. Check that the drv_cat_* table exists: `\dt drv_cat_<name>`
3. Run the generated DML manually to see the SQL error
4. Fix the registry (source_expr, source_table), regenerate, retry

## Progress Tracking

Once this is wired, you can run the parity tests (§10 of BUILD_INSTRUCTIONS):

```bash
pytest tests/test_cat_parity.py -k drv_cat_price
pytest tests/test_cat_parity.py -k drv_cat_bollinger
# ... etc for each table
```

Each passing test validates that one drv_cat_* table is parity-complete with Excel.
