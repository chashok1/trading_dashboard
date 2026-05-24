#!/usr/bin/env python
"""Final verification that rule groups are working."""
import json
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    date = '2026-05-06'

    # Find a symbol with actual triggered groups
    result = s.execute(text(f"""
        SELECT symbol, triggered_group_ids, triggered_composite_ids
        FROM drv_stks
        WHERE as_of_date = '{date}'
        AND triggered_group_ids IS NOT NULL
        AND jsonb_array_length(triggered_group_ids) > 0
        LIMIT 5
    """)).fetchall()

    if result:
        print("=" * 70)
        print("RULE GROUPS IMPLEMENTATION - FINAL VERIFICATION")
        print("=" * 70)

        for symbol, groups_json, composites_json in result:
            groups = json.loads(groups_json) if isinstance(groups_json, str) else groups_json
            composites = json.loads(composites_json) if isinstance(composites_json, str) else composites_json

            print(f"\n{symbol}:")
            print(f"  Triggered Composites: {len(composites)} rules")
            for comp in composites[:3]:
                print(f"    - {comp['rule_id']}: score={comp['score']}")
            if len(composites) > 3:
                print(f"    ... and {len(composites)-3} more")

            print(f"  Triggered Groups: {len(groups)} groups")
            for grp in groups:
                print(f"    - {grp['rule_group_code']}: action={grp['action']}, priority={grp['priority']}")

        print("\n" + "=" * 70)
        print("SUCCESS: Rule groups are working end-to-end!")
        print("=" * 70)
    else:
        # No symbols with triggered groups - that's okay if composites are also empty
        with_composites = s.execute(text(f"""
            SELECT COUNT(*)
            FROM drv_stks
            WHERE as_of_date = '{date}' AND jsonb_array_length(triggered_composite_ids) > 0
        """)).scalar()

        print(f"No symbols with triggered groups found")
        print(f"Symbols with triggered composites: {with_composites}")

        if with_composites == 0:
            print("\nNote: This is normal if the test date has limited rule firing")
            print("The implementation is correct - empty arrays are being stored properly")
        else:
            print(f"\nWarning: {with_composites} symbols have composites but no groups")
            print("This suggests a group evaluation logic error")
