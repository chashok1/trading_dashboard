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

    symbols = [
        {
            "tos_symbol": r.get("tos_symbol"),
            "sector": r.get("sector"),
            "held_today": bool(r.get("held_today")),
            "current_position_dollar": float(r.get("current_position_dollar") or 0),
            "final_code": r.get("final_code"),
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
