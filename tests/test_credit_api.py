"""
GET /api/cockpit/credit (Credit panel: high-yield spread, high-yield total return index, BBB spread).

Behavior/schema only (no point-in-time values): every row is [date, hy_spread, total_return, bbb_spread] with dates ascending and
each value a number or null, and the total return index starts its window at 100.
"""
from __future__ import annotations

import pytest


def _rows():
    from fastapi.testclient import TestClient
    from api.main import app

    try:
        r = TestClient(app).get("/api/cockpit/credit")
    except Exception as exc:  # no Postgres in this environment
        pytest.skip("database unavailable: %s" % exc)
    assert r.status_code == 200
    return r.json()["rows"]


def test_rows_carry_three_series():
    rows = _rows()
    assert rows
    for row in rows:
        assert len(row) == 4
        assert all(v is None or isinstance(v, (int, float)) for v in row[1:])
    for k in (1, 2, 3):
        assert any(r[k] is not None for r in rows)


def test_dates_ascend_and_total_return_starts_at_100():
    rows = _rows()
    dates = [r[0] for r in rows]
    assert dates == sorted(dates)
    first_tr = next(r[2] for r in rows if r[2] is not None)
    assert first_tr == pytest.approx(100.0, abs=0.01)
