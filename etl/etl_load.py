"""
Single-file loader for ongoing ETL.

Each source file is named '{Filetype} YYYY-MM-DD.xlsx' (e.g.
'PS 2026-04-25.xlsx'). The file_type maps via ref_load_files to a
target hist_* table.

Workflow per file:
  1. Compute SHA256 hash, see if already processed (meta_file_processed).
     If hash matches what we processed before -> skip silently.
  2. Copy source file to ETL_WORKING_DIR/<basename> (NEVER move/delete).
  3. Open workbook, find the sheet named after target_tab in ref_load_files.
  4. Look up the matching mapping in HIST_MAPS; load via load_one_tab.
  5. Mark meta_file_processed.
  6. Trigger derive_all() for the snapshot date parsed from filename.

Usage:
    python -m etl.etl_load <file_path> [--no-derive] [--type FILETYPE]
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from config.settings import settings
from etl.db import session_scope
from etl.derive import derive_all, get_anchor_date
from etl.excel_io import open_workbook
from etl.load_raw import (
    close_run, file_hash, load_etf, load_etfchg, load_iichg, load_one_tab,
    load_rr, load_tw, open_run, parse_file_date_from_name,
)
from etl.mark_sales import mark_cs_sales, mark_f_sales
from etl.mappings import HIST_MAPS

from etl._logging import setup_logging
setup_logging()
log = logging.getLogger("etl_load")


def load_ref_tables(session, wb, source_file):
    """
    Triggered when a Tickers workbook is detected by the folder monitor.
    Refreshes all tunable ref tables via run_all().
    """
    from etl.refresh_ref import run_all
    counts = run_all(source_file)
    total_read = sum(v[0] for v in counts.values())
    total_ins = sum(v[1] for v in counts.values())
    total_skp = sum(v[2] for v in counts.values())
    return total_read, total_ins, total_skp


# Custom-handler dispatch for source files whose tab layout doesn't fit
# the generic mapping pattern. Keys are file_type values from ref_load_files.
CUSTOM_HANDLERS = {
    # tab name -> custom function (session, wb, source_file) -> (read, ins, skp)
    "etf":    load_etf,
    "etfchg": load_etfchg,
    "iichg":  load_iichg,
    "rr":     load_rr,
    "tw":     load_tw,
    "ref_tickers": load_ref_tables,
    # 'miss' has no loader - it is a derived table only
}


def lookup_target_tab(session, file_type: str) -> Optional[str]:
    """Look up the target tab name from ref_load_files. file_type is case-insensitive.
    Returns the target_tab in lowercase for consistent HIST_MAPS lookups."""
    row = session.execute(text("""
        SELECT LOWER(target_tab) FROM ref_load_files
        WHERE LOWER(file_type) = LOWER(:ft) AND enabled = TRUE
        LIMIT 1
    """), {"ft": file_type}).first()
    return row[0] if row else None


def already_processed(session, file_path: str, file_mtime: float) -> bool:
    # Case-insensitive lookup so Windows path casing differences don't cause
    # spurious re-loads. Integer-seconds comparison because the stored column
    # is REAL (single-precision float, ~7 digits) and Unix epoch timestamps
    # need 10+ digits — REAL silently loses ~30 seconds of precision.
    row = session.execute(text("""
        SELECT file_mtime FROM meta_file_processed WHERE LOWER(file_path) = LOWER(:p)
    """), {"p": file_path}).first()
    return (bool(row) and row[0] is not None
            and abs(int(row[0]) - int(file_mtime)) <= 2)


def mark_processed(session, *, file_path: str, file_mtime: float,
                   file_type: str, target_tab: str,
                   file_dt: Optional[date], run_id: int) -> None:
    # Resolve source_kind: 'email' if emit.py registered this path, else 'file'
    sk_row = session.execute(text(
        "SELECT source_kind FROM meta_file_origin WHERE file_path=:p"
    ), {"p": file_path}).first()
    source_kind = sk_row[0] if sk_row else "file"
    session.execute(text("""
        INSERT INTO meta_file_processed
            (file_path, file_mtime, file_type, target_tab, file_date,
             processed_at, last_run_id, source_kind)
        VALUES (:p, :mt, :ft, :tab, :d, now(), :rid, :sk)
        ON CONFLICT (file_path) DO UPDATE
          SET file_mtime   = EXCLUDED.file_mtime,
              file_type    = EXCLUDED.file_type,
              target_tab   = EXCLUDED.target_tab,
              file_date    = EXCLUDED.file_date,
              processed_at = now(),
              last_run_id  = EXCLUDED.last_run_id,
              source_kind  = EXCLUDED.source_kind
    """), {"p": file_path, "mt": file_mtime, "ft": file_type, "tab": target_tab,
           "d": file_dt, "rid": run_id, "sk": source_kind})


def copy_to_working(src: Path) -> Path:
    """Copy source to ETL_WORKING_DIR. NEVER touches the original."""
    work_dir = Path(settings.etl_working_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    dst = work_dir / src.name
    shutil.copy2(str(src), str(dst))
    return dst


def infer_file_type(filename: str) -> Optional[str]:
    """
    Filename pattern: '{Filetype} YYYY-MM-DD.xlsx'.
    Returns the Filetype portion or None.
    File type inference is case-insensitive; lookup_target_tab will normalize it.
    """
    base = Path(filename).stem
    parts = base.split()
    if len(parts) < 2:
        return None
    # last token should be the date; everything before is the file type
    ft = " ".join(parts[:-1])
    return ft


def _log_anchor_warning(msg: str, file_name: str) -> None:
    """Surface a 'cannot anchor derive' problem to the scheduler log + DB."""
    log.warning(msg, extra={'file_name': file_name})
    logging.getLogger("scheduler").warning(msg, extra={'file_name': file_name})
    try:
        with session_scope() as s:
            s.execute(text("""
                INSERT INTO meta_scheduler_log (logged_at, message, log_level, file_name)
                VALUES (now(), :msg, 'WARNING', :fn)
            """), {"msg": msg, "fn": file_name})
    except Exception:
        log.exception("could not write anchor warning to meta_scheduler_log")


def load_one_file(file_path: str, file_type: Optional[str] = None,
                  do_derive: bool = True, force: bool = False) -> dict:
    """
    Process one source file. Returns a small status dict.
    If force=True, reprocess even if already processed (for reprocess button).
    """
    p = Path(file_path)
    if not p.exists():
        return {"status": "error", "msg": f"file not found: {file_path}"}

    # Handle CSV files (Schwab positions and transactions) separately before inferring file type.
    # Recognized filename patterns for Schwab transactions (file_type CST):
    #   - Anything containing "_Transactions_"  (Schwab's own export naming)
    #   - Anything starting with "CST "         (user-renamed files in the CST folder)
    if p.suffix.lower() == '.csv' and (
        '_Transactions_' in p.name
        or p.name.lower().startswith('cst ')
        or p.name.lower().startswith('cst_')
    ):
        from etl.load_raw import load_cs_transactions
        file_mtime = p.stat().st_mtime
        with session_scope() as s:
            if not force and already_processed(s, str(p), file_mtime):
                log.info("skipping %s (already processed; mtime unchanged)", p.name)
                return {"status": "skipped", "file_type": "CST", "target_tab": "hist_cst"}

            file_dt_str = parse_file_date_from_name(p.name)
            # If filename has no date, use file mtime
            if not file_dt_str and file_mtime:
                from datetime import datetime as dt_
                file_dt_str = dt_.fromtimestamp(file_mtime).strftime('%Y-%m-%d')
            run_id = open_run(s, file_path=str(p), file_type='CST', target_tab='hist_cst')
            # Commit now so the run record survives a later rollback in the
            # except block below (Postgres aborted-txn recovery would
            # otherwise silently discard this uncommitted INSERT too,
            # leaving close_run's error UPDATE matching zero rows).
            s.commit()
            try:
                read, ins, skp = load_cs_transactions(s, str(p), p.name)
                close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
                mark_processed(s, file_path=str(p), file_mtime=file_mtime,
                               file_type='CST', target_tab='hist_cst',
                               file_dt=file_dt_str, run_id=run_id)
                log.info("LOADED hist_cst: %d read, %d ins, %d skip", read, ins, skp)

                # Derive realized gains for all dates in the loaded transactions.
                # Two layers run in parallel:
                #   (a) legacy avg-cost-per-snapshot via derive_cs_realized_gain
                #       — feeds drv_cs_realized_gain, used by older dashboards
                #   (b) FIFO across all transactions via derive_realized_gain
                #       — feeds drv_realized_gain, used by the new Portfolio
                #         Realized tab. Mixes CS + F so a single rebuild keeps
                #         the picture consistent across both brokerages.
                if do_derive and ins > 0:
                    distinct_dates = s.execute(text("""
                        SELECT DISTINCT trade_date FROM hist_cst
                        ORDER BY trade_date DESC LIMIT 10
                    """)).scalars().all()
                    for trade_date in distinct_dates:
                        try:
                            from etl.derive import derive_cs_realized_gain
                            log.info("deriving realized gains for %s ...", trade_date)
                            with session_scope() as s2:
                                derive_cs_realized_gain(s2, trade_date)
                        except Exception as e:
                            log.exception("derive_cs_realized_gain failed for %s", trade_date)
                    try:
                        from etl.derive_realized import derive_realized_gain
                        with session_scope() as s2:
                            n_r = derive_realized_gain(s2)
                        log.info("drv_realized_gain rebuilt: %d sell-event rows", n_r)
                    except Exception:
                        log.exception("derive_realized_gain failed (continuing)")
            except Exception as e:
                # Roll back the aborted txn so close_run can write cleanly —
                # see /docs/CLAUDE.md "Working notes for Claude" on this trap.
                try: s.rollback()
                except Exception: pass
                try:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                except Exception:
                    log.exception("close_run failed for %s (continuing)", p.name)
                log.exception("load failed for %s", p.name)
                return {"status": "error", "msg": str(e)}
        return {"status": "loaded", "file_type": 'CST', "target_tab": 'hist_cst', "rows_inserted": ins}

    # Handle 401(k) "Contribution History" export (file_type F401K).
    # File arrives sporadically with overlapping date ranges (user re-exports
    # "since Jan 1" every month) so the loader is purely additive — natural-key
    # conflict skips re-runs. Recognized filename pattern: anything starting
    # with "F401K " (user names the file per the LoadFiles convention).
    if p.suffix.lower() == '.csv' and p.name.lower().startswith('f401k'):
        from etl.load_raw import load_401k_contributions
        file_mtime = p.stat().st_mtime
        with session_scope() as s:
            if not force and already_processed(s, str(p), file_mtime):
                log.info("skipping %s (already processed; mtime unchanged)", p.name)
                return {"status": "skipped", "file_type": "F401K", "target_tab": "hist_401k_contrib"}
            file_dt_str = parse_file_date_from_name(p.name)
            if not file_dt_str and file_mtime:
                from datetime import datetime as dt_
                file_dt_str = dt_.fromtimestamp(file_mtime).strftime('%Y-%m-%d')
            run_id = open_run(s, file_path=str(p), file_type='F401K',
                              target_tab='hist_401k_contrib')
            s.commit()
            try:
                read, ins, skp = load_401k_contributions(s, str(p), p.name)
                close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
                mark_processed(s, file_path=str(p), file_mtime=file_mtime,
                               file_type='F401K', target_tab='hist_401k_contrib',
                               file_dt=file_dt_str, run_id=run_id)
                log.info("LOADED hist_401k_contrib: %d read, %d ins, %d skip",
                         read, ins, skp)
            except Exception as e:
                try:
                    s.rollback()
                except Exception:
                    pass
                try:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                except Exception:
                    log.exception("close_run failed for %s (continuing)", p.name)
                log.exception("load failed for %s", p.name)
                return {"status": "error", "msg": str(e)}
        return {"status": "loaded", "file_type": 'F401K',
                "target_tab": 'hist_401k_contrib', "rows_inserted": ins}

    # Handle Fidelity Accounts_History.csv (transaction activity export).
    # File arrives sporadically (user downloads 6m or 1y at a time) so the
    # loader is purely additive — PK conflict skips re-runs.
    # Recognized filename patterns for Fidelity transactions (file_type FT):
    #   - Anything starting with "accounts_history"  (Fidelity's own export naming)
    #   - Anything starting with "history_for_account" (newer Fidelity export naming)
    #   - Anything starting with "FT "               (user-renamed files in the FT folder)
    if p.suffix.lower() == '.csv' and (
        p.name.lower().startswith('accounts_history')
        or p.name.lower().startswith('history_for_account')
        or p.name.lower().startswith('ft ')
        or p.name.lower().startswith('ft_')
    ):
        from etl.load_raw import load_f_transactions
        file_mtime = p.stat().st_mtime
        with session_scope() as s:
            if not force and already_processed(s, str(p), file_mtime):
                log.info("skipping %s (already processed; mtime unchanged)", p.name)
                return {"status": "skipped", "file_type": "FT", "target_tab": "hist_ft"}
            file_dt_str = parse_file_date_from_name(p.name)
            # If filename has no date (e.g., History_for_Account_*.csv), use file mtime
            if not file_dt_str and file_mtime:
                from datetime import datetime as dt_
                file_dt_str = dt_.fromtimestamp(file_mtime).strftime('%Y-%m-%d')
            run_id = open_run(s, file_path=str(p), file_type='FT',
                              target_tab='hist_ft')
            # Commit now so the run record survives a later rollback in the
            # except block below (see CST branch above for why).
            s.commit()
            try:
                read, ins, skp = load_f_transactions(s, str(p), p.name)
                close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
                mark_processed(s, file_path=str(p), file_mtime=file_mtime,
                               file_type='FT', target_tab='hist_ft',
                               file_dt=file_dt_str, run_id=run_id)
                log.info("LOADED hist_ft: %d read, %d ins, %d skip",
                         read, ins, skp)
                # Rebuild FIFO realized gains across BOTH sources after any
                # transaction file lands. derive_realized_gain is fast (single
                # in-memory pass per account/symbol) so this is fine to do
                # every time.
                if do_derive and ins > 0:
                    try:
                        from etl.derive_realized import derive_realized_gain
                        with session_scope() as s2:
                            n_r = derive_realized_gain(s2)
                        log.info("drv_realized_gain rebuilt: %d sell-event rows", n_r)
                    except Exception:
                        log.exception("derive_realized_gain failed (continuing)")
            except Exception as e:
                # The original error left the PG transaction in 'aborted'
                # state; any further write on the same session will raise
                # InFailedSqlTransaction. Roll back BEFORE the bookkeeping
                # write so close_run lands cleanly and the worker thread
                # doesn't die.
                try:
                    s.rollback()
                except Exception:
                    pass
                try:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                except Exception:
                    log.exception("close_run failed for %s (continuing)", p.name)
                log.exception("load failed for %s", p.name)
                return {"status": "error", "msg": str(e)}
        return {"status": "loaded", "file_type": 'FT',
                "target_tab": 'hist_ft', "rows_inserted": ins}

    # Handle CS positions CSV files separately
    if p.suffix.lower() == '.csv' and p.name.startswith('CS '):
        from etl.load_raw import load_cs_positions_csv
        file_mtime = p.stat().st_mtime
        file_dt_str = parse_file_date_from_name(p.name)
        file_dt = datetime.strptime(file_dt_str, "%Y-%m-%d").date() if file_dt_str else None

        with session_scope() as s:
            if not force and already_processed(s, str(p), file_mtime):
                log.info("skipping %s (already processed; mtime unchanged)", p.name)
                return {"status": "skipped", "file_type": "CS", "target_tab": "hist_cs"}

            run_id = open_run(s, file_path=str(p), file_type='CS', target_tab='hist_cs')
            # Commit now so the run record survives a later rollback in the
            # except block below (see CST branch earlier for why).
            s.commit()
            try:
                read, ins, skp = load_cs_positions_csv(s, str(p), p.name)
                close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
                mark_processed(s, file_path=str(p), file_mtime=file_mtime,
                               file_type='CS', target_tab='hist_cs',
                               file_dt=file_dt, run_id=run_id)
                log.info("LOADED hist_cs (CSV): %d read, %d ins, %d skip", read, ins, skp)

                # Derive for this date.
                # NOTE: do NOT re-import derive_all here — the module-level
                # import on line 34 covers it. A local `from … import …`
                # would make Python treat derive_all as a function-scoped
                # variable everywhere in load_one_file, breaking the
                # generic-loader branch below with UnboundLocalError.
                # Derive the ANCHOR date (MAX export_date in hist_td), not this
                # file's filename date. See get_anchor_date / docs/derive_date_logic.md.
                if do_derive and ins > 0:
                    try:
                        with session_scope() as s2:
                            anchor_d = get_anchor_date(s2)
                            if anchor_d is None:
                                _log_anchor_warning(
                                    f"{p.name}: loaded, but hist_td (TOSD) is empty "
                                    f"— cannot anchor a derive date.", p.name)
                            else:
                                log.info("deriving all tables for anchor %s ...", anchor_d)
                                derive_all(s2, anchor_d)
                    except Exception as e:
                        log.exception("derive_all failed for anchor date")
            except Exception as e:
                # Aborted-txn safe error path
                try: s.rollback()
                except Exception: pass
                try:
                    close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                              status="error", error_msg=str(e)[:500])
                except Exception:
                    log.exception("close_run failed for %s (continuing)", p.name)
                log.exception("load failed for %s", p.name)
                return {"status": "error", "msg": str(e)}
        return {"status": "loaded", "file_type": "CS", "target_tab": "hist_cs", "rows_inserted": ins}

    file_dt_str = parse_file_date_from_name(p.name)
    file_dt = datetime.strptime(file_dt_str, "%Y-%m-%d").date() if file_dt_str else None
    ft = file_type or infer_file_type(p.name)
    if not ft:
        return {"status": "error", "msg": f"could not infer file type from {p.name}"}

    file_mtime = p.stat().st_mtime

    with session_scope() as s:
        target_tab = lookup_target_tab(s, ft)
        if not target_tab:
            return {"status": "error",
                    "msg": f"file_type '{ft}' not in ref_load_files (run initial load first)"}

        if not force and already_processed(s, str(p), file_mtime):
            log.info("skipping %s (already processed; mtime unchanged)", p.name)
            return {"status": "skipped", "file_type": ft, "target_tab": target_tab}

    # Copy to working dir (preserve source per user rules)
    work_path = copy_to_working(p)
    log.info("copied %s -> %s", p, work_path)

    with session_scope() as s:
        run_id = open_run(s, file_path=str(p), file_type=ft, target_tab=target_tab)
        # Commit now so the run record survives a later rollback in the
        # except block below (see CST branch earlier for why).
        s.commit()
        all_rows_skipped = False
        try:
            wb = open_workbook(work_path)

            # Choose handler: custom function takes precedence; else mapping-driven
            custom_fn = CUSTOM_HANDLERS.get(target_tab.lower())
            skip_reasons = {}
            if custom_fn is not None:
                read, ins, skp = custom_fn(s, wb, str(p))
            else:
                # Find a HIST_MAPS entry whose `sheet` matches target_tab (case-insensitive)
                mapping = next((m for m in HIST_MAPS.values() if m["sheet"].lower() == target_tab.lower()), None)
                if mapping is None:
                    raise ValueError(f"no HIST_MAPS entry for sheet '{target_tab}'")
                read, ins, skp, skip_reasons = load_one_tab(s, wb, mapping, str(p), run_id=run_id)

            close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp, skip_reasons=skip_reasons or None)

            # For RR files the file name date is the email received date, but the
            # data date (snapshot_date in hist_rr) is the previous business day.
            # Override file_dt so meta_file_processed.file_date reflects the data date.
            if target_tab.lower() == "rr" and ins > 0:
                try:
                    actual_dt = s.execute(
                        text("SELECT MAX(snapshot_date) FROM hist_rr WHERE source_file = :fp"),
                        {"fp": str(p)},
                    ).scalar()
                    if actual_dt:
                        file_dt = actual_dt
                except Exception:
                    pass

            mark_processed(s, file_path=str(p), file_mtime=file_mtime,
                           file_type=ft, target_tab=target_tab,
                           file_dt=file_dt, run_id=run_id)
            log.info("LOADED %s: %d read, %d ins, %d skip", target_tab, read, ins, skp)

            # After loading positions, mark any sold positions by detecting missing symbols
            if ins > 0 and file_dt and target_tab.upper() in ('F', 'CS'):
                try:
                    if target_tab.upper() == 'CS':
                        marked = mark_cs_sales(file_dt)
                    elif target_tab.upper() == 'F':
                        marked = mark_f_sales(file_dt)
                    if marked > 0:
                        log.info("MARKED %d sold positions in %s as of %s", marked, target_tab, file_dt)
                except Exception as e:
                    log.warning("Could not mark sales for %s: %s", target_tab, e)

            # If all rows were skipped, log a summary warning with reason
            if skp > 0 and ins == 0 and read > 0:
                all_rows_skipped = True
                if skip_reasons:
                    reason_str = "; ".join([f"{count} {reason}" for reason, count in sorted(skip_reasons.items())])
                    msg = f"{p.name}: {read} rows skipped — {reason_str}"
                else:
                    msg = f"{p.name}: {read} rows skipped"
                # Log to both etl_load and scheduler loggers
                log.warning(msg, extra={'file_name': p.name})
                logger_sched = logging.getLogger("scheduler")
                logger_sched.warning(msg, extra={'file_name': p.name})
                # Also log directly to database to ensure it appears in Scheduler Output
                try:
                    s.execute(text("""
                        INSERT INTO meta_scheduler_log (logged_at, message, log_level, file_name)
                        VALUES (now(), :msg, 'WARNING', :fn)
                    """), {"msg": msg, "fn": p.name})
                    s.commit()
                except Exception:
                    pass
        except Exception as e:
            # Aborted-txn safe error path
            try: s.rollback()
            except Exception: pass
            try:
                close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                          status="error", error_msg=str(e)[:500])
            except Exception:
                log.exception("close_run failed for %s (continuing)", p.name)
            log.exception("load failed for %s", p.name)
            return {"status": "error", "msg": str(e)}

    # Derive cascade — runs in-process right after a successful load.
    # derive_all() rebuilds every drv_* table for this file's date; the
    # forward re-derive below then repairs any later dates that a backfilled
    # or out-of-order file invalidated. Skip the whole step with --no-derive
    # (do_derive=False) — used for bulk loads that derive once at the end.
    # Derive target = the ANCHOR date (MAX export_date in hist_td / TOSD), NOT
    # this file's filename date. TOSD is the only thing that advances the date;
    # every other load (intraday TOSL/Y, periodic feeds) re-derives the current
    # anchor. If hist_td is empty the date cannot be anchored — warn, don't derive.
    # See get_anchor_date() / docs/derive_date_logic.md.
    derive_error = None
    derive_dt = None
    if do_derive:
        with session_scope() as s2:
            derive_dt = get_anchor_date(s2)
        if derive_dt is None:
            _log_anchor_warning(
                f"{p.name}: loaded, but hist_td (TOSD) has no export_date — "
                f"cannot anchor a derive date. Load a TOSD export first.", p.name)
        else:
            log.info("rebuilding derived tables for anchor %s ...", derive_dt)
            try:
                with session_scope() as s2:
                    derive_all(s2, derive_dt)
            except BaseException as e:
                derive_error = str(e)
                log.exception("derive_all failed for %s (continuing)", derive_dt)

    # --- Automatic forward re-derive --------------------------------------
    # A file whose rows land on an OLD snapshot date can invalidate every
    # date already derived AFTER file_dt: each derive reads its sources with
    # a "latest snapshot <= D" window, so newly-arrived older data changes
    # those downstream results. After the main derive_all(file_dt) above,
    # rebuild the FULL cascade for every already-derived date later than
    # file_dt. No-op for a normal current-day load (nothing is derived past
    # file_dt); only does real work on backfills / out-of-order loads.
    # Runs only when the main derive succeeded and new rows were inserted.
    if (do_derive and derive_dt is not None and derive_error is None
            and 'ins' in locals() and ins > 0):
        try:
            with session_scope() as s3:
                forward_dates = [
                    r[0] for r in s3.execute(text(
                        "SELECT DISTINCT as_of_date FROM drv_dash "
                        "WHERE as_of_date > :fd ORDER BY as_of_date"
                    ), {"fd": derive_dt}).all()
                ]
            if forward_dates:
                log.info("forward re-derive: %d date(s) after %s need rebuilding",
                         len(forward_dates), derive_dt)
                for i, fwd in enumerate(forward_dates, 1):
                    log.info("forward re-derive: %s (%d/%d)", fwd, i, len(forward_dates))
                    try:
                        with session_scope() as s4:
                            derive_all(s4, fwd)
                    except BaseException:
                        log.exception("forward re-derive: derive_all failed for %s "
                                      "(continuing with remaining dates)", fwd)
                log.info("forward re-derive: done (%d date(s))", len(forward_dates))
        except BaseException:
            log.exception("forward re-derive: block failed (continuing)")

    # TOS watchlist file generation (2026-08-19, user-directed): "i load TOS
    # EOD exports only once a day, why can't we run this after loading all
    # TOS uploads?" -- was a once-daily clock-hour-gated nightly job (moved
    # from there to here, same day). Fires after any of the daily TOS EOD
    # sources loads and derives successfully -- TOSD (advances the anchor),
    # TOSL, TOSW. NOT TOSO (user: "TOSO is weekly load"), and not any other
    # file_type (RR/CS/F/CALL/etc never touch watchlist eligibility).
    # All 3, not just TOSD, because load order isn't fixed within one EOD
    # batch (e.g. 2026-08-19: TOSL, then TOSD, then TOSW) -- whichever lands
    # LAST naturally produces the final fresh files. generate_watchlist_
    # files() reads the anchor fresh each call, so firing 2-3x in one batch
    # is harmless, just redundant. Wrapped in try/except -- must never break
    # the load path for any file type, TOS or otherwise.
    if do_derive and derive_error is None and ft.upper() in ('TOSD', 'TOSL', 'TOSW'):
        try:
            from etl.generate_watchlist_files import generate_watchlist_files
            with session_scope() as s5:
                wl_result = generate_watchlist_files(
                    s5, "daily", settings.watchlist_files_dir, settings.watchlist_lists_dir)
            log.info("watchlist file generation (after %s load): %s", ft, wl_result)
            from etl.scheduler import _run_watchlist_housekeeping_reminders
            _run_watchlist_housekeeping_reminders(wl_result)
        except BaseException:
            log.exception("watchlist file generation failed after %s load (continuing)", ft)

    return {"status": "loaded", "rows_inserted": ins if 'ins' in locals() else 0}


def main() -> int:
    """CLI entry point: load a single file and print the result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path", help="Absolute path to the source file to load")
    parser.add_argument("--type", default=None, help="Override file_type detection")
    parser.add_argument("--no-derive", action="store_true", help="Skip derive_all")
    parser.add_argument("--force", action="store_true", help="Force reload")
    args = parser.parse_args()

    file_path = args.file_path
    if not file_path or not Path(file_path).exists():
        print(f"ERROR: file not found: {file_path}", file=sys.stderr)
        return 2

    result = load_one_file(file_path, file_type=args.type,
                           do_derive=not args.no_derive, force=args.force)
    import json as _json
    print(_json.dumps(result, default=str, indent=2))
    return 0 if result.get("status") in ("loaded", "skipped") else 1


if __name__ == "__main__":
    raise SystemExit(main())
