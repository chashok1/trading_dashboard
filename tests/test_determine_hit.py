"""
Tests for etl.compute_outcomes._determine_hit — the function that decides
whether a logged user action was a "hit" based on forward return.

Covers Phase 1 #1 — branches for REMOVE/REDUCE (sell-direction) and
ADD/INCREASE (buy-direction) plus the ACTED fallback.

Pure-Python: no DB needed.
"""
from __future__ import annotations

import pytest

from etl.compute_outcomes import _determine_hit


_DEFAULT_SETTINGS = {
    "outcome_hit_threshold_buy":  "0.5",
    "outcome_hit_threshold_sell": "-0.5",
    "outcome_hold_threshold":     "1.0",
}


class TestSellCodes:
    @pytest.mark.parametrize("code", ["SA", "STM", "SS", "REMOVE", "REDUCE"])
    def test_hits_on_negative_move(self, code):
        assert _determine_hit(code, -1.0, _DEFAULT_SETTINGS) is True
        assert _determine_hit(code, -0.5, _DEFAULT_SETTINGS) is True

    @pytest.mark.parametrize("code", ["SA", "STM", "SS", "REMOVE", "REDUCE"])
    def test_misses_on_positive_move(self, code):
        assert _determine_hit(code, 0.5, _DEFAULT_SETTINGS) is False
        assert _determine_hit(code, 5.0, _DEFAULT_SETTINGS) is False


class TestBuyCodes:
    @pytest.mark.parametrize("code", ["BM", "ADD", "INCREASE"])
    def test_hits_on_positive_move(self, code):
        assert _determine_hit(code, 1.0, _DEFAULT_SETTINGS) is True
        assert _determine_hit(code, 0.5, _DEFAULT_SETTINGS) is True

    @pytest.mark.parametrize("code", ["BM", "ADD", "INCREASE"])
    def test_misses_on_negative_move(self, code):
        assert _determine_hit(code, -1.0, _DEFAULT_SETTINGS) is False


class TestHoldCodes:
    @pytest.mark.parametrize("code", ["HOLD", "SKIP"])
    def test_hits_when_within_band(self, code):
        assert _determine_hit(code, 0.5, _DEFAULT_SETTINGS) is True
        assert _determine_hit(code, -0.5, _DEFAULT_SETTINGS) is True

    @pytest.mark.parametrize("code", ["HOLD", "SKIP"])
    def test_misses_when_outside_band(self, code):
        assert _determine_hit(code, 2.0, _DEFAULT_SETTINGS) is False
        assert _determine_hit(code, -2.0, _DEFAULT_SETTINGS) is False


class TestActedFallback:
    """ACTED should normally be resolved upstream, but if it slips through,
    score as 'did the symbol move meaningfully'."""
    def test_acted_hits_on_meaningful_move(self):
        assert _determine_hit("ACTED", 2.0, _DEFAULT_SETTINGS) is True
        assert _determine_hit("ACTED", -2.0, _DEFAULT_SETTINGS) is True

    def test_acted_misses_on_flat(self):
        assert _determine_hit("ACTED", 0.1, _DEFAULT_SETTINGS) is False


class TestEdges:
    def test_none_return_is_false(self):
        assert _determine_hit("REMOVE", None, _DEFAULT_SETTINGS) is False

    def test_unknown_code_is_false(self):
        assert _determine_hit("MYSTERY", 5.0, _DEFAULT_SETTINGS) is False

    def test_case_insensitive(self):
        assert _determine_hit("remove", -1.0, _DEFAULT_SETTINGS) is True
        assert _determine_hit(" Reduce ", -1.0, _DEFAULT_SETTINGS) is True

    def test_settings_override_threshold(self):
        # Tighter threshold means a 0.6% move is no longer a hit for BM
        tight = {"outcome_hit_threshold_buy": "2.0"}
        assert _determine_hit("BM", 1.0, tight) is False
        assert _determine_hit("BM", 2.5, tight) is True
