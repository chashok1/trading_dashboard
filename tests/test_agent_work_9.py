"""
Tests for AGENT_WORK_9 — market tape rollout completion (all 18 pages).

Acceptance criteria:
  1. All 18 HTML pages in web/ include market_bar.js.
  2. All 18 HTML pages in web/ include warning_badge.js (parity).
  3. The 3 newly added pages (param_sets.html, rules_health.html,
     test_results.html) each have both script tags placed before </body>.
  4. [RETIRED — TASK_110] cockpit.html has no <script> tag referencing
     macro_band.js (only a CSS comment is allowed). cockpit.html was deleted
     outright in TASK_109 (/cockpit is now a bare 301 redirect); see the
     retirement note below.
  5. web/market_bar.js passes node --check (syntax clean).
  6. GET /api/marketbar returns HTTP 200 (regression; skips if DB absent).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"

NEWLY_PATCHED = ["param_sets.html", "rules_health.html", "test_results.html"]
# REWRITTEN (TASK_112, 2026-07-04): the page set has grown past 18 web/*.html
# files (21 today) as new screens were added over time — an exact frozen
# count is the wrong invariant here; it breaks on every legitimate new page.
# MIN_HTML_COUNT is a floor (regression guard against pages disappearing),
# not a pin.
MIN_HTML_COUNT = 18


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_html_files() -> list[Path]:
    return sorted(WEB_DIR.glob("*.html"))


def _read(filename: str) -> str:
    return (WEB_DIR / filename).read_text(encoding="utf-8")


def _files_with_pattern(pattern: str) -> set[str]:
    result = set()
    for p in _all_html_files():
        if pattern in p.read_text(encoding="utf-8"):
            result.add(p.name)
    return result


# ---------------------------------------------------------------------------
# 1 & 2. Coverage — all 18 pages have both scripts
# ---------------------------------------------------------------------------

class TestScriptCoverage:
    """All 18 web/*.html files must include both market_bar.js and warning_badge.js."""

    def test_total_html_file_count_at_least_18(self):
        """Page count floor (not a pin) — regression guard against pages
        disappearing. See MIN_HTML_COUNT comment above for why this is a
        floor, not an exact count."""
        files = _all_html_files()
        assert len(files) >= MIN_HTML_COUNT, (
            f"Expected at least {MIN_HTML_COUNT} HTML files, found {len(files)}: "
            f"{[f.name for f in files]}"
        )

    def test_all_pages_have_market_bar_js(self):
        """REAL BUG, MINOR (not test debt — do not weaken): ingest_log.html
        has neither market_bar.js nor warning_badge.js (never retrofitted,
        unlike every other page). NOTE: 8 OTHER pages (dbstats/explore/
        groups/param_sets/ref/rule_performance/rules/trace) were previously
        truncated on disk mid-<script> tag — that larger bug has since been
        fixed externally (commit 7d7f692, "restore truncated closing tags
        on 8 page templates"), leaving only this one pre-existing gap."""
        files_with_mb = _files_with_pattern("market_bar.js")
        all_html = {p.name for p in _all_html_files()}
        missing = all_html - files_with_mb
        assert not missing, (
            f"{len(missing)} pages missing market_bar.js: {sorted(missing)}"
        )

    def test_all_pages_have_warning_badge_js(self):
        """REAL BUG, MINOR (not test debt — do not weaken): ingest_log.html
        is cleanly-formed but was simply never retrofitted with either
        script. The larger truncation bug (8 other pages cut off mid-
        <script> tag) has since been fixed externally (commit 7d7f692) —
        see test_all_pages_have_market_bar_js docstring."""
        files_with_wb = _files_with_pattern("warning_badge.js")
        all_html = {p.name for p in _all_html_files()}
        missing = all_html - files_with_wb
        assert not missing, (
            f"{len(missing)} pages missing warning_badge.js: {sorted(missing)}"
        )

    def test_market_bar_and_warning_badge_exact_parity(self):
        """Same set of files must have both scripts — no asymmetry.

        REAL BUG, MINOR (not test debt): currently red only because of the
        one pre-existing ingest_log.html gap (see
        test_all_pages_have_warning_badge_js docstring) — the larger
        8-file truncation bug is fixed (commit 7d7f692).
        """
        mb_files = _files_with_pattern("market_bar.js")
        wb_files = _files_with_pattern("warning_badge.js")
        assert mb_files == wb_files, (
            f"Parity mismatch.\n"
            f"  Has market_bar but not warning_badge: {sorted(mb_files - wb_files)}\n"
            f"  Has warning_badge but not market_bar: {sorted(wb_files - mb_files)}"
        )


# ---------------------------------------------------------------------------
# 3. Newly patched pages — correct placement of both tags before </body>
# ---------------------------------------------------------------------------

class TestNewlyPatchedPages:
    """param_sets.html, rules_health.html, test_results.html must each have
    both script tags placed before </body>.

    NOTE: param_sets.html was previously truncated on disk mid-<script>
    tag (part of the 8-file truncation bug found during TASK_113); that has
    since been fixed externally (commit 7d7f692, "restore truncated
    closing tags on 8 page templates"), so all cases here now pass.
    """

    @pytest.mark.parametrize("filename", NEWLY_PATCHED)
    def test_market_bar_present(self, filename: str):
        content = _read(filename)
        assert "market_bar.js" in content, (
            f"{filename}: market_bar.js script tag is missing"
        )

    @pytest.mark.parametrize("filename", NEWLY_PATCHED)
    def test_warning_badge_present(self, filename: str):
        content = _read(filename)
        assert "warning_badge.js" in content, (
            f"{filename}: warning_badge.js script tag is missing"
        )

    @pytest.mark.parametrize("filename", NEWLY_PATCHED)
    def test_market_bar_before_closing_body(self, filename: str):
        content = _read(filename)
        mb_pos = content.find("market_bar.js")
        body_pos = content.find("</body>")
        assert mb_pos != -1, f"{filename}: market_bar.js not found"
        assert body_pos != -1, f"{filename}: </body> not found"
        assert mb_pos < body_pos, (
            f"{filename}: market_bar.js appears AFTER </body> "
            f"(positions: {mb_pos} vs {body_pos})"
        )

    @pytest.mark.parametrize("filename", NEWLY_PATCHED)
    def test_warning_badge_before_closing_body(self, filename: str):
        content = _read(filename)
        wb_pos = content.find("warning_badge.js")
        body_pos = content.find("</body>")
        assert wb_pos != -1, f"{filename}: warning_badge.js not found"
        assert body_pos != -1, f"{filename}: </body> not found"
        assert wb_pos < body_pos, (
            f"{filename}: warning_badge.js appears AFTER </body> "
            f"(positions: {wb_pos} vs {body_pos})"
        )

    @pytest.mark.parametrize("filename", NEWLY_PATCHED)
    def test_market_bar_before_warning_badge(self, filename: str):
        """market_bar.js tag must appear before warning_badge.js tag."""
        content = _read(filename)
        mb_pos = content.find("market_bar.js")
        wb_pos = content.find("warning_badge.js")
        assert mb_pos < wb_pos, (
            f"{filename}: market_bar.js ({mb_pos}) appears AFTER "
            f"warning_badge.js ({wb_pos})"
        )


# ---------------------------------------------------------------------------
# 4. cockpit.html — RETIRED (TASK_110 test cleanup)
# ---------------------------------------------------------------------------
# TASK_109 deleted web/cockpit.html outright — /cockpit is now a bare 301
# redirect to /actionable (api/routers/pages.py::page_cockpit). There is no
# cockpit.html left to read, so every assertion below that opened the file
# raised FileNotFoundError. Since the whole page is gone (not just its
# macro_band.js script tag), there's nothing left to check here, and no clean
# /actionable equivalent — /actionable's own macro-band wiring is already
# covered by test_agent_work_39.py::TestTask7_CockpitRetirement. Retired
# rather than rewritten.


# ---------------------------------------------------------------------------
# 5. JS syntax check
# ---------------------------------------------------------------------------

class TestMarketBarJSSyntax:
    """web/market_bar.js must pass node --check."""

    def test_market_bar_js_exists(self):
        js_path = WEB_DIR / "market_bar.js"
        assert js_path.exists(), f"market_bar.js not found at {js_path}"

    def test_node_check_passes(self):
        js_path = WEB_DIR / "market_bar.js"
        result = subprocess.run(
            ["node", "--check", str(js_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# 6. API regression — /api/marketbar returns 200
# ---------------------------------------------------------------------------

class TestMarketbarAPIRegression:
    """GET /api/marketbar must return HTTP 200 (skips if Postgres unavailable)."""

    def test_marketbar_endpoint_200(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available — skipping API regression")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200, (
            f"Expected HTTP 200, got {response.status_code}: {response.text[:300]}"
        )

        data = response.json()
        assert "items" in data, f"Response missing 'items': {data}"
        assert "as_of" in data, f"Response missing 'as_of': {data}"
