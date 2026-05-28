#!/usr/bin/env python3
"""
Check all hist_* tables for columns that are entirely NULL.
Produces a report of tables and their all-NULL columns.
"""
from sqlalchemy import inspect, text
from etl.db import session_scope


def check_null_columns():
    """Check all hist_* tables for columns with all NULL values."""

    with session_scope() as session:
        inspector = inspect(session.bind)

        # Get all tables starting with 'hist_'
        all_tables = inspector.get_table_names()
        hist_tables = sorted([t for t in all_tables if t.startswith('hist_')])

        print("=" * 80)
        print("NULL COLUMNS ANALYSIS - hist_* tables")
        print("=" * 80)

        all_null_columns = {}  # {table: [columns]}

        for table_name in hist_tables:
            columns = inspector.get_columns(table_name)
            col_names = [c['name'] for c in columns]

            # Get row count
            row_count_result = session.execute(
                text(f"SELECT COUNT(*) as cnt FROM {table_name}")
            ).fetchone()
            row_count = row_count_result[0] if row_count_result else 0

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

        # Summary
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)

        if all_null_columns:
            print(f"\nFound {len(all_null_columns)} table(s) with all-NULL columns:\n")
            for table_name in sorted(all_null_columns.keys()):
                cols = all_null_columns[table_name]
                print(f"  {table_name}: {len(cols)} column(s)")
                for col in cols:
                    print(f"    - {col}")
        else:
            print("\n[OK] No all-NULL columns found in any hist_* table")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    check_null_columns()
