"""
Retention runner. Deletes hist_* rows older than the policy in
meta_cleanup_policy and logs each run to meta_cleanup_history.

NOTE: This deletes ONLY rows, never tables. The policy is per table:
  - table_name      e.g. 'hist_y'
  - date_column     e.g. 'snapshot_date' or 'event_date' or 'imported_date'
  - retention_days  e.g. 365
  - enabled         skip when FALSE

Run order:
  1. Compute cutoff = today - retention_days for each policy
  2. DELETE FROM <table_name> WHERE <date_column> < cutoff
  3. INSERT a row into meta_cleanup_history

Usage:
    python -m etl.cleanup                   # apply all enabled policies
    python -m etl.cleanup --table hist_y    # only one table
    python -m etl.cleanup --dry-run         # report what would be deleted
"""
from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import settings
from etl.db import get_table, safe_ident, session_scope

from etl._logging import setup_logging
setup_logging()
log = logging.getLogger("cleanup")


def list_policies(session: Session, table: Optional[str] = None) -> list[dict]:
    sql = """
        SELECT table_name, date_column, retention_days, enabled, notes
        FROM meta_cleanup_policy
    """
    if table:
        sql += " WHERE table_name = :t"
        rows = session.execute(text(sql), {"t": table}).mappings().all()
    else:
        rows = session.execute(text(sql)).mappings().all()
    return [dict(r) for r in rows]


def _validate_policy_target(table: str, date_col: str) -> tuple[str, str]:
    """
    Reflect the table from SQLAlchemy MetaData and confirm date_col exists on it.
    Raises ValueError if either is unknown. Returns the validated names so callers
    can safely interpolate them into an f-string SQL.
    """
    t = get_table(table)
    safe_table = safe_ident(table, {t.name})
    safe_col = safe_ident(date_col, {c.name for c in t.columns})
    return safe_table, safe_col


def count_to_delete(session: Session, table: str, date_col: str, cutoff: date) -> int:
    """Return how many rows would be deleted by the cutoff."""
    # date_col may be a TEXT column (e.g. for_month in hist_ismh) - in that
    # case the comparison is lexicographic; we still use the same SQL because
    # ISO dates and 'YYYY-MM' both compare correctly lexicographically.
    safe_table, safe_col = _validate_policy_target(table, date_col)
    sql = f"SELECT COUNT(*) FROM {safe_table} WHERE {safe_col} < :c"
    return int(session.execute(text(sql), {"c": cutoff}).scalar() or 0)


def delete_older_than(session: Session, table: str, date_col: str, cutoff: date) -> int:
    safe_table, safe_col = _validate_policy_target(table, date_col)
    sql = f"DELETE FROM {safe_table} WHERE {safe_col} < :c"
    result = session.execute(text(sql), {"c": cutoff})
    return result.rowcount or 0


def log_cleanup(session: Session, table: str, cutoff: date, rows_deleted: int) -> None:
    cleanup_table = get_table("meta_cleanup_history")
    session.execute(
        cleanup_table.insert().values(
            table_name=table,
            deleted_before_date=cutoff,
            rows_deleted=rows_deleted,
        )
    )


def run_cleanup(table_filter: Optional[str] = None, dry_run: bool = False,
                today: Optional[date] = None) -> dict[str, int]:
    """
    Execute retention. Returns {table_name: rows_deleted}.
    Each policy is applied in its own transaction so a failure on one table
    doesn't undo the others.
    """
    if today is None:
        today = date.today()

    summary: dict[str, int] = {}

    with session_scope() as s_init:
        policies = list_policies(s_init, table_filter)

    if not policies:
        log.warning("No matching policies in meta_cleanup_policy.")
        return summary

    for pol in policies:
        if not pol["enabled"]:
            log.info("[%s] disabled - skipping", pol["table_name"])
            continue
        retention = int(pol["retention_days"] or settings.default_retention_days)
        cutoff = today - timedelta(days=retention)

        try:
            with session_scope() as s:
                n = count_to_delete(s, pol["table_name"], pol["date_column"], cutoff)
                if dry_run:
                    log.info("[%s] DRY-RUN: would delete %d rows where %s < %s "
                             "(retention=%d days)",
                             pol["table_name"], n, pol["date_column"], cutoff, retention)
                    summary[pol["table_name"]] = n
                    continue

                if n == 0:
                    log.info("[%s] nothing to delete (cutoff=%s, retention=%d days)",
                             pol["table_name"], cutoff, retention)
                    log_cleanup(s, pol["table_name"], cutoff, 0)
                    summary[pol["table_name"]] = 0
                    continue

                deleted = delete_older_than(s, pol["table_name"],
                                            pol["date_column"], cutoff)
                log_cleanup(s, pol["table_name"], cutoff, deleted)
                log.info("[%s] deleted %d rows older than %s (retention=%d days)",
                         pol["table_name"], deleted, cutoff, retention)
                summary[pol["table_name"]] = deleted
        except Exception as e:
            log.exception("[%s] cleanup FAILED: %s", pol["table_name"], e)
            summary[pol["table_name"]] = -1

    return summary


# Meta-tables grow unbounded if never pruned. By default keep 90 days.
META_RETENTION_DAYS = 90
META_PRUNE = [
    ("meta_etl_run",         "started_at"),
    ("meta_derived_run",     "started_at"),
    ("meta_cleanup_history", "cleanup_at"),
]


def cleanup_meta_tables(dry_run: bool = False,
                        retention_days: int = META_RETENTION_DAYS) -> dict[str, int]:
    """Prune old rows from meta_* observability tables.

    Independent of meta_cleanup_policy — those policies are for *hist_* raw
    data, which must be governed explicitly. The meta_* tables are operational
    bookkeeping and are safe to prune on a fixed schedule.
    """
    cutoff_sql = f"now() - INTERVAL '{int(retention_days)} days'"
    summary: dict[str, int] = {}
    with session_scope() as s:
        for table, col in META_PRUNE:
            safe_t = safe_ident(table, {table})
            safe_c = safe_ident(col, {col})
            try:
                n = int(s.execute(text(
                    f"SELECT COUNT(*) FROM {safe_t} WHERE {safe_c} < {cutoff_sql}"
                )).scalar() or 0)
                if dry_run:
                    log.info("[%s] DRY-RUN: would prune %d rows (older than %d days)",
                             table, n, retention_days)
                    summary[table] = n
                    continue
                if n == 0:
                    summary[table] = 0
                    continue
                res = s.execute(text(
                    f"DELETE FROM {safe_t} WHERE {safe_c} < {cutoff_sql}"
                ))
                summary[table] = res.rowcount or 0
                log.info("[%s] pruned %d rows (retention %d days)",
                         table, summary[table], retention_days)
            except Exception as e:
                log.exception("[%s] meta prune FAILED: %s", table, e)
                summary[table] = -1
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", default=None,
                        help="Only run cleanup for this table_name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report counts but don't delete")
    parser.add_argument("--meta", action="store_true",
                        help="Also prune meta_etl_run / meta_derived_run / "
                             "meta_cleanup_history older than 90 days")
    parser.add_argument("--meta-only", action="store_true",
                        help="Run only the meta_* prune; skip hist_* policies")
    parser.add_argument("--retention-days", type=int, default=META_RETENTION_DAYS,
                        help=f"Meta retention in days (default {META_RETENTION_DAYS})")
    args = parser.parse_args()

    if not settings.pg_password:
        log.error("PG_PASSWORD is empty in .env.")
        return 2

    summary: dict[str, int] = {}
    if not args.meta_only:
        summary.update(run_cleanup(table_filter=args.table, dry_run=args.dry_run))
    if args.meta or args.meta_only:
        meta_sum = cleanup_meta_tables(dry_run=args.dry_run,
                                       retention_days=args.retention_days)
        summary.update(meta_sum)

    total = sum(v for v in summary.values() if v >= 0)
    failed = sum(1 for v in summary.values() if v < 0)
    log.info("done. total rows %s: %d (across %d tables, %d failed)",
             "that WOULD be deleted" if args.dry_run else "deleted",
             total, len(summary), failed)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
