"""Close-to-close realized vol used by drv_market_stat (pure Python, no DB)."""
import math
import statistics

from etl.derive_market_stat import _close_returns, _close_to_close


def _rows(prices):
    return [{"last_price": p} for p in prices]


def test_flat_prices_give_zero_vol():
    assert abs(_close_to_close(_close_returns(_rows([100.0] * 30)), 21)) < 1e-9


def test_matches_sample_stdev_annualized():
    prices = [100, 101, 99, 102, 100, 103, 101, 104, 102, 105, 103]
    rets = _close_returns(_rows(prices))
    expected = statistics.stdev(rets[-10:]) * math.sqrt(252) * 100
    assert abs(_close_to_close(rets, 10) - expected) < 1e-9


def test_none_when_fewer_than_n_returns_never_a_shorter_window():
    rets = _close_returns(_rows([100, 101, 102, 101]))
    assert len(rets) == 3
    assert _close_to_close(rets, 10) is None


def test_bad_closes_are_skipped():
    rets = _close_returns(_rows([100, None, 0, 101, 102]))
    assert len(rets) == 2
