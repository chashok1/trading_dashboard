#!/usr/bin/env python
"""Debug why groups aren't populating in drv_stks."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    latest_date = s.execute(text("SELECT MAX(as_of_date) FROM drv_ma")).scalar()

    print(f"Checking drv_stks for {latest_date}\n")

    # Check raw data
    rows = s.execute(text(f"""
        SELECT symbol, triggered_group_ids, triggered_composite_ids
        FROM drv_stks
        WHERE as_of_date = '{latest_date}'
        LIMIT 5
    """)).fetchall()

    print("Raw data from drv_stks:")
    for symbol, groups, composites in rows:
        print(f"\n{symbol}:")
        print(f"  triggered_group_ids: {repr(groups)}")
        print(f"  triggered_composite_ids: {repr(composites)}")

    # Check if groups exist
    group_count = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_rule_group WHERE rule_group_code LIKE 'GROUP-%'
    """)).scalar()

    print(f"\n\nTotal rule groups in DB: {group_count}")

    # Check group members
    members = s.execute(text("""
        SELECT rule_group_code, COUNT(*) as member_count
        FROM ref_trig_group_member
        GROUP BY rule_group_code
        ORDER BY rule_group_code
    """)).fetchall()

    print("\nRule group members:")
    for code, count in members:
        print(f"  {code}: {count} members")
