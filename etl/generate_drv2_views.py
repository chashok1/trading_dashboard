#!/usr/bin/env python3
"""
Generate db/15_drv2_views.sql from the registry.

The drv2_* views pivot drv_cat_* tables back to the source perspective.
For example, drv2_td (derived from TD daily file) JOINs all drv_cat_* tables
that contain TD-sourced columns.

This is a lightweight alternative to materializing both drv_cat_* and drv2_*.
"""

import sys
import re
from pathlib import Path
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_FILE = PROJECT_ROOT / "db" / "15_drv2_views.sql"


def generate_drv2_views(session):
    """Generate VIEW definitions for all drv2_* tables."""
    from etl.ma_codegen import get_all_drv2_tables

    # Get list of all drv2_* tables
    drv2_tables = get_all_drv2_tables(session)
    # Filter out invalid names (those with special characters like parentheses)
    drv2_tables = [t for t in drv2_tables if t.isidentifier() or (t.startswith('drv2_') or t.startswith('('))]
    # Actually, skip entries with parentheses entirely - they're not valid SQL identifiers
    drv2_tables = [t for t in drv2_tables if not any(c in t for c in '()[]{}')]

    if not drv2_tables:
        print("ERROR: No valid drv2_* tables found in registry")
        sys.exit(1)

    print(f"Generating views for {len(drv2_tables)} drv2_* tables: {', '.join(drv2_tables)}")

    # Build VIEW for each drv2_* table
    views = {}

    for drv2_table in drv2_tables:
        # Get all columns for this drv2_* table
        cols = session.execute(
            text("""
                SELECT column_name, drv_cat_table
                FROM ref_ma_columns
                WHERE drv2_table = :dt AND drv_cat_table != 'drv_cat_separator'
                ORDER BY excel_col_idx
            """),
            {"dt": drv2_table},
        ).mappings().all()

        if not cols:
            continue

        # Group by drv_cat_table
        by_cat = {}
        for col in cols:
            cat = col["drv_cat_table"]
            if cat not in by_cat:
                by_cat[cat] = []
            by_cat[cat].append(col["column_name"])

        # Build JOIN clauses
        joins = []
        joins.append("drv_cat_identity i")  # Always start with identity
        for cat_table in sorted(by_cat.keys()):
            if cat_table != "drv_cat_identity":
                alias = cat_table.replace("drv_cat_", "")
                joins.append(
                    f"LEFT JOIN {cat_table} {alias} USING (as_of_date, symbol)"
                )

        # Build SELECT list
        # Include identity columns always
        select_cols = ["i.as_of_date", "i.symbol"]

        # Add columns from each cat_table
        for cat_table in sorted(by_cat.keys()):
            if cat_table == "drv_cat_identity":
                continue
            alias = cat_table.replace("drv_cat_", "")
            for col_name in by_cat[cat_table]:
                # Quote column names that aren't valid SQL identifiers
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col_name):
                    col_name_quoted = f'"{col_name}"'
                else:
                    col_name_quoted = col_name
                select_cols.append(f"{alias}.{col_name_quoted}")

        # Build the VIEW
        view_sql = (
            f"CREATE OR REPLACE VIEW {drv2_table} AS\n"
            f"SELECT  {select_cols[0]},\n        "
        )
        view_sql += ",\n        ".join(select_cols[1:])
        view_sql += f"\nFROM    {joins[0]}\n"
        for join in joins[1:]:
            view_sql += f"  {join}\n"
        view_sql += ";"

        views[drv2_table] = view_sql

    # Write to file
    with open(OUTPUT_FILE, "w") as f:
        f.write("-- Auto-generated from ref_ma_columns registry\n")
        f.write("-- View definitions for drv2_* tables (source perspective)\n")
        f.write("-- DO NOT EDIT BY HAND\n\n")

        for view_name in sorted(views.keys()):
            f.write(f"-- {view_name}\n")
            f.write(views[view_name])
            f.write("\n\n")

    print(f"Generated {len(views)} drv2_* views in {OUTPUT_FILE}")
    print("\nNext: Review and apply with python -m db.init_db")


if __name__ == "__main__":
    from etl.db import session_scope

    with session_scope() as session:
        # Verify registry is seeded
        count = session.execute(text("SELECT COUNT(*) FROM ref_ma_columns")).scalar()
        if count == 0:
            print("ERROR: ref_ma_columns is empty. Run seed_ref_ma_columns.py first.")
            sys.exit(1)

        generate_drv2_views(session)
