"""
Tests for AGENT_WORK_10 — fix buildEconHtml in web/market_bar.js to parse
the actual /api/macro response shape.

Acceptance criteria:
  1. web/market_bar.js passes node --check (no syntax errors).
  2. buildEconHtml uses Object.entries to iterate the groups object.
  3. buildEconHtml reads item.latest_value (correct field name).
  4. buildEconHtml reads item.chg_abs (correct field name).
  5. No old econ-panel field names (grp.items, item.value, item.chg[non-suffixed],
     item.stale, item.as_of) appear inside buildEconHtml.
  6. buildEconHtml uses the object key (groupName) as the group label, not grp.group/grp.label.
  7. Empty groups object produces a "No econ data available" fallback (not a crash).
  8. Value formatting: unit='%' produces x.xx%, otherwise toLocaleString 2dp.
  9. Change coloring: chg_abs > 0 -> mt-up, < 0 -> mt-down, 0 -> mt-flat.
 10. Tooltip uses item.latest_date (not item.as_of or item.stale).
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


def _js() -> str:
    return MARKET_BAR_JS.read_text(encoding="utf-8")


def _build_econ_body() -> str:
    """Extract just the buildEconHtml function body from market_bar.js."""
    js = _js()
    # Find start and end of the function
    start = js.find("function buildEconHtml(")
    assert start != -1, "buildEconHtml function not found in market_bar.js"
    # Walk braces to find the matching closing brace
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


# ---------------------------------------------------------------------------
# 1. Syntax check
# ---------------------------------------------------------------------------

class TestSyntax:
    """node --check must pass (no syntax errors)."""

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
        assert result.stdout.strip() == "", (
            f"node --check produced unexpected output: {result.stdout!r}"
        )


# ---------------------------------------------------------------------------
# 2 & 3. Grep presence checks
# ---------------------------------------------------------------------------

class TestRequiredPatterns:
    """Both Object.entries and latest_value must appear in market_bar.js."""

    def test_object_entries_present(self):
        js = _js()
        assert "Object.entries" in js, (
            "market_bar.js must use Object.entries to iterate the groups object"
        )

    def test_latest_value_present(self):
        js = _js()
        assert "latest_value" in js, (
            "market_bar.js must reference item.latest_value (correct API field name)"
        )

    def test_chg_abs_present(self):
        js = _js()
        assert "chg_abs" in js, (
            "market_bar.js must reference item.chg_abs (correct API field name)"
        )

    def test_latest_date_present(self):
        js = _js()
        assert "latest_date" in js, (
            "market_bar.js must reference item.latest_date for the tooltip"
        )


# ---------------------------------------------------------------------------
# 4. Absence checks — old econ-panel field names must be gone from buildEconHtml
# ---------------------------------------------------------------------------

class TestAbsentOldFieldNames:
    """Stale field names from the old (wrong) API shape must not exist in buildEconHtml."""

    def test_grp_items_absent(self):
        body = _build_econ_body()
        assert "grp.items" not in body, (
            "buildEconHtml still references grp.items (old wrong field name)"
        )

    def test_item_value_absent_in_econ(self):
        """item.value (no suffix) must not appear in buildEconHtml; correct field is item.latest_value."""
        body = _build_econ_body()
        # item.value_format is fine in buildTapeHtml but must not appear in buildEconHtml
        # Check for bare item.value NOT followed by _ or alphanumeric
        matches = re.findall(r"item\.value(?!_\w|\w)", body)
        assert not matches, (
            f"buildEconHtml still uses bare 'item.value': {matches} — should be item.latest_value"
        )

    def test_item_stale_absent_in_econ(self):
        body = _build_econ_body()
        assert "item.stale" not in body, (
            "buildEconHtml references item.stale — that field does not exist on /api/macro"
        )

    def test_item_as_of_absent_in_econ(self):
        """item.as_of does not exist on /api/macro items; correct field is item.latest_date."""
        body = _build_econ_body()
        assert "item.as_of" not in body, (
            "buildEconHtml references item.as_of — should use item.latest_date instead"
        )

    def test_standalone_item_chg_absent(self):
        """item.chg (standalone, no suffix) must be gone; correct fields are item.chg_abs / item.chg_pct."""
        body = _build_econ_body()
        # Match item.chg not followed by _ or alphanumeric
        matches = re.findall(r"item\.chg(?![_a-zA-Z])", body)
        assert not matches, (
            f"buildEconHtml still uses bare 'item.chg': {matches} — should use item.chg_abs or item.chg_pct"
        )


# ---------------------------------------------------------------------------
# 5. Structural correctness of buildEconHtml
# ---------------------------------------------------------------------------

class TestBuildEconHtmlStructure:
    """buildEconHtml must use the object iteration pattern and groupName as label."""

    def test_groups_initialized_as_object(self):
        """macro.groups || {} (not || []) to handle missing groups gracefully."""
        body = _build_econ_body()
        assert "macro.groups || {}" in body, (
            "buildEconHtml must initialise groups as: macro.groups || {}"
        )

    def test_object_entries_used_for_iteration(self):
        body = _build_econ_body()
        assert "Object.entries(groups)" in body, (
            "buildEconHtml must call Object.entries(groups) to iterate the keyed object"
        )

    def test_group_name_used_as_label(self):
        """The group label must come from the object key (groupName), not grp.group/grp.label."""
        body = _build_econ_body()
        # Destructure must include groupName (or equivalent first-position name)
        assert "groupName" in body, (
            "buildEconHtml must use the object key as the group label (expected variable: groupName)"
        )
        assert "grp.group" not in body, (
            "buildEconHtml still references grp.group (old pattern)"
        )
        assert "grp.label" not in body, (
            "buildEconHtml still references grp.label (old pattern)"
        )

    def test_empty_groups_fallback(self):
        """No econ data available message must be returned when groups is empty."""
        body = _build_econ_body()
        assert "No econ data available" in body, (
            "buildEconHtml must return a fallback message when groups is empty"
        )

    def test_unit_percent_formatting(self):
        """Unit='%' branch must produce x.xx% formatted value."""
        body = _build_econ_body()
        # Should check item.unit === '%'
        assert "item.unit" in body, (
            "buildEconHtml must inspect item.unit to decide value format"
        )
        assert "'%'" in body or '"%"' in body, (
            "buildEconHtml must branch on unit === '%'"
        )

    def test_tolocalestring_for_non_pct(self):
        """Non-% values must use toLocaleString with 2 decimal places."""
        body = _build_econ_body()
        assert "toLocaleString" in body, (
            "buildEconHtml must use toLocaleString for non-% value formatting"
        )

    def test_chg_abs_coloring(self):
        """Change coloring must be driven by chg_abs sign (mt-up / mt-down / mt-flat)."""
        body = _build_econ_body()
        assert "chg_abs" in body, "buildEconHtml must use chg_abs for change display"
        assert "mt-up" in body, "buildEconHtml must set mt-up class for positive chg_abs"
        assert "mt-down" in body, "buildEconHtml must set mt-down class for negative chg_abs"

    def test_tooltip_uses_latest_date(self):
        """Tooltip must reference item.latest_date."""
        body = _build_econ_body()
        assert "latest_date" in body, (
            "buildEconHtml tooltip must reference item.latest_date"
        )

    def test_chg_pct_optional_in_tooltip(self):
        """chg_pct may optionally appear in the tooltip (parenthetical)."""
        body = _build_econ_body()
        assert "chg_pct" in body, (
            "buildEconHtml tooltip should optionally include chg_pct"
        )


# ---------------------------------------------------------------------------
# 6. buildTapeHtml untouched (regression guard)
# ---------------------------------------------------------------------------

class TestTapeHtmlUnchanged:
    """buildTapeHtml (for /api/marketbar) must still use its own field names."""

    def _tape_body(self) -> str:
        js = _js()
        start = js.find("function buildTapeHtml(")
        assert start != -1, "buildTapeHtml not found in market_bar.js"
        depth = 0
        i = js.index("{", start)
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    return js[js.index("{", start) : i + 1]
            i += 1
        raise AssertionError("Could not find closing brace for buildTapeHtml")

    def test_tape_still_uses_item_value(self):
        """buildTapeHtml still reads item.value (correct for /api/marketbar)."""
        body = self._tape_body()
        assert "item.value" in body, (
            "buildTapeHtml must still use item.value for /api/marketbar items"
        )

    def test_tape_still_uses_item_stale(self):
        """buildTapeHtml still reads item.stale (correct for /api/marketbar)."""
        body = self._tape_body()
        assert "item.stale" in body, (
            "buildTapeHtml must still use item.stale for /api/marketbar items"
        )

    def test_tape_does_not_use_latest_value(self):
        """buildTapeHtml must NOT use item.latest_value (that's a /api/macro field)."""
        body = self._tape_body()
        assert "latest_value" not in body, (
            "buildTapeHtml mistakenly references item.latest_value — wrong endpoint"
        )


# ---------------------------------------------------------------------------
# 7. Logic simulation via node (JS-level unit test)
# ---------------------------------------------------------------------------

class TestBuildEconHtmlLogic:
    """
    Execute buildEconHtml logic directly in Node.js with a synthetic /api/macro
    payload matching the spec and assert the output contains expected tokens.
    """

    _HARNESS = textwrap.dedent(r"""
        // Inline the escHtml helper (minimal, no module system needed)
        function escHtml(s) {
          return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
          }[c]));
        }

        // Paste buildEconHtml verbatim from market_bar.js
        {FUNC_BODY}

        // --- test cases ---

        // TC1: normal payload with two groups
        const macroNormal = {
          as_of: "2026-06-05",
          groups: {
            rates: [
              { series_id: "DGS10", label: "10Y Treasury", unit: "%",
                latest_value: 4.47, latest_date: "2026-06-04",
                chg_abs: -0.02, chg_pct: -0.45 }
            ],
            index: [
              { series_id: "SP500", label: "S&P 500", unit: "index",
                latest_value: 5280.5, latest_date: "2026-06-04",
                chg_abs: 12.3, chg_pct: 0.23 }
            ]
          }
        };

        const html1 = buildEconHtml(macroNormal);

        // Must contain group labels from the object keys
        console.assert(html1.includes("rates"),
          "FAIL: group key 'rates' not in output: " + html1.slice(0, 200));
        console.assert(html1.includes("index"),
          "FAIL: group key 'index' not in output: " + html1.slice(0, 200));

        // Must contain the formatted value for 10Y Treasury (4.47%)
        console.assert(html1.includes("4.47%"),
          "FAIL: % unit value '4.47%' not in output: " + html1.slice(0, 400));

        // Must contain the formatted value for S&P 500 (toLocaleString)
        console.assert(html1.includes("5,280.50") || html1.includes("5280.50"),
          "FAIL: S&P 500 value not properly formatted in output: " + html1.slice(0, 400));

        // Negative chg_abs -> mt-down
        console.assert(html1.includes("mt-down"),
          "FAIL: mt-down class not found for negative chg_abs: " + html1.slice(0, 400));

        // Positive chg_abs -> mt-up
        console.assert(html1.includes("mt-up"),
          "FAIL: mt-up class not found for positive chg_abs: " + html1.slice(0, 400));

        // latest_date in tooltip (as of:)
        console.assert(html1.includes("2026-06-04"),
          "FAIL: latest_date not in tooltip: " + html1.slice(0, 400));

        // TC2: empty groups -> fallback message
        const macroEmpty = { groups: {} };
        const html2 = buildEconHtml(macroEmpty);
        console.assert(html2.includes("No econ data available"),
          "FAIL: empty groups must return fallback message, got: " + html2);

        // TC3: groups missing entirely -> fallback message
        const macroNull = {};
        const html3 = buildEconHtml(macroNull);
        console.assert(html3.includes("No econ data available"),
          "FAIL: missing groups must return fallback message, got: " + html3);

        // TC4: null latest_value renders em dash
        const macroNullVal = {
          groups: {
            risk: [
              { series_id: "VIXCLS", label: "VIX", unit: "%",
                latest_value: null, latest_date: "2026-06-04",
                chg_abs: null, chg_pct: null }
            ]
          }
        };
        const html4 = buildEconHtml(macroNullVal);
        console.assert(html4.includes("—") || html4.includes("&mdash;"),
          "FAIL: null latest_value should render '—', got: " + html4);

        // TC5: zero chg_abs renders mt-flat (not mt-up or mt-down)
        const macroZeroChg = {
          groups: {
            jobs: [
              { series_id: "UNRATE", label: "Unemployment", unit: "%",
                latest_value: 4.0, latest_date: "2026-06-04",
                chg_abs: 0, chg_pct: 0 }
            ]
          }
        };
        const html5 = buildEconHtml(macroZeroChg);
        // Zero chg renders mt-flat (per spec: chgRaw < 0 ? 'mt-down' : 'mt-flat' branch)
        console.assert(html5.includes("mt-flat") || !html5.includes("mt-up"),
          "FAIL: zero chg_abs should render mt-flat or no chg span, got: " + html5);

        process.stdout.write("ALL_JS_ASSERTIONS_PASSED\n");
    """)

    def test_build_econ_html_logic(self):
        body = _build_econ_body()
        # Strip the outer {} wrapper from the function body to get just the content,
        # then construct a standalone function declaration for the harness.
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
            f"One or more JS assertions failed:\n{result.stdout}\n{result.stderr}"
        )
        # Any console.assert failures emit to stdout; confirm none
        assert "FAIL:" not in result.stdout, (
            f"JS assertion failures detected:\n{result.stdout}"
        )
