#!/usr/bin/env python3
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as session:
    # Check if ref_sector exists
    result = session.execute(text("""
        SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'ref_sector')
    """)).scalar()
    print(f"ref_sector exists: {result}")

    if result:
        # Get columns
        cols = session.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'ref_sector'
            ORDER BY ordinal_position
        """)).scalars().all()
        print(f"Columns in ref_sector: {cols}")

        # Get row count
        count = session.execute(text("SELECT COUNT(*) FROM ref_sector")).scalar()
        print(f"Row count: {count}")
