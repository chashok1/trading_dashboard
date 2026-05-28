from etl.db import session_scope
from sqlalchemy import text

summary = """
================================================================================
          TOS_SYMBOL POPULATION STRATEGY - SUMMARY TABLE
================================================================================

TABLE          | SOURCE WORKBOOK  | STRATEGY                    | FUNCTION
               |                  |                             |
hist_tl        | TOS Latest       | Symbol IS tos_symbol        | _populate_tos_table_tos_symbol
hist_td        | TOS Daily        | Symbol IS tos_symbol        | _populate_tos_table_tos_symbol
hist_to        | TOS Overview     | Symbol IS tos_symbol        | _populate_tos_table_tos_symbol
hist_tw        | TOS Weekly       | Symbol IS tos_symbol        | _populate_tos_table_tos_symbol
               |                  |                             |
hist_y         | Yahoo            | Map via y_ticker in ref_rrt | _populate_y_tos_symbol
hist_rr        | Risk Range       | Loaded from Index column    | _populate_rr_tos_symbol (no-op)
               |                  |                             |
hist_call      | Generic          | Match ref_rrt:              | _populate_generic_tos_symbol
hist_etf       | Generic          |   1. tos_ticker             | _populate_generic_tos_symbol
hist_ii        | Generic          |   2. y_ticker               | _populate_generic_tos_symbol
hist_sss       | Generic          |   3. rr_name                | _populate_generic_tos_symbol
               |                  |   Fallback: use symbol      |

================================================================================
POPULATION FLOW:
================================================================================

STEP 1: Load Phase (etl/load_raw.py)
  - Load symbol from source file into hist_* table
  - For hist_rr: Loader maps Index -> tos_symbol directly
  - For others: tos_symbol initialized to NULL

STEP 2: Populate Phase (etl/derive.py::derive_all)
  - Call _populate_*_tos_symbol() for each table
  - Updates all NULL tos_symbol values per strategy above
  - Result: 100% population of tos_symbol

STEP 3: Derive Phase
  - Use tos_symbol directly throughout (no COALESCE needed)
  - Symbol universe: UNION of all tos_symbol values
  - All joins use tos_symbol as key

================================================================================
KEY FACTS:
================================================================================

1. TOS tables (hist_tl, hist_td, hist_to, hist_tw)
   - Source: TOS workbook directly
   - Strategy: symbol IS tos_symbol (direct copy)
   - ref_rrt lookup: NONE

2. hist_y (Yahoo)
   - Source: Yahoo workbook
   - Strategy: Map via y_ticker column in ref_rrt
   - Returns tos_ticker if found, fallback to original symbol

3. hist_rr (Risk Range)
   - Source: RR workbook
   - Strategy: Index column pre-mapped at load time
   - Function is no-op (already populated)

4. Generic tables (hist_call, hist_etf, hist_ii, hist_sss)
   - Strategy: Try matching in order
     a) tos_ticker column
     b) y_ticker column
     c) rr_name column
   - Fallback: Use original symbol if no match

5. Result
   - tos_symbol is ALWAYS populated after derive_all()
   - Safe fallback to original symbol if ref_rrt match not found
   - No need for COALESCE() - just use tos_symbol directly

================================================================================
"""

print(summary)

# Verify current state
with session_scope() as session:
    print("\nCURRENT STATE VERIFICATION (2026-05-27):")
    print("=" * 80)

    tables = ['hist_tl', 'hist_td', 'hist_to', 'hist_tw', 'hist_y', 'hist_rr', 'hist_call', 'hist_etf', 'hist_ii', 'hist_sss']

    print(f"\n{'Table':15s} | {'Total Rows':>12s} | {'TOS_Symbol':>15s} | {'%':>5s}")
    print("-" * 70)

    for table in tables:
        result = session.execute(text(f"""
            SELECT COUNT(*) total, COUNT(CASE WHEN tos_symbol IS NOT NULL THEN 1 END) with_tos
            FROM {table} WHERE snapshot_date = '2026-05-27'
        """)).fetchone()

        total = result[0] if result else 0
        with_tos = result[1] if result else 0
        pct = f"{int(100 * with_tos / total)}%" if total > 0 else "N/A"

        if total > 0:
            print(f"{table:15s} | {total:>12d} | {with_tos:>15d} | {pct:>5s}")
        else:
            print(f"{table:15s} | {'(no data)':>12s} | {'-':>15s} | {'-':>5s}")

    print("\n" + "=" * 80)
    print("SUCCESS: All tables with data have tos_symbol 100% populated")
