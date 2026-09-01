"""
Macro read card endpoint — TASK_78.

GET /api/macro-areas?date=D
  Returns per-area stance roll-up from drv_rr, drv_technicals, drv_quote,
  plus a ranked sectors row and a one-line top-down posture sentence.

All computation is done server-side (keeps stance logic co-located with the
MACRO-column logic, not duplicated in JS).
"""
from __future__ import annotations

import json
import math
import statistics
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from api._helpers import (
    _resolve_date, _get_ref_setting, load_quote_ohlc, load_vol_thresholds, rr_pos,
)
from etl.db import session_scope
from etl.derive_macro import _classify_style

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
    # 2026-08-10 -- NOT a GICS-11 sector -- country/region ETFs (EWZ, FXI,
    # INDY, etc.) that Yahoo Finance mistags equity_sector='Financials'
    # (fund-issuer classification quirk, not what the fund holds -- see
    # db/seeds_country_etf_sector.sql). Added here only so
    # etl/derive_category_perf.py::_canon_sector accepts it (_GICS_SET =
    # set(_SECTOR_ETF.keys())) -- this dict is the shared source of truth
    # both that file and this one's own breadth panel (below) import from.
    # No benchmark ETF: VEU/ACWX/VXUS/EFA (broad ex-US equity proxies) all
    # have zero drv_quote history in this system. Does NOT create a new row
    # in this file's OWN Actionable breadth panel below -- that logic gates
    # on the separate, fixed _GICS_11_LOWER set, so a "country etf" sector
    # symbol is skipped there exactly like any other non-GICS-11 sector
    # already was. User: "why can't name them as 'Country ETF'?"
    "Country ETF":             None,
}

# Canonical ordering for areas — each of these is now its own side-panel
# section (broken out one row per member); frontend routes each area_key to
# its own container based on this same set of keys.
# 2026-08-27 -- 'sector_etfs' added: the 11 GICS sector SPDR ETFs (XLF/XLK/
# etc.) as their own full rail panel, same railAreaRow rendering as every
# other area here -- distinct from the separate breadth-based "sectors" roll-
# up below (data.sectors, keyed off drv_technicals per-stock breadth, not
# this table) which now shows breadth stats + $ exposure instead of a single
# ETF-proxy sub-row. User: "add a SECTORS panel in the middle with
# corresponding ETFs (starts with X) similar to other panels."
_AREA_ORDER = [
    "volatility", "top9", "rates_duration", "credit", "commodities_credit",
    "usd_currency", "country_etfs", "crypto", "sector_etfs", "remaining",
]

# Canonical area display name, matching the side-rail section headers in
# actionable.html exactly (2026-07-04). Hardcoded here rather than derived
# from ref_macro_area.label: that column is reused per-member for two
# different things (the area's own name, repeated on most rows, vs. a
# genuine per-member override like '/GC' -> 'Gold' on a few) -- once enough
# members in an area carry a real override, neither "last row" nor "most
# common" reliably recovers the true area name from that column anymore.
_AREA_DISPLAY_NAME = {
    "volatility":          "Volatility",
    "top9":                "Major Markets",
    "rates_duration":      "Rates & Duration",
    "credit":              "Credit",
    "commodities_credit":  "Commodities",
    "usd_currency":        "USD & Currency",
    "country_etfs":        "Country ETFs",
    "crypto":              "Crypto",
    "sector_etfs":         "Sectors",
    "remaining":           "Tech & ETFs",
}

# Symbols that are yield-curve members — skip rr_pos
_CURVE_SYMS = {"DGS2:FRED", "TNX:CGI", "TYX:CGI"}

# Symbols whose color convention flips vs. plain price direction (HY credit —
# rising spread = risk-off = red), mirroring web/market_bar.js's INVERTED
# set (keyed there by chip short-label 'HY'/'HYSPRD'; keyed here by
# tos_symbol so the frontend consolidation (TASK_116) can read it straight
# off each member instead of keeping its own list).
_INVERTED_SYMBOLS = {"HYG", "HYOAS"}


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

        # 2026-08-31 -- final_action (post-suppression, NOT consolidated_action
        # -- see the MSFT investigation this session: consolidated_action is
        # the raw pre-suppression source label and can show a stale/wrong
        # call like ADD on an already-overweight position) for the hover
        # tooltip's action line. Most rail symbols (VIX, /GC, currencies,
        # indices) have no drv_actionable row at all -- left as a graceful
        # gap in the tooltip, not a placeholder dash.
        act_rows = s.execute(text("""
            SELECT tos_symbol, final_action FROM drv_actionable WHERE as_of_date = :d
        """), {"d": anchor}).mappings().all()
        act_map = {r["tos_symbol"]: r["final_action"] for r in act_rows}

        # OHLC (candle) at the same anchor date, and vol thresholds — shared
        # helpers, same source query /api/rr-bar uses (api/_helpers.py
        # ::load_quote_ohlc / load_vol_thresholds), factored out so this
        # router doesn't copy-paste the SQL a third time.
        ohlc_map = load_quote_ohlc(s, anchor)
        vt_map = load_vol_thresholds(s)

        # Load drv_macro_score (Quad-calendar-derived monthly_score + the
        # detail JSONB behind the 6-caret window/quarter breakdown) — same
        # source as rrTape's tile glyph (api/routers/marketbar.py::_RR_SQL).
        ms_rows = s.execute(text("""
            SELECT tos_symbol, monthly_score, detail
            FROM drv_macro_score
            WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_macro_score)
        """)).mappings().all()
        ms_map = {
            r["tos_symbol"]: {
                "monthly_score": r["monthly_score"],
                "macro6": _macro6_from_detail(r["monthly_score"], r["detail"]),
            }
            for r in ms_rows
        }

        # Fund/instrument description, for the symbol-link hover title
        # (web/macro_areas.js::symLink) when a rail member has no friendly
        # ref_macro_area.label override — e.g. HYG's own label is just its
        # area's name ("Credit"), so the row falls back to the raw ticker;
        # ref_sector.description gives "Tracks an index of U.S.
        # dollar-denominated high-yield corporate bonds." instead of
        # nothing. User: "Why HYG is not saying High yield credit?"
        desc_rows = s.execute(text("""
            SELECT ticker, description, sub_asset_class FROM ref_sector
        """)).mappings().all()
        desc_map = {r["ticker"]: (r["description"] or r["sub_asset_class"]) for r in desc_rows}

        # Category Drivers (Sector/Asset Class/Style membership breakdown),
        # for the rail carets' hover popover -- same content, same rules,
        # as the Actionable grid's MACRO-cell popover (api/routers/dash.py::
        # _resolve_memberships), reused here rather than duplicated: same
        # _classify_style() import, same Fixed Income -> sub_asset_class
        # redirect (2026-08-27 HYG/XLF fix), same ref_rrt bridge for
        # symbols ref_sector can't reach directly (2026-08-27 TNX/TYX fix)
        # -- minus drv_actionable, which most rail symbols (VIX, /GC, ...)
        # don't have a row in at all. User: "display the same popover that
        # is just fixed on dashboard screen carets popover."
        fund_rows = s.execute(text("""
            SELECT tos_symbol, sector, asset_class, sub_asset_class,
                   beta, pe_ratio, div_yield, rsi, market_cap_str
            FROM drv_ma WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_ma)
        """)).mappings().all()
        fund_map = {r["tos_symbol"]: r for r in fund_rows}
        bridge_rows = s.execute(text("""
            SELECT DISTINCT ON (rrt.tos_ticker)
                   rrt.tos_ticker, rs.asset_class, rs.sub_asset_class
            FROM ref_rrt rrt
            JOIN ref_sector rs ON rs.ticker = rrt.y_ticker
            WHERE rrt.tos_ticker IS NOT NULL
            ORDER BY rrt.tos_ticker, rrt.preferred_display DESC NULLS LAST, rrt.y_ticker
        """)).fetchall()
        bridge_map = {b.tos_ticker: b for b in bridge_rows}
        quad_rows = s.execute(text("""
            SELECT category, sub_category, quad1, quad2, quad3, quad4
            FROM ref_quad_outlook
        """)).mappings().all()
        quad_lookup = {
            (r["category"], (r["sub_category"] or "").lower()):
                (r["quad1"], r["quad2"], r["quad3"], r["quad4"])
            for r in quad_rows
        }

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
    for r in members_rows:
        area_members[r["area_key"]].append(dict(r))

    areas_out: list[dict] = []
    for area_key in _AREA_ORDER:
        if area_key not in area_members:
            continue
        members_cfg = area_members[area_key]
        label = _AREA_DISPLAY_NAME.get(area_key, area_key)

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
                    "monthly_score": _maybe_float(ms_map.get(sym, {}).get("monthly_score")),
                    "macro6": ms_map.get(sym, {}).get("macro6"),
                    "desc": desc_map.get(sym),
                    "drivers": _category_drivers_for(sym, fund_map, bridge_map, quad_lookup),
                    "inverted": inverted,
                })
                continue

            # 2026-09-01 -- curve members (10Y/30Y Treasury) now go through
            # the SAME rr_pos() computation as everything else below,
            # instead of skipping it. The 2026-08-01 "nonsensical values"
            # revert predates rr_pos()'s own defensive scale guard (see its
            # docstring in api/_helpers.py) -- built specifically for
            # TNX:CGI's day-to-day scale inconsistency (x10 index-level
            # most days, plain percent on 'Y'-feed days) -- which already
            # handles exactly the case that broke the old inline attempt.
            # trade/trend stay None automatically below (that block is
            # gated on role=="dual", which curve members aren't -- they
            # have no drv_technicals Trade/Trend lines to show anyway).
            # User: "Display RR bar for 10year and 30year like others."
            curve_lrr_raw = curve_trr_raw = None
            if role == "curve":
                curve_lrr_raw = _maybe_float(rr.get("lrr"))
                curve_trr_raw = _maybe_float(rr.get("trr"))

            # RR position (all non-gauge) — shared TASK_133 helper
            lrr = _maybe_float(rr.get("lrr"))
            trr = _maybe_float(rr.get("trr"))
            rr_pos_val = rr_pos(last, lrr, trr)

            # Dual: technicals available
            trade_sig = None
            trend_sig = None
            trade_val = None
            trend_val = None
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

            if rr_pos_val is not None:
                rr_positions.append(rr_pos_val)

            wow_pct = _wow_pct(last, wow_map.get(sym))
            member_details.append({
                "symbol": sym,
                "role": role,
                "label": mc.get("label"),
                "last": _maybe_float(last),
                "pct_change": _maybe_float(pct_chg),
                "open": ohlc.get("open"),
                "high": ohlc.get("high"),
                "low": ohlc.get("low"),
                "outlook": rr.get("outlook"),
                "rr_pos": _pct(rr_pos_val),
                "trade": trade_sig,
                "trend": trend_sig,
                "trade_val": trade_val,
                "trend_val": trend_val,
                "action": act_map.get(sym),
                "is_hot": rr_pos_val is not None and rr_pos_val >= hot_pct,
                "is_cold": rr_pos_val is not None and rr_pos_val <= cold_pct,
                "curve_lrr_pct": (curve_lrr_raw / 10.0) if curve_lrr_raw is not None else None,
                "curve_trr_pct": (curve_trr_raw / 10.0) if curve_trr_raw is not None else None,
                "wow_pct": wow_pct,
                "monthly_score": _maybe_float(ms_map.get(sym, {}).get("monthly_score")),
                "macro6": ms_map.get(sym, {}).get("macro6"),
                "desc": desc_map.get(sym),
                "drivers": _category_drivers_for(sym, fund_map, bridge_map, quad_lookup),
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
            "hot_pct": hot_pct,
            "cold_pct": cold_pct,
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


# The 6-caret MacroNet breakdown (60D window, this/next/following month,
# Qtr, Next Qtr) — same 6 legs the Actionable grid's MACRO-cell popover
# shows (web/actionable.js's Window + Quarter sections), sourced from the
# SAME drv_macro_score.detail JSONB that endpoint reads. Deliberately NOT
# reusing /api/actionable/macro-detail here: that endpoint 404s for any
# symbol without a drv_actionable row (rail-panel members — VIX, DXY,
# futures, gauges — mostly don't have one), while detail/monthly_score on
# drv_macro_score itself are populated for the full quad-engine universe.
def _macro6_leg(leg, fallback_label):
    if not leg:
        return None
    return {
        "label": leg.get("m") or leg.get("label") or fallback_label,
        "quad":  leg.get("quad"),
        "w":     _maybe_float(leg.get("w")),
        "stance": _maybe_float(leg.get("stance")),
    }


def _macro6_from_detail(monthly_score, detail) -> Optional[dict]:
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except (TypeError, ValueError):
            detail = None
    if not isinstance(detail, dict):
        detail = {}
    months = detail.get("months") or []
    qw = detail.get("quarter_window") or {}
    carets = {
        "window":    {"label": "60D window", "quad": None, "w": None,
                       "stance": _maybe_float(monthly_score)},
        "month1":    _macro6_leg(months[0] if len(months) > 0 else None, "This month"),
        "month2":    _macro6_leg(months[1] if len(months) > 1 else None, "Next month"),
        "month3":    _macro6_leg(months[2] if len(months) > 2 else None, "Following month"),
        "qtr":       _macro6_leg(qw.get("cur"),  "Qtr"),
        "next_qtr":  _macro6_leg(qw.get("next"), "Next Qtr"),
    }
    if not any(v and v.get("stance") is not None for v in carets.values()):
        return None
    return carets


def _driver_leg(cat: str, sub: str, weight: float, quad_lookup: dict) -> Optional[dict]:
    q = quad_lookup.get((cat, (sub or "").lower()))
    if not q:
        return None
    return {"category": cat, "sub_cat": sub, "weight": weight,
            "quad1": q[0], "quad2": q[1], "quad3": q[2], "quad4": q[3]}


def _category_drivers_for(sym: str, fund_map: dict, bridge_map: dict,
                          quad_lookup: dict) -> list[dict]:
    """Sector/Asset Class/Style membership breakdown for one symbol -- same
    rows, same rules, as the Actionable grid's MACRO-cell popover (see
    api/routers/dash.py::_resolve_memberships, kept in sync by hand since
    that copy also needs drv_actionable context this one doesn't have)."""
    f = fund_map.get(sym)
    sector    = (f["sector"] if f else None) or ""
    asset_cls = (f["asset_class"] if f else None) or ""
    sub_asset = f["sub_asset_class"] if f else None
    if not sector and not asset_cls:
        b = bridge_map.get(sym)
        if b:
            asset_cls = b.asset_class or ""
            sub_asset = b.sub_asset_class

    drivers = []
    if asset_cls == "Fixed Income":
        if sub_asset:
            leg = _driver_leg("Fixed Income", sub_asset, 2.0, quad_lookup)
            if leg: drivers.append(leg)
    elif sector:
        leg = _driver_leg("Equity Sectors", sector, 2.0, quad_lookup)
        if leg: drivers.append(leg)
    if asset_cls:
        leg = _driver_leg("Asset Class", asset_cls, 1.0, quad_lookup)
        if leg: drivers.append(leg)
    if f:
        for cat, sub, wt in _classify_style(
                f["beta"], f["pe_ratio"], f["div_yield"], f["rsi"],
                f["market_cap_str"], sector):
            leg = _driver_leg(cat, sub, wt, quad_lookup)
            if leg: drivers.append(leg)
    return drivers


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
    rr_pos_val = rr_pos(last, lrr, trr)
    return {
        "symbol": symbol,
        "last": last,
        "pct_change": _maybe_float(q.get("pct_change")),
        "td": "up" if tv is not None and last > tv else ("down" if tv is not None else None),
        "tn": "up" if trv is not None and last > trv else ("down" if trv is not None else None),
        "rr_pos": _pct(rr_pos_val),
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
