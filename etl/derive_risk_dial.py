"""
etl/derive_risk_dial.py — TASK_133 Phase 3.5: the Risk Dial.

Turns market context into a single 0-100 "how much size should I use today"
number. Called by etl/derive_market_stat.py (which has already computed
vrp/breadth/participation for the same as_of_date and passes them in via
`extra_ctx`) — this module does NOT write to the DB itself; it returns
(gauges_fired: list[dict], summary: dict) for the caller to persist into
drv_market_stat.gauges_fired / risk_budget / risk_label.

Each Gauge is a (key, predicate) pair. predicate(ctx) -> bool | None:
    True  -> fired (risk-off condition present)
    False -> quiet (evaluated, did not fire)
    None  -> cannot evaluate (data missing) -- excluded from BOTH the
             numerator and denominator of risk_budget, never counted as
             passing (spec: "a None gauge is excluded ... never counted as
             passing").

risk_budget = round(100 * (1 - fired_weight / evaluable_weight))
  80-100 CLEAR | 55-79 CAUTION | 30-54 DEFENSIVE | 0-29 NOT INVESTABLE

Weights/active-flags come from ref_risk_gauge (a tuning surface); the
predicate logic itself lives here, per the table's own comment.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Callable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from api._helpers import rr_pos

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds not covered by ref_vol_threshold / ref_level_watch (spec Phase
# 3.5 table). These are gauge PREDICATE logic, not tuning knobs -- per
# ref_risk_gauge's own header comment, weight/active live in the DB table,
# the condition itself lives here.
# ---------------------------------------------------------------------------
CREDIT_WIDEN_BP = 25.0     # BAMLH0A0HYM2 widened >= this over CREDIT_WIDEN_DAYS
CREDIT_WIDEN_DAYS = 10
CURVE_INVERT_BP = 15.0     # T10Y2Y fell >= this over CURVE_INVERT_DAYS
CURVE_INVERT_DAYS = 5


def _normalize_tnx(last: Optional[float]) -> Optional[float]:
    """TNX:CGI's drv_quote is inconsistently scaled day to day (TL/TD source:
    x10 index-level ~45-47; 'Y' source: plain percent ~4.5-4.7 -- see
    api/_helpers.py::rr_pos docstring / DEV_HANDOFF.md for the live-DB
    evidence). ref_level_watch's TNX:CGI rows are seeded on the x10 scale
    (predominant scale) so this normalizes any percent-scale reading up
    before comparing against them."""
    if last is None:
        return None
    last = float(last)
    return last * 10 if last < 15 else last


# ---------------------------------------------------------------------------
# Context builder — one round-trip per source table, reused across gauges.
# ---------------------------------------------------------------------------

_RR_SYMS = ["SPX", "HYG", "TNX:CGI", "$DXY", "/CL"]
_QUOTE_SYMS = ["SPX", "HYG", "TNX:CGI", "$DXY", "/CL", "VIX", "MOVE:GIF",
               "GVZ:CGI", "OVX:CGI"]


def build_context(session: Session, as_of_date: date, extra: dict) -> dict:
    """extra: {'vrp': float|None, 'pct_above_sma50': float|None,
    'pct_above_sma50_5d_chg': float|None} -- computed by derive_market_stat.py
    in the same run, passed straight through."""
    rr_rows = session.execute(text(
        "SELECT tos_symbol, lrr, trr, outlook FROM drv_rr "
        "WHERE as_of_date = :d AND tos_symbol = ANY(:syms)"
    ), {"d": as_of_date, "syms": _RR_SYMS}).mappings().all()
    rr_map = {r["tos_symbol"]: {"lrr": float(r["lrr"]) if r["lrr"] is not None else None,
                                 "trr": float(r["trr"]) if r["trr"] is not None else None,
                                 "outlook": r["outlook"]} for r in rr_rows}

    q_rows = session.execute(text(
        "SELECT tos_symbol, last_price, pct_change FROM drv_quote "
        "WHERE as_of_date = :d AND tos_symbol = ANY(:syms)"
    ), {"d": as_of_date, "syms": _QUOTE_SYMS}).mappings().all()
    quote_map = {r["tos_symbol"]: float(r["last_price"])
                 for r in q_rows if r["last_price"] is not None}
    # 2026-08-14 -- day's own %change per symbol, feeds _g_vix_spx_divergence
    # below (needs VIX's/SPX's OWN daily move, not just their level).
    quote_chg_map = {r["tos_symbol"]: float(r["pct_change"])
                      for r in q_rows if r["pct_change"] is not None}

    vol_rows = session.execute(text(
        "SELECT tos_symbol, low, high FROM ref_vol_threshold"
    )).mappings().all()
    vol_map = {r["tos_symbol"]: {"low": float(r["low"]), "high": float(r["high"])}
               for r in vol_rows}

    level_rows = session.execute(text(
        "SELECT tos_symbol, level_value, tolerance FROM ref_level_watch "
        "WHERE is_active"
    )).mappings().all()
    levels_by_sym: dict[str, list] = {}
    for r in level_rows:
        levels_by_sym.setdefault(r["tos_symbol"], []).append(
            (float(r["level_value"]), float(r["tolerance"])))

    gamma_row = session.execute(text(
        "SELECT gamma_throttle, rvol_10day FROM hist_msr WHERE snapshot_date <= :d "
        "ORDER BY snapshot_date DESC LIMIT 1"
    ), {"d": as_of_date}).first()
    gamma_throttle = float(gamma_row[0]) if gamma_row and gamma_row[0] is not None else None
    rvol_10day = float(gamma_row[1]) if gamma_row and gamma_row[1] is not None else None

    # 2026-08-14 -- VIX9D (CBOE 9-day/short-dated implied vol), feeds
    # _g_short_vol_disc below. etl/fetch_vix9d.py (yfinance, symbol
    # '^VIX9D') writes here, separate from ref_corr_asset (that table also
    # drives the Dollar Correlation panel; VIX9D isn't a USD-correlation
    # asset). User: "Short dated volatility calendar... close to 10 and
    # Imp vol disc is -ve" -> "use it" -- VIX9D vs rvol_10day is the
    # standardized, independently-verifiable version of that MSR chart
    # reading (vs OCR'ing Hedgeye's own proprietary number).
    vix9d_row = session.execute(text(
        "SELECT close FROM hist_quote_daily WHERE source = 'yfinance' AND symbol = '^VIX9D' "
        "AND obs_date <= :d ORDER BY obs_date DESC LIMIT 1"
    ), {"d": as_of_date}).first()
    vix9d = float(vix9d_row[0]) if vix9d_row and vix9d_row[0] is not None else None

    def _macro_series(series_id: str, lookback_days: int) -> Optional[list]:
        rows = session.execute(text(
            "SELECT obs_date, value FROM hist_macro WHERE series_id = :sid "
            "AND obs_date <= :d ORDER BY obs_date DESC LIMIT :n"
        ), {"sid": series_id, "d": as_of_date, "n": lookback_days + 2}).all()
        return [(r[0], float(r[1])) for r in rows if r[1] is not None]

    return {
        "rr": rr_map,
        "quote": quote_map,
        "quote_chg": quote_chg_map,
        "vol": vol_map,
        "levels": levels_by_sym,
        "gamma_throttle": gamma_throttle,
        "rvol_10day": rvol_10day,
        "vix9d": vix9d,
        "hy_oas": _macro_series("BAMLH0A0HYM2", CREDIT_WIDEN_DAYS),
        "t10y2y": _macro_series("T10Y2Y", CURVE_INVERT_DAYS),
        "vrp": extra.get("vrp"),
        "pct_above_sma50": extra.get("pct_above_sma50"),
        "pct_above_sma50_5d_chg": extra.get("pct_above_sma50_5d_chg"),
    }


def _rr_pos_sym(ctx: dict, sym: str) -> Optional[float]:
    rr = ctx["rr"].get(sym)
    last = ctx["quote"].get(sym)
    if not rr or last is None:
        return None
    return rr_pos(last, rr.get("lrr"), rr.get("trr"))


def _vol_value(ctx: dict, sym: str) -> Optional[float]:
    return ctx["quote"].get(sym)


def _series_delta(series: Optional[list], days: int) -> Optional[tuple]:
    """(latest_value, delta_over_n_trading_days) from a DESC-ordered
    [(date, value), ...] list, or None if not enough history."""
    if not series or len(series) <= days:
        return None
    latest = series[0][1]
    past = series[days][1]
    return latest, latest - past


def _leg_detail(legs: list, fired: bool) -> str:
    """TASK_134 B.1 -- shared leg-selection logic for multi-leg gauges.

    `legs` is a list of (leg_fired: bool, margin: float, text: str), given in
    the gauge's own leg-definition order (its "most decisive"/primary-signal
    order -- e.g. WTI before its OVX confirmation, HYG before the HY OAS
    confirmation). `margin` is <= 0 once a leg has fired, > 0 while quiet
    (smaller = nearer to firing) -- used only to rank quiet legs.

    When the gauge fired overall, returns only the legs that themselves
    fired, in that definition order -- never mentions a leg that did not
    fire alongside one that did (this was the reported bug: "WTI 39% of
    range; OVX 63" leading with the non-triggering leg). When the gauge did
    not fire, returns only the single nearest-to-firing leg.
    """
    if not legs:
        return "no data"
    if fired:
        firing = [t for f, _m, t in legs if f]
        return "; ".join(firing) or "no data"
    quiet = sorted(((m, t) for f, m, t in legs if not f), key=lambda x: x[0])
    return quiet[0][1] if quiet else "no data"


# ---------------------------------------------------------------------------
# Gauges — (key, fn(ctx) -> (fired: bool|None, value: float|None, detail: str))
# ---------------------------------------------------------------------------

def _spx_range_detail(ctx: dict, v: float) -> str:
    """Detail-string builder for _g_spx_top_range below -- adds upside-to-TRR
    / downside-to-LRR round-trip percentages (both relative to the current
    price, not the range width) alongside the existing %-of-range/LRR/TRR
    text. Also consumed directly by the Dashboard's Risk Dial UI, which reads
    this gauge's `value` (0..1 position within LRR/TRR) every day -- fired or
    not -- to draw an always-visible vertical range indicator (2026-08-14
    follow-up: text line replaced by the bar; gauge itself fires only at
    >=85%, per user: "Only fire the gauge if above 85%")."""
    last = ctx["quote"].get("SPX")
    rr = ctx["rr"].get("SPX", {})
    lrr, trr = rr.get("lrr"), rr.get("trr")
    base = f"SPX {last:.0f} — {v*100:.0f}% of range (LRR {lrr} / TRR {trr})"
    if last and lrr is not None and trr is not None:
        upside_pct = (float(trr) - last) / last * 100.0
        downside_pct = (last - float(lrr)) / last * 100.0
        base += f" · +{upside_pct:.1f}% to TRR / -{downside_pct:.1f}% to LRR"
    return base


def _g_spx_top_range(ctx):
    v = _rr_pos_sym(ctx, "SPX")
    if v is None:
        return None, None, "SPX risk range unavailable"
    return v >= 0.85, v, _spx_range_detail(ctx, v)


def _g_spx_bottom_range(ctx):
    v = _rr_pos_sym(ctx, "SPX")
    if v is None:
        return None, None, "SPX risk range unavailable"
    return v <= 0.15, v, f"SPX {v*100:.0f}% of range"


# 2026-08-14 -- VIX and SPX normally move inversely (~-70 to -80%
# correlation historically); when that breaks down on a big up-day --
# VIX green (any positive tick) WHILE SPX rallies >=1.5% -- it's often
# read as dealers/hedgers buying protection INTO the rally rather than
# believing it, a real divergence signal rather than noise. User: "if VIX
# is green and SPY is up massively => Get out of the market" -- thresholds
# (SPX >=1.5%, VIX simply >0) confirmed with the user; SPX chosen over SPY
# to match every other equity gauge already in this file.
def _g_vix_spx_divergence(ctx):
    vix_chg = ctx["quote_chg"].get("VIX")
    spx_chg = ctx["quote_chg"].get("SPX")
    if vix_chg is None or spx_chg is None:
        return None, None, "VIX or SPX %change unavailable"
    fired = vix_chg > 0 and spx_chg >= 1.5
    # 2026-08-14 BUGFIX -- "(inverse relationship broken)" was hardcoded
    # onto the detail string unconditionally, so a normal/quiet day (e.g.
    # SPX -0.2% with VIX -2.7%, the expected inverse move) still claimed
    # the relationship was "broken" -- only true when fired.
    tag = "inverse relationship broken" if fired else "normal inverse move"
    return fired, spx_chg, f"SPX {spx_chg:+.1f}% with VIX {vix_chg:+.1f}% ({tag})"


def _g_vix_elevated(ctx):
    v = _vol_value(ctx, "VIX")
    th = ctx["vol"].get("VIX")
    if v is None or th is None:
        return None, v, "VIX unavailable"
    return v > th["high"], v, f"VIX {v:.1f} vs elevated>{th['high']:.0f}"


def _g_vix_chop(ctx):
    v = _vol_value(ctx, "VIX")
    th = ctx["vol"].get("VIX")
    if v is None or th is None:
        return None, v, "VIX unavailable"
    return th["low"] <= v <= th["high"], v, f"VIX {v:.1f} in chop {th['low']:.0f}-{th['high']:.0f}"


def _g_move_elevated(ctx):
    v = _vol_value(ctx, "MOVE:GIF")
    th = ctx["vol"].get("MOVE:GIF")
    if v is None or th is None:
        return None, v, "MOVE unavailable"
    return v > th["high"], v, f"MOVE {v:.0f} vs elevated>{th['high']:.0f}"


# 2026-08-14 -- MOVE's own "chop zone" companion, mirroring _g_vix_chop
# above -- ref_vol_threshold's MOVE:GIF low (100) was already seeded but
# unused by any gauge until now. User: "What do you consider as high risk
# when bond volatility moves higher..." -> discussed move_elevated's
# existing >120 threshold -> "yes" (add this, leave move_elevated as-is).
def _g_move_chop(ctx):
    v = _vol_value(ctx, "MOVE:GIF")
    th = ctx["vol"].get("MOVE:GIF")
    if v is None or th is None:
        return None, v, "MOVE unavailable"
    return th["low"] <= v <= th["high"], v, f"MOVE {v:.0f} in chop {th['low']:.0f}-{th['high']:.0f}"


def _g_credit_stress(ctx):
    v = _rr_pos_sym(ctx, "HYG")
    hy_widen = _series_delta(ctx.get("hy_oas"), CREDIT_WIDEN_DAYS)
    widened = hy_widen is not None and hy_widen[1] * 100 >= CREDIT_WIDEN_BP
    if v is None and hy_widen is None:
        return None, None, "HYG range and HY OAS unavailable"
    hyg_fired = v is not None and v <= 0.15
    fired = hyg_fired or widened
    legs = []
    if v is not None:
        legs.append((hyg_fired, (v - 0.15) / 0.15, f"HYG {v*100:.0f}% of range"))
    if hy_widen is not None:
        legs.append((widened, (CREDIT_WIDEN_BP - hy_widen[1] * 100) / CREDIT_WIDEN_BP,
                     f"HY OAS {hy_widen[0]:.2f}% ({hy_widen[1]*100:+.0f}bp/{CREDIT_WIDEN_DAYS}d)"))
    return fired, v, _leg_detail(legs, fired)


def _g_yield_level_watch(ctx):
    raw = ctx["quote"].get("TNX:CGI")
    tnx = _normalize_tnx(raw)
    v = _rr_pos_sym(ctx, "TNX:CGI")
    levels = ctx["levels"].get("TNX:CGI", [])
    near_level = None
    if tnx is not None:
        for lvl, tol in levels:
            if abs(tnx - lvl) <= tol:
                near_level = lvl
                break
    if tnx is None and v is None:
        return None, None, "10Y yield unavailable"
    level_fired = near_level is not None
    range_fired = v is not None and v >= 0.85
    fired = level_fired or range_fired
    legs = []
    if tnx is not None and (level_fired or levels):
        if level_fired:
            legs.append((True, -1.0,
                         f"10Y {tnx/10:.2f}% — within tolerance of {near_level/10:.2f}% watch level"))
        else:
            lvl, tol = min(levels, key=lambda lt: abs(tnx - lt[0]) / lt[1] if lt[1] else float("inf"))
            margin = ((abs(tnx - lvl) - tol) / tol) if tol else 0.0
            legs.append((False, margin, f"10Y {tnx/10:.2f}% (nearest watch level {lvl/10:.2f}%)"))
    if v is not None:
        prefix = f"10Y {tnx/10:.2f}% — " if tnx is not None else ""
        legs.append((range_fired, (0.85 - v) / 0.85, f"{prefix}{v*100:.0f}% of risk range"))
    if not legs:
        legs.append((False, 0.0, f"10Y {tnx/10:.2f}%" if tnx is not None else "10Y n/a"))
    return fired, v if v is not None else tnx, _leg_detail(legs, fired)


def _g_curve_inverting(ctx):
    d = _series_delta(ctx.get("t10y2y"), CURVE_INVERT_DAYS)
    if d is None:
        return None, None, "2s10s history unavailable"
    latest, delta = d
    fired = (delta * 100) <= -CURVE_INVERT_BP
    return fired, latest, f"2s10s {latest*100:.0f}bp ({delta*100:+.0f}bp/{CURVE_INVERT_DAYS}d)"


def _g_dollar_strong(ctx):
    v = _rr_pos_sym(ctx, "$DXY")
    if v is None:
        return None, None, "DXY range unavailable"
    return v >= 0.85, v, f"DXY {v*100:.0f}% of range"


def _g_oil_shock(ctx):
    v = _rr_pos_sym(ctx, "/CL")
    ovx = _vol_value(ctx, "OVX:CGI")
    ovx_th = ctx["vol"].get("OVX:CGI")
    ovx_elevated = ovx is not None and ovx_th is not None and ovx > ovx_th["high"]
    if v is None and ovx is None:
        return None, None, "WTI range and OVX unavailable"
    wti_fired = v is not None and (v >= 0.85 or v <= 0.15)
    fired = wti_fired or ovx_elevated
    legs = []
    if v is not None:
        # distance to whichever edge of the range is nearer -- <=0 once fired.
        margin = (0.85 - v) if v >= 0.5 else (v - 0.15)
        legs.append((wti_fired, margin / 0.85, f"WTI {v*100:.0f}% of range"))
    if ovx is not None:
        ovx_text = (f"OVX {ovx:.0f} — above elevated ({ovx_th['high']:.0f})"
                    if ovx_elevated and ovx_th else f"OVX {ovx:.0f}")
        margin = ((ovx_th["high"] - ovx) / ovx_th["high"]) if ovx_th else 0.0
        legs.append((ovx_elevated, margin, ovx_text))
    return fired, v, _leg_detail(legs, fired)


def _g_vrp_gone(ctx):
    v = ctx.get("vrp")
    if v is None:
        return None, None, "VRP unavailable (needs rv21 backfill)"
    return v <= 0, v, f"VRP {v:+.1f} (VIX - RV21)"


# 2026-08-14 -- short-dated companion to _g_vrp_gone above -- same "implied
# vol discount gone negative" shape (VIX - RV21 <= 0), but VIX9D (CBOE
# 9-day/short-dated implied vol, etl/fetch_vix9d.py) vs rvol_10day (MSR's
# own 10-day realized vol) instead of the standard 30-day VIX vs 21-day
# realized. The short end of the vol curve moves first -- this can fire
# (and did, live: VIX9D 10.96 vs rvol_10day) before vrp_gone does on the
# same underlying dynamic. User: "Short dated volatility calendar -> close
# to 10 and Imp vol disc is -ve. Should not buy stocks" -> confirmed
# "Imp vol disc is implied vol vs hist vol" -> "use it" (VIX9D, not OCR).
def _g_short_vol_disc(ctx):
    vix9d, rv10 = ctx.get("vix9d"), ctx.get("rvol_10day")
    if vix9d is None or rv10 is None:
        return None, None, "VIX9D or rvol_10day unavailable"
    disc = vix9d - rv10
    return disc <= 0, disc, f"Short vol disc {disc:+.1f} (VIX9D {vix9d:.1f} - RV10 {rv10:.1f})"


# 2026-08-14 -- separate, absolute-level companion to _g_short_vol_disc
# above -- that one is RELATIVE (VIX9D vs realized vol); this one is
# VIX9D's own level against its typical 10-30 range, low end only. User:
# "Typically ranges from 10 to 30. 10 - sell stocks. 30 - buy stocks" --
# only the low/bearish end fires here (Risk Dial gauges only ever fire on
# caution/reduce-budget conditions; there's no mechanism for a fired gauge
# to signal "buy" the way the 30-end would need to -- discussed and user
# confirmed: "Low end only, as a Risk Dial gauge"). 12 (not a literal 10)
# as the cutoff -- a small buffer catching "near the low end" per the
# user's own "close to 10" framing of the live reading that prompted this,
# rather than requiring VIX9D to touch the exact floor.
def _g_short_vol_low(ctx):
    v = ctx.get("vix9d")
    if v is None:
        return None, None, "VIX9D unavailable"
    return v <= 12, v, f"VIX9D {v:.1f} (low end of its typical 10-30 range)"


def _g_gamma_negative(ctx):
    v = ctx.get("gamma_throttle")
    if v is None:
        return None, None, "gamma_throttle unavailable"
    return v < 0, v, f"Dealer gamma throttle {v:+.2f}"


def _g_breadth_deteriorating(ctx):
    pct = ctx.get("pct_above_sma50")
    chg = ctx.get("pct_above_sma50_5d_chg")
    if pct is None or chg is None:
        return None, pct, "breadth unavailable"
    return (pct < 40 and chg < 0), pct, f"{pct:.0f}% above 50-DMA ({chg:+.0f}pp/5d)"


def _g_gold_vol_elevated(ctx):
    v = _vol_value(ctx, "GVZ:CGI")
    th = ctx["vol"].get("GVZ:CGI")
    if v is None or th is None:
        return None, v, "GVZ unavailable"
    return v > th["high"], v, f"GVZ {v:.0f} vs elevated>{th['high']:.0f}"


def _g_volume_breadth_weak(ctx):
    """Phase 4.1 -- NULL/None until hist_internals ($UVOL/$DVOL) is flowing.
    Seeded is_active=FALSE in ref_risk_gauge until then."""
    vb = ctx.get("vol_breadth")
    if vb is None:
        return None, None, "hist_internals not yet flowing"
    return vb < 0.35, vb, f"up/down volume breadth {vb:.2f}"


GAUGES: list[tuple[str, Callable]] = [
    ("spx_top_range", _g_spx_top_range),
    ("spx_bottom_range", _g_spx_bottom_range),
    ("vix_spx_divergence", _g_vix_spx_divergence),
    ("vix_elevated", _g_vix_elevated),
    ("vix_chop", _g_vix_chop),
    ("move_elevated", _g_move_elevated),
    ("move_chop", _g_move_chop),
    ("credit_stress", _g_credit_stress),
    ("yield_level_watch", _g_yield_level_watch),
    ("curve_inverting", _g_curve_inverting),
    ("dollar_strong", _g_dollar_strong),
    ("oil_shock", _g_oil_shock),
    ("vrp_gone", _g_vrp_gone),
    ("short_vol_disc", _g_short_vol_disc),
    ("short_vol_low", _g_short_vol_low),
    ("gamma_negative", _g_gamma_negative),
    ("breadth_deteriorating", _g_breadth_deteriorating),
    ("gold_vol_elevated", _g_gold_vol_elevated),
    ("volume_breadth_weak", _g_volume_breadth_weak),
]


def _risk_label(budget: Optional[int]) -> Optional[str]:
    if budget is None:
        return None
    if budget >= 80:
        return "CLEAR"
    if budget >= 55:
        return "CAUTION"
    if budget >= 30:
        return "DEFENSIVE"
    return "NOT INVESTABLE"


def compute_budget(gauges_fired: list[dict]) -> dict:
    """Pure weight-arithmetic step, extracted from evaluate_gauges() so it's
    unit-testable without a DB session (tests/test_risk_dial.py).

    fired=None gauges (data missing, can't evaluate) are excluded from BOTH
    the numerator and the denominator -- never counted as passing (spec 3.5).
    """
    fired_weight = 0.0
    evaluable_weight = 0.0
    for g in gauges_fired:
        if g.get("fired") is None:
            continue
        weight = float(g.get("weight") or 0)
        evaluable_weight += weight
        if g["fired"]:
            fired_weight += weight
    risk_budget = (round(100 * (1 - fired_weight / evaluable_weight))
                   if evaluable_weight > 0 else None)
    return {
        "risk_budget": risk_budget,
        "risk_label": _risk_label(risk_budget),
        "fired_weight": fired_weight,
        "evaluable_weight": evaluable_weight,
    }


def evaluate_gauges(session: Session, as_of_date: date, extra_ctx: dict) -> tuple[list, dict]:
    """Returns (gauges_fired: list[dict], summary: dict).

    summary = {risk_budget, risk_label, fired_weight, evaluable_weight}
    """
    gauge_rows = session.execute(text(
        "SELECT gauge_key, label, weight, is_active FROM ref_risk_gauge"
    )).mappings().all()
    reg = {r["gauge_key"]: r for r in gauge_rows}

    ctx = build_context(session, as_of_date, extra_ctx)
    ctx["vol_breadth"] = extra_ctx.get("vol_breadth")

    gauges_fired: list[dict] = []

    for key, fn in GAUGES:
        row = reg.get(key)
        if row is None or not row["is_active"]:
            continue
        try:
            fired, value, detail = fn(ctx)
        except Exception as e:  # a single gauge crashing must not break the dial
            log.exception("risk gauge %s raised: %s", key, e)
            fired, value, detail = None, None, f"error evaluating gauge: {e}"
        weight = float(row["weight"])
        entry = {
            "key": key,
            "label": row["label"],
            "fired": fired,
            "weight": weight,
            "value": value,
            "detail": detail,
        }
        gauges_fired.append(entry)

    summary = compute_budget(gauges_fired)
    return gauges_fired, summary
