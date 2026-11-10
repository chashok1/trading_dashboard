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


# ---- hedge-cycle gauges (2026-11-05) ----
from etl.derive_risk_dial import _g_event_hedging, _g_hedge_removal_rally, _g_rally_fuel_spent

_TH = {"rd_hedge_event_days": 5.0, "rd_hedge_9d_rise_pct": 40.0, "rd_hedge_event_rise_pct": 10.0, "rd_hedge_vix_drop_pct": 15.0, "rd_hedge_fuel_days": 5.0}


def _hctx(hist, **kw):
    c = {"hedge_th": _TH, "hedge_hist": hist, "vix9d_hist": [], "quote": {}, "event_next": None, "event_always": ["Fed Meeting"]}
    c.update(kw)
    return c


def test_removal_rally_fires_on_vix_drop_with_spx_up():
    f, _, _ = _g_hedge_removal_rally(_hctx([{"vix": 16.7, "spx": 7689}, {"vix": 20.8, "spx": 7569}]))
    assert f is True


def test_removal_rally_not_when_spx_down_or_vix_drop_small():
    assert _g_hedge_removal_rally(_hctx([{"vix": 16.0, "spx": 7500}, {"vix": 20.0, "spx": 7569}]))[0] is False
    assert _g_hedge_removal_rally(_hctx([{"vix": 19.0, "spx": 7700}, {"vix": 20.0, "spx": 7569}]))[0] is False


def test_removal_rally_unavailable_without_history():
    assert _g_hedge_removal_rally(_hctx([]))[0] is None


def test_event_hedging_fires_on_9d_rise_without_event():
    c = _hctx([], vix9d_hist=[22.0, 20, 18, 17, 16, 15.6], quote={"VIX": 24.0})
    assert _g_event_hedging(c)[0] is True


def test_event_hedging_fires_on_event_and_inverted_curve():
    c = _hctx([], vix9d_hist=[22.0, 21, 20, 20, 20, 19.0], quote={"VIX": 18.0}, event_next=("Fed Meeting", "2026-11-08"))
    assert _g_event_hedging(c)[0] is True


def test_event_hedging_non_fed_event_and_inverted_but_no_rise_does_not_fire():
    c = _hctx([], vix9d_hist=[20.0, 20, 20, 20, 20, 20.0], quote={"VIX": 18.0}, event_next=("NFP", "2026-11-08"))
    assert _g_event_hedging(c)[0] is False


def test_event_hedging_fed_fires_without_rise_when_inverted():
    c = _hctx([], vix9d_hist=[20.0, 20, 20, 20, 20, 20.0], quote={"VIX": 18.0}, event_next=("Fed Meeting", "2026-11-08"))
    assert _g_event_hedging(c)[0] is True


def test_event_hedging_quiet():
    c = _hctx([], vix9d_hist=[15.0, 15, 15, 15, 15, 15.0], quote={"VIX": 17.0})
    assert _g_event_hedging(c)[0] is False


def test_fuel_spent_after_rally_when_vix_flat_and_no_new_high():
    # newest first: today VIX up, SPX below the rally-day close; rally was 2 sessions ago
    h = [{"vix": 17.5, "spx": 7600}, {"vix": 17.0, "spx": 7650}, {"vix": 16.7, "spx": 7689}, {"vix": 20.8, "spx": 7569}]
    assert _g_rally_fuel_spent(_hctx(h))[0] is True


def test_fuel_not_spent_when_spx_makes_new_high():
    h = [{"vix": 16.0, "spx": 7720}, {"vix": 17.0, "spx": 7650}, {"vix": 16.7, "spx": 7689}, {"vix": 20.8, "spx": 7569}]
    assert _g_rally_fuel_spent(_hctx(h))[0] is False


def test_fuel_false_with_no_recent_rally():
    h = [{"vix": 17.0, "spx": 7600}, {"vix": 17.0, "spx": 7610}, {"vix": 17.0, "spx": 7620}]
    assert _g_rally_fuel_spent(_hctx(h))[0] is False


def test_event_hedging_cpi_and_nfp_fire_without_rise_when_inverted():
    for cat in ("CPI MoM", "NFP"):
        c = _hctx([], vix9d_hist=[20.0, 20, 20, 20, 20, 20.0], quote={"VIX": 18.0}, event_next=(cat, "2026-11-08"),
                  event_always=["Fed Meeting", "CPI MoM", "NFP"])
        assert _g_event_hedging(c)[0] is True


def test_event_hedging_pce_needs_rise_unless_listed():
    c = _hctx([], vix9d_hist=[20.0, 20, 20, 20, 20, 20.0], quote={"VIX": 18.0}, event_next=("PCE", "2026-11-08"),
              event_always=["Fed Meeting", "CPI MoM", "NFP"])
    assert _g_event_hedging(c)[0] is False
    c["event_always"] = ["PCE"]
    assert _g_event_hedging(c)[0] is True


# --- 2026-11-09: "Markets at records" (pure, no DB) -------------------------------------------------------------------
def _rec(key, price, high, near=2.0, use_low=False, low=None):
    return {"key": key, "label": key.upper(), "price": price, "high": high, "high_date": "2026-10-06",
            "low": low, "low_date": "2020-01-01", "near_pct": near, "use_low": use_low}


def test_markets_at_records_fires_only_within_distance():
    from etl.derive_risk_dial import _g_markets_at_records
    far = _g_markets_at_records({"records": [_rec("spx", 95.0, 100.0)]})
    near = _g_markets_at_records({"records": [_rec("spx", 99.0, 100.0)]})
    past = _g_markets_at_records({"records": [_rec("spx", 101.0, 100.0)]})
    assert far[0] is False and near[0] is True and past[0] is True


def test_markets_at_records_low_side_only_when_enabled_and_no_data_is_none():
    from etl.derive_risk_dial import _g_markets_at_records
    off = _g_markets_at_records({"records": [_rec("vix", 9.2, 80.0, near=10, use_low=False, low=9.0)]})
    on = _g_markets_at_records({"records": [_rec("vix", 9.2, 80.0, near=10, use_low=True, low=9.0)]})
    assert off[0] is False and on[0] is True
    assert _g_markets_at_records({"records": []})[0] is None
