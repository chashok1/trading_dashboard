#!/usr/bin/env python
"""Check actual JSON content stored in the column."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    date = '2026-05-06'

    # Get raw text representation
    result = s.execute(text(f"""
        SELECT symbol,
               triggered_group_ids::text as groups_text,
               triggered_composite_ids::text as composites_text
        FROM drv_stks
        WHERE as_of_date = '{date}'
        LIMIT 10
    """)).fetchall()

    print("Raw text representation of JSONB columns:\n")
    for symbol, groups_text, composites_text in result:
        print(f"{symbol}:")
        print(f"  groups: {repr(groups_text)}")
        print(f"  composites: {repr(composites_text)}")

    # Get JSON info
    print("\n\nJSON array/object info:")
    info = s.execute(text(f"""
        SELECT symbol,
               jsonb_typeof(triggered_group_ids) as group_type,
               jsonb_array_length(triggered_group_ids) as group_length,
               jsonb_typeof(triggered_composite_ids) as composite_type
        FROM drv_stks
        WHERE as_of_date = '{date}'
        LIMIT 5
    """)).fetchall()

    for row in info:
        sym, gtype, glen, ctype = row
        print(f"  {sym}: groups type={gtype} length={glen}, composites type={ctype}")
