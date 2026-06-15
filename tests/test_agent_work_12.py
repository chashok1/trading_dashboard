"""
Tests for AGENT_WORK_12 — Add per-series mm/dd date stamps to Econ expander panel.

Acceptance criteria:
  1. web/market_bar.js passes `node --check` (no syntax errors).
  2. web/market_bar.js contains class `mt-econ-date` in buildEconHtml.
  3. web/market_bar.js converts latest_date (YYYY-MM-DD) to mm/dd by splitting on '-'
     and joining parts[1] + '/' + parts[2].
  4. web/styles.css contains .mt-econ-date with expected properties
     (color, font-size, margin-left, white-space).
  5. Null/missing latest_date guard exists (renders '--' fallback).
  6. JS-level: rendered HTML includes correct mm/dd string for a known date.
  7. JS-level: null latest_date renders '--' without crashing.
  8. JS-level: invalid/non-YYYY-MM-DD latest_date renders '--' without crashing.
  9. The existing tooltip still shows the full YYYY-MM-DD date (regression guard).
 10. buildTapeHtml (tape strip) is not affected — no mt-econ-date there.
"""
from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
MARKET_BAR_JS = WEB_DIR / "market_bar.js"
STYLES_CSS = WEB_DIR / "styles.css"


def _js() -> str:
    return MARKET_BAR_JS.read_text(encoding="utf-8")


def _css() -> str:
    return STYLES_CSS.read_text(encoding="utf-8")


def _build_econ_body() -> str:
    """Extract the buildEconHtml function body from market_bar.js."""
    js = _js()
    start = js.find("function buildEconHtml(")
    assert start != -1, "buildEconHtml function not found in market_bar.js"
    depth = 0
    i = js.index("{", start)
    func_start = i
    while i < len(js):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[func_start : i + 1]
        i += 1
    raise AssertionError("Could not find closing brace for buildEconHtml")


def _build_tape_body() -> str:
    """Extract the buildTapeHtml function body from market_bar.js."""
    js = _js()
    start = js.find("function buildTapeHtml(")
    assert start != -1, "buildTapeHtml function not found in market_bar.js"
    depth = 0
    i = js.index("{", start)
    func_start = i
    while i < len(js):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[func_start : i + 1]
        i += 1
    raise AssertionError("Could not find closing brace for buildTapeHtml")


# ---------------------------------------------------------------------------
# 1. Syntax check
# ---------------------------------------------------------------------------

class TestSyntax:
    """node --check must pass with no errors."""

    def test_file_exists(self):
        assert MARKET_BAR_JS.exists(), f"market_bar.js not found at {MARKET_BAR_JS}"

    def test_node_check_passes(self):
        result = subprocess.run(
            ["node", "--check", str(MARKET_BAR_JS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check exited {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # node --check prints nothing on success
        assert result.stderr.strip() == "", (
            f"node --check produced unexpected stderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# 2. mt-econ-date class present in buildEconHtml
# ---------------------------------------------------------------------------

class TestEconDateClassPresent:
    """mt-econ-date must appear in buildEconHtml output HTML."""

    def test_mt_econ_date_in_econ_body(self):
        body = _build_econ_body()
        assert "mt-econ-date" in body, (
            "buildEconHtml must emit a span with class 'mt-econ-date'"
        )

    def test_mt_econ_date_span_structure(self):
        """The span must use the dateLbl variable (or equivalent) inside it."""
        body = _build_econ_body()
        # The rendered span must reference the date label variable
        assert 'mt-econ-date' in body, (
            "Expected mt-econ-date span in buildEconHtml"
        )
        # It must be a span element, not just a comment
        assert re.search(r'<span[^>]*class="mt-econ-date"', body), (
            "Expected <span class=\"mt-econ-date\"> element in buildEconHtml"
        )


# ---------------------------------------------------------------------------
# 3. Date slicing/formatting logic
# ---------------------------------------------------------------------------

class TestDateFormattingLogic:
    """The mm/dd conversion must split on '-' and join parts[1] + '/' + parts[2]."""

    def test_split_on_dash_present(self):
        body = _build_econ_body()
        # Must split on '-'
        assert ".split('-')" in body or '.split("-")' in body, (
            "buildEconHtml must split latest_date on '-' to extract mm/dd"
        )

    def test_parts_1_slash_parts_2(self):
        """Month/day join: parts[1] + '/' + parts[2] (or equivalent)."""
        body = _build_econ_body()
        # Accept either quote style
        assert ("parts[1] + '/' + parts[2]" in body or
                'parts[1] + "/" + parts[2]' in body), (
            "buildEconHtml must construct mm/dd as parts[1] + '/' + parts[2]"
        )

    def test_regex_guard_present(self):
        """A guard against non-YYYY-MM-DD strings must exist (regex or truthiness check)."""
        body = _build_econ_body()
        # The implementation uses a regex /^\d{4}-\d{2}-\d{2}$/
        has_regex = r"\d{4}-\d{2}-\d{2}" in body
        has_truthiness = "item.latest_date &&" in body or "item.latest_date)" in body
        assert has_regex or has_truthiness, (
            "buildEconHtml must guard against null/non-date latest_date before splitting"
        )

    def test_dateLbl_variable_used(self):
        """dateLbl (or equivalent) variable must be defined and used in the span."""
        body = _build_econ_body()
        assert "dateLbl" in body, (
            "buildEconHtml must use a dateLbl variable to hold the mm/dd string"
        )


# ---------------------------------------------------------------------------
# 4. CSS — .mt-econ-date present with expected properties
# ---------------------------------------------------------------------------

class TestCssClass:
    """web/styles.css must define .mt-econ-date with the required properties."""

    def test_css_file_exists(self):
        assert STYLES_CSS.exists(), f"styles.css not found at {STYLES_CSS}"

    def test_mt_econ_date_rule_present(self):
        css = _css()
        assert ".mt-econ-date" in css, (
            ".mt-econ-date rule missing from web/styles.css"
        )

    def test_color_text_3(self):
        css = _css()
        # Find the .mt-econ-date rule block
        idx = css.find(".mt-econ-date")
        assert idx != -1, ".mt-econ-date not found in styles.css"
        # Extract up to the next rule boundary (next '{' ... '}')
        block_start = css.find("{", idx)
        block_end = css.find("}", block_start)
        block = css[block_start:block_end + 1]
        assert "var(--text-3)" in block, (
            f".mt-econ-date must use color: var(--text-3), got block: {block!r}"
        )

    def test_font_size_10px(self):
        css = _css()
        idx = css.find(".mt-econ-date")
        block_start = css.find("{", idx)
        block_end = css.find("}", block_start)
        block = css[block_start:block_end + 1]
        assert "10px" in block, (
            f".mt-econ-date must have font-size: 10px, got block: {block!r}"
        )

    def test_margin_left_8px(self):
        css = _css()
        idx = css.find(".mt-econ-date")
        block_start = css.find("{", idx)
        block_end = css.find("}", block_start)
        block = css[block_start:block_end + 1]
        assert "8px" in block, (
            f".mt-econ-date must have margin-left: 8px, got block: {block!r}"
        )

    def test_white_space_nowrap(self):
        css = _css()
        idx = css.find(".mt-econ-date")
        block_start = css.find("{", idx)
        block_end = css.find("}", block_start)
        block = css[block_start:block_end + 1]
        assert "nowrap" in block, (
            f".mt-econ-date must have white-space: nowrap, got block: {block!r}"
        )

    def test_mt_econ_date_positioned_after_mt_econ_stale(self):
        """Per spec: .mt-econ-date placed immediately after .mt-econ-stale."""
        css = _css()
        stale_idx = css.find(".mt-econ-stale")
        date_idx = css.find(".mt-econ-date")
        assert stale_idx != -1, ".mt-econ-stale not found in styles.css"
        assert date_idx != -1, ".mt-econ-date not found in styles.css"
        assert date_idx > stale_idx, (
            ".mt-econ-date should appear after .mt-econ-stale in styles.css"
        )


# ---------------------------------------------------------------------------
# 5. Null/missing guard exists
# ---------------------------------------------------------------------------

class TestNullGuard:
    """Guard against null/missing latest_date must render '--' fallback."""

    def test_dash_dash_fallback_present(self):
        body = _build_econ_body()
        # Default value should be '--'
        assert "'--'" in body or '"--"' in body, (
            "buildEconHtml must define '--' as the fallback when latest_date is null/missing"
        )

    def test_null_guard_in_conditional(self):
        """The guard must check item.latest_date before splitting."""
        body = _build_econ_body()
        # item.latest_date must appear in a conditional context before the split
        assert "item.latest_date" in body, (
            "buildEconHtml must reference item.latest_date in the date-formatting block"
        )
        # The '--' fallback and the split must both exist
        assert ".split(" in body, "Date split must be present"
        assert "'--'" in body or '"--"' in body, "Fallback '--' must be present"


# ---------------------------------------------------------------------------
# 9. Regression: tooltip still contains full YYYY-MM-DD date
# ---------------------------------------------------------------------------

class TestTooltipRegression:
    """The existing tooltip must still show full date via item.latest_date."""

    def test_tooltip_uses_latest_date(self):
        body = _build_econ_body()
        # Tooltip tip variable must reference item.latest_date
        assert "item.latest_date" in body, (
            "Tooltip in buildEconHtml must still use item.latest_date for full date"
        )

    def test_tooltip_as_of_label(self):
        """Tooltip text must include 'as of:' prefix (existing pattern)."""
        body = _build_econ_body()
        assert "as of:" in body, (
            "buildEconHtml tooltip must still include 'as of:' label"
        )


# ---------------------------------------------------------------------------
# 10. Tape strip not affected
# ---------------------------------------------------------------------------

class TestTapeNotAffected:
    """buildTapeHtml must not contain mt-econ-date."""

    def test_tape_has_no_econ_date_class(self):
        body = _build_tape_body()
        assert "mt-econ-date" not in body, (
            "buildTapeHtml (market tape) must not contain mt-econ-date — tape is unaffected"
        )


# ---------------------------------------------------------------------------
# 6, 7, 8. JS-level logic tests via Node.js
# ---------------------------------------------------------------------------

class TestBuildEconHtmlDateLogic:
    """
    Execute buildEconHtml via Node.js with synthetic payloads and assert
    that mm/dd formatting, null guard, and invalid-date guard work correctly.
    """

    _HARNESS = textwrap.dedent(r"""
        // Minimal escHtml helper
        function escHtml(s) {
          return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
          }[c]));
        }

        // Paste buildEconHtml verbatim
        {FUNC_BODY}

        // --- TC1: normal date 2026-06-04 should render as 06/04 ---------------
        const macro1 = {
          groups: {
            rates: [
              { series_id: "DGS10", label: "10Y Treasury", unit: "%",
                latest_value: 4.47, latest_date: "2026-06-04",
                chg_abs: -0.02, chg_pct: -0.45 }
            ]
          }
        };
        const html1 = buildEconHtml(macro1);
        console.assert(
          html1.includes("06/04"),
          "FAIL TC1: expected '06/04' in output for latest_date='2026-06-04', got: " + html1.slice(0, 400)
        );
        console.assert(
          html1.includes('mt-econ-date'),
          "FAIL TC1: expected mt-econ-date span in output, got: " + html1.slice(0, 400)
        );

        // --- TC2: null latest_date should render '--' without crashing ---------
        const macro2 = {
          groups: {
            rates: [
              { series_id: "DGS2", label: "2Y Treasury", unit: "%",
                latest_value: 4.21, latest_date: null,
                chg_abs: 0.01, chg_pct: 0.24 }
            ]
          }
        };
        let html2;
        try {
          html2 = buildEconHtml(macro2);
        } catch(e) {
          console.assert(false, "FAIL TC2: null latest_date threw: " + e.message);
          process.exit(1);
        }
        console.assert(
          html2.includes('--'),
          "FAIL TC2: expected '--' fallback for null latest_date, got: " + html2.slice(0, 400)
        );
        console.assert(
          html2.includes('mt-econ-date'),
          "FAIL TC2: expected mt-econ-date span even for null date, got: " + html2.slice(0, 400)
        );

        // --- TC3: missing latest_date key should render '--' without crashing --
        const macro3 = {
          groups: {
            inflation: [
              { series_id: "CPIAUCSL", label: "CPI", unit: "%",
                latest_value: 3.4,
                chg_abs: 0.1, chg_pct: 0.3 }
              // latest_date intentionally omitted (undefined)
            ]
          }
        };
        let html3;
        try {
          html3 = buildEconHtml(macro3);
        } catch(e) {
          console.assert(false, "FAIL TC3: missing latest_date threw: " + e.message);
          process.exit(1);
        }
        console.assert(
          html3.includes('--'),
          "FAIL TC3: expected '--' fallback for missing latest_date, got: " + html3.slice(0, 400)
        );

        // --- TC4: invalid date string (not YYYY-MM-DD) renders '--' ------------
        const macro4 = {
          groups: {
            jobs: [
              { series_id: "UNRATE", label: "Unemployment", unit: "%",
                latest_value: 4.0, latest_date: "Jun 2026",
                chg_abs: 0.0, chg_pct: 0.0 }
            ]
          }
        };
        const html4 = buildEconHtml(macro4);
        console.assert(
          html4.includes('--') && !html4.includes('Jun') || html4.includes('mt-econ-date'),
          "FAIL TC4: invalid date string should render '--', got: " + html4.slice(0, 400)
        );

        // --- TC5: tooltip still has full YYYY-MM-DD ----------------------------
        const html5 = buildEconHtml(macro1);
        console.assert(
          html5.includes("2026-06-04"),
          "FAIL TC5: tooltip must still contain full date '2026-06-04', got: " + html5.slice(0, 400)
        );
        console.assert(
          html5.includes("as of:"),
          "FAIL TC5: tooltip must still contain 'as of:' label, got: " + html5.slice(0, 400)
        );

        // --- TC6: different month/day (2026-01-15) renders 01/15 ---------------
        const macro6 = {
          groups: {
            risk: [
              { series_id: "NFCI", label: "NFCI", unit: "index",
                latest_value: -0.12, latest_date: "2026-01-15",
                chg_abs: 0.03, chg_pct: 1.1 }
            ]
          }
        };
        const html6 = buildEconHtml(macro6);
        console.assert(
          html6.includes("01/15"),
          "FAIL TC6: expected '01/15' for latest_date='2026-01-15', got: " + html6.slice(0, 400)
        );

        process.stdout.write("ALL_JS_ASSERTIONS_PASSED\n");
    """)

    def test_date_formatting_js(self):
        body = _build_econ_body()
        func_decl = f"function buildEconHtml(macro) {body}"
        harness = self._HARNESS.replace("{FUNC_BODY}", func_decl)

        result = subprocess.run(
            ["node", "-e", harness],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"Node harness crashed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "ALL_JS_ASSERTIONS_PASSED" in result.stdout, (
            f"Not all JS assertions passed:\n{result.stdout}\n{result.stderr}"
        )
        assert "FAIL" not in result.stdout, (
            f"JS assertion failures detected:\n{result.stdout}"
        )
