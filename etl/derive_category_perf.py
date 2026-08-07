"""
etl/derive_category_perf.py — TASK_133 Phase 5: drv_category_perf (factor
scorecard). "My allocation % to each sector/asset-class/style and how I am
doing over 1w/3w/1m/2m/3m, time-weighted, vs a proxy benchmark and vs the
quad's own stance for that category."

Wired into derive_all() AFTER drv_macro_score (needs sector_stance/
asset_class_stance/style_stances -- the live per-membership quad-regime read
against the effective 60-day window, TASK_126) and AFTER drv_market_stat
(needs risk_budget for the ADD/PRESS -> HOLD cap). This is later than the
"after drv_portfolio" note in TASK_133's own Phase 5 header -- drv_portfolio
alone doesn't carry quad_stance, drv_macro_score does, and drv_macro_score
runs near the end of derive_all(); see DEV_HANDOFF.md for this decision.

Returns must be TIME-WEIGHTED (r_t = (V_t - V_{t-1} - netflow_t) / V_{t-1},
chain-linked) -- naive V_end/V_start-1 would count deposits/trades as
performance. See Phase 5.2 mandatory validation in DEV_HANDOFF.md.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import _wrap
from etl.db import replace_for_date
from etl.derive_macro import _classify_style

log = logging.getLogger(__name__)

WINDOWS = {"1w": 5, "3w": 15, "1m": 21, "2m": 42, "3m": 63}
# TASK_140 -- single-day windows, each (window_days, end_offset). "today" is
# the 1-day return ending at D (calendar[-1]); "yesterday" is the isolated
# 1-day return ending at D-1 (calendar[-2]) -- NOT a 2-day cumulative window,
# see _twr_window's end_offset docstring. Kept separate from WINDOWS (which
# every other flows_confidence/verdict computation still iterates over
# unchanged) so CALENDAR_BUFFER and the vs-Mkt trailing-window columns are
# unaffected by this addition.
EXTRA_WINDOWS = {"today": (1, 0), "yesterday": (1, 1)}
CALENDAR_BUFFER = 70          # trading days fetched (>= max window + 1 for the baseline day)
FLOW_GUARD_PCT = 25.0          # |r_t| > this -> flow-artefact guard (spec 5.2)

# GICS "Health care"/"Health Care" case-variant canonicalization (mirrors
# api/routers/macro_areas.py::_GICS_DISPLAY so sector labels match everywhere).
_SECTOR_CANON = {
    "health care": "Health Care", "healthcare": "Health Care",
}

# Sector -> proxy ETF, reused verbatim from api/routers/macro_areas.py (do
# not reimplement -- same source of truth for both screens).
from api.routers.macro_areas import _SECTOR_ETF  # noqa: E402

# Asset-class -> proxy ETF. All confirmed to have live drv_quote history
# during TASK_133 investigation (132 days, matching the tracked universe).
_ASSET_CLASS_ETF = {
    "Equities":     "SPY",
    "Fixed Income": "TLT",   # AGG has no drv_quote history in this system; TLT does
    "Commodities":  "GSG",
    "Gold":         "GLD",
    "FX":           "UUP",
    "Crypto":       "IBIT",
    "USD":          "UUP",
    # Cash: no proxy -- flat 0% benchmark (informational only), see bench_symbol=NULL below.
}

# Style tag -> proxy ETF. Best-effort; several dedicated factor ETFs (SPHB,
# SPYV/VTV, MDY/IJH) have no drv_quote history in this system, so those fall
# back to SPY as a generic market benchmark -- documented, not hidden.
_STYLE_ETF = {
    "Momentum":  "MTUM",
    "High Beta": "SPY",     # SPHB unavailable -- fallback
    "Low Beta":  "SPLV",
    "Cyclical":  "XLY",
    "Defensives": "XLP",
    "Secular":   "QQQ",
    "Value":     "SPY",     # VTV/SPYV unavailable -- fallback
    "Dividend":  "VYM",
    "Small Caps": "IWM",
    "Mid Caps":  "SPY",     # MDY/IJH unavailable -- fallback
}

_GICS_SET = set(_SECTOR_ETF.keys())
_ASSET_CLASS_SET = set(_ASSET_CLASS_ETF.keys()) | {"Cash"}
_STYLE_SET = set(_STYLE_ETF.keys())


def _canon_sector(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s2 = s.strip()
    if s2.lower() in _SECTOR_CANON:
        return _SECTOR_CANON[s2.lower()]
    return s2 if s2 in _GICS_SET else None


def _trading_calendar(session: Session, as_of_date: date, n: int) -> list:
    rows = session.execute(text(
        "SELECT export_date FROM hist_td WHERE export_date <= :d "
        "GROUP BY export_date ORDER BY export_date DESC LIMIT :n"
    ), {"d": as_of_date, "n": n}).scalars().all()
    return sorted(rows)  # ascending


# ---------------------------------------------------------------------------
# Category map: tos_symbol -> {sector, asset_class, style_tags, source}
# ---------------------------------------------------------------------------

def _build_category_map(session: Session, as_of_date: date, symbols: set) -> dict:
    out: dict = {}
    if not symbols:
        return out
    syms = list(symbols)

    ma_rows = session.execute(text(
        "SELECT tos_symbol, sector, asset_class, beta, pe_ratio, div_yield, "
        "rsi, market_cap_str FROM drv_ma WHERE as_of_date = :d "
        "AND tos_symbol = ANY(:syms)"
    ), {"d": as_of_date, "syms": syms}).mappings().all()
    have = set()
    for r in ma_rows:
        sector = _canon_sector(r["sector"])
        asset_class = r["asset_class"] if r["asset_class"] in _ASSET_CLASS_SET else None
        styles = [s[1] for s in _classify_style(
            r["beta"], r["pe_ratio"], r["div_yield"], r["rsi"], r["market_cap_str"], sector)]
        out[r["tos_symbol"]] = {"sector": sector, "asset_class": asset_class,
                                 "styles": styles, "source": "drv_ma"}
        have.add(r["tos_symbol"])

    missing = [s for s in syms if s not in have]
    if missing:
        # Fallback: ref_sector (broader universe, ~961 tickers, same
        # asset_class/equity_sector vocabulary confirmed during investigation).
        rf_rows = session.execute(text(
            "SELECT ticker, equity_sector, asset_class FROM ref_sector "
            "WHERE ticker = ANY(:syms)"
        ), {"syms": missing}).mappings().all()
        for r in rf_rows:
            sector = _canon_sector(r["equity_sector"])
            asset_class = r["asset_class"] if r["asset_class"] in _ASSET_CLASS_SET else None
            out[r["ticker"]] = {"sector": sector, "asset_class": asset_class,
                                 "styles": [], "source": "ref_sector"}
            have.add(r["ticker"])

    for s in syms:
        if s not in have:
            out[s] = {"sector": None, "asset_class": None, "styles": [], "source": "unmapped"}
    return out


# ---------------------------------------------------------------------------
# Position + flow series
# ---------------------------------------------------------------------------

_POSITIONS_SQL = text("""
    SELECT snapshot_date, tos_symbol, symbol, security_type AS sec_type,
           description, market_value AS mv, qty, 'CS' AS src
    FROM hist_cs WHERE snapshot_date BETWEEN :lo AND :hi
    UNION ALL
    SELECT snapshot_date, tos_symbol, symbol, type AS sec_type,
           description, current_value AS mv, qty, 'F' AS src
    FROM hist_f WHERE snapshot_date BETWEEN :lo AND :hi
""")

_FLOWS_SQL = text("""
    SELECT trade_date, tos_symbol, action, amount, 'CST' AS src
    FROM hist_cst WHERE trade_date BETWEEN :lo AND :hi
      AND (UPPER(COALESCE(action,'')) LIKE '%BUY%' OR UPPER(COALESCE(action,'')) LIKE '%SELL%')
    UNION ALL
    SELECT trade_date, tos_symbol, action_kind AS action, amount, 'FT' AS src
    FROM hist_ft WHERE trade_date BETWEEN :lo AND :hi
      AND (UPPER(COALESCE(action_kind,'')) LIKE '%BUY%' OR UPPER(COALESCE(action_kind,'')) LIKE '%SELL%')
""")

# Broad (ANY action) flow-dates query, used only for gap DETECTION -- not for
# netflow math. A Buy/Sell isn't the only legitimate reason a qty can change
# (Stock Split, Reinvest Shares, Reinvest Dividend all move qty too); any row
# at all on that date for that symbol is enough to explain the change. See
# _build_series' gap-detection block and DEV_HANDOFF.md (round 2 / Part A).
_ANY_FLOW_DATES_SQL = text("""
    SELECT DISTINCT trade_date, tos_symbol FROM hist_cst
    WHERE trade_date BETWEEN :lo AND :hi AND tos_symbol IS NOT NULL
    UNION
    SELECT DISTINCT trade_date, tos_symbol FROM hist_ft
    WHERE trade_date BETWEEN :lo AND :hi AND tos_symbol IS NOT NULL
""")


def _load_positions_and_flows(session: Session, lo: date, hi: date) -> tuple[list, list]:
    positions = session.execute(_POSITIONS_SQL, {"lo": lo, "hi": hi}).mappings().all()
    flows = session.execute(_FLOWS_SQL, {"lo": lo, "hi": hi}).mappings().all()
    return list(positions), list(flows)


def _load_any_flow_dates(session: Session, lo: date, hi: date) -> dict:
    """{tos_symbol: {trade_date, ...}} for ANY hist_cst/hist_ft row (any
    action) in the window -- used only to tell whether a qty change on a
    given date is explained by *some* transaction row, not to compute
    netflow amounts."""
    rows = session.execute(_ANY_FLOW_DATES_SQL, {"lo": lo, "hi": hi}).all()
    out: dict = {}
    for trade_date, tos_symbol in rows:
        if tos_symbol is None:
            continue
        out.setdefault(tos_symbol, set()).add(trade_date)
    return out


def _categories_for(symbol_key: str, cat_map: dict, axis: str) -> list:
    """Which categories (of this axis) a holding's value/flow should be
    attributed to. sector/asset_class: exactly 1 category (falls back to
    "Unmapped" whenever it can't resolve -- whether the symbol itself is
    outside both drv_ma and ref_sector, OR it's IN one of them but that
    field is NULL there. TASK_133 bug found + fixed during Phase 5
    reconciliation testing: DESK/IPAY/NOBL/VYM are in drv_ma with sector=
    asset_class=NULL, and an earlier version of this function returned []
    for them -- silently dropping ~$566 of market value from every axis
    with no Unmapped row to catch it. See DEV_HANDOFF.md.). style: 0..N tags
    (overlap by design -- spec 5.1); a mapped symbol with genuinely zero
    qualifying tags is NOT a gap (expected _classify_style behavior) so only
    truly-unmapped symbols get a style "Unmapped" bucket."""
    info = cat_map.get(symbol_key)
    if info is None:
        return ["Unmapped"] if axis != "style" else []
    if axis == "sector":
        return [info["sector"]] if info["sector"] else ["Unmapped"]
    if axis == "asset_class":
        return [info["asset_class"]] if info["asset_class"] else ["Unmapped"]
    if axis == "style":
        if info["source"] == "unmapped":
            return ["Unmapped"]
        return list(info["styles"])  # empty list = valid "no style tags" (not an Unmapped case)
    return []


def _build_series(positions: list, flows: list, cat_map: dict, cash_keys: set,
                  calendar: list, any_flow_dates: dict) -> dict:
    """Returns {axis: {category: {date: {'v': value, 'flow': netflow,
    'gap_symbols': [...]}}}}.

    Two clean passes: (1) accumulate RAW same-day totals only (no
    carry-forward yet, so a flow-only day is never mistaken for a real
    zero-value snapshot), (2) walk the trading calendar once per category
    carrying the last REAL snapshot value forward and attaching that day's
    own flow (0.0 if none) -- this is what makes the TWR telescoping
    identity (Phase 5.2 mandatory check) hold exactly.

    Plus (round 2 / Part A): per-symbol qty-gap detection. If a symbol's
    total qty changes between two REPORTED snapshots with zero matching row
    in hist_cst/hist_ft (any action -- a Stock Split/Reinvest legitimately
    explains a qty change and must not be flagged), that date is tagged
    'gap_symbols' for every category the symbol maps to on every axis.
    _twr_window() treats a tagged date the same as the existing 25%
    flow-artefact guard: r_t forced to 0, window marked 'suspect'. Found
    during TASK_133 round-2 investigation (TEST_REPORT_39.md): a Schwab
    transaction feed (hist_cst) for one account stopped loading 2026-06-02
    while its hist_cs positions kept updating, and a Fidelity account's
    positions (hist_f) have never had a single matching hist_ft row -- both
    real, ongoing feed gaps, not one-off corporate actions. See
    DEV_HANDOFF.md."""
    axes = ("sector", "asset_class", "style")
    raw_v: dict = {ax: {} for ax in axes}     # {category: {date: value}}
    raw_flow: dict = {ax: {} for ax in axes}  # {category: {date: flow}}
    raw_gap: dict = {ax: {} for ax in axes}   # {category: {date: {symbols}}}

    # Days the portfolio was ACTUALLY snapshotted at all (any symbol, any
    # category) -- computed up-front since the gap-detection pass below
    # needs it too (see _build_series docstring / carry-forward note below).
    reported_dates = {p["snapshot_date"] for p in positions}

    # --- qty-gap detection (round 2 / Part A) ---
    qty_by_symbol: dict = {}   # {symbol: {date: qty}}
    for p in positions:
        key = p["tos_symbol"] or p["symbol"]
        if key in cash_keys:
            continue
        d = p["snapshot_date"]
        q = float(p["qty"]) if p.get("qty") is not None else 0.0
        qs = qty_by_symbol.setdefault(key, {})
        qs[d] = qs.get(d, 0.0) + q

    gap_symbols_by_date: dict = {}  # {date: {symbols}}
    for key, qs in qty_by_symbol.items():
        flow_dates = any_flow_dates.get(key, set())
        last_qty = None
        for d in calendar:
            if d not in reported_dates:
                continue
            today_qty = qs.get(d, 0.0)
            if (last_qty is not None and abs(today_qty - last_qty) > 1e-6
                    and d not in flow_dates):
                gap_symbols_by_date.setdefault(d, set()).add(key)
            last_qty = today_qty

    for p in positions:
        key = p["tos_symbol"] or p["symbol"]
        d = p["snapshot_date"]
        mv = float(p["mv"]) if p["mv"] is not None else 0.0
        if key in cash_keys:
            rv = raw_v["asset_class"].setdefault("Cash", {})
            rv[d] = rv.get(d, 0.0) + mv
            continue
        is_gap_symbol = key in gap_symbols_by_date.get(d, set())
        for ax in ("sector", "asset_class"):
            for cat in _categories_for(key, cat_map, ax):
                rv = raw_v[ax].setdefault(cat, {})
                rv[d] = rv.get(d, 0.0) + mv
                if is_gap_symbol:
                    rg = raw_gap[ax].setdefault(cat, {}).setdefault(d, set())
                    rg.add(key)
        for cat in _categories_for(key, cat_map, "style"):
            rv = raw_v["style"].setdefault(cat, {})
            rv[d] = rv.get(d, 0.0) + mv
            if is_gap_symbol:
                rg = raw_gap["style"].setdefault(cat, {}).setdefault(d, set())
                rg.add(key)

    for f in flows:
        key = f["tos_symbol"]
        d = f["trade_date"]
        if key in cash_keys or key is None:
            continue
        amt = float(f["amount"]) if f["amount"] is not None else 0.0
        # netflow (position-value impact) = -amount: hist_cst/hist_ft amount
        # follows a cash-ledger sign (Buy=negative cash, Sell=positive cash);
        # negating gives the position-value impact (Buy=+, Sell=-). Verified
        # against live rows during TASK_133 investigation.
        flow = -amt
        for ax in ("sector", "asset_class"):
            for cat in _categories_for(key, cat_map, ax):
                rf = raw_flow[ax].setdefault(cat, {})
                rf[d] = rf.get(d, 0.0) + flow
        for cat in _categories_for(key, cat_map, "style"):
            rf = raw_flow["style"].setdefault(cat, {})
            rf[d] = rf.get(d, 0.0) + flow

    # reported_dates is used here (not recomputed -- see top of function) to
    # tell "this category has zero holdings today" (a real, reportable 0)
    # apart from "hist_cs/hist_f simply didn't load today" (a true gap ->
    # carry forward). Without this distinction, a position that is fully
    # sold/closed mid-window would carry its stale last-known value forward
    # FOREVER instead of resetting to 0 on the next real snapshot -- found
    # during Phase 5 portfolio-reconciliation testing (USD/FX categories kept
    # showing $22,667 of value from closed positions that no longer exist in
    # today's holdings). See DEV_HANDOFF.md.

    series: dict = {ax: {} for ax in axes}
    for ax in axes:
        categories = set(raw_v[ax]) | set(raw_flow[ax])
        for cat in categories:
            v_by_date = raw_v[ax].get(cat, {})
            f_by_date = raw_flow[ax].get(cat, {})
            g_by_date = raw_gap[ax].get(cat, {})
            by_date: dict = {}
            last_v = None
            for d in calendar:
                if d in v_by_date:
                    last_v = v_by_date[d]
                elif d in reported_dates:
                    last_v = 0.0
                by_date[d] = {"v": last_v if last_v is not None else 0.0,
                              "flow": f_by_date.get(d, 0.0),
                              "gap_symbols": sorted(g_by_date.get(d, set()))}
            series[ax][cat] = by_date
    return series


def _twr_window(by_date: dict, calendar: list, window_days: int, end_offset: int = 0) -> tuple:
    """Returns (twr, flows_confidence, detail). calendar is ascending; the
    window is `window_days` steps ending `end_offset` days back from
    calendar[-1] -- end_offset=0 (default) ends at calendar[-1] (today, D);
    end_offset=1 ends at calendar[-2] (yesterday, D-1), used for the
    "Yesterday" column, an isolated single day, not "today back through
    yesterday" -- that distinction is why this needs its own offset rather
    than just window_days=2.

    Two independent guards force r_t=0 and mark the window 'suspect': (1) the
    original |r_t| > 25% flow-artefact guard, and (2) (round 2 / Part A) an
    unexplained symbol-level qty gap on d_cur -- a qty change with zero
    matching hist_cst/hist_ft row, which the 25% guard alone would miss
    whenever the swap is small relative to the category's total value (see
    _build_series docstring and DEV_HANDOFF.md)."""
    if len(calendar) <= window_days + end_offset:
        return None, "amber", {"reason": "insufficient calendar history"}
    end_idx = len(calendar) - end_offset
    idx_dates = calendar[end_idx - (window_days + 1):end_idx]  # window_days+1 points -> window_days steps
    product = 1.0
    suspect = False
    day_count = 0
    netflow_total = 0.0
    gap_days = []
    for i in range(1, len(idx_dates)):
        d_prev, d_cur = idx_dates[i - 1], idx_dates[i]
        v_prev = by_date.get(d_prev, {}).get("v", 0.0)
        v_cur = by_date.get(d_cur, {}).get("v", 0.0)
        flow = by_date.get(d_cur, {}).get("flow", 0.0)
        gap_syms = by_date.get(d_cur, {}).get("gap_symbols") or []
        netflow_total += flow
        if not v_prev:
            r = 0.0
        else:
            r = (v_cur - v_prev - flow) / v_prev
            if abs(r) > FLOW_GUARD_PCT / 100.0:
                r = 0.0
                suspect = True
        if gap_syms:
            r = 0.0
            suspect = True
            gap_days.append({"date": d_cur.isoformat(), "symbols": gap_syms})
        product *= (1.0 + r)
        day_count += 1
    twr = product - 1.0
    confidence = "suspect" if suspect else "green"
    detail = {"day_count": day_count, "netflow_total": round(netflow_total, 2)}
    if gap_days:
        detail["gap_days"] = gap_days
    return twr, confidence, detail


def _bench_return(session: Session, symbol: Optional[str], calendar: list, window_days: int,
                   end_offset: int = 0) -> Optional[float]:
    if not symbol or len(calendar) <= window_days + end_offset:
        return None
    end_idx = len(calendar) - end_offset
    d_start, d_end = calendar[end_idx - (window_days + 1)], calendar[end_idx - 1]
    rows = session.execute(text(
        "SELECT as_of_date, last_price FROM drv_quote WHERE tos_symbol = :s "
        "AND as_of_date IN (:a, :b)"
    ), {"s": symbol, "a": d_start, "b": d_end}).mappings().all()
    by_date = {r["as_of_date"]: float(r["last_price"]) for r in rows if r["last_price"]}
    if d_start not in by_date or d_end not in by_date or by_date[d_start] == 0:
        return None
    return by_date[d_end] / by_date[d_start] - 1.0


def _quad_label(stance: Optional[float]) -> Optional[str]:
    if stance is None:
        return None
    if stance > 0:
        return "BULLISH"
    if stance < 0:
        return "BEARISH"
    return "NEUTRAL"


def _verdict(quad: Optional[str], band: Optional[str], twr: dict, bench: dict,
             risk_budget: Optional[int]) -> tuple:
    """band: 'under' | 'at' | 'over' | None. Returns (verdict, note)."""
    if quad is None or band is None:
        return None, "no target/quad data -- verdict not computed"
    matrix = {
        ("under", "BULLISH"): "ADD", ("under", "NEUTRAL"): "WATCH", ("under", "BEARISH"): "AVOID",
        ("at", "BULLISH"): "HOLD", ("at", "NEUTRAL"): "HOLD", ("at", "BEARISH"): "TRIM",
        ("over", "BULLISH"): "HOLD_NO_ADD", ("over", "NEUTRAL"): "TRIM", ("over", "BEARISH"): "TRIM_HARD",
    }
    v = matrix.get((band, quad))
    if v is None:
        return None, "unrecognized band/quad combination"
    note = None
    if v == "HOLD" and band == "at" and quad == "BULLISH":
        m1 = twr.get("twr_1m")
        if m1 is not None and m1 > 0:
            v = "PRESS"
    if v == "ADD":
        trailing = sum(
            1 for w in WINDOWS
            if twr.get(f"twr_{w}") is not None and bench.get(f"bench_{w}") is not None
            and twr[f"twr_{w}"] < bench[f"bench_{w}"]
        )
        if trailing >= 2:
            v = "ROTATE"
            note = f"trails benchmark in {trailing}/5 windows"
    if v in ("ADD", "PRESS") and risk_budget is not None and risk_budget < 55:
        note = (note + "; " if note else "") + f"risk_budget {risk_budget} < 55 -> capped to HOLD"
        v = "HOLD"
    return v, note


def _derive_category_perf_impl(session: Session, as_of_date: date, run_id) -> int:
    calendar = _trading_calendar(session, as_of_date, CALENDAR_BUFFER)
    if not calendar:
        return replace_for_date(session, "drv_category_perf", "as_of_date", as_of_date, [])
    lo, hi = calendar[0], calendar[-1]

    positions, flows = _load_positions_and_flows(session, lo, hi)

    symbols = {(p["tos_symbol"] or p["symbol"]) for p in positions}
    cash_keys = set()
    is_cash_rows = session.execute(text(
        "SELECT DISTINCT COALESCE(tos_symbol, symbol) AS k FROM ("
        "  SELECT tos_symbol, symbol, security_type, description FROM hist_cs "
        "  WHERE snapshot_date BETWEEN :lo AND :hi"
        "  UNION ALL"
        "  SELECT tos_symbol, symbol, type AS security_type, description FROM hist_f "
        "  WHERE snapshot_date BETWEEN :lo AND :hi"
        ") u WHERE is_cash(symbol, security_type, description)"
    ), {"lo": lo, "hi": hi}).scalars().all()
    cash_keys = set(is_cash_rows)

    non_cash_symbols = symbols - cash_keys
    cat_map = _build_category_map(session, as_of_date, non_cash_symbols)

    any_flow_dates = _load_any_flow_dates(session, lo, hi)
    series = _build_series(positions, flows, cat_map, cash_keys, calendar, any_flow_dates)

    # Total portfolio value at D (market + cash) for weight_pct -- same
    # universe as /api/portfolio/summary (latest hist_f/hist_cs snapshot <= D
    # each, cash included). Phase 5 mandatory reconciliation check.
    total_row = session.execute(text("""
        WITH f_latest AS (SELECT MAX(snapshot_date) d FROM hist_f WHERE snapshot_date <= :d),
             cs_latest AS (SELECT MAX(snapshot_date) d FROM hist_cs WHERE snapshot_date <= :d)
        SELECT
          COALESCE((SELECT SUM(current_value) FROM hist_f WHERE snapshot_date=(SELECT d FROM f_latest)),0)
        + COALESCE((SELECT SUM(market_value) FROM hist_cs WHERE snapshot_date=(SELECT d FROM cs_latest)),0)
          AS total
    """), {"d": as_of_date}).scalar()
    total_value = float(total_row) if total_row else 0.0

    # Quad stance per category via drv_macro_score's live per-membership
    # read (sector_stance/asset_class_stance/style_stances) -- already
    # computed against the effective 60-day window (TASK_126); reused, not
    # recomputed. One representative tos_symbol per category is enough since
    # the stance value is a function of (axis, category) only, not the symbol.
    quad_rows = session.execute(text(
        "SELECT sector, asset_class, sector_stance, asset_class_stance, style_stances "
        "FROM drv_ma m LEFT JOIN drv_macro_score ms "
        "  ON ms.tos_symbol = m.tos_symbol AND ms.as_of_date = m.as_of_date "
        "WHERE m.as_of_date = :d"
    ), {"d": as_of_date}).mappings().all()
    sector_stance_map: dict = {}
    asset_class_stance_map: dict = {}
    style_stance_map: dict = {}
    for r in quad_rows:
        sec = _canon_sector(r["sector"])
        if sec and sec not in sector_stance_map and r["sector_stance"] is not None:
            sector_stance_map[sec] = float(r["sector_stance"])
        ac = r["asset_class"]
        if ac and ac not in asset_class_stance_map and r["asset_class_stance"] is not None:
            asset_class_stance_map[ac] = float(r["asset_class_stance"])
        styles = r["style_stances"]
        if isinstance(styles, str):
            import json as _json
            try:
                styles = _json.loads(styles)
            except Exception:
                styles = []
        for s in (styles or []):
            lbl = s.get("label")
            if lbl and lbl not in style_stance_map and s.get("stance") is not None:
                style_stance_map[lbl] = float(s["stance"])

    risk_budget = session.execute(text(
        "SELECT risk_budget FROM drv_market_stat WHERE as_of_date = :d"
    ), {"d": as_of_date}).scalar()

    aa_rows = session.execute(text(
        "SELECT category, min_pct, max_pct, min_dollar, max_dollar FROM ref_asset_allocation"
    )).mappings().all()
    aa_map = {r["category"]: r for r in aa_rows}
    _AC_TO_AA = {"Equities": "Equities", "Fixed Income": "Fixed Income",
                 "Commodities": "Commodities", "Cash": "Cash", "FX": "Foreign Exchange"}

    rows_out = []
    for axis, etf_map, stance_map in (
        ("sector", _SECTOR_ETF, sector_stance_map),
        ("asset_class", _ASSET_CLASS_ETF, asset_class_stance_map),
        ("style", _STYLE_ETF, style_stance_map),
    ):
        for category, by_date in series[axis].items():
            mv = by_date.get(hi, {}).get("v", 0.0)
            weight_pct = (mv / total_value * 100.0) if total_value else None

            twr = {}
            bench = {}
            window_detail = {}
            confs = []
            for wlabel, wdays in WINDOWS.items():
                t, conf, detail_w = _twr_window(by_date, calendar, wdays)
                twr[f"twr_{wlabel}"] = t
                b = _bench_return(session, etf_map.get(category), calendar, wdays)
                bench[f"bench_{wlabel}"] = b
                window_detail[wlabel] = {"confidence": conf, **detail_w}
                if len(calendar) > wdays:
                    confs.append(conf)
            for wlabel, (wdays, offset) in EXTRA_WINDOWS.items():
                t, conf, detail_w = _twr_window(by_date, calendar, wdays, offset)
                twr[f"twr_{wlabel}"] = t
                b = _bench_return(session, etf_map.get(category), calendar, wdays, offset)
                bench[f"bench_{wlabel}"] = b
                window_detail[wlabel] = {"confidence": conf, **detail_w}
                if len(calendar) > wdays + offset:
                    confs.append(conf)
            # flows_confidence: worst across windows that had data
            flows_confidence = ("suspect" if "suspect" in confs
                               else "amber" if any(c == "amber" for c in confs) else
                               ("green" if confs else "amber"))

            quad_stance = _quad_label(stance_map.get(category))

            target_min = target_max = None
            band = None
            detail: dict = {"category_source": "computed"}
            if axis == "style":
                detail["note"] = "overlapping tags -- not an allocation; no weight-based verdict"
            elif category == "Unmapped":
                detail["note"] = "holdings that did not resolve to a category (see DEV_HANDOFF.md)"
            else:
                aa_key = _AC_TO_AA.get(category, category) if axis == "asset_class" else None
                aa_row = aa_map.get(aa_key) if aa_key else None
                if aa_row and aa_row["min_dollar"] is not None and aa_row["max_dollar"] is not None:
                    min_d, max_d = float(aa_row["min_dollar"]), float(aa_row["max_dollar"])
                    target_min = (min_d / total_value * 100.0) if total_value else None
                    target_max = (max_d / total_value * 100.0) if total_value else None
                    if mv < min_d:
                        band = "under"
                    elif mv > max_d:
                        band = "over"
                    else:
                        band = "at"
                    detail["target_source"] = "ref_asset_allocation (dollar band)"
                elif axis == "sector":
                    mid = 100.0 / 11.0
                    target_min, target_max = mid - 3.0, mid + 3.0
                    if weight_pct is not None:
                        band = "under" if weight_pct < target_min else ("over" if weight_pct > target_max else "at")
                    detail["target_source"] = "equal-weight (100/11 GICS sectors) +/- 3pp -- no per-sector benchmark target exists in the schema"
                else:
                    detail["note"] = "no allocation target defined for this category"

            verdict, note = (_verdict(quad_stance, band, twr, bench, int(risk_budget) if risk_budget is not None else None)
                            if axis != "style" else (None, "overlapping tags -- not an allocation"))
            if note:
                detail["verdict_note"] = note
            detail["windows"] = window_detail

            rows_out.append({
                "as_of_date": as_of_date, "axis": axis, "category": category,
                "market_value": mv, "weight_pct": weight_pct,
                "target_min": target_min, "target_max": target_max,
                **twr, **bench,
                "bench_symbol": etf_map.get(category),
                "flows_confidence": flows_confidence,
                "quad_stance": quad_stance, "verdict": verdict,
                "detail": detail,
            })

    return replace_for_date(session, "drv_category_perf", "as_of_date", as_of_date, rows_out)


derive_category_perf = _wrap("drv_category_perf", _derive_category_perf_impl)
