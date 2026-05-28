# Symbol Normalization Strategy (tos_symbol)

## Overview

All symbols across all source feeds are normalized to TOS (thinkOrSwim) symbols. This normalization happens in two phases:
1. **Populate Phase** (during ETL load/derive): `tos_symbol` column is populated in all `hist_*` tables
2. **Derive Phase**: All `drv_*` functions use `tos_symbol` as the primary symbol key

## Why tos_symbol?

Different source feeds use different symbol formats:
- **TOS tables** (hist_tl, hist_td, hist_to, hist_tw): Use TOS ticker symbols natively
- **Yahoo** (hist_y): Uses Yahoo symbols (usually same as TOS but sometimes different)
- **Risk Range** (hist_rr): Uses RR names (e.g., "RR_AAPL") mapped to TOS symbols
- **Generic tables** (hist_call, hist_etf, hist_ii, hist_sss): May use any format
- **Account data** (hist_cs, hist_cst, hist_f): Use standard stock tickers

Using `tos_symbol` as the common key ensures:
- All symbol-based joins work correctly regardless of source
- Symbol universe is consistent across all derives
- No data loss from unmapped symbols (they're tracked as warnings)

## Populate Phase Strategy

The populate phase (`derive_all()`) runs before any derives and fills `tos_symbol` for all tables:

### GROUP 1: TOS Tables (hist_tl, hist_td, hist_to, hist_tw)
- **Strategy**: Direct copy — `symbol IS tos_symbol`
- **Function**: `_populate_tos_table_tos_symbol()`
- **Implementation**: `UPDATE hist_* SET tos_symbol = symbol WHERE tos_symbol IS NULL`

### GROUP 2: Yahoo (hist_y)
- **Strategy**: Map via `ref_rrt` WHERE `y_ticker = symbol`
- **Function**: `_populate_y_tos_symbol()`
- **Fallback**: If not found in ref_rrt, use original symbol
- **Result**: `tos_symbol` is always populated (never NULL)

### GROUP 3: Risk Range (hist_rr)
- **Strategy**: Pre-mapped at load time from RR Index column
- **Function**: `_populate_rr_tos_symbol()` (no-op, already done)
- **Fallback**: If symbol not in ref_rrt, keep `tos_symbol` NULL and create warning
- **Result**: Missing mappings are flagged for manual intervention

### GROUP 4: Generic Tables (hist_call, hist_etf, hist_ii, hist_sss, hist_cs, hist_cst)
- **Strategy**: Smart matching in priority order
  1. Try `ref_rrt` WHERE `tos_ticker = symbol`
  2. Try `ref_rrt` WHERE `y_ticker = symbol`
  3. Try `ref_rrt` WHERE `rr_name = symbol`
  4. If no match: use original symbol (fallback)
- **Function**: `_populate_generic_tos_symbol()`
- **Result**: `tos_symbol` is always populated (never NULL)

## Derive Phase Usage

### In SQL Queries

**Symbol Universe CTE** — use `tos_symbol` from all sources:
```sql
syms AS (
    SELECT DISTINCT s FROM (
        SELECT ticker AS s FROM ref_sector
        UNION SELECT tos_symbol FROM hist_tl WHERE snapshot_date <= :d
        UNION SELECT tos_symbol FROM hist_y WHERE snapshot_date <= :d
        UNION SELECT tos_symbol FROM hist_call WHERE snapshot_date <= :d
        -- ... all sources select tos_symbol
    ) u WHERE s IS NOT NULL
)
```

**Per-source CTEs** — extract `tos_symbol` as the symbol key:
```sql
tl AS (
    SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol AS symbol,
           h.snapshot_date, h.last_price, ...
    FROM hist_tl h
    WHERE h.snapshot_date <= :d
    ORDER BY h.tos_symbol, h.snapshot_date DESC
)
```

**Joins** — use `tos_symbol` from normalized CTEs:
```sql
FROM syms s
LEFT JOIN tl ON tl.symbol = s.s           -- tl.symbol comes from tos_symbol
LEFT JOIN dq ON dq.tos_symbol = s.s       -- drv_quote uses tos_symbol
LEFT JOIN td ON td.symbol = s.s           -- td.symbol comes from tos_symbol
```

### In Output Rows

All derive output must include both `symbol` and `tos_symbol`:
```python
{
    "as_of_date": as_of_date,
    "symbol": r["symbol"],              # Original symbol (for backwards compat)
    "tos_symbol": r["tos_symbol"],      # Normalized TOS symbol
    "description": r["description"],
    # ... other fields
}
```

This allows:
- **Backwards compatibility**: Old code reading `symbol` still works
- **New code normalization**: New code uses `tos_symbol` as primary key
- **Traceability**: Easy to see what the original symbol was

## Implementation Checklist

When adding a new derive function:

1. **Symbol Universe**
   - [ ] Include `tos_symbol` selections from all `hist_*` sources
   - [ ] Don't use `COALESCE(tos_symbol, symbol)` — populate phase guarantees population

2. **Per-source CTEs**
   - [ ] Use `DISTINCT ON (tos_symbol)` instead of `symbol`
   - [ ] Select `tos_symbol AS symbol` to normalize column names
   - [ ] Order by `tos_symbol` consistently

3. **Joins**
   - [ ] Join on normalized symbol keys from CTEs
   - [ ] Use `symbol` column from CTEs (which actually contains `tos_symbol`)

4. **Output Rows**
   - [ ] Include `symbol` and `tos_symbol` fields
   - [ ] Set both from the normalized symbol value (usually from syms CTE)

5. **Group/Order Operations**
   - [ ] GROUP BY and ORDER BY use `tos_symbol`, not `symbol`
   - [ ] Portfolio aggregations (held positions) use `tos_symbol`

## Example: Adding a New Derive

```python
def _derive_example_impl(session: Session, as_of_date: date, run_id: int) -> int:
    """Example derive using tos_symbol normalization."""
    
    sql = text("""
    INSERT INTO drv_example (as_of_date, symbol, tos_symbol, value)
    WITH syms AS (
        SELECT DISTINCT s FROM (
            SELECT tos_symbol AS s FROM hist_example WHERE snapshot_date <= :d
            -- Add all relevant sources with tos_symbol
        ) WHERE s IS NOT NULL
    ),
    ex AS (
        SELECT DISTINCT ON (h.tos_symbol) h.tos_symbol AS symbol, h.value
        FROM hist_example h
        WHERE h.snapshot_date <= :d
        ORDER BY h.tos_symbol, h.snapshot_date DESC
    )
    SELECT (SELECT d FROM p) AS as_of_date, s.s, s.s,  -- symbol and tos_symbol both = s.s
           ex.value
    FROM syms s
    LEFT JOIN ex ON ex.symbol = s.s
    """)
    
    session.execute(text("DELETE FROM drv_example WHERE as_of_date = :d"), {"d": as_of_date})
    result = session.execute(sql, {"d": as_of_date})
    return result.rowcount or 0
```

## Database Schema

All tables have `tos_symbol` columns:
- **hist_* tables**: TEXT, indexed on (tos_symbol, snapshot_date) for performance
- **drv_* tables**: TEXT, indexed on tos_symbol for lookups and filtering
- **Portfolio tables** (hist_cs, hist_cst, hist_f): TEXT with same indexing

## Warnings

If a symbol cannot be mapped to `tos_symbol`:
- **GROUP 2-4 (Yahoo, Generic)**: Falls back to original symbol, no warning
- **GROUP 3 (RR)**: Stays NULL and creates error warning in `data-quality` screen

Check warnings if `drv_ma` has fewer symbols than expected.

## Migration History

- **2026-05-28**: Complete normalization of all derives to use tos_symbol
  - Updated: drv_quote, drv_ma, drv_dash, drv_stks, drv_missing_symbols, drv_trig, drv_cs_realized_gain
  - Added tos_symbol to all hist_* and drv_* tables
  - Created indexes for query performance
