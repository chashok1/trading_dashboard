"""
etl/derive_market_read.py — TASK_143: drv_source_breadth + drv_theme_stance,
the data layer behind GET /api/market-read (api/routers/cockpit.py) and the
Market Read panel on `/` (web/market_read.js).

Design: docs/market_state_factor_sss_design.md (Addendum A-H). Display +
measurement only — never touches derive_actionable.py/ref_trig_*/
SOURCE_ORDER/ref_settings decision switches.

Wired into derive_all() after drv_category_perf/drv_market_stat, non-
critical (_safe wraps it — a failure here can't break the cascade).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from api._helpers import compute_quad_monthly_stance
from etl._derive_common import _wrap, position_ceiling
from etl.db import replace_for_date
from etl.derive_sss_breadth import _normalize_sss_sector

log = logging.getLogger(__name__)

SOURCES = ["RR", "ETF", "PS", "SSS", "CALL"]

# THEME_CATEGORY_MAP -- theme -> drv_category_perf (axis, category) pairs,
# used for BOTH the theme grid's Price column (reuses the exact breadth
# query behind GET /api/actionable/quad-rotation, api/routers/dash.py::
# get_quad_rotation) and the You $/You % positions columns (Addendum C,
# drv_category_perf.market_value summed over these categories). Coarser
# than ref_symbol_theme's own quad_category/quad_sub_category (e.g.
# drv_category_perf has one "Fixed Income" asset_class bucket, not split by
# duration) -- themes needing that finer split (Duration vs Cash/short FI)
# are left unmapped here and read $0/no breadth, same as the mockup shows,
# rather than misattributing a duration-mismatched dollar figure.
#
# Deliberately ONE axis per theme, never sector+style together for the same
# theme: a single stock carries both a sector AND (independently) a style
# tag, so summing both axes' market_value for one theme double-counts that
# stock's dollars. Found live during TASK_146 verification (Cyclicals'
# sector-only sum + its style="Cyclical" duplicate inflated "risk $ in
# bear-stance themes" to 54% against a real ~8-27% range) -- sector is kept
# (the primary, non-overlapping-within-itself axis for these multi-sector
# themes) and the style duplicate dropped.
THEME_CATEGORY_MAP: dict[str, list[tuple[str, str]]] = {
    "Cash/short FI": [("asset_class", "Fixed Income"), ("asset_class", "Cash")],
    "Small caps": [("style", "Small Caps")],
    "Momentum": [("style", "Momentum")],
    "Defensives": [("sector", "Consumer Staples"), ("sector", "Utilities")],
    "Cyclicals": [("sector", "Consumer Discretionary"), ("sector", "Financials"),
                   ("sector", "Industrials"), ("sector", "Real Estate")],
    "Healthcare": [("sector", "Health Care")],
    "Tech/software": [("sector", "Information Technology")],
    "Energy": [("sector", "Energy")],
    "Precious metals": [("asset_class", "Gold")],
    "Industrial metals": [("asset_class", "Commodities")],
    "Ags": [("asset_class", "Commodities")],
    "Crypto": [("asset_class", "Crypto")],
    "Large caps": [("asset_class", "Equities")],
}

# SSS sector -> theme, for the theme grid's SSS column and Market Read's
# rail-expand click target. Best-effort, not exhaustive -- a sector with no
# entry here simply doesn't vote into any theme's SSS cell (still counted
# in drv_sss_breadth's own sector cards, TASK_144).
SSS_SECTOR_TO_THEME = {
    "Software": "Tech/software",
    "Global Tech": "Semis",
    "Healthcare": "Healthcare",
    "Health Policy": "Healthcare",
    "Financials": "Cyclicals",
    "Retail": "Cyclicals",
    "Industrials": "Cyclicals",
    "Consumer Staples": "Defensives",
    "Energy": "Energy",
    "Restaurants": "Cyclicals",
    "Communications": "Tech/software",
    "Small Caps": "Small caps",
}


# ---------------------------------------------------------------------------
# drv_source_breadth
# ---------------------------------------------------------------------------

def _latest_snapshot(session: Session, table: str, as_of_date: date, date_col: str = "snapshot_date") -> Optional[date]:
    """Latest available snapshot <= ceiling, where ceiling is TODAY on the
    LIVE anchor (these Hedgeye lists routinely lead the TOSD anchor, same
    effective_date convention the Hedgeye panel already uses -- CLAUDE.md
    Lookup: 'effective_date = MAX(anchor, latest across hist_rta/...') but
    as_of_date itself on a HISTORICAL re-derive, to prevent look-ahead bias
    in the 13-week series / trend_1w/4w columns. Same ceiling pattern as
    etl/_derive_common.py::position_ceiling."""
    ceiling = position_ceiling(session, as_of_date)
    return session.execute(text(
        f"SELECT MAX({date_col}) FROM {table} WHERE {date_col} <= :t"
    ), {"t": ceiling}).scalar()


def _rr_bull_bear_counts(session: Session, d: date) -> dict:
    rows = session.execute(text(
        "SELECT outlook, COUNT(*) AS c FROM hist_rr WHERE snapshot_date = :d GROUP BY outlook"
    ), {"d": d}).fetchall()
    n_bull = sum(c for o, c in rows if (o or "").upper() == "BULLISH")
    n_bear = sum(c for o, c in rows if (o or "").upper() == "BEARISH")
    n_neu = sum(c for o, c in rows if (o or "").upper() == "NEUTRAL")
    return {"n_bull": n_bull, "n_bear": n_bear, "n_neutral": n_neu}


def _etf_or_call_counts(session: Session, table: str, d: date) -> dict:
    rows = session.execute(text(
        f"SELECT outlook, COUNT(*) AS c FROM {table} WHERE snapshot_date = :d GROUP BY outlook"
    ), {"d": d}).fetchall()
    n_bull = sum(c for o, c in rows if (o or "").upper() == "BULLISH")
    n_bear = sum(c for o, c in rows if (o or "").upper() == "BEARISH")
    n_neu = sum(c for o, c in rows if (o or "").upper() == "NEUTRAL")
    return {"n_bull": n_bull, "n_bear": n_bear, "n_neutral": n_neu}


def _call_lookback_days(session: Session) -> int:
    """CALL's configured sparse-window length -- same column
    etl/derive_outlook_action.py::_action_call_standing reads
    (`s.get("lookback_days") or 30`), so this stays consistent with how
    the actionable pipeline already treats CALL as a 30-day standing
    source, not a daily one."""
    v = session.execute(text(
        "SELECT lookback_days FROM ref_outlook_source WHERE source_code = 'CALL'"
    )).scalar()
    return int(v) if v else 30


def _call_window_counts(session: Session, as_of_date: date, lookback_days: int) -> tuple[Optional[date], dict]:
    """CALL is a sparse standing source (_action_call_standing): a symbol's
    call persists for `lookback_days` after its last row, not just on the
    single most-recent snapshot_date -- unlike RR/ETF/PS/SSS (dense/
    periodic), most of CALL's universe won't share the same latest date.
    Dedup per symbol to its most recent row in the window (same ROW_NUMBER/
    DISTINCT-ON pattern etl/derive_outlook_action.py::_call_window_states
    already uses) before counting bull/bear/neutral, so a symbol updated
    more than once inside the window is never counted twice. Returns
    (latest date with any row in the window, counts) -- None if the window
    is empty (source has gone stale past its own lookback)."""
    ceiling = position_ceiling(session, as_of_date)
    cutoff = ceiling - timedelta(days=lookback_days)
    rows = session.execute(text("""
        SELECT outlook, COUNT(*) AS c FROM (
            SELECT DISTINCT ON (symbol) symbol, outlook
            FROM hist_call
            WHERE snapshot_date <= :ceil AND snapshot_date >= :cutoff
            ORDER BY symbol, snapshot_date DESC
        ) latest
        GROUP BY outlook
    """), {"ceil": ceiling, "cutoff": cutoff}).fetchall()
    n_bull = sum(c for o, c in rows if (o or "").upper() == "BULLISH")
    n_bear = sum(c for o, c in rows if (o or "").upper() == "BEARISH")
    n_neu = sum(c for o, c in rows if (o or "").upper() == "NEUTRAL")
    latest_date = session.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_call WHERE snapshot_date <= :ceil AND snapshot_date >= :cutoff"
    ), {"ceil": ceiling, "cutoff": cutoff}).scalar()
    if latest_date is None:
        return None, {}
    return latest_date, {"n_bull": n_bull, "n_bear": n_bear, "n_neutral": n_neu}


def _rr_flips(session: Session, d: date) -> Optional[int]:
    """Symbols whose RR outlook on d differs from the prior RR snapshot."""
    prior = session.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_rr WHERE snapshot_date < :d"
    ), {"d": d}).scalar()
    if prior is None:
        return None
    rows = session.execute(text("""
        SELECT cur.symbol FROM hist_rr cur
        JOIN hist_rr prev ON prev.symbol = cur.symbol AND prev.snapshot_date = :prior
        WHERE cur.snapshot_date = :d AND cur.outlook IS DISTINCT FROM prev.outlook
    """), {"d": d, "prior": prior}).fetchall()
    return len(rows)


def _derive_source_breadth_impl(session: Session, as_of_date: date, run_id) -> int:
    rows_out = []
    for source_code in SOURCES:
        table = {"RR": "hist_rr", "ETF": "hist_etf", "PS": "hist_ps",
                 "SSS": "hist_sss", "CALL": "hist_call"}[source_code]
        if source_code == "CALL":
            # Sparse 30-day standing source (see _call_window_counts) --
            # NOT the single-latest-date lookup the other four sources use.
            lb = _call_lookback_days(session)
            d, counts = _call_window_counts(session, as_of_date, lb)
            if d is None:
                continue
            flips = None
        else:
            d = _latest_snapshot(session, table, as_of_date)
            if d is None:
                continue
            if source_code == "RR":
                counts = _rr_bull_bear_counts(session, d)
                flips = _rr_flips(session, d)
            elif source_code == "ETF":
                counts = _etf_or_call_counts(session, table, d)
                flips = None
            else:
                # PS/SSS: single-sided lists (everything on the list counts
                # as a "bull"/long entry -- neither carries an explicit
                # polarity).
                n_total = session.execute(text(
                    f"SELECT COUNT(*) FROM {table} WHERE snapshot_date = :d"
                ), {"d": d}).scalar() or 0
                counts = {"n_bull": n_total, "n_bear": 0, "n_neutral": 0}
                flips = None
        n_total = counts["n_bull"] + counts["n_bear"] + counts["n_neutral"]
        rows_out.append({
            "as_of_date": as_of_date, "source_code": source_code,
            "snapshot_date": d, "n_bull": counts["n_bull"], "n_bear": counts["n_bear"],
            "n_neutral": counts["n_neutral"], "net": counts["n_bull"] - counts["n_bear"],
            "n_total": n_total, "flips_vs_prior": flips,
        })
    return replace_for_date(session, "drv_source_breadth", "as_of_date", as_of_date, rows_out)


derive_source_breadth = _wrap("drv_source_breadth", _derive_source_breadth_impl)


# ---------------------------------------------------------------------------
# drv_theme_stance
# ---------------------------------------------------------------------------

def _source_symbol_stance_map(session: Session, source_code: str, as_of_date: date) -> tuple:
    """Returns (snapshot_date, {symbol: 'B'|'S'|'N'}) for RR/ETF, or
    (snapshot_date, {symbol: 'B'}) for PS (single-sided -- everything on
    the list is a long idea). CALL does NOT go through here -- it's a
    sparse standing source, see _call_stance_window_map instead."""
    table = {"RR": "hist_rr", "ETF": "hist_etf", "PS": "hist_ps"}[source_code]
    d = _latest_snapshot(session, table, as_of_date)
    if d is None:
        return None, {}
    if source_code == "PS":
        rows = session.execute(text(
            "SELECT ticker FROM hist_ps WHERE snapshot_date = :d"
        ), {"d": d}).scalars().all()
        return d, {sym: "B" for sym in rows}
    rows = session.execute(text(
        f"SELECT symbol, outlook FROM {table} WHERE snapshot_date = :d"
    ), {"d": d}).fetchall()
    out = {}
    for sym, outlook in rows:
        o = (outlook or "").upper()
        out[sym] = "B" if o == "BULLISH" else "S" if o == "BEARISH" else "N"
    return d, out


def _call_stance_window_map(session: Session, as_of_date: date, lookback_days: int) -> tuple:
    """CALL variant of _source_symbol_stance_map -- CALL is a sparse
    standing source (see _call_window_counts), not a single-date lookup.
    Dedup per symbol to its most recent row in the window before mapping
    to B/S/N, same reasoning as the breadth-count fix above."""
    ceiling = position_ceiling(session, as_of_date)
    cutoff = ceiling - timedelta(days=lookback_days)
    latest_date = session.execute(text(
        "SELECT MAX(snapshot_date) FROM hist_call WHERE snapshot_date <= :ceil AND snapshot_date >= :cutoff"
    ), {"ceil": ceiling, "cutoff": cutoff}).scalar()
    if latest_date is None:
        return None, {}
    rows = session.execute(text("""
        SELECT DISTINCT ON (symbol) symbol, outlook
        FROM hist_call
        WHERE snapshot_date <= :ceil AND snapshot_date >= :cutoff
        ORDER BY symbol, snapshot_date DESC
    """), {"ceil": ceiling, "cutoff": cutoff}).fetchall()
    out = {}
    for sym, outlook in rows:
        o = (outlook or "").upper()
        out[sym] = "B" if o == "BULLISH" else "S" if o == "BEARISH" else "N"
    return latest_date, out


def _vote(stances: list) -> str:
    """B/S when >=2/3 of members with a directional stance agree; else M.
    stances: list of 'B'/'S'/'N'. Returns 'B'/'S'/'M'/'N' (no member with
    B/S at all and at least one N -> 'N'; truly no members -> caller uses
    '-' before calling this)."""
    directional = [s for s in stances if s in ("B", "S")]
    if not directional:
        return "N"
    n_b = directional.count("B")
    n_s = directional.count("S")
    total = len(directional)
    if n_b / total >= 2 / 3:
        return "B"
    if n_s / total >= 2 / 3:
        return "S"
    return "M"


def _theme_price_breadth(session: Session, as_of_date: date, axis_categories: list) -> tuple:
    """(pct, n_above, n_tracked) -- reuses the exact breadth query behind
    GET /api/actionable/quad-rotation (api/routers/dash.py::
    get_quad_rotation), summed across every (axis, category) the theme maps
    to. Returns (None, 0, 0) when the theme has no mapped category."""
    n_above = n_tracked = 0
    for axis, category in axis_categories:
        if axis == "style":
            row = session.execute(text("""
                SELECT COUNT(*) AS n_tracked,
                       COUNT(*) FILTER (WHERE t.last_price > t.a_trade_value
                                          AND t.last_price > t.a_trend_value) AS n_above
                FROM drv_macro_score ms
                JOIN drv_technicals t ON t.tos_symbol = ms.tos_symbol AND t.as_of_date = ms.as_of_date
                CROSS JOIN LATERAL jsonb_array_elements(COALESCE(ms.style_stances, '[]'::jsonb)) elem
                WHERE ms.as_of_date = :d AND elem->>'label' = :cat
            """), {"d": as_of_date, "cat": category}).mappings().first()
        else:
            col = "sector" if axis == "sector" else "asset_class"
            row = session.execute(text(f"""
                SELECT COUNT(*) AS n_tracked,
                       COUNT(*) FILTER (WHERE t.last_price > t.a_trade_value
                                          AND t.last_price > t.a_trend_value) AS n_above
                FROM drv_ma m
                JOIN drv_technicals t ON t.tos_symbol = m.tos_symbol AND t.as_of_date = m.as_of_date
                WHERE m.as_of_date = :d AND m.{col} = :cat
            """), {"d": as_of_date, "cat": category}).mappings().first()
        if row:
            n_above += int(row["n_above"] or 0)
            n_tracked += int(row["n_tracked"] or 0)
    if not axis_categories:
        return None, 0, 0
    pct = round(n_above / n_tracked * 100) if n_tracked else None
    return pct, n_above, n_tracked


def _theme_quad_says(quad_stance_map: dict, quad_keys: set) -> Optional[str]:
    if not quad_keys:
        return None
    stances = [quad_stance_map.get(k) for k in quad_keys if quad_stance_map.get(k)]
    if not stances:
        return None
    if len(set(stances)) == 1:
        return stances[0]
    n_bull = stances.count("BULLISH")
    n_bear = stances.count("BEARISH")
    if n_bull > n_bear:
        return "BULLISH"
    if n_bear > n_bull:
        return "BEARISH"
    return "NEUTRAL"


def _sss_theme_votes(session: Session, d: Optional[date]) -> dict:
    """theme -> list of 'B'/'S' votes, one per mapped sector, derived from
    that sector's own row-count vs its 13-week median (or 'new' -> bull) --
    reproduces the pattern in docs/mockups/market_read_one_picture_mockup
    .html's SSS column (e.g. Tech/software 'Software 10, top sector' B
    because 10 >= its own median; Defensives 'Staples 4 vs med 8' S because
    4 < its own median). Minor duplication of drv_sss_breadth's own
    row-count-vs-median logic (TASK_144) is deliberate -- this module stays
    self-contained per its own TASK_143 spec rather than depending on
    TASK_144's derive having already run in the same cascade pass."""
    if d is None:
        return {}
    cur = session.execute(text(
        "SELECT sector FROM hist_sss WHERE snapshot_date = :d"
    ), {"d": d}).scalars().all()
    counts: dict = {}
    for s in cur:
        sec = _normalize_sss_sector(s) or "Unclassified"
        counts[sec] = counts.get(sec, 0) + 1

    hist_dates = session.execute(text(
        "SELECT DISTINCT snapshot_date FROM hist_sss WHERE snapshot_date <= :d "
        "ORDER BY snapshot_date DESC LIMIT 14 OFFSET 1"
    ), {"d": d}).scalars().all()
    votes: dict = {}
    for sec, n in counts.items():
        theme = SSS_SECTOR_TO_THEME.get(sec)
        if not theme:
            continue
        hist_rows = session.execute(text(
            "SELECT sector FROM hist_sss WHERE snapshot_date = ANY(:dates)"
        ), {"dates": list(hist_dates)}).scalars().all() if hist_dates else []
        hist_n = sum(1 for s in hist_rows if (_normalize_sss_sector(s) or "Unclassified") == sec)
        med = hist_n / len(hist_dates) if hist_dates else None
        vote = "B" if (med is None or n >= med) else "S"
        votes.setdefault(theme, []).append(vote)
    return votes


def _derive_theme_stance_impl(session: Session, as_of_date: date, run_id) -> int:
    themes = session.execute(text(
        "SELECT DISTINCT theme FROM ref_symbol_theme ORDER BY theme"
    )).scalars().all()
    themes = list(themes) + [t for t in SSS_SECTOR_TO_THEME.values() if t not in themes]

    rr_d, rr_map = _source_symbol_stance_map(session, "RR", as_of_date)
    etf_d, etf_map = _source_symbol_stance_map(session, "ETF", as_of_date)
    ps_d, ps_map = _source_symbol_stance_map(session, "PS", as_of_date)
    call_d, call_map = _call_stance_window_map(session, as_of_date, _call_lookback_days(session))
    sss_d = _latest_snapshot(session, "hist_sss", as_of_date)
    sss_votes = _sss_theme_votes(session, sss_d)

    members_by_theme = session.execute(text(
        "SELECT theme, source_code, symbol, inverted, quad_category, quad_sub_category "
        "FROM ref_symbol_theme ORDER BY theme"
    )).mappings().all()
    theme_members: dict = {}
    for r in members_by_theme:
        theme_members.setdefault(r["theme"], []).append(r)

    quad_stance_map = compute_quad_monthly_stance(session, as_of_date)

    # trend_1w/4w: compare today's stance to the stance 5/20 anchor dates ago.
    prior_stances = {}
    for label, back in (("1w", 5), ("4w", 20)):
        prior_date = session.execute(text(
            "SELECT as_of_date FROM drv_theme_stance WHERE as_of_date < :d "
            "ORDER BY as_of_date DESC OFFSET :off LIMIT 1"
        ), {"d": as_of_date, "off": back - 1}).scalar()
        prior_stances[label] = {}
        if prior_date:
            rows = session.execute(text(
                "SELECT theme, stance FROM drv_theme_stance WHERE as_of_date = :d"
            ), {"d": prior_date}).fetchall()
            prior_stances[label] = {t: s for t, s in rows}

    rows_out = []
    for theme in themes:
        members = theme_members.get(theme, [])
        cells = {}
        for src, smap, snap_d in (("rr", rr_map, rr_d), ("etf", etf_map, etf_d),
                                    ("ps", ps_map, ps_d), ("call", call_map, call_d)):
            src_code = src.upper()
            stances = []
            member_detail = []
            for m in members:
                if m["source_code"] != src_code:
                    continue
                st = smap.get(m["symbol"])
                if st is None:
                    continue
                if m["inverted"] and st in ("B", "S"):
                    st = "S" if st == "B" else "B"
                stances.append(st)
                member_detail.append({"symbol": m["symbol"], "stance": st})
            cells[src] = {"vote": _vote(stances) if stances else "-", "members": member_detail}

        sss_stances = sss_votes.get(theme, [])
        cells["sss"] = {"vote": _vote(sss_stances) if sss_stances else "-", "members": []}

        axis_categories = THEME_CATEGORY_MAP.get(theme, [])
        price_pct, n_above, n_tracked = _theme_price_breadth(session, as_of_date, axis_categories)

        quad_keys = {(m["quad_category"], m["quad_sub_category"]) for m in members
                     if m["quad_category"] and m["quad_sub_category"]}
        quad_says = _theme_quad_says(quad_stance_map, quad_keys)

        voting = [cells["rr"]["vote"], cells["etf"]["vote"], cells["ps"]["vote"], cells["sss"]["vote"]]
        directional = [v for v in voting if v in ("B", "S")]
        stance = _vote(directional) if directional else "N"
        agree_n = directional.count(stance) if stance in ("B", "S") else 0

        quad_conflict = bool(quad_says and stance in ("B", "S")
                              and quad_says != "NEUTRAL"
                              and ((stance == "B" and quad_says == "BEARISH")
                                   or (stance == "S" and quad_says == "BULLISH")))

        def _trend(label):
            prior = prior_stances[label].get(theme)
            if prior is None or prior == stance:
                return "flat" if prior == stance else None
            order = {"S": -1, "N": 0, "M": 0, "B": 1}
            return "up" if order.get(stance, 0) > order.get(prior, 0) else "down"

        rows_out.append({
            "as_of_date": as_of_date, "theme": theme,
            "rr": cells["rr"]["vote"], "etf": cells["etf"]["vote"],
            "ps": cells["ps"]["vote"], "sss": cells["sss"]["vote"], "call": cells["call"]["vote"],
            "price_pct": price_pct, "price_n_above": n_above, "price_n_tracked": n_tracked,
            "stance": stance, "agree_n": agree_n,
            "trend_1w": _trend("1w"), "trend_4w": _trend("4w"),
            "quad_says": quad_says, "quad_conflict": quad_conflict,
            "members": {k: v["members"] for k, v in cells.items()},
        })

    return replace_for_date(session, "drv_theme_stance", "as_of_date", as_of_date, rows_out)


derive_theme_stance = _wrap("drv_theme_stance", _derive_theme_stance_impl)


def derive_market_read(session: Session, as_of_date: date, parent_run_id=None) -> dict:
    """Convenience entrypoint for derive_all() -- runs both tables in order."""
    n1 = derive_source_breadth(session, as_of_date, parent_run_id)
    n2 = derive_theme_stance(session, as_of_date, parent_run_id)
    return {"drv_source_breadth": n1, "drv_theme_stance": n2}
