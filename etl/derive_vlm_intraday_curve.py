"""
etl/derive_vlm_intraday_curve.py — empirical intraday volume-completion
curve backing drv_technicals.vlm_projected (etl/derive.py::_derive_technicals_impl).

Replaces the old flat-linear "volume_so_far * 390 / minutes_elapsed"
projection (assumed a constant trading pace all day). Measures, per
30-minute bucket since the 9:30 open, the MEDIAN fraction of a symbol-day's
eventual full-day volume that has typically occurred by then — computed
from this system's own hist_tl history (every symbol-day that has both an
intraday snapshot before 16:00 and that same day's 16:30 close).

Finding that motivated this (user: "if the volume is doubled in a few
minutes then intraday calc will not be correct... I need proper values
otherwise no point in using it"): on a typical day only ~67% of the day's
total volume has happened with 30 minutes left in the session — the
closing auction alone is roughly a third of a day's volume. The flat
formula chronically under-projected the full-day total at every point in
the day, not just near the close (see db/baseline.sql's
ref_vlm_intraday_curve comment for the measured numbers).

Not part of the daily derive_all() cascade — a periodic tunable-table
refresh (same spirit as etl/refresh_ref.py, full TRUNCATE + rebuild each
run, no history kept), run manually as more trading days accumulate and
the curve can only get more reliable:

    python -m etl.derive_vlm_intraday_curve
"""
from __future__ import annotations

import logging
import statistics

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl.db import session_scope

log = logging.getLogger(__name__)

BUCKET_SIZE_MIN = 30
SESSION_MINUTES = 390          # 9:30-16:00 ET regular session
MIN_OBS_PER_BUCKET = 30        # below this a bucket isn't reliable enough to keep


def _minutes_elapsed(sequence: int) -> int:
    """`sequence` is HHMM (e.g. 1556 -> 15:56); minutes since the 9:30 open."""
    return (sequence // 100) * 60 + (sequence % 100) - 570


def refresh_vlm_intraday_curve(session: Session) -> int:
    """Recompute ref_vlm_intraday_curve from hist_tl history. Returns bucket count."""
    rows = session.execute(text("""
        SELECT h1.sequence, h1.volume::numeric AS v_snap, h2.volume::numeric AS v_close
        FROM hist_tl h1
        JOIN hist_tl h2
          ON h2.tos_symbol = h1.tos_symbol AND h2.export_date = h1.export_date
             AND h2.sequence = 1630
        WHERE h1.sequence >= 930 AND h1.sequence < 1600
          AND h1.volume IS NOT NULL AND h2.volume IS NOT NULL AND h2.volume > 0
    """)).fetchall()

    buckets: dict[int, list[float]] = {}
    last_bucket_start = (SESSION_MINUTES // BUCKET_SIZE_MIN - 1) * BUCKET_SIZE_MIN
    for sequence, v_snap, v_close in rows:
        mins = _minutes_elapsed(sequence)
        if mins <= 0 or mins >= SESSION_MINUTES:
            continue
        bucket_start = min(mins // BUCKET_SIZE_MIN, last_bucket_start // BUCKET_SIZE_MIN) * BUCKET_SIZE_MIN
        buckets.setdefault(bucket_start, []).append(float(v_snap) / float(v_close))

    curve_rows = []
    for bucket_start in sorted(buckets):
        vals = buckets[bucket_start]
        if len(vals) < MIN_OBS_PER_BUCKET:
            log.warning(
                "ref_vlm_intraday_curve: bucket %d-%d has only %d obs (<%d), dropping",
                bucket_start, bucket_start + BUCKET_SIZE_MIN, len(vals), MIN_OBS_PER_BUCKET)
            continue
        curve_rows.append({
            "bucket_start_min": bucket_start,
            "bucket_end_min": bucket_start + BUCKET_SIZE_MIN,
            "median_fraction": statistics.median(vals),
            "n_obs": len(vals),
        })

    # Enforce monotonic non-decreasing fraction across buckets — day-completion
    # can never logically go backwards; small-sample noise between adjacent
    # buckets otherwise occasionally dips (see db/baseline.sql comment).
    running_max = 0.0
    for r in curve_rows:
        running_max = max(running_max, r["median_fraction"])
        r["median_fraction"] = running_max

    session.execute(text("TRUNCATE TABLE ref_vlm_intraday_curve"))
    if curve_rows:
        session.execute(text("""
            INSERT INTO ref_vlm_intraday_curve
              (bucket_start_min, bucket_end_min, median_fraction, n_obs)
            VALUES (:bucket_start_min, :bucket_end_min, :median_fraction, :n_obs)
        """), curve_rows)
    return len(curve_rows)


if __name__ == "__main__":
    from etl._logging import setup_logging
    setup_logging()
    with session_scope() as s:
        n = refresh_vlm_intraday_curve(s)
    msg = f"ref_vlm_intraday_curve refreshed: {n} buckets"
    log.info(msg)
    print(msg)
