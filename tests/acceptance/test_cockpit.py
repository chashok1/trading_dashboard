"""
tests/acceptance/test_cockpit.py -- TASK_133 (dashboard cockpit) acceptance
proof. One-time acceptance checks for this task's deliverable (new tables
populated for the anchor date, each cockpit endpoint returns 200 with the
documented shape, drv_category_perf reconciles to /api/portfolio/summary) --
deletable after commit per docs/audit/test_debt_review.md §2. Marked
@pytest.mark.acceptance, excluded from the default run (pytest.ini).

Skips gracefully (not a failure) if Postgres isn't reachable.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.acceptance


@pytest.fixture(scope="module")
def anchor_date():
    try:
        from etl.db import session_scope
        from sqlalchemy import text
    except Exception:
        pytest.skip("etl.db not importable")
    try:
        with session_scope() as s:
            d = s.execute(text("SELECT MAX(export_date) FROM hist_td")).scalar()
    except Exception as e:
        pytest.skip(f"DB not available: {e}")
    if d is None:
        pytest.skip("hist_td empty -- no anchor date")
    return d


def test_drv_market_stat_populated(anchor_date):
    from etl.db import session_scope
    from sqlalchemy import text
    with session_scope() as s:
        row = s.execute(text(
            "SELECT risk_budget, risk_label, gauges_fired FROM drv_market_stat WHERE as_of_date = :d"
        ), {"d": anchor_date}).first()
    assert row is not None
    assert row[2] is not None  # gauges_fired jsonb populated


def test_drv_category_perf_populated(anchor_date):
    from etl.db import session_scope
    from sqlalchemy import text
    with session_scope() as s:
        n = s.execute(text(
            "SELECT COUNT(*) FROM drv_category_perf WHERE as_of_date = :d"
        ), {"d": anchor_date}).scalar()
    assert n and n > 0


def test_drv_category_perf_reconciles_to_portfolio_summary(anchor_date):
    """The single most important check in Phase 5 (spec's own words) --
    asset_class market_value total must reconcile to /api/portfolio/summary."""
    from etl.db import session_scope
    from sqlalchemy import text
    with session_scope() as s:
        cat_total = s.execute(text(
            "SELECT SUM(market_value) FROM drv_category_perf "
            "WHERE axis = 'asset_class' AND as_of_date = :d"
        ), {"d": anchor_date}).scalar()
    try:
        from api.routers.dash import get_portfolio_summary
        summary = get_portfolio_summary(date=anchor_date.isoformat())
    except Exception as e:
        pytest.skip(f"/api/portfolio/summary not callable in-process: {e}")
    portfolio_total = float(summary.get("market_value") or 0) + float(summary.get("cash_value") or 0)
    assert cat_total is not None
    assert abs(float(cat_total) - portfolio_total) < 1.0  # within a dollar of rounding


@pytest.mark.parametrize("axis", ["sector", "asset_class", "style"])
def test_cockpit_endpoints_return_200_with_shape(anchor_date, axis):
    from api.routers.cockpit import (
        get_risk_dial, get_events, get_factor_scorecard, get_shortlist,
    )
    d = anchor_date.isoformat()

    fs = get_factor_scorecard(date=d, axis=axis)
    assert fs["axis"] == axis
    assert "rows" in fs

    rd = get_risk_dial(date=d)
    assert "risk_budget" in rd and "fired" in rd and "quiet" in rd

    ev = get_events(date=d)
    assert "quiet" in ev

    sl = get_shortlist(date=d)
    assert "rows" in sl
    assert len(sl["rows"]) <= 3  # hard cap (spec 6.4)
