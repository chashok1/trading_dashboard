#!/usr/bin/env python
"""Check the actual schema of drv_stks table."""
from sqlalchemy import text, inspect
from etl.db import get_engine

engine = get_engine()

with engine.connect() as conn:
    # Get column info
    cols = conn.execute(text("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'drv_stks'
        ORDER BY ordinal_position
    """)).fetchall()

    print("drv_stks columns:")
    for col_name, data_type, is_nullable in cols:
        if 'trigger' in col_name or 'group' in col_name or 'composite' in col_name:
            print(f"  {col_name:30} {data_type:10} nullable={is_nullable}")

    # Check if column exists
    has_group_ids = any(c[0] == 'triggered_group_ids' for c in cols)
    print(f"\ntriggered_group_ids exists: {has_group_ids}")

    # Check some sample data
    print("\nSample data from drv_stks:")
    sample = conn.execute(text("""
        SELECT symbol, triggered_group_ids, triggered_composite_ids FROM drv_stks LIMIT 3
    """)).fetchall()

    for sym, grp, comp in sample:
        print(f"  {sym}: groups={repr(grp)}, composites={repr(comp)}")
