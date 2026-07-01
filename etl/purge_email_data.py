"""
etl/purge_email_data.py — Delete all data inserted via Gmail/email processing.

Covers:
  File-backed feeds (emitted via emit.py → loader):
    hist_rr, hist_iichg, hist_etfchg, hist_ps, hist_call
    Identified via: meta_file_origin.source_kind='email' → source_file column

  Direct-insert email-only feeds (all rows deleted — these tables are 100% email):
    hist_rta, hist_call_top5, hist_hedgeye_stance, hist_sss_change,
    note_repo, hist_media, llm_analysis

  Meta / processing tables:
    meta_hedgeye_msg, meta_file_processed (source_kind='email'), meta_file_origin

  Archive files on disk:
    Emitted xlsx/csv files registered in meta_file_origin (source_kind='email')

Usage:
    python -m etl.purge_email_data              # dry-run (safe, no changes)
    python -m etl.purge_email_data --execute    # actually delete everything
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

load_dotenv()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from etl.db import session_scope  # noqa: E402

# File-backed tables: (table_name, date_column, source_file_column)
FILE_BACKED = [
    ("hist_rr",     "snapshot_date", "source_file"),
    ("hist_iichg",  "event_date",    "source_file"),
    ("hist_etfchg", "event_date",    "source_file"),
    ("hist_ps",     "snapshot_date", "source_file"),
    ("hist_call",   "snapshot_date", "source_file"),
]

# Direct-insert tables keyed by message_id
MSG_BACKED = [
    "hist_rta",
    "hist_call_top5",
    "hist_hedgeye_stance",
    "hist_sss_change",
    "note_repo",
    "hist_media",
    "llm_analysis",
]


def _count(session, table: str, where: str, params: dict) -> int:
    try:
        return session.execute(
            text(f"SELECT count(*) FROM {table} WHERE {where}"), params
        ).scalar() or 0
    except Exception:
        return -1  # table may not exist yet


def _delete(session, table: str, where: str, params: dict) -> int:
    try:
        return session.execute(
            text(f"DELETE FROM {table} WHERE {where}"), params
        ).rowcount
    except Exception as e:
        print(f"  [WARN] {table}: {e}")
        return 0


def run(execute: bool) -> None:
    label = "EXECUTING" if execute else "DRY-RUN"
    print(f"\n=== purge_email_data  [{label}] ===\n")

    with session_scope() as session:
        # ------------------------------------------------------------------ #
        # 1. Collect identifiers
        # ------------------------------------------------------------------ #
        msg_ids: list[str] = [
            r[0] for r in session.execute(
                text("SELECT message_id FROM meta_hedgeye_msg")
            ).fetchall()
        ]
        emitted_paths: list[str] = [
            r[0] for r in session.execute(
                text("SELECT file_path FROM meta_file_origin WHERE source_kind='email'")
            ).fetchall()
        ]

        print(f"Email message IDs in ledger : {len(msg_ids)}")
        print(f"Emitted file paths registered: {len(emitted_paths)}\n")

        if not msg_ids and not emitted_paths:
            print("Nothing to purge.")
            return

        # ------------------------------------------------------------------ #
        # 2. File-backed hist tables  (keyed by source_file)
        # ------------------------------------------------------------------ #
        print("--- File-backed tables (source_file) ---")
        for table, date_col, sf_col in FILE_BACKED:
            if not emitted_paths:
                print(f"  {table}: 0 (no emitted files)")
                continue
            where = f"{sf_col} = ANY(:paths)"
            params = {"paths": emitted_paths}
            n = _count(session, table, where, params)
            print(f"  {table}: {n} rows")
            if execute and n > 0:
                deleted = _delete(session, table, where, params)
                print(f"    -> deleted {deleted}")

        # ------------------------------------------------------------------ #
        # 3. Direct-insert tables  (all rows — these tables are 100% email)
        # ------------------------------------------------------------------ #
        print("\n--- Direct-insert tables (all rows — exclusively email-sourced) ---")
        for table in MSG_BACKED:
            n = _count(session, table, "TRUE", {})
            print(f"  {table}: {n} rows")
            if execute and n > 0:
                deleted = _delete(session, table, "TRUE", {})
                print(f"    -> deleted {deleted}")

        # ------------------------------------------------------------------ #
        # 4. Meta / processing tables
        # ------------------------------------------------------------------ #
        print("\n--- Meta tables ---")

        # meta_file_processed (source_kind='email')
        n = _count(session, "meta_file_processed", "source_kind='email'", {})
        print(f"  meta_file_processed (source_kind=email): {n} rows")
        if execute and n > 0:
            _delete(session, "meta_file_processed", "source_kind='email'", {})
            print(f"    -> deleted {n}")

        # meta_file_origin
        n = _count(session, "meta_file_origin", "source_kind='email'", {})
        print(f"  meta_file_origin (source_kind=email): {n} rows")
        if execute and n > 0:
            _delete(session, "meta_file_origin", "source_kind='email'", {})
            print(f"    -> deleted {n}")

        # meta_hedgeye_msg (all rows = email)
        n = _count(session, "meta_hedgeye_msg", "TRUE", {})
        print(f"  meta_hedgeye_msg (all): {n} rows")
        if execute and n > 0:
            _delete(session, "meta_hedgeye_msg", "TRUE", {})
            print(f"    -> deleted {n}")

        if execute:
            session.commit()
            print("\n[DB committed]")

        # ------------------------------------------------------------------ #
        # 5. Archive files on disk
        # ------------------------------------------------------------------ #
        print("\n--- Archive files on disk ---")
        missing = []
        present = []
        for path_str in emitted_paths:
            p = Path(path_str)
            if p.exists():
                present.append(p)
            else:
                missing.append(path_str)

        print(f"  Found on disk  : {len(present)}")
        print(f"  Already gone   : {len(missing)}")
        for p in present:
            print(f"    {p}")

        if execute:
            removed = 0
            for p in present:
                try:
                    p.unlink()
                    removed += 1
                except Exception as e:
                    print(f"  [WARN] could not delete {p}: {e}")
            print(f"  -> removed {removed} files")

    if not execute:
        print("\n[DRY-RUN complete — no changes made]")
        print("Re-run with  --execute  to apply.\n")
    else:
        print("\n[Done]\n")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Purge all data inserted via Gmail/email processing."
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete. Without this flag the script is a safe dry-run.",
    )
    args = ap.parse_args()
    run(execute=args.execute)


if __name__ == "__main__":
    main()
