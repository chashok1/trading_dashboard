"""
One-time loader for the full Tickers YYYY-MM-DD.xlsx workbook.

Two-step process per Step 3 of the original spec:
  Step A: load raw rows into ref_* and hist_* tables (skip duplicates)
  Step B: rebuild drv_* tables for the snapshot date

Usage (from project root):
    .venv\\Scripts\\activate
    python -m etl.tickers_initial_load
        # uses TICKERS_FILE / LOADFILES_FILE from .env

    # or pass the file paths explicitly:
    python -m etl.tickers_initial_load "C:\\path\\Tickers 2026-04-30.xlsx"
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from config.settings import settings
from etl.db import session_scope, query_one
from etl.derive import derive_all
from etl.excel_io import open_workbook
from etl.load_raw import (
    close_run, file_hash, load_data_tab_blackout, load_data_tab_calendar_events,
    load_data_tab_econ, load_data_tab_holidays, load_etfchg, load_hqds, load_hquad,
    load_iichg, load_loadfiles, load_one_tab, load_parm,
    load_trig_rules, open_run, parse_file_date_from_name,
)
from etl.mappings import HIST_MAPS, REF_MAPS

from etl._logging import setup_logging
setup_logging()
log = logging.getLogger("tickers_initial_load")


def step_a_load_raw(tickers_path: str, loadfiles_path: str | None) -> date:
    """Load all reference + history tabs. Returns snapshot_date parsed from filename.
    Commits after each table for progress tracking and resilience."""
    from sqlalchemy import text

    log.info("Opening Tickers workbook: %s", tickers_path)
    wb = open_workbook(tickers_path)

    file_name = Path(tickers_path).name
    fdate_str = parse_file_date_from_name(file_name)
    if not fdate_str:
        log.error("Could not parse YYYY-MM-DD from filename '%s'.", file_name)
        sys.exit(2)
    snapshot_date = datetime.strptime(fdate_str, "%Y-%m-%d").date()
    log.info("Snapshot date detected: %s", snapshot_date)

    fhash = file_hash(tickers_path)

    # Mark file as being processed (idempotent)
    with session_scope() as s:
        s.execute(text("""
            INSERT INTO meta_file_processed
                (file_path, file_hash, file_type, target_tab, file_date, processed_at)
            VALUES (:p, :h, 'Tickers', 'multi', :d, now())
            ON CONFLICT (file_path) DO UPDATE
              SET file_hash = EXCLUDED.file_hash,
                  processed_at = now()
        """), {"p": tickers_path, "h": fhash, "d": snapshot_date})

    n_loaded = 0
    n_skipped = 0
    total_rows_inserted = 0

    def _already_loaded(target_tab: str) -> bool:
        """Check if this tab from this file was already successfully loaded.

        Two-step verification (added 2026-05-10):
          1. meta_etl_run shows a prior status='success' row for (file, tab).
          2. The target table actually has at least one row.

        Step 2 protects against the failure mode where db.init_db drops the
        data table (e.g. the historical DROP TABLE IF EXISTS in 02_schema_hist
        before that was removed) but meta_etl_run keeps the success record.
        Without it, a wiped data table is never refilled because the gate
        believes the load is still good.
        """
        with session_scope() as s:
            from etl.db import query_all
            from sqlalchemy import text as _text
            result = query_all(s, """
                SELECT COUNT(*) FROM meta_etl_run
                WHERE file_path = :fp AND target_tab = :tt AND status = 'success'
            """, fp=tickers_path, tt=target_tab)
            has_run = (result[0][0] if result else 0) > 0
            if not has_run:
                return False
            # Probe the target table; only treat as loaded if it has rows.
            # ref_* tables, hist_*, drv_* and ref_trig_* all live in public.
            try:
                row = s.execute(_text(
                    f"SELECT 1 FROM {target_tab} LIMIT 1"
                )).first()
                if row is None:
                    log.warning("âš  %s: meta_etl_run says loaded but table is empty â€” will reload",
                               target_tab)
                    return False
                return True
            except Exception:
                # Table doesn't exist (yet) or unreadable â€” force reload
                return False

    # 2. LoadFiles (separate file - schedules)
    if loadfiles_path and Path(loadfiles_path).exists():
        if _already_loaded("ref_load_files"):
            log.info("âŠ˜ ref_load_files: already loaded, skipping")
            n_skipped += 1
        else:
            with session_scope() as s:
                run_id = open_run(s, file_path=loadfiles_path,
                                  file_type="LoadFiles", target_tab="ref_load_files")
                try:
                    read, ins, skp = load_loadfiles(s, loadfiles_path)
                    close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
                    log.info("[OK] ref_load_files: %d read, %d inserted, %d skipped", read, ins, skp)
                    n_loaded += 1
                    total_rows_inserted += ins
                except Exception as e:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                    log.error("âœ— ref_load_files FAILED: %s", str(e)[:500])
                    raise

    # 3. Reference tabs (Sctr, RRT, Desc, Miss)
    for key, m in REF_MAPS.items():
        table_name = m["table"]
        if _already_loaded(table_name):
            log.info("âŠ˜ %s: already loaded, skipping", table_name)
            n_skipped += 1
        else:
            with session_scope() as s:
                run_id = open_run(s, file_path=tickers_path,
                                  file_type="Tickers", target_tab=table_name)
                try:
                    read, ins, skp, skip_reasons = load_one_tab(s, wb, m, tickers_path, run_id=run_id)
                    close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp, skip_reasons=skip_reasons or None)
                    log.info("[OK] %s: %d read, %d inserted, %d skipped", table_name, read, ins, skp)
                    n_loaded += 1
                    total_rows_inserted += ins
                except Exception as e:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                    log.error("âœ— %s FAILED: %s", table_name, str(e)[:500])
                    raise
            # Verify rows were inserted
            with session_scope() as s:
                cnt = query_one(s, f"SELECT COUNT(*) FROM {table_name}")
                print(f"  [OK] {table_name}: {cnt[0] if cnt else 0} rows now in DB")

    # 4. Data-tab special-cases + Parm + HQuad + HQds
    for fn, name in [
        (load_data_tab_holidays,        "ref_holiday"),
        (load_data_tab_econ,            "ref_econ_indicator"),
        (load_data_tab_blackout,        "ref_fed_blackout"),
        (load_data_tab_calendar_events, "ref_calendar_event"),
        (load_parm,                     "ref_param + ref_param_lookup + ref_asset_allocation"),
        (load_hquad,                    "ref_quad_outlook"),
        (load_hqds,                     "ref_quad_periods"),
    ]:
        if _already_loaded(name):
            log.info("âŠ˜ %s: already loaded, skipping", name)
            n_skipped += 1
        else:
            with session_scope() as s:
                run_id = open_run(s, file_path=tickers_path,
                                  file_type="Tickers", target_tab=name)
                try:
                    read, ins, skp = fn(s, wb, tickers_path)
                    close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
                    log.info("[OK] %s: %d read, %d inserted, %d skipped", name, read, ins, skp)
                    n_loaded += 1
                    total_rows_inserted += ins
                except Exception as e:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                    log.error("âœ— %s FAILED: %s", name, str(e)[:500])
                    raise
            # Verify rows inserted (handle multi-table loaders)
            with session_scope() as s:
                if name == "ref_param + ref_param_lookup + ref_asset_allocation":
                    for tbl in ["ref_param", "ref_param_lookup", "ref_asset_allocation"]:
                        cnt = query_one(s, f"SELECT COUNT(*) FROM {tbl}")
                        print(f"  [OK] {tbl}: {cnt[0] if cnt else 0} rows now in DB")
                else:
                    cnt = query_one(s, f"SELECT COUNT(*) FROM {name}")
                    print(f"  [OK] {name}: {cnt[0] if cnt else 0} rows now in DB")

    # 5. Trig rule definitions
    if _already_loaded("ref_trig_rules"):
        log.info("âŠ˜ ref_trig_rules: already loaded, skipping")
        n_skipped += 1
    else:
        with session_scope() as s:
            run_id = open_run(s, file_path=tickers_path,
                              file_type="Tickers", target_tab="ref_trig_rules")
            try:
                read, ins, skp = load_trig_rules(s, wb)
                close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
                log.info("[OK] ref_trig_rules: %d read, %d inserted, %d skipped", read, ins, skp)
                n_loaded += 1
                total_rows_inserted += ins
            except Exception as e:
                close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                          status="error", error_msg=str(e)[:500])
                log.error("âœ— ref_trig_rules FAILED: %s", str(e)[:500])
                raise
        # Verify rows inserted (multi-table)
        with session_scope() as s:
            for tbl in ["ref_trig_atomic_rule", "ref_trig_composite_mapping"]:
                cnt = query_one(s, f"SELECT COUNT(*) FROM {tbl}")
                print(f"  [OK] {tbl}: {cnt[0] if cnt else 0} rows now in DB")

    # 6. History tabs (per HIST_MAPS)
    for key, m in HIST_MAPS.items():
        table_name = m["table"]
        if _already_loaded(table_name):
            log.info("âŠ˜ %s: already loaded, skipping", table_name)
            n_skipped += 1
        else:
            with session_scope() as s:
                run_id = open_run(s, file_path=tickers_path,
                                  file_type="Tickers", target_tab=table_name)
                try:
                    read, ins, skp, skip_reasons = load_one_tab(s, wb, m, tickers_path, run_id=run_id)
                    close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp, skip_reasons=skip_reasons or None)
                    log.info("[OK] %s: %d read, %d inserted, %d skipped", table_name, read, ins, skp)
                    n_loaded += 1
                    total_rows_inserted += ins
                except Exception as e:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                    log.error("âœ— %s FAILED: %s", table_name, str(e)[:500])
                    raise
            # Verify rows were inserted
            with session_scope() as s:
                cnt = query_one(s, f"SELECT COUNT(*) FROM {table_name}")
                print(f"  [OK] {table_name}: {cnt[0] if cnt else 0} rows now in DB")

    # 7. Custom history loaders (etfchg, IIchg, sss, ssL)
    for fn, name in [
        (load_etfchg, "hist_etfchg"),
        (load_iichg,  "hist_iichg"),
    ]:
        if _already_loaded(name):
            log.info("âŠ˜ %s: already loaded, skipping", name)
            n_skipped += 1
        else:
            with session_scope() as s:
                run_id = open_run(s, file_path=tickers_path,
                                  file_type="Tickers", target_tab=name)
                try:
                    read, ins, skp = fn(s, wb, tickers_path)
                    close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
                    log.info("[OK] %s: %d read, %d inserted, %d skipped", name, read, ins, skp)
                    n_loaded += 1
                    total_rows_inserted += ins
                except Exception as e:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                    log.error("âœ— %s FAILED: %s", name, str(e)[:500])
                    raise

    log.info("=== Step A summary: %d loaded, %d skipped, %d total rows inserted ===",
             n_loaded, n_skipped, total_rows_inserted)


def step_b_derive(snapshot_date: date) -> None:
    """Step B: re-derive drv_* tables for the given snapshot date + recent source dates."""
    from sqlalchemy import text

    log.info("=== Step B: derive_all(%s) ===", snapshot_date)
    with session_scope() as s:
        # Derive for the main snapshot date
        derive_all(s, snapshot_date)

        # Also derive for recent source dates where data exists
        # This captures changes in the source tables that would produce actionable signals
        source_dates = set()
        for table, date_col in [
            ("hist_rr", "snapshot_date"),
            ("hist_call", "snapshot_date"),
            ("hist_etf", "snapshot_date"),
            ("hist_ii", "snapshot_date"),
            ("hist_ps", "snapshot_date"),
            ("hist_sss", "snapshot_date"),
        ]:
            try:
                result = s.execute(text(f"""
                    SELECT DISTINCT {date_col} FROM {table}
                    WHERE {date_col} > :cutoff AND {date_col} <= :d
                    ORDER BY {date_col} DESC LIMIT 10
                """), {"d": snapshot_date, "cutoff": snapshot_date - timedelta(days=15)}).fetchall()
                for row in result:
                    if row[0]:
                        source_dates.add(row[0])
            except Exception as e:
                log.debug("Could not fetch dates from %s: %s", table, e)

        # Derive for each recent source date (skip if already derived for snapshot_date)
        for src_date in sorted(source_dates, reverse=True):
            if src_date != snapshot_date:
                log.info("=== Also deriving for source date %s ===", src_date)
                try:
                    derive_all(s, src_date)
                except Exception as e:
                    log.warning("Derive for %s failed: %s", src_date, e)

    log.info("=== Step B complete ===")


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="One-time initial load of the Tickers workbook.")
    p.add_argument("tickers_file", nargs="?", default=settings.tickers_file,
                   help="Path to the Tickers YYYY-MM-DD.xlsx workbook.")
    p.add_argument("--loadfiles", default=settings.loadfiles_file,
                   help="Path to the LoadFiles.xlsx schedule (optional).")
    p.add_argument("--no-derive", action="store_true",
                   help="Skip the derive step (Step B); load raw only.")
    args = p.parse_args()

    if not args.tickers_file:
        log.error("No Tickers file path given (positional arg or TICKERS_FILE in .env).")
        return 2
    tickers_path = str(Path(args.tickers_file).resolve())
    if not Path(tickers_path).exists():
        log.error("Tickers file not found: %s", tickers_path)
        return 2

    # Parse the snapshot date from the filename (YYYY-MM-DD anywhere in name)
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2})", Path(tickers_path).name)
    if not m:
        log.error("Could not parse YYYY-MM-DD from filename: %s", Path(tickers_path).name)
        return 2
    snapshot_date = datetime.strptime(m.group(1), "%Y-%m-%d").date()
    log.info("=== tickers_initial_load: %s  (snapshot_date=%s) ===",
             tickers_path, snapshot_date)

    step_a_load_raw(tickers_path, args.loadfiles)
    if not args.no_derive:
        step_b_derive(snapshot_date)
    log.info("=== DONE ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

