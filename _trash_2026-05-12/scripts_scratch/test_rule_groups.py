#!/usr/bin/env python
"""Test suite for rule groups implementation."""
import psycopg
from config.settings import settings
from etl.rule_groups import eval_rule_group, resolve_final_action, create_rule_group, add_group_member
from etl.db import session_scope

def test_schema():
    """Verify rule groups tables were created."""
    print("=" * 60)
    print("TEST 1: Verify Rule Groups Schema")
    print("=" * 60)

    with psycopg.connect(host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
                         user=settings.pg_user, password=settings.pg_password) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name IN ('ref_trig_rule_group', 'ref_trig_group_member')
            """)
            tables = sorted([row[0] for row in cur.fetchall()])
            assert len(tables) == 2, f"Expected 2 tables, got {len(tables)}"
            print(f"[OK] Tables created: {tables}")

            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'ref_trig_rule_group' ORDER BY ordinal_position
            """)
            cols = [row[0] for row in cur.fetchall()]
            expected = ['rule_group_code', 'group_type', 'action_label', 'priority', 'category', 'intent_text', 'deprecated_at', 'created_at']
            assert all(c in cols for c in expected), f"Missing columns: {set(expected) - set(cols)}"
            print(f"[OK] All expected columns exist")

def test_crud():
    """Test create, read operations."""
    print("\n" + "=" * 60)
    print("TEST 2: Test CRUD Operations")
    print("=" * 60)

    with session_scope() as s:
        # Create test group
        ok = create_rule_group(s, "TEST-SA-GROUP", "action", "SA", 1, "Test", "Test group")
        assert ok, "Failed to create group"
        print(f"[OK] Create group: OK")

        # Add members
        ok = add_group_member(s, "TEST-SA-GROUP", "899-SA-Trend-Breaks", "composite", "AND", 1)
        assert ok, "Failed to add member 1"
        print(f"[OK] Add member 1: OK")

        ok = add_group_member(s, "TEST-SA-GROUP", "888-SA-Trade-Breaks", "composite", "AND", 2)
        assert ok, "Failed to add member 2"
        print(f"[OK] Add member 2: OK")

        s.commit()

def test_evaluation():
    """Test rule group evaluation logic."""
    print("\n" + "=" * 60)
    print("TEST 3: Test Recursive Evaluation Logic")
    print("=" * 60)

    with session_scope() as s:
        composite_results = {
            "899-SA-Trend-Breaks": True,
            "888-SA-Trade-Breaks": True,
        }

        # Both members true = triggered
        triggered, action, priority = eval_rule_group(s, "TEST-SA-GROUP", composite_results)
        assert triggered == True, "AND(True, True) should be True"
        assert action == "SA", f"Expected action SA, got {action}"
        assert priority == 1, f"Expected priority 1, got {priority}"
        print(f"[OK] Test AND(True, True): triggered={triggered}, action={action}, priority={priority}")

        # One member false = not triggered
        composite_results["888-SA-Trade-Breaks"] = False
        triggered, action, priority = eval_rule_group(s, "TEST-SA-GROUP", composite_results)
        assert triggered == False, "AND(True, False) should be False"
        assert action == None and priority == None, "Non-triggered group should return None for action/priority"
        print(f"[OK] Test AND(True, False): triggered={triggered}, action={action}, priority={priority}")

def test_priority():
    """Test priority resolution."""
    print("\n" + "=" * 60)
    print("TEST 4: Test Priority Resolution")
    print("=" * 60)

    triggered_groups = [
        {"rule_group_code": "SA-Group", "action": "SA", "priority": 1},
        {"rule_group_code": "BM-Group", "action": "BM", "priority": 4},
        {"rule_group_code": "SS-Group", "action": "SS", "priority": 3},
    ]

    winner = resolve_final_action(triggered_groups)
    assert winner["priority"] == 1, f"Expected priority 1, got {winner['priority']}"
    assert winner["rule_group_code"] == "SA-Group", f"Expected SA-Group, got {winner['rule_group_code']}"
    print(f"[OK] Highest priority wins: {winner['rule_group_code']} (Priority {winner['priority']})")

def test_persistence():
    """Verify data persisted to database."""
    print("\n" + "=" * 60)
    print("TEST 5: Verify Data in Database")
    print("=" * 60)

    with psycopg.connect(host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
                         user=settings.pg_user, password=settings.pg_password) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT rule_group_code, action_label, priority FROM ref_trig_rule_group WHERE rule_group_code = 'TEST-SA-GROUP'")
            group = cur.fetchone()
            assert group, "Group not found in DB"
            assert group[0] == "TEST-SA-GROUP", f"Wrong code: {group[0]}"
            assert group[1] == "SA", f"Wrong action: {group[1]}"
            assert group[2] == 1, f"Wrong priority: {group[2]}"
            print(f"[OK] Group persisted: code={group[0]}, action={group[1]}, priority={group[2]}")

            cur.execute("SELECT COUNT(*) FROM ref_trig_group_member WHERE rule_group_code = 'TEST-SA-GROUP'")
            member_count = cur.fetchone()[0]
            assert member_count == 2, f"Expected 2 members, got {member_count}"
            print(f"[OK] Members persisted: {member_count} members")

if __name__ == "__main__":
    try:
        test_schema()
        test_crud()
        test_evaluation()
        test_priority()
        test_persistence()

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED [OK]")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        exit(1)
    except Exception as e:
        print(f"\n[FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
