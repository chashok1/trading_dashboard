"""TOP5/RTA outdated-call helpers: behaviour only, pure Python (fake session, no DB)."""
from datetime import date

from etl.derive_outlook_action import _broken_since_call, _weekdays_back


class _Res:
    def __init__(self, rows): self._rows = rows
    def fetchall(self): return self._rows


class _Sess:
    def __init__(self, rows): self._rows = rows
    def execute(self, *a, **k): return _Res(self._rows)


def test_weekdays_back_skips_weekend():
    assert _weekdays_back(date(2026, 10, 28), 3) == date(2026, 10, 23)   # Wed -> Fri
    assert _weekdays_back(date(2026, 10, 26), 3) == date(2026, 10, 21)   # Mon -> Wed


def test_buy_broken_when_price_closes_below_trade_after_call():
    rows = [("X", date(2026, 10, 19), 100, 90, 80), ("X", date(2026, 10, 20), 95, 90, 80), ("X", date(2026, 10, 21), 85, 90, 80)]
    assert _broken_since_call(_Sess(rows), [("X", date(2026, 10, 19), 1)], date(2026, 10, 21)) == {"X": date(2026, 10, 21)}


def test_not_broken_when_price_was_already_below_on_call_day():
    rows = [("X", date(2026, 10, 19), 71, 86, 45), ("X", date(2026, 10, 20), 70, 86, 45)]
    assert _broken_since_call(_Sess(rows), [("X", date(2026, 10, 19), 1)], date(2026, 10, 20)) == {}


def test_sell_broken_when_price_closes_above_both_lines_after_call():
    rows = [("X", date(2026, 10, 19), 70, 90, 80), ("X", date(2026, 10, 20), 95, 90, 80)]
    assert _broken_since_call(_Sess(rows), [("X", date(2026, 10, 19), -1)], date(2026, 10, 20)) == {"X": date(2026, 10, 20)}
