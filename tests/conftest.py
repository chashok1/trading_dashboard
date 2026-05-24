"""
Shared test fixtures.

The DB-dependent tests use a session fixture that talks to the configured
trading database (read-only by default — see DDL_ROLLBACK below). Pure-Python
tests don't need any of this.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# Make `etl.*` and `api.*` importable regardless of where pytest is invoked from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def db_available():
    """Boolean — is a Postgres connection actually reachable?

    Each DB-touching test that wants to skip gracefully on dev machines without
    Postgres can ask for this fixture and call `pytest.skip` if it's False.
    """
    try:
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture
def db_session(db_available):
    """A transactional session that ROLLS BACK at the end — never commits.

    Tests can INSERT and run derives against this session without leaving a
    trace behind, as long as they don't call session.commit() themselves.
    """
    if not db_available:
        pytest.skip("No Postgres available — set PG_PASSWORD in .env to run DB tests")
    from etl.db import _engine  # noqa: WPS437 (intentional — we need raw engine)
    from sqlalchemy.orm import Session

    conn = _engine().connect()
    trans = conn.begin()
    s = Session(bind=conn)
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        conn.close()
