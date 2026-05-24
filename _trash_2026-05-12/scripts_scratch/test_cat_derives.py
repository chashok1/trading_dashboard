#!/usr/bin/env python3
"""Test only the drv_cat_* derives (skip drv_trig and other derives)."""

from etl.derive import derive_all
from etl.db import session_scope
from datetime import date

print("Testing drv_cat_* derives for 2026-04-30...")
print("=" * 80)

with session_scope() as session:
    try:
        # Just run derive_all - we'll see how many drv_cat_* tables get populated
        # even if drv_trig fails
        counts = {}

        # Manually derive just the drv_cat_* tables
        from etl import ma_codegen
        from sqlalchemy import text

        as_of_date = date(2026, 4, 30)

        # Create a run ID
        result = session.execute(text("""
            INSERT INTO meta_derived_run (as_of_date, target_table, status)
            VALUES (:d, 'drv_cat_batch', 'running')
            RETURNING run_id
        """), {"d": as_of_date})
        run_id = result.scalar()
        session.commit()

        # Derive each cat_table
        for cat_table in sorted(ma_codegen.get_all_cat_tables(session)):
            session.execute(text(f"DELETE FROM {cat_table} WHERE as_of_date = :d"), {"d": as_of_date})
            dml = ma_codegen.build_dml(session, cat_table)
            if not dml:
                counts[cat_table] = 0
                continue
            result = session.execute(text(dml), {"d": as_of_date, "run_id": run_id})
            counts[cat_table] = result.rowcount or 0
            session.commit()

        print("\nDrv_cat_* Derives Results:")
        print("-" * 80)

        cat_tables = {k: v for k, v in counts.items() if k.startswith('drv_cat_')}

        print(f"\ndrv_cat_* tables ({len(cat_tables)} total):")
        for table_name in sorted(cat_tables.keys()):
            count = cat_tables[table_name]
            status = "OK" if count > 500 else "LOW" if count > 0 else "EMPTY"
            print(f"  {table_name:<30} {count:>6} rows  [{status}]")

        total_cat = sum(cat_tables.values())
        print(f"\nTotal drv_cat_* rows: {total_cat:,}")
        print(f"Expected: ~{26 * 820:,} (26 tables x ~820 symbols)")

        if total_cat > 15000:
            print("\n[SUCCESS] drv_cat_* derives completed successfully!")
        else:
            print("\n[WARNING] Fewer rows than expected - check for NULL source_expr errors")

    except Exception as e:
        print(f"[ERROR] Derive failed: {e}")
        import traceback
        traceback.print_exc()
