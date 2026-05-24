"""Generate docs/data_flow_detailed.html — column-by-column data flow report.

Reads ref_ma_columns + information_schema to produce a single self-contained
HTML page showing every drv_cat_* / drv2_* table, every target column, and the
exact source expression used to populate it. Uses your live DB so it stays
current as registry edits land.

Run from project root:
    python -m etl.gen_data_flow_doc

Output:
    docs/data_flow_detailed.html  (open in any browser)
"""
from __future__ import annotations

import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from etl.db import session_scope


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH     = PROJECT_ROOT / "docs" / "data_flow_detailed.html"
OVERVIEW_SVG = PROJECT_ROOT / "docs" / "diagrams" / "data_flow_current.svg"


# -----------------------------------------------------------------------------
# Data fetchers
# -----------------------------------------------------------------------------

def fetch_registry(session) -> list[dict]:
    """One row per registry column with its source_expr and current target table."""
    rows = session.execute(text("""
        SELECT
            COALESCE(drv_cat_table, '(unmapped)') AS drv_cat_table,
            column_name,
            pg_type,
            source_table,
            source_expr,
            pipeline_stage,
            concept,
            excel_header
        FROM ref_ma_columns
        WHERE COALESCE(drv_cat_table, '') NOT IN ('drv_cat_separator', '')
        ORDER BY drv_cat_table, column_name
    """)).mappings().all()
    return [dict(r) for r in rows]


def fetch_table_row_counts(session, table_names: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for tbl in table_names:
        try:
            n = session.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar() or 0
        except Exception:
            n = -1  # table doesn't exist
        counts[tbl] = n
    return counts


def fetch_real_columns(session, schema: str = "public") -> dict[str, list[tuple[str, str]]]:
    """For every table+view in the schema, return [(column_name, data_type), ...]."""
    rows = session.execute(text("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = :s
        ORDER BY table_name, ordinal_position
    """), {"s": schema}).all()
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for tn, cn, dt in rows:
        out[tn].append((cn, dt))
    return out


# -----------------------------------------------------------------------------
# Rendering helpers
# -----------------------------------------------------------------------------

def status_badge(rows: int) -> str:
    if rows < 0:
        return '<span class="badge badge-missing">no table</span>'
    if rows == 0:
        return '<span class="badge badge-empty">empty</span>'
    return f'<span class="badge badge-ok">{rows:,} rows</span>'


def expr_class(expr: str | None) -> str:
    if not expr:
        return "expr-null"
    if " " in expr or "(" in expr or "CASE" in expr.upper() or "::" in expr:
        return "expr-computed"
    return "expr-passthrough"


def render_drv_cat_section(name: str, cols: list[dict], row_count: int) -> str:
    """One <details> block per drv_cat_* table, listing every target column."""
    n_total   = len(cols)
    n_mapped  = sum(1 for c in cols if c["source_expr"])
    n_unmap   = n_total - n_mapped

    badge = status_badge(row_count)
    summary = (
        f"<summary>"
        f"<span class='tname'>{html.escape(name)}</span> "
        f"{badge} "
        f"<span class='tmeta'>· {n_total} cols · {n_mapped} mapped · {n_unmap} unmapped</span>"
        f"</summary>"
    )

    rows_html = []
    for c in cols:
        src_table = c["source_table"] or "—"
        src_expr  = c["source_expr"] or ""
        pg_type   = c["pg_type"] or ""
        stage     = c["pipeline_stage"] or ""
        concept   = c["concept"] or ""
        excel_h   = c["excel_header"] or ""
        cls       = expr_class(src_expr)
        rows_html.append(
            f"<tr class='{cls}'>"
            f"<td class='c'>{html.escape(c['column_name'])}</td>"
            f"<td class='c'>{html.escape(pg_type)}</td>"
            f"<td class='c'>{html.escape(src_table)}</td>"
            f"<td class='c expr'>{html.escape(src_expr) if src_expr else '<i>NULL — unmapped</i>'}</td>"
            f"<td class='c'>{html.escape(stage)}</td>"
            f"<td class='c'>{html.escape(concept)}</td>"
            f"<td class='c excel'>{html.escape(excel_h)}</td>"
            f"</tr>"
        )

    table = (
        "<table class='cols'>"
        "<thead><tr>"
        "<th>target column</th>"
        "<th>type</th>"
        "<th>source table</th>"
        "<th>source_expr (SQL)</th>"
        "<th>pipeline stage</th>"
        "<th>concept</th>"
        "<th>excel header</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )

    return f"<details class='cat-block'>{summary}{table}</details>"


def render_source_section(table: str, cols: list[tuple[str, str]], row_count: int) -> str:
    """One <details> per source table — just lists columns + types."""
    badge = status_badge(row_count)
    rows_html = "".join(
        f"<tr><td class='c'>{html.escape(cn)}</td><td class='c'>{html.escape(dt)}</td></tr>"
        for cn, dt in cols
    )
    return (
        f"<details class='src-block'>"
        f"<summary><span class='tname'>{html.escape(table)}</span> {badge} "
        f"<span class='tmeta'>· {len(cols)} cols</span></summary>"
        f"<table class='cols small'><thead><tr><th>column</th><th>type</th></tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
        f"</details>"
    )


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:
    with session_scope() as s:
        registry = fetch_registry(s)
        all_cols = fetch_real_columns(s)

        # Discover all tables of interest, then look up their counts
        cat_tables = sorted({r["drv_cat_table"] for r in registry
                             if r["drv_cat_table"].startswith("drv_cat_")})
        hist_tables = sorted([t for t in all_cols if t.startswith("hist_")])
        drv_tables  = sorted([t for t in all_cols
                              if t.startswith("drv_") and not t.startswith("drv_cat_")
                                 and not t.startswith("drv2_")])
        drv2_tables = sorted([t for t in all_cols if t.startswith("drv2_")])

        all_for_count = cat_tables + hist_tables + drv_tables + drv2_tables
        counts = fetch_table_row_counts(s, all_for_count)

    # Group registry rows by drv_cat_table
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in registry:
        by_cat[r["drv_cat_table"]].append(r)

    overview_svg_inline = ""
    if OVERVIEW_SVG.exists():
        overview_svg_inline = OVERVIEW_SVG.read_text(encoding="utf-8")

    css = """
    body { font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
           margin: 0; padding: 0; background: #f7f7f5; color: #1c1917; font-size: 13px; }
    header { background: #fff; border-bottom: 1px solid #e5e5e2; padding: 16px 24px; position: sticky; top: 0; z-index: 10; }
    h1 { margin: 0; font-size: 18px; }
    .meta { font-size: 12px; color: #57534e; margin-top: 4px; }
    main { padding: 16px 24px 80px; }
    h2 { margin: 28px 0 12px; font-size: 14px; text-transform: uppercase; letter-spacing: 0.06em; color: #6b7280;
         padding-bottom: 6px; border-bottom: 1px solid #e5e5e2; }
    .overview { background: #fff; padding: 12px; border: 1px solid #e5e5e2; border-radius: 6px; overflow-x: auto; }
    .overview svg { display: block; max-width: 100%; height: auto; }
    details { background: #fff; border: 1px solid #e5e5e2; border-radius: 4px; margin-bottom: 6px; }
    details > summary { padding: 8px 12px; cursor: pointer; font-size: 13px; user-select: none; }
    details > summary:hover { background: #fafaf8; }
    details[open] > summary { border-bottom: 1px solid #e5e5e2; background: #fafaf8; }
    .tname { font-weight: 700; font-family: ui-monospace, "SF Mono", Consolas, monospace; }
    .tmeta { font-size: 11px; color: #6b7280; margin-left: 6px; }
    .badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 11px; font-weight: 600;
             margin-left: 4px; }
    .badge-ok       { background: #dcfce7; color: #15803d; }
    .badge-empty    { background: #fef3c7; color: #b45309; }
    .badge-missing  { background: #fee2e2; color: #b91c1c; }
    table.cols { width: 100%; border-collapse: collapse; font-size: 11px; }
    table.cols thead th { background: #f7f7f5; text-align: left; padding: 4px 8px;
                          font-weight: 600; font-size: 10px; text-transform: uppercase;
                          letter-spacing: 0.04em; color: #6b7280; border-bottom: 1px solid #e5e5e2; }
    table.cols tbody td { padding: 3px 8px; border-bottom: 1px solid #f1f1ec; vertical-align: top; }
    table.cols td.c { font-family: ui-monospace, "SF Mono", Consolas, monospace; }
    table.cols td.expr { white-space: pre-wrap; word-break: break-word; max-width: 380px; }
    table.cols td.excel { color: #6b7280; }
    table.cols.small td, table.cols.small th { font-size: 10px; padding: 2px 8px; }
    tr.expr-passthrough td.expr { color: #15803d; }
    tr.expr-computed    td.expr { color: #1d4ed8; }
    tr.expr-null        td.expr { color: #9ca3af; font-style: italic; }
    .legend { background: #fff; border: 1px solid #e5e5e2; border-radius: 4px; padding: 10px 14px;
              font-size: 11px; display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
    .legend > span { display: inline-flex; align-items: center; gap: 6px; }
    .swatch { width: 12px; height: 12px; border-radius: 2px; display: inline-block; }
    .col-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    @media (max-width: 1100px) { .col-grid { grid-template-columns: 1fr; } }
    """

    legend = """
    <div class='legend'>
      <span><span class='swatch' style='background:#dcfce7'></span> populated table</span>
      <span><span class='swatch' style='background:#fef3c7'></span> empty table</span>
      <span><span class='swatch' style='background:#fee2e2'></span> table missing</span>
      <span style='margin-left:auto;'>
        Source-expr colors:
        <span style='color:#15803d; font-weight:600;'>passthrough</span> ·
        <span style='color:#1d4ed8; font-weight:600;'>computed</span> ·
        <span style='color:#9ca3af; font-style:italic;'>NULL (unmapped)</span>
      </span>
    </div>
    """

    # Build sections
    cat_sections = "\n".join(
        render_drv_cat_section(name, by_cat[name], counts.get(name, -1))
        for name in cat_tables
    )

    hist_sections = "\n".join(
        render_source_section(t, all_cols[t], counts.get(t, -1)) for t in hist_tables
    )
    drv_sections = "\n".join(
        render_source_section(t, all_cols[t], counts.get(t, -1)) for t in drv_tables
    )
    drv2_sections = "\n".join(
        render_source_section(t, all_cols[t], counts.get(t, -1)) for t in drv2_tables
    )

    when = datetime.now().strftime("%Y-%m-%d %H:%M")

    html_doc = f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<title>Data Flow — Detailed Column Map</title>
<style>{css}</style>
</head><body>
<header>
  <h1>Trading Dashboard — Data Flow (column-level)</h1>
  <div class='meta'>Generated {when} from live ref_ma_columns + information_schema. Re-run <code>python -m etl.gen_data_flow_doc</code> to refresh.</div>
</header>
<main>

<h2>Overview</h2>
<div class='overview'>
{overview_svg_inline if overview_svg_inline else '<i>data_flow_current.svg not found — generate it first</i>'}
</div>

{legend}

<h2>Concept tables (drv_cat_*) — target column → source mapping</h2>
<p class='meta'>Each row shows where one column's value comes from. Click a table to expand. Rows are color-coded:
green = passthrough (single column read), blue = computed (CASE/arithmetic), gray = unmapped (NULL source_expr).</p>
{cat_sections}

<h2>Source tables (hist_*)</h2>
<p class='meta'>Raw imports from the Excel workbook. These feed everything downstream.</p>
<div class='col-grid'>
{hist_sections}
</div>

<h2>Per-row derived (drv_*)</h2>
<p class='meta'>One row per source row, with cleaned/computed columns.</p>
<div class='col-grid'>
{drv_sections}
</div>

<h2>Source-aggregated (drv2_*)</h2>
<p class='meta'>Phase 1 of drv2 migration: one row per (as_of_date, symbol) per source.</p>
<div class='col-grid'>
{drv2_sections}
</div>

</main></body></html>
"""

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(html_doc, encoding="utf-8")
    print(f"OK: wrote {OUT_PATH}")
    print(f"     Open it in a browser, or in VS Code with the Live Preview extension.")


if __name__ == "__main__":
    main()
