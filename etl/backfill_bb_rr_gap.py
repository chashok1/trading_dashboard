"""Backfill drv_bb_rr_gap (TASK_132) across the full hist_rr history.

One-off, additive & safe: loops ASCENDING over every distinct hist_rr
snapshot_date and re-derives drv_bb_rr_gap for that date (idempotent
DELETE+INSERT per date via etl.derive_bb_rr_gap.derive_bb_rr_gap). Must run
ascending so each date's rolling 20-trading-day median reads the
already-backfilled prior dates — same one-off-loop pattern as
etl/backfill_derives.py.

Run:
    python -m etl.backfill_bb_rr_gap                  # full history
    python -m etl.backfill_bb_rr_gap --limit 30        # smoke test
    python -m etl.backfill_bb_rr_gap --from 2026-01-01 --to 2026-06-01
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
from etl.derive_bb_rr_gap import derive_bb_rr_gap  # noqa: E402
from etl._logging import setup_logging  # noqa: E402

setup_logging()
log = logging.getLogger("etl.backfill_bb_rr_gap")


def _all_dates(session, d_from=None, d_to=None):
    rows = session.execute(text("""
        SELECT DISTINCT snapshot_date AS d
        FROM hist_rr
        WHERE (CAST(:f AS date) IS NULL OR snapshot_date >= CAST(:f AS date))
          AND (CAST(:t AS date) IS NULL OR snapshot_date <= CAST(:t AS date))
        ORDER BY snapshot_date
    """), {"f": d_from, "t": d_to}).scalars().all()
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=None, help="Only the first N dates")
    p.add_argument("--from", dest="d_from", default=None, help="YYYY-MM-DD lower bound")
    p.add_argument("--to", dest="d_to", default=None, help="YYYY-MM-DD upper bound")
    args = p.parse_args()

    d_from = datetime.strptime(args.d_from, "%Y-%m-%d").date() if args.d_from else None
    d_to = datetime.strptime(args.d_to, "%Y-%m-%d").date() if args.d_to else None

    with session_scope() as s:
        dates = _all_dates(s, d_from, d_to)
    if args.limit:
        dates = dates[:args.limit]

    if not dates:
        log.info("No hist_rr dates found — nothing to do.")
        return 0

    log.info("Backfilling drv_bb_rr_gap for %d dates: %s .. %s", len(dates), dates[0], dates[-1])
    ok = 0
    for i, d in enumerate(dates, 1):
        try:
            with session_scope() as s:
                n = derive_bb_rr_gap(s, d)
            log.info("[%d/%d] %s -> %d rows", i, len(dates), d, n)
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.error("[%d/%d] %s FAILED: %s", i, len(dates), d, e)
    log.info("Backfill done: %d/%d dates derived.", ok, len(dates))
    return 0 if ok == len(dates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
