"""PS-drop rule: a held PS drop is HOLD (ignored) unless RR is not Bullish,
price is below the Trade line, or price is >= ps_drop_sell_pct below its drop close."""
from datetime import date

from etl._derive_common import _ps_drop_verdicts


class _Res:
    def __init__(self, rows): self._rows = rows
    def scalar(self): return self._rows
    def fetchall(self): return self._rows


class _Sess:
    """First execute = ref_settings lookup, second = the symbol rows."""
    def __init__(self, rows, pct=None):
        self._seq = [_Res(pct), _Res(rows)]
    def execute(self, *_a, **_k): return self._seq.pop(0)


def _v(outlook, px, trade, px_drop, pct=None):
    rows = [("XLE", outlook, px, trade, px_drop)]
    return _ps_drop_verdicts(_Sess(rows, pct), date(2026, 10, 8), date(2026, 10, 2), ["XLE"])["XLE"]


def test_bullish_above_trade_line_and_up_is_ignored():
    assert _v("BULLISH", 65.4, 61.4, 63.4)[0] == "HOLD"


def test_bullish_label_variants_count_as_bullish():
    for o in ("Bullish", "Mild Bullish", "Light Bullish"):
        assert _v(o, 65.4, 61.4, 63.4)[0] == "HOLD"


def test_not_bullish_sells_all():
    assert _v("Neutral", 65.4, 61.4, 63.4)[0] == "REMOVE"


def test_below_trade_line_sells_all():
    assert _v("BULLISH", 60.0, 61.4, 59.0)[0] == "REMOVE"


def test_four_percent_below_drop_price_sells_all():
    assert _v("BULLISH", 96.0, 90.0, 100.0)[0] == "REMOVE"      # -4.0%
    assert _v("BULLISH", 96.5, 90.0, 100.0)[0] == "HOLD"        # -3.5%


def test_threshold_is_a_setting():
    assert _v("BULLISH", 96.5, 90.0, 100.0, pct="3")[0] == "REMOVE"


def test_missing_rr_or_price_keeps_remove():
    out = _ps_drop_verdicts(_Sess([("XLE", None, 65.0, 61.0, 63.0)]), date(2026, 10, 8), date(2026, 10, 2), ["XLE"])
    assert "XLE" not in out                                      # caller keeps today's REMOVE
