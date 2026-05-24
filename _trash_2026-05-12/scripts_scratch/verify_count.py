#!/usr/bin/env python
"""Verify the count query logic."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    date = '2026-05-06'

    # Simple queries
    total = s.execute(text(f"SELECT COUNT(*) FROM drv_stks WHERE as_of_date = '{date}'")).scalar()
    print(f"Total rows: {total}")

    # Check groups column directly
    null_count = s.execute(text(f"""
        SELECT COUNT(*) FROM drv_stks
        WHERE as_of_date = '{date}' AND triggered_group_ids IS NULL
    """)).scalar()

    not_null_count = s.execute(text(f"""
        SELECT COUNT(*) FROM drv_stks
        WHERE as_of_date = '{date}' AND triggered_group_ids IS NOT NULL
    """)).scalar()

    print(f"\ntriggered_group_ids:")
    print(f"  IS NULL: {null_count}")
    print(f"  IS NOT NULL: {not_null_count}")
    print(f"  Total: {null_count + not_null_count}")

    # Try CASE WHEN
    case_count = s.execute(text(f"""
        SELECT COUNT(CASE WHEN triggered_group_ids IS NOT NULL THEN 1 END)
        FROM drv_stks WHERE as_of_date = '{date}'
    """)).scalar()

    print(f"\nCASE WHEN count: {case_count}")

    # Check if maybe the column is the problem
    print(f"\nChecking column definition:")
    cols = s.execute(text("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'drv_stks' AND column_name = 'triggered_group_ids'
    """)).fetchall()

    for name, dtype, nullable in cols:
        print(f"  {name}: {dtype}, nullable={nullable}")

    # Get actual raw values
    print(f"\nSample raw values:")
    samples = s.execute(text(f"""
        SELECT symbol, triggered_group_ids FROM drv_stks
        WHERE as_of_date = '{date}'
        LIMIT 3
    """)).fetchall()

    for sym, val in samples:
        print(f"  {sym}: {repr(val)} (type={type(val).__name__})")
