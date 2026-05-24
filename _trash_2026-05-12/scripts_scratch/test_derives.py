#!/usr/bin/env python3
"""Test the drv_cat_* derives."""

from etl.derive import derive_all
from etl.db import session_scope
from datetime import date

print("Testing drv_cat_* derives for 2026-04-30...")
print("=" * 80)

with session_scope() as session:
    try:
        counts = derive_all(session, date(2026, 4, 30))

        print("\nDerive Results:")
        print("-" * 80)

        # Separate drv_cat_* tables from others
        cat_tables = {k: v for k, v in counts.items() if k.startswith('drv_cat_')}
        other_tables = {k: v for k, v in counts.items() if not k.startswith('drv_cat_')}

        print(f"\ndrv_cat_* tables ({len(cat_tables)} total):")
        for table_name in sorted(cat_tables.keys()):
            count = cat_tables[table_name]
            status = "OK" if count > 500 else "LOW" if count > 0 else "EMPTY"
            print(f"  {table_name:<30} {count:>6} rows  [{status}]")

        print(f"\nOther tables ({len(other_tables)} total):")
        for table_name in sorted(other_tables.keys()):
            count = other_tables[table_name]
            print(f"  {table_name:<30} {count:>6} rows")

        total_cat = sum(cat_tables.values())
        print(f"\nTotal drv_cat_* rows: {total_cat:,}")
        print(f"Expected: ~{26 * 820:,} (26 tables x ~820 symbols)")

        if total_cat > 15000:
            print("\n[SUCCESS] Derives completed successfully!")
        else:
            print("\n[WARNING] Fewer rows than expected - check for NULL source_expr errors")

    except Exception as e:
        print(f"[ERROR] Derive failed: {e}")
        import traceback
        traceback.print_exc()
