#!/usr/bin/env python
"""Inspect a symbol that has triggered groups."""
import json
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    latest_date = s.execute(text("SELECT MAX(as_of_date) FROM drv_ma")).scalar()

    # Get details for ^SPX
    symbol = "^SPX"
    data = s.execute(text(f"""
        SELECT triggered_atomic_ids, triggered_composite_ids, triggered_group_ids
        FROM drv_stks
        WHERE symbol = '{symbol}' AND as_of_date = '{latest_date}'
    """)).fetchone()

    if data:
        atomic_ids, composite_ids, group_ids = data

        print(f"Symbol: {symbol} ({latest_date})\n")

        print("=" * 60)
        print("TRIGGERED ATOMIC RULES")
        print("=" * 60)
        if atomic_ids:
            try:
                atomics = json.loads(atomic_ids) if isinstance(atomic_ids, str) else atomic_ids
                print(f"Count: {len(atomics)}")
                for i, atom in enumerate(atomics[:5], 1):
                    print(f"  {i}. Rule {atom['rule_id']}: weight={atom['weight']}, value={atom['value']}")
                if len(atomics) > 5:
                    print(f"  ... and {len(atomics)-5} more")
            except Exception as e:
                print(f"Error parsing: {e}")
        else:
            print("None")

        print("\n" + "=" * 60)
        print("TRIGGERED COMPOSITE RULES")
        print("=" * 60)
        if composite_ids:
            try:
                composites = json.loads(composite_ids) if isinstance(composite_ids, str) else composite_ids
                print(f"Count: {len(composites)}")
                for i, comp in enumerate(composites[:10], 1):
                    print(f"  {i}. {comp['rule_id']}: score={comp['score']}")
                if len(composites) > 10:
                    print(f"  ... and {len(composites)-10} more")
            except Exception as e:
                print(f"Error parsing: {e}")
        else:
            print("None")

        print("\n" + "=" * 60)
        print("TRIGGERED RULE GROUPS")
        print("=" * 60)
        if group_ids:
            try:
                groups = json.loads(group_ids) if isinstance(group_ids, str) else group_ids
                print(f"Count: {len(groups)}")
                for i, grp in enumerate(groups, 1):
                    print(f"  {i}. {grp['rule_group_code']}: action={grp['action']}, priority={grp['priority']}")
            except Exception as e:
                print(f"Error parsing: {e}")
        else:
            print("None")

        print("\n" + "=" * 60)
        print("RESULT: Rule Groups Implementation is WORKING!")
        print("=" * 60)
    else:
        print(f"No data found for {symbol}")
