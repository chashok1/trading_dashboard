"""
One-shot: delete hist_tw rows, then reload all TOSW files in-place.
Bypasses load_one_file (which would fail: src == dst in working dir).

Run from project root:
    python reprocess_tosw.py [--no-derive]
"""
import sys
import logging
from pathlib import Path
from sqlalchemy import text
from config.settings import settings
from etl.db import get_engine, session_scope
from etl.excel_io import open_workbook
from etl.etl_load import (
    mark_processed, open_run, close_run, parse_file_date_from_name
)
from etl.load_raw import load_tw

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger(__name__)

WORKING_DIR = Path(settings.etl_working_dir)
DO_DERIVE = "--no-derive" not in sys.argv

# --- 1. Find all TOSW files -------------------------------------------------
tosw_files = sorted(WORKING_DIR.glob("[Tt][Oo][Ss][Ww] *.csv"))
if not tosw_files:
    log.error("No TOSW *.csv files found in %s", WORKING_DIR)
    sys.exit(1)
log.info("Found %d TOSW files to reprocess", len(tosw_files))

engine = get_engine()

with engine.begin() as conn:
    # --- 2. Delete all hist_tw (TOSW is the sole source) -------------------
    log.info("Deleting all rows from hist_tw ...")
    r = conn.execute(text("DELETE FROM hist_tw"))
    log.info("  deleted %d rows", r.rowcount)

    # --- 3. Clear meta_file_processed for TOSW files -----------------------
    log.info("Clearing meta_file_processed for TOSW files ...")
    r = conn.execute(text(
        "DELETE FROM meta_file_processed WHERE LOWER(file_path) LIKE '%tosw%'"
    ))
    log.info("  cleared %d rows", r.rowcount)

# --- 4. Reload each file ----------------------------------------------------
total_ins = 0
for f in tosw_files:
    log.info("Loading %s ...", f.name)
    file_mtime = f.stat().st_mtime
    file_dt = parse_file_date_from_name(f.name)
    with session_scope() as s:
        run_id = open_run(s, file_path=str(f), file_type="TW", target_tab="hist_tw")
        try:
            wb = open_workbook(f)
            read, ins, skp = load_tw(s, wb, str(f))
            close_run(s, run_id, rows_read=read, rows_inserted=ins, rows_skipped=skp)
            mark_processed(s, file_path=str(f), file_mtime=file_mtime,
                           file_type="TW", target_tab="hist_tw",
                           file_dt=file_dt, run_id=run_id)
            log.info("  read=%d  inserted=%d  skipped=%d", read, ins, skp)
            total_ins += ins
        except Exception as e:
            try:
                s.rollback()
                close_run(s, run_id, rows_read=0, rows_inserted=0, rows_skipped=0,
                          status="error", error_msg=str(e)[:500])
            except Exception:
                pass
            log.exception("  FAILED: %s", e)

log.info("Total rows inserted into hist_tw: %d", total_ins)

# --- 5. Re-derive -----------------------------------------------------------
if DO_DERIVE:
    log.info("Running derive_all for anchor date ...")
    from etl.derive import get_anchor_date, derive_all
    with session_scope() as s:
        anchor = get_anchor_date(s)
        if anchor:
            log.info("  anchor = %s", anchor)
            derive_all(s, anchor)
            log.info("  derive complete")
        else:
            log.warning("  no anchor date — skipping derive")
else:
    log.info("Skipping derive (--no-derive)")

log.info("Done.")
