"""Registry-driven DDL/DML generation for drv_cat_* and drv2_* layers.

Generates:
  - DDL  -> db/drv_cat_tables.sql (DROP+CREATE so registry edits take effect)
  - DML  -> per-table INSERT...SELECT executed during derive_all()
  - VIEWs -> db/15_drv2_views.sql (source-perspective pivots over drv_cat_*)

Everything is driven by the `ref_ma_columns` registry. Hand-written DDL/DML
in this layer is an anti-goal.
"""
from typing import Dict, List
import re
import sys
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


# =============================================================================
# Symbol universe â€” UNION across hist_* (matches _derive_ma_impl behaviour).
# Symbols loaded into hist_* but missing from ref_sector still get a row (B4).
# =============================================================================
SYMBOL_UNIVERSE_CTE = """
WITH p AS (SELECT CAST(:d AS date) AS d),
syms AS (
  SELECT DISTINCT s AS symbol FROM (
    SELECT ticker AS s FROM ref_sector
    UNION SELECT symbol FROM hist_tl   WHERE snapshot_date <= (SELECT d FROM p)
    UNION SELECT symbol FROM hist_td   WHERE snapshot_date <= (SELECT d FROM p)
    UNION SELECT symbol FROM hist_tw   WHERE snapshot_date <= (SELECT d FROM p)
    UNION SELECT symbol FROM hist_y    WHERE snapshot_date <= (SELECT d FROM p)
    UNION SELECT symbol FROM hist_rr   WHERE snapshot_date <= (SELECT d FROM p)
    UNION SELECT symbol FROM hist_ii   WHERE snapshot_date <= (SELECT d FROM p)
    UNION SELECT symbol FROM hist_call WHERE snapshot_date <= (SELECT d FROM p)
    UNION SELECT symbol FROM hist_etf  WHERE snapshot_date <= (SELECT d FROM p)
    UNION SELECT symbol FROM hist_sss  WHERE snapshot_date <= (SELECT d FROM p)
  ) u WHERE s IS NOT NULL
)
"""


def _hist_join(table: str, alias: str, key: str = "symbol",
               date_col: str = "snapshot_date") -> str:
    """Compose a 'LEFT JOIN <table> <alias> ... latest <= :d' clause."""
    return (
        f"LEFT JOIN {table} {alias} ON ({alias}.{key} = syms.symbol "
        f"AND {alias}.{date_col} = (SELECT MAX({date_col}) FROM {table} "
        f"WHERE {date_col} <= :d AND {key} = syms.symbol))"
    )


# Standard JOIN patterns for each source table.
JOIN_PATTERNS = {
    "ref_sector": "LEFT JOIN ref_sector rs ON (rs.ticker = syms.symbol)",
    "drv_td":   _hist_join("drv_td",   "td"),
    "drv_tw":   _hist_join("drv_tw",   "tw"),
    "hist_y":   _hist_join("hist_y",   "y"),
    "hist_tl":  _hist_join("hist_tl",  "tl"),
    "hist_td":  _hist_join("hist_td",  "td"),
    "hist_tw":  _hist_join("hist_tw",  "tw"),
    "hist_rr":  _hist_join("hist_rr",  "rr"),
    "hist_ii":  _hist_join("hist_ii",  "ii"),
    "hist_call":_hist_join("hist_call","hcall"),
    "hist_etf": _hist_join("hist_etf", "hetf"),
    "hist_sss": _hist_join("hist_sss", "hsss"),
    "drv_ssh":  _hist_join("drv_ssh",  "dssh"),
    "hist_to":  ('LEFT JOIN hist_to "to" ON ("to".symbol = syms.symbol '
                 'AND "to".snapshot_date = (SELECT MAX(snapshot_date) FROM hist_to '
                 'WHERE snapshot_date <= :d AND symbol = syms.symbol))'),
    "hist_ps":   _hist_join("hist_ps", "ps",   key="ticker"),
    "hist_etfchg": _hist_join("hist_etfchg", "etfchg", date_col="event_date"),
    "hist_iichg":  _hist_join("hist_iichg",  "iichg",  date_col="event_date"),
    "hist_f": ("LEFT JOIN (SELECT symbol, SUM(qty) AS held_qty_fid FROM hist_f "
               "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d) "
               "GROUP BY symbol) fid ON fid.symbol = syms.symbol"),
    "hist_cs": ("LEFT JOIN (SELECT symbol, SUM(qty) AS held_qty_cs FROM hist_cs "
                "WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d) "
                "GROUP BY symbol) cs ON cs.symbol = syms.symbol"),
    # Lookup-only tables â€” table-specific WHERE goes in source_expr
    "ref_param":          "",
    "ref_param_lookup":   "",
    "ref_rrt":            "",
    "ref_quad_outlook":   "",
    "ref_calendar_event": "",
    "ref_holiday":        "",
    "ref_econ_indicator": "",
}


def _quote_ident(name: str) -> str:
    """Quote a column name only if it isn't a valid bare PG identifier."""
    if re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return name
    return f'"{name}"'


def unique(items: List) -> List:
    """Remove duplicates while preserving order."""
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def build_ddl(session: Session, *, drop_first: bool = True) -> Dict[str, str]:
    """Generate DROP+CREATE DDL for every drv_cat_* table.

    drop_first=True (default) emits DROP TABLE IF EXISTS â€¦ CASCADE before
    each CREATE so registry-driven schema edits actually take effect on
    regeneration. (CREATE TABLE IF NOT EXISTS silently skips if the table
    already exists â€” that was H2 in the audit.)
    """
    rows = session.execute(text("""
        SELECT * FROM ref_ma_columns
        WHERE drv_cat_table != 'drv_cat_separator'
        ORDER BY drv_cat_table, excel_col_idx
    """)).mappings().all()

    by_cat: Dict[str, List] = {}
    for row in rows:
        by_cat.setdefault(row["drv_cat_table"], []).append(row)

    out: Dict[str, str] = {}
    for cat_table in sorted(by_cat.keys()):
        col_defs = []
        for c in by_cat[cat_table]:
            cn = c["column_name"]
            if cn in ("as_of_date", "symbol"):
                continue
            pg_type = c["pg_type"] or "NUMERIC"
            col_defs.append(f"  {_quote_ident(cn):<40} {pg_type}")

        create_kw = "CREATE TABLE" if drop_first else "CREATE TABLE IF NOT EXISTS"
        drop_stmt = f"DROP TABLE IF EXISTS {cat_table} CASCADE;\n" if drop_first else ""

        body_lines = [
            f"{create_kw} {cat_table} (",
            "  as_of_date         DATE NOT NULL,",
            "  symbol             TEXT NOT NULL,",
            *(line + "," for line in col_defs),
            "  source_run_id      BIGINT,",
            "  computed_at        TIMESTAMPTZ DEFAULT now(),",
            "  PRIMARY KEY (as_of_date, symbol)",
            ");",
        ]
        out[cat_table] = drop_stmt + "\n".join(body_lines)
    return out


def build_dml(session: Session, cat_table: str, *,
              strict: bool = False,
              skip_missing: bool = True) -> str:
    """Generate INSERT...SELECT for one drv_cat_* table.

    Behaviour on registry rows with NULL source_expr (the common bug source):
      strict=True       -> raise ValueError listing the bad columns.
      skip_missing=True -> emit DML omitting those columns; warn on stderr.
                           (default â€” safe: no silent NULL data.)
      Both False        -> fall back to NULL::<type>.
    """
    cols = session.execute(text("""
        SELECT * FROM ref_ma_columns
        WHERE drv_cat_table = :c AND drv_cat_table != 'drv_cat_separator'
        ORDER BY excel_col_idx
    """), {"c": cat_table}).mappings().all()
    if not cols:
        return ""

    missing = [c for c in cols
               if c["column_name"] not in ("as_of_date", "symbol")
               and not c["source_expr"]]
    if missing and strict:
        bad = ", ".join(c["column_name"] for c in missing[:8])
        raise ValueError(
            f"{cat_table}: {len(missing)} columns have NULL source_expr "
            f"(e.g. {bad}). Populate ref_ma_columns.source_expr or pass strict=False."
        )
    if missing:
        msg = (f"[ma_codegen] WARN {cat_table}: {len(missing)} columns skipped "
               f"(NULL source_expr): "
               f"{', '.join(c['column_name'] for c in missing[:5])}"
               f"{'...' if len(missing) > 5 else ''}")
        log.warning(msg)
        print(msg, file=sys.stderr)

    if skip_missing:
        cols = [c for c in cols
                if c["column_name"] in ("as_of_date", "symbol")
                or c["source_expr"]]
    if not any(c["column_name"] not in ("as_of_date", "symbol") for c in cols):
        log.warning("%s: no columns left after skip_missing; emitting empty DML",
                    cat_table)
        return ""

    sources = unique([c["source_table"] for c in cols if c["source_table"]])
    unmapped = [s for s in sources if s not in JOIN_PATTERNS]
    if unmapped:
        print(f"[ma_codegen] WARN {cat_table}: source_table(s) without "
              f"JOIN_PATTERN: {unmapped}. Add to JOIN_PATTERNS.",
              file=sys.stderr)

    join_clauses = [JOIN_PATTERNS[s] for s in sources
                    if s in JOIN_PATTERNS and JOIN_PATTERNS[s]]
    join_str = "\n  ".join(join_clauses)

    select_exprs = []
    col_names_list = []
    for c in cols:
        cn = c["column_name"]
        if cn in ("as_of_date", "symbol"):
            continue
        cnq = _quote_ident(cn)
        col_names_list.append(cnq)
        select_exprs.append(f"{c['source_expr']} AS {cnq}")

    select_list = ",\n  ".join(select_exprs)
    col_names = ", ".join(col_names_list)

    dml = (
        f"{SYMBOL_UNIVERSE_CTE.rstrip()}\n"
        f"INSERT INTO {cat_table} (as_of_date, symbol, {col_names}, source_run_id)\n"
        f"SELECT :d AS as_of_date, syms.symbol,\n  {select_list},\n  :run_id AS source_run_id\n"
        f"FROM syms"
    )
    if join_str:
        dml += f"\n  {join_str}"
    dml += ";"
    return dml


def build_dml_strict(session: Session, cat_table: str) -> str:
    """Like build_dml() but raises on NULL source_expr. Used in tests."""
    return build_dml(session, cat_table, strict=True, skip_missing=False)


def get_all_cat_tables(session: Session) -> List[str]:
    """List all drv_cat_* table names (excluding separators)."""
    rows = session.execute(text("""
        SELECT DISTINCT drv_cat_table FROM ref_ma_columns
        WHERE drv_cat_table != 'drv_cat_separator'
        ORDER BY drv_cat_table
    """)).scalars().all()
    return list(rows)


def get_all_drv2_tables(session: Session) -> List[str]:
    """List all drv2_* table names (only valid identifiers)."""
    rows = session.execute(text("""
        SELECT DISTINCT drv2_table FROM ref_ma_columns
        WHERE drv2_table IS NOT NULL
        ORDER BY drv2_table
    """)).scalars().all()
    return [t for t in rows
            if t and t.startswith("drv2_")
            and not any(ch in t for ch in "()[]{}")]

