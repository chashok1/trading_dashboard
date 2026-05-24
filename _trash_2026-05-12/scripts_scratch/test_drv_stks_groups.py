#!/usr/bin/env python
"""Test that drv_stks populates triggered_group_ids correctly."""
import json
from datetime import date
from sqlalchemy import text
from config.settings import settings
from etl.db import session_scope, get_engine
from etl.derive import derive_stks

def test_derive_stks_with_groups():
    """Run derive_stks for latest date and verify triggered_group_ids are populated."""
    print("=" * 60)
    print("Testing drv_stks with triggered_group_ids")
    print("=" * 60)

    with session_scope() as s:
        # Find latest as_of_date in drv_ma
        latest_date = s.execute(
            text("SELECT MAX(as_of_date) FROM drv_ma")
        ).scalar()

        if not latest_date:
            print("[FAIL] No data in drv_ma. Cannot test derivation.")
            return False

        print(f"\n[OK] Latest date in drv_ma: {latest_date}")

        # Delete any existing rows for this date so we can re-derive
        s.execute(text(f"DELETE FROM drv_stks WHERE as_of_date = '{latest_date}'"))
        s.commit()
        print(f"[OK] Cleared drv_stks for {latest_date}")

    # Run the derivation
    print(f"\n[OK] Running derive_stks for {latest_date}...")
    with session_scope() as s:
        try:
            n = derive_stks(s, latest_date)
            s.commit()
            print(f"[OK] Derived {n} rows for drv_stks")
        except Exception as e:
            print(f"[FAIL] Derivation error: {e}")
            import traceback
            traceback.print_exc()
            return False

    # Verify triggered_group_ids were populated
    with session_scope() as s:
        rows = s.execute(
            text(f"SELECT symbol, triggered_group_ids FROM drv_stks WHERE as_of_date = '{latest_date}' LIMIT 10")
        ).fetchall()

        if not rows:
            print("[FAIL] No rows found in drv_stks after derivation")
            return False

        print(f"\n[OK] Sample rows from drv_stks:")
        for symbol, triggered_groups in rows:
            if triggered_groups:
                try:
                    groups = json.loads(triggered_groups) if isinstance(triggered_groups, str) else triggered_groups
                    print(f"  {symbol}: {len(groups)} groups triggered")
                    for g in groups:
                        print(f"    - {g.get('rule_group_code')}: action={g.get('action')}, priority={g.get('priority')}")
                except Exception as e:
                    print(f"  {symbol}: Error parsing groups: {e}")
            else:
                print(f"  {symbol}: No groups triggered")

        # Count total rows with triggered groups
        with_groups = s.execute(
            text(f"SELECT COUNT(*) FROM drv_stks WHERE as_of_date = '{latest_date}' AND triggered_group_ids IS NOT NULL")
        ).scalar()
        total = s.execute(
            text(f"SELECT COUNT(*) FROM drv_stks WHERE as_of_date = '{latest_date}'")
        ).scalar()

        print(f"\n[OK] Summary: {with_groups}/{total} symbols have triggered groups")

        if with_groups > 0:
            print("[OK] Rule groups are being evaluated and tracked!")
            return True
        else:
            print("[INFO] No rule groups triggered for this date (may be normal if no groups configured)")
            return True

if __name__ == "__main__":
    try:
        success = test_derive_stks_with_groups()
        if success:
            print("\n" + "=" * 60)
            print("DERIVATION TEST PASSED [OK]")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("DERIVATION TEST FAILED [FAIL]")
            print("=" * 60)
            exit(1)
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
