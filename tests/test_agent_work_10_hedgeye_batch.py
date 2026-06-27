"""
Verification tests for AGENT_WORK_10 — Hedgeye batch
(TASK_97 feed_code, TASK_100 hedgeye router, P3 notes, P4 digest, per-symbol dossier, LLM).

All tests are pure-Python or DB-backed; none require a running HTTP server.
DB tests skip automatically if Postgres is unreachable.
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).parent.parent
WEB = PROJECT / "web"
API_ROUTERS = PROJECT / "api" / "routers"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_session():
    """Return a live session or None if Postgres unreachable."""
    try:
        os.chdir(str(PROJECT))
        from dotenv import load_dotenv
        load_dotenv()
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            s.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_session()

skip_no_db = pytest.mark.skipif(not DB_AVAILABLE, reason="Postgres not available")


# ---------------------------------------------------------------------------
# 1. Syntax — all 7 new/changed files parse cleanly
# ---------------------------------------------------------------------------

class TestSyntax:
    @pytest.mark.parametrize("relpath", [
        "api/main.py",
        "api/routers/hedgeye.py",
        "api/routers/pages.py",
    ])
    def test_python_syntax(self, relpath):
        src = (PROJECT / relpath).read_text(encoding="utf-8")
        tree = ast.parse(src)
        assert tree is not None, f"{relpath} failed to parse"

    @pytest.mark.parametrize("relpath", [
        "web/hedgeye_panel.js",
        "web/notes.js",
        "web/digest.js",
        "web/symbol_hedgeye.js",
    ])
    def test_js_syntax(self, relpath):
        result = subprocess.run(
            ["node", "--check", str(PROJECT / relpath)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"{relpath}: {result.stderr}"


# ---------------------------------------------------------------------------
# 2. DB — feed_code column + v_feed_catalog populated
# ---------------------------------------------------------------------------

class TestDbFeedCode:
    @skip_no_db
    def test_feed_code_column_exists_on_ref_load_files(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            row = s.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='ref_load_files' AND column_name='feed_code'"
            )).first()
        assert row is not None, "feed_code column missing from ref_load_files"

    @skip_no_db
    def test_v_feed_catalog_has_rows(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            n = s.execute(text("SELECT count(*) FROM v_feed_catalog")).scalar()
        assert n > 0, "v_feed_catalog is empty"

    @skip_no_db
    def test_v_feed_catalog_has_expected_count(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            n = s.execute(text("SELECT count(*) FROM v_feed_catalog")).scalar()
        # DEV_HANDOFF says 29 rows
        assert n >= 20, f"v_feed_catalog has only {n} rows, expected >= 20"

    @skip_no_db
    def test_overlapping_feeds_both_channels(self):
        """Feeds that exist in both file-based and email-based channels."""
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            rows = s.execute(text(
                "SELECT feed_code FROM v_feed_catalog "
                "WHERE file_type IS NOT NULL AND email_type IS NOT NULL "
                "ORDER BY feed_code"
            )).fetchall()
        codes = [r[0] for r in rows]
        # Expect at least 5 overlapping feeds per spec
        assert len(codes) >= 5, f"Only {len(codes)} overlapping feeds: {codes}"

    @skip_no_db
    def test_risk_range_feed_code_populated(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            row = s.execute(text(
                "SELECT feed_code FROM ref_load_files WHERE feed_code = 'RISK_RANGE' LIMIT 1"
            )).first()
        assert row is not None, "RISK_RANGE feed_code not set in ref_load_files"

    @skip_no_db
    def test_ref_hedgeye_email_type_has_rows(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            n = s.execute(text("SELECT count(*) FROM ref_hedgeye_email_type")).scalar()
        assert n > 0, "ref_hedgeye_email_type is empty"


# ---------------------------------------------------------------------------
# 3. API routes — all 11 hedgeye router paths present
# ---------------------------------------------------------------------------

class TestHedgeyeRoutes:
    @pytest.fixture(scope="class")
    def route_map(self):
        os.chdir(str(PROJECT))
        sys.path.insert(0, str(PROJECT))
        from dotenv import load_dotenv
        load_dotenv()
        from api.routers import hedgeye
        return {(r.path, m) for r in hedgeye.router.routes
                if hasattr(r, "methods")
                for m in r.methods}

    @pytest.mark.parametrize("path,method", [
        ("/api/actionable/hedgeye", "GET"),
        ("/api/notes", "GET"),
        ("/api/notes/source-types", "GET"),
        ("/api/rule-candidates", "GET"),
        ("/api/rule-candidates", "POST"),
        ("/api/rule-candidates/{cid}", "PATCH"),
        ("/api/digest/preopen", "GET"),
        ("/api/digest/weekly", "GET"),
        ("/api/macro/hedgeye-quad", "GET"),
        ("/api/symbol/{sym}/hedgeye", "GET"),
        ("/api/notes/{message_id}/llm", "GET"),
    ])
    def test_route_present(self, route_map, path, method):
        assert (path, method) in route_map, \
            f"Route {method} {path} not found in hedgeye router"


# ---------------------------------------------------------------------------
# 4. Page routes — /notes /digest /symbol-hedgeye present
# ---------------------------------------------------------------------------

class TestPageRoutes:
    @pytest.fixture(scope="class")
    def page_paths(self):
        os.chdir(str(PROJECT))
        sys.path.insert(0, str(PROJECT))
        from dotenv import load_dotenv
        load_dotenv()
        from api.routers import pages
        return {r.path for r in pages.router.routes if hasattr(r, "path")}

    @pytest.mark.parametrize("path", ["/notes", "/digest", "/symbol-hedgeye"])
    def test_page_route_present(self, page_paths, path):
        assert path in page_paths, f"Page route {path} missing from pages router"


# ---------------------------------------------------------------------------
# 5. hedgeye router registered in main.py
# ---------------------------------------------------------------------------

class TestMainPyRegistration:
    def test_hedgeye_in_router_list(self):
        src = (PROJECT / "api" / "main.py").read_text(encoding="utf-8")
        assert '"hedgeye"' in src or "'hedgeye'" in src, \
            "hedgeye not in router name list in main.py"

    def test_include_router_hedgeye(self):
        src = (PROJECT / "api" / "main.py").read_text(encoding="utf-8")
        assert "hedgeye.router" in src, \
            "app.include_router(hedgeye.router) not found in main.py"


# ---------------------------------------------------------------------------
# 6. Live DB — underlying tables accessible and populated
# ---------------------------------------------------------------------------

class TestDbTables:
    @skip_no_db
    def test_note_repo_has_rows(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            n = s.execute(text("SELECT count(*) FROM note_repo")).scalar()
        assert n >= 30, f"note_repo has {n} rows, expected >= 30"

    @skip_no_db
    def test_hist_rta_accessible(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            n = s.execute(text("SELECT count(*) FROM hist_rta")).scalar()
        assert n >= 0  # table must exist; 0 rows is acceptable

    @skip_no_db
    def test_hist_call_top5_accessible(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            n = s.execute(text("SELECT count(*) FROM hist_call_top5")).scalar()
        assert n >= 0

    @skip_no_db
    def test_hist_hedgeye_stance_accessible(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            n = s.execute(text("SELECT count(*) FROM hist_hedgeye_stance")).scalar()
        assert n >= 0

    @skip_no_db
    def test_drv_rr_trend_change_accessible(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            n = s.execute(text("SELECT count(*) FROM drv_rr_trend_change")).scalar()
        assert n >= 0

    @skip_no_db
    def test_rule_candidate_table_schema(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            cols = {r[0] for r in s.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='rule_candidate'"
            )).fetchall()}
        required = {"candidate_id", "title", "hypothesis", "linked_note_ids",
                    "proposed_rule_def", "status", "promoted_rule_id",
                    "created_at", "updated_at"}
        missing = required - cols
        assert not missing, f"rule_candidate missing columns: {missing}"

    @skip_no_db
    def test_llm_analysis_table_schema(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            cols = {r[0] for r in s.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='llm_analysis'"
            )).fetchall()}
        required = {"message_id", "model", "prompt_version", "json_output", "created_at"}
        missing = required - cols
        assert not missing, f"llm_analysis missing columns: {missing}"

    @skip_no_db
    def test_note_repo_source_types_populated(self):
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            types = {r[0] for r in s.execute(text(
                "SELECT DISTINCT source_type FROM note_repo"
            )).fetchall()}
        assert len(types) >= 5, f"Only {len(types)} source_types in note_repo"


# ---------------------------------------------------------------------------
# 7. HTML files — title / styles.css / nav / script tags
# ---------------------------------------------------------------------------

class TestHtmlFiles:
    @pytest.mark.parametrize("filename,expected_title,expected_js", [
        ("notes.html", "Notes", "notes.js"),
        ("digest.html", "Digest", "digest.js"),
        ("symbol_hedgeye.html", "Hedgeye", "symbol_hedgeye.js"),
    ])
    def test_html_has_title(self, filename, expected_title, expected_js):
        content = (WEB / filename).read_text(encoding="utf-8")
        assert expected_title in content, \
            f"{filename}: expected title containing '{expected_title}'"

    @pytest.mark.parametrize("filename,expected_title,expected_js", [
        ("notes.html", "Notes", "notes.js"),
        ("digest.html", "Digest", "digest.js"),
        ("symbol_hedgeye.html", "Hedgeye", "symbol_hedgeye.js"),
    ])
    def test_html_loads_styles_css(self, filename, expected_title, expected_js):
        content = (WEB / filename).read_text(encoding="utf-8")
        assert "styles.css" in content, f"{filename}: styles.css not linked"

    @pytest.mark.parametrize("filename,expected_title,expected_js", [
        ("notes.html", "Notes", "notes.js"),
        ("digest.html", "Digest", "digest.js"),
        ("symbol_hedgeye.html", "Hedgeye", "symbol_hedgeye.js"),
    ])
    def test_html_has_nav(self, filename, expected_title, expected_js):
        content = (WEB / filename).read_text(encoding="utf-8")
        assert "nav-menu" in content or "<nav" in content, \
            f"{filename}: no nav element found"

    @pytest.mark.parametrize("filename,expected_title,expected_js", [
        ("notes.html", "Notes", "notes.js"),
        ("digest.html", "Digest", "digest.js"),
        ("symbol_hedgeye.html", "Hedgeye", "symbol_hedgeye.js"),
    ])
    def test_html_loads_js(self, filename, expected_title, expected_js):
        content = (WEB / filename).read_text(encoding="utf-8")
        assert expected_js in content, \
            f"{filename}: {expected_js} not found in script tags"


# ---------------------------------------------------------------------------
# 8. Endpoint response structure (no HTTP server — call functions directly)
# ---------------------------------------------------------------------------

class TestEndpointStructure:
    @skip_no_db
    def test_actionable_hedgeye_response_keys(self):
        os.chdir(str(PROJECT))
        from dotenv import load_dotenv
        load_dotenv()
        from api.routers.hedgeye import actionable_hedgeye
        result = actionable_hedgeye(date="2026-06-26")
        assert isinstance(result, dict)
        for key in ("date", "top5", "alerts", "trend_flips", "stance"):
            assert key in result, f"actionable_hedgeye missing key: {key}"

    @skip_no_db
    def test_actionable_hedgeye_stance_has_bullish_bearish(self):
        from api.routers.hedgeye import actionable_hedgeye
        result = actionable_hedgeye(date="2026-06-26")
        assert "bullish" in result["stance"]
        assert "bearish" in result["stance"]

    @skip_no_db
    def test_actionable_hedgeye_top5_is_list(self):
        from api.routers.hedgeye import actionable_hedgeye
        result = actionable_hedgeye(date="2026-06-26")
        assert isinstance(result["top5"], list)

    @skip_no_db
    def test_list_notes_returns_list(self):
        from api.routers.hedgeye import list_notes
        result = list_notes(date=None, ticker=None, source_type=None, q=None, limit=50)
        assert isinstance(result, list)

    @skip_no_db
    def test_list_notes_filter_by_source_type(self):
        from api.routers.hedgeye import list_notes
        result = list_notes(source_type="early_look", date=None, ticker=None, q=None, limit=50)
        assert isinstance(result, list)
        for row in result:
            assert row["source_type"] == "early_look"

    @skip_no_db
    def test_note_source_types_returns_list_of_dicts(self):
        from api.routers.hedgeye import note_source_types
        result = note_source_types()
        assert isinstance(result, list)
        for item in result:
            assert "source_type" in item
            assert "count" in item

    @skip_no_db
    def test_list_rule_candidates_returns_list(self):
        from api.routers.hedgeye import list_rule_candidates
        result = list_rule_candidates(status=None)
        assert isinstance(result, list)

    @skip_no_db
    def test_digest_preopen_structure(self):
        from api.routers.hedgeye import digest_preopen
        result = digest_preopen(date="2026-06-26")
        assert "date" in result
        assert "sections" in result
        assert "overnight_alerts" in result
        assert isinstance(result["sections"], list)
        assert len(result["sections"]) == 3

    @skip_no_db
    def test_digest_weekly_structure(self):
        from api.routers.hedgeye import digest_weekly
        result = digest_weekly(date="2026-06-26")
        assert "date" in result
        assert "portfolio_solutions" in result
        assert "notes" in result

    @skip_no_db
    def test_hedgeye_quad_returns_quad_key(self):
        from api.routers.hedgeye import hedgeye_quad
        result = hedgeye_quad(date="2026-06-26")
        assert "quad" in result

    @skip_no_db
    def test_symbol_hedgeye_structure(self):
        from api.routers.hedgeye import symbol_hedgeye
        result = symbol_hedgeye(sym="AAPL", date="2026-06-26")
        assert "symbol" in result
        assert result["symbol"] == "AAPL"
        for key in ("risk_range", "trend_flips", "alerts", "ii_changes",
                    "etf_changes", "top5", "notes"):
            assert key in result, f"symbol_hedgeye missing key: {key}"

    @skip_no_db
    def test_note_llm_returns_enriched_list(self):
        from api.routers.hedgeye import note_llm
        result = note_llm(message_id="nonexistent-message-id")
        assert "message_id" in result
        assert "enriched" in result
        assert isinstance(result["enriched"], list)
        # Non-existent message_id → empty list, not error
        assert len(result["enriched"]) == 0


# ---------------------------------------------------------------------------
# 9. Rule-candidate CRUD (create + read + patch)
# ---------------------------------------------------------------------------

class TestRuleCandidateCrud:
    @skip_no_db
    def test_create_and_list_rule_candidate(self):
        from api.routers.hedgeye import create_rule_candidate, list_rule_candidates
        payload = {
            "title": "Test candidate from AGENT_WORK_10 tests",
            "hypothesis": "When X fires, Y happens",
            "status": "draft",
        }
        result = create_rule_candidate(payload)
        assert "candidate_id" in result
        cid = result["candidate_id"]
        assert isinstance(cid, int)

        # Verify it appears in list
        candidates = list_rule_candidates(status=None)
        ids = [c["candidate_id"] for c in candidates]
        assert cid in ids, "Newly created candidate not found in list"

    @skip_no_db
    def test_patch_rule_candidate(self):
        from api.routers.hedgeye import create_rule_candidate, update_rule_candidate, list_rule_candidates
        # Create one first
        result = create_rule_candidate({
            "title": "Patch target from tests",
            "hypothesis": "Original hypothesis",
            "status": "draft",
        })
        cid = result["candidate_id"]

        # Patch it
        patch_result = update_rule_candidate(cid=cid, payload={"status": "active"})
        assert patch_result["candidate_id"] == cid

        # Verify updated status
        candidates = list_rule_candidates(status="active")
        ids = [c["candidate_id"] for c in candidates]
        assert cid in ids, "Patched candidate not found in active status list"

    @skip_no_db
    def test_patch_nonexistent_candidate_raises_404(self):
        from fastapi import HTTPException
        from api.routers.hedgeye import update_rule_candidate
        with pytest.raises(HTTPException) as exc_info:
            update_rule_candidate(cid=999999999, payload={"status": "active"})
        assert exc_info.value.status_code == 404

    @skip_no_db
    def test_patch_with_no_updatable_fields_raises_400(self):
        from fastapi import HTTPException
        from api.routers.hedgeye import update_rule_candidate
        with pytest.raises(HTTPException) as exc_info:
            update_rule_candidate(cid=1, payload={})
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# 10. Nav links in existing screens
# ---------------------------------------------------------------------------

class TestNavLinks:
    @pytest.mark.parametrize("filename", [
        "index.html",
        "digest.html",
        "notes.html",
    ])
    def test_notes_link_present(self, filename):
        content = (WEB / filename).read_text(encoding="utf-8")
        assert 'href="/notes"' in content, f"{filename}: /notes nav link missing"

    @pytest.mark.parametrize("filename", [
        "index.html",
        "digest.html",
        "notes.html",
    ])
    def test_digest_link_present(self, filename):
        content = (WEB / filename).read_text(encoding="utf-8")
        assert 'href="/digest"' in content, f"{filename}: /digest nav link missing"

    def test_index_html_has_both_new_links(self):
        content = (WEB / "index.html").read_text(encoding="utf-8")
        assert 'href="/notes"' in content
        assert 'href="/digest"' in content

    def test_new_screens_have_actionable_link(self):
        """New screens should link back to /actionable."""
        for fname in ("notes.html", "digest.html"):
            content = (WEB / fname).read_text(encoding="utf-8")
            assert 'href="/actionable"' in content, \
                f"{fname}: /actionable nav link missing"


# ---------------------------------------------------------------------------
# 11. No SQL injection risk — parametrised queries only
# ---------------------------------------------------------------------------

class TestSqlInjectionSafety:
    def test_no_fstring_sql_in_hedgeye_py(self):
        """All dynamic SQL must use bind parameters, not f-strings."""
        src = (API_ROUTERS / "hedgeye.py").read_text(encoding="utf-8")
        # Look for obvious f-string SQL patterns on a SINGLE line:
        # e.g.  f"SELECT ... {var}" or f'INSERT ... {var}'
        import re
        # Match f"..." or f'...' containing both a SQL keyword and a {variable}
        # within the same quoted segment (no DOTALL — stay on single line)
        pattern = re.compile(
            r'f["\'](?:[^"\'\n])*(?:SELECT|INSERT|UPDATE|DELETE|FROM|WHERE)'
            r'(?:[^"\'\n])*\{[^}]+\}',
            re.IGNORECASE
        )
        match = pattern.search(src)
        assert match is None, \
            f"Possible f-string SQL injection risk in hedgeye.py: {match.group()[:120] if match else ''}"

    def test_hedgeye_uses_bind_params(self):
        """hedgeye.py should use :param style bind parameters."""
        src = (API_ROUTERS / "hedgeye.py").read_text(encoding="utf-8")
        # Should contain at least 5 :param references
        import re
        params = re.findall(r':\w+', src)
        assert len(params) >= 5, \
            f"Expected >= 5 bind params in hedgeye.py, found {len(params)}"
