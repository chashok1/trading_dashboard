#!/usr/bin/env python
"""Auto-create rule groups from composite rule action prefixes."""
import re
from sqlalchemy import text
from etl.db import session_scope
from etl.rule_groups import create_rule_group, add_group_member

# Map action prefix to (action_label, priority)
ACTION_MAP = {
    'SA': ('SA', 1),      # Sell All - highest priority
    'SS': ('SS', 2),      # Sell Some
    'STM': ('STM', 3),    # Sell To Market
    'SW': ('SW', 3),      # Sell Weak
    'BW': ('BW', 4),      # Buy Weak
    'BS': ('BS', 4),      # Buy Strong
    'BR': ('BR', 4),      # Buy Reversal
}

def extract_action_prefix(rule_code):
    """Extract action prefix from rule code like '899-SA-Trend-Breaks'."""
    # Format is typically NNN-CODE-Description
    parts = rule_code.split('-')
    if len(parts) >= 2:
        # Remove leading digits from second part if present
        code_part = parts[1]
        # Try to match known action codes
        for prefix in ['SA', 'SS', 'STM', 'SW', 'BW', 'BS', 'BR']:
            if code_part.startswith(prefix):
                return prefix
    return None

def main():
    print("=" * 60)
    print("Auto-Creating Rule Groups from Composite Rules")
    print("=" * 60)

    with session_scope() as s:
        # Fetch all composite rules
        rules = s.execute(text("""
            SELECT DISTINCT composite_rule_code
            FROM ref_trig_composite_mapping
            WHERE deprecated_at IS NULL
            ORDER BY composite_rule_code
        """)).fetchall()

        # Group rules by action
        rules_by_action = {}
        for (rule_code,) in rules:
            action = extract_action_prefix(rule_code)
            if action:
                if action not in rules_by_action:
                    rules_by_action[action] = []
                rules_by_action[action].append(rule_code)

        print(f"\nFound {len(rules)} composite rules in {len(rules_by_action)} action categories:")
        for action, rule_list in sorted(rules_by_action.items()):
            print(f"  {action}: {len(rule_list)} rules")

        # Create a rule group for each action
        print("\nCreating rule groups...")
        for action, rule_list in sorted(rules_by_action.items()):
            action_label, priority = ACTION_MAP.get(action, (action, 5))
            group_code = f"GROUP-{action}"

            # Delete existing group if present
            s.execute(text(f"DELETE FROM ref_trig_group_member WHERE rule_group_code = '{group_code}'"))
            s.execute(text(f"DELETE FROM ref_trig_rule_group WHERE rule_group_code = '{group_code}'"))

            # Create new group
            ok = create_rule_group(
                s,
                group_code,
                group_type="action",
                action_label=action_label,
                priority=priority,
                category="Auto-Generated",
                intent_text=f"All {action} rules grouped by action prefix"
            )

            if ok:
                print(f"  [OK] Created {group_code} with {len(rule_list)} members (priority={priority})")

                # Add all rules as members
                for seq, rule_code in enumerate(rule_list, 1):
                    ok = add_group_member(s, group_code, rule_code, "composite", "OR", seq)
                    if not ok:
                        print(f"      [FAIL] Failed to add {rule_code}")

                print(f"      [OK] Added {len(rule_list)} members with OR logic")
            else:
                print(f"  [FAIL] Failed to create {group_code}")

        s.commit()

    # Verify creation
    with session_scope() as s:
        groups = s.execute(text("""
            SELECT rule_group_code, action_label, priority, COUNT(*) as member_count
            FROM ref_trig_rule_group
            LEFT JOIN ref_trig_group_member USING (rule_group_code)
            WHERE rule_group_code LIKE 'GROUP-%'
            GROUP BY rule_group_code, action_label, priority
            ORDER BY priority
        """)).fetchall()

        print("\n" + "=" * 60)
        print("Created Rule Groups:")
        print("=" * 60)
        for group_code, action, priority, count in groups:
            print(f"  {group_code:15} {action:5} priority={priority} ({count} members)")

        return True

if __name__ == "__main__":
    try:
        if main():
            print("\n[OK] Rule group creation complete")
        else:
            print("\n[FAIL] Rule group creation failed")
            exit(1)
    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
