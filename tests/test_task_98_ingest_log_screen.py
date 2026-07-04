"""
Tests for TASK_98 / AGENT_WORK_8 — Ingest Log dashboard screen.

Acceptance criteria verified (pure-Python, no DB required):

  File existence
    Check 01 — web/ingest_log.html exists
    Check 02 — web/ingest_log.js exists

  Syntax
    Check 03 — ingest_log.js passes node --check (syntax valid)
    Check 04 — pages.py is valid Python (ast.parse)
    Check 05 — monitor.py is valid Python (ast.parse)

  HTML content — ingest_log.html
    Check 06 — has <title> containing "Ingest Log"
    Check 07 — loads /static/styles.css
    Check 08 — loads /static/ingest_log.js
    Check 09 — has nav link <a href="/ingest-log"> with "active" class
    Check 10 — filter bar has Channel select with All/file_load/email options
    Check 11 — filter bar has Feed text input
    Check 12 — filter bar has Date date input
    Check 13 — filter bar has Clear button
    Check 14 — table has 8 correct column headers (When, Channel, Source, Feed,
               Target table, Data date, Status, Reference)
    Check 15 — has row count display element (id="rowCount")
    Check 16 — has Refresh button in header

  JS content — ingest_log.js
    Check 17 — fetches /api/ingest-log
    Check 18 — builds querystring with channel, feed, date, limit params
    Check 19 — renders email badge for source_kind='email'
    Check 20 — displays row count
    Check 21 — handles empty result (No records found)
    Check 22 — handles fetch error gracefully
    Check 23 — Clear button resets filters and reloads
    Check 24 — initial load() called on page load
    Check 25 — no hardcoded data (no inline sample rows)

  pages.py — page route
    Check 26 — GET /ingest-log route present
    Check 27 — route serves ingest_log.html via FileResponse
    Check 28 — route follows same pattern as other page routes

  Nav links — added to all required screens
    Check 29 — web/index.html has /ingest-log nav link
    Check 30 — web/file_monitor.html has /ingest-log nav link
    Check 31 — web/actionable.html has /ingest-log nav link
    Check 32 — web/portfolio.html has /ingest-log nav link
    Check 33 — web/rules.html has /ingest-log nav link
    Check 34 — web/groups.html has /ingest-log nav link
    Check 35 — web/rule_performance.html has /ingest-log nav link
    Check 36 — web/trace.html has /ingest-log nav link
    Check 37 — web/rule_flow.html has /ingest-log nav link
    Check 38 — web/ref.html has /ingest-log nav link
    Check 39 — web/explore.html has /ingest-log nav link
    Check 40 — web/dbstats.html has /ingest-log nav link
    Check 41 — web/param_sets.html has /ingest-log nav link

  API availability
    Check 42 — /api/ingest-log route intact in monitor.py (import check)

  DEV_HANDOFF
    Check 43 — DEV_HANDOFF.md references AGENT_WORK_8
    Check 44 — DEV_HANDOFF.md Status is ALL_DONE
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

HTML_FILE   = PROJECT / "web" / "ingest_log.html"
JS_FILE     = PROJECT / "web" / "ingest_log.js"
PAGES_PY    = PROJECT / "api" / "routers" / "pages.py"
MONITOR_PY  = PROJECT / "api" / "routers" / "monitor.py"
DEV_HANDOFF = PROJECT / "DEV_HANDOFF.md"

# Screens that must have the nav link
NAV_SCREENS = [
    "index.html",
    "file_monitor.html",
    "actionable.html",
    "portfolio.html",
    "rules.html",
    "groups.html",
    "rule_performance.html",
    "trace.html",
    "rule_flow.html",
    "ref.html",
    "explore.html",
    "dbstats.html",
    "param_sets.html",
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def html_src() -> str:
    assert HTML_FILE.exists(), f"Missing: {HTML_FILE}"
    return _read(HTML_FILE)


@pytest.fixture(scope="module")
def js_src() -> str:
    assert JS_FILE.exists(), f"Missing: {JS_FILE}"
    return _read(JS_FILE)


@pytest.fixture(scope="module")
def pages_src() -> str:
    assert PAGES_PY.exists(), f"Missing: {PAGES_PY}"
    return _read(PAGES_PY)


@pytest.fixture(scope="module")
def monitor_src() -> str:
    assert MONITOR_PY.exists(), f"Missing: {MONITOR_PY}"
    return _read(MONITOR_PY)


@pytest.fixture(scope="module")
def handoff_src() -> str:
    assert DEV_HANDOFF.exists(), f"Missing: {DEV_HANDOFF}"
    return _read(DEV_HANDOFF)


# ===========================================================================
# FILE EXISTENCE
# ===========================================================================

class TestFileExistence:

    def test_check01_html_exists(self):
        """Check 01 — web/ingest_log.html exists."""
        assert HTML_FILE.exists(), f"web/ingest_log.html not found at {HTML_FILE}"

    def test_check02_js_exists(self):
        """Check 02 — web/ingest_log.js exists."""
        assert JS_FILE.exists(), f"web/ingest_log.js not found at {JS_FILE}"


# ===========================================================================
# SYNTAX CHECKS
# ===========================================================================

class TestSyntax:

    def test_check03_js_node_syntax(self):
        """Check 03 — ingest_log.js passes node --check."""
        result = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check failed for ingest_log.js:\n{result.stderr}"
        )

    def test_check04_pages_py_syntax(self, pages_src):
        """Check 04 — pages.py is valid Python."""
        try:
            ast.parse(pages_src)
        except SyntaxError as e:
            pytest.fail(f"pages.py has a syntax error: {e}")

    def test_check05_monitor_py_syntax(self, monitor_src):
        """Check 05 — monitor.py is valid Python."""
        try:
            ast.parse(monitor_src)
        except SyntaxError as e:
            pytest.fail(f"monitor.py has a syntax error: {e}")


# ===========================================================================
# HTML CONTENT CHECKS
# ===========================================================================

class TestHtmlContent:

    def test_check06_title_contains_ingest_log(self, html_src):
        """Check 06 — <title> contains 'Ingest Log'."""
        assert "<title>" in html_src, "No <title> tag in ingest_log.html"
        import re
        m = re.search(r'<title>(.*?)</title>', html_src, re.IGNORECASE)
        assert m, "No <title>...</title> found"
        assert "Ingest Log" in m.group(1), (
            f"Title does not contain 'Ingest Log': {m.group(1)!r}"
        )

    def test_check07_loads_styles_css(self, html_src):
        """Check 07 — loads /static/styles.css."""
        assert "styles.css" in html_src, (
            "styles.css not referenced in ingest_log.html"
        )

    def test_check08_loads_ingest_log_js(self, html_src):
        """Check 08 — loads /static/ingest_log.js."""
        assert "ingest_log.js" in html_src, (
            "ingest_log.js not referenced in ingest_log.html"
        )

    def test_check09_nav_active_link(self, html_src):
        """Check 09 — nav link to /ingest-log has 'active' class (self-link)."""
        assert 'href="/ingest-log"' in html_src or "href='/ingest-log'" in html_src, (
            "/ingest-log link missing from nav in ingest_log.html"
        )
        # The self-link should be marked active
        import re
        m = re.search(r'href=["\']\/ingest-log["\'][^>]*class=["\'][^"\']*active', html_src)
        m2 = re.search(r'class=["\'][^"\']*active[^"\']*["\'][^>]*href=["\']\/ingest-log["\']', html_src)
        assert m or m2, (
            "/ingest-log nav link does not have 'active' class in ingest_log.html"
        )

    def test_check10_channel_select_with_options(self, html_src):
        """Check 10 — filter bar has Channel select with All/file_load/email options."""
        assert "channelSelect" in html_src or 'id="channelSelect"' in html_src, (
            "Channel select (id=channelSelect) missing from ingest_log.html"
        )
        assert "file_load" in html_src, (
            "'file_load' option missing from Channel select in ingest_log.html"
        )
        assert ">email<" in html_src or '"email"' in html_src, (
            "'email' option missing from Channel select in ingest_log.html"
        )

    def test_check11_feed_text_input(self, html_src):
        """Check 11 — filter bar has Feed text input."""
        assert 'id="feedInput"' in html_src or "feedInput" in html_src, (
            "Feed text input (id=feedInput) missing from ingest_log.html"
        )
        assert 'type="text"' in html_src, (
            "text input missing from filter bar in ingest_log.html"
        )

    def test_check12_date_input(self, html_src):
        """Check 12 — filter bar has Date date input."""
        assert 'id="dateInput"' in html_src or "dateInput" in html_src, (
            "Date input (id=dateInput) missing from ingest_log.html"
        )
        assert 'type="date"' in html_src, (
            "date input missing from filter bar in ingest_log.html"
        )

    def test_check13_clear_button(self, html_src):
        """Check 13 — filter bar has Clear button."""
        assert 'id="clearBtn"' in html_src or "clearBtn" in html_src, (
            "Clear button (id=clearBtn) missing from ingest_log.html"
        )
        assert "Clear" in html_src, (
            "Clear button label missing from ingest_log.html"
        )

    def test_check14_table_8_columns(self, html_src):
        """Check 14 — table has 8 correct column headers."""
        expected_headers = [
            "When", "Channel", "Source", "Feed",
            "Target table", "Data date", "Status", "Reference",
        ]
        for header in expected_headers:
            assert header in html_src, (
                f"Column header '{header}' missing from table in ingest_log.html"
            )
        # Count <th> tags to verify exactly 8 (use \b to avoid matching <thead>)
        import re
        ths = re.findall(r'<th\b[^>]*>', html_src, re.IGNORECASE)
        assert len(ths) == 8, (
            f"Expected 8 <th> elements in table, found {len(ths)}"
        )

    def test_check15_row_count_element(self, html_src):
        """Check 15 — has row count display element (id='rowCount')."""
        assert 'id="rowCount"' in html_src or "rowCount" in html_src, (
            "Row count element (id=rowCount) missing from ingest_log.html"
        )

    def test_check16_refresh_button(self, html_src):
        """Check 16 — has Refresh button in header."""
        assert 'id="refreshBtn"' in html_src or "refreshBtn" in html_src, (
            "Refresh button (id=refreshBtn) missing from ingest_log.html"
        )
        assert "Refresh" in html_src, (
            "Refresh button label missing from ingest_log.html"
        )


# ===========================================================================
# JS CONTENT CHECKS
# ===========================================================================

class TestJsContent:

    def test_check17_fetches_api_ingest_log(self, js_src):
        """Check 17 — fetches /api/ingest-log."""
        assert "/api/ingest-log" in js_src, (
            "fetch('/api/ingest-log') not found in ingest_log.js"
        )

    def test_check18_builds_querystring(self, js_src):
        """Check 18 — builds querystring with channel, feed, date, limit params."""
        for param in ("channel", "feed", "date", "limit"):
            assert param in js_src, (
                f"Querystring param '{param}' not found in ingest_log.js"
            )
        assert "encodeURIComponent" in js_src or "URLSearchParams" in js_src, (
            "URL encoding (encodeURIComponent or URLSearchParams) missing from ingest_log.js"
        )

    def test_check19_email_badge(self, js_src):
        """Check 19 — renders email badge for source_kind='email'."""
        assert "source_kind" in js_src, (
            "source_kind field not referenced in ingest_log.js"
        )
        assert "badge-email" in js_src or "email" in js_src, (
            "Email badge class (.badge-email) not found in ingest_log.js"
        )
        # Check specific condition
        assert "'email'" in js_src or '"email"' in js_src, (
            "email literal not found in ingest_log.js badge logic"
        )

    def test_check20_row_count_display(self, js_src):
        """Check 20 — displays row count."""
        assert "rowCount" in js_src, (
            "rowCount element not referenced in ingest_log.js"
        )
        assert "rows.length" in js_src or ".length" in js_src, (
            "row count calculation missing from ingest_log.js"
        )

    def test_check21_empty_result_message(self, js_src):
        """Check 21 — handles empty result with 'No records found.' message."""
        assert "No records found" in js_src, (
            "'No records found' message missing from ingest_log.js"
        )

    def test_check22_error_handling(self, js_src):
        """Check 22 — handles fetch error gracefully."""
        assert ".catch" in js_src or "catch" in js_src, (
            "Error handling (.catch) missing from ingest_log.js"
        )
        assert "Error" in js_src, (
            "Error display missing from ingest_log.js"
        )

    def test_check23_clear_button_resets_filters(self, js_src):
        """Check 23 — Clear button resets filters and calls load()."""
        assert "clearBtn" in js_src, (
            "clearBtn not referenced in ingest_log.js"
        )
        # Clear should reset each filter input
        assert "channelSel.value" in js_src or "channelSelect" in js_src, (
            "Channel select not reset in clearBtn handler in ingest_log.js"
        )
        assert "feedInput.value" in js_src, (
            "Feed input not reset in clearBtn handler in ingest_log.js"
        )
        assert "dateInput.value" in js_src, (
            "Date input not reset in clearBtn handler in ingest_log.js"
        )

    def test_check24_initial_load_called(self, js_src):
        """Check 24 — initial load() called on page load."""
        # The IIFE should call load() at the bottom
        assert js_src.rstrip().endswith("}());") or "load();" in js_src, (
            "Initial load() call not found at end of ingest_log.js"
        )
        # Verify load() is called after all wiring
        import re
        # Should find standalone load(); call (not a function definition)
        calls = re.findall(r'\bload\(\);', js_src)
        assert len(calls) >= 1, (
            "No load() call found in ingest_log.js"
        )

    def test_check25_no_hardcoded_data(self, js_src):
        """Check 25 — no hardcoded sample row data in JS."""
        import re
        # Check for suspicious hardcoded ticker/date patterns in sample data
        # Reject obvious hardcoded data arrays like [{symbol: 'SPY', ...}]
        hardcoded_patterns = [
            r'\{.*?symbol.*?:.*?["\']SPY["\']',
            r'\{.*?feed.*?:.*?["\']RR["\'].*?date',
        ]
        for pattern in hardcoded_patterns:
            m = re.search(pattern, js_src)
            assert not m, (
                f"Possible hardcoded data found in ingest_log.js: {m.group()[:60]!r}"
            )
        # The JS should read all data from the fetch response
        assert "fetch(" in js_src, (
            "fetch() not found — data must come from API"
        )


# ===========================================================================
# PAGES.PY ROUTE CHECKS
# ===========================================================================

class TestPagesRoute:

    def test_check26_ingest_log_route_present(self, pages_src):
        """Check 26 — GET /ingest-log route present in pages.py."""
        assert '"/ingest-log"' in pages_src or "'/ingest-log'" in pages_src, (
            "@router.get('/ingest-log') not found in pages.py"
        )

    def test_check27_serves_ingest_log_html(self, pages_src):
        """Check 27 — route serves ingest_log.html via FileResponse."""
        assert "ingest_log.html" in pages_src, (
            "ingest_log.html not referenced in pages.py route"
        )
        assert "FileResponse" in pages_src, (
            "FileResponse not used in pages.py"
        )

    def test_check28_follows_same_pattern(self, pages_src):
        """Check 28 — route follows same pattern (def page_ingest_log)."""
        assert "def page_ingest_log" in pages_src, (
            "def page_ingest_log() function not found in pages.py"
        )


# ===========================================================================
# NAV LINK CHECKS
# ===========================================================================

class TestNavLinks:

    @pytest.mark.parametrize("screen", NAV_SCREENS, ids=NAV_SCREENS)
    def test_nav_link_present(self, screen):
        """Checks 29-41 — /ingest-log nav link present in each screen."""
        html_path = PROJECT / "web" / screen
        assert html_path.exists(), f"Screen file not found: {html_path}"
        content = _read(html_path)
        assert 'href="/ingest-log"' in content or "href='/ingest-log'" in content, (
            f"/ingest-log nav link missing from {screen}"
        )
        assert "Ingest Log" in content, (
            f"'Ingest Log' link text missing from {screen}"
        )


# ===========================================================================
# API ROUTE INTACT CHECK
# ===========================================================================

class TestApiRoute:

    def test_check42_ingest_log_route_in_monitor(self, monitor_src):
        """Check 42 — /api/ingest-log route intact in monitor.py."""
        assert '"/api/ingest-log"' in monitor_src or "'/api/ingest-log'" in monitor_src, (
            "@router.get('/api/ingest-log') not found in monitor.py — API endpoint lost"
        )
        assert "def get_ingest_log(" in monitor_src, (
            "get_ingest_log function not found in monitor.py"
        )


# ===========================================================================
# DEV_HANDOFF CHECKS
# ===========================================================================

class TestDevHandoff:

    # test_check43_references_agent_work_8 — RETIRED (TASK_111 test-debt
    # cleanup, 2026-07-04). DEV_HANDOFF.md is a rolling file, overwritten
    # fresh by every task's developer pass (per
    # docs/agent_handoff_workflow.md), so an assertion pinned to one
    # historical task's content (AGENT_WORK_8) is permanently stale by
    # design — same pattern retired for AGENT_WORK_1 in TASK_110. Cat A
    # per docs/audit/test_debt_review.md.

    def test_check44_status_all_done(self, handoff_src):
        """Check 44 — DEV_HANDOFF.md Status is ALL_DONE."""
        lines = [ln.strip() for ln in handoff_src.splitlines() if ln.strip()]
        assert lines, "DEV_HANDOFF.md is empty"
        assert lines[-1] == "ALL_DONE", (
            f"DEV_HANDOFF.md last non-blank line is '{lines[-1]}', expected 'ALL_DONE'"
        )
