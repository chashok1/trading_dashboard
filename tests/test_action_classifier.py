"""
Tests for etl.derive_outlook_action._action_outlook_modifier.

This is the single function whose bug-class produced the "REMOVE storm"
(every symbol from the most recent snapshot incorrectly classified as REMOVE
when a source hadn't been re-loaded for the current date). Tests below cover:

  - All 9 (base, prev, held) edge cases the classifier branches on
  - Symmetric paths (e.g. REMOVE only when held, ADD on first appearance)
  - Float-precision parity (string-formatted reasons)

These tests are pure-Python (no DB) so they run with no setup.

Run:
    pytest tests/test_action_classifier.py -v
"""
from __future__ import annotations

import pytest

from etl.derive_outlook_action import _action_outlook_modifier, _action_outlook_v2


# ─── Truth table ────────────────────────────────────────────────────────────
#  base | prev | held | expected_action | reason_contains
# ─────────────────────────────────────────────────────────────────────────────
_CASES = [
    # both missing — no-op
    (None,  None,  True,  None,       "no data"),
    (None,  None,  False, None,       "no data"),

    # symbol dropped from today's snapshot (the bug fix target)
    (None,  +3.0,  True,  "REMOVE",   "dropped from snapshot"),
    (None,  +3.0,  False, "REMOVE",   "dropped from snapshot"),
    (None,  -3.0,  True,  "REMOVE",   "dropped from snapshot"),

    # symbol new in today's snapshot
    (+3.0,  None,  True,  "ADD",      "new in snapshot"),
    (+3.0,  None,  False, "ADD",      "new in snapshot"),
    (-3.0,  None,  False, "ADD",      "new in snapshot"),

    # held, weight changed
    (-3.0,  +3.0,  True,  "REMOVE",   "flipped non-positive"),
    (0.0,   +3.0,  True,  "REMOVE",   "flipped non-positive"),
    (+3.0,  -3.0,  True,  "ADD",      "flipped positive"),
    (+3.0,  0.0,   True,  "ADD",      "flipped positive"),
    (+5.0,  +3.0,  True,  "INCREASE", "weight +3"),
    (+1.0,  +3.0,  True,  "REDUCE",   "weight +3"),
    (+3.0,  +3.0,  True,  "HOLD",     "unchanged"),

    # not held, present today
    (+3.0,  +3.0,  False, "ADD",      "not held"),
    (+1.0,  +3.0,  False, "ADD",      "not held"),
    (-1.0,  -3.0,  False, None,       "no action"),
    (0.0,   0.0,   False, None,       "no action"),
]


@pytest.mark.parametrize("base, prev, held, want_action, want_reason_part", _CASES)
def test_action_outlook_modifier(base, prev, held, want_action, want_reason_part):
    action, reason = _action_outlook_modifier(base, prev, held)
    assert action == want_action, (
        f"({base=}, {prev=}, {held=}) -> expected {want_action!r}, got {action!r}"
    )
    assert want_reason_part in reason, (
        f"reason {reason!r} does not contain {want_reason_part!r}"
    )


def test_remove_storm_regression():
    """
    Regression for the 2026-05-12 bug: when a source wasn't loaded for the
    current date, today_w would be empty and every symbol in prev_w would
    classify as REMOVE. The classifier itself is not the fix point — the
    presence guard in _derive_outlook_action_impl is — but if we ever
    accidentally call this with a 'missing source' set, REMOVE *is* the
    right semantic answer for symbols that genuinely dropped from the
    snapshot. This test pins that behavior so refactors don't change it.
    """
    # Held symbol with prev outlook but absent today -> REMOVE
    action, _ = _action_outlook_modifier(None, +3.0, True)
    assert action == "REMOVE"
    # Unheld symbol with prev outlook but absent today -> still REMOVE
    # (it might no longer matter for the user, but the classifier is consistent)
    action, _ = _action_outlook_modifier(None, +3.0, False)
    assert action == "REMOVE"


def test_no_action_when_both_missing():
    """Both base and prev None — classifier returns (None, 'no data either snapshot')."""
    action, reason = _action_outlook_modifier(None, None, True)
    assert action is None
    assert "no data" in reason


# ═════════════════════════════════════════════════════════════════════════════
# v2 classifier tests (2026-05-12)
# ═════════════════════════════════════════════════════════════════════════════
#
# Rules (held-agnostic; precedence top-to-bottom):
#   base=None, prev>0           → REMOVE   (unless suppress_disappearance=True)
#   base=None, prev<=0 or None  → silent
#   prev=None, base>2           → ADD
#   prev=None, base<=2          → silent
#   prev>0 & base<=0  OR  prev>=0 & base<0   → REMOVE
#   base>0 & base>prev          → INCREASE  (wins over sign-flip ADD)
#   base>0 & base<prev          → REDUCE
#   else                        → silent
#
# When suppress_disappearance=True (CALL): any base=None case is silent.

_V2_CASES = [
    # base, prev, suppress, expected_action, reason_contains

    # ── disappearance (β: only fire REMOVE if prev > 0) ──
    (None,  None,  False, None,     "no data"),
    (None,  None,  True,  None,     "no data"),
    (None,  3.0,   False, "REMOVE", "removed from snapshot"),
    (None,  3.0,   True,  None,     "aging out is silent"),
    (None,  0.5,   False, "REMOVE", "removed from snapshot"),   # prev>0 fires REMOVE
    (None,  0.0,   False, None,     "silent per β"),            # prev=0 silent
    (None,  -3.0,  False, None,     "silent per β"),            # prev<0 silent
    (None,  -3.0,  True,  None,     "aging out is silent"),     # suppress trumps

    # ── new entries ──
    (3.0,   None,  False, "ADD",    "> 2"),
    (3.0,   None,  True,  "ADD",    "> 2"),
    (5.0,   None,  False, "ADD",    "> 2"),
    (2.0,   None,  False, None,     "≤ 2"),                     # boundary: not strictly >
    (1.0,   None,  False, None,     "≤ 2"),
    (0.0,   None,  False, None,     "≤ 2"),
    (-3.0,  None,  False, None,     "≤ 2"),

    # ── both present: REMOVE (strict OR form) ──
    (-3.0,  3.0,   False, "REMOVE", "→"),                       # BULLISH→BEARISH
    (0.0,   3.0,   False, "REMOVE", "→"),                       # BULLISH→NEUTRAL  ← user's (a)
    (-3.0,  0.0,   False, "REMOVE", "→"),                       # NEUTRAL→BEARISH

    # ── both present: REMOVE clauses NOT triggered ──
    (0.0,   0.0,   False, None,     "no qualifying change"),    # NEUTRAL→NEUTRAL (strict OR excludes)

    # ── INCREASE/REDUCE: require base>0 ──
    (5.0,   3.0,   False, "INCREASE", "→"),
    (1.0,   3.0,   False, "REDUCE",   "→"),
    (3.0,   3.0,   False, None,       "no qualifying change"),   # unchanged

    # ── INCREASE wins over sign-flip ADD when both apply ──
    (4.0,   -3.0,  False, "INCREASE", "→"),    # would-be sign-flip ADD, INCREASE wins per #1
    (3.0,   0.0,   False, "INCREASE", "→"),    # 0→positive
    (4.0,   -1.0,  False, "INCREASE", "→"),

    # ── Edge case: weight decreased but still positive ──
    (0.5,   3.0,   False, "REDUCE", "→"),
]


@pytest.mark.parametrize("base, prev, suppress, want_action, want_reason_part", _V2_CASES)
def test_action_outlook_v2(base, prev, suppress, want_action, want_reason_part):
    action, reason = _action_outlook_v2(base, prev, suppress_disappearance=suppress)
    assert action == want_action, (
        f"v2({base=}, {prev=}, suppress={suppress}) -> "
        f"expected {want_action!r}, got {action!r} (reason: {reason!r})"
    )
    assert want_reason_part in reason, (
        f"v2({base=}, {prev=}, suppress={suppress}) reason {reason!r} "
        f"does not contain {want_reason_part!r}"
    )


def test_v2_call_aging_out_silent():
    """CALL-specific: aging out (prev>0, base=None, suppress=True) is silent."""
    action, _ = _action_outlook_v2(None, 3.0, suppress_disappearance=True)
    assert action is None


def test_v2_etf_disappearance_remove():
    """ETF/II: disappearance of a previously-Long symbol fires REMOVE."""
    action, _ = _action_outlook_v2(None, 3.0, suppress_disappearance=False)
    assert action == "REMOVE"


def test_v2_etf_short_disappearance_silent():
    """ETF/II: disappearance of a previously-Short symbol is silent (β)."""
    action, _ = _action_outlook_v2(None, -3.0, suppress_disappearance=False)
    assert action is None


def test_v2_increase_wins_over_sign_flip_add():
    """Precedence: INCREASE wins over the sign-flip ADD when both rules match."""
    # prev=-3, base=4: rule 4 (sign-flip ADD) and rule INCREASE both qualify.
    # User chose INCREASE wins.
    action, _ = _action_outlook_v2(4.0, -3.0, suppress_disappearance=False)
    assert action == "INCREASE"


def test_v2_bullish_to_neutral_remove():
    """User's (a) clarification: BULLISH (+3) → NEUTRAL (0) must fire REMOVE."""
    action, _ = _action_outlook_v2(0.0, 3.0, suppress_disappearance=False)
    assert action == "REMOVE"


def test_v2_new_bearish_silent():
    """New entry with base<=2 (e.g. base=-3 for new Short) — silent."""
    action, _ = _action_outlook_v2(-3.0, None, suppress_disappearance=False)
    assert action is None
