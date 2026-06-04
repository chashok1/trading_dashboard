"""
Reference data CRUD + data explorer endpoints.

This router handles:
1. Fetching ref_* tables (static/lookup data)
2. CRUD operations on ref_* tables (POST/PUT/DELETE)
3. Data explorer: fetching any non-ref table paginated by date
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from api._helpers import (
    discover_data_tables,
    discover_ref_tables,
    _apply_filter_rule,
    _lookup_filter_rule,
    _resolve_date,
    safe_ident,
)
from etl.db import session_scope, get_table

router = APIRouter()

# ---------------------------------------------------------------------------
# Symbol rename — dynamically discovers every table with symbol/tos_symbol
# ---------------------------------------------------------------------------

@router.post("/api/admin/rename-symbol", response_model=dict)
def rename_symbol(body: dict):
    """Rename a symbol across every table that stores symbol/tos_symbol.
    Discovers tables dynamically from information_schema so nothing is missed.
    Body: {"from": "VSCO", "to": "VSXY"}
    """
    old = (body.get("from") or "").strip().upper()
    new = (body.get("to") or "").strip().upper()
    if not old or not new:
        raise HTTPException(status_code=400, detail="from and to are required")
    if old == new:
        raise HTTPException(status_code=400, detail="from and to are the same")

    counts: dict = {}
    with session_scope() as s:
        # Discover all real tables (not views) with symbol and/or tos_symbol
        col_rows = s.execute(text("""
            SELECT t.table_name, array_agg(c.column_name) AS cols
            FROM information_schema.tables t
            JOIN information_schema.columns c
              ON c.table_name = t.table_name AND c.table_schema = 'public'
            WHERE t.table_schema = 'public'
              AND t.table_type = 'BASE TABLE'
              AND c.column_name IN ('symbol', 'tos_symbol')
            GROUP BY t.table_name
            ORDER BY t.table_name
        """)).mappings().all()

        for row in col_rows:
            tbl  = row["table_name"]
            cols = set(row["cols"])
            has_sym = "symbol"     in cols
            has_tos = "tos_symbol" in cols
            try:
                with s.begin_nested():
                    if has_sym and has_tos:
                        r = s.execute(text(
                            f'UPDATE "{tbl}" SET symbol=:new, tos_symbol=:new '
                            f'WHERE symbol=:old OR tos_symbol=:old'
                        ), {"new": new, "old": old})
                    elif has_tos:
                        r = s.execute(text(
                            f'UPDATE "{tbl}" SET tos_symbol=:new WHERE tos_symbol=:old'
                        ), {"new": new, "old": old})
                    else:
                        r = s.execute(text(
                            f'UPDATE "{tbl}" SET symbol=:new WHERE symbol=:old'
                        ), {"new": new, "old": old})
                    if r.rowcount:
                        counts[tbl] = r.rowcount
            except Exception:
                pass  # skip tables that fail (e.g. views, FKs)

        s.commit()

    total = sum(counts.values())
    return {"ok": True, "from": old, "to": new, "total_rows": total, "by_table": counts}


@router.get("/api/admin/missing-symbols", response_model=list)
def get_missing_symbols():
    """Symbols in drv_cat_atomic_input (latest date) missing from hist_tw or hist_td."""
    with session_scope() as s:
        rows = s.execute(text("""
            SELECT d.tos_symbol,
                   CASE WHEN tw.tos_symbol IS NULL THEN true ELSE false END AS missing_tw,
                   CASE WHEN td.tos_symbol IS NULL THEN true ELSE false END AS missing_td
            FROM drv_cat_atomic_input d
            LEFT JOIN (
                SELECT DISTINCT tos_symbol FROM hist_tw
            ) tw ON tw.tos_symbol = d.tos_symbol
            LEFT JOIN (
                SELECT DISTINCT tos_symbol FROM hist_td
            ) td ON td.tos_symbol = d.tos_symbol
            WHERE d.as_of_date = (SELECT MAX(as_of_date) FROM drv_cat_atomic_input)
              AND (tw.tos_symbol IS NULL OR td.tos_symbol IS NULL)
            ORDER BY d.tos_symbol
        """)).mappings().all()
    return [dict(r) for r in rows]



# =============================================================================
# Pydantic models — API contracts
# =============================================================================

class RefTableColumn(BaseModel):
    name: str
    is_pk: bool


class RefTableData(BaseModel):
    table: str
    columns: list[RefTableColumn]
    rows: list[dict]
    total: int
    filter_description: Optional[str] = None


class DataTableMeta(BaseModel):
    name: str
    category: str
    row_count: int
    tunable: bool = True


class RefRowInsertResult(BaseModel):
    ok: bool
    inserted: int


class TableStats(BaseModel):
    name: str
    category: str
    date_col: Optional[str]
    total_rows: int
    rows_on_date: Optional[int]
    distinct_dates: Optional[int]
    min_date: Optional[str]
    max_date: Optional[str]


# =============================================================================
# Ref table CRUD
# =============================================================================

@router.get("/api/ref/tables", response_model=list[DataTableMeta])
def list_ref_tables():
    """List all ref_* tables with row counts."""
    result = []
    with session_scope() as s:
        for table_name in discover_ref_tables():
            try:
                count_row = s.execute(text(f"SELECT COUNT(*) FROM {table_name}")).first()
                row_count = count_row[0] if count_row else 0
            except Exception:
                row_count = 0

            result.append(DataTableMeta(
                name=table_name,
                category="ref",
                row_count=row_count,
            ))

    return sorted(result, key=lambda x: x.name)


@router.get("/api/ref/{table_name}", response_model=RefTableData)
def get_ref_table(
    table_name: str,
    date: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """Fetch a ref_* table (all rows, no date filtering)."""
    if table_name not in set(discover_ref_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown ref table: {table_name}")

    with session_scope() as s:
        table = get_table(table_name)
        pk_cols = {c.name for c in table.primary_key.columns}
        columns = [
            RefTableColumn(name=c.name, is_pk=(c.name in pk_cols))
            for c in table.columns
        ]

        sql = f"SELECT * FROM {table_name} LIMIT :lim OFFSET :off"
        rows_result = s.execute(text(sql), {"lim": limit, "off": offset}).mappings().all()
        rows = [dict(r) for r in rows_result]

        count_result = s.execute(text(f"SELECT COUNT(*) FROM {table_name}")).first()
        total = count_result[0] if count_result else 0

    return RefTableData(
        table=table_name,
        columns=columns,
        rows=rows,
        total=total,
        filter_description="all rows (ref table — no date filtering)",
    )


def _coerce_row_types(table, row_data: dict) -> dict:
    """Normalize incoming JSON values to the Python types psycopg expects.

    JSON has no native bool-string vs bool distinction in form payloads —
    browsers / form serializers commonly send "true"/"false" for checkboxes.
    psycopg refuses to coerce string → bool, so we do it here for any
    BOOLEAN column. Empty string → None so NULLs round-trip.
    """
    from sqlalchemy import Boolean
    out = dict(row_data)
    for col in table.columns:
        if col.name not in out:
            continue
        v = out[col.name]
        # Empty string anywhere → NULL (more forgiving for blank form fields).
        if v == "":
            out[col.name] = None
            continue
        if isinstance(col.type, Boolean) and isinstance(v, str):
            s = v.strip().lower()
            if s in ("true", "t", "1", "yes", "y"):
                out[col.name] = True
            elif s in ("false", "f", "0", "no", "n"):
                out[col.name] = False
            else:
                out[col.name] = None
    return out


@router.post("/api/ref/{table_name}", response_model=RefRowInsertResult)
def insert_ref_row(table_name: str, row_data: dict):
    """Insert a single row into a ref_* table.

    Returns 409 Conflict if row already exists (duplicate PK).
    """
    if table_name not in set(discover_ref_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown ref table: {table_name}")

    try:
        with session_scope() as s:
            table = get_table(table_name)
            row_data = _coerce_row_types(table, row_data)
            stmt = table.insert().values(**row_data)
            result = s.execute(stmt)
            n_inserted = result.rowcount
            s.commit()

            # Verify the insert actually happened (detect silent failures)
            if n_inserted == 0:
                raise HTTPException(status_code=500, detail="Insert returned 0 rows affected")

            return RefRowInsertResult(ok=True, inserted=n_inserted)

    except IntegrityError as e:
        if "duplicate key value" in str(e).lower() or "unique constraint" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="Row already exists (duplicate primary key)"
            )
        raise HTTPException(status_code=400, detail=f"Integrity error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert failed: {str(e)}")


@router.put("/api/ref/{table_name}", response_model=RefRowInsertResult)
def upsert_ref_row(table_name: str, row_data: dict):
    """Upsert (insert or update) a single row into a ref_* table using ON CONFLICT DO UPDATE.

    Requires the row dict to include all primary key columns.
    """
    if table_name not in set(discover_ref_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown ref table: {table_name}")

    try:
        with session_scope() as s:
            # Use raw SQL to execute Postgres UPSERT
            # Extract PK columns to construct the conflict clause
            table = get_table(table_name)
            row_data = _coerce_row_types(table, row_data)
            pk_cols = [c.name for c in table.primary_key.columns]
            if not pk_cols:
                raise HTTPException(status_code=400, detail="Table has no primary key for upsert")

            col_names = list(row_data.keys())
            col_placeholders = ", ".join(col_names)
            col_values = ", ".join(f":{col}" for col in col_names)
            pk_conflict = ", ".join(pk_cols)
            update_set = ", ".join(f"{col} = EXCLUDED.{col}" for col in col_names if col not in pk_cols)

            if not update_set:
                # All columns are PKs, so nothing to update
                update_set = f"{col_names[0]} = EXCLUDED.{col_names[0]}"

            sql = f"""
            INSERT INTO {table_name} ({col_placeholders})
            VALUES ({col_values})
            ON CONFLICT ({pk_conflict}) DO UPDATE SET {update_set}
            """

            result = s.execute(text(sql), row_data)
            s.commit()

            return RefRowInsertResult(ok=True, inserted=result.rowcount or 0)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upsert failed: {str(e)}")


@router.delete("/api/ref/{table_name}")
def delete_ref_row(table_name: str, row_data: dict):
    """Delete a single row from a ref_* table by primary key."""
    if table_name not in set(discover_ref_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown ref table: {table_name}")

    try:
        with session_scope() as s:
            table = get_table(table_name)
            pk_cols = [c.name for c in table.primary_key.columns]

            where_parts = [f"{col} = :{col}" for col in pk_cols]
            where_clause = " AND ".join(where_parts)
            sql = f"DELETE FROM {table_name} WHERE {where_clause}"

            # Extract only PK values
            pk_data = {col: row_data[col] for col in pk_cols if col in row_data}
            result = s.execute(text(sql), pk_data)
            s.commit()

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Row not found")

            return {"ok": True, "deleted": result.rowcount}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.patch("/api/ref/{table_name}/row")
def patch_ref_row(table_name: str, request_data: dict):
    """Update specific columns in a row, identified by primary key.

    Request body: {"pk": {...pk_cols}, "updates": {...non_pk_cols}}
    """
    if table_name not in set(discover_ref_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown ref table: {table_name}")

    pk = request_data.get("pk", {})
    updates = request_data.get("updates", {})

    if not pk:
        raise HTTPException(status_code=400, detail="Missing 'pk' in request")
    if not updates:
        raise HTTPException(status_code=400, detail="Missing 'updates' in request")

    try:
        with session_scope() as s:
            table = get_table(table_name)
            pk_cols = [c.name for c in table.primary_key.columns]

            where_parts = [f"{col} = :{col}" for col in pk_cols]
            where_clause = " AND ".join(where_parts)

            update_parts = [f"{col} = :{col}" for col in updates.keys()]
            if not update_parts:
                raise HTTPException(status_code=400, detail="No columns to update")

            update_clause = ", ".join(update_parts)
            sql = f"UPDATE {table_name} SET {update_clause} WHERE {where_clause}"

            # Combine pk and updates for parameters
            params = {**pk, **updates}
            result = s.execute(text(sql), params)
            s.commit()

            return {"ok": True, "updated": result.rowcount}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


# Also expose POST for backward compatibility (for simple inserts where duplicate PK is expected to fail)
@router.post("/api/ref/{table_name}/upsert", response_model=RefRowInsertResult)
def upsert_ref_row_endpoint(table_name: str, row_data: dict):
    """Alias for PUT to upsert a row."""
    return upsert_ref_row(table_name, row_data)


# Optional: GET a single row by PK (forward compatible but low priority)
@router.get("/api/ref/{table_name}/{pk_values}", response_model=Optional[dict])
def get_ref_row(table_name: str, pk_values: str):
    """Fetch a single row by comma-separated PK values (optional, low priority).

    Example: /api/ref/ref_sector/AAPL
    """
    if table_name not in set(discover_ref_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown ref table: {table_name}")

    try:
        with session_scope() as s:
            table = get_table(table_name)
            pk_cols = [c.name for c in table.primary_key.columns]

            # For now, assume single-column PK and pk_values is the raw value
            if len(pk_cols) != 1:
                raise HTTPException(status_code=400, detail="Multi-column PK not yet supported")

            where_clause = f"{pk_cols[0]} = :pk"
            sql = f"SELECT * FROM {table_name} WHERE {where_clause}"
            row = s.execute(text(sql), {"pk": pk_values}).mappings().first()

            if not row:
                raise HTTPException(status_code=404, detail="Row not found")

            return dict(row)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


# =============================================================================
# Data Explorer
# =============================================================================

print(f"[DEBUG] discover_data_tables() loaded with {len(discover_data_tables())} entries")
print(f"[DEBUG] drv_cat_* count: {len([k for k in discover_data_tables() if k.startswith('drv_cat_')])}")


@router.get("/api/data/tables", response_model=list[DataTableMeta])
def list_data_tables():
    """List all non-ref tables with row counts and date column info."""
    result = []
    with session_scope() as s:
        for table_name in discover_data_tables():
            _rule_lp = _lookup_filter_rule(s, table_name)
            date_col = _rule_lp['date_column'] if _rule_lp else None
            try:
                count_row = s.execute(text(f"SELECT COUNT(*) FROM {table_name}")).first()
                row_count = count_row[0] if count_row else 0
            except Exception:
                row_count = 0
            # Categorize: hist, drv, drv2, drv_cat, ref, meta, other
            if table_name.startswith("drv_cat_"):
                category = "drv_cat"
            elif table_name.startswith("drv_"):
                category = "drv"
            elif table_name.startswith("hist_"):
                category = "hist"
            elif table_name.startswith("ref_"):
                category = "ref"
            elif table_name.startswith("meta_"):
                category = "meta"
            else:
                category = "other"

            result.append(DataTableMeta(
                name=table_name,
                category=category,
                row_count=row_count,
            ))

    return sorted(result, key=lambda x: (x.category, x.name))


@router.get("/api/data/stats", response_model=list[TableStats])
def get_data_stats():
    """Get detailed stats for all data tables: total rows, rows for selected date, etc."""
    results: list[TableStats] = []

    with session_scope() as s:
        # Hist/drv tables with date awareness
        for table_name in [t for t in discover_data_tables() if t.startswith(("hist_", "drv_", "drv_cat_"))]:
            _rule = _lookup_filter_rule(s, table_name)
            date_col = _rule['date_column'] if _rule else None

            try:
                # Total rows
                cnt_row = s.execute(text(f"SELECT COUNT(*) FROM {table_name}")).first()
                total_rows = cnt_row[0] if cnt_row else 0

                # Rows on latest date
                rows_on_date = None
                distinct_dates = None
                min_date = None
                max_date = None

                if date_col:
                    # Count rows on the latest date
                    is_ts = False  # assume date col is DATE type
                    d_cast = f"{date_col}::date" if is_ts else date_col

                    max_d = s.execute(
                        text(f"SELECT MAX({d_cast}) FROM {table_name}")
                    ).scalar()
                    if max_d:
                        max_date = str(max_d)
                        d_cnt = s.execute(
                            text(f"SELECT COUNT(*) FROM {table_name} WHERE {d_cast} = :d"),
                            {"d": max_d}
                        ).first()
                        rows_on_date = d_cnt[0] if d_cnt else 0

                        # Distinct dates
                        dist = s.execute(
                            text(f"SELECT COUNT(DISTINCT {d_cast}) FROM {table_name}")
                        ).first()
                        distinct_dates = dist[0] if dist else 0

                        min_d = s.execute(
                            text(f"SELECT MIN({d_cast}) FROM {table_name}")
                        ).scalar()
                        min_date = str(min_d) if min_d else None

                cat = ("drv_cat" if table_name.startswith("drv_cat_") else
                       "drv" if table_name.startswith("drv_") else
                       "hist")

                results.append(TableStats(
                    name=table_name,
                    category=cat,
                    date_col=date_col,
                    total_rows=total_rows,
                    rows_on_date=rows_on_date,
                    distinct_dates=distinct_dates,
                    min_date=min_date,
                    max_date=max_date,
                ))
            except Exception as e:
                print(f"Error querying {table_name}: {e}")

        # Ref tables (no date awareness)
        for table_name in discover_ref_tables():
            try:
                cnt_row = s.execute(text(f"SELECT COUNT(*) FROM {table_name}")).first()
                row_count = cnt_row[0] if cnt_row else 0
                results.append(TableStats(
                    name=table_name,
                    category="ref",
                    date_col=None,
                    total_rows=row_count,
                    rows_on_date=None,
                    distinct_dates=None,
                    min_date=None,
                    max_date=None,
                ))
            except Exception as e:
                print(f"Error querying {table_name}: {e}")

    return sorted(results, key=lambda r: (r.category, r.name))


@router.get("/api/data/{table_name}", response_model=RefTableData)
def get_data_table(
    table_name: str,
    date: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    # Trig screen pulls drv_trig in one shot (~5000-50000 rows), so the cap is
    # generous. Pagination (`offset`) is still respected for screens that page.
    limit: int = Query(200, ge=1, le=100000),
    offset: int = Query(0, ge=0),
    sort_by: Optional[str] = Query(None),
    sort_dir: Optional[str] = Query("asc", pattern="^(asc|desc)$"),
):
    """Fetch data from any non-ref table using dashboard date with table-specific logic and optional sorting.

    Supports optional symbol filter for tables with a 'symbol' column.
    """
    if table_name not in set(discover_data_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown table: {table_name}")

    with session_scope() as _s_dc:
        _rule_dc = _lookup_filter_rule(_s_dc, table_name)
    date_col = _rule_dc['date_column'] if _rule_dc else None

    # Handle special "all" value to search all dates
    show_all_dates = (date == "all")
    d = _resolve_date(date) if (date_col and not show_all_dates) else None

    with session_scope() as s:
        table = get_table(table_name)
        pk_cols = {c.name for c in table.primary_key.columns}
        columns = [
            RefTableColumn(name=c.name, is_pk=(c.name in pk_cols))
            for c in table.columns
            if c.name not in {"loaded_at", "computed_at"}
        ]

        # Look up filter rule from ref_data_filter_logic and apply it.
        rule = _lookup_filter_rule(s, table_name)
        if show_all_dates:
            # User explicitly wants all dates - no date filter
            filter_description = "all rows across all dates"
            where_clause = ""
            params: dict = {"lim": limit, "off": offset}
        elif not rule and date_col:
            # Backwards compatibility: table not yet registered in ref_data_filter_logic.
            # Show all rows but make it visible in the UI.
            filter_description = f"no rule in ref_data_filter_logic for {table_name!r} - showing all rows"
            where_clause = ""
            params: dict = {"lim": limit, "off": offset}
        else:
            where_clause, extra_params, filter_description = _apply_filter_rule(
                s, table, table_name, rule, d
            )
            params: dict = {"lim": limit, "off": offset, **(extra_params or {})}

        # Add symbol filter if provided and table has a symbol or ticker column
        symbol_filter = ""
        if symbol:
            col_names = {c.name for c in table.columns}
            symbol_col = None
            if "tos_symbol" in col_names:
                symbol_col = "tos_symbol"
            elif "symbol" in col_names:
                symbol_col = "symbol"
            elif "ticker" in col_names:
                symbol_col = "ticker"

            if symbol_col:
                symbol_filter = f"AND {symbol_col} = :symbol" if where_clause else f"WHERE {symbol_col} = :symbol"
                params["symbol"] = symbol.upper()
                # Update filter description
                if filter_description:
                    filter_description += f" AND {symbol_col} = {symbol.upper()}"
                else:
                    filter_description = f"{symbol_col} = {symbol.upper()}"

            # Append the symbol filter to the WHERE we've built so far.
            if where_clause and symbol_filter:
                where_clause = where_clause + " " + symbol_filter
            elif symbol_filter:
                where_clause = symbol_filter

        # Determine ORDER BY. safe_ident enforces the allow-list of column names, defaulting to PK
        # for safe deterministic ordering.
        col_name_set = {c.name for c in table.columns}
        order_by = ""
        if sort_by and sort_by in col_name_set:
            direction = "DESC" if (sort_dir or "asc").lower() == "desc" else "ASC"
            order_by = f"ORDER BY {sort_by} {direction}"
        elif pk_cols:
            order_by = "ORDER BY " + ", ".join(sorted(pk_cols))

        sql = f"SELECT * FROM {table_name} {where_clause} {order_by} LIMIT :lim OFFSET :off"
        rows_result = s.execute(text(sql), params).mappings().all()
        rows = [dict(r) for r in rows_result]

        count_sql = f"SELECT COUNT(*) FROM {table_name} {where_clause}"
        # COUNT uses the same filter params except LIMIT/OFFSET.
        count_params = {k: v for k, v in params.items() if k not in ("lim", "off")}
        count_result = s.execute(text(count_sql), count_params).first()
        total = count_result[0] if count_result else 0

    return RefTableData(
        table=table_name,
        columns=columns,
        rows=rows,
        total=total,
        filter_description=filter_description,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Explore screen mutation endpoints — accept ANY discoverable data table.
# Mirrors the /api/ref/* logic but with the wider Explore guard. CLAUDE.md
# conventions #1/#2 ("never delete/overwrite raw data") are relaxed for this
# ad-hoc admin path — Explore is a power-user tool, handle with care.
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/api/data/{table_name}", response_model=RefRowInsertResult)
def insert_data_row(table_name: str, row_data: dict):
    """Insert a single row into any Explore-eligible table."""
    if table_name not in set(discover_data_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown data table: {table_name}")
    try:
        with session_scope() as s:
            table = get_table(table_name)
            row_data = _coerce_row_types(table, row_data)
            stmt = table.insert().values(**row_data)
            result = s.execute(stmt)
            n_inserted = result.rowcount
            s.commit()
            if n_inserted == 0:
                raise HTTPException(status_code=500, detail="Insert returned 0 rows affected")
            return RefRowInsertResult(ok=True, inserted=n_inserted)
    except IntegrityError as e:
        if "duplicate key value" in str(e).lower() or "unique constraint" in str(e).lower():
            raise HTTPException(status_code=409, detail="Row already exists (duplicate primary key)")
        raise HTTPException(status_code=400, detail=f"Integrity error: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Insert failed: {str(e)}")


@router.delete("/api/data/{table_name}")
def delete_data_row(table_name: str, row_data: dict):
    """Delete a single row from any Explore-eligible table by primary key."""
    if table_name not in set(discover_data_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown data table: {table_name}")
    try:
        with session_scope() as s:
            table = get_table(table_name)
            pk_cols = [c.name for c in table.primary_key.columns]
            if not pk_cols:
                raise HTTPException(status_code=400, detail="Table has no primary key - cannot delete by PK")
            pk_data = {col: row_data[col] for col in pk_cols if col in row_data}
            if len(pk_data) != len(pk_cols):
                missing = sorted(set(pk_cols) - set(pk_data))
                raise HTTPException(status_code=400, detail=f"Missing PK columns: {missing}")
            where_clause = " AND ".join(f"{col} = :{col}" for col in pk_cols)
            sql = f"DELETE FROM {table_name} WHERE {where_clause}"
            result = s.execute(text(sql), pk_data)
            s.commit()
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Row not found")
            return {"ok": True, "deleted": result.rowcount}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


@router.patch("/api/data/{table_name}/row")
def patch_data_row(table_name: str, request_data: dict):
    """Update specific columns in a row of any Explore-eligible table.

    Body: {"pk": {...pk_cols}, "updates": {...non_pk_cols}}
    Uses pk_/upd_ prefixed bind params so a column name appearing in both
    pk and updates can't collide.
    """
    if table_name not in set(discover_data_tables()):
        raise HTTPException(status_code=404, detail=f"Unknown data table: {table_name}")
    pk = request_data.get("pk", {})
    updates = request_data.get("updates", {})
    if not pk:
        raise HTTPException(status_code=400, detail="Missing 'pk' in request")
    if not updates:
        raise HTTPException(status_code=400, detail="Missing 'updates' in request")
    try:
        with session_scope() as s:
            table = get_table(table_name)
            updates = _coerce_row_types(table, updates)
            pk_cols = [c.name for c in table.primary_key.columns]
            where_clause = " AND ".join(f"{col} = :pk_{col}" for col in pk_cols)
            update_clause = ", ".join(f"{col} = :upd_{col}" for col in updates.keys())
            sql = f"UPDATE {table_name} SET {update_clause} WHERE {where_clause}"
            params = {f"pk_{k}": v for k, v in pk.items()}
            params.update({f"upd_{k}": v for k, v in updates.items()})
            result = s.execute(text(sql), params)
            s.commit()
            return {"ok": True, "updated": result.rowcount}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")
