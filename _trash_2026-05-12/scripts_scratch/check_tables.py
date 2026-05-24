#!/usr/bin/env python3
from etl.db import session_scope
from sqlalchemy import text

print("Checking registry vs database tables...")
print("=" * 80)

with session_scope() as session:
    # Get all distinct drv_cat_tables from registry
    registry_tables = set(session.execute(
        text("SELECT DISTINCT drv_cat_table FROM ref_ma_columns WHERE drv_cat_table != 'drv_cat_separator' ORDER BY drv_cat_table")
    ).scalars().all())

    # Get all existing drv_cat_* tables from database
    db_tables = set(session.execute(
        text("""SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name LIKE 'drv_cat_%'
                ORDER BY table_name""")
    ).scalars().all())

    print(f"\nTables in registry: {len(registry_tables)}")
    print(f"Tables in database: {len(db_tables)}")

    missing = registry_tables - db_tables
    extra = db_tables - registry_tables

    if missing:
        print(f"\n[MISSING from database] {len(missing)} tables:")
        for t in sorted(missing):
            print(f"  {t}")

    if extra:
        print(f"\n[EXTRA in database] {len(extra)} tables:")
        for t in sorted(extra):
            print(f"  {t}")

    if not missing and not extra:
        print("\n[OK] Registry and database tables match!")
