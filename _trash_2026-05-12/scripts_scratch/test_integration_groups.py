#!/usr/bin/env python
"""Integration test: Create rule group, trigger composites, verify group fires in drv_stks."""
import json
from sqlalchemy import text
from etl.db import session_scope
from etl.rule_groups import create_rule_group, add_group_member, eval_rule_group
from etl.derive import derive_stks

def test_end_to_end():
    """Full integration: create group, add composites, derive, verify firing."""
    print("=" * 60)
    print("Integration Test: Rule Groups End-to-End")
    print("=" * 60)

    # Step 1: Clean up any existing test group
    with session_scope() as s:
        s.execute(text("DELETE FROM ref_trig_group_member WHERE rule_group_code = 'INTEG-TEST-GROUP'"))
        s.execute(text("DELETE FROM ref_trig_rule_group WHERE rule_group_code = 'INTEG-TEST-GROUP'"))
        s.commit()
    print("[OK] Step 1: Cleaned up any existing test group")

    # Step 2: Create a new test rule group
    with session_scope() as s:
        ok = create_rule_group(
            s,
            "INTEG-TEST-GROUP",
            group_type="action",
            action_label="TEST-ACTION",
            priority=5,
            category="Testing",
            intent_text="Integration test group"
        )
        if not ok:
            print("[FAIL] Failed to create test group")
            return False

        # Add members - use existing composite rules that are likely to fire
        ok = add_group_member(s, "INTEG-TEST-GROUP", "899-SA-Trend-Breaks", "composite", "AND", 1)
        if not ok:
            print("[FAIL] Failed to add member 1")
            return False

        s.commit()
    print("[OK] Step 2: Created test group with 1 composite member")

    # Step 3: Test evaluation logic
    with session_scope() as s:
        # Simulate both true
        composite_results = {"899-SA-Trend-Breaks": True}
        triggered, action, priority = eval_rule_group(s, "INTEG-TEST-GROUP", composite_results)
        if triggered and action == "TEST-ACTION" and priority == 5:
            print(f"[OK] Step 3a: Evaluation works - triggered={triggered}, action={action}, priority={priority}")
        else:
            print(f"[FAIL] Step 3a: Unexpected evaluation result")
            return False

        # Simulate false
        composite_results = {"899-SA-Trend-Breaks": False}
        triggered, action, priority = eval_rule_group(s, "INTEG-TEST-GROUP", composite_results)
        if not triggered:
            print(f"[OK] Step 3b: Correctly not triggered when composite is false")
        else:
            print(f"[FAIL] Step 3b: Should not trigger when composite is false")
            return False

    # Step 4: Re-derive drv_stks and check if any symbols have this group triggered
    with session_scope() as s:
        latest_date = s.execute(
            text("SELECT MAX(as_of_date) FROM drv_ma")
        ).scalar()

        if not latest_date:
            print("[FAIL] No data in drv_ma for derivation test")
            return False

        # Clear drv_stks for this date
        s.execute(text(f"DELETE FROM drv_stks WHERE as_of_date = '{latest_date}'"))
        s.commit()

    print(f"[OK] Step 4a: Cleared drv_stks for {latest_date}")

    with session_scope() as s:
        n = derive_stks(s, latest_date)
        s.commit()
    print(f"[OK] Step 4b: Derived {n} rows for drv_stks")

    # Step 5: Check if INTEG-TEST-GROUP fired for any symbol
    with session_scope() as s:
        rows_with_group = s.execute(
            text(f"""
            SELECT symbol, triggered_group_ids
            FROM drv_stks
            WHERE as_of_date = '{latest_date}'
            AND triggered_group_ids IS NOT NULL
            AND triggered_group_ids::text LIKE '%INTEG-TEST-GROUP%'
            LIMIT 5
            """)
        ).fetchall()

        if rows_with_group:
            print(f"\n[OK] Step 5: Group fired for {len(rows_with_group)} symbols")
            for symbol, groups in rows_with_group:
                try:
                    parsed = json.loads(groups) if isinstance(groups, str) else groups
                    print(f"  {symbol}: {[g.get('rule_group_code') for g in parsed]}")
                except Exception as e:
                    print(f"  {symbol}: Error parsing: {e}")
            return True
        else:
            # This is ok - depends on whether 899-SA-Trend-Breaks actually fired
            print(f"\n[INFO] Step 5: Group didn't fire for any symbols")
            print("[INFO] (This is normal if 899-SA-Trend-Breaks didn't trigger)")

            # Check if any symbols have 899-SA-Trend-Breaks triggered
            check = s.execute(
                text(f"""
                SELECT COUNT(*) FROM drv_stks
                WHERE as_of_date = '{latest_date}'
                AND triggered_composite_ids IS NOT NULL
                AND triggered_composite_ids::text LIKE '%899-SA-Trend-Breaks%'
                """)
            ).scalar()

            if check > 0:
                print(f"[INFO] But 899-SA-Trend-Breaks DID fire for {check} symbols")
                print("[FAIL] Group should have fired but didn't - logic error")
                return False
            else:
                print("[OK] Confirmed: 899-SA-Trend-Breaks didn't fire, so group correctly didn't fire")
                return True

    return True

if __name__ == "__main__":
    try:
        success = test_end_to_end()
        if success:
            print("\n" + "=" * 60)
            print("INTEGRATION TEST PASSED [OK]")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("INTEGRATION TEST FAILED [FAIL]")
            print("=" * 60)
            exit(1)
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
