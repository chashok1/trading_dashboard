"""Trade-date helpers (api/_recent_buys.py). Pure, no DB."""
from datetime import date

from api._recent_buys import is_today, trading_days_since

THU = date(2026, 10, 1)


def test_same_day_is_today():
    assert is_today(THU, THU)
    assert trading_days_since(THU, THU) == 0


def test_yesterday_and_none_are_not_today():
    assert not is_today(date(2026, 9, 30), THU)
    assert not is_today(None, THU)


def test_counts_weekdays_only():
    # Fri 9/25 -> Thu 10/1 = Mon, Tue, Wed, Thu
    assert trading_days_since(date(2026, 9, 25), THU) == 4
    assert trading_days_since(date(2026, 10, 2), THU) == -1


from api._recent_buys import classify_today


def test_classify_new_position_and_adding_more():
    assert classify_today(0, 100, 0) == "bought_new"
    assert classify_today(50, 100, 0) == "bought_more"


def test_classify_selling_some_vs_all():
    assert classify_today(100, 0, 30) == "sold_some"
    assert classify_today(100, 0, 100) == "sold_all"
    assert classify_today(100, 0, 150) == "sold_all"      # stale pre: never negative-some


def test_classify_mixed_day_follows_the_net():
    assert classify_today(200, 100, 75) == "bought_more"   # TXG-style
    assert classify_today(75, 10, 35) == "sold_some"       # IGV-style
    assert classify_today(100, 40, 40) == "traded"


def test_classify_falls_back_to_snapshot_when_no_transactions():
    assert classify_today(100, 0, 0, snap_post=60) == "sold_some"
    assert classify_today(100, 0, 0, snap_post=0) == "sold_all"
    assert classify_today(0, 0, 0, snap_post=25) == "bought_new"
    assert classify_today(100, 0, 0, snap_post=100) is None
    assert classify_today(100, 0, 0) is None


from api._recent_buys import flags_apply, prev_trading_day

FRI, MON = date(2026, 10, 2), date(2026, 10, 5)


def test_prev_trading_day_skips_weekends_and_holidays():
    assert prev_trading_day(MON) == FRI
    assert prev_trading_day(THU) == date(2026, 9, 30)
    assert prev_trading_day(THU, holidays={date(2026, 9, 30)}) == date(2026, 9, 29)


def test_flags_apply_on_live_screen_only():
    assert flags_apply(THU, THU)                        # anchor caught up (after 8 PM TOSD)
    assert flags_apply(date(2026, 9, 30), THU)          # anchor lagging during the session
    assert not flags_apply(date(2026, 9, 29), THU)      # older date from the picker
