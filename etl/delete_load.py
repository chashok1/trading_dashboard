"""
Delete all hist_* rows written by one ETL load, so a wrong/partial file can
be corrected and reprocessed cleanly.

This is a deliberate, logged, confirm-gated exception to the "never delete
raw hist_*" convention (CLAUDE.md #1) — it exists specifically to undo a load
that was wrong (partial file, wrong file date, etc.), not for routine
cleanup. `etl/cleanup.py` remains the only *automatic* deleter; this is a
manual action triggered from the File Monitor screen's "Delete load" button
(or the CLI below).

Workflow:
    1. preview_delete_load(session, run_id) -> counts + file info, no writes.
    2. delete_load(session, run_id) ->
         a. DELETE FROM <target_tab> WHERE source_file = <file_path>
         b. DELETE meta_file_processed WHERE file_path = <file_path>
              (so the file becomes eligible for reprocessing again)
         c. UPDATE meta_etl_run SET status='reverted' (audit trail kept —
              the run row itself is never deleted)
         d. derive_all(anchor) + the same forward-re-derive sweep
              etl_load.py runs after a load, so drv_* reflects whatever
              remains in hist_* after the deletion.

Usage:
    python -m etl.delete_load --run-id 1919 [--yes]
"""
from __future__ import annotations

import argparse
import logging
import os
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.db import get_table, safe_ident, session_scope
from etl.derive import derive_all, get_anchor_date

from etl._logging import setup_logging
setup_logging()
log = logging.getLogger("delete_load")


def _run_info(session: Session, run_id: int) -> Optional[dict]:
    row = session.execute(text("""
        SELECT run_id, file_path, target_tab, file_type, status
        FROM meta_etl_run WHERE run_id = :rid
    """), {"rid": run_id}).first()
    if not row:
        return None
    return dict(zip(("run_id", "file_path", "target_tab", "file_type", "status"), row))


def _validate_deletable(info: dict) -> Optional[str]:
    """Returns an error message if this run isn't safe to delete, else None."""
    if not info["file_path"]:
        return "run has no file_path recorded"
    target_tab = info["target_tab"]
    if not target_tab or not target_tab.startswith("hist_"):
        return f"target_tab '{target_tab}' is not a hist_* table — nothing to delete"
    try:
        table = get_table(target_tab)
    except Exception as e:
        return f"could not resolve table '{target_tab}': {e}"
    if "source_file" not in {c.name for c in table.columns}:
        return f"{target_tab} has no source_file column — cannot target this load safely"
    return None


def preview_delete_load(session: Session, run_id: int) -> dict:
    """Read-only: what would delete_load() do for this run_id."""
    info = _run_info(session, run_id)
    if not info:
        return {"found": False, "msg": f"run_id {run_id} not found"}

    err = _validate_deletable(info)
    if err:
        return {"found": False, "msg": err}

    target_tab = info["target_tab"]
    safe_tab = safe_ident(target_tab, {target_tab})
    # The CSV custom handlers (CS/CST/FT/F401K) stamp hist_*.source_file with
    # just the basename, while the generic Excel loader stamps the full path
    # (both use file_path=str(p) for meta_etl_run/meta_file_processed either
    # way) — match either form so preview/delete work for both loader kinds.
    row_count = session.execute(text(
        f'SELECT COUNT(*) FROM "{safe_tab}" WHERE source_file IN (:fp, :fname)'
    ), {"fp": info["file_path"], "fname": os.path.basename(info["file_path"])}).scalar()

    fd_row = session.execute(text(
        "SELECT file_date FROM meta_file_processed WHERE file_path = :fp"
    ), {"fp": info["file_path"]}).first()

    return {
        "found": True,
        "run_id": run_id,
        "file_path": info["file_path"],
        "file_type": info["file_type"],
        "target_tab": target_tab,
        "row_count": row_count,
        "file_date": fd_row[0].isoformat() if fd_row and fd_row[0] else None,
        "already_reverted": info["status"] == "reverted",
    }


def delete_load(session: Session, run_id: int) -> dict:
    """Delete this run's hist_* rows + meta_file_processed entry, mark the
    run reverted, and re-derive. Caller owns the session/transaction for the
    delete step; the re-derive step opens its own session(s), matching
    etl_load.py's pattern so a derive failure can't roll back the deletion."""
    info = _run_info(session, run_id)
    if not info:
        return {"success": False, "msg": f"run_id {run_id} not found"}

    err = _validate_deletable(info)
    if err:
        return {"success": False, "msg": err}

    target_tab = info["target_tab"]
    file_path = info["file_path"]
    safe_tab = safe_ident(target_tab, {target_tab})

    # Capture file_date BEFORE removing meta_file_processed — this is the
    # same value etl_load.py itself uses as the forward-re-derive threshold.
    fd_row = session.execute(text(
        "SELECT file_date FROM meta_file_processed WHERE file_path = :fp"
    ), {"fp": file_path}).first()
    file_date = fd_row[0] if fd_row else None

    result = session.execute(text(
        f'DELETE FROM "{safe_tab}" WHERE source_file IN (:fp, :fname)'
    ), {"fp": file_path, "fname": os.path.basename(file_path)})
    n_deleted = result.rowcount if result.rowcount is not None else 0

    session.execute(text(
        "DELETE FROM meta_file_processed WHERE file_path = :fp"
    ), {"fp": file_path})

    session.execute(text("""
        UPDATE meta_etl_run
           SET status = 'reverted',
               error_msg = COALESCE(error_msg || ' | ', '') ||
                           'Deleted via File Monitor at ' || now()::text ||
                           ' (' || :n || ' rows removed from ' || :tab || ')'
         WHERE run_id = :rid
    """), {"rid": run_id, "n": n_deleted, "tab": target_tab})
    session.commit()
    log.warning("delete_load: run_id=%s file=%s target_tab=%s rows_deleted=%d",
                run_id, file_path, target_tab, n_deleted)

    # Re-derive from whatever remains in hist_*, same cascade etl_load.py
    # runs after a load: rebuild the current anchor, then forward re-derive
    # every already-derived date after file_date — a deletion can invalidate
    # later dates exactly like a backfilled insert can (positions/periodic
    # feeds carry forward "latest snapshot <= D").
    derive_error = None
    anchor = None
    forward_count = 0
    try:
        with session_scope() as s2:
            anchor = get_anchor_date(s2)
        if anchor is not None:
            with session_scope() as s2:
                derive_all(s2, anchor)
    except BaseException as e:
        derive_error = str(e)
        log.exception("delete_load: derive_all failed for anchor %s", anchor)

    if anchor is not None and derive_error is None and file_date is not None:
        try:
            with session_scope() as s3:
                forward_dates = [r[0] for r in s3.execute(text(
                    "SELECT DISTINCT as_of_date FROM drv_dash "
                    "WHERE as_of_date > :fd ORDER BY as_of_date"
                ), {"fd": file_date}).all()]
            for fwd in forward_dates:
                try:
                    with session_scope() as s4:
                        derive_all(s4, fwd)
                    forward_count += 1
                except BaseException:
                    log.exception("delete_load: forward re-derive failed for %s", fwd)
        except BaseException:
            log.exception("delete_load: forward re-derive block failed (continuing)")

    return {
        "success": True,
        "run_id": run_id,
        "file_path": file_path,
        "target_tab": target_tab,
        "rows_deleted": n_deleted,
        "anchor_derived": anchor.isoformat() if anchor else None,
        "forward_rederived_count": forward_count,
        "derive_error": derive_error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int, required=True, help="meta_etl_run.run_id to delete")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    with session_scope() as s:
        preview = preview_delete_load(s, args.run_id)
    if not preview.get("found"):
        print(f"ERROR: {preview.get('msg')}")
        return 2

    print(f"Will delete {preview['row_count']} row(s) from {preview['target_tab']} "
          f"(source_file={preview['file_path']}, file_date={preview['file_date']}), "
          f"clear its meta_file_processed entry, and re-derive.")
    if not args.yes:
        resp = input("Proceed? [y/N] ").strip().lower()
        if resp != "y":
            print("Cancelled.")
            return 1

    with session_scope() as s:
        result = delete_load(s, args.run_id)
    import json as _json
    print(_json.dumps(result, default=str, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
