"""
drv_bb_rr_gap (TASK_132) — daily TOS-band (BBTop/BBBottom) vs Hedgeye
hist_rr variance tracking + drift alert.

TASK_128–131 fit TOS/BBTop.txt / BBBottom.txt to hist_rr's buy_trade/
sell_trade, but nothing monitored the match on an ongoing basis. This
deriver records the band-vs-RR absolute-percent-error (APE) every day
inside the normal derive cascade, plus a rolling 20-trading-day median and
a WARN/ALERT drift flag that acts as the "time to recalibrate" alarm.

Idempotent: DELETE WHERE as_of_date=D then INSERT (via replace_for_date).
Rows only for symbols present in BOTH hist_rr and hist_td — same
carry-forward alignment (hist_rr snapshot_date <= D, hist_td snapshot_date
< D, EOD max sequence) and reverse-symbol scaling (ref_rrt.reverse,
ref_settings.rr_reverse_scale) as etl/calibrate_tos_rr.py and
etl/derive.py::_derive_rr_impl.

Rolling medians are computed over the symbol's own prior drv_bb_rr_gap
rows (this table IS the rolling-window store — a live view would be
awkward for this). Window includes D; a symbol needs >=5 observations
before ape_*_med20/drift_flag are emitted (else NULL).

See docs/tos_rr_calibration.md "Ongoing monitoring" section for the
threshold rationale and the recalibration playbook.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import _wrap
from etl.db import replace_for_date

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — thresholds calibrated against TASK_130/131's final medians
# (TOP 0.70%, BOTTOM 0.84%). WARN ~= 2x, ALERT ~= 3x. Known structural
# outliers get doubled thresholds so they don't permanently sit in WARN.
# ---------------------------------------------------------------------------
MEDIAN_WINDOW = 20        # trailing trading days (includes D)
MEDIAN_MIN_OBS = 5        # minimum observations before medians/flags are emitted
WARN_TOP_PCT = 1.4
WARN_BOT_PCT = 1.7
ALERT_TOP_PCT = 2.1
ALERT_BOT_PCT = 2.5
ALERT_WARN_COUNT = 10     # >=N symbols simultaneously WARN on the same date -> promote to ALERT (regime shift)
OUTLIER_SYMBOLS = {"VIX", "ORCL", "NFLX"}  # docs/tos_rr_calibration.md — structural outliers
OUTLIER_MULT = 2.0

_RR_SQL = """
    SELECT DISTINCT ON (tos_symbol) tos_symbol, buy_trade, sell_trade
    FROM hist_rr
    WHERE snapshot_date <= :d
    ORDER BY tos_symbol, snapshot_date DESC
"""

_TD_SQL = """
    SELECT DISTINCT ON (tos_symbol) tos_symbol, a_bb_top, a_bb_bottom
    FROM hist_td
    WHERE snapshot_date < :d AND tos_symbol = ANY(:syms)
    ORDER BY tos_symbol, snapshot_date DESC, sequence DESC
"""

_REV_SQL = """
    SELECT DISTINCT ON (tos_ticker) tos_ticker, reverse
    FROM ref_rrt ORDER BY tos_ticker, loaded_at DESC
"""

_PRIOR_SQL = """
    SELECT tos_symbol, ape_top, ape_bottom
    FROM (
        SELECT tos_symbol, ape_top, ape_bottom,
               ROW_NUMBER() OVER (PARTITION BY tos_symbol ORDER BY as_of_date DESC) AS rn
        FROM drv_bb_rr_gap
        WHERE tos_symbol = ANY(:syms) AND as_of_date < :d
    ) x
    WHERE rn <= :w
"""


def _rr_reverse_scale(session: Session) -> float:
    row = dict(session.execute(text(
        "SELECT setting_name, CAST(setting_value AS NUMERIC) FROM ref_settings "
        "WHERE setting_name = 'rr_reverse_scale'"
    )).fetchall())
    return float(row.get("rr_reverse_scale", 10))


def _scaled(raw, is_rev: bool, scale: float) -> Optional[float]:
    """NULLIF(raw,0)-style guard, then reverse-symbol scale — matches
    etl/derive.py::_derive_rr_impl's LRR/TRR CASE expression."""
    if raw is None or raw == 0:
        return None
    v = float(raw)
    return v * scale if is_rev else v


def _drift_flag(sym: str, ape_top_med: Optional[float],
                ape_bot_med: Optional[float]) -> Optional[str]:
    """Per-symbol WARN/ALERT from the rolling medians. Outlier symbols use
    doubled thresholds. The >=10-symbols-WARN universe-wide override is
    applied by the caller after every symbol's base flag is known."""
    if ape_top_med is None and ape_bot_med is None:
        return None
    mult = OUTLIER_MULT if sym in OUTLIER_SYMBOLS else 1.0
    if ((ape_top_med is not None and ape_top_med > ALERT_TOP_PCT * mult)
            or (ape_bot_med is not None and ape_bot_med > ALERT_BOT_PCT * mult)):
        return "ALERT"
    if ((ape_top_med is not None and ape_top_med > WARN_TOP_PCT * mult)
            or (ape_bot_med is not None and ape_bot_med > WARN_BOT_PCT * mult)):
        return "WARN"
    return None


def _derive_bb_rr_gap_impl(session: Session, as_of_date: date, run_id: int) -> int:
    rr_scale = _rr_reverse_scale(session)

    rr_rows = session.execute(text(_RR_SQL), {"d": as_of_date}).mappings().all()
    if not rr_rows:
        return replace_for_date(session, "drv_bb_rr_gap", "as_of_date", as_of_date, [])
    rr_by_sym = {r["tos_symbol"]: r for r in rr_rows}
    rr_syms = list(rr_by_sym.keys())

    td_rows = session.execute(text(_TD_SQL), {"d": as_of_date, "syms": rr_syms}).mappings().all()
    td_by_sym = {r["tos_symbol"]: r for r in td_rows}

    # Rows only for symbols present in BOTH feeds.
    both_syms = [s for s in rr_syms if s in td_by_sym]
    if not both_syms:
        return replace_for_date(session, "drv_bb_rr_gap", "as_of_date", as_of_date, [])

    reverse_map = dict(session.execute(text(_REV_SQL)).fetchall())

    prior_rows = session.execute(text(_PRIOR_SQL), {
        "d": as_of_date, "syms": both_syms, "w": MEDIAN_WINDOW - 1,
    }).mappings().all()
    prior_by_sym: dict = {}
    for r in prior_rows:
        prior_by_sym.setdefault(r["tos_symbol"], []).append(r)

    rows = []
    warn_syms: list[str] = []
    for sym in both_syms:
        rr, td = rr_by_sym[sym], td_by_sym[sym]
        is_rev = reverse_map.get(sym) == "Y"
        rr_buy = _scaled(rr["buy_trade"], is_rev, rr_scale)
        rr_sell = _scaled(rr["sell_trade"], is_rev, rr_scale)
        bb_top = float(td["a_bb_top"]) if td["a_bb_top"] is not None else None
        bb_bottom = float(td["a_bb_bottom"]) if td["a_bb_bottom"] is not None else None

        ape_top = (abs(bb_top - rr_sell) / rr_sell * 100
                   if bb_top is not None and rr_sell not in (None, 0) else None)
        ape_bottom = (abs(bb_bottom - rr_buy) / rr_buy * 100
                      if bb_bottom is not None and rr_buy not in (None, 0) else None)

        hist = prior_by_sym.get(sym, [])
        top_vals = [float(h["ape_top"]) for h in hist if h["ape_top"] is not None]
        bot_vals = [float(h["ape_bottom"]) for h in hist if h["ape_bottom"] is not None]
        if ape_top is not None:
            top_vals.append(ape_top)
        if ape_bottom is not None:
            bot_vals.append(ape_bottom)
        top_med = statistics.median(top_vals) if len(top_vals) >= MEDIAN_MIN_OBS else None
        bot_med = statistics.median(bot_vals) if len(bot_vals) >= MEDIAN_MIN_OBS else None

        flag = _drift_flag(sym, top_med, bot_med)
        if flag == "WARN":
            warn_syms.append(sym)

        rows.append({
            "as_of_date": as_of_date,
            "tos_symbol": sym,
            "bb_top": bb_top,
            "bb_bottom": bb_bottom,
            "rr_sell": rr_sell,
            "rr_buy": rr_buy,
            "ape_top": ape_top,
            "ape_bottom": ape_bottom,
            "ape_top_med20": top_med,
            "ape_bottom_med20": bot_med,
            "drift_flag": flag,
            "source_run_id": run_id,
        })

    # Universe-wide drift override: >=10 symbols simultaneously WARN on the
    # same date reads as a regime shift, not a single-name event -> ALERT.
    if len(warn_syms) >= ALERT_WARN_COUNT:
        warn_set = set(warn_syms)
        for r in rows:
            if r["tos_symbol"] in warn_set:
                r["drift_flag"] = "ALERT"

    return replace_for_date(session, "drv_bb_rr_gap", "as_of_date", as_of_date, rows)


derive_bb_rr_gap = _wrap("drv_bb_rr_gap", _derive_bb_rr_gap_impl)
