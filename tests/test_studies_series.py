"""Action-popup studies series (MACD, Volume rate of change): behaviour only, pure Python (no DB)."""
from datetime import date, timedelta

from api.routers.dash import _ema, _studies_series


def _rows(closes, vols):
    d0 = date(2026, 1, 1)
    return [(d0 + timedelta(days=i), c, v, 50.0, 0.3, 1.0) for i, (c, v) in enumerate(zip(closes, vols))]


def test_ema_of_constant_is_constant():
    assert all(abs(x - 5.0) < 1e-9 for x in _ema([5.0] * 30, 12))


def test_ema_none_carries_previous_value():
    assert _ema([1.0, None, 3.0], 2)[1] == 1.0


def test_flat_closes_give_zero_macd_and_hist():
    out = _studies_series(_rows([10.0] * 60, [100.0] * 60), 20)
    assert len(out) == 20
    assert all(abs(p["macd"]) < 1e-9 and abs(p["hist"]) < 1e-9 for p in out)


def test_rising_closes_give_positive_macd():
    out = _studies_series(_rows([10.0 + i for i in range(80)], [100.0] * 80), 10)
    assert out[-1]["macd"] > 0


def test_vroc_is_percent_change_vs_14_rows_back():
    vols = [100.0] * 20 + [50.0]
    assert abs(_studies_series(_rows([10.0] * 21, vols), 1)[0]["vroc"] - (-50.0)) < 1e-9


def test_vroc_is_none_without_a_volume_14_rows_back():
    vols = [100.0] * 6 + [None] + [100.0] * 14
    assert _studies_series(_rows([10.0] * 21, vols), 21)[20]["vroc"] is None


def test_spike_study_up_then_down_markers():
    from api.routers.dash import _spike_study
    vals = [1.0] * 70 + [1.3] + [1.2] + [0.5] * 3
    avg, thr, mk = _spike_study(vals)
    assert mk[70] == "up" and mk[71] is None
    assert mk[72] == "down"
    assert abs(thr[70] - avg[70] * 1.15) < 1e-9


def test_spike_study_needs_enough_history():
    from api.routers.dash import _spike_study
    avg, thr, mk = _spike_study([1.0] * 10 + [5.0])
    assert avg[-1] is None and mk[-1] is None
