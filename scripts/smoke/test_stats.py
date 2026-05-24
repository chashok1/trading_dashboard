#!/usr/bin/env python
"""Quick test of the stats endpoint."""
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    # Check if any tables exist
    result = s.execute(text("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema='public'
    """)).scalar()
    print(f"Total tables in database: {result}")

    # List first 10 tables
    tables = s.execute(text("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema='public'
        ORDER BY table_name
        LIMIT 10
    """)).scalars().all()
    print(f"\nFirst 10 tables: {tables}")

    # Try to count rows in ref_sector if it exists
    try:
        count = s.execute(text("SELECT COUNT(*) FROM ref_sector")).scalar()
        print(f"\nref_sector has {count} rows")
    except Exception as e:
        print(f"\nref_sector error: {e}")
