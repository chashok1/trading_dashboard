"""Behaviour tests for the Factor Weights calculation core (pure Python, no database)."""
import numpy as np

from etl import factor_lab_core as f


def test_bucket_ties_go_to_lower_bucket_and_missing_is_na():
    assert f.bucket_rsi(30.0) == "Oversold"
    assert f.bucket_rsi(30.01) == "Neutral"
    assert f.bucket_rsi(70.0) == "Neutral"
    assert f.bucket_rsi(None) == f.NA
    assert f.bucket_sign(0.0) == "Down"
    assert f.bucket_sign(float("nan")) == f.NA


def test_range_position_zones():
    # LRR 100, TRR 200
    assert f.bucket_range_position(90, 100, 200) == "Below LRR"
    assert f.bucket_range_position(125, 100, 200) == "LRR zone"   # exactly 25% -> lower bucket
    assert f.bucket_range_position(150, 100, 200) == "Mid"
    assert f.bucket_range_position(170, 100, 200) == "Upper"
    assert f.bucket_range_position(190, 100, 200) == "TRR zone"
    assert f.bucket_range_position(210, 100, 200) == "Above TRR"
    assert f.bucket_range_position(150, None, 200) == f.NA


def test_forward_returns_use_calendar_and_never_carry_forward():
    closes = [100.0] + [None] * 4 + [110.0] + [None] * 4 + [120.0]
    out = f.forward_outcomes(closes, 0, horizons=(5, 10))
    assert abs(out["ret_5"] - 0.10) < 1e-12
    assert abs(out["ret_10"] - 0.20) < 1e-12
    closes[5] = None
    out = f.forward_outcomes(closes, 0, horizons=(5, 10))
    assert out["ret_5"] is None          # missing price is left empty, not filled


def test_frozen_price_and_data_errors_are_dropped():
    frozen = [100.0] * 7
    assert f.forward_outcomes(frozen, 0, horizons=(5,))["skip_reason"] == "frozen_price"
    huge = [100.0, 101, 102, 103, 104, 250.0]
    assert f.forward_outcomes(huge, 0, horizons=(5,))["ret_5"] is None
    jump = [100.0, 101, 160.0, 161, 162, 163]
    assert f.forward_outcomes(jump, 0, horizons=(5,))["ret_5"] is None


def test_sell_sign_is_flipped():
    assert abs(f.excess_return(-0.05, 0.01, "SELL") - 0.06) < 1e-12
    assert abs(f.excess_return(-0.05, 0.01, "BUY") + 0.06) < 1e-12
    assert f.excess_return(None, 0.01, "BUY") is None


def test_episode_gap_rule():
    assert f.build_episodes([1, 2, 3, 9, 10]) == [0, 0, 0, 1, 1]     # gap of 6 starts a new one
    assert f.build_episodes([1, 2, 7]) == [0, 0, 0]                   # gap of 5 does not


def test_trust_flag_cases():
    base = dict(n_episodes=120, n_stocks=60)
    assert f.trust_flag(2.0, 0.5, 3.0, w_early=1.0, w_late=2.0, **base) == "Trust (helps)"
    assert f.trust_flag(-2.0, -3.0, -0.5, w_early=-1.0, w_late=-2.0, **base) == "Trust (hurts)"
    assert f.trust_flag(1.0, -0.5, 2.0, w_early=1.0, w_late=1.0, **base) == "No effect"
    assert f.trust_flag(2.0, 0.5, 3.0, w_early=-1.0, w_late=2.0, **base) == "Unstable"
    assert f.trust_flag(2.0, 0.5, 3.0, n_episodes=10, n_stocks=60, w_early=1, w_late=1) == "Too few"
    assert f.trust_flag(2.0, 0.5, 3.0, w_early=1, w_late=1, contradicts_call=True, **base) == "Contradicts the call"


def test_ridge_recovers_planted_effect_and_interval_excludes_zero():
    rng = np.random.default_rng(0)
    n = 1500
    X = (rng.random((n, 3)) < 0.3).astype(float)
    y = 3.0 * X[:, 0] + 0.0 * X[:, 1] + rng.normal(0, 2.0, n)
    beta = f.ridge_fit(X, y, alpha=10.0)
    assert abs(beta[0] - 3.0) < 0.5
    assert abs(beta[1]) < 0.6
    stocks = rng.integers(0, 80, n)
    weeks = rng.integers(0, 20, n)
    lo, hi = f.bootstrap_interval(X, y, stocks, weeks, alpha=10.0, reps=100)
    assert lo[0] > 0
    assert lo[1] < 0 < hi[1]


def test_walk_forward_passes_real_signal_and_fails_noise():
    rng = np.random.default_rng(1)
    good = []
    noise = []
    for _ in range(5):
        pred = rng.normal(size=120)
        good.append({"pred": pred, "actual": pred + rng.normal(0, 1.0, 120)})
        noise.append({"pred": pred, "actual": rng.normal(size=120)})
    assert f.walk_forward_pass(good, reps=200)["passed"] is True
    assert f.walk_forward_pass(noise, reps=200)["passed"] is False
    assert f.walk_forward_pass(good[:2], reps=50)["passed"] is False    # too few test months
