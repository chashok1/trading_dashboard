#!/usr/bin/env python3
"""
Enrich ref_ma_columns with data from ma_columns_full.csv and ma_columns_registry_seed.csv

This script merges:
  - ma_columns_v2.csv (pipeline_stage, concept, drv_cat_table)
  - ma_columns_full.csv (drv2_table, first_source_sheet)
  - ma_columns_registry_seed.csv (pg_type hints, source_table hints)

Then updates the registry table with this information.
"""

import csv
import sys
from pathlib import Path
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parent.parent


def load_full_csv():
    """Load ma_columns_full.csv into a dict keyed by header."""
    full_file = PROJECT_ROOT / "docs" / "ma_columns_full.csv"
    result = {}
    with open(full_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Key by header to allow merging with v2
            header = row.get("header", "").strip()
            if header:
                result[header] = row
    return result


def load_seed_csv():
    """Load ma_columns_registry_seed.csv into a dict keyed by column_name."""
    seed_file = PROJECT_ROOT / "docs" / "ma_columns_registry_seed.csv"
    if not seed_file.exists():
        return {}

    result = {}
    with open(seed_file) as f:
        reader = csv.DictReader(f)
        for row in reader:
            col_name = row.get("pg_name", "").strip()
            if col_name:
                result[col_name] = row
    return result


def enrich_registry(session):
    """Enrich the registry with additional data."""
    full_data = load_full_csv()
    seed_data = load_seed_csv()

    # Get all rows from the registry
    rows = session.execute(
        text("SELECT * FROM ref_ma_columns ORDER BY excel_col_idx")
    ).mappings().all()

    updates = 0
    for row in rows:
        col_name = row["column_name"]
        excel_header = row["excel_header"]

        # Lookup in full_csv
        full_info = full_data.get(excel_header, {})
        drv2_table = full_info.get("drv2_table") or row["drv2_table"]
        first_source_sheet = full_info.get("first_source_sheet")

        # Infer source_table from first_source_sheet if not set
        source_table = row["source_table"]
        if not source_table and first_source_sheet:
            # Map sheet name to hist_*/drv_* table
            sheet_to_table = {
                "Y": "hist_y",
                "TL": "hist_tl",
                "TD": "hist_td",
                "TW": "hist_tw",
                "RR": "hist_rr",
                "II": "hist_ii",
                "call": "hist_call",
                "etf": "hist_etf",
                "SSS": "hist_sss",
                "TO": "hist_to",
                "ps": "hist_ps",
                "F": "hist_f",
                "CS": "hist_cs",
            }
            source_table = sheet_to_table.get(first_source_sheet.strip())

        # Lookup in seed_csv for pg_type hint
        seed_info = seed_data.get(col_name, {})
        pg_type = row["pg_type"]
        if seed_info.get("pg_type"):
            pg_type = seed_info.get("pg_type")

        # Update if any field changed
        if (drv2_table != row["drv2_table"] or
            source_table != row["source_table"] or
            pg_type != row["pg_type"]):

            sql = text("""
                UPDATE ref_ma_columns
                SET drv2_table = :drv2_table,
                    source_table = :source_table,
                    pg_type = :pg_type
                WHERE column_name = :col_name
            """)
            session.execute(sql, {
                "drv2_table": drv2_table,
                "source_table": source_table,
                "pg_type": pg_type,
                "col_name": col_name,
            })
            updates += 1

    session.commit()
    print(f"Updated {updates} registry rows with enriched data")

    # Print summary
    result = session.execute(text("""
        SELECT
            drv_cat_table,
            COUNT(*) as count,
            COUNT(CASE WHEN source_table IS NOT NULL THEN 1 END) as with_source_table,
            COUNT(CASE WHEN source_expr IS NOT NULL THEN 1 END) as with_source_expr,
            COUNT(CASE WHEN display_label IS NOT NULL THEN 1 END) as with_display_label
        FROM ref_ma_columns
        WHERE drv_cat_table != 'drv_cat_separator'
        GROUP BY drv_cat_table
        ORDER BY drv_cat_table
    """)).mappings().all()

    print("\nRegistry enrichment status by category:")
    print("drv_cat_table,count,source_table,source_expr,display_label")
    for row in result:
        print(f"{row['drv_cat_table']},{row['count']},"
              f"{row['with_source_table']}/{row['count']},"
              f"{row['with_source_expr']}/{row['count']},"
              f"{row['with_display_label']}/{row['count']}")

    print("\nNext steps:")
    print("  1. Manually populate source_expr for NULL entries (use Excel formulas as guide)")
    print("  2. Populate display_label for user-facing columns")
    print("  3. Verify drv2_table assignments")
    print("  4. Run: python -m etl.generate_cat_ddl")

    print("\n=== Backfilling source_expr from source_table aliases ===")
    backfill_source_expr(session)


if __name__ == "__main__":
    from etl.db import session_scope

    with session_scope() as session:
        # Verify the registry exists
        count = session.execute(text("SELECT COUNT(*) FROM ref_ma_columns")).scalar()
        if count == 0:
            print("ERROR: ref_ma_columns is empty. Run seed_ref_ma_columns.py first.")
            sys.exit(1)

        print(f"Enriching {count} registry rows with data from full/seed CSVs")
        enrich_registry(session)


# =============================================================================
# Smart source_expr backfill
# Fills in `source_expr` for rows where source_table is set but source_expr is
# NULL. Uses the same alias mapping that ma_codegen.JOIN_PATTERNS expects.
# Covers the simplest case: passthrough column reads from a single source row.
# Columns whose source_table itself is NULL are left alone (require manual
# population - see docs/RULES_ENGINE_NEXT_STEPS.md).
# =============================================================================

# Mirror of JOIN_PATTERNS aliases in etl/ma_codegen.py.
# Keep this in sync if aliases change there.
_TABLE_ALIAS = {
    "ref_sector":   "rs",
    "drv_td":       "td",
    "drv_tw":       "tw",
    "hist_y":       "y",
    "hist_tl":      "tl",
    "hist_td":      "td",
    "hist_tw":      "tw",
    "hist_rr":      "rr",
    "hist_ii":      "ii",
    "hist_call":    "hcall",
    "hist_etf":     "hetf",
    "hist_sss": "hsss",
    "drv_ssh":      "dssh",
    "hist_to":      '"to"',
    "hist_ps":      "ps",
    "hist_etfchg":  "etfchg",
    "hist_iichg":   "iichg",
    "hist_f":       "fid",
    "hist_cs":      "cs",
    "drv_ma":       "ma",
}


def backfill_source_expr(session):
    """For each row where source_table IS NOT NULL AND source_expr IS NULL,
    set source_expr = '<alias>.<column_name>' using the JOIN_PATTERNS alias map.
    Reports how many rows were touched and how many remain NULL.
    """
    from sqlalchemy import text
    rows = session.execute(text("""
        SELECT column_name, source_table
        FROM ref_ma_columns
        WHERE source_table IS NOT NULL
          AND (source_expr IS NULL OR source_expr = '')
    """)).mappings().all()

    updated = 0
    skipped_no_alias = []
    for r in rows:
        st = r["source_table"]
        cn = r["column_name"]
        alias = _TABLE_ALIAS.get(st)
        if not alias:
            skipped_no_alias.append((st, cn))
            continue
        # Quote the column if it isn't a clean identifier
        col_part = cn if cn.replace("_", "").isalnum() and not cn[:1].isdigit() else f'"{cn}"'
        expr = f"{alias}.{col_part}"
        session.execute(
            text("UPDATE ref_ma_columns SET source_expr = :se WHERE column_name = :cn"),
            {"se": expr, "cn": cn},
        )
        updated += 1
    session.commit()

    # Tally final state
    final = session.execute(text("""
        SELECT
          COUNT(*) AS total,
          COUNT(source_expr) FILTER (WHERE source_expr IS NOT NULL AND source_expr <> '') AS with_expr,
          COUNT(*) FILTER (WHERE source_table IS NULL) AS no_source_table
        FROM ref_ma_columns
    """)).mappings().first()

    print(f"backfill_source_expr: updated {updated} rows")
    if skipped_no_alias:
        unique_tables = sorted({s for s, _ in skipped_no_alias})
        print(f"  skipped {len(skipped_no_alias)} rows - no alias for source_table: {unique_tables}")
        print(f"  -> add those tables to _TABLE_ALIAS above")
    print(f"registry state: {final['with_expr']}/{final['total']} rows have source_expr")
    print(f"  ({final['no_source_table']} rows still have source_table=NULL - need manual population)")


