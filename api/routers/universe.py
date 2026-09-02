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

from api.routers.dash import get_actionable, get_portfolio, list_actionable_accounts

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
        }
        for r in portfolio_rows
        if not r.get("is_cash") and r.get("symbol") and r.get("market_value")
    ]
    cash_totals: dict[str, float] = {}
    for r in portfolio_rows:
        if r.get("is_cash") and r.get("account_id"):
            cash_totals[r["account_id"]] = cash_totals.get(r["account_id"], 0.0) + float(r.get("market_value") or 0)
    cash_by_account = [{"account_id": k, "cash_value": v} for k, v in cash_totals.items()]

    return {"symbols": symbols, "positions": positions, "accounts": accounts, "cash_by_account": cash_by_account}
