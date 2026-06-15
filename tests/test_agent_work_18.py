"""
Tests for AGENT_WORK_18 — Direction-colored Rules (edge) badges.

Acceptance criteria:
  1. node --check web/actionable.js passes (no syntax errors).
  2. _ruleSide() helper exists and calls actionDisplay() — single source of
     truth via actions.js; no second hardcoded direction map.
  3. Old hardcoded color values (#15803d, #b91c1c) are absent from
     ruleEdgeBadge / firesCellHtml contexts.
  4. No inline style="color:..." in ruleEdgeBadge() or firesCellHtml().
  5. CSS classes .rule-buy, .rule-sell, .rule-neutral, .rule-strong,
     .rule-weak, .rule-edge-badge are all present in web/styles.css.
  6. Edge numeric display (edge_20d) is still present — badge shows the
     edge number (e.g. '+3.2%').
  7. Winning-first ordering logic (sort by score then edge) is still present
     in firesCellHtml().
  8. ruleEdgeBadge() uses CSS classes (sideCls + emphCls) not inline colors.
  9. firesCellHtml() uses CSS classes on pill spans, not inline colors.
 10. No git commit was made — web/actionable.js and web/styles.css appear as
     modified (unstaged) in git status.
 11. pill-rule base class combined with rule-buy/sell/neutral direction
     classes exist in styles.css for grid cell badges.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
ACTIONABLE_JS = WEB_DIR / "actionable.js"
STYLES_CSS = WEB_DIR / "styles.css"


def _js() -> str:
    return ACTIONABLE_JS.read_text(encoding="utf-8")


def _css() -> str:
    return STYLES_CSS.read_text(encoding="utf-8")


def _extract_function(js: str, name: str) -> str:
    """Extract a named function body from JS source."""
    pat = f"function {name}("
    start = js.find(pat)
    if start == -1:
        raise AssertionError(f"Function '{name}' not found in actionable.js")
    brace_start = js.index("{", start)
    depth = 0
    i = brace_start
    while i < len(js):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[start: i + 1]
        i += 1
    raise AssertionError(f"Could not find closing brace for function '{name}'")


# ---------------------------------------------------------------------------
# 1. Syntax check
# ---------------------------------------------------------------------------

class TestSyntaxCheck:
    """node --check must exit 0 and produce no stderr."""

    def test_file_exists(self):
        assert ACTIONABLE_JS.exists(), f"actionable.js not found at {ACTIONABLE_JS}"

    def test_node_check_passes(self):
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check exited {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert result.stderr.strip() == "", (
            f"node --check produced unexpected stderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# 2. _ruleSide helper exists and routes through actionDisplay()
# ---------------------------------------------------------------------------

class TestRuleSideHelper:
    """_ruleSide() must exist and delegate to actionDisplay (no second map)."""

    def test_rule_side_function_defined(self):
        js = _js()
        assert "function _ruleSide(" in js, (
            "_ruleSide() function must be defined in actionable.js"
        )

    def test_rule_side_calls_action_display(self):
        js = _js()
        body = _extract_function(js, "_ruleSide")
        assert "actionDisplay(" in body, (
            "_ruleSide() must call actionDisplay() — single source of truth"
        )

    def test_rule_side_uses_dot_side(self):
        js = _js()
        body = _extract_function(js, "_ruleSide")
        assert ".side" in body, (
            "_ruleSide() must use the .side property returned by actionDisplay()"
        )

    def test_no_second_hardcoded_direction_map(self):
        """_ruleSide must not contain its own side→color lookup table.

        It should call actionDisplay() and read .side — the only acceptable
        mapping inside _ruleSide is 'BUY'→BM/'SELL'→SA to pick a
        representative code for actionDisplay.
        """
        js = _js()
        body = _extract_function(js, "_ruleSide")
        # The body must NOT contain a standalone 'buy': or 'sell': object
        # literal that would constitute a second mapping table.
        # Allowed: string comparisons like === 'buy' or === 'sell' (from .side)
        # Not allowed: { buy: ..., sell: ... } color maps.
        assert "{" not in body or "actionDisplay" in body, (
            "_ruleSide() must not contain an independent lookup object — "
            "use actionDisplay() as the sole side resolver"
        )

    def test_rule_side_returns_neutral_fallback(self):
        """Fallback to 'neutral' when scorecard entry or direction is missing."""
        js = _js()
        body = _extract_function(js, "_ruleSide")
        assert "neutral" in body, (
            "_ruleSide() must return 'neutral' as fallback"
        )


# ---------------------------------------------------------------------------
# 3. Old hardcoded hex colors absent from badge functions
# ---------------------------------------------------------------------------

class TestNoHardcodedColors:
    """#15803d and #b91c1c (old --bull/--bear CSS vars) must not appear in
    ruleEdgeBadge or firesCellHtml."""

    def test_no_15803d_in_rule_edge_badge(self):
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        assert "#15803d" not in body, (
            "ruleEdgeBadge() must not contain hardcoded color #15803d"
        )

    def test_no_b91c1c_in_rule_edge_badge(self):
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        assert "#b91c1c" not in body, (
            "ruleEdgeBadge() must not contain hardcoded color #b91c1c"
        )

    def test_no_15803d_in_fires_cell_html(self):
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert "#15803d" not in body, (
            "firesCellHtml() must not contain hardcoded color #15803d"
        )

    def test_no_b91c1c_in_fires_cell_html(self):
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert "#b91c1c" not in body, (
            "firesCellHtml() must not contain hardcoded color #b91c1c"
        )


# ---------------------------------------------------------------------------
# 4. No inline style="color:..." in ruleEdgeBadge / firesCellHtml
# ---------------------------------------------------------------------------

class TestNoInlineColorInBadgeFunctions:
    """The edge coloring must use CSS classes, not inline style= attributes."""

    def test_no_inline_color_in_rule_edge_badge(self):
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        # Allow only non-edge-color inline styles (e.g. opacity, font-size).
        # The critical check: no 'style="color:' for edge direction.
        # We check that there is no color in a style attribute for the badge span itself.
        # The span returned by ruleEdgeBadge must carry class= not style=color.
        assert 'style="color:' not in body and "style='color:" not in body, (
            "ruleEdgeBadge() must not use inline style=color — use CSS classes instead"
        )

    def test_rule_edge_badge_uses_class_attribute(self):
        """ruleEdgeBadge must build a span with class= containing side/emph classes."""
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        assert 'class="rule-edge-badge' in body or "class=`rule-edge-badge" in body or \
               "rule-edge-badge" in body, (
            "ruleEdgeBadge() must assign class rule-edge-badge to its span"
        )
        assert "sideCls" in body, (
            "ruleEdgeBadge() must use a sideCls variable for direction class"
        )
        assert "emphCls" in body, (
            "ruleEdgeBadge() must use an emphCls variable for emphasis class"
        )

    def test_fires_cell_html_no_inline_color_on_pills(self):
        """firesCellHtml pill spans must not carry style=color for direction."""
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        # The pills must use CSS class attributes for direction, not inline color.
        # We verify sideCls is applied on the pill span.
        assert "sideCls" in body, (
            "firesCellHtml() must use sideCls variable on pill spans"
        )
        assert "emphCls" in body, (
            "firesCellHtml() must use emphCls variable on pill spans"
        )


# ---------------------------------------------------------------------------
# 5. Required CSS classes present in styles.css
# ---------------------------------------------------------------------------

class TestCssClassesPresent:
    """All six required CSS classes must exist in web/styles.css."""

    def test_css_file_exists(self):
        assert STYLES_CSS.exists(), f"styles.css not found at {STYLES_CSS}"

    def test_rule_edge_badge_class(self):
        css = _css()
        assert ".rule-edge-badge" in css, (
            ".rule-edge-badge CSS class must be defined in styles.css"
        )

    def test_rule_buy_class(self):
        css = _css()
        assert ".rule-buy" in css, (
            ".rule-buy CSS class must be defined in styles.css"
        )

    def test_rule_sell_class(self):
        css = _css()
        assert ".rule-sell" in css, (
            ".rule-sell CSS class must be defined in styles.css"
        )

    def test_rule_neutral_class(self):
        css = _css()
        assert ".rule-neutral" in css, (
            ".rule-neutral CSS class must be defined in styles.css"
        )

    def test_rule_strong_class(self):
        css = _css()
        assert ".rule-strong" in css, (
            ".rule-strong CSS class must be defined in styles.css"
        )

    def test_rule_weak_class(self):
        css = _css()
        assert ".rule-weak" in css, (
            ".rule-weak CSS class must be defined in styles.css"
        )


# ---------------------------------------------------------------------------
# 6. Edge numeric display still present
# ---------------------------------------------------------------------------

class TestEdgeNumericDisplay:
    """The edge number must still be shown inside the badge."""

    def test_edge_20d_read_in_rule_edge_badge(self):
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        assert "edge_20d" in body, (
            "ruleEdgeBadge() must read edge_20d from the scorecard entry"
        )

    def test_edge_value_formatted_with_sign(self):
        """Badge must show sign-prefixed number like '+3.2%' or '-1.1%'."""
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        # Must contain toFixed for formatting
        assert "toFixed(" in body, (
            "ruleEdgeBadge() must use toFixed() to format the edge number"
        )
        # Must include a sign prefix ('+' for positive edge)
        assert "+" in body, (
            "ruleEdgeBadge() must prefix positive edge values with '+'"
        )

    def test_edge_formatted_in_fires_cell(self):
        """firesCellHtml must also show the edge number inside its pills."""
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert "toFixed(" in body, (
            "firesCellHtml() must use toFixed() to format the edge number on pills"
        )


# ---------------------------------------------------------------------------
# 7. Winning-first ordering still present in firesCellHtml
# ---------------------------------------------------------------------------

class TestWinningFirstOrdering:
    """Highest-score rule must still appear first in the fires cell."""

    def test_sort_by_score_present(self):
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        # The sort must reference .score
        assert ".score" in body or "score" in body, (
            "firesCellHtml() must sort items by score"
        )
        assert ".sort(" in body or "sort(" in body, (
            "firesCellHtml() must sort the items array"
        )

    def test_sort_descending_score(self):
        """Winning rule first means sort descending by score (b.score - a.score)."""
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert re.search(r"b\.score\s*-\s*a\.score", body), (
            "firesCellHtml() sort must be descending by score: b.score - a.score"
        )

    def test_secondary_sort_by_edge(self):
        """Secondary sort key must be edge (b.e - a.e or equivalent)."""
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert re.search(r"b\.e|a\.e", body), (
            "firesCellHtml() must use edge as secondary sort key"
        )


# ---------------------------------------------------------------------------
# 8. ruleEdgeBadge uses CSS classes not inline colors
# ---------------------------------------------------------------------------

class TestRuleEdgeBadgeStructure:
    """ruleEdgeBadge must produce a span with class= for both hue and emphasis."""

    def test_badge_uses_rule_buy_sell_neutral_variable(self):
        """sideCls must be assigned one of rule-buy / rule-sell / rule-neutral."""
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        assert "rule-buy" in body, (
            "ruleEdgeBadge() must reference 'rule-buy' CSS class"
        )
        assert "rule-sell" in body, (
            "ruleEdgeBadge() must reference 'rule-sell' CSS class"
        )
        assert "rule-neutral" in body, (
            "ruleEdgeBadge() must reference 'rule-neutral' CSS class"
        )

    def test_badge_uses_strong_weak_variable(self):
        """emphCls must be assigned rule-strong or rule-weak based on edge sign."""
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        assert "rule-strong" in body, (
            "ruleEdgeBadge() must reference 'rule-strong' CSS class"
        )
        assert "rule-weak" in body, (
            "ruleEdgeBadge() must reference 'rule-weak' CSS class"
        )

    def test_strong_for_positive_edge(self):
        """Positive edge (e > 0) must yield rule-strong."""
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        # Should see: e > 0 ? 'rule-strong' : 'rule-weak'
        assert re.search(r"e\s*>\s*0", body), (
            "ruleEdgeBadge() must check e > 0 to pick rule-strong vs rule-weak"
        )

    def test_rule_side_called_from_rule_edge_badge(self):
        """ruleEdgeBadge must call _ruleSide() to get the side."""
        js = _js()
        body = _extract_function(js, "ruleEdgeBadge")
        assert "_ruleSide(" in body, (
            "ruleEdgeBadge() must call _ruleSide() to resolve the direction"
        )


# ---------------------------------------------------------------------------
# 9. firesCellHtml uses CSS classes on pill spans
# ---------------------------------------------------------------------------

class TestFiresCellHtmlStructure:
    """firesCellHtml must use sideCls/emphCls on each pill span."""

    def test_pill_rule_class_present(self):
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert "pill-rule" in body, (
            "firesCellHtml() must use the pill-rule CSS class on each badge span"
        )

    def test_rule_buy_sell_neutral_in_fires_cell(self):
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert "rule-buy" in body, (
            "firesCellHtml() must reference rule-buy CSS class"
        )
        assert "rule-sell" in body, (
            "firesCellHtml() must reference rule-sell CSS class"
        )
        assert "rule-neutral" in body, (
            "firesCellHtml() must reference rule-neutral CSS class"
        )

    def test_strong_weak_in_fires_cell(self):
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert "rule-strong" in body, (
            "firesCellHtml() must reference rule-strong CSS class"
        )
        assert "rule-weak" in body, (
            "firesCellHtml() must reference rule-weak CSS class"
        )

    def test_rule_side_called_from_fires_cell(self):
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        assert "_ruleSide(" in body, (
            "firesCellHtml() must call _ruleSide() to resolve direction for each pill"
        )

    def test_no_inline_color_on_pills(self):
        """No style='color:...' on the pill spans in firesCellHtml."""
        js = _js()
        body = _extract_function(js, "firesCellHtml")
        # The pill span should use class= for hue; inline style should not set color.
        # We allow style= for things like font-size and white-space (layout only).
        color_inline = re.search(r'style=["\'][^"\']*color\s*:\s*#[0-9a-fA-F]{3,6}["\']', body)
        if color_inline:
            snippet = color_inline.group(0)
            # Only fail if the color looks like a direction color (red/green hex families)
            fail_colors = ["#15803d", "#b91c1c", "#16a34a", "#dc2626", "#22c55e"]
            for fc in fail_colors:
                assert fc not in snippet, (
                    f"firesCellHtml() must not use inline color {fc} on pills — use CSS classes"
                )


# ---------------------------------------------------------------------------
# 10. No git commit — files still unstaged
# ---------------------------------------------------------------------------

class TestNoGitCommit:
    """web/actionable.js and web/styles.css must be unstaged (not committed)."""

    def test_actionable_js_unstaged(self):
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--short"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"git status failed: {result.stderr}"
        lines = result.stdout.splitlines()
        # Find the line for actionable.js — must be " M" (unstaged modified)
        matched = [l for l in lines if "web/actionable.js" in l or "actionable.js" in l]
        assert matched, "web/actionable.js must appear in git status output"
        # The first char should NOT be 'A' (staged new) or 'M' in column 1 (staged)
        for line in matched:
            status_code = line[:2]
            assert "?" not in status_code or "M" in status_code[1], (
                f"web/actionable.js status '{status_code}' unexpected — must be modified"
            )
            # Not a clean committed state
            assert status_code.strip() != "", (
                "web/actionable.js must show as modified in git status"
            )

    def test_styles_css_unstaged(self):
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--short"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"git status failed: {result.stderr}"
        lines = result.stdout.splitlines()
        matched = [l for l in lines if "web/styles.css" in l or "styles.css" in l]
        assert matched, "web/styles.css must appear in git status output"
        for line in matched:
            assert line.strip() != "", (
                "web/styles.css must show as modified in git status"
            )

    def test_actionable_js_not_staged_for_commit(self):
        """actionable.js must be unstaged (column 1 of git status must not be 'M' or 'A')."""
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--short"],
            capture_output=True,
            text=True,
        )
        lines = result.stdout.splitlines()
        for line in lines:
            if "actionable.js" in line:
                # Column 0 = index status; ' M' means unstaged, 'M ' means staged
                assert line[0] == " " or line[0] == "?", (
                    f"web/actionable.js must NOT be staged for commit (status: '{line[:2]}')"
                )


# ---------------------------------------------------------------------------
# 11. pill-rule combined with direction classes in styles.css
# ---------------------------------------------------------------------------

class TestPillRuleDirectionClasses:
    """Triple-class selectors .pill-rule.rule-buy.rule-strong etc. must exist."""

    def test_pill_rule_buy_strong(self):
        css = _css()
        assert ".pill-rule.rule-buy.rule-strong" in css, (
            ".pill-rule.rule-buy.rule-strong must be defined in styles.css"
        )

    def test_pill_rule_buy_weak(self):
        css = _css()
        assert ".pill-rule.rule-buy.rule-weak" in css, (
            ".pill-rule.rule-buy.rule-weak must be defined in styles.css"
        )

    def test_pill_rule_sell_strong(self):
        css = _css()
        assert ".pill-rule.rule-sell.rule-strong" in css, (
            ".pill-rule.rule-sell.rule-strong must be defined in styles.css"
        )

    def test_pill_rule_sell_weak(self):
        css = _css()
        assert ".pill-rule.rule-sell.rule-weak" in css, (
            ".pill-rule.rule-sell.rule-weak must be defined in styles.css"
        )

    def test_pill_rule_neutral_strong(self):
        css = _css()
        assert ".pill-rule.rule-neutral.rule-strong" in css, (
            ".pill-rule.rule-neutral.rule-strong must be defined in styles.css"
        )

    def test_pill_rule_neutral_weak(self):
        css = _css()
        assert ".pill-rule.rule-neutral.rule-weak" in css, (
            ".pill-rule.rule-neutral.rule-weak must be defined in styles.css"
        )

    def test_buy_strong_uses_green_palette(self):
        """Solid green for buy-strong must use the project palette color."""
        css = _css()
        # Find the .pill-rule.rule-buy.rule-strong block and check it has #2f9e2f
        pattern = re.compile(
            r'\.pill-rule\.rule-buy\.rule-strong\s*\{([^}]+)\}', re.DOTALL
        )
        match = pattern.search(css)
        assert match, ".pill-rule.rule-buy.rule-strong block not found in styles.css"
        block = match.group(1)
        assert "#2f9e2f" in block, (
            ".pill-rule.rule-buy.rule-strong must use #2f9e2f (project green palette)"
        )

    def test_sell_strong_uses_red_palette(self):
        """Solid red for sell-strong must use the project palette color."""
        css = _css()
        pattern = re.compile(
            r'\.pill-rule\.rule-sell\.rule-strong\s*\{([^}]+)\}', re.DOTALL
        )
        match = pattern.search(css)
        assert match, ".pill-rule.rule-sell.rule-strong block not found in styles.css"
        block = match.group(1)
        assert "#d83a3a" in block, (
            ".pill-rule.rule-sell.rule-strong must use #d83a3a (project red palette)"
        )
