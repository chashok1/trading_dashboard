#!/usr/bin/env python
"""Test rule group evaluation directly."""
from sqlalchemy import text
from etl.db import session_scope
from etl.rule_groups import eval_rule_group

with session_scope() as s:
    # Get a sample composite rule that might fire
    composite = s.execute(text("""
        SELECT composite_rule_code FROM ref_trig_composite_mapping
        LIMIT 1
    """)).scalar()

    print(f"Testing with composite rule: {composite}")

    # Test 1: Directly evaluate a group with the composite firing
    print("\nTest 1: GROUP-SA with SA composite triggering")
    composite_results = {composite: True}

    # Check if 899-SA-Trend-Breaks is in GROUP-SA
    is_member = s.execute(text("""
        SELECT COUNT(*) FROM ref_trig_group_member
        WHERE rule_group_code = 'GROUP-SA' AND member_code = :code
    """), {"code": composite}).scalar()

    if is_member > 0:
        print(f"  {composite} IS in GROUP-SA")
        triggered, action, priority = eval_rule_group(s, "GROUP-SA", {composite: True})
        print(f"  Result: triggered={triggered}, action={action}, priority={priority}")
    else:
        print(f"  {composite} is NOT in GROUP-SA")

    # Test 2: Check what composites are actually in GROUP-SA
    print("\nTest 2: Composites in GROUP-SA")
    members = s.execute(text("""
        SELECT member_code FROM ref_trig_group_member
        WHERE rule_group_code = 'GROUP-SA'
    """)).fetchall()

    print(f"  GROUP-SA has {len(members)} members:")
    for (code,) in members:
        print(f"    {code}")

        # Test evaluating this member
        triggered, action, priority = eval_rule_group(s, "GROUP-SA", {code: True})
        print(f"      -> With {code}=True: triggered={triggered}, action={action}, priority={priority}")

    # Test 3: Check overall GROUP evaluation
    print("\nTest 3: Evaluating all auto-generated groups")
    groups = s.execute(text("""
        SELECT rule_group_code, action_label, priority FROM ref_trig_rule_group
        WHERE rule_group_code LIKE 'GROUP-%'
    """)).fetchall()

    for group_code, action, priority in groups:
        # Get all members
        members = s.execute(text("""
            SELECT member_code FROM ref_trig_group_member
            WHERE rule_group_code = :code AND deprecated_at IS NULL
        """), {"code": group_code}).fetchall()

        if members:
            # Test with first member true
            first_member = members[0][0]
            composite_results = {first_member: True}
            triggered, ret_action, ret_priority = eval_rule_group(s, group_code, composite_results)
            print(f"  {group_code}: with {first_member}=True -> triggered={triggered}")
        else:
            print(f"  {group_code}: NO MEMBERS!")
