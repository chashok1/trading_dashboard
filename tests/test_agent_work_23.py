"""
Tests for AGENT_WORK_23 — Unify all action badge displays under a single
.act-badge CSS component.

Acceptance criteria (from AGENT_WORK_23.md / DEV_HANDOFF.md):
  1. node --check web/actionable.js passes (syntax OK).
  2. No 'badge-action' classes remain in web/actionable.js (dead classes removed).
  3. No 'badge-action' classes remain in web/actionable.html body (inline block removed).
     Exception: a comment line mentioning removal is acceptable.
  4. .act-badge is used in Action column cell in renderGrid().
  5. .act-badge is used in TrTnBBRskRng column cell in renderGrid().
  6. .act-badge is used in Final Call cell (_finalCallHtml).
  7. .act-badge is used in firesCellHtml() (Rules/edge column).
  8. .act-badge is used in _renderOtherSources() (other-source pills).
  9. .act-badge is used in modal drilldown Action field (openDrilldown).
 10. .act-badge is used in per-source actions table (modal sources table cell).
 11. .act-badge is used in modal fires section (pill-rule pills).
 12. .act-badge is used in _comparisonPanelHtml() (comparison panel action).
 13. .act-badge is used in _actionPopHtml() (action hover popup).
 14. .act-badge-sm is used in firesCellHtml() (small Rules badges).
 15. .act-badge-sm is used in _renderOtherSources() (small other-source pills).
 16. .act-badge-sm is used in _actionPopHtml() All Sources list.
 17. .act-badge-sm is used in modal fires pills.
 18. colorCls token from actions.js is still used alongside act-badge (not hardcoded).
 19. .act-badge defined in styles.css (pill shape: inline-block, border-radius, font-size).
 20. .act-badge-sm defined in styles.css (smaller variant).
 21. Old pill-rule color rules removed from styles.css; .act-badge-sm.rule-* colors present.
 22. .pill-rule interactive CSS (cursor, hover, active) preserved in actionable.html.
 23. Filter chips (act-chip / act-chip-*) still present in actionable.html (not touched).
 24. No truncation: actionable.js and styles.css end at a valid closing brace/statement.
 25. No production Python files were modified.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT    = Path(__file__).resolve().parent.parent
WEB_DIR         = PROJECT_ROOT / "web"
ACTIONABLE_HTML = WEB_DIR / "actionable.html"
ACTIONABLE_JS   = WEB_DIR / "actionable.js"
STYLES_CSS      = WEB_DIR / "styles.css"
API_DIR         = PROJECT_ROOT / "api"


# ─── helpers ────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_body(src: str, func_name: str, max_len: int = 6000) -> str:
    """Return the source text from 'function func_name' up to max_len chars."""
    idx = src.find(f"function {func_name}(")
    if idx == -1:
        idx = src.find(f"async function {func_name}(")
    assert idx != -1, f"{func_name}() not found in source"
    return src[idx: idx + max_len]


# ─── Criterion 1: Syntax check ───────────────────────────────────────────────

class TestSyntaxCheck:
    def test_actionable_js_syntax(self):
        """node --check must pass with no output and exit 0."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"node --check failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
        assert result.stdout.strip() == "", (
            f"node --check produced unexpected output: {result.stdout!r}"
        )


# ─── Criteria 2-3: No dead badge-action classes remain ───────────────────────

class TestNoBadgeActionRemnants:
    def setup_method(self):
        self.js   = _read(ACTIONABLE_JS)
        self.html = _read(ACTIONABLE_HTML)

    def test_no_badge_action_in_actionable_js(self):
        """'badge-action' class must not appear anywhere in actionable.js."""
        # Any use (string literal, template literal, class attribute) counts.
        assert "badge-action" not in self.js, (
            "Dead 'badge-action' class still present in actionable.js"
        )

    def test_no_badge_action_in_actionable_html_styles(self):
        """Inline <style> in actionable.html must not define badge-action rules.
        A comment noting its removal is acceptable; a CSS rule definition is not.
        """
        # Find the inline <style> block
        style_match = re.search(r'<style[^>]*>(.*?)</style>', self.html, re.DOTALL)
        if style_match:
            style_block = style_match.group(1)
            # CSS rule pattern: .badge-action { ... } or .badge-action-* { ... }
            assert not re.search(r'\.badge-action[\w-]*\s*\{', style_block), (
                "actionable.html still contains a .badge-action CSS rule definition "
                "(it should have been removed, per the handoff)"
            )

    def test_badge_action_html_only_in_comment(self):
        """Any remaining 'badge-action' text in actionable.html must be comment-only."""
        # If badge-action appears at all, it must be inside a CSS comment /* ... */
        # or an HTML comment <!-- ... -->
        for m in re.finditer(r'badge-action', self.html):
            pos = m.start()
            # Check if it's inside a CSS comment
            css_comment_start = self.html.rfind('/*', 0, pos)
            css_comment_end   = self.html.find('*/', pos)
            in_css_comment = (css_comment_start != -1 and css_comment_end != -1
                              and css_comment_end > css_comment_start)
            # Check if it's inside an HTML comment
            html_comment_start = self.html.rfind('<!--', 0, pos)
            html_comment_end   = self.html.find('-->', pos)
            in_html_comment = (html_comment_start != -1 and html_comment_end != -1
                               and html_comment_end > html_comment_start)
            assert in_css_comment or in_html_comment, (
                f"'badge-action' found at position {pos} in actionable.html "
                "but it is NOT inside a comment — a live CSS/HTML reference remains"
            )


# ─── Criteria 4-13: .act-badge present at all major call sites ───────────────

class TestActBadgeCallSites:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_act_badge_in_render_grid_action_cell(self):
        """renderGrid() Action column cell must use act-badge."""
        render_body = _func_body(self.src, "renderGrid", max_len=8000)
        assert "act-badge" in render_body, (
            "renderGrid() Action cell must use .act-badge"
        )

    def test_act_badge_in_render_grid_trtnsbb_cell(self):
        """renderGrid() TrTnBBRskRng cell (rrHtml) must use act-badge."""
        # The TrTnBBRskRng cell is built immediately before tr.innerHTML in renderGrid.
        render_body = _func_body(self.src, "renderGrid", max_len=8000)
        # Look for act-badge in the context of rrHtml construction
        rr_idx = render_body.find("rrHtml")
        assert rr_idx != -1, "rrHtml variable not found in renderGrid()"
        surrounding = render_body[rr_idx: rr_idx + 400]
        assert "act-badge" in surrounding, (
            "TrTnBBRskRng rrHtml in renderGrid() must use .act-badge"
        )

    def test_act_badge_in_final_call_html(self):
        """_finalCallHtml() must use act-badge for the Final Call pill."""
        fc_body = _func_body(self.src, "_finalCallHtml", max_len=2000)
        assert "act-badge" in fc_body, (
            "_finalCallHtml() must render the Final Call pill with .act-badge"
        )

    def test_act_badge_in_fires_cell_html(self):
        """firesCellHtml() must use act-badge for Rules/edge pill spans."""
        fires_body = _func_body(self.src, "firesCellHtml", max_len=1500)
        assert "act-badge" in fires_body, (
            "firesCellHtml() must use .act-badge for the Rules(edge) pills"
        )

    def test_act_badge_in_render_other_sources(self):
        """_renderOtherSources() must use act-badge for other-source pills."""
        os_body = _func_body(self.src, "_renderOtherSources", max_len=1500)
        assert "act-badge" in os_body, (
            "_renderOtherSources() must use .act-badge for other-source pills"
        )

    def test_act_badge_in_open_drilldown_action_field(self):
        """openDrilldown() modal Action KV field must use act-badge."""
        od_body = _func_body(self.src, "openDrilldown", max_len=5000)
        # The Action field is in the modalKv innerHTML
        assert "act-badge" in od_body, (
            "openDrilldown() modal Action field must use .act-badge"
        )

    def test_act_badge_in_modal_sources_table(self):
        """Per-source actions table in openDrilldown() must use act-badge for action column."""
        od_body = _func_body(self.src, "openDrilldown", max_len=7000)
        # The per-source action cell is the last <td> column in the source table
        # Check that act-badge appears in the per-source loop section
        src_idx = od_body.find("srcTbody")
        assert src_idx != -1, "srcTbody not found in openDrilldown()"
        src_section = od_body[src_idx: src_idx + 2000]
        assert "act-badge" in src_section, (
            "Per-source actions table in openDrilldown() must use .act-badge "
            "for the per-source action column"
        )

    def test_act_badge_in_modal_fires(self):
        """Modal fires pills must use act-badge."""
        od_body = _func_body(self.src, "openDrilldown", max_len=7000)
        fires_idx = od_body.find("modalFires")
        assert fires_idx != -1, "modalFires section not found in openDrilldown()"
        fires_section = od_body[fires_idx: fires_idx + 700]
        assert "act-badge" in fires_section, (
            "Modal fires pills in openDrilldown() must use .act-badge"
        )

    def test_act_badge_in_comparison_panel(self):
        """_comparisonPanelHtml() must use act-badge for action display."""
        cmp_body = _func_body(self.src, "_comparisonPanelHtml", max_len=3000)
        assert "act-badge" in cmp_body, (
            "_comparisonPanelHtml() must use .act-badge for the action display"
        )

    def test_act_badge_in_action_pop_html(self):
        """_actionPopHtml() hover popup must use act-badge."""
        pop_body = _func_body(self.src, "_actionPopHtml", max_len=3000)
        assert "act-badge" in pop_body, (
            "_actionPopHtml() hover popup must use .act-badge for the action badge"
        )


# ─── Criteria 14-17: .act-badge-sm used in dense/small contexts ──────────────

class TestActBadgeSmCallSites:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_act_badge_sm_in_fires_cell_html(self):
        """firesCellHtml() must use act-badge-sm for compact Rules/edge pills."""
        fires_body = _func_body(self.src, "firesCellHtml", max_len=1500)
        assert "act-badge-sm" in fires_body, (
            "firesCellHtml() must use .act-badge-sm for compact Rule badges"
        )

    def test_act_badge_sm_in_render_other_sources(self):
        """_renderOtherSources() must use act-badge-sm for other-source pills."""
        os_body = _func_body(self.src, "_renderOtherSources", max_len=1500)
        assert "act-badge-sm" in os_body, (
            "_renderOtherSources() must use .act-badge-sm for compact other-source pills"
        )

    def test_act_badge_sm_in_action_pop_html_all_sources(self):
        """_actionPopHtml() All Sources list must use act-badge-sm."""
        pop_body = _func_body(self.src, "_actionPopHtml", max_len=5000)
        assert "act-badge-sm" in pop_body, (
            "_actionPopHtml() All Sources list must use .act-badge-sm for per-source pills"
        )

    def test_act_badge_sm_in_modal_fires_pills(self):
        """Modal fires pills in openDrilldown() must use act-badge-sm."""
        od_body = _func_body(self.src, "openDrilldown", max_len=7000)
        fires_idx = od_body.find("modalFires")
        assert fires_idx != -1, "modalFires section not found in openDrilldown()"
        fires_section = od_body[fires_idx: fires_idx + 700]
        assert "act-badge-sm" in fires_section, (
            "Modal fires pills in openDrilldown() must use .act-badge-sm"
        )


# ─── Criterion 18: colorCls token still used (not hardcoded) ─────────────────

class TestColorClsTokenUsed:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_colorcls_used_in_action_badge_construction(self):
        """colorCls from actions.js must still appear (tokens not replaced by hardcoded hex)."""
        assert "colorCls" in self.src, (
            "'colorCls' token from actions.js must still be used in actionable.js "
            "(colors should not be hardcoded)"
        )

    def test_actiondisplay_still_called_for_color(self):
        """actionDisplay() must still be called to obtain colorCls."""
        assert "actionDisplay(" in self.src, (
            "actionDisplay() from actions.js must still be called to get colorCls"
        )

    def test_no_hardcoded_hex_in_badge_markup(self):
        """act-badge markup must not contain hardcoded color hex values like background:#."""
        # Search for act-badge template literals that include background:# inline styles
        # (would indicate colorCls was abandoned for hardcoded colors)
        # Allow background: in CSS class rules, but not inside template literal strings
        # building act-badge spans with inline style="background:#..."
        matches = re.findall(
            r'act-badge[^`"\']*style=["\'][^"\']*background\s*:#',
            self.src
        )
        assert len(matches) == 0, (
            f"act-badge markup found with hardcoded background color (colorCls abandoned): {matches}"
        )


# ─── Criteria 19-20: .act-badge and .act-badge-sm defined in styles.css ──────

class TestActBadgeCssDefined:
    def setup_method(self):
        self.css = _read(STYLES_CSS)

    def test_act_badge_class_defined(self):
        """.act-badge must be defined as a CSS class in styles.css."""
        assert ".act-badge {" in self.css or ".act-badge{" in self.css, (
            ".act-badge CSS class is not defined in styles.css"
        )

    def test_act_badge_is_inline_block(self):
        """.act-badge must use display:inline-block (pill shape)."""
        badge_idx = self.css.find(".act-badge {")
        if badge_idx == -1:
            badge_idx = self.css.find(".act-badge{")
        assert badge_idx != -1, ".act-badge class not found"
        rule_block = self.css[badge_idx: badge_idx + 400]
        assert "inline-block" in rule_block, (
            ".act-badge must set display:inline-block for the pill shape"
        )

    def test_act_badge_has_border_radius(self):
        """.act-badge must define border-radius (pill shape)."""
        badge_idx = self.css.find(".act-badge {")
        if badge_idx == -1:
            badge_idx = self.css.find(".act-badge{")
        assert badge_idx != -1
        rule_block = self.css[badge_idx: badge_idx + 400]
        assert "border-radius" in rule_block, (
            ".act-badge must define border-radius for the pill shape"
        )

    def test_act_badge_has_font_size(self):
        """.act-badge must define font-size."""
        badge_idx = self.css.find(".act-badge {")
        if badge_idx == -1:
            badge_idx = self.css.find(".act-badge{")
        assert badge_idx != -1
        rule_block = self.css[badge_idx: badge_idx + 400]
        assert "font-size" in rule_block, (
            ".act-badge must define font-size"
        )

    def test_act_badge_sm_defined(self):
        """.act-badge-sm variant must be defined in styles.css."""
        assert ".act-badge-sm {" in self.css or ".act-badge-sm{" in self.css, (
            ".act-badge-sm CSS class is not defined in styles.css"
        )

    def test_act_badge_sm_has_smaller_font_size(self):
        """.act-badge-sm must override font-size (smaller variant)."""
        sm_idx = self.css.find(".act-badge-sm {")
        if sm_idx == -1:
            sm_idx = self.css.find(".act-badge-sm{")
        assert sm_idx != -1
        rule_block = self.css[sm_idx: sm_idx + 200]
        assert "font-size" in rule_block, (
            ".act-badge-sm must override font-size to make a smaller variant"
        )


# ─── Criterion 21: pill-rule color rules removed; act-badge-sm.rule-* present ─

class TestPillRuleColorsReplaced:
    def setup_method(self):
        self.css = _read(STYLES_CSS)

    def test_no_standalone_pill_rule_color_rules(self):
        """styles.css must not define color rules on .pill-rule alone (superseded)."""
        # Old pattern was: .pill-rule.rule-buy, .pill-rule.rule-sell etc.
        # or .pill-rule { color: ...; background: ... }
        # These should be gone; the file should have .act-badge-sm.rule-* instead.
        bad_patterns = [
            r'\.pill-rule\.rule-buy\s*\{',
            r'\.pill-rule\.rule-sell\s*\{',
            r'\.pill-rule\.rule-neutral\s*\{',
            r'\.pill-rule\s*\{\s*(?:[^}]*(?:background|color)\s*:[^}]*)\}',
        ]
        for pat in bad_patterns:
            assert not re.search(pat, self.css), (
                f"Old pill-rule color rule still present in styles.css (pattern: {pat!r}). "
                "It should have been superseded by .act-badge-sm.rule-* rules."
            )

    def test_act_badge_sm_rule_buy_strong_defined(self):
        """.act-badge-sm.rule-buy.rule-strong must be defined in styles.css."""
        assert ".act-badge-sm.rule-buy.rule-strong" in self.css, (
            ".act-badge-sm.rule-buy.rule-strong not defined in styles.css "
            "(replaces old pill-rule.rule-buy color)"
        )

    def test_act_badge_sm_rule_sell_strong_defined(self):
        """.act-badge-sm.rule-sell.rule-strong must be defined in styles.css."""
        assert ".act-badge-sm.rule-sell.rule-strong" in self.css, (
            ".act-badge-sm.rule-sell.rule-strong not defined in styles.css"
        )

    def test_act_badge_sm_rule_neutral_defined(self):
        """.act-badge-sm.rule-neutral.rule-weak must be defined in styles.css."""
        assert ".act-badge-sm.rule-neutral" in self.css, (
            ".act-badge-sm.rule-neutral.* not defined in styles.css"
        )


# ─── Criterion 22: pill-rule interactive CSS preserved in actionable.html ─────

class TestPillRuleInteractivePreserved:
    def setup_method(self):
        self.html = _read(ACTIONABLE_HTML)

    def test_pill_rule_cursor_pointer_present(self):
        """.pill-rule cursor:pointer must still be defined in actionable.html."""
        style_match = re.search(r'<style[^>]*>(.*?)</style>', self.html, re.DOTALL)
        assert style_match, "No inline <style> block found in actionable.html"
        style_block = style_match.group(1)
        # Check pill-rule still has a cursor:pointer rule
        assert re.search(r'\.pill-rule\s*\{[^}]*cursor\s*:\s*pointer', style_block,
                         re.DOTALL), (
            ".pill-rule { cursor: pointer } must be preserved in actionable.html "
            "(modal fires pills rely on it for interactivity)"
        )

    def test_pill_rule_hover_state_present(self):
        """.pill-rule:hover must still be defined for interactive state."""
        style_match = re.search(r'<style[^>]*>(.*?)</style>', self.html, re.DOTALL)
        assert style_match
        style_block = style_match.group(1)
        assert ".pill-rule:hover" in style_block, (
            ".pill-rule:hover interactive state must remain in actionable.html"
        )

    def test_pill_rule_active_state_present(self):
        """.pill-rule.active must still be defined for click feedback."""
        style_match = re.search(r'<style[^>]*>(.*?)</style>', self.html, re.DOTALL)
        assert style_match
        style_block = style_match.group(1)
        assert ".pill-rule.active" in style_block, (
            ".pill-rule.active interactive state must remain in actionable.html"
        )

    def test_modal_fires_pills_still_use_pill_rule(self):
        """openDrilldown() modal fires pills must still carry 'pill-rule' class
        for their interactive cursor/hover/active CSS."""
        js = _read(ACTIONABLE_JS)
        od_body = _func_body(js, "openDrilldown", max_len=7000)
        fires_idx = od_body.find("modalFires")
        assert fires_idx != -1
        fires_section = od_body[fires_idx: fires_idx + 700]
        assert "pill-rule" in fires_section, (
            "Modal fires pills in openDrilldown() must still have 'pill-rule' class "
            "for cursor/hover/active interactivity (act-badge-sm provides shape, "
            "pill-rule provides behavior)"
        )


# ─── Criterion 23: Filter chips still present (not touched) ──────────────────

class TestFilterChipsUntouched:
    def setup_method(self):
        self.html = _read(ACTIONABLE_HTML)

    def test_act_chip_class_present(self):
        """act-chip CSS class must still be defined (filter chips unchanged)."""
        style_match = re.search(r'<style[^>]*>(.*?)</style>', self.html, re.DOTALL)
        assert style_match
        style_block = style_match.group(1)
        assert ".act-chip" in style_block, (
            ".act-chip CSS must still be defined — filter chips must not be changed"
        )

    def test_act_chip_remove_border_present(self):
        """act-chip-remove colored border must still be defined."""
        style_match = re.search(r'<style[^>]*>(.*?)</style>', self.html, re.DOTALL)
        assert style_match
        style_block = style_match.group(1)
        assert ".act-chip-remove" in style_block, (
            ".act-chip-remove must still be defined in actionable.html"
        )

    def test_summary_chips_div_present(self):
        """summaryChips element must still be in the HTML."""
        assert 'id="summaryChips"' in self.html, (
            "summaryChips element missing from actionable.html — filter chips broken"
        )


# ─── Criterion 24: No file truncation ────────────────────────────────────────

class TestNoTruncation:
    def test_actionable_js_ends_properly(self):
        """actionable.js must end with a valid closing brace (not mid-statement)."""
        js = _read(ACTIONABLE_JS)
        stripped = js.rstrip()
        # File must end with } (closing function/block)
        assert stripped.endswith("}"), (
            f"actionable.js appears truncated — last chars: {stripped[-40:]!r}"
        )

    def test_styles_css_ends_properly(self):
        """styles.css must end with a valid closing brace."""
        css = _read(STYLES_CSS)
        stripped = css.rstrip()
        assert stripped.endswith("}"), (
            f"styles.css appears truncated — last chars: {stripped[-40:]!r}"
        )

    def test_actionable_js_minimum_length(self):
        """actionable.js must be at least 50 000 chars (sanity check against wholesale wipe)."""
        js = _read(ACTIONABLE_JS)
        assert len(js) >= 50_000, (
            f"actionable.js is suspiciously short ({len(js)} chars) — possible truncation"
        )

    def test_styles_css_minimum_length(self):
        """styles.css must be at least 25 000 chars (sanity check)."""
        css = _read(STYLES_CSS)
        assert len(css) >= 25_000, (
            f"styles.css is suspiciously short ({len(css)} chars) — possible truncation"
        )


# ─── Criterion 25: No production Python files modified ───────────────────────

class TestNoPythonChanges:
    """Verify no API/ETL Python files contain act-badge references (JS-only change)."""

    def test_act_badge_not_in_python_files(self):
        """act-badge must not appear in any Python file (JS/CSS only)."""
        for py in API_DIR.rglob("*.py"):
            content = py.read_text(encoding="utf-8", errors="replace")
            assert "act-badge" not in content, (
                f"act-badge leaked into Python file: {py}"
            )

    def test_api_routers_dash_py_intact(self):
        """api/routers/dash.py must exist and not be empty."""
        dash = API_DIR / "routers" / "dash.py"
        assert dash.exists(), "api/routers/dash.py missing"
        content = dash.read_text(encoding="utf-8")
        assert len(content) > 100, "api/routers/dash.py appears truncated"

    def test_no_badge_action_in_python_files(self):
        """badge-action must not appear in any Python file."""
        for py in API_DIR.rglob("*.py"):
            content = py.read_text(encoding="utf-8", errors="replace")
            assert "badge-action" not in content, (
                f"badge-action leaked into Python file: {py}"
            )
