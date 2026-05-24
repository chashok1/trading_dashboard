#!/usr/bin/env python
"""List all composite rules in the system."""
from sqlalchemy import text
from etl.db import session_scope

with session_scope() as s:
    # Get all unique composite rules and their categories
    rules = s.execute(text("""
        SELECT DISTINCT
            composite_rule_code,
            category,
            intent_text
        FROM ref_trig_composite_mapping
        WHERE deprecated_at IS NULL
        ORDER BY composite_rule_code
    """)).fetchall()

    print(f"Found {len(rules)} active composite rules:\n")
    for code, cat, intent in rules:
        print(f"  {code:30} | {cat:15} | {intent}")

    # Also check if there are any action codes in ref_rule_desc
    print("\n" + "=" * 80)
    print("Action codes from ref_rule_desc:\n")

    actions = s.execute(text("""
        SELECT DISTINCT rule_code, rule_desc
        FROM ref_rule_desc
        ORDER BY rule_code
    """)).fetchall()

    for code, desc in actions[:20]:  # First 20
        print(f"  {code:10} | {desc}")
