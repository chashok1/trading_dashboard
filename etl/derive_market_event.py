"""
etl/derive_market_event.py -- TASK_133 Phase 6.2: drv_market_event.

"What changed" -- the second cockpit band. Detectors run in this priority
order (a highest-trust first):

  (a) Risk-range events -- deterministic, no statistics (range_break_up/down,
      trend_flip via drv_rr_trend_change, entered_top/bottom_decile via
      api._helpers.rr_pos crossing 0.85/0.15).
  (b) Z-scores -- only where risk ranges don't reach. Rates are scored on
      basis-point change, not percent (spec 6.2b).
  (c) The 8 ref_market_pattern conditions (built on (b)'s z-scores).
  (d) Calendar (ref_calendar_event) + surprise/trend-deviation.

CROSSINGS ONLY: a gauge sustained for many days is not re-emitted every day --
only the day the state changes. This is the whole point of the band (spec:
"a VIX elevated for nine days is not news on day nine").

Wired into derive_all() AFTER derive_market_stat() (needs drv_market_stat's
vrp / risk_budget for context, and ref_vol_threshold crossings need day-2
history that's already resolved by then).
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import _wrap
from etl.db import replace_for_date
from api._helpers import rr_pos

log = logging.getLogger(__name__)

# Symbols z-scored for the (b)/(c) detectors. is_rate=True -> z is computed on
# basis-point day-over-day change, not pct_change (a % change on a yield near
# zero is meaningless -- spec 6.2b).
_Z_SYMBOLS = [
    ("SPX", False), ("VIX", False), ("$DXY", False), ("TNX:CGI", True),
    ("HYG", False), ("/CL", False), ("/GC", False), ("/HG", False),
    ("/NG", False), ("/6J", False), ("EWY", False),
]
_Z_LOOKBACK = 60          # trading days
_Z_WARN, _Z_SEVERE = 2.0, 3.0

# High-impact calendar categories (spec 6d). Matched case-insensitively as a
# substring so 'CPI MoM'/'CPI YOY'/'CPI Core MoM' etc. all match 'CPI', and
# both 'FOMC Minutes' (spec spelling) and 'FMOC Minutes' (a live typo in the
# workbook data, confirmed via `SELECT DISTINCT category` during Phase 6
# build) match.
_HIGH_IMPACT = ("fed meeting", "fomc", "fmoc", "cpi", "ppi", "pce",
                "gdp", "nfp", "ism mfg", "ism svcs")

# Categories where NO free consensus exists -- spec 6d table, third row.
# Shown as "actual vs its own 3-month trend", labelled a deviation, never a
# "surprise". CPI is handled separately (Hedgeye Nowcast IS a real forecast).
_TREND_ONLY = ("unemp", "nfp", "adp nfp", "ism", "ppi", "gdp", "pce")


def _get_series(session: Session, symbol: str, lo: date, hi: date) -> dict:
    """{date: value} for `symbol`, trying drv_quote (tos-native symbols)
    first, then hist_macro (FRED/Yahoo/Cboe-only series -- e.g. ^KS11, which
    the KOSPI Yahoo fetch (Phase 4.2) writes to hist_macro, not drv_quote)."""
    rows = session.execute(text(
        "SELECT as_of_date, last_price FROM drv_quote "
        "WHERE tos_symbol = :s AND as_of_date BETWEEN :lo AND :hi"
    ), {"s": symbol, "lo": lo, "hi": hi}).all()
    out = {d: float(v) for d, v in rows if v is not None}
    if not out:
        rows = session.execute(text(
            "SELECT obs_date, value FROM hist_macro "
            "WHERE series_id = :s AND obs_date BETWEEN :lo AND :hi"
        ), {"s": symbol, "lo": lo, "hi": hi}).all()
        out = {d: float(v) for d, v in rows if v is not None}
    if symbol == "TNX:CGI":
        # Same scale inconsistency documented in api._helpers.rr_pos(): TL/TD
        # rows land on the x10 index-level convention (~45-50 for 4.5-5.0%),
        # 'Y'-sourced rows are plain percent (~4.5-5.0). Without an lrr/trr
        # midpoint to guard against here (this is a raw time series, not a
        # range position), normalize on a fixed absolute threshold instead --
        # 10Y yields realistically sit in 1-10%, so anything < 15 is plain
        # percent and gets x10'd to match the dominant convention. Found
        # during Phase 6 build: an un-normalized day produced a bogus
        # ~4200bp z-score day-over-day jump.
        out = {d: (v * 10.0 if v < 15 else v) for d, v in out.items()}
    return out


def _zscores(session: Session, as_of_date: date) -> dict:
    """{symbol: (z, latest_value, latest_change)} for _Z_SYMBOLS.

    z = (today's change - mean(60d changes)) / stdev(60d changes). 'change'
    is basis points for rate symbols, percent otherwise."""
    lo = as_of_date - timedelta(days=int(_Z_LOOKBACK * 1.6) + 10)
    out: dict = {}
    for sym, is_rate in _Z_SYMBOLS:
        series = _get_series(session, sym, lo, as_of_date)
        dates = sorted(series)
        if len(dates) < 20:
            continue
        changes = []
        for i in range(1, len(dates)):
            prev, cur = series[dates[i - 1]], series[dates[i]]
            if is_rate:
                changes.append((cur - prev) * 100.0)   # index pts -> bp (x10 scale, see rr_pos)
            elif prev:
                changes.append((cur / prev - 1.0) * 100.0)
        changes = changes[-_Z_LOOKBACK:]
        if len(changes) < 20:
            continue
        mean_c = statistics.fmean(changes)
        try:
            sd = statistics.stdev(changes)
        except statistics.StatisticsError:
            continue
        if not sd:
            continue
        today_chg = changes[-1]
        z = (today_chg - mean_c) / sd
        out[sym] = (z, series[dates[-1]], today_chg)
    return out


def _severity(z: float) -> Optional[str]:
    if abs(z) >= _Z_SEVERE:
        return "severe"
    if abs(z) >= _Z_WARN:
        return "warn"
    return None


def _risk_range_events(session: Session, as_of_date: date, prev_date: Optional[date]) -> list:
    """(a) range_break_up/down, trend_flip, entered_top/bottom_decile."""
    events = []
    # TASK_134 B.3: genuine Hedgeye risk-range instruments only (source='RR',
    # ~55 curated symbols) -- excludes the 'BB' TOS-Bollinger-band fallback
    # rows drv_rr synthesizes for the entire ~1,000-symbol universe, which
    # otherwise flood this band with range-break/decile events for symbols
    # (e.g. ATRO, PNDRY) that were never in the Hedgeye Risk Range feed.
    rr_today = {r[0]: r for r in session.execute(text(
        "SELECT tos_symbol, lrr, trr FROM drv_rr WHERE as_of_date = :d AND source = 'RR'"
    ), {"d": as_of_date}).all()}
    q_today = {r[0]: r[1] for r in session.execute(text(
        "SELECT tos_symbol, last_price FROM drv_quote WHERE as_of_date = :d"
    ), {"d": as_of_date}).all()}
    if prev_date:
        q_prev = {r[0]: r[1] for r in session.execute(text(
            "SELECT tos_symbol, last_price FROM drv_quote WHERE as_of_date = :d"
        ), {"d": prev_date}).all()}
    else:
        q_prev = {}

    for sym, (_, lrr, trr) in rr_today.items():
        last = q_today.get(sym)
        prev = q_prev.get(sym)
        if last is None or lrr is None or trr is None:
            continue
        last, lrr, trr = float(last), float(lrr), float(trr)
        pos_today = rr_pos(last, lrr, trr)
        pos_prev = rr_pos(prev, lrr, trr) if prev is not None else None
        was_inside = prev is not None and lrr <= float(prev) <= trr
        if last > trr and was_inside:
            events.append(("range_break_up", "warn", sym,
                          f"{sym} broke above its risk range top (TRR {trr:g})",
                          {"last": last, "trr": trr, "lrr": lrr}))
        elif last < lrr and was_inside:
            events.append(("range_break_down", "warn", sym,
                          f"{sym} broke below its risk range bottom (LRR {lrr:g})",
                          {"last": last, "trr": trr, "lrr": lrr}))
        if pos_today is not None and pos_prev is not None:
            if pos_today >= 0.85 and pos_prev < 0.85:
                events.append(("entered_top_decile", "info", sym,
                              f"{sym} entered the top decile of its risk range",
                              {"rr_pos": round(pos_today, 3)}))
            if pos_today <= 0.15 and pos_prev > 0.15:
                events.append(("entered_bottom_decile", "info", sym,
                              f"{sym} entered the bottom decile of its risk range",
                              {"rr_pos": round(pos_today, 3)}))

    # TASK_134 B.3: verified, not assumed -- drv_rr_trend_change (db/baseline.sql)
    # is a VIEW built directly off hist_rr (LAG(outlook) partitioned by
    # tos_symbol), not off drv_rr. hist_rr is the raw Hedgeye Risk Range feed
    # table itself -- it is only ever populated for the curated ~55
    # instruments the feed covers, so BB-fallback symbols (which exist only
    # in drv_rr, synthesized from hist_td Bollinger columns) can never reach
    # this query. No filter needed here.
    flips = session.execute(text(
        "SELECT tos_symbol, from_trend, to_trend FROM drv_rr_trend_change "
        "WHERE as_of_date = :d"
    ), {"d": as_of_date}).all()
    for sym, from_t, to_t in flips:
        events.append(("trend_flip", "warn", sym,
                      f"{sym} Trend flipped {from_t} -> {to_t}",
                      {"from": from_t, "to": to_t}))
    return events


def _vol_zone(v: float, low: float, high: float) -> str:
    """Pure classifier used by _vol_regime_events -- extracted so the
    CROSSING-not-level property (spec 6.2: only the transition day emits an
    event) is unit-testable without a DB session. See tests/test_market_patterns.py."""
    if v < float(low):
        return "low"
    if v > float(high):
        return "high"
    return "chop"


def _vol_regime_events(session: Session, as_of_date: date, prev_date: Optional[date]) -> list:
    """vol_regime_break -- a ref_vol_threshold gauge CROSSED a low/chop/high
    boundary today (not merely sustained above it)."""
    if not prev_date:
        return []
    thresh = session.execute(text(
        "SELECT tos_symbol, low, high FROM ref_vol_threshold"
    )).all()
    events = []
    for sym, low, high in thresh:
        vt = _get_series(session, sym, prev_date, as_of_date)
        if prev_date not in vt or as_of_date not in vt:
            continue
        z_prev = _vol_zone(vt[prev_date], low, high)
        z_today = _vol_zone(vt[as_of_date], low, high)
        if z_prev != z_today:
            events.append(("vol_regime_break", "severe" if z_today == "high" else "warn",
                          sym, f"{sym} crossed from {z_prev} into {z_today} zone "
                               f"({vt[as_of_date]:g})", {"from": z_prev, "to": z_today}))
    return events


def _pattern_events(z: dict) -> list:
    """(c) the 8 seeded ref_market_pattern conditions, from z-scores in `z`."""
    def zv(sym):
        return z.get(sym, (None, None, None))[0]

    events = []
    if (zv("/6J") is not None and zv("/6J") >= 2.0
            and ((zv("TNX:CGI") is not None and zv("TNX:CGI") <= -1.0)
                 or (zv("/GC") is not None and zv("/GC") >= 1.0))):
        events.append(("yen_bid",))
    if (zv("$DXY") is not None):
        z_dxy, last_dxy, _ = z["$DXY"]
        # rr_pos($DXY) >= 0.85 substitutes z-based "at top of range" proxy
        # when drv_rr has no $DXY row -- use z >= 1.5 as the practical proxy,
        # documented in DEV_HANDOFF.md (drv_rr does not track $DXY).
        commod = [zv(s) for s in ("/CL", "/GC", "/HG", "/NG") if zv(s) is not None]
        if commod and statistics.fmean(commod) <= -1.0 and z_dxy is not None and z_dxy >= 1.5:
            events.append(("dollar_wrecking_ball",))
    if zv("TNX:CGI") is not None and abs(zv("TNX:CGI")) >= 2.0:
        events.append(("rates_shock",))
    if ((zv("HYG") is not None and zv("HYG") <= -2.0)
            and zv("SPX") is not None and abs(zv("SPX")) < 1.0):
        events.append(("credit_leads_equity",))
    if (zv("/GC") is not None and zv("/GC") >= 2.0
            and zv("TNX:CGI") is not None and zv("TNX:CGI") <= -1.0
            and zv("SPX") is not None and zv("SPX") <= -1.0):
        events.append(("flight_to_quality",))
    if zv("EWY") is not None and zv("EWY") <= -2.0:
        events.append(("korea_semis",))
    return events


def _oil_squeeze_event(session: Session, as_of_date: date, prev_date: Optional[date]) -> list:
    """oil_squeeze -- rr_pos(/CL) >= 0.85 AND OVX:CGI rising into elevated.
    Needs drv_rr's lrr/trr for /CL (not a z-score input), so it's computed
    separately from _pattern_events rather than folded into it."""
    if not prev_date:
        return []
    rr = session.execute(text(
        "SELECT lrr, trr FROM drv_rr WHERE tos_symbol = '/CL' AND as_of_date = :d"
    ), {"d": as_of_date}).first()
    last = session.execute(text(
        "SELECT last_price FROM drv_quote WHERE tos_symbol = '/CL' AND as_of_date = :d"
    ), {"d": as_of_date}).scalar()
    if not rr or last is None:
        return []
    pos = rr_pos(last, rr[0], rr[1])
    if pos is None or pos < 0.85:
        return []
    ovx = _get_series(session, "OVX:CGI", prev_date, as_of_date)
    thresh = session.execute(text(
        "SELECT high FROM ref_vol_threshold WHERE tos_symbol = 'OVX:CGI'"
    )).scalar()
    if prev_date not in ovx or as_of_date not in ovx or thresh is None:
        return []
    rising_into_elevated = ovx[as_of_date] > ovx[prev_date] and ovx[as_of_date] > float(thresh)
    if not rising_into_elevated:
        return []
    return [("oil_squeeze",)]


def _calendar_events(session: Session, as_of_date: date) -> list:
    """(d) calendar (D, D+1) + surprise/trend-deviation."""
    d1 = as_of_date + timedelta(days=1)
    rows = session.execute(text(
        "SELECT category, event_date FROM ref_calendar_event "
        "WHERE event_date IN (:d0, :d1)"
    ), {"d0": as_of_date, "d1": d1}).all()
    events = []
    for cat, ev_date in rows:
        cat_l = (cat or "").lower()
        if not any(h in cat_l for h in _HIGH_IMPACT):
            continue
        title = f"{cat} due {ev_date:%Y-%m-%d}"
        legs = {"category": cat, "event_date": ev_date.isoformat()}
        if "cpi" in cat_l:
            nowcast = session.execute(text(
                "SELECT obs_date, value FROM hist_macro WHERE series_id = 'HE_CPI_NOWCAST' "
                "ORDER BY obs_date DESC LIMIT 1"
            )).first()
            if nowcast:
                legs["hedgeye_nowcast"] = float(nowcast[1])
                legs["nowcast_date"] = nowcast[0].isoformat()
                read_text = (f"Hedgeye CPI Nowcast {nowcast[1]:.2f}% vs the last print -- "
                             "see the Actionable Hedgeye panel for the parsed print once it lands.")
            else:
                read_text = None
            events.append(("calendar", "info", None, None, title, legs, read_text))
        elif any(h in cat_l for h in _TREND_ONLY):
            events.append(("calendar", "info", None, None, title, legs,
                          "No free consensus exists for this release -- "
                          "compare the print to its own 3-month trend, not a surprise."))
        else:
            events.append(("calendar", "info", None, None, title, legs, None))
    return events


def _derive_market_event_impl(session: Session, as_of_date: date, run_id) -> int:
    prev_date = session.execute(text(
        "SELECT MAX(export_date) FROM hist_td WHERE export_date < :d"
    ), {"d": as_of_date}).scalar()

    rows_out = []
    seq = 0

    def _emit(event_type, severity, tos_symbol, pattern_key, title, legs, read_text, exposure=None):
        nonlocal seq
        rows_out.append({
            "as_of_date": as_of_date, "event_seq": seq, "event_type": event_type,
            "severity": severity, "tos_symbol": tos_symbol, "pattern_key": pattern_key,
            "title": title, "legs": legs, "read_text": read_text, "exposure": exposure,
        })
        seq += 1

    for etype, sev, sym, title, legs in _risk_range_events(session, as_of_date, prev_date):
        _emit(etype, sev, sym, None, title, legs, None)

    for etype, sev, sym, title, legs in _vol_regime_events(session, as_of_date, prev_date):
        _emit(etype, sev, sym, None, title, legs, None)

    z = _zscores(session, as_of_date)
    max_abs_z, max_z_sym = 0.0, None
    for sym, (zval, last_val, chg) in z.items():
        if abs(zval) > max_abs_z:
            max_abs_z, max_z_sym = abs(zval), sym
        sev = _severity(zval)
        if sev:
            _emit("zscore", sev, sym, None,
                 f"{sym} {chg:+.2f}{'bp' if sym == 'TNX:CGI' else '%'} today, z={zval:+.2f}",
                 {"z": round(zval, 2), "value": last_val, "change": round(chg, 3)}, None)

    patt_rows = session.execute(text(
        "SELECT pattern_key, label, read_text, severity FROM ref_market_pattern WHERE is_active"
    )).mappings().all()
    patt_map = {r["pattern_key"]: r for r in patt_rows}
    fired_patterns = _pattern_events(z) + _oil_squeeze_event(session, as_of_date, prev_date)
    for (pkey,) in fired_patterns:
        p = patt_map.get(pkey)
        if not p:
            continue
        _emit("pattern", p["severity"], None, pkey, p["label"], None, p["read_text"])

    for etype, sev, sym, pkey, title, legs, read_text in _calendar_events(session, as_of_date):
        _emit(etype, sev, sym, pkey, title, legs, read_text)

    # Exposure per row via ref_gauge_transmission -> drv_category_perf, for
    # any event whose type key (event_type for range/vol events keyed by
    # tos_symbol don't map cleanly to a gauge_key, so only pattern_key rows
    # and rows whose tos_symbol matches a ref_risk_gauge's implicit key get
    # exposure -- pattern rows are the common, documented case (spec 6.1's
    # exposure example is on a *gauge*, reused identically here for patterns).
    if rows_out:
        pattern_keys = {r["pattern_key"] for r in rows_out if r["pattern_key"]}
        if pattern_keys:
            trans = session.execute(text(
                "SELECT gauge_key, axis, category FROM ref_gauge_transmission "
                "WHERE gauge_key = ANY(:keys)"
            ), {"keys": list(pattern_keys)}).all()
            by_key: dict = {}
            for gk, axis, cat in trans:
                by_key.setdefault(gk, []).append((axis, cat))
            cat_rows = session.execute(text(
                "SELECT axis, category, market_value FROM drv_category_perf WHERE as_of_date = :d"
            ), {"d": as_of_date}).all()
            mv_map = {(a, c): float(v or 0) for a, c, v in cat_rows}
            for r in rows_out:
                pk = r["pattern_key"]
                if pk in by_key:
                    exp_cats = by_key[pk]
                    dollar = sum(mv_map.get((a, c), 0.0) for a, c in exp_cats)
                    r["exposure"] = {
                        "categories": [f"{a}:{c}" for a, c in exp_cats],
                        "dollar": round(dollar, 2),
                    }

    if not rows_out:
        _emit("quiet", "info", None, None, "No material market events today", None, None,
             exposure={"quiet": True, "instruments_checked": len(_Z_SYMBOLS),
                       "max_abs_z": round(max_abs_z, 2), "max_z_symbol": max_z_sym,
                       "range_breaks": 0})

    return replace_for_date(session, "drv_market_event", "as_of_date", as_of_date, rows_out)


derive_market_event = _wrap("drv_market_event", _derive_market_event_impl)
