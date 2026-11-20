from etl.size_class import size_class, STOCKS, STOCKS_HALF, ETFS, FIXED_INCOME, FOREIGN_CURRENCY, OTHER


def test_stock_on_signal_strength_full():
    assert size_class("Equities", "EQUITY", {"SSS", "CALL"}) == STOCKS


def test_stock_call_or_rr_only_half():
    assert size_class("Equities", "EQUITY", {"CALL"}) == STOCKS_HALF
    assert size_class("Equities", "EQUITY", {"RR", "II"}) == STOCKS_HALF


def test_stock_on_other_or_no_list_full():
    assert size_class("Equities", "EQUITY", {"PS"}) == STOCKS
    assert size_class("Equities", "EQUITY", set()) == STOCKS


def test_etf_ignores_signal_strength_rule():
    assert size_class("Equities", "ETF", {"CALL"}) == ETFS
    assert size_class("Equities", "ETF", {"SSS"}) == ETFS


def test_asset_class_beats_quote_type():
    assert size_class("Fixed Income", "ETF", set()) == FIXED_INCOME
    assert size_class("USD", "ETF", set()) == FOREIGN_CURRENCY
    assert size_class("Domestic Fixed Income", None, set()) == FIXED_INCOME


def test_non_tradable_types_and_unknown():
    assert size_class(None, "INDEX", {"RR"}) == OTHER
    assert size_class(None, "CURRENCY", {"RR"}) == FOREIGN_CURRENCY
    assert size_class(None, None, set()) is None
    assert size_class(None, None, {"CALL"}) == STOCKS_HALF
