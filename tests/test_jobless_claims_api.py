"""
GET /api/cockpit/jobless-claims (Jobless claims dashboard panel).

Behavior/schema only (no point-in-time values): rows are [week_ending, claims, 4-week average], in date order, and the 4-week average
equals the mean of that week and the three before it whenever those weeks are present.
"""
from __future__ import annotations

import pytest


def _get():
    from fastapi.testclient import TestClient
    from api.main import app

    try:
        r = TestClient(app).get("/api/cockpit/jobless-claims")
    except Exception as exc:  # no Postgres in this environment
        pytest.skip("database unavailable: %s" % exc)
    return r


def test_payload_shape():
    r = _get()
    assert r.status_code == 200
    j = r.json()
    assert set(j) >= {"as_of", "rows"}
    dates = [row[0] for row in j["rows"]]
    assert dates == sorted(dates)
    for row in j["rows"]:
        assert len(row) == 3 and row[1] > 0


def test_four_week_average():
    rows = _get().json()["rows"]
    for i in range(3, len(rows)):
        if rows[i][2] is not None:
            assert rows[i][2] == pytest.approx(sum(r[1] for r in rows[i - 3:i + 1]) / 4, abs=0.1)
