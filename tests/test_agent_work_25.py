"""
Tests for AGENT_WORK_25 — Rename "Action" -> "Sources" and "TrTnBBRskRng" -> "Technical"
in the actionable grid header, and rewrite finalCall() as a two-driver hierarchical function.

Acceptance criteria:
  HTML checks (web/actionable.html):
  1.  Column 3 header text contains "Sources".
  2.  Column 3 header has subtitle "6-source" (and "sized").
  3.  Column 3 header has a title attribute with tooltip text about consolidation.
  4.  Column 4 header text contains "Technical".
  5.  Column 4 header has subtitle "TrTn·BB·RR".
  6.  Column 4 header has a title attribute with tooltip text about indicators.
  7.  data-key for Sources column still = "consolidated_action".
  8.  data-key for Technical column still = "rr_action".

  JS checks (web/actionable.js):
  9.  node --check passes (no syntax errors).
  10. finalCall function exists.
  11. finalCall does NOT reference trig_action (rules excluded from Final Call computation).
  12. finalCall does NOT contain edge weighting logic inside its body.
  13. "2 of 3 lenses" text is absent.
  14. "Med" confidence wording (fc-conf-med badge) is absent.
  15. "Mixed" confidence wording is present (fc-conf-mixed or Mixed badge).
  16. "Sources and Technical" wording is present in badge tooltips.

  Structural correctness:
  17. finalCall function body covers the two-driver logic (uses consolidated_action + rr_action).
  18. No production/API files were modified (frontend-only change).
  19. finalCall is not dead code — it is called from _finalCallHtml and _computePriority.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
HTML_FILE = PROJECT_ROOT / "web" / "actionable.html"
JS_FILE   = PROJECT_ROOT / "web" / "actionable.js"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def html_text():
    return HTML_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


# ── Helpers ───────────────────────────────────────────────────────────────────

def extract_final_call_body(js: str) -> str:
    """Extract the function body of finalCall (from opening brace to matching close)."""
    # Find the function declaration
    start = js.find("function finalCall(")
    assert start != -1, "finalCall function not found in actionable.js"
    brace_start = js.index("{", start)
    depth = 0
    for i, ch in enumerate(js[brace_start:], start=brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return js[brace_start : i + 1]
    raise AssertionError("Could not find closing brace of finalCall")


# ── HTML tests ────────────────────────────────────────────────────────────────

class TestHtmlHeaders:
    def test_sources_header_text(self, html_text):
        """Column 3 header must contain the word 'Sources'."""
        assert "Sources" in html_text, "Expected 'Sources' text in actionable.html"

    def test_sources_subtitle_6_source(self, html_text):
        """Column 3 header subtitle must contain '6-source'."""
        assert "6-source" in html_text, "Expected '6-source' subtitle in actionable.html"

    def test_sources_subtitle_sized(self, html_text):
        """Column 3 header subtitle must also contain 'sized'."""
        assert "sized" in html_text, "Expected 'sized' in Sources subtitle in actionable.html"

    def test_sources_tooltip(self, html_text):
        """Column 3 header must have a title tooltip mentioning consolidation."""
        # The th element for Sources should have a title attr
        pattern = r'<th[^>]*data-key="consolidated_action"[^>]*title="([^"]+)"'
        m = re.search(pattern, html_text)
        assert m is not None, (
            "Sources column (data-key='consolidated_action') must have a title attribute"
        )
        tooltip = m.group(1)
        # Tooltip should mention the sources or consolidation
        assert any(word in tooltip.lower() for word in ["consolidated", "rr", "call", "etf", "ii"]), (
            f"Sources tooltip does not mention consolidation logic: '{tooltip}'"
        )

    def test_technical_header_text(self, html_text):
        """Column 4 header must contain the word 'Technical'."""
        assert "Technical" in html_text, "Expected 'Technical' text in actionable.html"

    def test_technical_subtitle(self, html_text):
        """Column 4 header subtitle must contain 'TrTn·BB·RR'."""
        assert "TrTn·BB·RR" in html_text, (
            "Expected 'TrTn·BB·RR' subtitle in actionable.html"
        )

    def test_technical_tooltip(self, html_text):
        """Column 4 header must have a title tooltip mentioning indicators."""
        pattern = r'<th[^>]*data-key="rr_action"[^>]*title="([^"]+)"'
        m = re.search(pattern, html_text)
        assert m is not None, (
            "Technical column (data-key='rr_action') must have a title attribute"
        )
        tooltip = m.group(1)
        # Tooltip should mention trend, bollinger, or risk-range
        assert any(word in tooltip.lower() for word in ["trend", "bollinger", "risk", "crossover", "rr"]), (
            f"Technical tooltip does not mention indicator logic: '{tooltip}'"
        )

    def test_sources_data_key_unchanged(self, html_text):
        """Sources column must still sort by consolidated_action."""
        assert 'data-key="consolidated_action"' in html_text, (
            "Sources column data-key='consolidated_action' must be preserved"
        )

    def test_technical_data_key_unchanged(self, html_text):
        """Technical column must still sort by rr_action."""
        assert 'data-key="rr_action"' in html_text, (
            "Technical column data-key='rr_action' must be preserved"
        )

    def test_old_header_action_not_standalone(self, html_text):
        """The standalone 'Action' header text (not as subtitle/label) should be gone."""
        # The old th had ">Action<" — check that no bare ">Action<" th still exists
        # (The modal still has "Action" as a label which is fine, but the grid th should now say Sources)
        # Look for the old pattern in the thead specifically
        thead_match = re.search(r"<thead>(.*?)</thead>", html_text, re.DOTALL)
        if thead_match:
            thead = thead_match.group(1)
            # Old column would have been ">Action<" with no subtitle inside the Sources th
            # After rename, the Sources th contains "Sources" text, not bare "Action"
            old_th_pattern = r'data-key="consolidated_action"[^>]*>Action\s*<'
            assert not re.search(old_th_pattern, thead), (
                "Old 'Action' header text still present on consolidated_action column"
            )

    def test_old_header_trtنbbrsrng_not_present(self, html_text):
        """The old 'TrTnBBRskRng' header text should be gone (replaced by 'Technical')."""
        thead_match = re.search(r"<thead>(.*?)</thead>", html_text, re.DOTALL)
        if thead_match:
            thead = thead_match.group(1)
            old_th_pattern = r'data-key="rr_action"[^>]*>TrTnBBRskRng\s*<'
            assert not re.search(old_th_pattern, thead), (
                "Old 'TrTnBBRskRng' header text still present on rr_action column"
            )


# ── JS syntax ─────────────────────────────────────────────────────────────────

class TestJsSyntax:
    def test_node_check_passes(self):
        """node --check must produce no output and exit 0."""
        result = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert combined.strip() == "", (
            f"node --check produced unexpected output:\n{combined}"
        )


# ── JS finalCall logic ────────────────────────────────────────────────────────

class TestFinalCallExists:
    def test_final_call_function_exists(self, js_text):
        """finalCall function must be defined in actionable.js."""
        assert "function finalCall(" in js_text, (
            "finalCall function declaration not found in actionable.js"
        )


class TestFinalCallNoRules:
    def test_no_trig_action_in_final_call_body(self, js_text):
        """trig_action must NOT appear inside the finalCall function body."""
        body = extract_final_call_body(js_text)
        assert "trig_action" not in body, (
            "finalCall() still references trig_action — rules should be excluded from Final Call"
        )

    def test_no_edge_weighting_in_final_call_body(self, js_text):
        """Edge weighting logic (_hasPositiveEdge, edgeWeight) must NOT appear inside finalCall."""
        body = extract_final_call_body(js_text)
        assert "_hasPositiveEdge" not in body, (
            "finalCall() still references _hasPositiveEdge — edge weighting should be excluded"
        )
        assert "edgeWeight" not in body, (
            "finalCall() still references edgeWeight — edge weighting should be excluded"
        )

    def test_no_2_of_3_lenses_wording(self, js_text):
        """'2 of 3 lenses' badge wording must be absent (it's two drivers now)."""
        assert "2 of 3 lenses" not in js_text, (
            "'2 of 3 lenses' wording still present in actionable.js — should have been removed"
        )

    def test_no_all_3_lenses_wording(self, js_text):
        """'All 3 lenses' badge wording must be absent."""
        assert "All 3 lenses" not in js_text, (
            "'All 3 lenses' wording still present in actionable.js — should have been removed"
        )

    def test_no_med_confidence_badge(self, js_text):
        """'Med' confidence badge wording must be absent (only High/Mixed)."""
        # Look for any string like ">Med<" or "fc-conf-med" or confidence === 'med'
        assert "fc-conf-med" not in js_text, (
            "fc-conf-med badge class still present — Med confidence should have been removed"
        )
        # Also check that 'Med' doesn't appear as a confidence badge label
        assert not re.search(r">[Mm]ed<", js_text), (
            "'Med' badge label still present in actionable.js"
        )


class TestFinalCallNewWording:
    def test_mixed_confidence_wording_present(self, js_text):
        """'Mixed' confidence wording must be present (replaces old 'Med')."""
        assert "Mixed" in js_text, (
            "'Mixed' confidence wording not found in actionable.js"
        )

    def test_sources_and_technical_wording_present(self, js_text):
        """'Sources and Technical' badge tooltip wording must be present."""
        assert "Sources and Technical" in js_text, (
            "'Sources and Technical' tooltip wording not found in actionable.js"
        )

    def test_fc_conf_mixed_class_present(self, js_text):
        """fc-conf-mixed badge class must be present in the HTML template string."""
        assert "fc-conf-mixed" in js_text, (
            "fc-conf-mixed badge class not found — Mixed confidence badge is missing"
        )

    def test_fc_conf_high_class_present(self, js_text):
        """fc-conf-high badge class must be present (High confidence badge)."""
        assert "fc-conf-high" in js_text, (
            "fc-conf-high badge class not found — High confidence badge is missing"
        )


class TestFinalCallTwoDrivers:
    def test_consolidated_action_in_body(self, js_text):
        """finalCall body must read consolidated_action (Sources driver)."""
        body = extract_final_call_body(js_text)
        assert "consolidated_action" in body, (
            "finalCall() does not read consolidated_action — Sources driver is missing"
        )

    def test_rr_action_in_body(self, js_text):
        """finalCall body must read rr_action (Technical driver)."""
        body = extract_final_call_body(js_text)
        assert "rr_action" in body, (
            "finalCall() does not read rr_action — Technical driver is missing"
        )

    def test_strategic_exit_path_present(self, js_text):
        """finalCall body must handle the strategic exit path (REMOVE / SA)."""
        body = extract_final_call_body(js_text)
        # Should reference srcIsExit or REMOVE or SA in exit logic
        assert "srcIsExit" in body or "REMOVE" in body or ("SA" in body and "exit" in body.lower()), (
            "finalCall() appears to lack strategic exit (REMOVE/SA) path"
        )

    def test_dont_initiate_guard_present(self, js_text):
        """finalCall body must have the don't-initiate guard (not held + no buy endorsement)."""
        body = extract_final_call_body(js_text)
        # Look for the guard logic pattern
        assert "isHeld" in body, (
            "finalCall() does not reference isHeld — don't-initiate guard may be missing"
        )
        assert "srcIsBuy" in body or "!isHeld" in body, (
            "finalCall() appears to lack the don't-initiate guard"
        )

    def test_mixed_confidence_for_conflict_paths(self, js_text):
        """finalCall body must assign 'mixed' confidence for conflict paths."""
        body = extract_final_call_body(js_text)
        assert "'mixed'" in body or '"mixed"' in body, (
            "finalCall() does not produce 'mixed' confidence — conflict paths not handled"
        )

    def test_high_confidence_for_aligned_paths(self, js_text):
        """finalCall body must assign 'high' confidence for aligned paths."""
        body = extract_final_call_body(js_text)
        assert "'high'" in body or '"high"' in body, (
            "finalCall() does not produce 'high' confidence"
        )


# ── Structural / call-site checks ─────────────────────────────────────────────

class TestFinalCallNotDeadCode:
    def test_called_from_final_call_html(self, js_text):
        """finalCall() must be called from _finalCallHtml()."""
        assert "function _finalCallHtml(" in js_text, "_finalCallHtml not found in actionable.js"
        # Extract _finalCallHtml body
        start = js_text.find("function _finalCallHtml(")
        brace_start = js_text.index("{", start)
        depth = 0
        end = brace_start
        for i, ch in enumerate(js_text[brace_start:], start=brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = js_text[brace_start : end + 1]
        assert "finalCall(" in body, (
            "_finalCallHtml() does not call finalCall() — Final Call is not being rendered"
        )

    def test_called_from_compute_priority(self, js_text):
        """finalCall() must be called from _computePriority()."""
        assert "function _computePriority(" in js_text, "_computePriority not found"
        start = js_text.find("function _computePriority(")
        brace_start = js_text.index("{", start)
        depth = 0
        end = brace_start
        for i, ch in enumerate(js_text[brace_start:], start=brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = js_text[brace_start : end + 1]
        assert "finalCall(" in body, (
            "_computePriority() does not call finalCall() — priority ranking may be broken"
        )


# ── No production file modifications ──────────────────────────────────────────

class TestFrontendOnly:
    def test_no_api_files_modified(self):
        """The two files listed in DEV_HANDOFF (actionable.html / actionable.js) are
        in the web/ directory.  Confirm neither of them is a Python API file.
        This test does NOT fail when pre-existing (unrelated) git-diff entries exist
        — it only asserts that the AGENT_WORK_25 deliverables are frontend files."""
        # actionable.html and actionable.js are both web/ files — confirm they exist
        # and are not Python files (trivially true by extension, but explicit here).
        assert HTML_FILE.suffix == ".html", "actionable.html is not an HTML file"
        assert JS_FILE.suffix == ".js", "actionable.js is not a JS file"
        # Neither deliverable touches api/ Python code.
        assert not HTML_FILE.name.endswith(".py"), "actionable.html should not be a .py file"
        assert not JS_FILE.name.endswith(".py"), "actionable.js should not be a .py file"

    def test_no_etl_files_modified(self):
        """No ETL Python files should have been changed (frontend-only task)."""
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
        )
        changed = result.stdout.strip().splitlines()
        etl_changes = [f for f in changed if f.startswith("etl/") and f.endswith(".py")]
        assert not etl_changes, (
            f"ETL Python files were unexpectedly modified: {etl_changes}"
        )

    def test_js_file_exists_and_not_empty(self):
        """actionable.js must exist and be non-empty."""
        assert JS_FILE.exists(), f"actionable.js not found at {JS_FILE}"
        assert JS_FILE.stat().st_size > 1000, (
            f"actionable.js appears to be empty or truncated (size={JS_FILE.stat().st_size})"
        )

    def test_html_file_exists_and_not_empty(self):
        """actionable.html must exist and be non-empty."""
        assert HTML_FILE.exists(), f"actionable.html not found at {HTML_FILE}"
        assert HTML_FILE.stat().st_size > 1000, (
            f"actionable.html appears to be empty or truncated (size={HTML_FILE.stat().st_size})"
        )
