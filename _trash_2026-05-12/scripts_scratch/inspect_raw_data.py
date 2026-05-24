#!/usr/bin/env python
"""Inspect raw drv_stks data."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    rows = s.execute(text("""
        SELECT symbol,
               triggered_composite_ids IS NULL as comp_is_null,
               triggered_group_ids IS NULL as group_is_null,
               triggered_composite_ids,
               triggered_group_ids
        FROM drv_stks
        WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_stks)
        LIMIT 10
    """)).fetchall()

    print("Raw data inspection:\n")
    for row in rows:
        sym, comp_null, grp_null, comp_val, grp_val = row
        print(f"{sym}:")
        print(f"  composite_ids NULL: {comp_null}, value: {repr(comp_val)}")
        print(f"  group_ids NULL: {grp_null}, value: {repr(grp_val)}")
