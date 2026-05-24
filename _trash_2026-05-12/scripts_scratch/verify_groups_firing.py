#!/usr/bin/env python
"""Verify that auto-generated rule groups are actually firing."""
import json
from sqlalchemy import text
from etl.db import session_scope
from etl.derive import derive_stks

def main():
    print("=" * 60)
    print("Verifying Auto-Generated Rule Groups")
    print("=" * 60)

    with session_scope() as s:
        latest_date = s.execute(
            text("SELECT MAX(as_of_date) FROM drv_ma")
        ).scalar()

        if not latest_date:
            print("[FAIL] No data in drv_ma")
            return False

        print(f"\n[OK] Latest date: {latest_date}")

        # Clear and re-derive
        s.execute(text(f"DELETE FROM drv_stks WHERE as_of_date = '{latest_date}'"))
        s.commit()

    with session_scope() as s:
        n = derive_stks(s, latest_date)
        s.commit()
        print(f"[OK] Derived {n} rows")

    # Check how many symbols have groups triggered
    with session_scope() as s:
        # Get overall stats
        stats = s.execute(text(f"""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN triggered_group_ids IS NOT NULL THEN 1 END) as with_groups
            FROM drv_stks
            WHERE as_of_date = '{latest_date}'
        """)).fetchone()

        total, with_groups = stats or (0, 0)

        print(f"\n[OK] Statistics:")
        print(f"  Total symbols: {total}")
        print(f"  Symbols with groups triggered: {with_groups}")

        if with_groups > 0:
            print(f"\n[OK] Rule groups ARE firing! ({with_groups}/{total} symbols have triggered groups)")

            # Show sample triggered groups
            samples = s.execute(text(f"""
                SELECT
                    symbol,
                    triggered_group_ids,
                    triggered_composite_ids
                FROM drv_stks
                WHERE as_of_date = '{latest_date}'
                AND triggered_group_ids IS NOT NULL
                LIMIT 10
            """)).fetchall()

            print(f"\nSample triggered groups:")
            for symbol, groups, composites in samples:
                try:
                    g = json.loads(groups) if isinstance(groups, str) else groups
                    c = json.loads(composites) if isinstance(composites, str) else composites

                    group_names = [x.get('rule_group_code') for x in g] if g else []
                    composite_names = [x.get('rule_id') for x in c] if c else []

                    print(f"\n  {symbol}:")
                    print(f"    Groups: {group_names}")
                    if composite_names:
                        print(f"    Composites: {', '.join(composite_names[:3])}..." if len(composite_names) > 3 else f"    Composites: {composite_names}")
                except Exception as e:
                    print(f"  {symbol}: Error parsing: {e}")

            return True
        else:
            print(f"\n[INFO] No rule groups triggered for this date")

            # Check if ANY composites triggered
            composites_count = s.execute(text(f"""
                SELECT COUNT(*)
                FROM drv_stks
                WHERE as_of_date = '{latest_date}'
                AND triggered_composite_ids IS NOT NULL
            """)).scalar()

            if composites_count > 0:
                print(f"[INFO] But {composites_count} symbols HAVE triggered composites")
                print("[INFO] The rule group OR logic should have fired - checking...")

                # Check if the groups actually exist
                groups = s.execute(text("""
                    SELECT COUNT(*) FROM ref_trig_rule_group WHERE rule_group_code LIKE 'GROUP-%'
                """)).scalar()

                print(f"[INFO] Found {groups} auto-generated groups in DB")

                if groups > 0:
                    print("[FAIL] Groups exist but aren't firing - logic error")
                    return False
            else:
                print("[INFO] No composites triggered either - data may be in early/late dates")

            return True

if __name__ == "__main__":
    try:
        if main():
            print("\n" + "=" * 60)
            print("VERIFICATION COMPLETE")
            print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
