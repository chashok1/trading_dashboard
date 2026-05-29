"""
DB-dependent smoke test for the new v_outlook_changes SQL function.

Skipped automatically if Postgres isn't reachable (CI without DB).
Otherwise it just confirms the function exists, returns valid rows, and that
the dominant_action priority works as designed.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text


def test_function_exists(db_session):
    """v_outlook_changes(today) must be callable even when there are no rows."""
    rows = db_session.execute(text("SELECT * FROM v_outlook_changes(CURRENT_DATE)")).all()
    # No assertion on row count — empty result is valid.
    assert isinstance(rows, list)


def test_dominant_action_priority(db_session):
    """Insert a couple of fake drv_outlook_action rows and verify the view's
    dominant_action follows the REMOVE > REDUCE > ADD > INCREASE priority.

    All inserts happen inside the test session and roll back automatically.
    """
    # Pick a date 9999 days in the future so we don't collide with real data.
    test_date = "9999-01-01"
    test_sym  = "__TESTSYM__"

    # Need source_code values that exist in ref_outlook_source. Pick whatever
    # the DB has; skip if it has none.
    src = db_session.execute(text(
        "SELECT source_code FROM ref_outlook_source LIMIT 2"
    )).fetchall()
    if len(src) < 2:
        pytest.skip("ref_outlook_source needs ≥2 rows to run this test")
    src_a, src_b = src[0][0], src[1][0]

    # Insert two rows: one REMOVE and one INCREASE. Dominant must be REMOVE.
    db_session.execute(text("""
        INSERT INTO drv_outlook_action
          (as_of_date, tos_symbol, source_code, base_weight, prev_weight,
           weight_delta, held_today, action, action_reason)
        VALUES
          (:d, :s, :sc, -2, 3, -5, FALSE, 'REMOVE', 'test')
    """), {"d": test_date, "s": test_sym, "sc": src_a})
    db_session.execute(text("""
        INSERT INTO drv_outlook_action
          (as_of_date, tos_symbol, source_code, base_weight, prev_weight,
           weight_delta, held_today, action, action_reason)
        VALUES
          (:d, :s, :sc, 5, 2, 3, FALSE, 'INCREASE', 'test')
    """), {"d": test_date, "s": test_sym, "sc": src_b})

    rows = db_session.execute(text(
        "SELECT * FROM v_outlook_changes(:d) WHERE tos_symbol = :s"
    ), {"d": test_date, "s": test_sym}).mappings().all()

    assert len(rows) == 1, f"expected exactly 1 symbol row, got {len(rows)}"
    r = rows[0]
    assert r["dominant_action"] == "REMOVE"
    assert r["n_sources_changed"] == 2
    assert set(r["actions"]) == {"REMOVE", "INCREASE"}
