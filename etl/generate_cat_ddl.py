#!/usr/bin/env python3
"""
Generate db/drv_cat_tables.sql from the populated ref_ma_columns registry.

This script should be run AFTER:
  1. python -m db.init_db (creates the schema)
  2. python -m etl.seed_ref_ma_columns (populates ref_ma_columns)

Output: db/drv_cat_tables.sql — ready to apply via db.init_db or psql
"""

import sys
from pathlib import Path
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_FILE = PROJECT_ROOT / "db" / "drv_cat_tables.sql"


def generate_cat_ddl(session):
    """Generate DDL from the registry and write to file."""
    from etl.ma_codegen import build_ddl

    ddls = build_ddl(session)

    if not ddls:
        print("ERROR: No drv_cat_* tables found in ref_ma_columns")
        sys.exit(1)

    # Write to file with header
    with open(OUTPUT_FILE, "w") as f:
        f.write("-- Auto-generated from ref_ma_columns registry\n")
        f.write("-- DO NOT EDIT BY HAND\n")
        f.write("-- Regenerate with: python -m etl.generate_cat_ddl\n\n")

        for table_name in sorted(ddls.keys()):
            f.write(f"-- {table_name}\n")
            f.write(ddls[table_name])
            f.write("\n\n")

    print(f"Generated {len(ddls)} drv_cat_* table DDLs in {OUTPUT_FILE}")
    print("\nNext steps:")
    print("  1. Review db/drv_cat_tables.sql")
    print("  2. Run: python -m db.init_db (to apply the new DDLs)")
    print("  3. Add per-category derive functions to etl/derive.py")


if __name__ == "__main__":
    from etl.db import session_scope

    with session_scope() as session:
        # Verify the registry is seeded
        count = session.execute(text("SELECT COUNT(*) FROM ref_ma_columns")).scalar()
        if count == 0:
            print("ERROR: ref_ma_columns is empty. Run seed_ref_ma_columns.py first.")
            sys.exit(1)

        print(f"Registry has {count} columns")
        generate_cat_ddl(session)
