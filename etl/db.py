"""
Database engine + session helpers for the ETL layer.
Reads connection params from config/settings.py (which reads .env).
"""
from __future__ import annotations

import math
import re
from contextlib import contextmanager
from typing import Callable, Iterable

from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import settings


_engine: Engine | None = None
_SessionFactory = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.sqlalchemy_url, future=True, pool_pre_ping=True)
    return _engine


def get_session_factory():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _SessionFactory


@contextmanager
def session_scope() -> Session:
    """Transactional session. Commits on success, rolls back on error."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Regex for a syntactically valid SQL identifier (unquoted): starts with a letter
# or underscore, contains only letters/digits/underscores. Postgres unquoted
# identifiers are case-insensitive and folded to lowercase, but we use this only
# as a defensive check; the real safety comes from the allow-list.
_SQL_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def safe_ident(name: str, allowed: Iterable[str]) -> str:
    """
    Validate `name` as a SQL identifier suitable for interpolation into an
    f-string SQL fragment. The name must:
        1. Match [A-Za-z_][A-Za-z0-9_]*, AND
        2. Appear in `allowed` (a set, list, or other iterable of known names).

    Raises ValueError on mismatch. Use this anywhere a column or table name
    flows from a request body, query param, or other untrusted source into
    raw SQL — the typical f"... ORDER BY {col} ..." pattern.

    Returns the validated name unchanged so callers can write:
        order_clause = f"ORDER BY {safe_ident(sort_by, col_names)} DESC"
    """
    if not isinstance(name, str) or not _SQL_IDENT_RE.match(name):
        raise ValueError(f"invalid SQL identifier: {name!r}")
    allowed_set = allowed if isinstance(allowed, (set, frozenset)) else set(allowed)
    if name not in allowed_set:
        raise ValueError(f"identifier not in allow-list: {name!r}")
    return name



# --- reflection cache ---------------------------------------------------------

_metadata: MetaData | None = None


def get_metadata() -> MetaData:
    """Reflect schema once and cache."""
    global _metadata
    if _metadata is None:
        md = MetaData()
        md.reflect(bind=get_engine())
        _metadata = md
    return _metadata


def get_table(name: str) -> Table:
    md = get_metadata()
    if name not in md.tables:
        # Reflect on demand in case of new tables created during runtime.
        md.reflect(bind=get_engine(), only=[name], extend_existing=True)
    return md.tables[name]


# --- bulk insert helpers ------------------------------------------------------

_BATCH_SIZE = 1000  # max rows per INSERT to stay under PostgreSQL's 65535-param limit (safe margin for 57-col tables)

def insert_skip_duplicates(session: Session, table_name: str,
                           rows: Iterable[dict],
                           progress_cb: Callable[[int, int, int, int], None] | None = None,
                           update_on_conflict_cols: list[str] | None = None) -> tuple[int, int]:
    """
    Bulk INSERT with ON CONFLICT DO NOTHING (or DO UPDATE), committed per batch.
    Returns (n_attempted, n_inserted). Skipped rows are silently dropped.

    progress_cb(batch_num, total_batches, n_inserted_so_far, n_skipped_so_far) called after each commit.

    update_on_conflict_cols: if set, use ON CONFLICT DO UPDATE for these columns instead of DO NOTHING.
                             Allows reloads to update specific metadata columns (e.g. ['source_file']).
    """
    rows = list(rows)
    n_attempted = len(rows)
    if not rows:
        return 0, 0

    # Normalize: all dicts must have the same key set for bulk insert
    all_keys = {k for row in rows for k in row}
    rows = [{k: row.get(k) for k in all_keys} for row in rows]

    table = get_table(table_name)
    pk_cols = [col.name for col in table.primary_key]
    n_inserted = 0
    total_batches = math.ceil(len(rows) / _BATCH_SIZE)

    for batch_idx, i in enumerate(range(0, len(rows), _BATCH_SIZE), start=1):
        batch = rows[i:i + _BATCH_SIZE]
        batch_size = len(batch)
        stmt = pg_insert(table).values(batch)

        if update_on_conflict_cols:
            # ON CONFLICT DO UPDATE only for specified columns
            update_dict = {col: stmt.excluded[col] for col in update_on_conflict_cols if col in all_keys}
            stmt = stmt.on_conflict_do_update(index_elements=pk_cols, set_=update_dict)
        else:
            stmt = stmt.on_conflict_do_nothing()

        result = session.execute(stmt)
        # PostgreSQL returns rowcount=-1 for ON CONFLICT DO NOTHING (unknown).
        # If successful with no error, assume all rows were processed.
        if result.rowcount is not None and result.rowcount >= 0:
            n_inserted += result.rowcount
        elif result.rowcount == -1:
            n_inserted += batch_size  # Assume all rows inserted if no error

        session.commit()

        if progress_cb:
            n_skipped = (i + batch_size) - n_inserted
            progress_cb(batch_idx, total_batches, n_inserted, n_skipped)

    return n_attempted, max(0, n_inserted)


def insert_upsert(session: Session, table_name: str,
                  rows: Iterable[dict],
                  progress_cb: Callable[[int, int, int, int], None] | None = None,
                  conflict_columns: list[str] | None = None) -> tuple[int, int]:
    """
    Bulk INSERT with ON CONFLICT DO UPDATE for all non-PK, non-audit columns,
    committed per batch.

    Conflict target:
      • By default, uses the table's PRIMARY KEY columns.
      • If `conflict_columns` is provided, uses those instead. This is the
        path for tables with a surrogate `id` PK + a separate UNIQUE
        NULLS NOT DISTINCT constraint on the natural key — pass the natural
        key here. `conflict_columns` is ALSO used for in-batch dedup so a
        single batch doesn't violate "command cannot affect row a second time".

    If table has export_time column, only update if export_time differs.
    Otherwise, always update data columns.
    Used for hist_* tables so re-loading a file for the same date overwrites
    the existing row if export_time changed, otherwise ignores it.
    Returns (n_attempted, n_upserted).

    progress_cb(batch_num, total_batches, n_upserted_so_far, n_skipped_so_far) called after each commit.
    """
    rows = list(rows)
    n_attempted = len(rows)
    if not rows:
        return 0, 0

    all_keys = {k for row in rows for k in row}
    rows = [{k: row.get(k) for k in all_keys} for row in rows]

    table = get_table(table_name)
    pk_cols = {col.name for col in table.primary_key}
    # Caller may override the conflict target (for surrogate-PK tables that
    # have a separate UNIQUE constraint on the natural key).
    if conflict_columns:
        pk_list = list(conflict_columns)
        # Don't try to UPDATE the natural-key columns we're conflicting on,
        # AND don't try to UPDATE the surrogate `id` PK (auto-managed).
        pk_cols = set(conflict_columns) | pk_cols
    else:
        pk_list = list(pk_cols)

    # Check if table has export_time column
    has_export_time = "export_time" in {col.name for col in table.columns}

    # Deduplicate by PK within each batch (keep last occurrence of each key).
    # This prevents "ON CONFLICT DO UPDATE command cannot affect row a second time" error
    # when the same PK appears multiple times in the input.
    # Single-pass O(n) via dict; last write wins. The previous O(n²) list rebuild
    # blew up at 50k+ rows (hist_td) with MemoryError.
    by_pk: dict = {}
    for row in rows:
        pk_key = tuple(row.get(col) for col in pk_list)
        by_pk[pk_key] = row
    deduplicated_rows = list(by_pk.values())

    # loaded_at keeps its original value; only data columns are overwritten
    skip_cols = pk_cols | {"loaded_at"}
    update_cols = [k for k in all_keys if k not in skip_cols]

    n_upserted = 0
    total_batches = math.ceil(len(deduplicated_rows) / _BATCH_SIZE)

    for batch_idx, i in enumerate(range(0, len(deduplicated_rows), _BATCH_SIZE), start=1):
        batch = deduplicated_rows[i:i + _BATCH_SIZE]
        batch_size = len(batch)
        stmt = pg_insert(table).values(batch)
        if update_cols:
            set_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
            if has_export_time:
                # Check if source_file is in the columns being updated.
                # If so, always update (remove WHERE clause) to allow reprocessing to refresh source_file.
                # Otherwise, only update if export_time is different.
                safe_table = safe_ident(table_name, {table.name})
                if "source_file" in set_dict:
                    # Always update when source_file is present (reprocessing case)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=pk_list,
                        set_=set_dict,
                    )
                else:
                    # Conditionally update if export_time differs
                    where_clause = text(f"EXCLUDED.export_time IS DISTINCT FROM {safe_table}.export_time")
                    stmt = stmt.on_conflict_do_update(
                        index_elements=pk_list,
                        set_=set_dict,
                        where=where_clause,
                    )
            else:
                # No export_time: always update
                stmt = stmt.on_conflict_do_update(
                    index_elements=pk_list,
                    set_=set_dict,
                )
        else:
            stmt = stmt.on_conflict_do_nothing()
        result = session.execute(stmt)
        # PostgreSQL may return rowcount=-1 for ON CONFLICT clauses (unknown).
        # If successful, assume all rows were processed.
        if result.rowcount is not None and result.rowcount >= 0:
            n_upserted += result.rowcount
        elif result.rowcount == -1:
            n_upserted += batch_size

        session.commit()

        if progress_cb:
            n_skipped = (i + batch_size) - n_upserted
            progress_cb(batch_idx, total_batches, n_upserted, n_skipped)

    return n_attempted, max(0, n_upserted)


def replace_for_date(session: Session, table_name: str,
                     date_column: str, date_value,
                     rows: Iterable[dict]) -> int:
    """
    Atomic 'rebuild for one date':
        1. DELETE WHERE date_column = date_value
        2. Bulk INSERT new rows
    Single transaction, committed by session_scope at the end.
    Returns the number of rows inserted.
    """
    rows = list(rows)
    if not rows:
        # Still delete the existing rows for this date — caller expects an
        # idempotent rebuild even if the source is empty for this date.
        session.execute(
            text(f"DELETE FROM {table_name} WHERE {date_column} = :d"),
            {"d": date_value},
        )
        return 0

    safe_table = safe_ident(table_name, {table_name})
    safe_col   = safe_ident(date_column, {date_column})
    session.execute(
        text(f"DELETE FROM {safe_table} WHERE {safe_col} = :d"),
        {"d": date_value},
    )

    table = get_table(table_name)
    # Insert in batches to avoid hitting parameter limits on huge rebuilds.
    n_inserted = 0
    for i in range(0, len(rows), _BATCH_SIZE):
        batch = rows[i:i + _BATCH_SIZE]
        session.execute(table.insert(), batch)
        n_inserted += len(batch)
    return n_inserted
