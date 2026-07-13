"""
Unit tests for etl/derive_macro.py::_effective_quad_label — pure Python,
no DB. ref_quad_periods.quad (the declared label) can be stale/inconsistent
with its own quad1_pct..quad4_pct distribution; the sparkline popup must
show the argmax of the distribution, matching what the MACRO tooltip
already does via api/routers/dash.py::_effective_quad_col.
"""
from __future__ import annotations

from types import SimpleNamespace

from etl.derive_macro import _effective_quad_label


def _period(quad, q1=0, q2=0, q3=0, q4=0):
    return SimpleNamespace(quad=quad, quad1_pct=q1, quad2_pct=q2, quad3_pct=q3, quad4_pct=q4)


def test_argmax_wins_over_stale_declared_quad():
    # Real Jul-2026 case: declared "Quad 3" but distribution favors Quad 4 (55%).
    p = _period("Quad 3", q1=14, q2=6, q3=25, q4=55)
    assert _effective_quad_label(p) == "Quad 4"


def test_argmax_matches_declared_when_consistent():
    p = _period("Quad 1", q1=45, q2=37, q3=8, q4=10)
    assert _effective_quad_label(p) == "Quad 1"


def test_falls_back_to_declared_when_distribution_missing():
    p = _period("Quad 2", q1=0, q2=0, q3=0, q4=0)
    assert _effective_quad_label(p) == "Quad 2"


def test_falls_back_to_declared_when_percentiles_are_none():
    p = SimpleNamespace(quad="Quad 3", quad1_pct=None, quad2_pct=None,
                        quad3_pct=None, quad4_pct=None)
    assert _effective_quad_label(p) == "Quad 3"
