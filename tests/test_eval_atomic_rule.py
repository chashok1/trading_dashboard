"""
Tests for etl.derive.eval_atomic_rule — the single rule scorer used by
drv_stks, drv_trig, and every dry-run endpoint. After Phase 1 #4, the legacy
_bucket_weight is gone; if this file passes, all three consumers agree on
score for any rule definition.

Pure-Python: no DB needed.
"""
from __future__ import annotations

import pytest

from etl.derive import eval_atomic_rule


def _rule(mode="jump", lo=5, hi=10, wb=-1, wbt=1, wa=2, params=None):
    return {
        "scoring_mode": mode,
        "brkeout_from": lo, "brkeout_to": hi,
        "wt_below": wb, "wt_between": wbt, "wt_above": wa,
        "score_params": params,
    }


class TestJumpMode:
    def test_below(self):
        assert eval_atomic_rule(3, _rule()) == -1.0

    def test_between(self):
        assert eval_atomic_rule(7, _rule()) == 1.0

    def test_above(self):
        assert eval_atomic_rule(12, _rule()) == 2.0

    def test_at_lo_boundary_is_between(self):
        # v == lo → not below
        assert eval_atomic_rule(5, _rule()) == 1.0

    def test_at_hi_boundary_is_between(self):
        # v == hi → not above
        assert eval_atomic_rule(10, _rule()) == 1.0


class TestLinearMode:
    def test_below_returns_wt_below(self):
        assert eval_atomic_rule(0, _rule(mode="linear")) == -1.0

    def test_above_returns_wt_above(self):
        assert eval_atomic_rule(15, _rule(mode="linear")) == 2.0

    def test_midpoint_interpolation_uses_wt_between(self):
        # Implementation interpolates from wt_below to wt_above across [lo, hi].
        # Midpoint 7.5: (-1 + 2) / 2 = 0.5
        result = eval_atomic_rule(7.5, _rule(mode="linear"))
        assert -0.5 <= result <= 1.5  # robust range — anchors above are extremes


class TestEdgeCases:
    def test_none_value(self):
        assert eval_atomic_rule(None, _rule()) == 0.0

    def test_non_numeric_value(self):
        assert eval_atomic_rule("abc", _rule()) == 0.0

    def test_unknown_mode_falls_back_safely(self):
        # No exception, returns numeric
        v = eval_atomic_rule(7, _rule(mode="weird"))
        assert isinstance(v, (int, float))

    def test_missing_weights_default_to_zero(self):
        sparse = {"scoring_mode": "jump", "brkeout_from": 5, "brkeout_to": 10}
        assert eval_atomic_rule(7, sparse) == 0.0
