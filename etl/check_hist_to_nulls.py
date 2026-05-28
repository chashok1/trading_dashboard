#!/usr/bin/env python3
"""
Comprehensive NULL analysis for hist_to table.
Reports NULL count, percentage, and data quality for each column.
"""
from sqlalchemy import inspect, text
from etl.db import session_scope


def check_hist_to_nulls():
    """Analyze NULL values in hist_to."""

    with session_scope() as session:
        inspector = inspect(session.bind)

        # Get hist_to structure
        columns = inspector.get_columns('hist_to')
        col_names = [c['name'] for c in columns]
        col_types = {c['name']: str(c['type']) for c in columns}

        # Get total row count
        row_count_result = session.execute(text("SELECT COUNT(*) FROM hist_to")).fetchone()
        total_rows = row_count_result[0] if row_count_result else 0

        print("=" * 100)
        print(f"NULL VALUES ANALYSIS - hist_to")
        print("=" * 100)
        print(f"\nTotal rows: {total_rows:,}")
        print(f"Total columns: {len(col_names)}\n")

        # Analyze each column
        print(f"{'Column':<30} {'Type':<15} {'Non-NULL':<12} {'NULL':<12} {'%':<8}")
        print("-" * 100)

        null_summary = {}
        all_null_cols = []
        mostly_null_cols = []
        mostly_populated_cols = []

        for col_name in col_names:
            # Get non-NULL count
            non_null_result = session.execute(
                text(f"SELECT COUNT(*) FROM hist_to WHERE {col_name} IS NOT NULL")
            ).fetchone()
            non_null_count = non_null_result[0] if non_null_result else 0
            null_count = total_rows - non_null_count
            null_pct = (null_count / total_rows * 100) if total_rows > 0 else 0

            col_type = col_types[col_name]

            print(f"{col_name:<30} {col_type:<15} {non_null_count:<12,} {null_count:<12,} {null_pct:>6.1f}%")

            null_summary[col_name] = {
                'non_null': non_null_count,
                'null': null_count,
                'pct': null_pct,
                'type': col_type
            }

            # Categorize columns
            if null_count == total_rows:
                all_null_cols.append(col_name)
            elif null_pct > 50:
                mostly_null_cols.append((col_name, null_pct))
            elif null_pct == 0:
                mostly_populated_cols.append(col_name)

        # Summary sections
        print("\n" + "=" * 100)
        print("SUMMARY")
        print("=" * 100)

        print(f"\nFully Populated Columns (0% NULL): {len(mostly_populated_cols)}")
        for col in sorted(mostly_populated_cols):
            print(f"  [OK] {col}")

        if mostly_null_cols:
            print(f"\nPartially Populated Columns (1-50% NULL): {len(mostly_null_cols)}")
            for col, pct in sorted(mostly_null_cols, key=lambda x: x[1]):
                print(f"  [WARN] {col:<30} {pct:>6.1f}% NULL")

        if all_null_cols:
            print(f"\nCompletely NULL Columns (100% NULL): {len(all_null_cols)}")
            for col in sorted(all_null_cols):
                print(f"  [NULL] {col}")
        else:
            print("\n[OK] No completely NULL columns")

        # Data quality score
        populated_cols = [c for c in col_names if null_summary[c]['pct'] < 100]
        avg_null_pct = sum(null_summary[c]['pct'] for c in populated_cols) / len(populated_cols) if populated_cols else 0

        print(f"\nData Quality Metrics:")
        print(f"  - Columns with any data: {len(populated_cols)}/{len(col_names)}")
        print(f"  - Average NULL%: {avg_null_pct:.1f}%")
        print(f"  - Columns > 50% NULL: {len(mostly_null_cols)}")
        print(f"  - Columns 100% NULL: {len(all_null_cols)}")

        # Sample check for populated columns
        if populated_cols:
            print(f"\nMost Critical Columns (for drv_ma):")
            critical = ['beta', 'market_cap_str', 'pe_ratio', 'eps', 'div_yield', 'sector']
            for col in critical:
                if col in null_summary:
                    info = null_summary[col]
                    status = "[OK]" if info['pct'] < 10 else "[WARN]" if info['pct'] < 50 else "[CRITICAL]"
                    print(f"  {status} {col:<20} {info['non_null']:>6,} rows ({100-info['pct']:>5.1f}% populated)")

        print("\n" + "=" * 100)


if __name__ == "__main__":
    check_hist_to_nulls()
