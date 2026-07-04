"""
Shared test fixtures.

The DB-dependent tests use a session fixture that talks to the configured
trading database (read-only by default — see DDL_ROLLBACK below). Pure-Python
tests don't need any of this.

TASK_111 (2026-07-04) added the Cat E environment guards below: node-missing
auto-skip for `node --check` subprocess calls, and a short default socket
timeout so any live-network test (e.g. the FRED-adjacent tests in
test_agent_work_11.py) can't hang the suite when offline.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest


# Make `etl.*` and `api.*` importable regardless of where pytest is invoked from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def pytest_configure(config):
    """Register custom markers so `@pytest.mark.network` etc. don't warn."""
    config.addinivalue_line(
        "markers",
        "network: test hits a live external API/service — may be slow or "
        "offline-flaky (TASK_111 Cat E guard).",
    )


def node_available() -> bool:
    """True if a `node` executable is on PATH — used to skip `node --check` tests."""
    return shutil.which("node") is not None


@pytest.fixture(scope="session")
def node_available_fixture():
    """Fixture form of node_available(), for tests that prefer a fixture."""
    return node_available()


@pytest.fixture(autouse=True)
def _skip_node_check_if_missing(monkeypatch):
    """Auto-skip any test that shells out to `node --check ...` when Node
    isn't on PATH, instead of letting it hard-fail with FileNotFoundError.

    Many test_agent_work_N.py / test_task_NN_*.py files call
    `subprocess.run(["node", "--check", path])` inline to validate JS syntax.
    Rather than touching every call site, this wraps subprocess.run so any
    such call skips gracefully when Node is unavailable (TASK_111 Cat E).
    """
    if node_available():
        yield
        return

    real_run = subprocess.run

    def _guarded_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "node":
            pytest.skip("node not available on PATH — skipping node --check test")
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _guarded_run)
    yield


@pytest.fixture(autouse=True)
def _short_network_timeout():
    """Cap the default socket timeout for the duration of every test.

    Tests that hit a live server/API (FRED-adjacent tests in
    test_agent_work_11.py, /api/marketbar checks, etc.) can otherwise hang
    indefinitely if offline. A short default timeout makes any such call
    fail/skip fast instead of hanging the whole suite (TASK_111 Cat E).
    Tests that need a longer explicit timeout still get it — this only sets
    the *default* used when a call doesn't specify one.
    """
    previous = socket.getdefaulttimeout()
    socket.setdefaulttimeout(5)
    try:
        yield
    finally:
        socket.setdefaulttimeout(previous)


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
