#!/usr/bin/env python3
"""
Check all hist_* tables for:
1. Columns that are entirely NULL
2. Duplicate columns across related tables (hist_to, hist_td, hist_tw)
3. Verify if columns were moved to derived tables
"""
from sqlalchemy import inspect, text
from etl.db import session_scope


def check_null_columns_v2():
    """Check hist_* tables for all-NULL and duplicate columns."""

    with session_scope() as session:
        inspector = inspect(session.bind)

        # Get all tables starting with 'hist_'
        all_tables = inspector.get_table_names()
        hist_tables = sorted([t for t in all_tables if t.startswith('hist_')])
        drv_tables = sorted([t for t in all_tables if t.startswith('drv_')])

        print("=" * 100)
        print("NULL & DUPLICATE COLUMNS ANALYSIS - hist_* tables")
        print("=" * 100)

        all_null_columns = {}  # {table: [columns]}
        table_columns = {}     # {table: {col_name: row_count}}

        # First pass: check all hist_* tables for null columns
        for table_name in hist_tables:
            columns = inspector.get_columns(table_name)
            col_names = [c['name'] for c in columns]

            # Get row count
            row_count_result = session.execute(
                text(f"SELECT COUNT(*) as cnt FROM {table_name}")
            ).fetchone()
            row_count = row_count_result[0] if row_count_result else 0

            table_columns[table_name] = {col: row_count for col in col_names}

            if row_count == 0:
                print(f"\n{table_name:20} [0 rows] - SKIPPED (empty table)")
                continue

            null_cols = []

            # Check each column
            for col_name in col_names:
                non_null_result = session.execute(
                    text(f"SELECT COUNT(*) as cnt FROM {table_name} WHERE {col_name} IS NOT NULL")
                ).fetchone()
                non_null_count = non_null_result[0] if non_null_result else 0

                if non_null_count == 0:
                    null_cols.append(col_name)

            if null_cols:
                all_null_columns[table_name] = null_cols
                print(f"\n{table_name:20} [{row_count:6} rows] ALL-NULL COLUMNS:")
                for col in null_cols:
                    print(f"  - {col}")
            else:
                print(f"\n{table_name:20} [{row_count:6} rows] [OK] No all-NULL columns")

        # Second pass: find duplicate columns across hist_to, hist_td, hist_tw
        print("\n" + "=" * 100)
        print("DUPLICATE COLUMNS ACROSS RELATED TABLES")
        print("=" * 100)

        related_tables = ['hist_to', 'hist_td', 'hist_tw']
        related_cols = {}
        for table_name in related_tables:
            if table_name in table_columns:
                related_cols[table_name] = set(table_columns[table_name].keys())

        # Find columns that appear in multiple tables
        if len(related_cols) >= 2:
            all_cols = set()
            for cols in related_cols.values():
                all_cols.update(cols)

            duplicates_found = False
            for col in sorted(all_cols):
                tables_with_col = [t for t in related_tables if col in related_cols.get(t, set())]
                if len(tables_with_col) > 1:
                    duplicates_found = True
                    null_status = []
                    for table_name in tables_with_col:
                        is_null = table_name in all_null_columns and col in all_null_columns[table_name]
                        status = "[ALL NULL]" if is_null else "[populated]"
                        null_status.append(f"{table_name:12} {status}")

                    print(f"\n{col:25} appears in {len(tables_with_col)} table(s):")
                    for status_str in null_status:
                        print(f"  - {status_str}")

            if not duplicates_found:
                print("\n[OK] No duplicate columns across hist_to, hist_td, hist_tw")

        # Third pass: check if null columns exist in drv_cat_atomic_input
        print("\n" + "=" * 100)
        print("CHECKING IF COLUMNS EXIST IN DERIVED TABLES")
        print("=" * 100)

        drv_cat_cols = set()
        if 'drv_cat_atomic_input' in drv_tables:
            cols = inspector.get_columns('drv_cat_atomic_input')
            drv_cat_cols = {c['name'] for c in cols}
            print("\ndrv_cat_atomic_input columns found for:")

            moved_cols = []
            for table_name, null_cols in all_null_columns.items():
                for col in null_cols:
                    if col in drv_cat_cols:
                        moved_cols.append((table_name, col))

            if moved_cols:
                for table_name, col in moved_cols:
                    print(f"  - {col:25} (from {table_name}) [MOVED TO drv_cat_atomic_input]")
            else:
                print("  [none of the all-NULL columns appear to be moved]")

        # Final summary
        print("\n" + "=" * 100)
        print("SUMMARY")
        print("=" * 100)

        if all_null_columns:
            truly_unused = {}
            for table_name, cols in all_null_columns.items():
                unused = [c for c in cols if c not in drv_cat_cols]
                if unused:
                    truly_unused[table_name] = unused

            if truly_unused:
                print(f"\nFound {len(truly_unused)} table(s) with truly unused columns:\n")
                for table_name in sorted(truly_unused.keys()):
                    cols = truly_unused[table_name]
                    print(f"  {table_name}: {len(cols)} column(s)")
                    for col in cols:
                        print(f"    - {col}")
            else:
                print("\n[OK] All all-NULL columns appear to have been moved to derived tables")
        else:
            print("\n[OK] No all-NULL columns found in any hist_* table")

        print("\n" + "=" * 100)


if __name__ == "__main__":
    check_null_columns_v2()
