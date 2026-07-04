"""
Macro read card endpoint — TASK_78.

GET /api/macro-areas?date=D
  Returns per-area stance roll-up from drv_rr, drv_technicals, drv_quote,
  plus a ranked sectors row and a one-line top-down posture sentence.

All computation is done server-side (keeps stance logic co-located with the
MACRO-column logic, not duplicated in JS).
"""
from __future__ import annotations

import math
import statistics
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from api._helpers import (
    _resolve_date, _get_ref_setting, load_quote_ohlc, load_vol_thresholds,
)
from etl.db import session_scope

router = APIRouter(tags=["macro_areas"])

# GICS 11 standard sector names — canonical display form.
# Comparison is done lower-case so "Health Care" / "Health care" both match.
_GICS_11_LOWER = {
    "communication services",
    "consumer discretionary",
    "consumer staples",
    "energy",
    "financials",
    "health care",
    "healthcare",   # alias for "health care"
    "industrials",
    "information technology",
    "materials",
    "real estate",
    "utilities",
}

# Display-form map (lower -> display)
_GICS_DISPLAY = {
    "communication services": "Communication Services",
    "consumer discretionary": "Consumer Discretionary",
    "consumer staples": "Consumer Staples",
    "energy": "Energy",
    "financials": "Financials",
    "health care": "Health Care",
    "healthcare": "Health Care",
    "industrials": "Industrials",
    "information technology": "Information Technology",
    "materials": "Materials",
    "real estate": "Real Estate",
    "utilities": "Utilities",
}

# SPDR sector ETF proxy per GICS-11 sector — a single-symbol read (price,
# %chg, Trade/Trend direction, Risk Range position) shown alongside the
# breadth score, which averages across every symbol tagged with that sector.
_SECTOR_ETF = {
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Energy":                 "XLE",
    "Financials":              "XLF",
    "Health Care":             "XLV",
    "Industrials":             "XLI",
    "Information Technology": "XLK",
    "Materials":               "XLB",
    "Real Estate":             "XLRE",
    "Utilities":               "XLU",
}

# Canonical ordering for areas — each of these is now its own side-panel
# section (broken out one row per member); frontend routes each area_key to
# its own container based on this same set of keys.
_AREA_ORDER = [
    "volatility", "top9", "rates_duration", "credit", "commodities_credit",
    "usd_currency", "country_etfs", "crypto", "remaining",
]

# Symbols that are yield-curve members — skip rr_pos
_CURVE_SYMS = {"DGS2:FRED", "TNX:CGI", "TYX:CGI"}

# Symbols whose color convention flips vs. plain price direction (HY credit —
# rising spread = risk-off = red), mirroring web/market_bar.js's INVERTED
# set (keyed there by chip short-label 'HY'/'HYSPRD'; keyed here by
# tos_symbol so the frontend consolidation (TASK_116) can read it straight
# off each member instead of keeping its own list).
_INVERTED_SYMBOLS = {"HYG"}


def _sign(x: Optional[float]) -> int:
    if x is None or not math.isfinite(x):
        return 0
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _outlook_sig(outlook: Optional[str]) -> int:
    if not outlook:
        return 0
    ol = outlook.lower()
    if "bull" in ol:
        return 1
    if "bear" in ol:
        return -1
    return 0


def _stance_label(sig: int) -> str:
    if sig > 0:
        return "Long"
    if sig < 0:
        return "Short"
    return "Neutral"


def _safe_median(vals: list[float]) -> Optional[float]:
    clean = [v for v in vals if v is not None and math.isfinite(v)]
    if not clean:
        return None
    return statistics.median(clean)


def _build_top_down(areas: list[dict]) -> str:
    """Generate a one-line posture sentence from the area roll-up."""
    long_count = sum(1 for a in areas if a.get("stance") == "Long")
    short_count = sum(1 for a in areas if a.get("stance") == "Short")
    hot_count = sum(
        1 for a in areas
        if a.get("rr_pos") is not None and a["rr_pos"] >= 0.85
    )
    total = len([a for a in areas if a.get("stance") is not None])
    if total == 0:
        return "Insufficient data for posture read."

    if long_count >= 5 and hot_count >= 3:
        posture = (
            f"Risk-on bias ({long_count}/{total} areas Long) but broadly "
            f"stretched — {hot_count} area(s) above 85% of range. "
            "Harvest extended longs; raise cash."
        )
    elif long_count >= 4:
        posture = (
            f"Risk-on trend intact ({long_count}/{total} areas Long). "
            "Hold positions; watch for stretch signals."
        )
    elif short_count >= 4:
        posture = (
            f"Risk-off ({short_count}/{total} areas Short). "
            "Reduce exposure; favour defensive posture."
        )
    else:
        posture = (
            f"Mixed signals — {long_count} Long, {short_count} Short "
            f"of {total} areas. Selective exposure."
        )
    return posture


@router.get("/api/macro-areas")
def get_macro_areas(date: Optional[str] = Query(None)) -> dict:
    d = _resolve_date(date)

    hot_pct  = float(_get_ref_setting("macro_area_hot_pct",  "0.85"))
    cold_pct = float(_get_ref_setting("macro_area_cold_pct", "0.15"))

    with session_scope() as s:
        # Anchor: MAX(as_of_date) from drv_rr <= d
        anchor_row = s.execute(text(
            "SELECT MAX(as_of_date) FROM drv_rr WHERE as_of_date <= :d"
        ), {"d": d}).first()
        anchor = anchor_row[0] if anchor_row and anchor_row[0] else d

        # Load ref_macro_area members
        members_rows = s.execute(text("""
            SELECT area_key, label, member_symbol, role, sort_order
            FROM ref_macro_area
            WHERE enabled = TRUE
            ORDER BY sort_order
        """)).mappings().all()

        # Load drv_rr for anchor date
        rr_rows = s.execute(text("""
            SELECT tos_symbol, lrr, trr, mrr, outlook
            FROM drv_rr
            WHERE as_of_date = :d
        """), {"d": anchor}).mappings().all()
        rr_map = {r["tos_symbol"]: dict(r) for r in rr_rows}

        # Load drv_technicals for anchor date
        tech_rows = s.execute(text("""
            SELECT tos_symbol, a_trade_value, a_trend_value,
                   sector, asset_class, last_price
            FROM drv_technicals
            WHERE as_of_date = :d
        """), {"d": anchor}).mappings().all()
        tech_map = {r["tos_symbol"]: dict(r) for r in tech_rows}

        # Load drv_quote for last_price
        q_rows = s.execute(text("""
            SELECT tos_symbol, last_price, pct_change
            FROM drv_quote
            WHERE as_of_date = :d
        """), {"d": anchor}).mappings().all()
        q_map = {r["tos_symbol"]: dict(r) for r in q_rows}

        # OHLC (candle) at the same anchor date, and vol thresholds — shared
        # helpers, same source query /api/rr-bar uses (api/_helpers.py
        # ::load_quote_ohlc / load_vol_thresholds), factored out so this
        # router doesn't copy-paste the SQL a third time.
        ohlc_map = load_quote_ohlc(s, anchor)
        vt_map = load_vol_thresholds(s)

        # Load drv_macro_score (Quad-calendar-derived monthly_score) — same
        # source as rrTape's tile glyph (api/routers/marketbar.py::_RR_SQL).
        ms_rows = s.execute(text("""
            SELECT tos_symbol, monthly_score
            FROM drv_macro_score
            WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_macro_score)
        """)).mappings().all()
        ms_map = {r["tos_symbol"]: r["monthly_score"] for r in ms_rows}

        # WoW: quote 5 trading days ago (best effort)
        # Use the 5th-most-recent as_of_date in drv_quote before anchor
        wow_row = s.execute(text("""
            SELECT as_of_date FROM drv_quote
            WHERE as_of_date < :d
            GROUP BY as_of_date
            ORDER BY as_of_date DESC
            LIMIT 1 OFFSET 4
        """), {"d": anchor}).first()
        wow_date = wow_row[0] if wow_row else None
        wow_map: dict = {}
        if wow_date:
            wq = s.execute(text("""
                SELECT tos_symbol, last_price
                FROM drv_quote
                WHERE as_of_date = :d
            """), {"d": wow_date}).mappings().all()
            wow_map = {r["tos_symbol"]: r["last_price"] for r in wq}

        # Sectors roll-up from drv_technicals
        sector_rows = s.execute(text("""
            SELECT tos_symbol, sector,
                   last_price, a_trade_value, a_trend_value
            FROM drv_technicals
            WHERE as_of_date = :d
              AND sector IS NOT NULL
        """), {"d": anchor}).mappings().all()

    # --- Build per-area results ---
    # Group members by area
    from collections import defaultdict
    area_members: dict[str, list] = defaultdict(list)
    area_label: dict[str, str] = {}
    for r in members_rows:
        area_members[r["area_key"]].append(dict(r))
        area_label[r["area_key"]] = r["label"]

    areas_out: list[dict] = []
    for area_key in _AREA_ORDER:
        if area_key not in area_members:
            continue
        members_cfg = area_members[area_key]
        label = area_label.get(area_key, area_key)

        member_details: list[dict] = []
        sigs: list[int] = []
        rr_positions: list[float] = []
        trade_sigs: list[int] = []
        trend_sigs: list[int] = []

        for mc in members_cfg:
            sym = mc["member_symbol"]
            role = mc["role"]

            # last price: prefer drv_quote, fall back to drv_technicals
            last = None
            pct_chg = None
            if sym in q_map:
                last = _maybe_float(q_map[sym].get("last_price"))
                pct_chg = _maybe_float(q_map[sym].get("pct_change"))
            if last is None and sym in tech_map:
                last = _maybe_float(tech_map[sym].get("last_price"))

            rr = rr_map.get(sym, {})
            tech = tech_map.get(sym, {})
            ohlc = ohlc_map.get(sym, {})
            inverted = sym in _INVERTED_SYMBOLS

            # Gauge (VIX): compute zone from ref_vol_threshold
            if role == "gauge":
                vt = vt_map.get(sym, {})
                zone = None
                if last is not None and vt:
                    low = float(vt.get("low") or 0)
                    high = float(vt.get("high") or 0)
                    if last <= low:
                        zone = "investable"
                    elif last <= high:
                        zone = "chop"
                    else:
                        zone = "elevated"
                member_details.append({
                    "symbol": sym,
                    "role": role,
                    "label": mc.get("label"),
                    "last": _maybe_float(last),
                    "pct_change": _maybe_float(pct_chg),
                    "open": ohlc.get("open"),
                    "high": ohlc.get("high"),
                    "low": ohlc.get("low"),
                    "vol_low": vt.get("low"),
                    "vol_high": vt.get("high"),
                    "zone": zone,
                    "outlook": rr.get("outlook"),
                    "monthly_score": _maybe_float(ms_map.get(sym)),
                    "inverted": inverted,
                })
                continue

            # Curve members: use outlook only; skip rr_pos
            if role == "curve":
                ol_sig = _outlook_sig(rr.get("outlook"))
                if ol_sig != 0:
                    sigs.append(ol_sig)
                wow_pct = _wow_pct(last, wow_map.get(sym))
                member_details.append({
                    "symbol": sym,
                    "role": role,
                    "last": _maybe_float(last),
                    "pct_change": _maybe_float(pct_chg),
                    "open": ohlc.get("open"),
                    "high": ohlc.get("high"),
                    "low": ohlc.get("low"),
                    "outlook": rr.get("outlook"),
                    "rr_pos": None,
                    "trade": None,
                    "trend": None,
                    "wow_pct": wow_pct,
                    "monthly_score": _maybe_float(ms_map.get(sym)),
                    "inverted": inverted,
                })
                continue

            # RR position (all non-curve, non-gauge)
            rr_pos = None
            lrr = _maybe_float(rr.get("lrr"))
            trr = _maybe_float(rr.get("trr"))
            if (last is not None and lrr is not None and trr is not None
                    and trr != lrr):
                rr_pos = (last - lrr) / (trr - lrr)

            # Dual: technicals available
            trade_sig = None
            trend_sig = None
            if role == "dual" and tech:
                trade_val = _maybe_float(tech.get("a_trade_value"))
                trend_val = _maybe_float(tech.get("a_trend_value"))
                if last is not None and trade_val is not None:
                    trade_sig = _sign(last - trade_val)
                if last is not None and trend_val is not None:
                    trend_sig = _sign(last - trend_val)

            # Area signal contribution: prefer trade_sig, else outlook
            if role == "dual" and trade_sig is not None:
                sigs.append(trade_sig)
                trade_sigs.append(trade_sig)
                if trend_sig is not None:
                    trend_sigs.append(trend_sig)
            else:
                ol_sig = _outlook_sig(rr.get("outlook"))
                if ol_sig != 0:
                    sigs.append(ol_sig)

            if rr_pos is not None:
                rr_positions.append(rr_pos)

            wow_pct = _wow_pct(last, wow_map.get(sym))
            member_details.append({
                "symbol": sym,
                "role": role,
                "last": _maybe_float(last),
                "pct_change": _maybe_float(pct_chg),
                "open": ohlc.get("open"),
                "high": ohlc.get("high"),
                "low": ohlc.get("low"),
                "outlook": rr.get("outlook"),
                "rr_pos": _pct(rr_pos),
                "trade": trade_sig,
                "trend": trend_sig,
                "is_hot": rr_pos is not None and rr_pos >= hot_pct,
                "is_cold": rr_pos is not None and rr_pos <= cold_pct,
                "wow_pct": wow_pct,
                "monthly_score": _maybe_float(ms_map.get(sym)),
                "inverted": inverted,
            })

        # Area roll-up
        n = len(sigs)
        area_sig_sum = sum(sigs)
        area_stance_raw = _sign(area_sig_sum)
        conviction = abs(area_sig_sum) / n if n else 0.0
        area_rr_pos = _safe_median(rr_positions)
        extremes_hot = [
            m["symbol"] for m in member_details
            if m.get("is_hot")
        ]
        extremes_cold = [
            m["symbol"] for m in member_details
            if m.get("is_cold")
        ]

        # Trade/Trend area-level (majority vote from dual members)
        area_trade = _sign(sum(trade_sigs)) if trade_sigs else None
        area_trend = _sign(sum(trend_sigs)) if trend_sigs else None

        areas_out.append({
            "area_key": area_key,
            "label": label,
            "stance": _stance_label(area_stance_raw),
            "conviction": round(conviction, 2),
            "trade": area_trade,
            "trend": area_trend,
            "rr_pos": _pct(area_rr_pos),
            "extremes_hot": extremes_hot,
            "extremes_cold": extremes_cold,
            "members": member_details,
        })

    # --- Sectors roll-up ---
    from collections import defaultdict as _dd
    sec_data: dict[str, list] = _dd(list)
    for row in sector_rows:
        sec_raw = row.get("sector")
        if not sec_raw:
            continue
        sec_lower = sec_raw.strip().lower()
        if sec_lower not in _GICS_11_LOWER:
            continue
        # Use canonical display form (merges "Health care" and "Health Care")
        sec_display = _GICS_DISPLAY.get(sec_lower, sec_raw.strip())
        last = _maybe_float(row.get("last_price"))
        tv = _maybe_float(row.get("a_trade_value"))
        trv = _maybe_float(row.get("a_trend_value"))
        above_trade = (last is not None and tv is not None and last > tv)
        above_trend = (last is not None and trv is not None and last > trv)
        sec_data[sec_display].append({
            "sym": row["tos_symbol"],
            "above_trade": above_trade,
            "above_trend": above_trend,
        })

    sector_scores: list[dict] = []
    for sec, syms in sec_data.items():
        n = len(syms)
        if n == 0:
            continue
        pct_trade = sum(1 for x in syms if x["above_trade"]) / n
        pct_trend = sum(1 for x in syms if x["above_trend"]) / n
        score = (pct_trade + pct_trend) / 2
        etf_symbol = _SECTOR_ETF.get(sec)
        etf = _sector_etf_proxy(etf_symbol, q_map, tech_map, rr_map, ms_map) if etf_symbol else None
        sector_scores.append({
            "sector": sec,
            "n": n,
            "pct_above_trade": round(pct_trade, 2),
            "pct_above_trend": round(pct_trend, 2),
            "score": round(score, 2),
            "etf": etf,
        })
    sector_scores.sort(key=lambda x: -x["score"])

    leaders   = [s["sector"] for s in sector_scores[:3] if s["score"] >= 0.5]
    laggards  = [s["sector"] for s in reversed(sector_scores) if s["score"] < 0.3][:2]
    rotate_in = [
        s["sector"] for s in sector_scores
        if s["pct_above_trend"] >= 0.5 and s["pct_above_trade"] < 0.5
    ][:3]

    top_down = _build_top_down(areas_out)

    return {
        "as_of": str(anchor),
        "areas": areas_out,
        "sectors": {
            "all": sector_scores,
            "leaders": leaders,
            "laggards": laggards,
            "rotate_in": rotate_in,
        },
        "top_down": top_down,
    }


# ---- helpers ----

def _maybe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _pct(v: Optional[float]) -> Optional[float]:
    if v is None:
        return None
    return round(v, 3)


def _sector_etf_proxy(symbol: str, q_map: dict, tech_map: dict, rr_map: dict, ms_map: dict) -> Optional[dict]:
    """Single-symbol ETF read for a sector row: price/%chg (drv_quote, so it
    reflects the latest intraday quote on the anchor date), Trade/Trend
    direction (drv_technicals), and Risk Range position (drv_rr) — same
    fields/formula as the area rows above (rr_pos = (last-lrr)/(trr-lrr))."""
    q = q_map.get(symbol, {})
    t = tech_map.get(symbol, {})
    r = rr_map.get(symbol, {})
    last = _maybe_float(q.get("last_price"))
    if last is None:
        last = _maybe_float(t.get("last_price"))
    if last is None:
        return None
    tv = _maybe_float(t.get("a_trade_value"))
    trv = _maybe_float(t.get("a_trend_value"))
    lrr = _maybe_float(r.get("lrr"))
    trr = _maybe_float(r.get("trr"))
    rr_pos = None
    if lrr is not None and trr is not None and trr != lrr:
        rr_pos = (last - lrr) / (trr - lrr)
    return {
        "symbol": symbol,
        "last": last,
        "pct_change": _maybe_float(q.get("pct_change")),
        "td": "up" if tv is not None and last > tv else ("down" if tv is not None else None),
        "tn": "up" if trv is not None and last > trv else ("down" if trv is not None else None),
        "rr_pos": _pct(rr_pos),
        "outlook": r.get("outlook"),
        "monthly_score": _maybe_float(ms_map.get(symbol)),
    }


def _wow_pct(
    last, prior
) -> Optional[float]:
    try:
        l, p = float(last), float(prior)
    except (TypeError, ValueError):
        return None
    if p == 0:
        return None
    return round((l - p) / abs(p) * 100, 2)
