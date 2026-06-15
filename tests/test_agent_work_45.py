"""Tests for AGENT_WORK_45 — ETF drop-while-held returns REMOVE (SA) instead of REDUCE (SS).

Acceptance criteria (pure-Python, no DB required):
1. _action_standing(None, 3.0, held=True, drop_action="REMOVE") -> ("REMOVE", ...)
2. _action_standing(None, 3.0, held=True, drop_action="REDUCE") -> ("REDUCE", ...)  -- II/RR default
3. _action_standing(None, 3.0, held=False)                      -> (None, ...)       -- unchanged
4. _action_standing(2.0,  None, held=True)                      -> ("ADD",  ...)     -- unrelated path unchanged
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make sure the project root is on sys.path so etl imports work.
PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from etl.derive_outlook_action import _action_standing  # noqa: E402


# ---------------------------------------------------------------------------
# AC 1 — ETF drop while held => REMOVE
# ---------------------------------------------------------------------------

def test_etf_drop_held_returns_remove():
    """When drop_action='REMOVE' and symbol is held but absent from current list -> REMOVE."""
    action, reason = _action_standing(None, 3.0, held=True, drop_action="REMOVE")
    assert action == "REMOVE", f"Expected REMOVE, got {action!r}"
    assert "dropped from list" in reason


# ---------------------------------------------------------------------------
# AC 2 — II/RR drop while held => REDUCE (default behaviour preserved)
# ---------------------------------------------------------------------------

def test_ii_rr_drop_held_returns_reduce_explicit():
    """When drop_action='REDUCE' (II/RR) and symbol is held -> REDUCE."""
    action, reason = _action_standing(None, 3.0, held=True, drop_action="REDUCE")
    assert action == "REDUCE", f"Expected REDUCE, got {action!r}"
    assert "dropped from list" in reason


def test_default_drop_action_is_reduce():
    """Without drop_action kwarg the default is REDUCE (II/RR unchanged)."""
    action, reason = _action_standing(None, 3.0, held=True)
    assert action == "REDUCE", f"Default drop_action should be REDUCE, got {action!r}"


# ---------------------------------------------------------------------------
# AC 3 — dropped but NOT held => None regardless of drop_action
# ---------------------------------------------------------------------------

def test_drop_not_held_returns_none():
    """Symbol dropped from list but not held -> (None, ...) regardless of drop_action."""
    action, _ = _action_standing(None, 3.0, held=False)
    assert action is None

    action2, _ = _action_standing(None, 3.0, held=False, drop_action="REMOVE")
    assert action2 is None


# ---------------------------------------------------------------------------
# AC 4 — positive weight on current list => ADD (unrelated path unchanged)
# ---------------------------------------------------------------------------

def test_positive_weight_returns_add():
    """Positive weight on current list -> ADD regardless of held/prev."""
    action, reason = _action_standing(2.0, None, held=True)
    assert action == "ADD", f"Expected ADD, got {action!r}"
    assert "on list" in reason


def test_positive_weight_not_held_returns_add():
    """Positive weight, not held -> ADD (buy signal)."""
    action, _ = _action_standing(2.0, None, held=False)
    assert action == "ADD"


# ---------------------------------------------------------------------------
# Edge cases — non-numeric prev when drop_action="REMOVE"
# ---------------------------------------------------------------------------

def test_non_numeric_prev_remove():
    """Non-numeric prev value should not raise; still returns drop_action."""
    action, reason = _action_standing(None, "bad", held=True, drop_action="REMOVE")
    assert action == "REMOVE"
    assert "dropped from list" in reason


def test_non_numeric_prev_reduce():
    """Non-numeric prev value with default drop_action -> REDUCE."""
    action, reason = _action_standing(None, "bad", held=True)
    assert action == "REDUCE"
    assert "dropped from list" in reason


# ---------------------------------------------------------------------------
# Negative weight on current list => REMOVE (unchanged path)
# ---------------------------------------------------------------------------

def test_negative_weight_returns_remove():
    """Negative weight on current list -> REMOVE (existing REMOVE path untouched)."""
    action, reason = _action_standing(-1.5, None, held=True)
    assert action == "REMOVE"
    assert "on list" in reason
