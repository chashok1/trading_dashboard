"""Market calendar: weekends, holidays and early closes decide whether the market is open."""
from datetime import date, datetime, time

from etl import market_date, scheduler
from etl.derive_outlook_action import _weekdays_back
from etl.market_date import calendar_expiry_warnings, close_time, is_market_open, is_trading_day, previous_trading_day
from etl.scheduler import _intraday_slots

HOL = {date(2026, 11, 26)}
EARLY = {date(2026, 11, 27): time(13, 0)}


def _open(day, h, m=0):
    return is_market_open(datetime(2026, 11, day, h, m), HOL, EARLY)


def test_holiday_and_weekend_are_not_trading_days():
    assert is_trading_day(date(2026, 11, 26), HOL) is False
    assert is_trading_day(date(2026, 11, 28), HOL) is False
    assert is_trading_day(date(2026, 11, 27), HOL) is True


def test_close_time_and_open_hours():
    assert close_time(date(2026, 11, 27), EARLY) == time(13, 0)
    assert close_time(date(2026, 11, 30), EARLY) == time(16, 0)
    assert _open(25, 15, 59) is True
    assert _open(25, 16) is False
    assert _open(26, 11) is False
    assert _open(27, 12, 59) is True
    assert _open(27, 13) is False


def test_previous_trading_day_skips_holiday():
    assert previous_trading_day(date(2026, 11, 27), HOL) == date(2026, 11, 25)


def test_early_close_moves_the_afternoon_fetch():
    assert _intraday_slots(time(16, 0)) == [(10, 0), (15, 0)]
    assert _intraday_slots(time(13, 0)) == [(10, 0), (13, 15)]


def test_holiday_tosd_rows_are_left_out(monkeypatch):
    seen = []
    monkeypatch.setattr(market_date, "_set_warning", lambda s, feed, msg: seen.append((feed, msg)))
    rows = [{"export_date": date(2026, 11, 25)}, {"export_date": date(2026, 11, 26)}, {"export_date": None}]
    reasons = {}
    kept = market_date.drop_closed_day_rows(None, rows, "TOSD.csv", reasons, HOL)
    assert [r["export_date"] for r in kept] == [date(2026, 11, 25), None]
    assert reasons == {"market closed on 11/26 (weekend/holiday)": 1}
    assert seen[0][0] == "TOSD" and "11/26" in seen[0][1]


def test_signal_lookbacks_skip_the_holiday():
    assert _weekdays_back(date(2026, 11, 27), 1, HOL) == date(2026, 11, 25)
    assert _weekdays_back(date(2026, 11, 30), 3, HOL) == date(2026, 11, 24)


def test_calendar_warns_only_when_a_list_is_running_out():
    hol, early = {date(2028, 12, 25)}, {date(2028, 11, 24): time(13, 0)}
    assert calendar_expiry_warnings(date(2028, 1, 3), hol, early) == []
    late = calendar_expiry_warnings(date(2028, 9, 1), hol, early)
    assert len(late) == 2 and "12/25/2028" in late[0] and "ref_early_close" in late[1]
    assert "empty" in calendar_expiry_warnings(date(2028, 1, 3), set(), early)[0]


def test_nightly_risk_ranges_skip_closed_days(monkeypatch):
    called = []
    monkeypatch.setattr(scheduler, "is_trading_day", lambda d: False)
    monkeypatch.setattr("etl.derive.derive_rr", lambda *a: called.append(a))
    scheduler._nightly_derive_rr(date(2026, 11, 28))
    assert called == []
