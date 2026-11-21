"""Weekend catch-up rule for the pre/post-market price fetch: runs only if nothing was fetched since Friday 8 PM ET."""
from datetime import datetime
from zoneinfo import ZoneInfo
from etl.yahoo_fetch import ext_weekend_catchup_due

ET = ZoneInfo("America/New_York")


def _t(d, h=0, m=0):
    return datetime(2026, 11, d, h, m, tzinfo=ET)


def test_weekday_never_due():
    assert ext_weekend_catchup_due(_t(20, 21), None) is False   # Fri
    assert ext_weekend_catchup_due(_t(23, 12), None) is False   # Mon


def test_saturday_due_when_friday_8pm_fetch_missed():
    assert ext_weekend_catchup_due(_t(21, 13), _t(20, 17, 0)) is True    # last fetch was Fri 5 PM
    assert ext_weekend_catchup_due(_t(21, 13), None) is True


def test_saturday_not_due_when_friday_8pm_fetch_happened_or_caught_up():
    assert ext_weekend_catchup_due(_t(21, 13), _t(20, 20, 6)) is False   # the Fri 8:05 PM slot ran
    assert ext_weekend_catchup_due(_t(22, 9), _t(21, 13, 15)) is False   # Sunday, already caught up on Saturday


def test_sunday_due_when_nothing_since_friday_8pm():
    assert ext_weekend_catchup_due(_t(22, 9), _t(20, 17, 0)) is True
