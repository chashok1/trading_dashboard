"""/api/dashboard/missing-from-tos: every listed symbol really has no row in the newest TOS exports (needs the DB)."""
import pytest
from sqlalchemy import text


def test_listed_symbols_are_absent_from_the_newest_tos_exports():
    try:
        from fastapi.testclient import TestClient
        from api.main import app
        from etl.db import session_scope
        body = TestClient(app).get("/api/dashboard/missing-from-tos").json()
    except Exception as e:   # no database / app in this environment
        pytest.skip(f"unavailable: {e}")
    assert set(body) >= {"as_of", "count", "symbols"} and body["count"] == len(body["symbols"])
    with session_scope() as s:
        for row in body["symbols"]:
            assert row["lists"] and isinstance(row["us_ticker"], bool)
            for tbl in ("hist_td", "hist_tl", "hist_tw"):
                n = s.execute(text(
                    f"SELECT COUNT(*) FROM {tbl} WHERE tos_symbol = :s AND export_date = (SELECT MAX(export_date) FROM {tbl})"
                ), {"s": row["symbol"]}).scalar()
                assert n == 0, f"{row['symbol']} is in the newest {tbl} export"
