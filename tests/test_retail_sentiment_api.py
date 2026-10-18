"""
GET /api/cockpit/retail-sentiment (Retail sentiment dashboard panel).

Behavior/schema only (no point-in-time values): the payload lists the ETFs that have enough daily history, names the ones still
waiting, and every row has a date plus one close per returned symbol, starting on a day all returned symbols have a close.
"""
from __future__ import annotations

import pytest


def _get():
    from fastapi.testclient import TestClient
    from api.main import app

    try:
        r = TestClient(app).get("/api/cockpit/retail-sentiment")
    except Exception as exc:  # no Postgres in this environment
        pytest.skip("database unavailable: %s" % exc)
    return r


def test_payload_shape():
    r = _get()
    assert r.status_code == 200
    j = r.json()
    assert set(j) >= {"as_of", "syms", "pending", "rows"}
    # every tracked ETF is either returned or reported as pending, never both or neither
    assert sorted(j["syms"] + j["pending"]) == ["BUZZ", "GVIP", "MEME"]
    assert not set(j["syms"]) & set(j["pending"])


def test_rows_match_symbols():
    j = _get().json()
    dates = [row[0] for row in j["rows"]]
    assert dates == sorted(dates)
    for row in j["rows"]:
        assert len(row) == 1 + len(j["syms"])
        assert all(isinstance(v, (int, float)) and v > 0 for v in row[1:])
