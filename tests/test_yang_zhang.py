"""
tests/test_yang_zhang.py -- TASK_133 Phase 8.2.

Pure-Python, no DB. Covers etl/derive_market_stat.py::_yang_zhang /
_yz_daily_terms: known-input vectors, constant-price -> 0, the k coefficient
at n=10/21/63, and NULL on insufficient data (spec 3.1 guard: never
substitute a shorter window).
"""
import math
import statistics
from datetime import date, timedelta

from etl.derive_market_stat import _yang_zhang, _yz_daily_terms


def _flat_rows(n_days: int, price: float = 100.0):
    rows = []
    d = date(2026, 1, 1)
    for i in range(n_days):
        rows.append({
            "as_of_date": d + timedelta(days=i),
            "open_price": price, "high_price": price,
            "low_price": price, "last_price": price,
        })
    return rows


def test_constant_price_yields_zero_vol():
    """A flat OHLC series has every log-return term = 0 -> sigma_YZ = 0."""
    rows = _flat_rows(30)
    terms = _yz_daily_terms(rows)
    # First day has no prior close to form the overnight term -> 29 terms.
    assert len(terms) == 29
    sigma = _yang_zhang(terms, 21)
    assert sigma is not None
    assert abs(sigma) < 1e-9


def test_insufficient_data_returns_none_not_a_shorter_window():
    """Fewer than n clean observations -> None, never a smaller window."""
    terms = [(date(2026, 1, i + 1), 0.001, 0.001, 0.0001) for i in range(5)]
    assert _yang_zhang(terms, 21) is None
    assert _yang_zhang(terms, 10) is None
    assert _yang_zhang(terms, 5) is not None  # exactly n=5 IS enough


def test_k_coefficient_n10_21_63():
    """Isolate k by zeroing var_o/var_rs and driving var_c to a known
    sample-variance value; sigma_YZ must then equal sqrt(k*var_c*252)*100
    exactly, for each spec-called-out window length."""
    for n in (10, 21, 63):
        expected_k = 0.34 / (1.34 + (n + 1) / (n - 1))
        vals = [1.0 if i % 2 == 0 else -1.0 for i in range(n)]
        var_c = statistics.variance(vals)
        terms = [(date(2026, 1, 1), 0.0, v, 0.0) for v in vals]
        sigma = _yang_zhang(terms, n)
        expected_variance = expected_k * var_c
        expected_sigma = math.sqrt(expected_variance) * math.sqrt(252) * 100.0
        assert sigma is not None
        assert abs(sigma - expected_sigma) < 1e-6, (n, sigma, expected_sigma)


def test_yz_daily_terms_skips_bad_ohlc_and_resets_prev_close():
    rows = _flat_rows(5)
    rows[2]["low_price"] = 0  # invalid day -- skipped, breaks the prev_close chain
    terms = _yz_daily_terms(rows)
    # day0->no prev, day1 ok, day2 invalid (skipped), day3 has no valid
    # prev_close (day2 was invalid) so it's skipped too, day4 ok.
    assert len(terms) == 2
