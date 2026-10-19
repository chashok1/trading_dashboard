"""Quad market check: pure functions of etl/derive_quad_check.py (no DB)."""
import pytest

from etl.derive_quad_check import (
    factor_state, label_of, market_quads, meter, quad_fit, read_vs, sign_by_band, target_quad, transition_risk,
)


def test_sign_by_band():
    assert sign_by_band(2.5, 1) == 1
    assert sign_by_band(-2.5, 1) == -1
    assert sign_by_band(0.4, 1) == 0
    assert sign_by_band(None, 1) is None


def test_factor_state_needs_two_agreeing_checks():
    assert factor_state([1, 1, 0], 2) == 1
    assert factor_state([-1, -1, 1], 2) == -1
    assert factor_state([1, -1, 0], 2) == 0           # no two agree -> mixed
    assert factor_state([1, 1], 2) == 1               # with two checks both must agree
    assert factor_state([1, -1], 2) == 0


def test_factor_state_missing_when_too_few_checks():
    assert factor_state([1, None, None], 2) is None
    assert factor_state([None, None], 2) is None
    assert factor_state([-1], 1) == -1                # single-check factor (jobless claims)


def test_meter_weighted_and_coverage():
    score, cov = meter([(1, 1), (-1, 1), (1, 2)], 0.6)
    assert score == 50 and cov == 1.0
    score, cov = meter([(1, 1), (None, 3)], 0.6)      # only 25% of the weight has data
    assert score is None and cov == pytest.approx(0.25)
    assert meter([(1, 0)], 0.6) == (None, 0.0)       # zero-weight factors never vote


def test_read_vs_expected_arrow():
    assert read_vs(1, 40, 20) == "with"
    assert read_vs(1, 5, 20) == "unclear"
    assert read_vs(1, -30, 20) == "against"
    assert read_vs(-1, -30, 20) == "with"            # Quad 3/4 expect growth down
    assert read_vs(1, 20, 20) == "with"              # a tie at the band counts as with
    assert read_vs(1, None, 20) is None


def test_risk_label_and_target_cover_the_moves():
    # Quad 2 with growth flat and inflation firm -> watch, leaning to Quad 3 (growth flips)
    risk = transition_risk(2, 0, 80)
    assert 40 <= risk < 60 and label_of(risk) == "WATCH"
    assert target_quad(2, "unclear", "with") == 3
    # both meters against Quad 2 -> the diagonal move to Quad 4
    assert target_quad(2, "against", "against") == 4
    assert label_of(transition_risk(2, -60, -60)) == "TRANSITION"
    # inflation turning down while growth holds -> Quad 1
    assert target_quad(2, "with", "against") == 1
    # holding
    assert label_of(transition_risk(2, 60, 60)) == "HOLDING"
    assert label_of(None) == "NO_DATA"


def test_market_quads_and_fit():
    assert market_quads(50, 50, 20) == [2]
    assert market_quads(5, 60, 20) == [2, 3]          # growth unclear -> two Quads
    assert market_quads(-60, -60, 20) == [4]
    fit = quad_fit(5, 60, 40)
    assert sum(fit.values()) in (99, 100, 101)        # rounding
    assert max(fit, key=fit.get) in ("2", "3")
    assert fit["4"] < fit["2"] and fit["1"] < fit["3"]
