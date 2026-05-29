"""
Wipe all data from the database so the initial load can be re-run from scratch.

Truncates (in safe dependency order):
  - drv_*  (derived)
  - hist_* (raw history)
  - ref_*  (reference / lookup)
  - meta_etl_run, meta_derived_run, meta_file_processed  (audit)

meta_cleanup_policy and meta_cleanup_history are left untouched.

Usage:
    python -m db.reset_db            # prompts for confirmation
    python -m db.reset_db --yes      # skips prompt (for scripting)
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from etl.db import session_scope

# Truncate in this order so FK constraints don't fire.
# drv tables reference hist tables; hist tables reference nothing.
# ref_trig_composite_mapping references ref_trig_atomic_rule.
_TRUNCATE_ORDER = [
    # derived (may reference hist via FK)
    "drv_trig",
    "drv_stks",
    "drv_dash",
    "drv_dash_summary",
    "drv_missing_symbols",
    "drv_ma",
    "drv_tw",
    "drv_td",
    # history (raw)
    "hist_cs",
    "hist_f",
    "hist_ps",
    "hist_iichg",
    "hist_etfchg",
    "hist_ssh",
    "hist_ii",
    "hist_etf",
    "hist_call",
    "hist_rr",
    "hist_to",
    "hist_tw",
    "hist_td",
    "hist_tl",
    "hist_y",
    # reference
    "ref_trig_composite_mapping",
    "ref_trig_atomic_rule",
    "ref_ismh",
    "ref_asset_allocation",
    "ref_param_lookup",
    "ref_param",
    "ref_quad_periods",
    "ref_quad_outlook",
    "ref_calendar_event",
    "ref_fed_blackout",
    "ref_econ_indicator",
    "ref_holiday",
    "ref_rule_desc",
    "ref_rrt",
    "ref_sector",
    "ref_load_files",
    # audit / dedup
    "meta_derived_run",
    "meta_etl_run",
    "meta_file_processed",
]


def reset(yes: bool = False) -> None:
    if not yes:
        print("This will DELETE ALL DATA from hist_*, drv_*, ref_*, and meta audit tables.")
        ans = input("Type 'yes' to confirm: ").strip().lower()
        if ans != "yes":
            print("Aborted.")
            sys.exit(0)

    with session_scope() as session:
        for table in _TRUNCATE_ORDER:
            session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
            print(f"  truncated {table}")

    print("Done. Database is empty — ready for a fresh initial load.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wipe all data for a fresh re-load.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()
    reset(yes=args.yes)
