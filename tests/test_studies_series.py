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


def test_spike_study_flat_series_has_no_arrows_and_ratio_one():
    from api.routers.dash import _spike_study
    sm, white, red, ratio, mk = _spike_study([1.0] * 100)
    assert not any(mk) and abs(ratio[-1] - 1.0) < 1e-9
    assert abs(white[-1] - 1.0) < 1e-9 and abs(red[-1] - 1.15) < 1e-9


def test_spike_study_spike_then_normalize():
    from api.routers.dash import _spike_study
    vals = [1.0] * 80 + [2.0] * 8 + [0.5] * 40
    mk = _spike_study(vals)[4]
    assert mk.count("up") == 1 and mk.count("down") == 1
    assert mk.index("up") < mk.index("down")


def test_spike_study_normal_threshold_scales_the_white_line_for_hv():
    from api.routers.dash import _spike_study
    white = _spike_study([1.0] * 100, 63, 1.15, 0.95, 3, 5)[1]
    assert abs(white[-1] - 0.95) < 1e-9


def test_spike_study_needs_enough_history():
    from api.routers.dash import _spike_study
    sm, white, red, ratio, mk = _spike_study([1.0] * 10 + [5.0])
    assert white[-1] is None and ratio[-1] is None and mk[-1] is None


def test_volume_averages_10d_and_63d():
    out = _studies_series(_rows([10.0] * 100, [100.0] * 100), 5)
    assert abs(out[-1]["vol_avg10"] - 100.0) < 1e-9 and abs(out[-1]["vol_avg63"] - 100.0) < 1e-9


def test_volume_average_ignores_gaps_but_needs_enough_data():
    vols = [100.0] * 100
    vols[95] = None
    assert abs(_studies_series(_rows([10.0] * 100, vols), 1)[0]["vol_avg10"] - 100.0) < 1e-9
    assert _studies_series(_rows([10.0] * 30, [100.0] * 30), 1)[0]["vol_avg63"] is None
