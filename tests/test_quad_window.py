"""
Tests for etl.derive_macro — sliding look-ahead window pure functions
(TASK_126, agent-tasks/TASK_126_quad_lookahead_window.md).

Covers:
  - window_weights: overlap weights across month boundaries, mid-month slide
    (early vs late July mix), decay, truncation + coverage
  - near_far_split: nearest month vs weighted rest of window
  - tracking_tag: nearest-first match on technical direction sign
  - to_action: sign-agreement override redefined on near/far
  - build_effective_distribution: weighted quad-pct blend

Pure-Python, no DB — runs with no setup.

Run:
    pytest tests/test_quad_window.py -v
"""
from __future__ import annotations

from datetime import date

import pytest

from etl.derive_macro import (
    build_effective_distribution,
    near_far_split,
    to_action,
    tracking_tag,
    window_weights,
)


# ─── window_weights: month-boundary overlap + normalization ───────────────

def test_window_weights_single_month_full_coverage():
    # Anchor + a 10-day window fully inside one month -> single month, w=1.0
    d = date(2026, 7, 5)
    months = [(2026, 7)]
    weighted, coverage = window_weights(d, months, h=10)
    assert weighted == [((2026, 7), 1.0)]
    assert coverage == 100.0


def test_window_weights_crosses_month_boundary():
    # July has 31 days; anchor July 15 + 60-day window -> spans Jul/Aug/Sep.
    d = date(2026, 7, 15)
    months = [(2026, 7), (2026, 8), (2026, 9), (2026, 10)]
    weighted, coverage = window_weights(d, months, h=60)
    assert coverage == pytest.approx(100.0, abs=0.01)
    keys = [k for k, _w in weighted]
    assert keys == [(2026, 7), (2026, 8), (2026, 9)]
    # Weights normalized, sum to 1, nearest-first ordering
    total = sum(w for _k, w in weighted)
    assert total == pytest.approx(1.0, abs=1e-9)
    # July 15->31 = 17 days remaining (incl. 15th), Aug = 31 days,
    # remaining 60-17-31=12 days land in September (Sep 1-12)
    jul_days, aug_days, sep_days = 17, 31, 12
    denom = jul_days + aug_days + sep_days
    assert weighted[0][1] == pytest.approx(jul_days / denom, abs=1e-6)
    assert weighted[1][1] == pytest.approx(aug_days / denom, abs=1e-6)
    assert weighted[2][1] == pytest.approx(sep_days / denom, abs=1e-6)


def test_window_weights_mid_month_slide_early_vs_late_july():
    # Early-July anchor -> July dominates the mix; late-July anchor -> August
    # takes over. Both use the same 60-day window and month set.
    months = [(2026, 7), (2026, 8), (2026, 9), (2026, 10)]
    early, _ = window_weights(date(2026, 7, 2), months, h=60)
    late, _ = window_weights(date(2026, 7, 28), months, h=60)

    early_map = dict(early)
    late_map = dict(late)
    assert early_map[(2026, 7)] > late_map[(2026, 7)]
    # Late anchor should have less/no July weight (only 4d) than August's share
    assert late_map[(2026, 7)] < late_map.get((2026, 8), 0)


def test_window_weights_decay_favors_near_days():
    d = date(2026, 7, 1)
    months = [(2026, 7), (2026, 8)]
    flat, _ = window_weights(d, months, h=60, decay_hl=0)
    decayed, _ = window_weights(d, months, h=60, decay_hl=15)
    flat_map, decay_map = dict(flat), dict(decayed)
    # Decay concentrates weight on the nearer month (July) vs the flat window
    assert decay_map[(2026, 7)] > flat_map[(2026, 7)]


def test_window_weights_truncation_and_low_coverage_fallback_trigger():
    # Only July supplied, but window wants Jul+Aug+Sep -> partial coverage
    d = date(2026, 7, 15)
    months = [(2026, 7)]  # Aug/Sep missing entirely
    weighted, coverage = window_weights(d, months, h=60)
    assert weighted == [((2026, 7), 1.0)]
    # 17 of 60 days covered
    assert coverage == pytest.approx(17 / 60 * 100, abs=0.1)
    assert coverage < 50.0  # caller's fallback threshold


def test_window_weights_zero_coverage():
    d = date(2026, 7, 15)
    weighted, coverage = window_weights(d, [], h=60)
    assert weighted == []
    assert coverage == 0.0


def test_window_weights_nearest_first_ordering():
    d = date(2026, 1, 20)
    months = [(2026, 3), (2026, 1), (2026, 2)]  # deliberately unsorted input
    weighted, _cov = window_weights(d, months, h=60)
    keys = [k for k, _w in weighted]
    assert keys == [(2026, 1), (2026, 2), (2026, 3)]


# ─── build_effective_distribution ──────────────────────────────────────────

def test_build_effective_distribution_blends_by_weight():
    weighted = [((2026, 7), 0.25), ((2026, 8), 0.75)]
    pcts_by_month = {
        (2026, 7): [1.0, 0.0, 0.0, 0.0],   # 100% quad1
        (2026, 8): [0.0, 0.0, 0.0, 1.0],   # 100% quad4
    }
    eff = build_effective_distribution(weighted, pcts_by_month)
    assert eff == pytest.approx([0.25, 0.0, 0.0, 0.75])
    assert sum(eff) == pytest.approx(1.0)


def test_build_effective_distribution_missing_month_contributes_zero():
    weighted = [((2026, 7), 0.5), ((2026, 8), 0.5)]
    pcts_by_month = {(2026, 7): [1.0, 0.0, 0.0, 0.0]}  # Aug missing
    eff = build_effective_distribution(weighted, pcts_by_month)
    assert eff == pytest.approx([0.5, 0.0, 0.0, 0.0])


# ─── near_far_split ─────────────────────────────────────────────────────────

def test_near_far_split_basic():
    weighted = [((2026, 7), 0.2), ((2026, 8), 0.5), ((2026, 9), 0.3)]
    stance_by_month = {(2026, 7): -1.2, (2026, 8): 2.1, (2026, 9): 2.1}
    near, far = near_far_split(weighted, stance_by_month)
    assert near == pytest.approx(-1.2)
    # far = weighted avg of Aug/Sep renormalized: (0.5*2.1 + 0.3*2.1) / 0.8
    assert far == pytest.approx(2.1)


def test_near_far_split_single_month_no_rest():
    weighted = [((2026, 7), 1.0)]
    stance_by_month = {(2026, 7): 0.8}
    near, far = near_far_split(weighted, stance_by_month)
    assert near == pytest.approx(0.8)
    assert far is None


def test_near_far_split_empty():
    assert near_far_split([], {}) == (None, None)


# ─── to_action: sign-agreement override on near/far ────────────────────────

_THR = dict(thr_bm=0.62, thr_bs=0.276, thr_stm=-0.736, thr_sa=-0.88)


def test_to_action_both_negative_forces_sa():
    vocab, tag = to_action(-0.1, near=-0.5, far=-0.3, **_THR)
    assert vocab == 'SA'
    assert tag == 'SA'


def test_to_action_both_positive_floors_to_bs():
    vocab, tag = to_action(0.05, near=0.5, far=0.3, **_THR)
    assert vocab == 'BS'
    assert tag == 'BS'


def test_to_action_both_positive_still_reaches_bm_if_score_clears():
    vocab, tag = to_action(0.9, near=0.5, far=0.3, **_THR)
    assert vocab == 'BM'
    assert tag == 'BS'


def test_to_action_disagreement_falls_through_to_score_thresholds():
    vocab, tag = to_action(0.0, near=0.5, far=-0.3, **_THR)
    assert vocab == 'HOLD'
    assert tag == 'none'


def test_to_action_no_far_uses_score_only():
    vocab, tag = to_action(0.9, near=0.5, far=None, **_THR)
    assert vocab == 'BM'
    assert tag == 'none'


def test_to_action_score_gated_thresholds():
    assert to_action(1.0, None, None, **_THR)[0] == 'BM'
    assert to_action(0.4, None, None, **_THR)[0] == 'BS'
    assert to_action(-1.0, None, None, **_THR)[0] == 'SA'
    assert to_action(-0.8, None, None, **_THR)[0] == 'STM'
    assert to_action(0.0, None, None, **_THR)[0] == 'HOLD'


# ─── tracking_tag ────────────────────────────────────────────────────────

def test_tracking_tag_first_match_wins():
    weighted = [((2026, 7), 0.2), ((2026, 8), 0.5), ((2026, 9), 0.3)]
    stance_by_month = {(2026, 7): -1.2, (2026, 8): 2.1, (2026, 9): 2.1}
    quad_by_month = {(2026, 7): 3, (2026, 8): 1, (2026, 9): 1}
    tag = tracking_tag(1.5, weighted, stance_by_month, quad_by_month)  # bullish technical
    assert tag == "2026-08 (Quad 1)"


def test_tracking_tag_no_technical_direction_returns_none():
    weighted = [((2026, 7), 1.0)]
    stance_by_month = {(2026, 7): 1.0}
    quad_by_month = {(2026, 7): 1}
    assert tracking_tag(None, weighted, stance_by_month, quad_by_month) is None
    assert tracking_tag(0, weighted, stance_by_month, quad_by_month) is None


def test_tracking_tag_no_match_returns_none():
    weighted = [((2026, 7), 0.5), ((2026, 8), 0.5)]
    stance_by_month = {(2026, 7): -1.0, (2026, 8): -0.5}
    quad_by_month = {(2026, 7): 4, (2026, 8): 3}
    assert tracking_tag(1.0, weighted, stance_by_month, quad_by_month) is None  # bullish tech, all-bear months


def test_tracking_tag_bearish_technical_matches_bear_month():
    weighted = [((2026, 7), 0.6), ((2026, 8), 0.4)]
    stance_by_month = {(2026, 7): 0.5, (2026, 8): -1.0}
    quad_by_month = {(2026, 7): 1, (2026, 8): 4}
    tag = tracking_tag(-2.0, weighted, stance_by_month, quad_by_month)
    assert tag == "2026-08 (Quad 4)"
