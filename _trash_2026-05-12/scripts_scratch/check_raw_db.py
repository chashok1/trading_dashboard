#!/usr/bin/env python
"""Check raw database values."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    result = s.execute(text("""
        SELECT symbol, triggered_group_ids, triggered_composite_ids
        FROM drv_stks
        WHERE as_of_date = '2026-05-06'
        LIMIT 5
    """)).fetchall()

    for row in result:
        symbol, groups, composites = row
        print(f"\n{symbol}:")
        print(f"  groups raw: {repr(groups)}")
        print(f"  groups type: {type(groups)}")
        if groups:
            print(f"  groups content: {groups}")
        print(f"  composites raw: {repr(composites[:50]) if composites else None}")
