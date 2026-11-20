"""Which ref_asset_allocation row sizes a symbol (2026-11-19, user).

Sizing is by what the symbol IS (asset class), not which Hedgeye list it came from:

    Fixed Income / Commodities / Foreign Currency / Cash   by asset class
    Exchange Traded Funds                                  Yahoo quote type ETF (any equity-type fund)
    Stocks                                                 individual stocks, full strength
    Stocks (Call/RR only)                                  a stock on Call or RR and NOT on Signal Strength = half strength
    Other                                                  indexes, futures, anything unclassifiable ($0 envelope)

Pure function, no DB. Used by derive_actionable (sizes + position_category).
"""
from typing import Iterable, Optional

STOCKS = "Stocks"
STOCKS_HALF = "Stocks (Call/RR only)"
ETFS = "Exchange Traded Funds"
FIXED_INCOME = "Fixed Income"
COMMODITIES = "Commodities"
FOREIGN_CURRENCY = "Foreign Currency"
CASH = "Cash"
OTHER = "Other"

# Hedgeye / ref_sector spellings -> the allocation row
_AC_MAP = {
    "fixed income": FIXED_INCOME, "domestic fixed income": FIXED_INCOME,
    "us fixed income": FIXED_INCOME, "international fixed income": FIXED_INCOME,
    "commodities": COMMODITIES, "commodity": COMMODITIES,
    "foreign currency": FOREIGN_CURRENCY, "foreign currencies": FOREIGN_CURRENCY,
    "foreign exchange": FOREIGN_CURRENCY, "fx": FOREIGN_CURRENCY, "usd": FOREIGN_CURRENCY,
    "currency": FOREIGN_CURRENCY,
    "cash": CASH,
}

SS_SOURCES = {"SSS", "SSSCHG"}                                   # Signal Strength
CALL_RR_SOURCES = {"CALL", "TOP5", "RR", "RTA", "RTAINFO", "MACROSHOW"}

# Yahoo quote types that are not a stock or an ETF
_NOT_STOCK_QT = {"INDEX", "FUTURE", "ALTSYMBOL", "MUTUALFUND", "ECNQUOTE", "CRYPTOCURRENCY"}


def size_class(asset_class: Optional[str], quote_type: Optional[str],
               on_sources: Iterable[str], legacy_category: Optional[str] = None) -> Optional[str]:
    """on_sources = codes of the lists the symbol is currently ON (a REMOVE does not count)."""
    ac = _AC_MAP.get(str(asset_class or "").strip().lower())
    if ac:
        return ac
    if str(legacy_category or "").strip().lower() == "cash":
        return CASH
    qt = str(quote_type or "").strip().upper()
    if qt == "ETF":
        return ETFS
    if qt == "CURRENCY":
        return FOREIGN_CURRENCY
    if qt in _NOT_STOCK_QT:
        return OTHER
    srcs = {str(s).upper() for s in on_sources}
    if qt == "" and not srcs and not asset_class:
        return None                                              # unknown, on no list: no sizing (as before)
    if srcs & SS_SOURCES:
        return STOCKS
    if srcs & CALL_RR_SOURCES:
        return STOCKS_HALF
    return STOCKS
