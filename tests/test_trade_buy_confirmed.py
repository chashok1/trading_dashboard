"""Trade vs Trade2 (nightly email job's mirror of the screen rule): a Buy To Min stays in Trade only when PVV or the Tradability icon backs it.
Behaviour only, pure Python."""
import etl.export_trade_mode as t


def _row(**kw):
    base = {"final_code": "BMN", "fc_feasible": True, "winning_source": "RTA", "pvv_decision": "NO_ACTION",
            "asset_class": "Equity", "is_macro_instrument": False}
    base.update(kw)
    return base


def _qual(row, monkeypatch, score):
    monkeypatch.setattr(t, "_buy_tradability_score", lambda *a, **k: score)
    return t._is_qualifying_buy(row, True, 70, 30, 1.5, {}, {})


def test_buy_to_min_without_backing_goes_to_trade2(monkeypatch):
    assert _qual(_row(), monkeypatch, score=5) is False


def test_buy_to_min_with_tradability_icon_stays_in_trade(monkeypatch):
    assert _qual(_row(), monkeypatch, score=t._TRADABILITY_BADGE_MIN) is True


def test_buy_to_min_with_pvv_buy_stays_in_trade(monkeypatch):
    assert _qual(_row(pvv_decision="BUY_DIP"), monkeypatch, score=0) is True


def test_pvv_avoid_still_goes_to_trade2_even_with_the_icon(monkeypatch):
    assert _qual(_row(pvv_decision="AVOID"), monkeypatch, score=20) is False


def test_buy_more_is_unaffected(monkeypatch):
    assert _qual(_row(final_code="BM"), monkeypatch, score=0) is True
