"""
Tests for AGENT_WORK_10 — Fix the two issues from TEST_REPORT_9.

Fix 1 (CRITICAL): init_db failed with "cannot change name of view column fwd_5d_pct to
                  change_type". Root cause: CREATE OR REPLACE VIEW v_user_action_performance
                  tried to insert 5 new columns before an existing column. Fix: add
                  DROP VIEW IF EXISTS v_user_action_performance CASCADE; immediately before
                  each of the two CREATE OR REPLACE VIEW v_user_action_performance blocks.

Fix 2 (Minor):   colspan="8" in "Your actions" empty-state/error/loading rows should be
                 colspan="7" to match the 7-column thead.
                 The Rule scorecard table's colspan="8" is correct and must NOT have changed.

All DB tests auto-skip if Postgres is absent.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "db"
WEB_DIR = PROJECT_ROOT / "web"

BASELINE_SQL = DB_DIR / "baseline.sql"
RP_JS = WEB_DIR / "rule_performance.js"
RP_HTML = WEB_DIR / "rule_performance.html"
HANDOFF = PROJECT_ROOT / "DEV_HANDOFF.md"


def _sql() -> str:
    return BASELINE_SQL.read_text(encoding="utf-8")


def _rpjs() -> str:
    return RP_JS.read_text(encoding="utf-8")


def _rphtml() -> str:
    return RP_HTML.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Handoff verification
# ---------------------------------------------------------------------------

class TestHandoff:
    def test_status_all_done(self):
        content = HANDOFF.read_text(encoding="utf-8")
        assert "ALL_DONE" in content, "DEV_HANDOFF.md Status is not ALL_DONE"

    def test_mentions_drop_view_fix(self):
        content = HANDOFF.read_text(encoding="utf-8")
        assert "DROP VIEW IF EXISTS" in content, (
            "DEV_HANDOFF.md does not mention the DROP VIEW fix"
        )

    def test_mentions_colspan_fix(self):
        content = HANDOFF.read_text(encoding="utf-8")
        assert 'colspan' in content.lower(), (
            "DEV_HANDOFF.md does not mention the colspan fix"
        )


# ---------------------------------------------------------------------------
# Fix 1: baseline.sql — DROP VIEW IF EXISTS CASCADE before each CREATE
# ---------------------------------------------------------------------------

class TestDropViewFix:
    def test_two_drop_view_statements(self):
        """Both CREATE OR REPLACE VIEW definitions must be preceded by a DROP."""
        sql = _sql()
        drop_count = sql.count("DROP VIEW IF EXISTS v_user_action_performance CASCADE;")
        assert drop_count == 2, (
            f"Expected 2 DROP VIEW IF EXISTS v_user_action_performance CASCADE; "
            f"statements, found {drop_count}"
        )

    def test_two_create_view_statements(self):
        """There are exactly two CREATE OR REPLACE VIEW v_user_action_performance definitions."""
        sql = _sql()
        create_count = sql.count("CREATE OR REPLACE VIEW v_user_action_performance")
        assert create_count == 2, (
            f"Expected 2 CREATE OR REPLACE VIEW v_user_action_performance, found {create_count}"
        )

    def test_first_drop_before_first_create(self):
        """The first DROP must appear just before the first CREATE."""
        sql = _sql()
        first_drop_idx = sql.find("DROP VIEW IF EXISTS v_user_action_performance CASCADE;")
        first_create_idx = sql.find("CREATE OR REPLACE VIEW v_user_action_performance")
        assert first_drop_idx != -1, "First DROP VIEW not found"
        assert first_create_idx != -1, "First CREATE VIEW not found"
        assert first_drop_idx < first_create_idx, (
            "First DROP VIEW does not appear before the first CREATE VIEW"
        )
        between = sql[first_drop_idx:first_create_idx]
        assert len(between) < 300, (
            f"First DROP VIEW and CREATE VIEW are too far apart ({len(between)} chars)"
        )

    def test_second_drop_before_second_create(self):
        """The second DROP must appear just before the second CREATE."""
        sql = _sql()
        first_drop_end = sql.find("DROP VIEW IF EXISTS v_user_action_performance CASCADE;") + 50
        second_drop_idx = sql.find("DROP VIEW IF EXISTS v_user_action_performance CASCADE;", first_drop_end)
        first_create_end = sql.find("CREATE OR REPLACE VIEW v_user_action_performance") + 50
        second_create_idx = sql.find("CREATE OR REPLACE VIEW v_user_action_performance", first_create_end)
        assert second_drop_idx != -1, "Second DROP VIEW not found"
        assert second_create_idx != -1, "Second CREATE VIEW not found"
        assert second_drop_idx < second_create_idx, (
            "Second DROP VIEW does not appear before the second CREATE VIEW"
        )
        between = sql[second_drop_idx:second_create_idx]
        assert len(between) < 300, (
            f"Second DROP VIEW and CREATE VIEW are too far apart ({len(between)} chars)"
        )

    def test_cascade_on_both_drops(self):
        """Both DROP statements must include CASCADE."""
        sql = _sql()
        drops = re.findall(
            r'DROP VIEW IF EXISTS v_user_action_performance[^;]*;',
            sql
        )
        assert len(drops) == 2, f"Expected 2 DROP statements, found {len(drops)}"
        for drop in drops:
            assert "CASCADE" in drop, f"DROP statement missing CASCADE: {drop}"

    def test_new_columns_in_final_view(self):
        """The final (second) CREATE VIEW must include the 5 new columns."""
        sql = _sql()
        last_create_idx = sql.rfind("CREATE OR REPLACE VIEW v_user_action_performance")
        assert last_create_idx != -1
        block = sql[last_create_idx: last_create_idx + 3000]
        for col in ("change_type", "shares_delta", "attribution", "source_kind", "attributed_rule_ids"):
            assert col in block, (
                f"Column '{col}' missing from final v_user_action_performance definition"
            )

    def test_old_columns_still_in_final_view(self):
        """fwd_5d_pct and fwd_20d_pct must still appear in the final view definition."""
        sql = _sql()
        last_create_idx = sql.rfind("CREATE OR REPLACE VIEW v_user_action_performance")
        block = sql[last_create_idx: last_create_idx + 3000]
        assert "fwd_5d_pct" in block, (
            "fwd_5d_pct missing from final v_user_action_performance — backward compatibility broken"
        )
        assert "fwd_20d_pct" in block, (
            "fwd_20d_pct missing from final v_user_action_performance — backward compatibility broken"
        )


# ---------------------------------------------------------------------------
# Fix 2: colspan corrections in rule_performance.js and .html
# ---------------------------------------------------------------------------

class TestColspanFix:

    # ---- rule_performance.js ----

    def test_js_syntax_clean(self):
        result = subprocess.run(
            ["node", "--check", str(RP_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"node --check rule_performance.js failed:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_js_your_actions_empty_state_colspan_7(self):
        """'No actions logged yet' empty-state row must use colspan=7 (7-column Your-actions table)."""
        content = _rpjs()
        idx = content.find("No actions logged yet")
        assert idx != -1, "'No actions logged yet' empty-state not found in rule_performance.js"
        context = content[max(0, idx - 100): idx + 200]
        assert 'colspan="7"' in context, (
            f"'No actions logged yet' must use colspan=7, context:\n{context}"
        )
        assert 'colspan="8"' not in context, (
            "Your-actions empty-state still has colspan=8 — fix not applied"
        )

    def test_js_your_actions_error_row_colspan_7(self):
        """'Error loading actions' error row must use colspan=7."""
        content = _rpjs()
        idx = content.find("Error loading actions")
        assert idx != -1, "'Error loading actions' row not found in rule_performance.js"
        context = content[max(0, idx - 100): idx + 200]
        assert 'colspan="7"' in context, (
            f"'Error loading actions' row must use colspan=7, context:\n{context}"
        )
        assert 'colspan="8"' not in context, (
            "Your-actions error row still has colspan=8 — fix not applied"
        )

    def test_js_scorecard_loading_colspan_8_unchanged(self):
        """Rule scorecard loading row must still use colspan=8 (correct for 8-column table)."""
        content = _rpjs()
        idx = content.find("Loading scorecard")
        assert idx != -1, "'Loading scorecard' text not found in rule_performance.js"
        context = content[max(0, idx - 100): idx + 100]
        assert 'colspan="8"' in context, (
            "Scorecard loading row must retain colspan=8 — was incorrectly changed"
        )

    def test_js_scorecard_error_colspan_8_unchanged(self):
        """Rule scorecard error row must still use colspan=8."""
        content = _rpjs()
        idx = content.find("Failed to load scorecard")
        assert idx != -1, "'Failed to load scorecard' not found in rule_performance.js"
        # find the innerHTML assignment nearby
        context = content[idx: idx + 250]
        assert 'colspan="8"' in context, (
            "Scorecard error row must retain colspan=8"
        )

    # ---- rule_performance.html ----

    def test_html_syntax_has_closing_tag(self):
        content = _rphtml()
        assert "</html>" in content.lower(), "rule_performance.html missing </html>"

    def test_html_your_actions_loading_row_colspan_7(self):
        """'Loading…' initial row in myActionsBody must use colspan=7."""
        content = _rphtml()
        idx = content.find("myActionsBody")
        assert idx != -1, "myActionsBody not found in rule_performance.html"
        block = content[idx: idx + 300]
        assert 'colspan="7"' in block, (
            f"Your-actions Loading row must use colspan=7:\n{block}"
        )
        assert 'colspan="8"' not in block, (
            "Your-actions Loading row still has colspan=8 — fix not applied"
        )

    def test_html_scorecard_loading_row_colspan_8_unchanged(self):
        """Scorecard loading row in perfTableBody must still use colspan=8."""
        content = _rphtml()
        idx = content.find("perfTableBody")
        assert idx != -1, "perfTableBody not found in rule_performance.html"
        block = content[idx: idx + 400]
        assert 'colspan="8"' in block, (
            "Scorecard loading row must retain colspan=8 in rule_performance.html"
        )

    def test_html_your_actions_thead_7_columns(self):
        """Your-actions table <thead> must have exactly 7 <th> columns."""
        content = _rphtml()
        body_idx = content.find("myActionsBody")
        assert body_idx != -1
        section = content[max(0, body_idx - 2000): body_idx]
        thead_match = re.search(r'<thead>(.*?)</thead>', section, re.DOTALL | re.IGNORECASE)
        assert thead_match, "thead not found before myActionsBody in rule_performance.html"
        thead = thead_match.group(1)
        th_count = len(re.findall(r'<th[\s>]', thead, re.IGNORECASE))
        assert th_count == 7, (
            f"Your-actions thead must have 7 <th> columns, found {th_count}:\n{thead}"
        )

    def test_html_your_actions_column_labels(self):
        """The 7 Your-actions columns must include When, Symbol, Action, Source, Attribution."""
        content = _rphtml()
        body_idx = content.find("myActionsBody")
        section = content[max(0, body_idx - 2000): body_idx]
        thead_match = re.search(r'<thead>(.*?)</thead>', section, re.DOTALL | re.IGNORECASE)
        assert thead_match, "thead not found before myActionsBody"
        thead = thead_match.group(1)
        for label in ("When", "Symbol", "Action", "Source", "Attribution"):
            assert label in thead, (
                f"Column header '{label}' missing from Your-actions thead"
            )


# ---------------------------------------------------------------------------
# DB-integrated: verify init_db applied cleanly and DB objects are correct
# ---------------------------------------------------------------------------

class TestDatabaseAfterFix:
    """These tests require a live Postgres connection. Auto-skip if absent."""

    def test_db_drv_position_action_exists(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            r = s.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name='drv_position_action' AND table_schema='public'"
            )).fetchone()
        assert r is not None, (
            "drv_position_action table does not exist — run: python -m db.init_db"
        )

    def test_db_v_unified_track_record_exists(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            r = s.execute(text(
                "SELECT 1 FROM information_schema.views "
                "WHERE table_name='v_unified_track_record' AND table_schema='public'"
            )).fetchone()
        assert r is not None, "v_unified_track_record view does not exist"

    def test_db_v_user_action_performance_has_new_columns(self, db_available):
        """After init_db fix, the view must expose all 5 new columns without losing old ones."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            rows = s.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='v_user_action_performance' AND table_schema='public'"
            )).fetchall()
        cols = {r[0] for r in rows}
        required_new = {"change_type", "shares_delta", "attribution", "source_kind", "attributed_rule_ids"}
        required_old = {"fwd_5d_pct", "fwd_20d_pct"}
        missing_new = required_new - cols
        missing_old = required_old - cols
        assert not missing_new, (
            f"v_user_action_performance missing new columns: {missing_new}"
        )
        assert not missing_old, (
            f"v_user_action_performance lost old columns: {missing_old} — backward compatibility broken"
        )

    def test_db_new_cols_precede_fwd_cols_in_ordinal_order(self, db_available):
        """New columns (change_type, etc.) must appear before fwd_5d_pct in ordinal position."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            rows = s.execute(text(
                "SELECT column_name, ordinal_position FROM information_schema.columns "
                "WHERE table_name='v_user_action_performance' AND table_schema='public' "
                "ORDER BY ordinal_position"
            )).fetchall()
        col_positions = {r[0]: r[1] for r in rows}
        assert "change_type" in col_positions, "change_type column missing from view"
        assert "fwd_5d_pct" in col_positions, "fwd_5d_pct column missing from view"
        assert col_positions["change_type"] < col_positions["fwd_5d_pct"], (
            f"change_type (pos {col_positions['change_type']}) must precede "
            f"fwd_5d_pct (pos {col_positions['fwd_5d_pct']})"
        )

    def test_db_view_queryable_with_all_columns(self, db_available):
        """SELECT all expected columns from v_user_action_performance must not raise an error."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            result = s.execute(text(
                "SELECT id, acted_at, tos_symbol, user_action, consolidated_action, "
                "change_type, shares_delta, attribution, source_kind, attributed_rule_ids, "
                "fwd_5d_pct, fwd_20d_pct FROM v_user_action_performance LIMIT 0"
            )).fetchall()
        assert isinstance(result, list)

    def test_db_my_actions_endpoint_returns_200(self, db_available):
        """GET /api/rules/my-actions must return HTTP 200 (was 500 before the fix)."""
        if not db_available:
            pytest.skip("Postgres not available")
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/rules/my-actions")
        assert resp.status_code == 200, (
            f"GET /api/rules/my-actions returned {resp.status_code}: {resp.text[:300]}\n"
            "Expected 200 — the init_db fix may not have been applied yet"
        )
        data = resp.json()
        assert "summary" in data and "recent" in data, (
            f"my-actions response missing summary/recent keys: {data}"
        )
