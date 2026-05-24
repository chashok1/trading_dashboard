"""
Apply DDL to the trading database.

After the 2026-05-12 consolidation, the canonical schema lives in
`db/baseline.sql` (idempotent: CREATE IF NOT EXISTS / ON CONFLICT DO NOTHING).
This script runs every `db/*.sql` file in sorted order so future patch
migrations dropped into `db/` are picked up automatically.

Reads PG_* connection settings from .env (never hardcoded).
Safe to run multiple times.

Usage (from project root):
    .venv\\Scripts\\activate
    python -m db.init_db                  # preserves audit tables
    python -m db.init_db --reset-audit    # also truncates audit/dedup tables
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings  # noqa: E402

DB_DIR = Path(__file__).resolve().parent
DDL_FILES = sorted(p for p in DB_DIR.glob("*.sql"))


def run_sql_file(conn: psycopg.Connection, path: Path) -> None:
    print(f"\n=== {path.name} ===")
    raw = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(raw)
    print(f"  OK")


def clear_audit_tables(conn: psycopg.Connection) -> None:
    """Clear audit/tracking tables so loads can be re-run from scratch."""
    print(f"\n=== Clearing audit tables ===")
    meta_tables = [
        "meta_etl_run",
        "meta_file_processed",
        "meta_cleanup_history",
        "meta_derived_run",
    ]
    with conn.cursor() as cur:
        for table in meta_tables:
            try:
                cur.execute(sql.SQL("TRUNCATE TABLE {} CASCADE").format(sql.Identifier(table)))
                print(f"  TRUNCATE {table}")
            except psycopg.Error:
                pass  # Table might not exist yet
    print(f"  OK")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply all DDL files to the trading database."
    )
    parser.add_argument(
        "--reset-audit",
        action="store_true",
        default=False,
        help="Also TRUNCATE audit/dedup tables (meta_etl_run, meta_file_processed, "
             "meta_derived_run, meta_cleanup_history). "
             "WARNING: destroys SHA-256 deduplication history. "
             "Use only for a full database reset."
    )
    args = parser.parse_args()

    if not settings.pg_password:
        print("ERROR: PG_PASSWORD is empty. Edit .env and set your Postgres password.",
              file=sys.stderr)
        return 2

    print(f"Connecting to {settings.pg_host}:{settings.pg_port}/"
          f"{settings.pg_database} as {settings.pg_user} ...")
    try:
        with psycopg.connect(
            host=settings.pg_host,
            port=settings.pg_port,
            dbname=settings.pg_database,
            user=settings.pg_user,
            password=settings.pg_password,
            autocommit=False,
        ) as conn:
            print("  connected.")
            for f in DDL_FILES:
                run_sql_file(conn, f)
            if args.reset_audit:
                clear_audit_tables(conn)
            else:
                print("\n=== Audit tables preserved (use --reset-audit to clear) ===")
            conn.commit()
        msg = "All DDL applied"
        if args.reset_audit:
            msg += " and audit tables cleared"
        print(f"\n{msg} successfully.")
        return 0
    except psycopg.Error as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
