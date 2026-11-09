"""Trade vs Trade2 (nightly email job's mirror of the screen rule): a Buy To Min stays in Trade only when PVV backs it (the Tradability score was removed 2026-11-08).
Behaviour only, pure Python."""
import etl.export_trade_mode as t


def _row(**kw):
    base = {"final_code": "BMN", "fc_feasible": True, "winning_source": "RTA", "pvv_decision": "NO_ACTION",
            "asset_class": "Equity", "is_macro_instrument": False}
    base.update(kw)
    return base


def _qual(row, monkeypatch=None, score=None):
    return t._is_qualifying_buy(row, True)


def test_buy_to_min_without_backing_goes_to_trade2(monkeypatch):
    assert _qual(_row(), monkeypatch, score=5) is False


def test_buy_to_min_with_pvv_buy_stays_in_trade(monkeypatch):
    assert _qual(_row(pvv_decision="BUY_DIP"), monkeypatch, score=0) is True


def test_pvv_avoid_no_longer_vetoes_a_buy_more(monkeypatch):
    assert _qual(_row(final_code="BM", pvv_decision="AVOID"), monkeypatch, score=0) is True


def test_buy_more_is_unaffected(monkeypatch):
    assert _qual(_row(final_code="BM"), monkeypatch, score=0) is True
