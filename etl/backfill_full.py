"""Full history backfill: derives + firing outcomes.

Task 5 — AGENT_WORK_39. Combines etl/backfill_derives.py and
etl/compute_firing_outcomes.py into one command that:
  1. Inventories available hist_* history and reports the date range.
  2. Derives all missing dates that have hist_td data (idempotent).
  3. Runs compute_firing_outcomes over the full derived range.

Run:
    python -m etl.backfill_full               # full backfill
    python -m etl.backfill_full --inventory   # report only, no derive/outcomes
    python -m etl.backfill_full --limit 10    # smoke-test (first 10 missing dates)
    python -m etl.backfill_full --skip-outcomes  # derive only, skip outcomes
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sqlalchemy import text  # noqa: E402

from etl.db import session_scope  # noqa: E402
from etl.derive import derive_all  # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.backfill_full")


def _inventory(s) -> dict:
    """Return oldest/newest export_date per hist_* source and derived status."""
    sources = {
        "hist_td": "export_date",
        "hist_tl": "export_date",
        "hist_tw": "snapshot_date",
        "hist_y":  "export_date",
        "hist_rr": "snapshot_date",
        "hist_call": "snapshot_date",
        "hist_etf": "snapshot_date",
        "hist_ii":  "snapshot_date",
        "hist_sss": "snapshot_date",
    }
    result = {}
    for tbl, col in sources.items():
        try:
            row = s.execute(text(
                f"SELECT MIN({col}), MAX({col}), COUNT(*) FROM {tbl}"
            )).first()
            result[tbl] = {
                "min_date": row[0].isoformat() if row[0] else None,
                "max_date": row[1].isoformat() if row[1] else None,
                "rows": int(row[2] or 0),
            }
        except Exception as e:
            result[tbl] = {"error": str(e)}
    # Derived coverage
    try:
        dr = s.execute(text("""
            SELECT MIN(as_of_date), MAX(as_of_date), COUNT(DISTINCT as_of_date)
            FROM drv_trig
        """)).first()
        result["drv_trig"] = {
            "min_date": dr[0].isoformat() if dr[0] else None,
            "max_date": dr[1].isoformat() if dr[1] else None,
            "n_dates": int(dr[2] or 0),
        }
    except Exception as e:
        result["drv_trig"] = {"error": str(e)}
    try:
        ro = s.execute(text("""
            SELECT COUNT(*) FROM drv_rule_outcome
        """)).scalar()
        result["drv_rule_outcome"] = {"rows": int(ro or 0)}
    except Exception as e:
        result["drv_rule_outcome"] = {"error": str(e)}
    return result


def _missing_dates(s, d_from=None, d_to=None):
    return s.execute(text("""
        SELECT DISTINCT export_date AS d
        FROM hist_td
        WHERE export_date NOT IN (SELECT DISTINCT as_of_date FROM drv_trig)
          AND (CAST(:f AS date) IS NULL OR export_date >= CAST(:f AS date))
          AND (CAST(:t AS date) IS NULL OR export_date <= CAST(:t AS date))
        ORDER BY export_date
    """), {"f": d_from, "t": d_to}).scalars().all()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inventory", action="store_true",
                   help="Print inventory only, no derives")
    p.add_argument("--limit", type=int, default=None,
                   help="Only derive the first N missing dates")
    p.add_argument("--from", dest="d_from", default=None)
    p.add_argument("--to",   dest="d_to",   default=None)
    p.add_argument("--skip-outcomes", action="store_true",
                   help="Skip compute_firing_outcomes step")
    args = p.parse_args()

    d_from = datetime.strptime(args.d_from, "%Y-%m-%d").date() if args.d_from else None
    d_to   = datetime.strptime(args.d_to,   "%Y-%m-%d").date() if args.d_to   else None

    log.info("=== backfill_full inventory ===")
    with session_scope() as s:
        inv = _inventory(s)
    for tbl, info in inv.items():
        log.info("  %-25s  %s", tbl, info)

    if args.inventory:
        log.info("--inventory: stopping before derives.")
        return 0

    # Step 2: derive missing dates
    with session_scope() as s:
        dates = _missing_dates(s, d_from, d_to)
    if args.limit:
        dates = dates[:args.limit]

    if not dates:
        log.info("No missing dates — derives up to date.")
    else:
        log.info("Deriving %d missing dates: %s .. %s", len(dates), dates[0], dates[-1])
        ok = 0
        for i, d in enumerate(dates, 1):
            try:
                with session_scope() as s:
                    counts = derive_all(s, d)
                log.info("[%d/%d] %s  cat=%s stks=%s trig=%s actionable=%s",
                         i, len(dates), d,
                         counts.get("drv_cat_atomic_input"),
                         counts.get("drv_stks"),
                         counts.get("drv_trig"),
                         counts.get("drv_actionable"))
                ok += 1
            except Exception as e:
                log.error("[%d/%d] %s FAILED: %s", i, len(dates), d, e)
        log.info("Backfill derives: %d/%d dates derived.", ok, len(dates))

    # Step 3: compute firing outcomes
    if not args.skip_outcomes:
        log.info("Running compute_firing_outcomes over full history…")
        try:
            from etl.compute_firing_outcomes import main as _outcomes_main
            sys.argv = ["compute_firing_outcomes"]
            rc = _outcomes_main()
            log.info("compute_firing_outcomes exited with code %s", rc)
        except SystemExit as exc:
            log.info("compute_firing_outcomes done (exit %s)", exc.code)
        except Exception as e:
            log.error("compute_firing_outcomes failed: %s", e)
            return 1

    log.info("=== backfill_full complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
