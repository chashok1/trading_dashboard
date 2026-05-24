#!/usr/bin/env python3
"""Seed ref_ma_columns registry from docs/ma_columns_v2.csv.

CSV columns: idx, letter, header, pipeline_stage, concept, drv_cat_table,
             color, island_id, formula

drv2_table is side-loaded from docs/ma_columns_full.csv (which carries it).
"""
import csv
import sys
from pathlib import Path
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parent.parent
CSV_FILE = PROJECT_ROOT / "docs" / "ma_columns_v2.csv"


def snake_case(s):
    """Convert Excel header to a *valid* snake_case PostgreSQL identifier."""
    if s is None:
        return ""
    s = str(s).strip()
    if s.startswith("!"):
        s = "not_" + s[1:]
    s = s.replace("!", "_not_")
    s = s.replace("%", "pct").replace("(", "").replace(")", "").replace("-", "_")
    s = s.replace("+", "_")  # M+ves -> m_ves
    s = s.replace(" ", "_").replace("$", "").replace(",", "").replace("#", "num")
    s = s.replace("^", "").replace("&", "and").replace(".", "").replace("/", "_")
    while "__" in s:
        s = s.replace("__", "_")
    s = s.lower().strip("_")
    if s and s[0].isdigit():
        s = "c_" + s
    return s[:60]


def infer_pg_type(formula, concept):
    """Infer PostgreSQL type from formula + concept."""
    if formula is None:
        formula = ""
    formula_lower = str(formula).lower()
    TEXT_CONCEPTS = {"identity", "trig_summary", "action_decision",
                     "he_outlook", "separator"}
    if concept in TEXT_CONCEPTS:
        if "rank" in formula_lower or "sort" in formula_lower:
            return "NUMERIC"
        return "TEXT"
    if "date" in formula_lower or "import_date" in formula_lower or "export_date" in formula_lower:
        return "DATE"
    if concept == "holdings_dollars" and any(k in formula_lower for k in ("name", "ticker", "symbol")):
        return "TEXT"
    return "NUMERIC"


def infer_source_kind(formula):
    """Infer source_kind from formula."""
    if formula is None or formula == "":
        return "static_input"
    formula_str = str(formula).lower()
    if "array" in str(formula):
        return "array_formula"
    if "xlookup" in formula_str or "vlookup" in formula_str or "index" in formula_str:
        return "lookup"
    if any(op in formula_str for op in ["+", "-", "*", "/"]):
        return "arithmetic"
    if "if(" in formula_str or "case" in formula_str:
        return "conditional"
    if any(agg in formula_str for agg in ["sum(", "average(", "min(", "max(", "count"]):
        return "aggregate"
    if formula_str.startswith("=") and len(formula_str) < 10:
        return "passthrough"
    return "passthrough"


def _load_drv2_lookup():
    """Build {excel_col_letter -> drv2_table} from ma_columns_full.csv."""
    full_csv = PROJECT_ROOT / "docs" / "ma_columns_full.csv"
    if not full_csv.exists():
        return {}
    out = {}
    with open(full_csv) as f:
        for row in csv.DictReader(f):
            letter = row.get("col_letter") or row.get("letter")
            drv2 = (row.get("drv2_table") or "").strip()
            if letter and drv2 and drv2.startswith("drv2_") and "_thin" not in drv2:
                out[letter] = drv2
    return out


INSERT_SQL = """
INSERT INTO ref_ma_columns (
    column_name, excel_header, excel_col_letter, excel_col_idx,
    pipeline_stage, concept, drv_cat_table, drv2_table, color_island_id,
    pg_type, source_kind, source_table, source_expr, excel_formula,
    exposed_to_rules, exposed_to_dashboard, display_label, notes
) VALUES (
    :column_name, :excel_header, :excel_col_letter, :excel_col_idx,
    :pipeline_stage, :concept, :drv_cat_table, :drv2_table, :color_island_id,
    :pg_type, :source_kind, :source_table, :source_expr, :excel_formula,
    :exposed_to_rules, :exposed_to_dashboard, :display_label, :notes
)
ON CONFLICT (column_name) DO UPDATE SET
    excel_header = EXCLUDED.excel_header,
    excel_col_letter = EXCLUDED.excel_col_letter,
    excel_col_idx = EXCLUDED.excel_col_idx,
    pipeline_stage = EXCLUDED.pipeline_stage,
    concept = EXCLUDED.concept,
    drv_cat_table = EXCLUDED.drv_cat_table,
    drv2_table = EXCLUDED.drv2_table,
    color_island_id = EXCLUDED.color_island_id,
    pg_type = EXCLUDED.pg_type,
    source_kind = EXCLUDED.source_kind,
    exposed_to_rules = EXCLUDED.exposed_to_rules,
    exposed_to_dashboard = EXCLUDED.exposed_to_dashboard
"""


def load_registry(session):
    """Load ref_ma_columns from CSV."""
    if not CSV_FILE.exists():
        print(f"ERROR: {CSV_FILE} not found")
        sys.exit(1)

    drv2_lookup = _load_drv2_lookup()
    print(f"Loaded {len(drv2_lookup)} drv2_table assignments from ma_columns_full.csv")

    rows = []
    with open(CSV_FILE) as f:
        for row in csv.DictReader(f):
            col_idx = int(row["idx"])
            excel_col = row["letter"]
            excel_header = row["header"]
            pipeline_stage = row["pipeline_stage"]
            concept = row["concept"]
            drv_cat = row["drv_cat_table"]
            island = row.get("island_id")
            formula = row.get("formula")

            col_name = snake_case(excel_header)
            pg_type = infer_pg_type(formula, concept)
            source_kind = infer_source_kind(formula)

            if drv_cat == "drv_cat_separator":
                print(f"Skipping separator column: {excel_header} ({excel_col})")
                continue

            rows.append({
                "column_name": col_name,
                "excel_header": excel_header,
                "excel_col_letter": excel_col,
                "excel_col_idx": col_idx,
                "pipeline_stage": pipeline_stage,
                "concept": concept,
                "drv_cat_table": drv_cat,
                "drv2_table": drv2_lookup.get(excel_col),
                "color_island_id": int(island) if island else None,
                "pg_type": pg_type,
                "source_kind": source_kind,
                "source_table": None,
                "source_expr": None,
                "excel_formula": str(formula) if formula else None,
                "exposed_to_rules": concept == "atomic_input",
                "exposed_to_dashboard": drv_cat != "drv_cat_separator",
                "display_label": None,
                "notes": None,
            })

    print(f"Loaded {len(rows)} rows from {CSV_FILE}")

    sql = text(INSERT_SQL)
    for row in rows:
        session.execute(sql, row)
    session.commit()
    print(f"Inserted {len(rows)} rows into ref_ma_columns")


if __name__ == "__main__":
    from etl.db import session_scope
    with session_scope() as session:
        load_registry(session)
        count = session.execute(text("SELECT COUNT(*) FROM ref_ma_columns")).scalar()
        print(f"\nVerification: ref_ma_columns now has {count} rows")
