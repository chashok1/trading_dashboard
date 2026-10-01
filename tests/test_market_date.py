"""Market-date resolution for position snapshot files (etl/market_date.py).

Pure-function tests: behavior only, no DB.
"""
from datetime import date, datetime

from etl.market_date import market_date_for, resolve_snapshot_date

THU = date(2026, 10, 1)
WED = date(2026, 9, 30)
FRI = date(2026, 10, 2)
SAT = date(2026, 10, 3)
MON = date(2026, 10, 5)


def at(d, hh, mm=0):
    return datetime(d.year, d.month, d.day, hh, mm)


def test_before_open_belongs_to_previous_trading_day():
    assert market_date_for(at(THU, 0, 20)) == WED
    assert market_date_for(at(THU, 9, 29)) == WED


def test_open_and_after_hours_belong_to_same_day():
    assert market_date_for(at(THU, 9, 30)) == THU
    assert market_date_for(at(THU, 16, 28)) == THU
    assert market_date_for(at(THU, 23, 59)) == THU


def test_weekend_belongs_to_friday():
    assert market_date_for(at(SAT, 12)) == FRI
    assert market_date_for(at(MON, 8)) == FRI


def test_holiday_is_skipped():
    assert market_date_for(at(THU, 8), holidays={WED}) == date(2026, 9, 29)
    assert market_date_for(at(THU, 12), holidays={THU}) == WED


def test_midnight_download_is_shifted_on_latest_day():
    dl = at(THU, 0, 20)
    assert resolve_snapshot_date(THU, dl, at(THU, 0, 30), WED) == WED


def test_after_hours_download_is_not_shifted():
    dl = at(THU, 16, 28)
    assert resolve_snapshot_date(THU, dl, at(THU, 16, 40), THU) == THU


def test_old_file_is_never_shifted():
    dl = at(THU, 0, 20)
    assert resolve_snapshot_date(THU, dl, at(FRI, 12), WED) == THU     # > 24 h old


def test_not_shifted_when_inside_date_is_not_the_download_day():
    # file named/dated for an earlier day than it was downloaded: trust it
    assert resolve_snapshot_date(WED, at(THU, 0, 20), at(THU, 0, 30), WED) == WED


def test_not_shifted_when_a_later_snapshot_already_exists():
    # resolved date (WED) is older than data already stored (THU): not the latest day
    assert resolve_snapshot_date(THU, at(THU, 0, 20), at(THU, 0, 30), THU) == THU
