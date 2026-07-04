"""
Tests for TASK_96 / AGENT_WORK_7 — v_ingest_log unified ingest ledger + /api/ingest-log endpoint.

Acceptance criteria verified (pure-Python, no DB required unless Postgres is present):

  SQL view definition (db/baseline.sql)
    Check 01 — CREATE OR REPLACE VIEW v_ingest_log present (idempotent)
    Check 02 — file_load leg selects from meta_file_processed
    Check 03 — file_load leg sets channel = 'file_load'
    Check 04 — file_load leg sets source_kind = COALESCE(source_kind, 'file')
    Check 05 — file_load leg maps file_path to source_ref
    Check 06 — file_load leg maps file_type to feed
    Check 07 — file_load leg maps target_tab
    Check 08 — file_load leg maps file_date to data_date
    Check 09 — file_load leg sets status = 'loaded'
    Check 10 — file_load leg maps processed_at
    Check 11 — email leg selects from meta_hedgeye_msg
    Check 12 — email leg sets channel = 'email'
    Check 13 — email leg sets source_kind = 'email'
    Check 14 — email leg maps message_id to source_ref
    Check 15 — email leg maps email_type to feed
    Check 16 — email leg sets target_tab = NULL
    Check 17 — email leg sets data_date = NULL::date
    Check 18 — email leg maps status column
    Check 19 — email leg maps processed_at
    Check 20 — view uses UNION ALL (not UNION)

  API endpoint (api/routers/monitor.py)
    Check 21 — @router.get('/api/ingest-log') decorator present
    Check 22 — function name is get_ingest_log
    Check 23 — date optional param (alias='date') present
    Check 24 — channel optional param present
    Check 25 — feed optional param with ILIKE filter present
    Check 26 — limit param with default 500 and le=5000 present
    Check 27 — SQL queries v_ingest_log
    Check 28 — SQL orders by processed_at DESC
    Check 29 — SQL uses LIMIT :limit
    Check 30 — response is a list of dicts with all 8 expected fields
    Check 31 — date filter appended to WHERE when date_param provided
    Check 32 — channel filter appended to WHERE when channel provided
    Check 33 — feed filter uses ILIKE
    Check 34 — date filter raises row cap (limit * 10) when date given

  CLAUDE.md lookup row
    Check 35 — CLAUDE.md Lookup table contains v_ingest_log row

  DEV_HANDOFF
    Check 36 — DEV_HANDOFF.md references AGENT_WORK_7
    Check 37 — DEV_HANDOFF.md Status is ALL_DONE

  Live DB checks (skip if Postgres absent)
    Check 38 — view returns at least one file_load row
    Check 39 — view returns at least one email row
    Check 40 — view has exactly 8 columns
    Check 41 — date filter (data_date) returns only rows for that date
    Check 42 — channel filter returns only matching rows
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

BASELINE_SQL = PROJECT / "db" / "baseline.sql"
MONITOR_PY   = PROJECT / "api" / "routers" / "monitor.py"
CLAUDE_MD    = PROJECT / "CLAUDE.md"
DEV_HANDOFF  = PROJECT / "DEV_HANDOFF.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# DB availability probe
# ---------------------------------------------------------------------------

def _db_available() -> bool:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


_DB_AVAILABLE = _db_available()
db_required = pytest.mark.skipif(
    not _DB_AVAILABLE,
    reason="PostgreSQL not reachable — DB checks skipped"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sql_src() -> str:
    assert BASELINE_SQL.exists(), f"Missing: {BASELINE_SQL}"
    return _read(BASELINE_SQL)


@pytest.fixture(scope="module")
def monitor_src() -> str:
    assert MONITOR_PY.exists(), f"Missing: {MONITOR_PY}"
    return _read(MONITOR_PY)


@pytest.fixture(scope="module")
def claude_src() -> str:
    assert CLAUDE_MD.exists(), f"Missing: {CLAUDE_MD}"
    return _read(CLAUDE_MD)


@pytest.fixture(scope="module")
def handoff_src() -> str:
    assert DEV_HANDOFF.exists(), f"Missing: {DEV_HANDOFF}"
    return _read(DEV_HANDOFF)


@pytest.fixture(scope="module")
def view_block(sql_src) -> str:
    """Extract just the v_ingest_log view definition from baseline.sql."""
    start = sql_src.find("CREATE OR REPLACE VIEW v_ingest_log")
    assert start >= 0, "v_ingest_log view not found in baseline.sql"
    # View ends at the next semicolon
    end = sql_src.find(";", start)
    return sql_src[start: end + 1 if end > 0 else start + 3000]


@pytest.fixture(scope="module")
def endpoint_block(monitor_src) -> str:
    """Extract just the get_ingest_log function body."""
    start = monitor_src.find("def get_ingest_log(")
    assert start >= 0, "get_ingest_log function not found in monitor.py"
    # Extract a generous window — the function is ~70 lines
    return monitor_src[start: start + 2000]


# ===========================================================================
# SQL VIEW CHECKS
# ===========================================================================

class TestViewDefinition:

    def test_check01_create_or_replace_view(self, sql_src):
        """Check 01 — CREATE OR REPLACE VIEW v_ingest_log (idempotent)."""
        assert "CREATE OR REPLACE VIEW v_ingest_log" in sql_src, (
            "CREATE OR REPLACE VIEW v_ingest_log not found in baseline.sql"
        )

    def test_check02_file_load_leg_from_meta_file_processed(self, view_block):
        """Check 02 — file_load leg queries meta_file_processed."""
        assert "meta_file_processed" in view_block, (
            "meta_file_processed not referenced in v_ingest_log"
        )

    def test_check03_file_load_channel(self, view_block):
        """Check 03 — file_load leg sets channel = 'file_load'."""
        assert "'file_load'" in view_block, (
            "'file_load' channel literal missing from v_ingest_log"
        )

    def test_check04_file_load_source_kind_coalesce(self, view_block):
        """Check 04 — file_load leg uses COALESCE(source_kind, 'file') for source_kind."""
        assert "COALESCE(source_kind" in view_block or "coalesce(source_kind" in view_block.lower(), (
            "COALESCE(source_kind, 'file') missing from file_load leg of v_ingest_log"
        )

    def test_check05_file_path_as_source_ref(self, view_block):
        """Check 05 — file_load leg maps file_path to source_ref."""
        assert "file_path" in view_block and "source_ref" in view_block, (
            "file_path -> source_ref mapping missing from v_ingest_log file_load leg"
        )

    def test_check06_file_type_as_feed(self, view_block):
        """Check 06 — file_load leg maps file_type to feed."""
        assert "file_type" in view_block and "feed" in view_block, (
            "file_type -> feed mapping missing from v_ingest_log file_load leg"
        )

    def test_check07_target_tab_in_file_load_leg(self, view_block):
        """Check 07 — file_load leg maps target_tab column."""
        assert "target_tab" in view_block, (
            "target_tab column missing from v_ingest_log"
        )

    def test_check08_file_date_as_data_date(self, view_block):
        """Check 08 — file_load leg maps file_date to data_date."""
        assert "file_date" in view_block and "data_date" in view_block, (
            "file_date -> data_date mapping missing from v_ingest_log file_load leg"
        )

    def test_check09_loaded_status_in_file_load_leg(self, view_block):
        """Check 09 — file_load leg sets status = 'loaded'."""
        assert "'loaded'" in view_block, (
            "'loaded' status literal missing from v_ingest_log file_load leg"
        )

    def test_check10_processed_at_in_file_load_leg(self, view_block):
        """Check 10 — file_load leg maps processed_at."""
        assert "processed_at" in view_block, (
            "processed_at column missing from v_ingest_log"
        )

    def test_check11_email_leg_from_meta_hedgeye_msg(self, view_block):
        """Check 11 — email leg queries meta_hedgeye_msg."""
        assert "meta_hedgeye_msg" in view_block, (
            "meta_hedgeye_msg not referenced in v_ingest_log email leg"
        )

    def test_check12_email_channel_in_email_leg(self, view_block):
        """Check 12 — email leg sets channel = 'email'."""
        # Count occurrences — 'email' appears as both channel value and source_kind value
        assert view_block.count("'email'") >= 2, (
            "channel='email' literal missing from email leg of v_ingest_log"
        )

    def test_check13_email_source_kind(self, view_block):
        """Check 13 — email leg sets source_kind = 'email'."""
        # There should be an explicit 'email' literal for source_kind in the UNION ALL second leg
        # We check both legs are present
        assert "'email'" in view_block, (
            "source_kind='email' missing from email leg of v_ingest_log"
        )

    def test_check14_message_id_as_source_ref(self, view_block):
        """Check 14 — email leg maps message_id to source_ref."""
        assert "message_id" in view_block, (
            "message_id -> source_ref mapping missing from v_ingest_log email leg"
        )

    def test_check15_email_type_as_feed(self, view_block):
        """Check 15 — email leg maps email_type to feed."""
        assert "email_type" in view_block, (
            "email_type -> feed mapping missing from v_ingest_log email leg"
        )

    def test_check16_null_target_tab_in_email_leg(self, view_block):
        """Check 16 — email leg sets target_tab = NULL."""
        assert "NULL" in view_block and "target_tab" in view_block, (
            "NULL target_tab missing from v_ingest_log email leg"
        )

    def test_check17_null_date_data_date_in_email_leg(self, view_block):
        """Check 17 — email leg sets data_date = NULL::date."""
        assert "NULL::date" in view_block or "NULL :: date" in view_block.lower(), (
            "NULL::date data_date missing from v_ingest_log email leg"
        )

    def test_check18_status_in_email_leg(self, view_block):
        """Check 18 — email leg maps status column from meta_hedgeye_msg.

        The SELECT columns appear BEFORE the FROM clause, so we search the
        second SELECT leg (between UNION ALL and the end of the view block).
        """
        union_pos = view_block.find("UNION ALL")
        assert union_pos >= 0, "UNION ALL not found in v_ingest_log"
        second_leg = view_block[union_pos:]
        assert "status" in second_leg, (
            "status column not mapped in email leg of v_ingest_log"
        )

    def test_check19_processed_at_in_email_leg(self, view_block):
        """Check 19 — email leg maps processed_at.

        Columns appear in the SELECT before the FROM, so search from UNION ALL.
        """
        union_pos = view_block.find("UNION ALL")
        assert union_pos >= 0, "UNION ALL not found in v_ingest_log"
        second_leg = view_block[union_pos:]
        assert "processed_at" in second_leg, (
            "processed_at missing from email leg of v_ingest_log"
        )

    def test_check20_union_all_not_union(self, view_block):
        """Check 20 — view uses UNION ALL (preserves duplicate rows from both legs)."""
        assert "UNION ALL" in view_block, (
            "UNION ALL not found in v_ingest_log — must use UNION ALL not UNION"
        )
        # Confirm no bare UNION without ALL
        # Split on UNION ALL to check residuals
        parts = view_block.split("UNION ALL")
        for part in parts:
            assert not re.search(r'\bUNION\b', part), (
                "Bare UNION (without ALL) found in v_ingest_log — use UNION ALL"
            )


# ===========================================================================
# API ENDPOINT CHECKS
# ===========================================================================

class TestApiEndpoint:

    def test_check21_route_decorator_present(self, monitor_src):
        """Check 21 — @router.get('/api/ingest-log') decorator present in monitor.py."""
        assert '"/api/ingest-log"' in monitor_src or "'/api/ingest-log'" in monitor_src, (
            "@router.get('/api/ingest-log') not found in monitor.py"
        )

    def test_check22_function_name(self, monitor_src):
        """Check 22 — Endpoint function name is get_ingest_log."""
        assert "def get_ingest_log(" in monitor_src, (
            "def get_ingest_log() not found in monitor.py"
        )

    def test_check23_date_param_with_alias(self, endpoint_block):
        """Check 23 — date optional param uses alias='date'."""
        assert "alias=\"date\"" in endpoint_block or "alias='date'" in endpoint_block, (
            "date param with alias='date' missing from get_ingest_log"
        )
        assert "date_param" in endpoint_block, (
            "date_param variable missing from get_ingest_log signature"
        )

    def test_check24_channel_param(self, endpoint_block):
        """Check 24 — channel optional param present."""
        assert "channel" in endpoint_block, (
            "channel param missing from get_ingest_log"
        )

    def test_check25_feed_param_with_ilike(self, endpoint_block):
        """Check 25 — feed optional param present and ILIKE used."""
        assert "feed" in endpoint_block, (
            "feed param missing from get_ingest_log"
        )
        assert "ILIKE" in endpoint_block, (
            "ILIKE filter missing from get_ingest_log feed filter"
        )

    def test_check26_limit_param_default_500_max_5000(self, endpoint_block):
        """Check 26 — limit param has default 500 and le=5000."""
        assert "limit" in endpoint_block, "limit param missing from get_ingest_log"
        assert "500" in endpoint_block, "default limit=500 missing from get_ingest_log"
        assert "5000" in endpoint_block, "le=5000 missing from get_ingest_log limit param"

    def test_check27_queries_v_ingest_log(self, endpoint_block):
        """Check 27 — SQL queries v_ingest_log view."""
        assert "v_ingest_log" in endpoint_block, (
            "v_ingest_log not referenced in get_ingest_log SQL"
        )

    def test_check28_orders_by_processed_at_desc(self, endpoint_block):
        """Check 28 — SQL ORDER BY processed_at DESC."""
        assert "processed_at DESC" in endpoint_block, (
            "ORDER BY processed_at DESC missing from get_ingest_log SQL"
        )

    def test_check29_sql_uses_limit(self, endpoint_block):
        """Check 29 — SQL uses LIMIT :limit or similar bound parameter."""
        assert "LIMIT :limit" in endpoint_block or "LIMIT" in endpoint_block, (
            "LIMIT clause missing from get_ingest_log SQL"
        )

    def test_check30_returns_all_8_fields(self, endpoint_block):
        """Check 30 — Response dict contains all 8 expected fields."""
        expected_fields = [
            "channel", "source_kind", "source_ref", "feed",
            "target_tab", "data_date", "status", "processed_at",
        ]
        missing = [f for f in expected_fields if f not in endpoint_block]
        assert not missing, (
            f"get_ingest_log response dict missing fields: {missing}"
        )

    def test_check31_date_filter_in_where(self, endpoint_block):
        """Check 31 — date filter appended to WHERE clauses when date_param provided."""
        assert "date_param" in endpoint_block, "date_param not used in filter logic"
        # Verify it builds a WHERE clause with the date
        assert "data_date" in endpoint_block or "processed_at::date" in endpoint_block, (
            "date filter not applied against data_date or processed_at::date"
        )

    def test_check32_channel_filter_in_where(self, endpoint_block):
        """Check 32 — channel filter appended to WHERE when channel provided."""
        assert "channel = :channel" in endpoint_block or "channel=:channel" in endpoint_block, (
            "channel = :channel filter missing from get_ingest_log"
        )

    def test_check33_feed_uses_ilike(self, endpoint_block):
        """Check 33 — feed filter uses ILIKE for case-insensitive matching."""
        assert "ILIKE :feed" in endpoint_block or "ILIKE" in endpoint_block, (
            "feed ILIKE filter missing from get_ingest_log"
        )

    def test_check34_date_raises_row_cap(self, endpoint_block):
        """Check 34 — when date given, row cap is relaxed (limit * 10)."""
        # The implementation multiplies limit by 10 when date is provided
        assert "limit * 10" in endpoint_block or "* 10" in endpoint_block, (
            "Row cap not relaxed when date filter is applied in get_ingest_log"
        )


# ===========================================================================
# CLAUDE.md LOOKUP ROW
# ===========================================================================

class TestClaudeMdLookup:

    def test_check35_lookup_row_present(self, claude_src):
        """Check 35 — CLAUDE.md Lookup table contains v_ingest_log row."""
        assert "v_ingest_log" in claude_src, (
            "v_ingest_log not found in CLAUDE.md Lookup index"
        )
        assert "/api/ingest-log" in claude_src, (
            "/api/ingest-log not referenced in CLAUDE.md"
        )


# ===========================================================================
# DEV_HANDOFF STATUS
# ===========================================================================

class TestDevHandoffStatus:

    # test_check36_handoff_references_agent_work_7 — RETIRED (TASK_111
    # test-debt cleanup, 2026-07-04). DEV_HANDOFF.md is a rolling file,
    # overwritten fresh by every task's developer pass (per
    # docs/agent_handoff_workflow.md), so an assertion pinned to one
    # historical task's content (AGENT_WORK_7) is permanently stale by
    # design — same pattern retired for AGENT_WORK_1 in TASK_110. Cat A
    # per docs/audit/test_debt_review.md.

    def test_check37_handoff_status_all_done(self, handoff_src):
        """Check 37 — DEV_HANDOFF.md Status is ALL_DONE."""
        lines = [ln.strip() for ln in handoff_src.splitlines() if ln.strip()]
        assert lines, "DEV_HANDOFF.md is empty"
        assert lines[-1] == "ALL_DONE", (
            f"DEV_HANDOFF.md last non-blank line is '{lines[-1]}', expected 'ALL_DONE'"
        )


# ===========================================================================
# LIVE DB CHECKS
# ===========================================================================

@db_required
class TestLiveDB:

    def _db_execute(self, sql, params=None):
        from dotenv import load_dotenv
        load_dotenv()
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            return s.execute(text(sql), params or {}).fetchall()

    def test_check38_file_load_rows_exist(self):
        """Check 38 — v_ingest_log returns at least one file_load row."""
        rows = self._db_execute(
            "SELECT count(*) FROM v_ingest_log WHERE channel='file_load'"
        )
        count = rows[0][0]
        assert count > 0, (
            f"No file_load rows in v_ingest_log (got {count})"
        )

    def test_check39_email_rows_exist(self):
        """Check 39 — v_ingest_log returns at least one email row."""
        rows = self._db_execute(
            "SELECT count(*) FROM v_ingest_log WHERE channel='email'"
        )
        count = rows[0][0]
        assert count > 0, (
            f"No email rows in v_ingest_log (got {count})"
        )

    def test_check40_view_has_8_columns(self):
        """Check 40 — v_ingest_log has exactly 8 columns."""
        rows = self._db_execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'v_ingest_log'
            ORDER BY ordinal_position
        """)
        col_names = [r[0] for r in rows]
        expected = [
            "channel", "source_kind", "source_ref", "feed",
            "target_tab", "data_date", "status", "processed_at",
        ]
        assert col_names == expected, (
            f"v_ingest_log columns mismatch.\n  Got:      {col_names}\n  Expected: {expected}"
        )

    def test_check41_date_filter_returns_correct_rows(self):
        """Check 41 — data_date filter returns only rows matching that date."""
        # Find a date that has file_load rows
        date_rows = self._db_execute("""
            SELECT DISTINCT data_date FROM v_ingest_log
            WHERE channel = 'file_load' AND data_date IS NOT NULL
            ORDER BY data_date DESC
            LIMIT 1
        """)
        if not date_rows:
            pytest.skip("No file_load rows with data_date to test filter")

        target_date = date_rows[0][0]
        filtered = self._db_execute(
            "SELECT channel, data_date FROM v_ingest_log WHERE data_date = :d",
            {"d": target_date}
        )
        assert len(filtered) > 0, f"Date filter returned 0 rows for {target_date}"
        for row in filtered:
            assert row[1] == target_date, (
                f"Date filter returned row with wrong date: {row[1]} (expected {target_date})"
            )

    def test_check42_channel_filter_returns_correct_rows(self):
        """Check 42 — channel = 'email' filter returns only email rows."""
        rows = self._db_execute(
            "SELECT DISTINCT channel FROM v_ingest_log WHERE channel = 'email'"
        )
        assert len(rows) == 1 and rows[0][0] == "email", (
            f"channel='email' filter returned unexpected channels: {[r[0] for r in rows]}"
        )
