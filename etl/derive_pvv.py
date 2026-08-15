"""
drv_pvv — Price/Volume/Volatility (PVV, Hedgeye-style ROC) multi-bucket
signal + consolidated decision.

Informational v1: surfaced as a new column on the Actionable screen, but
NOT wired into drv_actionable / consolidated_action scoring (a later task
may do so). Idempotent: DELETE WHERE as_of_date=D then INSERT.

Full spec: docs/pvv_logic.md (bucket definitions, signal-code table,
decision matrix, JSONB detail shape), agent-tasks/TASK_125_pvv_buckets_actionable.md
(bucket calcs) and agent-tasks/TASK_127_pvv_outlook_decision.md (decision
layer — outlook x sig_today, TASK_127 superseded TASK_125's bucket-alignment
matrix).
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

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config — module-level constants for v1. A later task may move these to
# ref_param so they're tunable without a code change.
# ---------------------------------------------------------------------------
PVV_CONFIG = {
    "flat_band_today": 1.0,   # sigma multiplier — wide, alert-only band
    "flat_band_5d":    0.5,
    "flat_band_3w":    0.5,
    "sigma_window":     60,   # trailing rolling-ROC observations for sigma
    "sigma_min_obs":    20,   # minimum observations before trusting own sigma
    "iv_pctile_hi":     70,   # 3m bucket: vol direction up threshold
    "iv_pctile_lo":     30,   # 3m bucket: vol direction down threshold
    "min_window_pts":    3,   # fewer usable points in a ROC window -> NA
    "history_days":     180,  # calendar-day lookback for the daily series fetch
    "eod_vol_avg_n":     20,  # trailing days for "today" bucket's avg EOD volume
}

# =============================================================================
# Pure classification functions — unit-testable without a DB connection.
# =============================================================================

def classify_pvv(p_dir: Optional[str], v_dir: Optional[str],
                 vol_dir: Optional[str]) -> str:
    """Per-bucket signal code from Price/Volume/Volatility directions.

    p_dir / v_dir / vol_dir in {'up', 'down', 'flat'} — None means missing
    data for that leg (bucket signal -> 'NA'). Volume 'flat' resolves toward
    'down' (unconfirmed); Volatility 'flat' resolves toward 'down' (calm).
    See docs/pvv_logic.md §3.
    """
    if p_dir is None or v_dir is None or vol_dir is None:
        return "NA"
    if p_dir not in ("up", "down", "flat"):
        return "NA"
    if p_dir == "flat":
        return "NEUTRAL"
    v = "down" if v_dir == "flat" else v_dir
    vol = "down" if vol_dir == "flat" else vol_dir
    table = {
        ("up",   "up",   "down"): "STRONG_BULL",
        ("up",   "up",   "up"):   "OVEREXT_BULL",
        ("up",   "down", "down"): "WEAK_BULL",
        ("up",   "down", "up"):   "BEAR_DIV",
        ("down", "up",   "up"):   "STRONG_BEAR",
        ("down", "up",   "down"): "MILD_BEAR",
        ("down", "down", "down"): "DRIFT",
        ("down", "down", "up"):   "BEAR_LEAN",
    }
    return table.get((p_dir, v, vol), "NA")


def classify_pvv_3m(p_dir: Optional[str], vol_dir: Optional[str]) -> str:
    """3m bucket has no volume leg — classify on Price/Vol only (§3)."""
    if p_dir is None or vol_dir is None:
        return "NA"
    if p_dir == "flat":
        return "NEUTRAL"
    vol = "down" if vol_dir == "flat" else vol_dir
    if p_dir == "up" and vol == "down":
        return "STRONG_BULL"
    if p_dir == "up" and vol == "up":
        return "OVEREXT_BULL"
    if p_dir == "down" and vol == "up":
        return "STRONG_BEAR"
    if p_dir == "down" and vol == "down":
        return "DRIFT"
    return "NA"


def _normalize_outlook(outlook: Optional[str]) -> Optional[str]:
    """Case-insensitive/trim normalize an RR outlook string to the canonical
    display label 'Bullish' / 'Bearish' / 'Neutral', or None for missing /
    unrecognized values. See docs/pvv_logic.md §4."""
    if outlook is None:
        return None
    s = str(outlook).strip()
    if not s:
        return None
    su = s.upper()
    if su == "BULLISH":
        return "Bullish"
    if su == "BEARISH":
        return "Bearish"
    if su == "NEUTRAL":
        return "Neutral"
    return None


# outlook decides WHAT, sig_today decides WHEN (docs/pvv_logic.md §4). Each
# sig_today row maps {Bullish outlook -> decision, Bearish outlook -> decision};
# Neutral outlook and no-outlook both fall through to WATCH (below).
_PVV_DECISION_MATRIX = {
    "STRONG_BULL":  {"Bullish": "BUY",     "Bearish": "TRIM"},
    "WEAK_BULL":    {"Bullish": "BUY",     "Bearish": "TRIM"},
    "OVEREXT_BULL": {"Bullish": "TRIM",    "Bearish": "TRIM"},
    "BEAR_DIV":     {"Bullish": "WATCH",   "Bearish": "TRIM"},
    "NEUTRAL":      {"Bullish": "WATCH",   "Bearish": "AVOID"},
    "NA":           {"Bullish": "WATCH",   "Bearish": "AVOID"},
    "DRIFT":        {"Bullish": "BUY_DIP", "Bearish": "AVOID"},
    "MILD_BEAR":    {"Bullish": "BUY_DIP", "Bearish": "REDUCE"},
    "BEAR_LEAN":    {"Bullish": "BUY_DIP", "Bearish": "REDUCE"},
    "STRONG_BEAR":  {"Bullish": "WATCH",   "Bearish": "SELL"},   # knife guard
}


def decide_pvv(sig_today: Optional[str], outlook: Optional[str]) -> str:
    """Consolidated decision — RR outlook decides WHAT (direction), today's
    PVV signal decides WHEN (timing). See docs/pvv_logic.md §4 for the full
    9x3 matrix (TASK_127).

    Deliberate "knife guard": bullish outlook + STRONG_BEAR sig_today (a
    heavy-volume selloff day) does NOT fire BUY_DIP — it waits at WATCH
    rather than trying to catch the falling knife. Bearish outlook + any
    up-tape sig_today ("sell the rip") consolidates to TRIM. Neutral outlook
    and no-outlook (missing/NULL, e.g. BB-fallback rows) are both WATCH
    across every sig_today value. sig_5d/sig_3w/sig_3m no longer influence
    the decision — they remain display-only context in `detail`.
    """
    label = _normalize_outlook(outlook)
    row = _PVV_DECISION_MATRIX.get(sig_today, _PVV_DECISION_MATRIX["NA"])
    if label == "Bullish":
        return row["Bullish"]
    if label == "Bearish":
        return row["Bearish"]
    return "WATCH"


# =============================================================================
# Numeric helpers
# =============================================================================

def _roc(cur: Optional[float], prev: Optional[float]) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return (float(cur) - float(prev)) / float(prev)


def _direction(roc: Optional[float], sigma: Optional[float], k: float) -> Optional[str]:
    """Sign of `roc`, resolved to 'flat' when |roc| < k * sigma."""
    if roc is None:
        return None
    band = k * (sigma or 0.0)
    if abs(roc) < band:
        return "flat"
    return "up" if roc > 0 else "down"


def _rolling_roc_series(values: list, horizon: int, window: int) -> list:
    """Trailing up-to-`window` ROC(horizon) values from a daily series
    (oldest -> newest, one point per trading day, None allowed)."""
    out = []
    n = len(values)
    for i in range(horizon, n):
        prev = values[i - horizon]
        cur = values[i]
        r = _roc(cur, prev)
        if r is not None:
            out.append(r)
    return out[-window:]


def _trailing_sigma(values: list, horizon: int, min_obs: int, window: int) -> Optional[float]:
    """Own-symbol sigma of the ROC(horizon) series. None if too few points."""
    series = _rolling_roc_series(values, horizon, window)
    if len(series) < min_obs:
        return None
    try:
        return statistics.pstdev(series)
    except statistics.StatisticsError:
        return None


def _series_value_near(series: list, target: date, tol: int = 3):
    """series: list of (date, value) ascending. Nearest non-null value within
    `tol` calendar days of `target`, else None (missing-day fallback, §2)."""
    best = None
    best_diff = None
    for d, v in series:
        if v is None:
            continue
        diff = abs((d - target).days)
        if diff > tol:
            continue
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best = v
    return best


def _apply_3w_gate(sig: Optional[str], last_price, a_trend_value):
    """Duration-level gate on the 3w bucket (§2): demote one notch toward
    NEUTRAL when price hasn't confirmed the trend-value level."""
    if sig is None or last_price is None or a_trend_value is None:
        return sig, False
    try:
        last_price = float(last_price)
        a_trend_value = float(a_trend_value)
    except (TypeError, ValueError):
        return sig, False
    if sig == "STRONG_BULL" and last_price < a_trend_value:
        return "WEAK_BULL", True
    if sig == "WEAK_BULL" and last_price < a_trend_value:
        return "NEUTRAL", True
    if sig == "STRONG_BEAR" and last_price > a_trend_value:
        return "MILD_BEAR", True
    if sig == "MILD_BEAR" and last_price > a_trend_value:
        return "NEUTRAL", True
    return sig, False


def _round(v, nd=4):
    if v is None:
        return None
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


# =============================================================================
# Deriver
# =============================================================================

def _fetch_daily_td_series(session: Session, symbols: list, start: date, d: date) -> dict:
    """{tos_symbol: [(export_date, last_price, historical_vol, imp_volatility), ...]}
    ascending, one row per trading day (max sequence per day)."""
    if not symbols:
        return {}
    rows = session.execute(text("""
        SELECT tos_symbol, export_date, last_price, historical_vol, imp_volatility
        FROM (
            SELECT tos_symbol, export_date, last_price, historical_vol, imp_volatility,
                   ROW_NUMBER() OVER (
                       PARTITION BY tos_symbol, export_date ORDER BY sequence DESC
                   ) AS rn
            FROM hist_td
            WHERE export_date <= :d AND export_date >= :start
              AND tos_symbol = ANY(:syms)
        ) x
        WHERE rn = 1
        ORDER BY tos_symbol, export_date ASC
    """), {"d": d, "start": start, "syms": symbols}).fetchall()
    out: dict = {}
    for sym, ed, lp, hv, iv in rows:
        out.setdefault(sym, []).append((ed, lp, hv, iv))
    return out


def _fetch_daily_tl_volume(session: Session, symbols: list, start: date, d: date) -> dict:
    """{tos_symbol: [(export_date, volume), ...]} ascending, EOD (max sequence
    per day) volume — hist_td carries no volume column."""
    if not symbols:
        return {}
    rows = session.execute(text("""
        SELECT tos_symbol, export_date, volume
        FROM (
            SELECT tos_symbol, export_date, volume,
                   ROW_NUMBER() OVER (
                       PARTITION BY tos_symbol, export_date ORDER BY sequence DESC
                   ) AS rn
            FROM hist_tl
            WHERE export_date <= :d AND export_date >= :start
              AND tos_symbol = ANY(:syms)
        ) x
        WHERE rn = 1
        ORDER BY tos_symbol, export_date ASC
    """), {"d": d, "start": start, "syms": symbols}).fetchall()
    out: dict = {}
    for sym, ed, vol in rows:
        out.setdefault(sym, []).append((ed, float(vol) if vol is not None else None))
    return out


def _fetch_rr_outlook(session: Session, symbols: list, d: date) -> dict:
    """{tos_symbol: (outlook_raw, source)} from drv_rr for D.

    Within a fresh derive_all() cascade, derive_pvv now runs AFTER
    _derive_rr_outlook_from_qe's second-pass UPDATE (etl/derive.py, fixed
    2026-08-15 — used to run before it, so every source='BB' row was still
    outlook=NULL at this point, every day, not an edge case: measured 73% of
    that day's WATCH rows), so BB-fallback rows see their filled-in outlook
    the same as everything else. A standalone re-derive of drv_pvv alone
    (outside a full derive_all() cascade, e.g. a drv_pvv-only backfill loop)
    just reads whatever outlook is *currently* stored in drv_rr for that
    date — fine as long as it runs after a full cascade has already filled
    it in. Either way, a BB gradation (e.g. 'Light Bullish') is normalized
    by _normalize_outlook() the same way (see docs/pvv_logic.md §4)."""
    if not symbols:
        return {}
    rows = session.execute(text("""
        SELECT tos_symbol, outlook, source
        FROM drv_rr
        WHERE as_of_date = :d AND tos_symbol = ANY(:syms)
    """), {"d": d, "syms": symbols}).fetchall()
    return {sym: (outlook, source) for sym, outlook, source in rows}


def _fetch_technicals(session: Session, d: date) -> dict:
    rows = session.execute(text("""
        SELECT tos_symbol, last_price, imp_volatility, vlm_projected,
               iv_percentile, hv_percentile, sma_50, sma_200, a_trend_value
        FROM drv_technicals
        WHERE as_of_date = :d
    """), {"d": d}).mappings().all()
    return {r["tos_symbol"]: dict(r) for r in rows}


def _today_rocs(td_series: list, tl_series: list, tech: dict, as_of_date: date) -> Optional[dict]:
    """Raw (unclassified) ROC values for the 'today' bucket, or None if there
    isn't enough history yet.

    Two cases, detected by whether td_series[-1] is D's own settled row --
    D is *defined* as MAX(export_date) FROM hist_td, so once today's TOSD
    (EOD) file has loaded there IS always a TD row for D itself (2026-08-15
    fix: the old code assumed the opposite -- "there is no TD row for today
    itself" -- which was true only before that load landed):

      - **Still intraday** (D's TOSD row hasn't loaded yet, so td_series[-1]
        is genuinely yesterday's settled close): compare the live current
        price/IV (`tech`, which can carry a same-day intraday quote once one
        exists -- same baseline as drv_quote.pct_change on the Actionable
        grid) against that settled close. This is the normal case while
        actively trading, and is unchanged by this fix.
      - **After D's close has loaded**: there's no fresher price/IV left
        to compare against -- `tech`'s values resolve to that same settled
        close, so comparing it to itself always produced a false 0% ROC
        (not "flat trading", a same-value-vs-itself artifact — this was
        the actual 0/0 the user found on META and most other symbols).
        Fixed by shifting the whole window back one day: compare D's
        settled close/IV to D-1's, a real day-over-day change, instead.

    The day-before-the-reference row ([-2], or [-3] once shifted) is used
    only as the fallback HV comparison point (no live HV feed exists, so
    that leg always compares two settled daily readings, live-price case
    or not -- unaffected by which case above we're in).
    """
    if len(td_series) < 2:
        return None

    settled_today = td_series[-1][0] == as_of_date
    if settled_today:
        if len(td_series) < 3:
            return None
        d_prior, price_prior, hv_prior1, iv_prior1 = td_series[-2]
        _dp2, _lp2, hv_prior2, iv_prior2 = td_series[-3]
        _d_cur, cur_price, _hv_cur, cur_iv = td_series[-1]
    else:
        d_prior, price_prior, hv_prior1, iv_prior1 = td_series[-1]
        _dp2, _lp2, hv_prior2, iv_prior2 = td_series[-2]
        cur_price = tech.get("last_price")
        cur_iv = tech.get("imp_volatility")

    p_roc = _roc(cur_price, price_prior)

    vlm_today = tech.get("vlm_projected")
    vols = [v for (dd, v) in tl_series if dd < d_prior and v is not None]
    window = vols[-PVV_CONFIG["eod_vol_avg_n"]:]
    avg_vol = statistics.fmean(window) if len(window) >= PVV_CONFIG["min_window_pts"] else None
    v_roc = _roc(vlm_today, avg_vol)

    prior_iv, vol_src = iv_prior1, "iv"
    if cur_iv is None or prior_iv is None:
        cur_iv, prior_iv, vol_src = hv_prior1, hv_prior2, "hv"
    vol_roc = _roc(cur_iv, prior_iv)

    return {"p_roc": p_roc, "v_roc": v_roc, "vol_roc": vol_roc, "vol_src": vol_src}


def _horizon_rocs(horizon: int, td_series: list, tl_series: list, tech: dict) -> Optional[dict]:
    """Raw (unclassified) ROC values for a 5d/3w bucket, or None if there
    isn't enough daily TD history for this horizon."""
    if len(td_series) <= horizon:
        return None
    d_cur, price_cur, hv_cur, iv_cur = td_series[-1]
    d_prev, price_prev, hv_prev, iv_prev = td_series[-1 - horizon]

    p_roc = _roc(price_cur, price_prev)

    vol_cur = _series_value_near(tl_series, d_cur)
    vol_prev = _series_value_near(tl_series, d_prev)
    v_roc = _roc(vol_cur, vol_prev)

    vol_src = "iv"
    cur_iv, prev_iv = iv_cur, iv_prev
    if cur_iv is None or prev_iv is None:
        cur_iv, prev_iv, vol_src = hv_cur, hv_prev, "hv"
    vol_roc = _roc(cur_iv, prev_iv)

    return {"p_roc": p_roc, "v_roc": v_roc, "vol_roc": vol_roc, "vol_src": vol_src}


def _resolve_bucket(rocs: Optional[dict], band_k: float,
                    price_sigma: Optional[float], vol_sigma: Optional[float],
                    volat_sigma: Optional[float]) -> tuple:
    """Turn raw ROC values + resolved sigmas into a (sig, detail) pair."""
    if rocs is None:
        return "NA", {"sig": "NA"}
    p_roc, v_roc, vol_roc = rocs["p_roc"], rocs["v_roc"], rocs["vol_roc"]
    p_dir = _direction(p_roc, price_sigma, band_k)
    v_dir = _direction(v_roc, vol_sigma, band_k)
    vol_dir = _direction(vol_roc, volat_sigma, band_k)
    sig = classify_pvv(p_dir, v_dir, vol_dir)
    detail = {
        "sig": sig, "p_roc": _round(p_roc), "v_roc": _round(v_roc), "vol_roc": _round(vol_roc),
        "p_dir": p_dir, "v_dir": v_dir, "vol_dir": vol_dir, "vol_src": rocs["vol_src"],
    }
    return sig, detail


def _bucket_3m(tech: dict) -> tuple:
    last_price = tech.get("last_price")
    sma_50 = tech.get("sma_50")
    sma_200 = tech.get("sma_200")
    iv_pctile = tech.get("iv_percentile")
    vol_src = "iv"
    if iv_pctile is None:
        iv_pctile, vol_src = tech.get("hv_percentile"), "hv"

    p_dir = None
    price_vs_sma50 = None
    sma50_vs_sma200 = None
    if last_price is not None and sma_50 not in (None, 0) and sma_200 not in (None, 0):
        try:
            lp, s50, s200 = float(last_price), float(sma_50), float(sma_200)
            price_vs_sma50 = lp / s50 if s50 else None
            sma50_vs_sma200 = s50 / s200 if s200 else None
            if lp > s50 and s50 > s200:
                p_dir = "up"
            elif lp < s50 and s50 < s200:
                p_dir = "down"
            else:
                p_dir = "flat"
        except (TypeError, ValueError):
            p_dir = None

    vol_dir = None
    if iv_pctile is not None:
        try:
            ivp = float(iv_pctile)
            if ivp >= PVV_CONFIG["iv_pctile_hi"]:
                vol_dir = "up"
            elif ivp <= PVV_CONFIG["iv_pctile_lo"]:
                vol_dir = "down"
            else:
                vol_dir = "flat"
        except (TypeError, ValueError):
            vol_dir = None

    sig = classify_pvv_3m(p_dir, vol_dir)
    detail = {
        "sig": sig,
        "price_vs_sma50": _round(price_vs_sma50),
        "sma50_vs_sma200": _round(sma50_vs_sma200),
        "iv_pctile": _round(iv_pctile, 1),
        "vol_src": vol_src,
    }
    return sig, detail


def _derive_pvv_impl(session: Session, as_of_date: date, run_id: int) -> int:
    cfg = PVV_CONFIG
    universe = [r[0] for r in session.execute(
        text("SELECT tos_symbol FROM drv_symbols WHERE as_of_date = :d"),
        {"d": as_of_date},
    ).fetchall()]
    if not universe:
        return replace_for_date(session, "drv_pvv", "as_of_date", as_of_date, [])

    start = as_of_date - timedelta(days=cfg["history_days"])
    td_by_sym = _fetch_daily_td_series(session, universe, start, as_of_date)
    tl_by_sym = _fetch_daily_tl_volume(session, universe, start, as_of_date)
    tech_by_sym = _fetch_technicals(session, as_of_date)
    rr_by_sym = _fetch_rr_outlook(session, universe, as_of_date)

    # ---- pass 1: raw ROCs (today/5d/3w) + own-symbol trailing sigma per bucket ----
    _prelim: dict = {}
    for sym in universe:
        td = td_by_sym.get(sym, [])
        tl = tl_by_sym.get(sym, [])
        tech = tech_by_sym.get(sym, {})
        prices = [r[1] for r in td]
        # imp_volatility with historical_vol fallback per-point (§2 IV null fallback)
        vola = [(r[3] if r[3] is not None else r[2]) for r in td]
        vols_only = [v for (_d, v) in tl]

        def _own(horizon):
            return (
                _trailing_sigma(prices, horizon, cfg["sigma_min_obs"], cfg["sigma_window"]),
                _trailing_sigma(vols_only, horizon, cfg["sigma_min_obs"], cfg["sigma_window"]),
                _trailing_sigma(vola, horizon, cfg["sigma_min_obs"], cfg["sigma_window"]),
            )

        _prelim[sym] = {
            "td": td, "tl": tl, "tech": tech,
            "rocs_today": _today_rocs(td, tl, tech, as_of_date),
            "rocs_5d": _horizon_rocs(5, td, tl, tech),
            "rocs_3w": _horizon_rocs(15, td, tl, tech),
            "own_sigma_today": _own(1),
            "own_sigma_5d": _own(5),
            "own_sigma_3w": _own(15),
        }

    # ---- cross-sectional fallback sigma: pstdev of the raw ROC values across
    # the universe for a bucket/leg, used only when a symbol's own trailing
    # sigma is unavailable (§2 fallback chain). ----
    def _cross_sigma(bucket_key: str, leg: str) -> Optional[float]:
        vals = [p[bucket_key][leg] for p in _prelim.values()
                if p[bucket_key] is not None and p[bucket_key][leg] is not None]
        if len(vals) < 2:
            return None
        try:
            return statistics.pstdev(vals)
        except statistics.StatisticsError:
            return None

    cross = {
        "today": tuple(_cross_sigma("rocs_today", leg) for leg in ("p_roc", "v_roc", "vol_roc")),
        "5d":    tuple(_cross_sigma("rocs_5d", leg) for leg in ("p_roc", "v_roc", "vol_roc")),
        "3w":    tuple(_cross_sigma("rocs_3w", leg) for leg in ("p_roc", "v_roc", "vol_roc")),
    }

    # ---- pass 2: resolve direction/signal per bucket, own-sigma else cross ----
    out_rows = []
    for sym in universe:
        p = _prelim[sym]
        tech = p["tech"]

        def _sigmas(own_key, cross_key):
            own = p[own_key]
            fb = cross[cross_key]
            return tuple(own[i] if own[i] is not None else fb[i] for i in range(3))

        p1, v1, vol1 = _sigmas("own_sigma_today", "today")
        p5, v5, vol5 = _sigmas("own_sigma_5d", "5d")
        p15, v15, vol15 = _sigmas("own_sigma_3w", "3w")

        sig_today, det_today = _resolve_bucket(p["rocs_today"], cfg["flat_band_today"], p1, v1, vol1)
        sig_5d, det_5d = _resolve_bucket(p["rocs_5d"], cfg["flat_band_5d"], p5, v5, vol5)
        sig_3w_raw, det_3w = _resolve_bucket(p["rocs_3w"], cfg["flat_band_3w"], p15, v15, vol15)

        sig_3w, gated = _apply_3w_gate(
            sig_3w_raw, tech.get("last_price"), tech.get("a_trend_value"))
        det_3w["gated"] = gated
        if gated:
            det_3w["sig"] = sig_3w

        sig_3m, det_3m = _bucket_3m(tech)

        outlook_raw, rr_source = rr_by_sym.get(sym, (None, None))
        decision = decide_pvv(sig_today, outlook_raw)
        outlook_detail = {"value": _normalize_outlook(outlook_raw), "source": rr_source}

        out_rows.append({
            "as_of_date": as_of_date,
            "tos_symbol": sym,
            "sig_today": sig_today,
            "sig_5d": sig_5d,
            "sig_3w": sig_3w,
            "sig_3m": sig_3m,
            "decision": decision,
            "detail": {"today": det_today, "d5": det_5d, "w3": det_3w, "m3": det_3m,
                       "outlook": outlook_detail},
        })

    return replace_for_date(session, "drv_pvv", "as_of_date", as_of_date, out_rows)


derive_pvv = _wrap("drv_pvv", _derive_pvv_impl)
