#!/usr/bin/env python3
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as session:
    result = session.execute(text("""
        SELECT drv_cat_table, column_name, COUNT(*) as cnt
        FROM ref_ma_columns
        WHERE drv_cat_table IS NOT NULL AND drv_cat_table != 'drv_cat_separator'
        GROUP BY drv_cat_table, column_name
        HAVING COUNT(*) > 1
        ORDER BY drv_cat_table
    """)).mappings().all()

    if result:
        print("Duplicate columns found:")
        for row in result:
            print(f"  {row['drv_cat_table']}: {row['column_name']} (count={row['cnt']})")
    else:
        print("No duplicates found")

    # Also check for 'symbol' column conflicts
    result2 = session.execute(text("""
        SELECT drv_cat_table, COUNT(*) as cnt
        FROM ref_ma_columns
        WHERE drv_cat_table IS NOT NULL AND drv_cat_table != 'drv_cat_separator' AND column_name = 'symbol'
        GROUP BY drv_cat_table
    """)).mappings().all()

    if result2:
        print("\nTables with 'symbol' column (conflicts with PK):")
        for row in result2:
            print(f"  {row['drv_cat_table']}")
