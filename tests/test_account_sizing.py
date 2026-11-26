"""Buy / sell amounts are judged one account at a time (etl/account_sizing.py)."""
from etl.account_sizing import account_trade, stock_suppression

MIN, MAX, UNIT = 4000, 12000, 4000


def trade(code, consolidated, held):
    return account_trade(code, consolidated, held, MIN, MAX, UNIT)


def test_sell_some_sells_one_unit_but_stops_at_minimum():
    assert trade("SS", "REDUCE", 7038)[:2] == (0.0, 3038)
    assert trade("SS", "REDUCE", 11000)[:2] == (0.0, 4000)


def test_sell_some_below_minimum_sells_nothing():
    assert trade("SS", "REDUCE", 1078) == (0.0, 0.0, "at or below minimum")
    assert trade("SS", "REDUCE", 0) == (0.0, 0.0, "not held")


def test_sell_all_and_sell_to_minimum():
    assert trade("SA", "REMOVE", 1078)[:2] == (0.0, 1078)
    assert trade("STM", "REDUCE", 11000)[:2] == (0.0, 7000)


def test_buys_follow_the_account_limits():
    assert trade("BS", "INCREASE", 0)[:2] == (8000, 0.0)          # new position: minimum + one unit
    assert trade("BM", "INCREASE", 10000)[:2] == (2000, 0.0)      # never past the maximum
    assert trade("BM", "INCREASE", 13000) == (0.0, 0.0, "at maximum")
    assert trade("BMN", "ADD", 1000)[:2] == (3000, 0.0)           # fill to minimum


def test_hold_has_no_amount():
    assert trade("HOLD", "REDUCE", 9000) == (0.0, 0.0, None)


def _accts(*held):
    return [{"held": h, "min": MIN, "max": MAX} for h in held]


def test_suppressed_only_when_every_account_has_nothing_to_do():
    # 13k in one account is under any added-up maximum, but the other account still has room
    assert stock_suppression("INCREASE", True, _accts(13000, 0)) is None
    assert stock_suppression("INCREASE", True, _accts(13000, 12000)).startswith("AT CEILING")
    assert stock_suppression("ADD", True, _accts(5000, 0)) is None
    assert stock_suppression("ADD", True, _accts(5000, 4000)).startswith("ALREADY ESTABLISHED")
    assert stock_suppression("REDUCE", True, _accts(3000, 3000)).startswith("AT FLOOR")
    assert stock_suppression("REDUCE", True, _accts(3000, 9000)) is None
