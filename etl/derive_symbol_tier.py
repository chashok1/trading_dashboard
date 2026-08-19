"""
drv_symbol_tier — daily export-frequency tier per symbol.

2026-08-18, user-directed design (TOS-export right-sizing analysis, no task
number). Answers "how often does this symbol need fresh data" so the TOS/
Yfinance export automation can eventually export Tier 1 daily and Tier 2
weekly instead of exporting everything daily regardless of relevance.

Universe: ref_my_stocks WHERE active='Y' (the user's curated tracking
list), unioned with currently-held positions AND dashboard-dependency
symbols (see reason 4 below) as safety nets -- NOT raw drv_symbols, which
is every symbol ANY feed (including Hedgeye-only mentions) has ever
mentioned, curated or not. Using drv_symbols directly was tried first and
reverted (2026-08-18) -- it kept resurrecting symbols the user had already
deliberately deleted from ref_my_stocks as "needs adding to Tier 1".

tier=1 if ANY of these are true (checked in this priority order --
whichever fires first becomes `reason`):
  0. user_pinned         — ref_my_stocks.sticky_tier1='Y'. 2026-08-18: "i
                           want to have a list my own symbols to be added
                           to tier1 (they are going to be sticky) so i can
                           see them always regardless of HE" -- the user's
                           own explicit override, checked first, ahead of
                           every automatic/derived reason below.
  1. held               — a real position right now (hist_cs/hist_f, latest
                           snapshot <= D, qty <> 0), EXCLUDING hist_f rows
                           from employer retirement-plan accounts (e.g.
                           "BOEING 401(K)", account_name ILIKE '%401%') --
                           those hold plan-internal fund codes (NON40O26D
                           etc.) that are real positions but not TOS-
                           tradable instruments, so they'd never actually
                           import into a watchlist. See _fetch_held().
  2. active_90d          — drv_actionable.consolidated_action was non-blank
                           for this symbol on any date in [D-90, D].
  3. hedgeye_90d         — ANY Hedgeye call/stance/side/outlook in
                           [D-90, D], across hist_call, hist_hedgeye_stance,
                           hist_call_top5, hist_rta, hist_etfchg, hist_rr --
                           including NEUTRAL (2026-08-18: was directional-
                           only, i.e. BULLISH/BEARISH/long/short, excluding
                           NEUTRAL; user asked "add neutrals to tier 1 list
                           also" after finding AMD -- 6 straight NEUTRAL
                           calls, no other qualifying reason -- sitting in
                           Tier 2. Renamed from hedgeye_directional_90d
                           since it's no longer strictly directional.
                           hist_rta/hist_etfchg have no neutral value in
                           their vocabulary today (checked: only long/
                           short), so their predicates are unchanged;
                           hist_call/hist_call_top5/hist_rr all do and now
                           include it). hist_sss_change is deliberately
                           still excluded — its 'action' column is add/
                           remove list membership, not a stance at all.
  4. dashboard_dependency — a symbol a dashboard PANEL depends on to
                           function, independent of whether the user
                           personally trades it (index/benchmark/risk-gauge
                           inputs). 2026-08-18: user asked "make sure the
                           indexes and symbols used anywhere in the app are
                           part of tier 1" -- computed LIVE each run (not a
                           hardcoded list, so it can't drift out of sync)
                           from the same tables/constants those panels
                           already read: ref_market_metric's 'tos:'-adapter
                           entries, ref_macro_area's member_symbol (mini-
                           tape + macro rail), _SECTOR_ETF
                           (api/routers/macro_areas.py), and
                           _ASSET_CLASS_ETF/_STYLE_ETF
                           (etl/derive_category_perf.py, factor scorecard
                           benchmarks). Excludes symbols with no real TOS-
                           tradable form (FRED-only keys like DGS2:FRED,
                           market-internals $ADVN/$DECN/$UVOL/$DVOL which
                           live in hist_internals with no tos_symbol column
                           at all, ^VIX9D fetched directly via yfinance) --
                           those already have their own always-fresh feed
                           outside the TOS-watchlist path, so forcing them
                           onto a generated watchlist wouldn't help and (for
                           the FRED/internals ones) isn't even a symbol TOS
                           would recognize on import.
  5. special_format      — the symbol contains ':', '/', or '=' (see
                           _SPECIAL_CHARS). User: "make sure all important
                           stocks are in tier 1 (indexes, currencies,
                           sectors, the ones with special chars)" -- a
                           non-standard format is itself a signal the
                           symbol is an index/futures/currency/RR-
                           benchmark, not a plain equity, even if it isn't
                           wired into any of the dashboard_dependency
                           sources above. Only applies to symbols already
                           in the universe (curated/held/dashboard-
                           dependency) -- doesn't pull in anything new.
Else tier=2, reason='dormant'.

Idempotent: DELETE WHERE as_of_date=D then INSERT. Purely descriptive
today — nothing yet reads this table to change TOS export behavior; that's
a separate, later piece (see conversation this was designed in).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from etl._derive_common import _wrap
from etl.db import replace_for_date

log = logging.getLogger(__name__)

ACTIVE_WINDOW_DAYS = 90

# 2026-08-18: symbols carrying one of these are, by their format alone,
# an index/futures/currency/RR-benchmark rather than a plain equity --
# futures (/GC, /BTC), RR-index codes (TNX:CGI, MOVE:GIF), spot forex
# (USD/JPY). See reason 5 below.
_SPECIAL_CHARS = (":", "/", "=")

# Hedgeye tables that carry some notion of stance -- ANY stance now
# qualifies, including NEUTRAL (2026-08-18, see reason 3 above). Each
# entry: (table, date_column, has_a_stance_predicate). hist_hedgeye_stance
# has no neutral value at all (always a real stance), so its predicate is
# just TRUE. hist_rta/hist_etfchg have no neutral value in their
# vocabulary (checked live: only long/short) -- nothing to add there.
_HEDGEYE_SOURCES = [
    ("hist_call", "snapshot_date", "UPPER(outlook) IN ('BULLISH', 'BEARISH', 'NEUTRAL')"),
    ("hist_hedgeye_stance", "snapshot_date", "TRUE"),
    ("hist_call_top5", "snapshot_date", "LOWER(side) IN ('long', 'short', 'neutral')"),
    ("hist_rta", "snapshot_date", "LOWER(side) IN ('long', 'short')"),
    ("hist_etfchg", "event_date", "LOWER(outlook) IN ('long', 'short')"),
    ("hist_rr", "snapshot_date", "UPPER(outlook) IN ('BULLISH', 'BEARISH', 'NEUTRAL')"),
]


def _fetch_held(session: Session, d: date) -> set:
    # hist_f's account_name != '401%' exclusion (2026-08-18): employer
    # retirement-plan accounts (e.g. "BOEING 401(K)") hold plan-internal
    # fund codes (NON40O26D = "TARGET DATE 2035", NON40PGVY = "BOND FUND",
    # etc.) that are real positions but NOT TOS-tradable instruments --
    # zero hist_td history ever, and never will have any, since they're
    # proprietary record-keeper fund units, not exchange-traded securities.
    # They stay correctly "held" for portfolio-value purposes wherever else
    # hist_f is read; excluded ONLY from this tier universe, whose purpose
    # is specifically TOS-watchlist export cadence. Deliberately NOT a
    # blanket "no hist_td history" filter -- that would also wrongly
    # exclude real holdings that just aren't on a TOS watchlist yet (e.g.
    # CRAK/IGV/INTU/NOBL/SMDV, found sitting in this exact state), which is
    # precisely the case this tier table exists to catch and fix.
    rows = session.execute(text("""
        SELECT DISTINCT symbol FROM hist_cs
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_cs WHERE snapshot_date <= :d)
          AND qty <> 0
        UNION
        SELECT DISTINCT symbol FROM hist_f
        WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM hist_f WHERE snapshot_date <= :d)
          AND qty <> 0
          AND (account_name IS NULL OR account_name NOT ILIKE '%401%')
    """), {"d": d}).fetchall()
    return {r[0] for r in rows if r[0]}


def _fetch_active_90d(session: Session, d: date) -> set:
    rows = session.execute(text("""
        SELECT DISTINCT tos_symbol FROM drv_actionable
        WHERE as_of_date BETWEEN :start AND :d
          AND consolidated_action IS NOT NULL AND consolidated_action <> ''
    """), {"start": d - timedelta(days=ACTIVE_WINDOW_DAYS), "d": d}).fetchall()
    return {r[0] for r in rows if r[0]}


def _fetch_hedgeye_90d(session: Session, d: date) -> set:
    start = d - timedelta(days=ACTIVE_WINDOW_DAYS)
    out: set = set()
    for table, date_col, predicate in _HEDGEYE_SOURCES:
        rows = session.execute(text(f"""
            SELECT DISTINCT tos_symbol FROM {table}
            WHERE {date_col} BETWEEN :start AND :d
              AND tos_symbol IS NOT NULL
              AND ({predicate})
        """), {"start": start, "d": d}).fetchall()
        out.update(r[0] for r in rows if r[0])
    return out


# 2026-08-18: user-confirmed important indexes/instruments that aren't
# wired into any of the queried panel tables/constants below (so the live
# scan can't find them on its own) -- HSI:HK (Hang Seng), /NKD (Nikkei
# futures, distinct product from N225:JP's cash index), USD/JPY (spot
# forex, distinct product from the /6J futures contract). Manually
# maintained precisely because these are real exceptions, not a category
# with its own source-of-truth table -- add here if the user confirms
# another one-off the same way.
_MANUAL_DASHBOARD_SYMBOLS = {"HSI:HK", "/NKD", "USD/JPY"}

# 2026-08-18: dashboard-dependency symbols confirmed by the user's own live
# TOS session to have no real TOS-tradable form -- "TOS is not loading data
# for these". $SSEC is a real, currently-live dashboard row (ref_macro_area
# 'country_etfs', Yahoo-sourced price still works fine) so disabling that
# row would break a working panel; excluded HERE instead, from tier-1
# eligibility only, same rationale as the FRED-key/internals/VIX9D
# exclusions above just empirically confirmed per-symbol instead of by
# category. Add here (not deactivate ref_my_stocks/disable the source
# table) for any future symbol that's a legitimate dashboard dependency
# but confirmed non-TOS-loadable.
_MANUAL_EXCLUDED_SYMBOLS = {"$SSEC"}


def _fetch_dashboard_dependency(session: Session) -> set:
    """Symbols dashboard panels depend on regardless of whether the user
    personally trades them. Computed live from the same tables/constants
    those panels already read -- see module docstring reason 4."""
    out: set = set(_MANUAL_DASHBOARD_SYMBOLS)

    out.update(r[0] for r in session.execute(text("""
        SELECT DISTINCT substring(elem FROM 5) FROM ref_market_metric,
            jsonb_array_elements_text(source_priority) AS elem
        WHERE enabled AND elem LIKE 'tos:%'
    """)).fetchall() if r[0])

    out.update(r[0] for r in session.execute(text("""
        SELECT DISTINCT member_symbol FROM ref_macro_area
        WHERE enabled AND member_symbol NOT LIKE :fred_pattern
    """), {"fred_pattern": "%" + ":FRED"}).fetchall() if r[0])

    # Python-side constants -- shared source of truth with the panels that
    # already import these (api/routers/macro_areas.py's own breadth panel,
    # etl/derive_category_perf.py's factor scorecard). Imported here rather
    # than duplicated so this set can't drift from what those panels use.
    from api.routers.macro_areas import _SECTOR_ETF
    from etl.derive_category_perf import _ASSET_CLASS_ETF, _STYLE_ETF

    out.update(v for v in _SECTOR_ETF.values() if v)  # 'Country ETF': None -- no benchmark
    for v in _ASSET_CLASS_ETF.values():
        if isinstance(v, tuple):
            out.update(v)
        elif v:
            out.add(v)
    out.update(v for v in _STYLE_ETF.values() if v)

    out -= _MANUAL_EXCLUDED_SYMBOLS
    return out


def _fetch_user_pinned(session: Session) -> set:
    rows = session.execute(text(
        "SELECT tos_symbol FROM ref_my_stocks WHERE active = 'Y' AND sticky_tier1 = 'Y'"
    )).fetchall()
    return {r[0] for r in rows if r[0]}


def _derive_symbol_tier_impl(session: Session, as_of_date: date, run_id: int) -> int:
    held = _fetch_held(session, as_of_date)
    dashboard_dependency = _fetch_dashboard_dependency(session)
    user_pinned = _fetch_user_pinned(session)

    # 2026-08-18 fix: universe is the user's curated ref_my_stocks list
    # (active='Y'), NOT raw drv_symbols -- drv_symbols is every symbol ANY
    # feed ever mentioned (including Hedgeye-only mentions the user has
    # since deliberately deleted from ref_my_stocks), so using it directly
    # kept resurrecting already-deleted junk as "needs adding to Tier 1".
    # held and dashboard_dependency are unioned in as safety nets (a
    # position, or a symbol a dashboard panel depends on, should always be
    # tracked even if missing from ref_my_stocks). user_pinned is already
    # a subset of curated (sticky_tier1 rows are also active='Y' rows in
    # the same table) -- unioned anyway for clarity/robustness.
    curated = {r[0] for r in session.execute(
        text("SELECT tos_symbol FROM ref_my_stocks WHERE active = 'Y'")
    ).fetchall()}
    universe = sorted(curated | held | dashboard_dependency | user_pinned)
    if not universe:
        return replace_for_date(session, "drv_symbol_tier", "as_of_date", as_of_date, [])

    active_90d = _fetch_active_90d(session, as_of_date)
    hedgeye_90d = _fetch_hedgeye_90d(session, as_of_date)

    out_rows = []
    for sym in universe:
        if sym in user_pinned:
            tier, reason = 1, "user_pinned"
        elif sym in held:
            tier, reason = 1, "held"
        elif sym in active_90d:
            tier, reason = 1, "active_90d"
        elif sym in hedgeye_90d:
            tier, reason = 1, "hedgeye_90d"
        elif sym in dashboard_dependency:
            tier, reason = 1, "dashboard_dependency"
        elif any(c in sym for c in _SPECIAL_CHARS):
            tier, reason = 1, "special_format"
        else:
            tier, reason = 2, "dormant"
        out_rows.append({
            "as_of_date": as_of_date,
            "tos_symbol": sym,
            "tier": tier,
            "reason": reason,
        })

    return replace_for_date(session, "drv_symbol_tier", "as_of_date", as_of_date, out_rows)


derive_symbol_tier = _wrap("drv_symbol_tier", _derive_symbol_tier_impl)
