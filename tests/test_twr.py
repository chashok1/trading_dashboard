"""
tests/test_twr.py -- TASK_133 Phase 8.2.

Pure-Python, no DB. Covers etl/derive_category_perf.py::_twr_window: chain-
linking, a flow-only day produces r_t=0, the 25% guard trips and does not
compound, a no-flow window equals the naive V_end/V_start-1 ratio, and
(round 2 / Part A addition) the qty-gap guard forces r_t=0 + 'suspect' on a
day with an unexplained symbol-level gap, independent of magnitude.
"""
from datetime import date, timedelta

from etl.derive_category_perf import _twr_window


def _calendar(n, start=date(2026, 7, 1)):
    return [start + timedelta(days=i) for i in range(n)]


def test_chain_linking_matches_manual_product():
    cal = _calendar(4)
    by_date = {
        cal[0]: {"v": 100.0, "flow": 0.0, "gap_symbols": []},
        cal[1]: {"v": 110.0, "flow": 0.0, "gap_symbols": []},   # r=+10%
        cal[2]: {"v": 99.0,  "flow": 0.0, "gap_symbols": []},   # r=-10%
        cal[3]: {"v": 108.9, "flow": 0.0, "gap_symbols": []},   # r=+10%
    }
    twr, conf, detail = _twr_window(by_date, cal, 3)
    expected = (1.10 * 0.90 * 1.10) - 1.0
    assert abs(twr - expected) < 1e-9
    assert conf == "green"
    assert detail["day_count"] == 3


def test_flow_only_day_produces_zero_return():
    """A day where the whole value change is explained by netflow (e.g. a
    deposit) must contribute r_t=0, not register as performance."""
    cal = _calendar(2)
    by_date = {
        cal[0]: {"v": 100.0, "flow": 0.0, "gap_symbols": []},
        cal[1]: {"v": 150.0, "flow": 50.0, "gap_symbols": []},  # +50 flow, 0 return
    }
    twr, conf, detail = _twr_window(by_date, cal, 1)
    assert abs(twr - 0.0) < 1e-9
    assert conf == "green"
    assert detail["netflow_total"] == 50.0


def test_25pct_guard_trips_and_does_not_compound():
    cal = _calendar(2)
    by_date = {
        cal[0]: {"v": 100.0, "flow": 0.0, "gap_symbols": []},
        cal[1]: {"v": 140.0, "flow": 0.0, "gap_symbols": []},  # +40% -- flow artefact
    }
    twr, conf, detail = _twr_window(by_date, cal, 1)
    assert abs(twr - 0.0) < 1e-9   # guard forces r_t=0, not +40%
    assert conf == "suspect"


def test_no_flow_window_equals_naive_ratio():
    cal = _calendar(6)
    values = [1000.0, 1010.0, 990.0, 1005.0, 1020.0, 1030.0]
    by_date = {cal[i]: {"v": values[i], "flow": 0.0, "gap_symbols": []} for i in range(6)}
    twr, conf, detail = _twr_window(by_date, cal, 5)
    naive = values[-1] / values[0] - 1.0
    assert abs(twr - naive) < 1e-9
    assert conf == "green"


def test_gap_symbols_force_zero_and_suspect_regardless_of_magnitude():
    """Round 2 / Part A: an unexplained symbol-level qty gap must force
    r_t=0 and 'suspect' even when the day's |r_t| is small (well under the
    25% guard) -- this is exactly the case the 25% guard alone misses."""
    cal = _calendar(2)
    by_date = {
        cal[0]: {"v": 100000.0, "flow": 0.0, "gap_symbols": []},
        # +3% day -- comfortably under the 25% guard, but flagged by a gap.
        cal[1]: {"v": 103000.0, "flow": 0.0, "gap_symbols": ["CRAK", "DESK"]},
    }
    twr, conf, detail = _twr_window(by_date, cal, 1)
    assert abs(twr - 0.0) < 1e-9
    assert conf == "suspect"
    assert detail["gap_days"][0]["symbols"] == ["CRAK", "DESK"]
