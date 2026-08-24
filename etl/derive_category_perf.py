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
# 2026-08-08 -- MTD/QTD/YTD are CALENDAR-boundary windows (first trading day
# of the month/quarter/year through D), not a fixed trading-day count like
# WINDOWS -- their day-count varies by as_of_date (YTD in December needs
# ~250 trading days; in January needs ~1). YTD_CALENDAR_DAYS widens the
# initial calendar fetch (see _derive_category_perf_impl) so a late-year D
# still has enough history for a true YTD baseline; early in the dataset's
# own history (or early in a year) it clamps gracefully to "since inception"
# via _window_days_since below rather than returning None.
YTD_CALENDAR_DAYS = 260
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
    # 2026-08-10 -- Fixed Income switched from TLT (generic 20+yr Treasury
    # proxy, NOT held, duration/volatility mismatch vs the actual sleeve) to
    # an equal-weighted blend of the actual held FI positions -- user:
    # "for fixed income, can you use three BUXX, CLOX, CLOZ?" (confirmed:
    # blend, not a single pick, despite this meaning the "benchmark" is no
    # longer independent of holdings -- see _bench_return's tuple handling).
    # AGG/BND/SHV/BIL/JAAA have no drv_quote history in this system.
    "Fixed Income": ("BUXX", "CLOX", "CLOZ"),
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

# 2026-08-09 -- account-scoped variants (Cockpit Accounts filter, "how are
# you deciding on VERDICT outcomes?" -> "why can't you calculate Today/MTD/
# QTD by account?"): CS's account column and F's account_number column both
# store the same domain as ref_accounts.account_number directly (confirmed
# live -- every other account-scoped query in this codebase, e.g.
# api/routers/cockpit.py::_yesterday_by_symbol_account, joins ref_accounts
# ON ra.account_number = hist_cs.account with no translation), so a single
# `accounts` list of account_number strings filters both sources uniformly.
# TWR/flows math itself is account-agnostic -- _build_series/
# _eod_actual_change aggregate whatever positions/flows come in, grouped
# by category, with no portfolio-wide
# assumption baked in -- so filtering the INPUT to one account's rows here
# is sufficient; nothing downstream needs to change to get a correct
# per-account TWR, not just a per-account $ total.
def _acct_clause(accounts: Optional[list], cs_col: str = "account", f_col: str = "account_number") -> tuple[str, str]:
    """Returns (cs_clause, f_clause) SQL fragments -- empty strings when
    accounts is None/empty (unfiltered, today's existing portfolio-wide
    behavior, byte-identical query)."""
    if not accounts:
        return "", ""
    return f" AND {cs_col} = ANY(:accounts)", f" AND {f_col} = ANY(:accounts)"


def _positions_sql(accounts: Optional[list] = None):
    cs_acct, f_acct = _acct_clause(accounts)
    return text(f"""
        SELECT snapshot_date, tos_symbol, symbol, security_type AS sec_type,
               description, market_value AS mv, qty, 'CS' AS src
        FROM hist_cs WHERE snapshot_date BETWEEN :lo AND :hi
          AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
          {cs_acct}
        UNION ALL
        SELECT snapshot_date, tos_symbol, symbol, type AS sec_type,
               description, current_value AS mv, qty, 'F' AS src
        FROM hist_f WHERE snapshot_date BETWEEN :lo AND :hi
          AND account_number NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
          {f_acct}
    """)


def _flows_sql(accounts: Optional[list] = None):
    cs_acct, f_acct = _acct_clause(accounts)
    return text(f"""
        SELECT trade_date, tos_symbol, action, amount, 'CST' AS src
        FROM hist_cst WHERE trade_date BETWEEN :lo AND :hi
          AND (UPPER(COALESCE(action,'')) LIKE '%BUY%' OR UPPER(COALESCE(action,'')) LIKE '%SELL%')
          {cs_acct}
        UNION ALL
        SELECT trade_date, tos_symbol, action_kind AS action, amount, 'FT' AS src
        FROM hist_ft WHERE trade_date BETWEEN :lo AND :hi
          AND (UPPER(COALESCE(action_kind,'')) LIKE '%BUY%' OR UPPER(COALESCE(action_kind,'')) LIKE '%SELL%')
          {f_acct}
    """)


# Broad (ANY action) flow-dates query, used only for gap DETECTION -- not for
# netflow math. A Buy/Sell isn't the only legitimate reason a qty can change
# (Stock Split, Reinvest Shares, Reinvest Dividend all move qty too); any row
# at all on that date for that symbol is enough to explain the change. See
# _build_series' gap-detection block and DEV_HANDOFF.md (round 2 / Part A).
def _any_flow_dates_sql(accounts: Optional[list] = None):
    cs_acct, f_acct = _acct_clause(accounts)
    return text(f"""
        SELECT DISTINCT trade_date, tos_symbol FROM hist_cst
        WHERE trade_date BETWEEN :lo AND :hi AND tos_symbol IS NOT NULL {cs_acct}
        UNION
        SELECT DISTINCT trade_date, tos_symbol FROM hist_ft
        WHERE trade_date BETWEEN :lo AND :hi AND tos_symbol IS NOT NULL {f_acct}
    """)


def _load_positions_and_flows(session: Session, lo: date, hi: date,
                              accounts: Optional[list] = None) -> tuple[list, list]:
    params = {"lo": lo, "hi": hi, "accounts": accounts}
    positions = session.execute(_positions_sql(accounts), params).mappings().all()
    flows = session.execute(_flows_sql(accounts), params).mappings().all()
    return list(positions), list(flows)


def _load_any_flow_dates(session: Session, lo: date, hi: date,
                         accounts: Optional[list] = None) -> dict:
    """{tos_symbol: {trade_date, ...}} for ANY hist_cst/hist_ft row (any
    action) in the window -- used only to tell whether a qty change on a
    given date is explained by *some* transaction row, not to compute
    netflow amounts."""
    rows = session.execute(_any_flow_dates_sql(accounts), {"lo": lo, "hi": hi, "accounts": accounts}).all()
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
    truly-unmapped symbols get a style "Unmapped" bucket.

    2026-08-08 -- sector/style are equity-only axes: GICS sector on a bond/
    commodity/gold/crypto/FX ETF is a data-vendor artifact of the *issuer*
    (e.g. bond ETFs EMB/HYG/IEF/JNK/CLOX/CLOZ/BUXX tag sector="Financials",
    gold/commodity ETFs tag "Materials", crypto ETFs tag "Information
    Technology"/"Digital Assets") -- not a real equity-sector exposure, and
    _classify_style's beta/PE/div-yield inputs are equally meaningless for a
    non-equity instrument. Both axes now require asset_class == "Equities"
    (an explicitly-known NON-equity asset_class excludes; unknown/NULL
    asset_class does not -- some real equities have no asset_class tag but
    a valid sector, see the DESK/IPAY docstring note above, and must keep
    resolving normally). Sector routes the excluded dollars to a SEPARATE
    "Non-Equity (excluded)" category, not "Unmapped" (2026-08-08 follow-up:
    lumping the two made "Unmapped" mostly non-equity noise -- e.g. 75% of
    one portfolio's sector-Unmapped $ was actually gold/bond ETFs that were
    never supposed to resolve to a GICS sector, drowning out the small
    genuine-gap portion. Still exhaustive-partition safe -- same dollar-drop
    concern as the DESK/IPAY fix above -- just a distinct bucket so
    "Unmapped" means only genuine classification gaps; the API layer
    (api/routers/cockpit.py::get_factor_scorecard) drops this category from
    the response entirely, so it never reaches the grid/chart). Style
    returns no tags at all for non-equity (same as a mapped equity with
    genuinely zero qualifying tags -- not a gap, just not counted -- style
    has no analogous "Non-Equity (excluded)" bucket since it was never
    lumped into style's Unmapped to begin with)."""
    info = cat_map.get(symbol_key)
    if info is None:
        return ["Unmapped"] if axis != "style" else []
    non_equity = info["asset_class"] is not None and info["asset_class"] != "Equities"
    if axis == "sector":
        if non_equity:
            return ["Non-Equity (excluded)"]
        return [info["sector"]] if info["sector"] else ["Unmapped"]
    if axis == "asset_class":
        return [info["asset_class"]] if info["asset_class"] else ["Unmapped"]
    if axis == "style":
        if info["source"] == "unmapped":
            return ["Unmapped"]
        if non_equity:
            return []
        return list(info["styles"])  # empty list = valid "no style tags" (not an Unmapped case)
    return []


def _today_marked_to_market(session: Session, positions: list, cat_map: dict,
                             cash_keys: set, calendar: list) -> dict:
    """2026-08-08 -- INTRADAY-ONLY 'Today' preview, computed by marking
    YESTERDAY's (calendar[-2], the last FINALIZED F/CS position snapshot)
    share counts to TODAY's (calendar[-1]) LIVE price via drv_quote,
    instead of diffing two F/CS snapshots the way every other window does.
    Rationale: Schwab/Fidelity only export F/CS once a day (EOD), so mid-
    trading-day the anchor date's own F/CS snapshot doesn't exist yet --
    diffing against it (or querying its day_chng_dollar/today_gl_dollar,
    see _eod_actual_change) returns nothing. Freezing yesterday's shares
    and re-pricing them off drv_quote (which DOES tick intraday from TL
    loads, same source _bench_return already uses for bench_today) gives
    real intraday movement during market hours and naturally settles to
    exactly 0 outside them, with no special-casing needed: when drv_quote
    hasn't ticked past yesterday's close yet, today's price falls back to
    yesterday's and the marked value is unchanged. User-requested design
    (2026-08-08): "is today going to be calculated based on loads during
    market hours?" -> "yes, build it".

    2026-08-23 -- demoted from twr_today's ONLY source to its INTRADAY
    fallback only: once the anchor date's own EOD hist_cs/hist_f snapshot
    lands, _eod_actual_change(offset=0) takes over (the broker-actual
    figure, not this live-tick approximation) -- see the
    today_snapshot_exists gate around the EXTRA_WINDOWS loop below. This
    function alone used to be twr_today's whole story, which meant it
    never reflected the settled EOD gain even after market close (see
    _eod_actual_change's docstring for the "+$6,871 showed as 0" bug that
    motivated the split). User, after that fix removed live-updating
    intraday visibility entirely: "what does it show in middle of trading
    day?" -> restored as the intraday-only fallback (hybrid, recommended
    option).

    Returns {axis: {category: twr_or_None}}; None when the baseline value
    is 0 (nothing held) or no price data exists at all."""
    out = {axis: {} for axis in ("sector", "asset_class", "style")}
    if len(calendar) < 2:
        return out
    d_prev, d_today = calendar[-2], calendar[-1]

    qty_by_symbol: dict = {}
    for p in positions:
        if p["snapshot_date"] != d_prev:
            continue
        key = p["tos_symbol"] or p["symbol"]
        if key in cash_keys:
            continue
        qty_by_symbol[key] = qty_by_symbol.get(key, 0.0) + float(p["qty"] or 0.0)
    if not qty_by_symbol:
        return out

    syms = list(qty_by_symbol.keys())
    price_rows = session.execute(text(
        "SELECT tos_symbol, as_of_date, last_price FROM drv_quote "
        "WHERE tos_symbol = ANY(:syms) AND as_of_date IN (:a, :b)"
    ), {"syms": syms, "a": d_prev, "b": d_today}).mappings().all()
    price_map: dict = {}
    for r in price_rows:
        price_map.setdefault(r["tos_symbol"], {})[r["as_of_date"]] = float(r["last_price"] or 0.0)

    totals: dict = {axis: {} for axis in ("sector", "asset_class", "style")}
    for sym, qty in qty_by_symbol.items():
        prices = price_map.get(sym, {})
        p_prev = prices.get(d_prev)
        if p_prev is None:
            continue  # no baseline price -- can't mark this symbol at all
        p_today = prices.get(d_today, p_prev)  # no new tick yet -> flat vs yesterday's close
        v_prev_sym = qty * p_prev
        v_today_sym = qty * p_today
        for axis in ("sector", "asset_class", "style"):
            for cat in _categories_for(sym, cat_map, axis):
                bucket = totals[axis].setdefault(cat, {"today": 0.0, "prev": 0.0})
                bucket["today"] += v_today_sym
                bucket["prev"] += v_prev_sym

    for axis, cats in totals.items():
        for cat, vals in cats.items():
            out[axis][cat] = (vals["today"] - vals["prev"]) / vals["prev"] if vals["prev"] else None
    return out


def _eod_actual_change(session: Session, calendar: list, cat_map: dict,
                        cash_keys: set, accounts: Optional[list] = None,
                        offset: int = 1) -> dict:
    """2026-08-08 -- '$ change for one EOD-settled trading day, replacing
    the old mv-diff + 25%-swing-guard approach entirely. User's own
    diagnosis: hist_cs/hist_f already carry the broker's own daily
    gain/loss per position (day_chng_dollar / today_gl_dollar) -- correct
    as-is for an unchanged qty (pure price move) AND for a same-day new buy
    (broker reports ~$0 against a same-day cost basis, exactly the "don't
    count new money as a gain" behavior the old guard was clumsily trying
    to approximate). The ONE case that figure misses: broker day-change
    only reflects shares STILL HELD at end of day, so a full or partial
    SELL that day drops the sold portion's own intraday move (prior close
    -> sale price) -- recovered here from that day's hist_cst/hist_ft
    transaction row, same (sale_price - prior_close) * qty pattern already
    used by api/routers/dash.py's portfolio-summary "Today's Gain"
    (cs_sold_move). No guard needed anymore -- every number here is
    actually computed, not estimated-then-clamped.

    offset=1 (the original "yesterday" case) reads calendar[-2]/[-3];
    offset=0 reads calendar[-1]/[-2] -- i.e. the anchor date D itself.

    2026-08-23 -- offset=0 added: twr_today now uses this (broker-EOD-
    actual) once the anchor date's own hist_cs/hist_f snapshot has
    actually landed, instead of staying on _today_marked_to_market's
    live-tick mark forever -- that live version froze at 0 once the
    market closed for the day, so the anchor date's own FINAL settled
    gain never showed up under either "Today" (stale 0) or "Yest" (a
    different, earlier day). Confirmed live: anchor day's broker gain was
    +$6,871 while the grid showed twr_today=0 for every category. User:
    "check the data for yesterday. all showing as reds in reality +6.9k."
    -> root-caused to twr_today's live-tick design -> "yes, make that
    change". Follow-up ("what does it show in middle of trading day?")
    surfaced that hist_cs/hist_f for D don't exist until EOD, so this
    function alone returns no data all day -- see the today_snapshot_exists
    gate around the EXTRA_WINDOWS loop below, which keeps
    _today_marked_to_market as the INTRADAY-ONLY fallback (live preview
    while D's own snapshot hasn't landed yet) and switches to this
    function the moment it has.

    Returns {axis: {category: dollar_change}}; category keys with no
    contributing symbol are simply absent (treated as 0/no-data by the
    caller)."""
    out = {axis: {} for axis in ("sector", "asset_class", "style")}
    if len(calendar) < 2 + offset:
        return out
    d, prior = calendar[-(1 + offset)], calendar[-(2 + offset)]
    excl_cs = " AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)"
    excl_f = " AND account_number NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)"
    cs_acct, f_acct = _acct_clause(accounts)
    excl_cs += cs_acct
    excl_f += f_acct
    p = {"d": d, "accounts": accounts}
    pp_ = {"d": prior, "accounts": accounts}

    dc_by_sym: dict = {}
    for r in session.execute(text(
        "SELECT tos_symbol, symbol, SUM(day_chng_dollar) AS dc FROM hist_cs"
        " WHERE snapshot_date=:d" + excl_cs + " GROUP BY tos_symbol, symbol"
    ), p).mappings().all():
        key = r["tos_symbol"] or r["symbol"]
        dc_by_sym[key] = dc_by_sym.get(key, 0.0) + float(r["dc"] or 0)
    for r in session.execute(text(
        "SELECT tos_symbol, symbol, SUM(today_gl_dollar) AS dc FROM hist_f"
        " WHERE snapshot_date=:d" + excl_f + " GROUP BY tos_symbol, symbol"
    ), p).mappings().all():
        key = r["tos_symbol"] or r["symbol"]
        dc_by_sym[key] = dc_by_sym.get(key, 0.0) + float(r["dc"] or 0)

    # Prior-day close prices, needed only for the sold-shares adjustment.
    prior_px: dict = {}
    for r in session.execute(text(
        "SELECT tos_symbol, symbol, price FROM hist_cs WHERE snapshot_date=:d" + excl_cs
    ), pp_).mappings().all():
        if r["price"] is not None:
            prior_px[r["tos_symbol"] or r["symbol"]] = float(r["price"])
    for r in session.execute(text(
        "SELECT tos_symbol, symbol, last_price FROM hist_f WHERE snapshot_date=:d" + excl_f
    ), pp_).mappings().all():
        if r["last_price"] is not None:
            prior_px.setdefault(r["tos_symbol"] or r["symbol"], float(r["last_price"]))

    for r in session.execute(text(
        "SELECT tos_symbol, symbol, price, quantity FROM hist_cst"
        " WHERE trade_date=:d AND UPPER(COALESCE(action,'')) LIKE '%SELL%'"
        "   AND quantity IS NOT NULL AND price IS NOT NULL" + excl_cs
    ), p).mappings().all():
        key = r["tos_symbol"] or r["symbol"]
        pp = prior_px.get(key)
        if pp is None:
            continue
        dc_by_sym[key] = dc_by_sym.get(key, 0.0) + (float(r["price"]) - pp) * abs(float(r["quantity"]))
    for r in session.execute(text(
        "SELECT tos_symbol, symbol, price, quantity FROM hist_ft"
        " WHERE trade_date=:d AND action_kind='SELL'"
        "   AND quantity IS NOT NULL AND price IS NOT NULL" + excl_f
    ), p).mappings().all():
        key = r["tos_symbol"] or r["symbol"]
        pp = prior_px.get(key)
        if pp is None:
            continue
        dc_by_sym[key] = dc_by_sym.get(key, 0.0) + (float(r["price"]) - pp) * abs(float(r["quantity"]))

    for sym, dc in dc_by_sym.items():
        if sym in cash_keys:
            continue
        for axis in out:
            for cat in _categories_for(sym, cat_map, axis):
                out[axis][cat] = out[axis].get(cat, 0.0) + dc
    return out


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
        if key is None:
            continue
        amt = float(f["amount"]) if f["amount"] is not None else 0.0
        # netflow (position-value impact) = -amount: hist_cst/hist_ft amount
        # follows a cash-ledger sign (Buy=negative cash, Sell=positive cash);
        # negating gives the position-value impact (Buy=+, Sell=-). Verified
        # against live rows during TASK_133 investigation.
        flow = -amt
        # 2026-08-10 -- cash_keys' OWN buy/sell rows (money-market sweep
        # transactions, e.g. "Buy SPAXX $1000" when a stock sale settles)
        # now netted into Cash's flow series the same way every other
        # category already nets its own trades -- these WERE being skipped
        # entirely, so Cash's raw_v day-over-day changes (position loop
        # above, "Cash" bucket) had no offsetting flow to subtract, and the
        # TWR formula (v_end - v_start - flow) / v_start counted every
        # dollar that moved through the cash balance -- deposits, trade
        # settlements, dividends landing -- as "return." User: "Cash should
        # not have a value in period columns, right?" -> confirmed a bug,
        # not by design (the code's only comment on this, _ASSET_CLASS_ETF's
        # "flat 0% benchmark" note, addresses the bench side only, not this).
        # Only the "asset_class" axis -- Cash's raw_v is only ever populated
        # there too (see the positions loop above), never sector/style.
        if key in cash_keys:
            rf = raw_flow["asset_class"].setdefault("Cash", {})
            rf[d] = rf.get(d, 0.0) + flow
            continue
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


def _twr_window(by_date: dict, calendar: list, window_days: int, end_offset: int = 0,
                 ignore_gap_guard: bool = False, ignore_swing_guard: bool = False) -> tuple:
    """Returns (twr, flows_confidence, detail). calendar is ascending; the
    window is `window_days` steps ending `end_offset` days back from
    calendar[-1] -- end_offset=0 (default) ends at calendar[-1] (today, D);
    end_offset=1 ends at calendar[-2] (yesterday, D-1), used for the
    "Yesterday" column, an isolated single day, not "today back through
    yesterday" -- that distinction is why this needs its own offset rather
    than just window_days=2.

    Two independent guards normally force r_t=0 and mark the window
    'suspect': (1) the original |r_t| > 25% flow-artefact guard, and (2)
    (round 2 / Part A) an unexplained symbol-level qty gap on d_cur -- a qty
    change with zero matching hist_cst/hist_ft row, which the 25% guard
    alone would miss whenever the swap is small relative to the category's
    total value (see _build_series docstring and DEV_HANDOFF.md).

    2026-08-08 -- ignore_gap_guard=True (Today/Yesterday, by explicit user
    request): skips guard (2), computing r_t straight off the F/CS snapshot
    diff (still netting any KNOWN flow amount) instead of forcing r_t=0 when
    a qty change has no matching CST/FT row. Trade-off knowingly accepted:
    if that unexplained qty change WAS a real trade, its dollar impact is
    misattributed as market return rather than netted out as a flow.

    ignore_swing_guard=True (Yesterday only, by explicit follow-up user
    request after seeing every sector except one zeroed by guard (1)):
    additionally skips guard (1), showing the raw snapshot-diff return even
    when it's an implausible single-day swing (traced live to missing
    snapshot rows for specific symbols on specific days -- e.g. PM absent
    from the 8/5 hist_cs export -- not real trading activity). Accepted
    trade-off: an obviously-wrong number (e.g. +878%) now displays as-is
    instead of being hidden behind a protective 0.

    Either bypass marks the day 'amber' confidence (not 'green') and, for
    the gap-guard case, records gap_symbols in gap_days (tagged unverified)
    so the caveat stays visible even though the day is no longer zeroed.
    Every other window (WINDOWS' 1w-3m, MTD/QTD/YTD, and Today's own guard
    -- Today is unconditionally forced to 0 by the caller regardless of
    what this function returns, see EXTRA_WINDOWS loop) keeps both guards
    as-is."""
    if len(calendar) <= window_days + end_offset:
        return None, "amber", {"reason": "insufficient calendar history"}
    end_idx = len(calendar) - end_offset
    idx_dates = calendar[end_idx - (window_days + 1):end_idx]  # window_days+1 points -> window_days steps
    product = 1.0
    suspect = False
    unverified = False
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
                if ignore_swing_guard:
                    unverified = True
                else:
                    r = 0.0
                    suspect = True
        if gap_syms:
            if ignore_gap_guard:
                unverified = True
                gap_days.append({"date": d_cur.isoformat(), "symbols": gap_syms, "unverified": True})
            else:
                r = 0.0
                suspect = True
                gap_days.append({"date": d_cur.isoformat(), "symbols": gap_syms})
        product *= (1.0 + r)
        day_count += 1
    twr = product - 1.0
    confidence = "suspect" if suspect else ("amber" if unverified else "green")
    detail = {"day_count": day_count, "netflow_total": round(netflow_total, 2)}
    if gap_days:
        detail["gap_days"] = gap_days
    return twr, confidence, detail


def _bench_return(session: Session, symbol, calendar: list, window_days: int,
                   end_offset: int = 0) -> Optional[float]:
    """symbol is normally a single ticker; a tuple/list (e.g. Fixed Income's
    (BUXX, CLOX, CLOZ) blend, see _ASSET_CLASS_ETF) computes the EQUAL-
    WEIGHTED AVERAGE of each member's own return over the same window --
    not an averaged price series (meaningless across differently-priced
    ETFs), an average of returns, the standard custom-composite-index
    approach. Members missing a price on either endpoint are skipped
    (partial blend, not a hard failure); returns None only if every member
    lacks data."""
    if isinstance(symbol, (tuple, list)):
        rets = [r for r in (_bench_return(session, s, calendar, window_days, end_offset) for s in symbol)
                if r is not None]
        return sum(rets) / len(rets) if rets else None
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


def _bench_symbol_label(symbol) -> Optional[str]:
    """Display/lookup label for drv_category_perf.bench_symbol -- a tuple
    blend (Fixed Income) becomes "BUXX+CLOX+CLOZ"; a plain string passes
    through unchanged. The '+'-joined form is also what
    GET /api/cockpit/benchmark-daily-change parses back apart to blend the
    daily chart the same way _bench_return blends the window returns."""
    if isinstance(symbol, (tuple, list)):
        return "+".join(symbol) if symbol else None
    return symbol


def _calendar_period_starts(d: date) -> dict:
    """First-of-month/quarter/year boundaries for `d` -- turns MTD/QTD/YTD
    into calendar-boundary windows, as opposed to WINDOWS' fixed
    trading-day counts."""
    q_start_month = ((d.month - 1) // 3) * 3 + 1
    return {
        "mtd": date(d.year, d.month, 1),
        "qtd": date(d.year, q_start_month, 1),
        "ytd": date(d.year, 1, 1),
    }


def _window_days_since(calendar: list, as_of_date: date, start_date: date) -> Optional[int]:
    """Trading-day step count from the baseline (the LAST calendar entry
    BEFORE start_date -- i.e. the prior period's closing value, e.g. the
    last trading day of July for MTD in August) through as_of_date
    (calendar's last entry) -- MTD/QTD/YTD's equivalent of WINDOWS' fixed
    day-counts, but calendar-boundary-driven instead of a hardcoded count.

    2026-08-08 bug fix: this originally baselined on the first calendar
    entry ON/AFTER start_date (the first trading day OF the period itself),
    which made _twr_window's first inter-day step "day 2 of the period vs
    day 1", silently excluding day 1's own return (prior-period-close ->
    day-1-close) from the window entirely -- understating the period return,
    and in a short/volatile window (MTD early in the month) potentially
    flipping its sign relative to the true period return. Baseline is now
    the day BEFORE start_date, so day 1's return is included like every
    other day.

    Clamps to the calendar's earliest available date when start_date (or
    the day before it) predates it (graceful "since inception" degrade --
    e.g. YTD is capped to however far hist_td actually goes back, same
    spirit as _twr_window's existing 'insufficient calendar history' guard,
    not a hard failure). Returns None if the calendar doesn't actually end
    on as_of_date, or the period has zero elapsed trading days (e.g. MTD on
    the 1st trading day of a new month, before any intra-month step exists)."""
    if not calendar or calendar[-1] != as_of_date:
        return None
    start_idx = next((i for i, cd in enumerate(calendar) if cd >= start_date), None)
    if start_idx is None:
        return None
    baseline_idx = max(0, start_idx - 1)
    window_days = (len(calendar) - 1) - baseline_idx
    return window_days if window_days > 0 else None


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


def _compute_category_rows(session: Session, as_of_date: date, accounts: Optional[list] = None) -> list:
    """Core row-computation logic, extracted so both the nightly portfolio-
    wide derive AND a live per-account request (Cockpit Accounts filter)
    can share the exact same TWR/flow-adjustment math -- filtering WHO
    (accounts) is included happens once, at the position/flow load, and
    cascades correctly through everything downstream unchanged (TWR math
    is account-agnostic; it aggregates whatever positions/flows come in).
    accounts=None means unfiltered (today's existing portfolio-wide
    behavior, byte-identical queries -- see _acct_clause)."""
    # 2026-08-08 -- widened to cover YTD (see YTD_CALENDAR_DAYS docstring);
    # harmless when less history exists (_trading_calendar just returns
    # whatever's available, no error) or as_of_date is early in the year.
    calendar = _trading_calendar(session, as_of_date, max(CALENDAR_BUFFER, YTD_CALENDAR_DAYS))
    if not calendar:
        return []
    lo, hi = calendar[0], calendar[-1]
    calendar_window_days = {k: _window_days_since(calendar, as_of_date, start)
                             for k, start in _calendar_period_starts(as_of_date).items()}

    positions, flows = _load_positions_and_flows(session, lo, hi, accounts)

    symbols = {(p["tos_symbol"] or p["symbol"]) for p in positions}
    cs_acct, f_acct = _acct_clause(accounts)
    cash_keys = set()
    is_cash_rows = session.execute(text(f"""
        SELECT DISTINCT COALESCE(tos_symbol, symbol) AS k FROM (
          SELECT tos_symbol, symbol, security_type, description FROM hist_cs
          WHERE snapshot_date BETWEEN :lo AND :hi
            AND account NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
            {cs_acct}
          UNION ALL
          SELECT tos_symbol, symbol, type AS security_type, description FROM hist_f
          WHERE snapshot_date BETWEEN :lo AND :hi
            AND account_number NOT IN (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
            {f_acct}
        ) u WHERE is_cash(symbol, security_type, description)
    """), {"lo": lo, "hi": hi, "accounts": accounts}).scalars().all()
    cash_keys = set(is_cash_rows)

    non_cash_symbols = symbols - cash_keys
    cat_map = _build_category_map(session, as_of_date, non_cash_symbols)

    any_flow_dates = _load_any_flow_dates(session, lo, hi, accounts)
    series = _build_series(positions, flows, cat_map, cash_keys, calendar, any_flow_dates)
    # 2026-08-14 -- briefly cloned asset_class's Cash row into sector's own
    # series too (a Cash row on the Sector axis), reverted same day -- user,
    # after seeing it live: "top sector included the cash, which it should
    # not." Sector intentionally has no Cash category (cash isn't
    # GICS-classified); the Portfolio Mix pie's Cash slice (web/
    # portfolio_mix.js) and the factor-scorecard's inline pie gap-filler
    # (web/app.js::_renderCatPie) were reverted alongside this for the same
    # reason -- see those files' own 2026-08-14 revert comments.
    today_change = _eod_actual_change(session, calendar, cat_map, cash_keys, accounts, offset=0)
    yesterday_change = _eod_actual_change(session, calendar, cat_map, cash_keys, accounts, offset=1)
    # 2026-08-23 -- twr_today's data source depends on whether the anchor
    # date's own EOD hist_cs/hist_f snapshot has landed yet (checked once,
    # portfolio-wide, from the already-fetched `positions` list -- no extra
    # query): before it lands (mid-trading-day), fall back to the live-tick
    # intraday preview; once it lands, today_change (broker-actual) above
    # is used instead. See _eod_actual_change's and
    # _today_marked_to_market's docstrings.
    today_snapshot_exists = bool(calendar) and any(p["snapshot_date"] == calendar[-1] for p in positions)
    today_live = None if today_snapshot_exists else \
        _today_marked_to_market(session, positions, cat_map, cash_keys, calendar)

    # Total portfolio(-slice) value at D (market + cash) for weight_pct --
    # same universe as /api/portfolio/summary (latest hist_f/hist_cs
    # snapshot <= D each, cash included). Phase 5 mandatory reconciliation
    # check. accounts filter narrows this to the selected account(s)' own
    # total, so weight_pct reads as "% of what you selected", not "% of
    # your whole portfolio" when filtered.
    total_row = session.execute(text(f"""
        WITH f_latest AS (SELECT MAX(snapshot_date) d FROM hist_f WHERE snapshot_date <= :d),
             cs_latest AS (SELECT MAX(snapshot_date) d FROM hist_cs WHERE snapshot_date <= :d),
             excl AS (SELECT account_number FROM ref_accounts WHERE is_active = FALSE)
        SELECT
          COALESCE((SELECT SUM(current_value) FROM hist_f WHERE snapshot_date=(SELECT d FROM f_latest)
                    AND account_number NOT IN (SELECT account_number FROM excl) {f_acct}),0)
        + COALESCE((SELECT SUM(market_value) FROM hist_cs WHERE snapshot_date=(SELECT d FROM cs_latest)
                    AND account NOT IN (SELECT account_number FROM excl) {cs_acct}),0)
          AS total
    """), {"d": as_of_date, "accounts": accounts}).scalar()
    total_value = float(total_row) if total_row else 0.0

    # 2026-08-08 -- total EQUITY value only (Asset Class axis's own
    # "Equities" bucket, already built by _build_series/_categories_for's
    # asset_class=="Equities" resolution), for re-basing Sector/Style
    # weight_pct against the equity sleeve instead of the whole portfolio
    # ("are sector percentages calculated based on equities?").
    total_equity_value = series.get("asset_class", {}).get("Equities", {}).get(hi, {}).get("v", 0.0)

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
            # sector/style only -- asset_class IS the total-portfolio view,
            # re-basing it against equities would be circular.
            weight_pct_equities = ((mv / total_equity_value * 100.0) if total_equity_value else None) \
                if axis in ("sector", "style") else None

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
            # 2026-08-08 -- Yesterday built from _eod_actual_change (broker
            # day_chng_dollar/today_gl_dollar + sold-transaction
            # adjustment) instead of the old mv-diff + 25%-swing-guard
            # approach -- see that function's docstring. No guard/suspect
            # marking needed since every number is actually computed, not
            # estimated-then-clamped; confidence is "green" whenever a
            # figure exists, "amber" (insufficient history) otherwise.
            # 2026-08-23 -- Today now shares this same EOD-actual
            # computation too, but ONLY once the anchor date's own
            # hist_cs/hist_f snapshot has landed (today_snapshot_exists,
            # computed once above) -- before that (mid-trading-day) it
            # falls back to _today_marked_to_market's live-tick intraday
            # preview instead, so the grid still updates during market
            # hours rather than showing blank all day. See both functions'
            # docstrings for the full history.
            eod_change_by_offset = {0: today_change, 1: yesterday_change}
            for wlabel, (wdays, offset) in EXTRA_WINDOWS.items():
                if wlabel == "today" and not today_snapshot_exists:
                    twr["twr_today"] = today_live.get(axis, {}).get(category)
                    b = _bench_return(session, etf_map.get(category), calendar, wdays, offset)
                    bench["bench_today"] = b
                    window_detail["today"] = {
                        "confidence": "amber",
                        "reason": "marked-to-market: yesterday's shares at today's live price "
                                  "(today's EOD snapshot not loaded yet)",
                    }
                    confs.append("amber")
                    continue
                prior_idx = -(2 + offset)
                prior_v = by_date.get(calendar[prior_idx], {}).get("v", 0.0) if len(calendar) >= (2 + offset) else 0.0
                dc = eod_change_by_offset[offset].get(axis, {}).get(category)
                t = (dc / prior_v) if (dc is not None and prior_v) else None
                conf = "green" if t is not None else "amber"
                twr[f"twr_{wlabel}"] = t
                b = _bench_return(session, etf_map.get(category), calendar, wdays, offset)
                bench[f"bench_{wlabel}"] = b
                window_detail[wlabel] = {
                    "confidence": conf,
                    "reason": "broker day_chng_dollar/today_gl_dollar + sold-transaction adjustment",
                }
                if len(calendar) > wdays + offset:
                    confs.append(conf)
            # 2026-08-08 -- MTD/QTD/YTD (calendar-boundary windows, see
            # _window_days_since) requested in place of the 1w/3w/1m/2m/3m
            # display columns. Kept as separate twr_mtd/qtd/ytd columns
            # rather than replacing WINDOWS -- _verdict()'s PRESS/ROTATE
            # logic below still reads WINDOWS/twr_1m unchanged.
            for wlabel, wdays in calendar_window_days.items():
                if wdays is None:
                    twr[f"twr_{wlabel}"] = None
                    bench[f"bench_{wlabel}"] = None
                    window_detail[wlabel] = {"confidence": "amber", "reason": "insufficient calendar history"}
                    continue
                t, conf, detail_w = _twr_window(by_date, calendar, wdays)
                twr[f"twr_{wlabel}"] = t
                b = _bench_return(session, etf_map.get(category), calendar, wdays)
                bench[f"bench_{wlabel}"] = b
                window_detail[wlabel] = {"confidence": conf, **detail_w}
                confs.append(conf)
            # 2026-08-10 -- Cash forced to no gain/loss on every window, not
            # just today/yesterday (which were already excluded structurally
            # above). The flow-netting fix just above (cash_keys' own buy/
            # sell rows now recorded as flows) still leaves residual noise
            # for cash movements that aren't a Buy/Sell trade row at all --
            # dividends/interest credited straight to the cash balance,
            # wires, ACH transfers, journal entries -- none of which
            # _flows_sql's BUY/SELL-only filter can see. Cash isn't a
            # tradeable instrument with a "return" in this app's model
            # (bench_* is already always None, no ETF proxy exists), so
            # rather than chase every possible cash-movement type, twr_* is
            # unconditionally None here too. User: "cash should not have
            # gain or loss."
            if axis == "asset_class" and category == "Cash":
                for k in twr:
                    twr[k] = None
                for k in bench:
                    bench[k] = None
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
            elif category == "Non-Equity (excluded)":
                detail["note"] = ("non-equity holdings (bond/gold/commodity ETFs) excluded from the "
                                   "equity sector axis by design -- shown as their own row, same as "
                                   "any other category (reversed 2026-08-11 from an earlier version "
                                   "that dropped it from the API response entirely)")
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
                "weight_pct_equities": weight_pct_equities,
                "target_min": target_min, "target_max": target_max,
                **twr, **bench,
                "bench_symbol": _bench_symbol_label(etf_map.get(category)),
                "flows_confidence": flows_confidence,
                "quad_stance": quad_stance, "verdict": verdict,
                "detail": detail,
            })

    return rows_out


def _derive_category_perf_impl(session: Session, as_of_date: date, run_id) -> int:
    rows_out = _compute_category_rows(session, as_of_date, accounts=None)
    return replace_for_date(session, "drv_category_perf", "as_of_date", as_of_date, rows_out)


derive_category_perf = _wrap("drv_category_perf", _derive_category_perf_impl)
