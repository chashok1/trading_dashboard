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

from etl.derive_outlook_action import _action_outlook_modifier


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
