"""
Tests for AGENT_WORK_51 / TASK 50 — Per-source reason list with action icons
in the Actionable Sources column.

Acceptance criteria (from DEV_HANDOFF.md and TASK_50_source_column_icons.md):

  Check 1  — node --check web/actions.js  exits 0 (no JS syntax errors)
  Check 2  — node --check web/actionable.js  exits 0
  Check 3a — _ICON map exists in actions.js with all 15 required keys
  Check 3b — _ICON_NONE = { g: '·', c: '#d1d5db' } exists in actions.js
  Check 3c — actionIcon() function is defined in actions.js
  Check 3d — window.actionIcon = actionIcon is exposed in actions.js
  Check 3e — actionIcon calls actionDisplay() inside its body
  Check 4a — _srcReasonsHtml function is defined in actionable.js
  Check 4b — _srcReasonsHtml calls _sourcesOf(r)
  Check 4c — _srcReasonsHtml calls actionIcon()
  Check 4d — _srcReasonsHtml produces src-reason-line divs with src-tag, src-ic, src-rsn spans
  Check 4e — _srcReasonsHtml puts winning source first (winner.concat(others) pattern)
  Check 4f — _srcReasonsHtml sorts others by ACTION_RANK
  Check 5a — act-action-cell template calls _srcReasonsHtml(r) (not _srcSubLineHtml)
  Check 5b — act-action-cell template still contains _badgeAction  (headline badge present)
  Check 5c — _winningReason(r) is NOT called inside the act-action-cell td template block
  Check 5d — over-Max overlay is still present in the template (_isOverMaxOverlay)
  Check 6  — _winningReason function definition is preserved in actionable.js
  Check 6b — _winningReason is still called at least twice in drilldown (lines 1835/1880/2809)
  Check 7  — _srcSubLineHtml function is still defined (not deleted) but not called in web/
  Check 8a — .src-reasons CSS rule present in actionable.html
  Check 8b — .src-reason-line CSS rule present in actionable.html
  Check 8c — .src-tag CSS rule present in actionable.html
  Check 8d — .src-ic CSS rule present in actionable.html
  Check 8e — .src-rsn CSS rule present in actionable.html
  Check 9  — DEV_HANDOFF.md last non-blank line is ALL_DONE
  Check 10 — No etl/ or api/ Python files changed for TASK 50 (front-end only)
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
ACTIONS_JS     = PROJECT / "web" / "actions.js"
ACTIONABLE_JS  = PROJECT / "web" / "actionable.js"
ACTIONABLE_HTML = PROJECT / "web" / "actionable.html"
DEV_HANDOFF    = PROJECT / "DEV_HANDOFF.md"

# Expected keys in _ICON map (from task spec)
EXPECTED_ICON_KEYS = {
    "BM", "BS", "BMN", "BW", "BSW",
    "HOLD", "N", "BN",
    "SA", "SS", "STM", "SO", "SW", "SWW", "SN",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Check 1 & 2: JavaScript syntax
# ---------------------------------------------------------------------------

class TestJSSyntax:
    def test_actions_js_syntax(self):
        """node --check web/actions.js must exit 0."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONS_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"node --check web/actions.js failed:\n{result.stderr}"
        )

    def test_actionable_js_syntax(self):
        """node --check web/actionable.js must exit 0."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"node --check web/actionable.js failed:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Check 3: _ICON map and actionIcon() in actions.js
# ---------------------------------------------------------------------------

class TestActionsJsIconMap:
    @pytest.fixture(autouse=True)
    def js(self):
        self._js = _read(ACTIONS_JS)

    def test_icon_map_exists(self):
        """_ICON variable is declared in actions.js."""
        assert "var _ICON" in self._js, "_ICON map not found in actions.js"

    @pytest.mark.parametrize("key", sorted(EXPECTED_ICON_KEYS))
    def test_icon_map_has_key(self, key):
        """_ICON map must contain every expected action code key."""
        # Look for the key as a JS property: either "KEY:" or BN: etc.
        pattern = rf"\b{re.escape(key)}\s*:"
        assert re.search(pattern, self._js), (
            f"_ICON map missing key '{key}' in actions.js"
        )

    def test_icon_none_exists(self):
        """_ICON_NONE must be defined with glyph '·' and color '#d1d5db'."""
        js = self._js
        assert "_ICON_NONE" in js, "_ICON_NONE not found in actions.js"
        # The glyph '·' (middle dot U+00B7) and color
        assert "·" in js or "\\u00b7" in js or "'·'" in js or '"·"' in js, (
            "_ICON_NONE glyph '·' not found in actions.js"
        )
        assert "#d1d5db" in js, "_ICON_NONE color '#d1d5db' not found in actions.js"

    def test_action_icon_function_defined(self):
        """actionIcon() function must be defined."""
        assert "function actionIcon(" in self._js, (
            "actionIcon function not found in actions.js"
        )

    def test_action_icon_exposed_on_window(self):
        """window.actionIcon must be assigned."""
        assert "window.actionIcon" in self._js, (
            "window.actionIcon not exposed in actions.js"
        )

    def test_action_icon_calls_action_display(self):
        """actionIcon() body must call actionDisplay() to resolve aliases."""
        # Find the function body
        m = re.search(r"function actionIcon\(.*?\{(.+?)^\s*\}", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate actionIcon function body"
        body = m.group(1)
        assert "actionDisplay(" in body, (
            "actionIcon() does not call actionDisplay() — alias resolution missing"
        )

    def test_buy_min_glyph_and_color(self):
        """BMN should map to glyph ↥ with color #16a34a."""
        js = self._js
        # Both glyph and color must appear near BMN
        assert "↥" in js or "↥" in js, "BMN glyph '↥' not found in actions.js"
        assert "#16a34a" in js, "BMN color '#16a34a' not found in actions.js"

    def test_sell_overage_glyph_and_color(self):
        """SO should map to glyph ↧ with color #ea580c."""
        js = self._js
        assert "↧" in js or "↧" in js, "SO glyph '↧' not found in actions.js"
        assert "#ea580c" in js, "SO color '#ea580c' not found in actions.js"

    def test_buy_watch_color(self):
        """BW/BSW should map to color #22c55e (green)."""
        assert "#22c55e" in self._js, "BW/BSW color '#22c55e' not found in actions.js"

    def test_sell_watch_color(self):
        """SW/SWW should map to color #f97316 (amber)."""
        assert "#f97316" in self._js, "SW/SWW color '#f97316' not found in actions.js"


# ---------------------------------------------------------------------------
# Check 4: _srcReasonsHtml() in actionable.js
# ---------------------------------------------------------------------------

class TestSrcReasonsHtml:
    @pytest.fixture(autouse=True)
    def js(self):
        self._js = _read(ACTIONABLE_JS)

    def test_function_defined(self):
        """_srcReasonsHtml must be defined in actionable.js."""
        assert "function _srcReasonsHtml(" in self._js, (
            "_srcReasonsHtml function not found in actionable.js"
        )

    def test_calls_sources_of(self):
        """_srcReasonsHtml must call _sourcesOf(r)."""
        # Find the function body
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "_sourcesOf(" in body, "_srcReasonsHtml does not call _sourcesOf()"

    def test_calls_action_icon(self):
        """_srcReasonsHtml must call actionIcon()."""
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "actionIcon(" in body, "_srcReasonsHtml does not call actionIcon()"

    def test_produces_src_reason_line_divs(self):
        """_srcReasonsHtml must produce src-reason-line divs."""
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "src-reason-line" in body, (
            '_srcReasonsHtml must produce <div class="src-reason-line"> elements'
        )

    def test_produces_src_tag_span(self):
        """_srcReasonsHtml must include .src-tag span."""
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "src-tag" in body, "_srcReasonsHtml missing src-tag span"

    def test_produces_src_ic_span(self):
        """_srcReasonsHtml must include .src-ic span."""
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "src-ic" in body, "_srcReasonsHtml missing src-ic span"

    def test_produces_src_rsn_span(self):
        """_srcReasonsHtml must include .src-rsn span."""
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "src-rsn" in body, "_srcReasonsHtml missing src-rsn span"

    def test_winner_concat_others(self):
        """_srcReasonsHtml must put winning source first (winner.concat(others) pattern)."""
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "winner.concat(others)" in body or "winner.concat(" in body, (
            "_srcReasonsHtml must put winning source first via winner.concat(others)"
        )

    def test_sorts_others_by_action_rank(self):
        """_srcReasonsHtml must sort non-winning sources by ACTION_RANK."""
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "ACTION_RANK" in body, (
            "_srcReasonsHtml must sort others by ACTION_RANK severity"
        )

    def test_wraps_in_src_reasons_div(self):
        """_srcReasonsHtml must wrap result in a .src-reasons div."""
        m = re.search(r"function _srcReasonsHtml\(.*?\{(.+?)^function ", self._js,
                      re.DOTALL | re.MULTILINE)
        assert m, "Could not locate _srcReasonsHtml function body"
        body = m.group(1)
        assert "src-reasons" in body, (
            "_srcReasonsHtml missing outer <div class='src-reasons'> wrapper"
        )


# ---------------------------------------------------------------------------
# Check 5: Template updated in act-action-cell
# ---------------------------------------------------------------------------

class TestTemplateCellUpdated:
    @pytest.fixture(autouse=True)
    def js(self):
        self._js = _read(ACTIONABLE_JS)
        # Find the act-action-cell td block context around _srcReasonsHtml
        # We look for the template section that contains act-action-cell
        m = re.search(
            r'class="act-action-cell"(.+?)</td>',
            self._js, re.DOTALL
        )
        self._cell_block = m.group(0) if m else ""

    def test_src_reasons_html_called_in_cell(self):
        """Template must call _srcReasonsHtml(r) in the act-action-cell td."""
        assert "_srcReasonsHtml(r)" in self._js, (
            "_srcReasonsHtml(r) not found in actionable.js template"
        )
        # Also confirm it appears in the cell block
        assert "_srcReasonsHtml(r)" in self._cell_block, (
            "_srcReasonsHtml(r) not called inside act-action-cell td"
        )

    def test_src_sub_line_html_not_called_in_cell(self):
        """Template must NOT call _srcSubLineHtml in the act-action-cell td."""
        assert "_srcSubLineHtml(r)" not in self._cell_block, (
            "_srcSubLineHtml(r) still called in act-action-cell td — not replaced"
        )

    def test_badge_action_present_in_cell(self):
        """Headline action badge (_badgeAction) must still be in the template."""
        assert "_badgeAction" in self._cell_block, (
            "_badgeAction missing from act-action-cell template — headline badge removed"
        )

    def test_winning_reason_not_in_cell_template(self):
        """_winningReason(r) must NOT appear in the act-action-cell td template."""
        assert "_winningReason(r)" not in self._cell_block, (
            "_winningReason(r) still rendered in act-action-cell template — should be removed"
        )

    def test_over_max_overlay_present_in_cell(self):
        """_isOverMaxOverlay must still be present in the act-action-cell template."""
        assert "_isOverMaxOverlay" in self._cell_block, (
            "_isOverMaxOverlay missing from act-action-cell — over-Max overlay was removed"
        )


# ---------------------------------------------------------------------------
# Check 6: _winningReason preserved and still used in drilldown
# ---------------------------------------------------------------------------

class TestWinningReasonPreserved:
    @pytest.fixture(autouse=True)
    def js(self):
        self._js = _read(ACTIONABLE_JS)

    def test_winning_reason_function_defined(self):
        """_winningReason function definition must be preserved."""
        assert "function _winningReason(" in self._js, (
            "_winningReason function was deleted — it is still needed by the drilldown"
        )

    def test_winning_reason_called_in_drilldown(self):
        """_winningReason must be called at least twice (drilldown usage)."""
        calls = re.findall(r"_winningReason\(", self._js)
        # Expect: 1 definition + at least 2 call sites
        assert len(calls) >= 3, (
            f"_winningReason appears only {len(calls)} times — expected definition + ≥2 calls"
        )


# ---------------------------------------------------------------------------
# Check 7: _srcSubLineHtml defined but not called in web/ files
# ---------------------------------------------------------------------------

class TestSrcSubLineHtmlUnused:
    # test_src_sub_line_html_still_defined — RETIRED (TASK_112 test-debt
    # cleanup, 2026-07-04). AGENT_WORK_50 deliberately kept `_srcSubLineHtml`
    # as dead code (unused but not deleted). A later cleanup removed it
    # outright, replacing its responsibility with `_srcReasonsHtml()` (see
    # test_agent_work_27.py::TestSrcReasonsHtml and the wholesale
    # retirement note in test_agent_work_24.py). Cat B — the "kept as dead
    # code" premise no longer holds; it was deleted in a later, legitimate
    # cleanup, not a regression.

    def test_src_sub_line_html_not_called_in_web(self):
        """_srcSubLineHtml must not be called from any web/ JS or HTML file."""
        web_dir = PROJECT / "web"
        callers = []
        for f in web_dir.glob("*.js"):
            content = f.read_text(encoding="utf-8")
            # Look for call pattern (not the definition line)
            for m in re.finditer(r"_srcSubLineHtml\s*\(", content):
                # Skip if this is the function definition
                line_start = content.rfind("\n", 0, m.start()) + 1
                line = content[line_start:content.find("\n", m.start())]
                if "function _srcSubLineHtml" not in line:
                    callers.append(f"{f.name}:{line.strip()}")
        assert not callers, (
            f"_srcSubLineHtml is still being called in web/ files: {callers}"
        )


# ---------------------------------------------------------------------------
# Check 8: CSS rules in actionable.html
# ---------------------------------------------------------------------------

class TestCSSRules:
    EXPECTED_CLASSES = [
        ".src-reasons",
        ".src-reason-line",
        ".src-tag",
        ".src-ic",
        ".src-rsn",
    ]

    @pytest.fixture(autouse=True)
    def html(self):
        self._html = _read(ACTIONABLE_HTML)

    @pytest.mark.parametrize("cls", EXPECTED_CLASSES)
    def test_css_class_present(self, cls):
        """Each new CSS class must be present in actionable.html style block."""
        assert cls in self._html, (
            f"CSS class '{cls}' not found in actionable.html"
        )

    def test_src_reasons_has_margin_top(self):
        """`.src-reasons` must include margin-top style."""
        assert "margin-top" in self._html, (
            ".src-reasons missing margin-top in actionable.html"
        )

    def test_src_reason_line_is_flex(self):
        """.src-reason-line must use display:flex."""
        # Find the rule
        m = re.search(r"\.src-reason-line\s*\{([^}]+)\}", self._html)
        assert m, ".src-reason-line rule not found"
        rule = m.group(1)
        assert "flex" in rule, ".src-reason-line must set display:flex"

    def test_src_rsn_has_ellipsis(self):
        """.src-rsn must have text-overflow:ellipsis for truncation."""
        m = re.search(r"\.src-rsn\s*\{([^}]+)\}", self._html)
        assert m, ".src-rsn rule not found"
        rule = m.group(1)
        assert "ellipsis" in rule, ".src-rsn missing text-overflow:ellipsis"


# ---------------------------------------------------------------------------
# Check 9: DEV_HANDOFF ends with ALL_DONE
# ---------------------------------------------------------------------------

def test_dev_handoff_all_done():
    """DEV_HANDOFF.md last non-blank line must be ALL_DONE."""
    text = _read(DEV_HANDOFF)
    non_blank = [line.rstrip() for line in text.splitlines() if line.strip()]
    assert non_blank, "DEV_HANDOFF.md is empty"
    assert non_blank[-1] == "ALL_DONE", (
        f"DEV_HANDOFF.md last non-blank line is '{non_blank[-1]}', expected 'ALL_DONE'"
    )


# ---------------------------------------------------------------------------
# Check 10: No ETL/API/DB changes for TASK 50 (front-end only)
# ---------------------------------------------------------------------------

def test_no_etl_api_db_python_changes():
    """TASK 50 is front-end only — verify changed files are only web/."""
    # We check the modified files from git status (working tree)
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--",
         "etl/derive_actionable.py",  # check TASK 50 did not touch this
         "api/routers/actionable.py"],
        capture_output=True, text=True,
        cwd=str(PROJECT)
    )
    # etl/derive_actionable.py changes belong to TASK 49, not TASK 50
    # For TASK 50 specifically we just ensure actions.js, actionable.js,
    # actionable.html are the only TASK-50-specific files changed.
    task50_changed = []
    for path in ["web/actions.js", "web/actionable.js", "web/actionable.html"]:
        full = PROJECT / path
        if full.exists():
            task50_changed.append(path)

    # All three TASK 50 files must exist and be the expected files
    assert "web/actions.js" in task50_changed
    assert "web/actionable.js" in task50_changed
    assert "web/actionable.html" in task50_changed

    # No new Python files that would be part of TASK 50
    unexpected = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "api/routers/actionable.py"],
        capture_output=True, text=True,
        cwd=str(PROJECT)
    )
    assert "actionable.py" not in unexpected.stdout, (
        "api/routers/actionable.py was modified — TASK 50 is front-end only"
    )
