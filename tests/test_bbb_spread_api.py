"""
GET /api/cockpit/bbb-spread (10-Year BBB spread panel, with the high-yield spread alongside).

Behavior/schema only (no point-in-time values): every row is [date, bbb_spread, hy_spread], dates ascend, bbb_spread is a number,
and hy_spread is a number or null.
"""
from __future__ import annotations

import pytest


def _rows():
    from fastapi.testclient import TestClient
    from api.main import app

    try:
        r = TestClient(app).get("/api/cockpit/bbb-spread")
    except Exception as exc:  # no Postgres in this environment
        pytest.skip("database unavailable: %s" % exc)
    assert r.status_code == 200
    return r.json()["rows"]


def test_rows_carry_both_spreads():
    rows = _rows()
    assert rows
    for row in rows:
        assert len(row) == 3
        assert isinstance(row[1], (int, float))
        assert row[2] is None or isinstance(row[2], (int, float))


def test_dates_ascend_and_high_yield_is_present():
    rows = _rows()
    dates = [r[0] for r in rows]
    assert dates == sorted(dates)
    assert any(r[2] is not None for r in rows)
