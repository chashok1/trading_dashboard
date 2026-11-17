"""drv_vol_spike: the TOS spike study, stress flag and held-symbol Watch alerts. Behaviour only, pure Python (fake session, no DB)."""
from datetime import date, timedelta

from etl import vol_spike as vs


def _dates(n, start=date(2026, 1, 5)):
    return [start + timedelta(days=i) for i in range(n)]


# ── spike_series -----------------------------------------------------------------------------------------------------
def test_flat_series_never_spikes():
    s = vs.spike_series([1.0] * 120)
    assert not any(s["mk"]) and not any(s["was"]) and abs(s["ratio"][-1] - 1.0) < 1e-9


def test_spike_then_normalize_in_order():
    s = vs.spike_series([1.0] * 80 + [2.0] * 8 + [0.5] * 40)
    assert s["mk"].count("up") == 1 and s["mk"].count("down") == 1
    assert s["mk"].index("up") < s["mk"].index("down")
    assert s["was"][s["mk"].index("up")] is True and s["was"][-1] is False


def test_exclusion_keeps_the_average_from_chasing_the_spike():
    # while spiked the average switches to the full (normal) average, so the red line is above the pre-spike one
    s = vs.spike_series([1.0] * 80 + [2.0] * 8)
    i = s["mk"].index("up")
    assert s["red"][i] < s["red"][-1]


# ── stress ------------------------------------------------------------------------------------------------------------
def test_stress_needs_spike_and_falling_price():
    assert vs.is_stress(True, 3, -4.0) is True
    assert vs.is_stress(True, 3, -1.0) is False          # price not falling enough
    assert vs.is_stress(False, 30, -9.0) is False        # no spike
    assert vs.is_stress(False, 2, -4.0) is True          # a fresh arrow still counts as spiked
    assert vs.is_stress(True, 3, None) is False


def test_build_rows_flags_stress_when_price_drops_during_a_spike():
    n = 130
    iv = [1.0] * 80 + [2.0] * 50
    px = [100.0] * 100 + [100.0 - 2 * i for i in range(30)]
    rows = vs.build_rows(_dates(n), px, iv, [1.0] * n)
    assert any(r["stress"] for r in rows)
    assert not any(r["stress"] for r in rows[:80])
    assert all(r["px_chg_5d"] is None for r in rows[:5])


def test_build_rows_carries_gaps_forward():
    iv = [1.0] * 100
    iv[50] = None
    rows = vs.build_rows(_dates(100), [10.0] * 100, iv, [1.0] * 100)
    assert rows[50]["iv"] == 1.0
