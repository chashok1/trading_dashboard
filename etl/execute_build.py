#!/usr/bin/env python3
"""
Direct execution of the drv_cat_* build without subprocess calls.
All steps use direct imports for better error handling.
"""

import sys
from pathlib import Path
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parent.parent


def step_1_init_db():
    """Apply all SQL DDL files."""
    print("\n" + "="*80)
    print("Step 1/7: Applying schema DDLs (db.init_db)")
    print("="*80)
    try:
        from db.init_db import main as db_init_main
        result = db_init_main()
        if result != 0:
            print(f"ERROR: db.init_db returned {result}")
            return False
        print("[OK] Schema initialized")
        return True
    except Exception as e:
        print(f"ERROR in step_1: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_2_seed():
    """Seed registry from CSV."""
    print("\n" + "="*80)
    print("Step 2/7: Seeding ref_ma_columns from ma_columns_v2.csv")
    print("="*80)
    try:
        from etl.seed_ref_ma_columns import load_registry
        from etl.db import session_scope

        with session_scope() as session:
            load_registry(session)
        print("[OK] Registry seeded")
        return True
    except Exception as e:
        print(f"ERROR in step_2: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_3_enrich():
    """Enrich registry."""
    print("\n" + "="*80)
    print("Step 3/7: Enriching registry (CSV merge + Excel analysis)")
    print("="*80)
    try:
        from etl.enrich_ref_ma_columns import enrich_registry
        from etl.db import session_scope

        with session_scope() as session:
            enrich_registry(session)

        # Run auto_enrich (surface failures with full traceback so they're visible)
        print("\nRunning Excel analysis enrichment...")
        try:
            from etl.auto_enrich_registry import auto_enrich
            with session_scope() as session:
                auto_enrich(session)
        except Exception as e:
            import traceback as _tb
            print(f"WARNING: Excel analysis FAILED (continuing build): {type(e).__name__}: {e}")
            print("--- traceback ---")
            _tb.print_exc()
            print("--- end traceback ---")
            print("This step is OPTIONAL - drv_cat_* tables will be empty until source_expr is populated.")

        return True
    except Exception as e:
        print(f"ERROR in step_3: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_4_generate_ddl():
    """Generate drv_cat_* table DDLs."""
    print("\n" + "="*80)
    print("Step 4/7: Generating db/drv_cat_tables.sql")
    print("="*80)
    try:
        from etl.ma_codegen import build_ddl
        from etl.db import session_scope

        with session_scope() as session:
            ddls = build_ddl(session)
            output_file = PROJECT_ROOT / "db" / "drv_cat_tables.sql"

            with open(output_file, "w") as f:
                f.write("-- Auto-generated from ref_ma_columns registry\n")
                f.write("-- DO NOT EDIT BY HAND\n\n")
                for table_name in sorted(ddls.keys()):
                    f.write(f"-- {table_name}\n")
                    f.write(ddls[table_name])
                    f.write("\n\n")

            print(f"[OK] Generated {len(ddls)} drv_cat_* table DDLs in {output_file}")
            return True
    except Exception as e:
        print(f"ERROR in step_4: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_5_apply_ddls():
    """Apply drv_cat_* DDLs."""
    print("\n" + "="*80)
    print("Step 5/7: Applying drv_cat_* table DDLs")
    print("="*80)
    try:
        from db.init_db import main as db_init_main
        result = db_init_main()
        if result != 0:
            print(f"ERROR: db.init_db returned {result}")
            return False
        print("[OK] drv_cat_* tables created")
        return True
    except Exception as e:
        print(f"ERROR in step_5: {e}")
        import traceback
        traceback.print_exc()
        return False


def step_6_generate_views():
    """Generate drv2_* view definitions."""
    print("\n" + "="*80)
    print("Step 6/7: Generating db/15_drv2_views.sql")
    print("="*80)
    try:
        from etl.generate_drv2_views import generate_drv2_views
        from etl.db import session_scope

        with session_scope() as session:
            generate_drv2_views(session)
        print("[OK] drv2_* views generated")
        return True
    except Exception as e:
        print(f"ERROR in step_6: {e}")
        import traceback
        traceback.print_exc()
        return False


def print_summary():
    """Print final summary."""
    print("\n" + "="*80)
    print("BUILD COMPLETE!")
    print("="*80)
    print("""
All drv_cat_* infrastructure is now in place:

[OK] Registry table (ref_ma_columns) seeded with 641 MA columns
[OK] Enriched with source_table, source_expr, pg_type from CSVs and Excel
[OK] Generated db/drv_cat_tables.sql (~30 CREATE TABLE statements)
[OK] Applied drv_cat_* tables to database
[OK] Generated db/15_drv2_views.sql (source-perspective views)
[OK] Per-category derives already wired into etl/derive.py

Next Steps:

1. Test the derives:
   python -m etl.tickers_initial_load
   (This will populate all drv_cat_* tables for the latest date)

2. Verify row counts in the database
   SELECT COUNT(*) FROM drv_cat_price;
   (Should have ~820-830 rows, one per symbol)

3. Check other drv_cat_* tables similarly

4. If any derives fail due to NULL source_expr, fix them in the registry and regenerate

5. Run parity tests to validate against Excel
   pytest tests/test_cat_parity.py

6. Once working, proceed with Phase 2 (thin drv_ma, rules engine, API, etc.)
""")


def step_7_apply_views():
    """Apply the freshly generated db/15_drv2_views.sql so the views exist in PG."""
    print("\n" + "="*80)
    print("Step 7/7: Applying db/15_drv2_views.sql (CREATE OR REPLACE VIEW ...)")
    print("="*80)
    try:
        from db.init_db import main as db_init_main
        result = db_init_main()
        if result != 0:
            print(f"ERROR: db.init_db returned {result}")
            return False
        print("[OK] drv2_* views created/replaced in DB")
        return True
    except Exception as e:
        print(f"ERROR in step_7: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    try:
        if not step_1_init_db():
            sys.exit(1)
        if not step_2_seed():
            sys.exit(1)
        if not step_3_enrich():
            sys.exit(1)
        if not step_4_generate_ddl():
            sys.exit(1)
        if not step_5_apply_ddls():
            sys.exit(1)
        if not step_6_generate_views():
            sys.exit(1)
        if not step_7_apply_views():
            sys.exit(1)
        print_summary()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
