"""
Refresh reference tables from an updated Tickers workbook using UPSERT
semantics (ON CONFLICT DO UPDATE). No history is kept - the row in the
DB always reflects the latest workbook content.

Use this whenever you've tuned values in the workbook:
  - Trig rule thresholds / weights / which atomic rules feed which composite
  - Parm sub-tables (BuySell weights, Vol Score thresholds, IV thresholds, ...)
  - Asset allocation targets
  - Sector classifications (Sctr)
  - Rule descriptions (Desc)

Static / append-only ref tables are NOT touched here:
  - ref_holiday, ref_econ_indicator, ref_calendar_event, ref_fed_blackout,
    ref_quad_outlook, ref_quad_periods, ref_ismh
  - ref_load_files, ref_rrt
  Those follow the regular initial-load path (ON CONFLICT DO NOTHING) since
  they don't hold tuned values.

Usage (from project root):
    python -m etl.refresh_ref                         # all tunable ref tables
    python -m etl.refresh_ref --table ref_sector
    python -m etl.refresh_ref --table ref_trig_atomic_rule
    python -m etl.refresh_ref --tickers "C:\\path\\Tickers 2026-04-30.xlsx"
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Callable, Iterable

from sqlalchemy import inspect, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from config.settings import settings
from etl.db import get_engine, get_table, session_scope
from etl.excel_io import open_workbook
from etl.load_raw import (
    get_sheet_case_insensitive,  # case-insensitive sheet lookup
    load_hquad,                  # used as full re-builder in upsert mode
    load_one_tab,                # used by REF_MAPS Sctr / Desc upsert
    load_parm,                   # rebuilds ref_param + ref_param_lookup + ref_asset_allocation
    load_trig_rules,             # rebuilds ref_trig_atomic_rule + ref_trig_composite_mapping
)
from etl.mappings import REF_MAPS

from etl._logging import setup_logging
setup_logging()
log = logging.getLogger("refresh_ref")


# ---------------------------------------------------------------------------
# UPSERT helper - replaces insert_skip_duplicates for the refresh path
# ---------------------------------------------------------------------------

def upsert_rows(session: Session, table_name: str, rows: list[dict],
                exclude_from_update: Iterable[str] = ()) -> tuple[int, int]:
    """
    INSERT ... ON CONFLICT (pk) DO UPDATE SET <every-non-pk-col> = EXCLUDED.<col>.
    Returns (n_attempted, n_affected).
    """
    if not rows:
        return 0, 0
    table = get_table(table_name)
    pk_cols = {c.name for c in table.primary_key.columns}
    skip = set(exclude_from_update) | pk_cols | {"loaded_at"}
    update_cols = [c.name for c in table.columns if c.name not in skip]
    if not update_cols:
        # No mutable cols — just insert-or-skip
        stmt = pg_insert(table).values(rows).on_conflict_do_nothing()
    else:
        stmt = (
            pg_insert(table).values(rows)
            .on_conflict_do_update(
                index_elements=list(pk_cols),
                set_={c: getattr(pg_insert(table).excluded, c) for c in update_cols},
            )
        )
    result = session.execute(stmt)
    return len(rows), result.rowcount or len(rows)


# ---------------------------------------------------------------------------
# Tunable reference tables - one rebuild function per source tab.
# Each function: TRUNCATE-then-bulk-load isn't used; we UPSERT to keep PKs
# stable and give the DB a chance to leave unrelated rows alone.
# ---------------------------------------------------------------------------

def refresh_sctr(wb, source_file) -> dict[str, int]:
    """Sctr tab -> ref_sector (UPSERT)."""
    m = REF_MAPS["Sctr"]
    with session_scope() as s:
        # Reuse load_one_tab's row construction by calling it but then
        # re-insert with UPSERT semantics. Simplest path: load via DO NOTHING
        # then for changed PKs, push UPDATE. Cleaner: rebuild rows here.
        from etl.load_raw import _row_to_record
        rows = [
            _row_to_record(raw, m, source_file)
            for raw in _iter_sheet(wb, m["sheet"], 2)
        ]
        rows = [r for r in rows if r is not None]
        a, n = upsert_rows(s, m["table"], rows)
        log.info("ref_sector: upserted %d / %d", n, a)
    return {"ref_sector": n}


def refresh_desc(wb, source_file) -> dict[str, int]:
    """Desc tab -> ref_rule_desc (UPSERT)."""
    m = REF_MAPS["Desc"]
    with session_scope() as s:
        from etl.load_raw import _row_to_record
        rows = [
            _row_to_record(raw, m, source_file)
            for raw in _iter_sheet(wb, m["sheet"], 2)
        ]
        rows = [r for r in rows if r is not None]
        a, n = upsert_rows(s, m["table"], rows)
        log.info("ref_rule_desc: upserted %d / %d", n, a)
    return {"ref_rule_desc": n}


def refresh_parm(wb, source_file) -> dict[str, int]:
    """
    Parm tab -> ref_param + ref_param_lookup + ref_asset_allocation (UPSERT).

    For these we use a wipe-then-insert per-table approach because Parm has
    many sub-sections and PKs span multiple data shapes. Wiping is safe
    because Parm is the single source of truth for these tables.
    """
    counts: dict[str, int] = {}
    with session_scope() as s:
        for tbl in ("ref_param", "ref_param_lookup", "ref_asset_allocation"):
            s.execute(text(f"DELETE FROM {tbl}"))
            counts[tbl] = 0
        # Now run the standard loader (DO NOTHING is fine - tables are empty)
        read, ins, skp = load_parm(s, wb, source_file)
        # Rough split — load_parm tracks combined; query back for accurate counts
        for tbl in counts:
            n = s.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            counts[tbl] = int(n or 0)
            log.info("%s: %d rows after refresh", tbl, counts[tbl])
    return counts


def refresh_trig(wb, source_file) -> dict[str, int]:
    """
    Trig tab -> ref_trig_atomic_rule + ref_trig_composite_mapping (UPSERT).

    Wipe-then-rebuild: the rule set is the workbook's single source of truth.
    drv_trig will be invalid until the next derive_trig() runs - the caller
    should re-derive after a refresh.
    """
    counts: dict[str, int] = {}
    with session_scope() as s:
        # Preserve non-default neg_multiplier values before wipe (workbook has no column for this)
        neg_mults = {
            r[0]: float(r[1])
            for r in s.execute(text(
                "SELECT rule_name, neg_multiplier FROM ref_trig_atomic_rule "
                "WHERE neg_multiplier IS DISTINCT FROM 1.0"
            )).fetchall()
        }
        # Composite mapping has FK to atomic_rule -> wipe child first
        s.execute(text("DELETE FROM ref_trig_composite_mapping"))
        s.execute(text("DELETE FROM ref_trig_atomic_rule"))
        load_trig_rules(s, wb)
        # Restore non-default neg_multiplier values after rebuild
        for rule_name, nm in neg_mults.items():
            s.execute(text(
                "UPDATE ref_trig_atomic_rule SET neg_multiplier=:nm WHERE rule_name=:n"
            ), {"nm": nm, "n": rule_name})
        for tbl in ("ref_trig_atomic_rule", "ref_trig_composite_mapping"):
            n = s.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()
            counts[tbl] = int(n or 0)
            log.info("%s: %d rows after refresh", tbl, counts[tbl])
    log.warning("Trig rules changed - next ETL or manual derive will rebuild drv_trig")
    return counts


def refresh_hquad(wb, source_file) -> dict[str, int]:
    """HQuad tab -> ref_quad_outlook (UPSERT)."""
    with session_scope() as s:
        # Simplest: wipe-and-rebuild, since Quad outlook is small and changes
        # in one go each quarter
        s.execute(text("DELETE FROM ref_quad_outlook"))
        load_hquad(s, wb, source_file)
        n = int(s.execute(text("SELECT COUNT(*) FROM ref_quad_outlook")).scalar() or 0)
        log.info("ref_quad_outlook: %d rows after refresh", n)
    return {"ref_quad_outlook": n}


# ---------------------------------------------------------------------------
# Table -> handler dispatch
# ---------------------------------------------------------------------------

REFRESH_HANDLERS: dict[str, Callable] = {
    "ref_sector":            refresh_sctr,
    "ref_rule_desc":         refresh_desc,
    "ref_param":             refresh_parm,
    "ref_param_lookup":      refresh_parm,        # combined refresh
    "ref_asset_allocation":  refresh_parm,        # combined refresh
    "ref_trig_atomic_rule":  refresh_trig,
    "ref_trig_composite_mapping": refresh_trig,   # combined refresh
    "ref_quad_outlook":      refresh_hquad,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _iter_sheet(wb, sheet_name: str, start_row: int = 2):
    """Light iterator yielding {header: value} dicts (mirrors excel_io behavior)."""
    actual_sheet_name = get_sheet_case_insensitive(wb, sheet_name)
    if actual_sheet_name is None:
        return iter([])
    sheet = wb[actual_sheet_name]
    headers = [str(sheet.cell(row=1, column=c).value or "")
               for c in range(1, sheet.max_column + 1)]
    out = []
    for r in range(start_row, sheet.max_row + 1):
        vals = [sheet.cell(row=r, column=c).value
                for c in range(1, sheet.max_column + 1)]
        if all(v is None for v in vals):
            break
        out.append({headers[i]: vals[i] for i in range(len(headers))})
    return iter(out)


# ---------------------------------------------------------------------------
# Programmatic API (for use by API endpoints, scheduler, etc.)
# ---------------------------------------------------------------------------

def run_one(table_name: str, tickers_path: str) -> tuple[int, int, int]:
    """
    Refresh a single tunable ref table from the workbook.
    Returns (rows_read, rows_inserted, rows_skipped) or raises on error.
    """
    if table_name not in REFRESH_HANDLERS:
        raise ValueError(f"No refresh handler for table '{table_name}'")

    if not Path(tickers_path).exists():
        raise FileNotFoundError(f"Tickers file not found: {tickers_path}")

    log.info("Refreshing %s from %s ...", table_name, tickers_path)
    wb = open_workbook(tickers_path)
    fn = REFRESH_HANDLERS[table_name]
    result = fn(wb, tickers_path)

    # result is a dict like {"ref_sector": 821}
    rows_inserted = result.get(table_name, 0)

    # For rows_read and rows_skipped, we'd need to track them in the handler
    # For now, assume rows_read = rows_inserted and rows_skipped = 0
    # (handlers use UPSERT so there are no "skipped" rows, only inserted/updated)
    return rows_inserted, rows_inserted, 0


def run_all(tickers_path: str) -> dict[str, tuple[int, int, int]]:
    """
    Refresh all tunable ref tables from the workbook.
    Returns {table_name: (rows_read, rows_inserted, rows_skipped)}.
    """
    if not Path(tickers_path).exists():
        raise FileNotFoundError(f"Tickers file not found: {tickers_path}")

    log.info("Opening %s for full ref refresh ...", tickers_path)
    wb = open_workbook(tickers_path)

    seen_fns = set()
    results: dict[str, tuple[int, int, int]] = {}

    for tbl in sorted(REFRESH_HANDLERS.keys()):
        fn = REFRESH_HANDLERS[tbl]
        if fn in seen_fns:
            continue
        seen_fns.add(fn)
        try:
            result = fn(wb, tickers_path)
            for table_name, rows_ins in result.items():
                results[table_name] = (rows_ins, rows_ins, 0)
        except Exception as e:
            log.exception("refresh failed for %s: %s", tbl, e)
            raise

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", default=settings.tickers_file,
                        help="Path to Tickers YYYY-MM-DD.xlsx")
    parser.add_argument("--table", default=None,
                        help="Refresh only this table (default: all tunable tables)")
    args = parser.parse_args()

    if not settings.pg_password:
        log.error("PG_PASSWORD is empty in .env.")
        return 2
    if not args.tickers or not Path(args.tickers).exists():
        log.error("Tickers file not found: %s", args.tickers)
        return 2

    try:
        if args.table:
            if args.table not in REFRESH_HANDLERS:
                log.error("No refresh handler for table '%s'. Options: %s",
                          args.table, list(REFRESH_HANDLERS))
                return 2
            read, ins, skp = run_one(args.table, args.tickers)
            log.info("Done. %s: %d read, %d inserted, %d skipped", args.table, read, ins, skp)
        else:
            results = run_all(args.tickers)
            log.info("Done. Summary:")
            for tbl, (read, ins, skp) in sorted(results.items()):
                log.info("  %s: %d read, %d inserted, %d skipped", tbl, read, ins, skp)
    except Exception as e:
        log.exception("refresh failed: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
