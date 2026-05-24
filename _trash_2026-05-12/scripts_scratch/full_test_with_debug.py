#!/usr/bin/env python
"""Full derivation test with explicit verification."""
from datetime import date
from sqlalchemy import text
import json
from etl.db import session_scope
from etl.derive import derive_stks

print("=" * 70)
print("FULL RULE GROUPS DERIVATION TEST")
print("=" * 70)

# Step 1: Get latest date and clear drv_stks
with session_scope() as s:
    latest_date = s.execute(text("SELECT MAX(as_of_date) FROM drv_ma")).scalar()
    if not latest_date:
        print("[FAIL] No data in drv_ma")
        exit(1)

    print(f"\n[1] Latest date in drv_ma: {latest_date}")

    # Count before
    before = s.execute(text(f"SELECT COUNT(*) FROM drv_stks WHERE as_of_date = '{latest_date}'")).scalar()
    print(f"[2] Rows in drv_stks before clear: {before}")

    s.execute(text(f"DELETE FROM drv_stks WHERE as_of_date = '{latest_date}'"))
    s.commit()
    print(f"[3] Cleared drv_stks for {latest_date}")

# Step 2: Run derivation
print(f"\n[4] Running derive_stks({latest_date})...")
with session_scope() as s:
    try:
        n = derive_stks(s, latest_date)
        s.commit()
        print(f"    -> Inserted {n} rows")
    except Exception as e:
        print(f"[FAIL] Derivation error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

# Step 3: Verify data was inserted
print(f"\n[5] Verifying data in drv_stks:")
with session_scope() as s:
    total = s.execute(text(f"SELECT COUNT(*) FROM drv_stks WHERE as_of_date = '{latest_date}'")).scalar()
    print(f"    Total rows: {total}")

    # Check column nullability patterns
    stats = s.execute(text(f"""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN triggered_atomic_ids IS NOT NULL THEN 1 END) as with_atoms,
            COUNT(CASE WHEN triggered_composite_ids IS NOT NULL THEN 1 END) as with_comps,
            COUNT(CASE WHEN triggered_group_ids IS NOT NULL THEN 1 END) as with_groups
        FROM drv_stks WHERE as_of_date = '{latest_date}'
    """)).fetchone()

    if stats:
        total, atoms, comps, groups = stats
        print(f"    With triggered atomics: {atoms}/{total}")
        print(f"    With triggered composites: {comps}/{total}")
        print(f"    With triggered groups: {groups}/{total}")

    # Get a sample with groups
    print(f"\n[6] Sample rows with triggered groups:")
    samples = s.execute(text(f"""
        SELECT symbol, triggered_atomic_ids, triggered_composite_ids, triggered_group_ids
        FROM drv_stks
        WHERE as_of_date = '{latest_date}'
        AND triggered_group_ids IS NOT NULL
        LIMIT 3
    """)).fetchall()

    if samples:
        for symbol, atoms, comps, groups in samples:
            print(f"\n    Symbol: {symbol}")
            try:
                if atoms:
                    a = json.loads(atoms) if isinstance(atoms, str) else atoms
                    print(f"      Atoms: {len(a)} triggered")
                if comps:
                    c = json.loads(comps) if isinstance(comps, str) else comps
                    print(f"      Composites: {len(c)} triggered")
                if groups:
                    g = json.loads(groups) if isinstance(groups, str) else groups
                    print(f"      Groups: {len(g)} triggered - {[x.get('rule_group_code') for x in g]}")
            except Exception as e:
                print(f"      Error parsing: {e}")
    else:
        print("    NO rows found with groups triggered!")
        print("    This means either:")
        print("      - No composites are firing for any symbol")
        print("      - OR the derivation code isn't running")
        print("      - OR the groups aren't being populated")

print("\n" + "=" * 70)
