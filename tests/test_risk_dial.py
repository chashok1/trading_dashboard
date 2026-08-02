"""
tests/test_risk_dial.py -- TASK_133 Phase 8.2.

Pure-Python, no DB. Covers etl/derive_risk_dial.py::compute_budget /
_risk_label: weight arithmetic, None gauges excluded from both numerator and
denominator, and every budget->label boundary (29/30, 54/55, 79/80).
"""
from etl.derive_risk_dial import compute_budget, _risk_label, _g_oil_shock, _g_credit_stress


def _g(key, fired, weight):
    return {"key": key, "label": key, "fired": fired, "weight": weight, "value": None, "detail": None}


def test_weight_arithmetic_basic():
    gauges = [_g("a", True, 3), _g("b", False, 1), _g("c", True, 2)]
    summary = compute_budget(gauges)
    # evaluable = 6, fired = 5 -> budget = round(100*(1-5/6)) = 17
    assert summary["evaluable_weight"] == 6
    assert summary["fired_weight"] == 5
    assert summary["risk_budget"] == round(100 * (1 - 5 / 6))


def test_none_gauges_excluded_from_numerator_and_denominator():
    """A gauge that can't be evaluated (fired=None, e.g. missing data) must
    not count toward evaluable_weight OR fired_weight (spec 3.5)."""
    gauges = [_g("a", True, 3), _g("b", None, 100), _g("c", False, 2)]
    summary = compute_budget(gauges)
    assert summary["evaluable_weight"] == 5   # the weight=100 None gauge excluded
    assert summary["fired_weight"] == 3
    assert summary["risk_budget"] == round(100 * (1 - 3 / 5))


def test_all_gauges_none_yields_none_budget():
    gauges = [_g("a", None, 3), _g("b", None, 2)]
    summary = compute_budget(gauges)
    assert summary["evaluable_weight"] == 0
    assert summary["risk_budget"] is None
    assert summary["risk_label"] is None


def test_no_gauges_fired_yields_full_budget():
    gauges = [_g("a", False, 3), _g("b", False, 2)]
    summary = compute_budget(gauges)
    assert summary["risk_budget"] == 100
    assert summary["risk_label"] == "CLEAR"


def test_risk_label_boundaries():
    assert _risk_label(80) == "CLEAR"
    assert _risk_label(79) == "CAUTION"
    assert _risk_label(55) == "CAUTION"
    assert _risk_label(54) == "DEFENSIVE"
    assert _risk_label(30) == "DEFENSIVE"
    assert _risk_label(29) == "NOT INVESTABLE"
    assert _risk_label(0) == "NOT INVESTABLE"
    assert _risk_label(None) is None


# ---------------------------------------------------------------------------
# TASK_134 B.1 -- multi-leg gauge detail must lead with the leg that fired.
# ---------------------------------------------------------------------------

def test_oil_shock_fires_on_ovx_leg_only_does_not_mention_wti():
    """WTI at 39% of range is mid-range and does not fire; OVX at 63 (above
    the 50 threshold) does. The bug reported "WTI 39% of range; OVX 63" --
    leading with the leg that never fired. Fixed detail must mention only
    OVX."""
    ctx = {
        "rr": {"/CL": {"lrr": 100.0, "trr": 200.0, "outlook": None}},
        "quote": {"/CL": 139.0, "OVX:CGI": 63.0},
        "vol": {"OVX:CGI": {"low": 20.0, "high": 50.0}},
    }
    fired, value, detail = _g_oil_shock(ctx)
    assert fired is True
    assert "OVX" in detail
    assert "WTI" not in detail


def test_oil_shock_both_legs_fire_mentions_both():
    ctx = {
        "rr": {"/CL": {"lrr": 100.0, "trr": 200.0, "outlook": None}},
        "quote": {"/CL": 191.0, "OVX:CGI": 63.0},
        "vol": {"OVX:CGI": {"low": 20.0, "high": 50.0}},
    }
    fired, value, detail = _g_oil_shock(ctx)
    assert fired is True
    assert "WTI" in detail and "OVX" in detail


def test_credit_stress_fires_on_hyg_leg_only_does_not_mention_oas():
    ctx = {
        "rr": {"HYG": {"lrr": 100.0, "trr": 200.0, "outlook": None}},
        "quote": {"HYG": 110.0},
        "vol": {},
        "hy_oas": None,
    }
    fired, value, detail = _g_credit_stress(ctx)
    assert fired is True
    assert "HYG" in detail
    assert "OAS" not in detail
