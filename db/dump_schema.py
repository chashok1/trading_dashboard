"""
Dump the current database schema to a single file.

Walks the live Postgres DB and emits CREATE TABLE / CREATE INDEX / seed
data for every relation in the public schema, in a dependency-safe order.

Usage:
    .venv\\Scripts\\activate
    python -m db.dump_schema           # writes db/schema.sql
    python -m db.dump_schema -o /tmp/x.sql
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path
from datetime import datetime

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings  # noqa: E402


def fetch_tables(cur) -> list[tuple[str, str]]:
    """Return (table_name, kind) for every relation in public schema."""
    cur.execute("""
        SELECT c.relname,
               CASE c.relkind
                 WHEN 'r' THEN 'table'
                 WHEN 'v' THEN 'view'
                 WHEN 'm' THEN 'matview'
               END AS kind
        FROM   pg_class c
        JOIN   pg_namespace n ON n.oid = c.relnamespace
        WHERE  n.nspname = 'public'
          AND  c.relkind IN ('r','v','m')
          AND  c.relname NOT LIKE 'pg_%'
        ORDER BY c.relname
    """)
    return cur.fetchall()


def fetch_table_ddl(cur, table: str) -> str:
    """Reconstruct CREATE TABLE statement for a table."""
    cur.execute("""
        SELECT column_name, data_type, character_maximum_length,
               is_nullable, column_default
        FROM   information_schema.columns
        WHERE  table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
    """, (table,))
    cols = cur.fetchall()
    if not cols:
        return ""

    lines = [f"CREATE TABLE IF NOT EXISTS {table} ("]
    col_defs = []
    for name, dtype, maxlen, nullable, default in cols:
        type_sql = dtype.upper()
        if maxlen and dtype in ('character varying', 'character'):
            type_sql = f"{type_sql}({maxlen})"
        d = f"    {name:30s} {type_sql}"
        if nullable == 'NO':
            d += " NOT NULL"
        if default:
            # Trim cast suffixes like ::text for readability
            d += f" DEFAULT {default}"
        col_defs.append(d)

    # Primary key
    cur.execute("""
        SELECT a.attname
        FROM   pg_index i
        JOIN   pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE  i.indrelid = %s::regclass AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
    """, (table,))
    pk_cols = [r[0] for r in cur.fetchall()]
    if pk_cols:
        col_defs.append(f"    PRIMARY KEY ({', '.join(pk_cols)})")

    lines.append(",\n".join(col_defs))
    lines.append(");")
    return "\n".join(lines)


def fetch_indexes(cur, table: str) -> list[str]:
    cur.execute("""
        SELECT indexname, indexdef
        FROM   pg_indexes
        WHERE  schemaname = 'public' AND tablename = %s
          AND  indexname NOT IN (
            SELECT conname FROM pg_constraint
            WHERE conrelid = %s::regclass AND contype IN ('p','u'))
        ORDER BY indexname
    """, (table, table))
    return [f"{r[1]};" for r in cur.fetchall()]


def fetch_view_ddl(cur, view: str) -> str:
    cur.execute("SELECT pg_get_viewdef(%s::regclass, true)", (view,))
    body = cur.fetchone()[0].rstrip(';\n')
    return f"CREATE OR REPLACE VIEW {view} AS\n{body};"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", default="db/schema.sql")
    args = ap.parse_args()
    out_path = Path(args.out)

    with psycopg.connect(host=settings.pg_host, port=settings.pg_port,
                         dbname=settings.pg_database, user=settings.pg_user,
                         password=settings.pg_password) as conn:
        with conn.cursor() as cur:
            objs = fetch_tables(cur)
            tables = [n for n, k in objs if k == 'table']
            views  = [n for n, k in objs if k == 'view']

            chunks = [
                f"-- =======================================================================",
                f"-- schema.sql — auto-generated from live DB on {datetime.utcnow().isoformat()}Z",
                f"-- Source DB: {settings.pg_database} @ {settings.pg_host}:{settings.pg_port}",
                f"-- Tables: {len(tables)}, Views: {len(views)}",
                f"-- =======================================================================",
                "",
            ]
            for t in tables:
                ddl = fetch_table_ddl(cur, t)
                if not ddl: continue
                chunks.append(f"-- ---- {t} ----")
                chunks.append(ddl)
                for ix in fetch_indexes(cur, t):
                    chunks.append(ix)
                chunks.append("")
            for v in views:
                chunks.append(f"-- ---- view: {v} ----")
                chunks.append(fetch_view_ddl(cur, v))
                chunks.append("")

    out_path.write_text("\n".join(chunks), encoding="utf-8")
    print(f"wrote {out_path} ({len(tables)} tables, {len(views)} views)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
