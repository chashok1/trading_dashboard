"""
etl/derive_market_stat.py — TASK_133 Phase 3: drv_market_stat.

Self-computed market inputs for the Risk Dial: Yang-Zhang realized
volatility + variance risk premium (SPX), breadth on this system's own
universe, participation (SPY/QQQ/IWM relative volume), then the Risk Dial
itself (etl/derive_risk_dial.py). One row per as_of_date, idempotent
(DELETE WHERE as_of_date=D -> INSERT via replace_for_date).

Wired into derive_all() after drv_technicals/drv_quote/drv_rr (it reads all
three) and before drv_cat_atomic_input.

Known data-history limit (documented in DEV_HANDOFF.md): the spec asks for a
>=300-trading-day backfill so vrp_z has a real distribution from day one.
This system's own history does not go back that far yet (SPX drv_quote
starts 2026-01-30, hist_tw breadth starts 2026-05-11) — the backfill CLI
below derives every date currently available (~130 trading days) instead;
vrp_z will have a thin distribution until more real history accumulates.
"""
from __future__ import annotations

import argparse
import logging
import math
import statistics
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import _wrap
from etl.db import replace_for_date, session_scope

log = logging.getLogger(__name__)

YZ_WINDOWS = (10, 21, 63)
VRP_Z_MIN_OBS = 20   # minimum trailing vrp observations before a z-score is emitted
VRP_Z_LOOKBACK = 252

# Volatility-gauge tos_symbols excluded from the breadth universe (they are
# indices/instruments, not tradeable equities/ETFs the breadth stat means to
# cover) in addition to the '$'/'/'-prefix exclusion the spec calls out.
_VOL_GAUGE_SYMS = {"VIX", "VVIX", "RVX", "VXN:CGI", "GVZ:CGI", "OVX:CGI",
                   "MOVE:GIF", "VXD"}

_SPX_QUOTE_SQL = text("""
    SELECT as_of_date, open_price, high_price, low_price, last_price
    FROM drv_quote WHERE tos_symbol = 'SPX' AND as_of_date <= :d
    ORDER BY as_of_date ASC
""")

_SPX_TD_SQL = text("""
    SELECT DISTINCT ON (export_date) export_date AS as_of_date,
           open_price, high_price, low_price, last_price
    FROM hist_td WHERE tos_symbol = 'SPX' AND export_date <= :d
    ORDER BY export_date ASC, sequence DESC
""")


def _load_spx_ohlc(session: Session, as_of_date: date) -> list[dict]:
    """SPX daily OHLC <= D, drv_quote primary + hist_td fallback per-day
    (spec 3.1: "fall back to hist_td if drv_quote history is short" —
    implemented per-day so any single date drv_quote is missing still gets
    filled from hist_td rather than gating on a whole-history-length check)."""
    dq_rows = session.execute(_SPX_QUOTE_SQL, {"d": as_of_date}).mappings().all()
    by_date = {r["as_of_date"]: dict(r) for r in dq_rows}
    td_rows = session.execute(_SPX_TD_SQL, {"d": as_of_date}).mappings().all()
    for r in td_rows:
        by_date.setdefault(r["as_of_date"], dict(r))
    return [by_date[d] for d in sorted(by_date.keys())]


def _valid_ohlc(row: dict) -> bool:
    for k in ("open_price", "high_price", "low_price", "last_price"):
        v = row.get(k)
        if v is None or float(v) <= 0:
            return False
    return True


def _yz_daily_terms(rows: list[dict]) -> list[tuple]:
    """[(date, o_t, c_t, rs_t), ...] — skips any day with non-positive/null
    OHLC or a missing/invalid previous close (needed for the overnight term)."""
    terms = []
    prev_close = None
    for row in rows:
        if not _valid_ohlc(row):
            prev_close = None
            continue
        o = float(row["open_price"]); h = float(row["high_price"])
        l = float(row["low_price"]); c = float(row["last_price"])
        if prev_close is not None and prev_close > 0:
            try:
                o_t = math.log(o / prev_close)
                c_t = math.log(c / o)
                rs_t = math.log(h / c) * math.log(h / o) + math.log(l / c) * math.log(l / o)
                terms.append((row["as_of_date"], o_t, c_t, rs_t))
            except ValueError:
                pass
        prev_close = c
    return terms


def _yang_zhang(terms: list[tuple], n: int) -> Optional[float]:
    """sigma_YZ (percent, annualized) over the trailing n clean observations,
    or None if fewer than n are available. Never substitutes a shorter
    window (spec 3.1 guard)."""
    if len(terms) < n:
        return None
    window = terms[-n:]
    o_vals = [t[1] for t in window]
    c_vals = [t[2] for t in window]
    rs_vals = [t[3] for t in window]
    if n < 2:
        return None
    var_o = statistics.variance(o_vals)     # sample variance, ddof=1
    var_c = statistics.variance(c_vals)
    var_rs = sum(rs_vals) / n               # spec: sigma^2_rs = sum(rs_t) / n
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    variance = var_o + k * var_c + (1 - k) * var_rs
    if variance < 0:
        return None
    return math.sqrt(variance) * math.sqrt(252) * 100.0


_VIX_SQL = text(
    "SELECT last_price FROM drv_quote WHERE tos_symbol='VIX' AND as_of_date=:d"
)

_PRIOR_VRP_SQL = text(
    "SELECT vrp FROM drv_market_stat WHERE as_of_date < :d AND vrp IS NOT NULL "
    "ORDER BY as_of_date DESC LIMIT :n"
)

_BREADTH_SQL = text("""
    SELECT 100.0 * COUNT(*) FILTER (WHERE last_price > sma_50) / NULLIF(COUNT(*),0) AS pct50,
           100.0 * COUNT(*) FILTER (WHERE last_price > sma_200) / NULLIF(COUNT(*),0) AS pct200,
           COUNT(*) AS n
    FROM hist_tw
    WHERE export_date = :d AND last_price IS NOT NULL AND sma_50 IS NOT NULL
      AND tos_symbol NOT LIKE '$%' AND tos_symbol NOT LIKE '/%'
      AND tos_symbol <> ALL(:excl)
""")

_PRIOR_BREADTH_SQL = text(
    "SELECT pct_above_sma50 FROM drv_market_stat WHERE as_of_date < :d "
    "AND pct_above_sma50 IS NOT NULL ORDER BY as_of_date DESC LIMIT 5"
)

_PARTICIPATION_SQL = text(
    "SELECT volume, volume_avg_10d FROM hist_tw "
    "WHERE export_date = :d AND tos_symbol = :sym"
)

_INTERNALS_SQL = text("""
    SELECT symbol, last_value FROM hist_internals
    WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_internals WHERE snapshot_date <= :d)
""")


def _compute_breadth(session: Session, as_of_date: date) -> dict:
    row = session.execute(_BREADTH_SQL, {
        "d": as_of_date, "excl": list(_VOL_GAUGE_SYMS),
    }).mappings().first()
    pct50 = float(row["pct50"]) if row and row["pct50"] is not None else None
    pct200 = float(row["pct200"]) if row and row["pct200"] is not None else None
    n = int(row["n"]) if row and row["n"] is not None else 0

    chg5d = None
    if pct50 is not None:
        prior = [float(r[0]) for r in session.execute(_PRIOR_BREADTH_SQL, {"d": as_of_date}).all()]
        if len(prior) == 5:
            chg5d = pct50 - prior[-1]
    return {"pct_above_sma50": pct50, "pct_above_sma200": pct200,
            "universe_n": n, "pct_above_sma50_5d_chg": chg5d}


def _compute_participation(session: Session, as_of_date: date) -> tuple[Optional[float], str]:
    for sym in ("SPY", "QQQ", "IWM"):
        row = session.execute(_PARTICIPATION_SQL, {"d": as_of_date, "sym": sym}).mappings().first()
        if row and row["volume"] is not None and row["volume_avg_10d"]:
            return float(row["volume"]) / float(row["volume_avg_10d"]), sym
    return None, "none"


def _compute_internals(session: Session, as_of_date: date) -> dict:
    rows = session.execute(_INTERNALS_SQL, {"d": as_of_date}).all()
    by_sym = {r[0]: float(r[1]) if r[1] is not None else None for r in rows}
    adv = by_sym.get("$ADVN")
    dec = by_sym.get("$DECN")
    up = by_sym.get("$UVOL")
    down = by_sym.get("$DVOL")
    trin = None
    if adv and dec and up and down:
        try:
            trin = (adv / dec) / (up / down)
        except ZeroDivisionError:
            trin = None
    vol_breadth = (up / (up + down)) if (up is not None and down is not None and (up + down) > 0) else None
    return {"adv_issues": adv, "dec_issues": dec, "up_volume": up,
            "down_volume": down, "trin": trin, "vol_breadth": vol_breadth}


def _derive_market_stat_impl(session: Session, as_of_date: date, run_id) -> int:
    detail: dict = {}

    # --- 3.1 Yang-Zhang realized vol (SPX) ---
    spx_rows = _load_spx_ohlc(session, as_of_date)
    terms = _yz_daily_terms(spx_rows)
    detail["yz_clean_observations"] = len(terms)
    rv = {n: _yang_zhang(terms, n) for n in YZ_WINDOWS}

    # --- 3.2 VRP ---
    vix_row = session.execute(_VIX_SQL, {"d": as_of_date}).first()
    vix = float(vix_row[0]) if vix_row and vix_row[0] is not None else None
    rv21 = rv[21]
    vrp = (vix - rv21) if (vix is not None and rv21 is not None) else None
    vrp_z = None
    if vrp is not None:
        prior_vrp = [float(r[0]) for r in
                     session.execute(_PRIOR_VRP_SQL, {"d": as_of_date, "n": VRP_Z_LOOKBACK}).all()]
        sample = prior_vrp + [vrp]
        if len(sample) >= VRP_Z_MIN_OBS:
            mean_v = statistics.mean(sample)
            stdev_v = statistics.pstdev(sample) if len(sample) < 2 else statistics.stdev(sample)
            vrp_z = (vrp - mean_v) / stdev_v if stdev_v else None
        detail["vrp_z_sample_n"] = len(sample)

    # --- 3.3 breadth ---
    breadth = _compute_breadth(session, as_of_date)

    # --- 3.4 participation ---
    spy_rvol, participation_src = _compute_participation(session, as_of_date)
    detail["participation_source"] = participation_src

    # --- 4.1 internals (NULL-safe until hist_internals flows) ---
    internals = _compute_internals(session, as_of_date)

    # --- 3.5 Risk Dial ---
    from etl.derive_risk_dial import evaluate_gauges
    extra_ctx = {
        "vrp": vrp,
        "pct_above_sma50": breadth["pct_above_sma50"],
        "pct_above_sma50_5d_chg": breadth["pct_above_sma50_5d_chg"],
        "vol_breadth": internals["vol_breadth"],
    }
    gauges_fired, summary = evaluate_gauges(session, as_of_date, extra_ctx)

    row = {
        "as_of_date": as_of_date,
        "rv10": rv[10], "rv21": rv[21], "rv63": rv[63],
        "vix": vix, "vrp": vrp, "vrp_z": vrp_z,
        "pct_above_sma50": breadth["pct_above_sma50"],
        "pct_above_sma200": breadth["pct_above_sma200"],
        "pct_above_sma50_5d_chg": breadth["pct_above_sma50_5d_chg"],
        "universe_n": breadth["universe_n"],
        "spy_rvol": spy_rvol,
        "adv_issues": internals["adv_issues"], "dec_issues": internals["dec_issues"],
        "up_volume": internals["up_volume"], "down_volume": internals["down_volume"],
        "trin": internals["trin"], "vol_breadth": internals["vol_breadth"],
        "risk_budget": summary["risk_budget"], "risk_label": summary["risk_label"],
        # NOTE: pass raw Python objects, not json.dumps() strings -- this
        # table is written via replace_for_date -> SQLAlchemy Core
        # Table.insert() against a reflected JSONB column, whose bind
        # processor already serializes Python objects itself. Pre-serializing
        # here would double-encode (jsonb_typeof would read back 'string',
        # not 'array'/'object') -- found and fixed during TASK_133 testing.
        "gauges_fired": gauges_fired,
        "detail": {**detail, "fired_weight": summary["fired_weight"],
                   "evaluable_weight": summary["evaluable_weight"]},
    }
    return replace_for_date(session, "drv_market_stat", "as_of_date", as_of_date, [row])


derive_market_stat = _wrap("drv_market_stat", _derive_market_stat_impl)


# ---------------------------------------------------------------------------
# Backfill CLI — lightweight (calls derive_market_stat directly, NOT the full
# derive_all cascade). Pattern mirrors etl/backfill_derives.py.
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--backfill", action="store_true",
                   help="Derive drv_market_stat for every hist_td export_date "
                        "(the anchor calendar), earliest first.")
    p.add_argument("--from", dest="d_from", default=None)
    p.add_argument("--to", dest="d_to", default=None)
    args = p.parse_args()

    if not args.backfill:
        with session_scope() as s:
            d = s.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
            if d is None:
                log.error("No hist_td data loaded.")
                return 1
            n = derive_market_stat(s, d)
        log.info("drv_market_stat @ %s: %d row(s)", d, n)
        return 0

    from datetime import datetime as _dt
    d_from = _dt.strptime(args.d_from, "%Y-%m-%d").date() if args.d_from else None
    d_to = _dt.strptime(args.d_to, "%Y-%m-%d").date() if args.d_to else None
    with session_scope() as s:
        dates = s.execute(text(
            "SELECT DISTINCT export_date FROM hist_td "
            "WHERE (CAST(:f AS date) IS NULL OR export_date >= CAST(:f AS date)) "
            "AND (CAST(:t AS date) IS NULL OR export_date <= CAST(:t AS date)) "
            "ORDER BY export_date"
        ), {"f": d_from, "t": d_to}).scalars().all()

    log.info("Backfilling drv_market_stat for %d dates: %s .. %s",
              len(dates), dates[0] if dates else None, dates[-1] if dates else None)
    ok = 0
    for i, d in enumerate(dates, 1):
        try:
            with session_scope() as s:
                n = derive_market_stat(s, d)
            log.info("[%d/%d] %s: %d row", i, len(dates), d, n)
            ok += 1
        except Exception as e:  # noqa: BLE001
            log.error("[%d/%d] %s FAILED: %s", i, len(dates), d, e)
    log.info("Backfill done: %d/%d dates.", ok, len(dates))
    return 0 if ok == len(dates) else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from etl._logging import setup_logging
    setup_logging()
    raise SystemExit(main())
