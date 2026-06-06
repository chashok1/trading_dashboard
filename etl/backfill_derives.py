"""Backfill derive_all across historical dates that have hist_td data but no
drv_trig firings yet.

ADDITIVE & SAFE:
  * Only derives dates that are MISSING from drv_trig — never re-touches dates
    already derived (including the current 6/4–6/5) and never modifies any rule
    definition. derive_all(D) is idempotent and scoped to date D only.
  * Each date is its own transaction, so a failure on one date doesn't roll back
    the others; the run can be re-started and will skip what's already done.

Run:
    python -m etl.backfill_derives             # backfill ALL missing dates
    python -m etl.backfill_derives --limit 3   # only the first N (smoke test)
    python -m etl.backfill_derives --from 2026-02-02 --to 2026-05-05
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
log = logging.getLogger("etl.backfill_derives")


def _missing_dates(session, d_from=None, d_to=None):
    rows = session.execute(text("""
        SELECT DISTINCT export_date AS d
        FROM hist_td
        WHERE export_date NOT IN (SELECT DISTINCT as_of_date FROM drv_trig)
          AND (CAST(:f AS date) IS NULL OR export_date >= CAST(:f AS date))
          AND (CAST(:t AS date) IS NULL OR export_date <= CAST(:t AS date))
        ORDER BY export_date
    """), {"f": d_from, "t": d_to}).scalars().all()
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=None, help="Only the first N missing dates")
    p.add_argument("--from", dest="d_from", default=None, help="YYYY-MM-DD lower bound")
    p.add_argument("--to", dest="d_to", default=None, help="YYYY-MM-DD upper bound")
    args = p.parse_args()

    d_from = datetime.strptime(args.d_from, "%Y-%m-%d").date() if args.d_from else None
    d_to = datetime.strptime(args.d_to, "%Y-%m-%d").date() if args.d_to else None

    with session_scope() as s:
        dates = _missing_dates(s, d_from, d_to)
    if args.limit:
        dates = dates[:args.limit]

    if not dates:
        log.info("No missing dates to backfill — nothing to do.")
        return 0

    log.info("Backfilling %d missing dates: %s .. %s", len(dates), dates[0], dates[-1])
    ok = 0
    for i, d in enumerate(dates, 1):
        try:
            with session_scope() as s:
                counts = derive_all(s, d)
            log.info("[%d/%d] %s  cat=%s stks=%s trig=%s actionable=%s",
                     i, len(dates), d,
                     counts.get("drv_cat_atomic_input"), counts.get("drv_stks"),
                     counts.get("drv_trig"), counts.get("drv_actionable"))
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.error("[%d/%d] %s FAILED: %s", i, len(dates), d, e)
    log.info("Backfill done: %d/%d dates derived.", ok, len(dates))
    return 0 if ok == len(dates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
