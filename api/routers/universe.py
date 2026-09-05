"""Universe-by-sector treemap screen (web/universe.html + universe.js).

GET /api/universe returns three flat lists -- symbol-level universe rows
(sector/held/final_code), per-account position rows, and account labels --
and leaves all filtering/aggregation/drilldown to the client (same model the
prototype used, see the Universe by Sector artifact this screen is built
from). Deliberately reuses the existing get_actionable/get_portfolio/
list_actionable_accounts functions (plain Python calls, not HTTP round
trips) instead of re-deriving their SQL -- those are the same queries
/api/actionable and /api/portfolio already run and depend on for their own
screens, so reusing them keeps this screen's numbers guaranteed consistent
with those rather than a second, potentially-drifting implementation.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from api.routers.dash import (
    get_actionable, get_portfolio, get_portfolio_realized, get_portfolio_dividends, list_actionable_accounts,
)

router = APIRouter()


@router.get("/api/universe")
def get_universe(date: Optional[str] = Query(None)):
    # NOTE: get_actionable/get_portfolio are FastAPI route functions whose
    # OTHER params default to `Query(...)` sentinel objects, not plain
    # Python values -- those only get resolved to real values on the HTTP
    # path. Calling them directly (as here) means every param must be
    # passed explicitly with a real value, or the function body's own
    # truthiness/method-call checks on the sentinel blow up.
    # show_suppressed=True (was False): the Actionable screen's own
    # suppression logic (already-established positions, over/under target,
    # etc.) is about what needs a trading DECISION today -- irrelevant to
    # this screen, which is a census of the whole universe/portfolio. With
    # it False, a held-but-suppressed symbol (e.g. "ALREADY ESTABLISHED --
    # held $9,391 >= floor $4,000") dropped out of `symbols` entirely, which
    # then silently dropped it from `positions` too (the join below only
    # keeps a position if its symbol is in `symbols`) -- e.g. SOFI vanishing
    # from the Designated_Bene_Individual ...254 ("Ra") account breakdown.
    actionable_rows = get_actionable(
        date=date, action=None, category=None,
        my_list_only=False, show_acted=False, show_suppressed=True,
    )
    portfolio_rows = get_portfolio(
        date=date, consolidated=False, account=None, source=None, latest_prices=False,
    )
    accounts = list_actionable_accounts(date=date)

    # is_macro_instrument flows through so the client can peel real
    # futures/FX/index instruments (no GICS sector by nature -- /GC, SPX,
    # /6E etc.) out of the "Unclassified" catch-all into their own bucket,
    # instead of lumping them in with ordinary stocks whose `sector` is
    # merely unpopulated in the reference data (a separate, larger, actual
    # data gap this screen doesn't try to paper over).
    # last_price/trade_line_value/trend_line_value/lrr/trr feed the
    # drilldown tile's Trade/Trend above-below coloring and mini Risk Range
    # bar -- same fields + formula (_rawRrPos) the Actionable screen's own
    # Action popup uses, so a tile's read matches what you'd see there.
    def _f(v):
        return float(v) if v is not None else None

    # asset_class (real_asset_class, normalized) + style_tags feed the new
    # "By Asset Class" hierarchy (Asset Class -> Sector-if-Equities ->
    # Symbol) and the Style filter. Region-split equity labels ("Domestic
    # Equities"/"Global Equities"/"International Equities"/"Emerging
    # Markets Equities") merged into one "Equities" -- only ~19 of 568
    # equity rows even carry a region tag, too sparse to be a useful split.
    # Currency labels ("Foreign Currency"/"Foreign Currencies"/"FX") merged
    # the same way. Unpopulated (None) is left as-is -- same "Unclassified"
    # catch-all treatment the client already gives an empty sector.
    _EQUITY_ALIASES = {"Equities", "Domestic Equities", "Global Equities",
                        "International Equities", "Emerging Markets Equities"}
    _FX_ALIASES = {"Foreign Currency", "Foreign Currencies", "FX", "USD"}
    _FIXED_INCOME_ALIASES = {"Fixed Income", "Domestic Fixed Income"}

    def _norm_asset_class(raw):
        s = (raw or "").strip()
        if not s:
            return None
        if s in _EQUITY_ALIASES:
            return "Equities"
        if s in _FX_ALIASES:
            return "FX / Currency"
        if s in _FIXED_INCOME_ALIASES:
            return "Fixed Income"
        return s

    def _style_labels(raw):
        if not raw:
            return []
        return [x.get("label") for x in raw if isinstance(x, dict) and x.get("label")]

    # sources: which outlook source(s) (RR/CALL/ETF/II/SSS/PS/...) flagged
    # this symbol, from drv_actionable.source_actions -- feeds the new "By
    # Source" hierarchy. A symbol can carry more than one (e.g. both RR and
    # CALL), so this is a list, same multi-tag shape as style_tags.
    def _source_codes(raw):
        if not raw:
            return []
        return [x.get("source") for x in raw if isinstance(x, dict) and x.get("source")]

    # 2026-09-03 (held-perspective proposal): unrealized P&L per symbol,
    # summed across accounts from the same `portfolio_rows` this endpoint
    # already fetches -- get_portfolio() computes avg_cost/cost_basis/
    # today_gain_*/total_gain_*/ytd_gain_*/mtd_gain_* per (symbol, account)
    # row already (real broker cost basis, hist_cs.cost_basis /
    # hist_f.cost_basis_total), it just wasn't being surfaced here. Dollar
    # totals sum naturally across accounts; percentages are RE-DERIVED from
    # the summed dollars (dollar / summed cost_basis, etc.) rather than
    # averaging each account's own %, which would mis-weight a symbol held
    # unevenly across accounts.
    _gain_keys = ("today_gain_dollar", "total_gain_dollar", "ytd_gain_dollar", "mtd_gain_dollar")
    gain_by_symbol: dict = {}
    for r in portfolio_rows:
        sym = r.get("symbol")
        if r.get("is_cash") or not sym or not r.get("market_value"):
            continue
        g = gain_by_symbol.setdefault(sym, {"cost_basis": 0.0, "market_value": 0.0, "qty": 0.0,
                                             "has_cost_basis": False, "has_qty": False,
                                             **{k: 0.0 for k in _gain_keys}})
        cb = r.get("cost_basis")
        if cb is not None:
            g["cost_basis"] += float(cb)
            g["has_cost_basis"] = True
        qty = r.get("qty")
        if qty is not None:
            g["qty"] += float(qty)
            g["has_qty"] = True
        g["market_value"] += float(r.get("market_value") or 0)
        for k in _gain_keys:
            v = r.get(k)
            if v is not None:
                g[k] += float(v)

    def _pct(dollar, base):
        return (dollar / base * 100.0) if base else None

    # Realized gain (FIFO-matched, drv_realized_gain via the same endpoint
    # /portfolio's Realized tab uses) -- summed per symbol across accounts.
    # Defensive try/except mirrors this file's/dash.py's own pattern for
    # supplementary decorations that shouldn't 500 the whole screen.
    realized_by_symbol: dict = {}
    try:
        for r in get_portfolio_realized(
            date=date, symbol=None, account=None, source=None,
            group_by="symbol", from_date=None, to_date=None,
        ):
            if r.get("bucket"):
                realized_by_symbol[r["bucket"]] = {
                    "total_realized": float(r.get("total_realized") or 0),
                    "ytd_realized": float(r.get("ytd_realized") or 0),
                }
    except Exception:
        pass

    def _gain_fields(sym):
        g = gain_by_symbol.get(sym)
        rg = realized_by_symbol.get(sym)
        out = {
            "avg_cost": None, "cost_basis": None,
            "today_gain_dollar": None, "today_gain_pct": None,
            "total_gain_dollar": None, "total_gain_pct": None,
            "ytd_gain_dollar": None, "mtd_gain_dollar": None,
            "total_realized": rg["total_realized"] if rg else None,
            "ytd_realized": rg["ytd_realized"] if rg else None,
        }
        if g:
            cb = g["cost_basis"] if g["has_cost_basis"] else None
            qty = g["qty"] if g["has_qty"] else None
            prior_mv = g["market_value"] - g["today_gain_dollar"]
            out.update({
                "avg_cost": (cb / qty) if (cb is not None and qty) else None,
                "cost_basis": cb,
                "today_gain_dollar": g["today_gain_dollar"],
                "today_gain_pct": _pct(g["today_gain_dollar"], prior_mv),
                "total_gain_dollar": g["total_gain_dollar"],
                "total_gain_pct": _pct(g["total_gain_dollar"], cb),
                "ytd_gain_dollar": g["ytd_gain_dollar"],
                "mtd_gain_dollar": g["mtd_gain_dollar"],
            })
        return out

    symbols = [
        {
            "tos_symbol": r.get("tos_symbol"),
            "sector": r.get("sector"),
            "held_today": bool(r.get("held_today")),
            "current_position_dollar": float(r.get("current_position_dollar") or 0),
            "final_code": r.get("final_code"),
            "is_macro_instrument": bool(r.get("is_macro_instrument")),
            "last_price": _f(r.get("last_price")),
            "trade_line_value": _f(r.get("trade_line_value")),
            "trend_line_value": _f(r.get("trend_line_value")),
            "lrr": _f(r.get("lrr")),
            "trr": _f(r.get("trr")),
            "hv": _f(r.get("hv")),
            "asset_class": _norm_asset_class(r.get("real_asset_class")),
            "style_tags": _style_labels(r.get("style_stances")),
            "sources": _source_codes(r.get("source_actions")),
            **_gain_fields(r.get("tos_symbol")),
        }
        for r in actionable_rows
        if r.get("tos_symbol")
    ]

    # Cash rows carry no sector, so they can't feed a by-sector breakdown --
    # same "non_cash" filter the Universe by Sector prototype applied to
    # this same /api/portfolio data. But an account that's ALL cash (no
    # non-cash positions at all) would then generate zero rows here and
    # disappear from the account list entirely rather than just showing $0
    # in securities -- e.g. Designated_Bene_Individual ...100 ("A"), 100%
    # cash. So cash is reported separately (summed per account, not
    # per-symbol -- it has no sector/symbol to attach to) instead of just
    # being dropped, and the client adds it into each account's total so a
    # cash-only account still gets a real, sized tile.
    positions = [
        {
            "tos_symbol": r.get("symbol"),
            "account_id": r.get("account_id"),
            "account_tag": r.get("account_tag"),
            "market_value": float(r.get("market_value") or 0),
            # 2026-09-03: per-account unrealized P&L, straight off this same
            # get_portfolio() row -- no aggregation needed here (unlike
            # symbols[] above, which sums across accounts per symbol).
            "avg_cost": _f(r.get("avg_cost")),
            "cost_basis": _f(r.get("cost_basis")),
            "today_gain_dollar": _f(r.get("today_gain_dollar")),
            "today_gain_pct": _f(r.get("today_gain_pct")),
            "total_gain_dollar": _f(r.get("total_gain_dollar")),
            "total_gain_pct": _f(r.get("total_gain_pct")),
            "ytd_gain_dollar": _f(r.get("ytd_gain_dollar")),
            "mtd_gain_dollar": _f(r.get("mtd_gain_dollar")),
        }
        for r in portfolio_rows
        if not r.get("is_cash") and r.get("symbol") and r.get("market_value")
    ]
    cash_totals: dict[str, float] = {}
    for r in portfolio_rows:
        if r.get("is_cash") and r.get("account_id"):
            cash_totals[r["account_id"]] = cash_totals.get(r["account_id"], 0.0) + float(r.get("market_value") or 0)
    cash_by_account = [{"account_id": k, "cash_value": v} for k, v in cash_totals.items()]

    # 2026-09-03: realized gain per account (YTD + all-time), for the
    # account-tile tooltip -- same drv_realized_gain rollup as
    # /api/portfolio/realized?group_by=account, called directly (plain
    # Python call, same reuse pattern as get_actionable/get_portfolio
    # above) rather than duplicating its SQL. `bucket` is the account's
    # raw account_number/account_id (CS) or Fidelity's own masked account
    # identifier (F) -- both are exactly what get_portfolio's own
    # `account_id` already uses, so this joins straight onto `positions`/
    # `cash_by_account` above with no translation needed.
    realized_by_account = []
    try:
        for r in get_portfolio_realized(
            date=date, symbol=None, account=None, source=None,
            group_by="account", from_date=None, to_date=None,
        ):
            if r.get("bucket"):
                realized_by_account.append({
                    "account_id": r["bucket"],
                    "total_realized": float(r.get("total_realized") or 0),
                    "ytd_realized": float(r.get("ytd_realized") or 0),
                })
    except Exception:
        pass

    # 2026-09-05: dividend income per account (YTD + all-time), for the
    # account-tile tooltip -- same shape/reuse pattern as realized_by_account
    # just above (drv_dividend_income via /api/portfolio/dividends).
    dividends_by_account = []
    try:
        for r in get_portfolio_dividends(
            date=date, symbol=None, account=None, source=None,
            group_by="account", from_date=None, to_date=None,
        ):
            if r.get("bucket"):
                dividends_by_account.append({
                    "account_id": r["bucket"],
                    "total_dividends": float(r.get("total_amount") or 0),
                    "ytd_dividends": float(r.get("ytd_amount") or 0),
                })
    except Exception:
        pass

    return {
        "symbols": symbols, "positions": positions, "accounts": accounts,
        "cash_by_account": cash_by_account, "realized_by_account": realized_by_account,
        "dividends_by_account": dividends_by_account,
    }
