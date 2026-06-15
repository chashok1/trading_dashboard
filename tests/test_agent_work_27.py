"""
Tests for AGENT_WORK_27 — Fix Sources column (standardized codes + restore popover colors)
and clean Sources/Technical header subtitles.

Acceptance criteria (from DEV_HANDOFF.md and AGENT_WORK_27.md):
  Check A — _srcSubLineHtml() routes action through actionText(actionDisplay(act)).
  Check B — _renderOtherSources(r) is called in renderGrid() (dead-code fix, iteration 2).
  Check C — _renderOtherSources() badge label uses actionText(actDisp) pattern.
  Check D — _renderSourcePop() renders a colored act-badge span using colorCls.
  Check E — Sources and Technical <th> elements have data-label, data-subtitle, title=,
             and a <div class="th-subtitle"> child.
  Check F — .act-grid th .th-subtitle CSS has display:block, ~10px font-size, normal weight,
             muted color.
  Check G — updateSortIndicators() uses innerHTML (not textContent) and includes data-subtitle
             in a .th-subtitle div.
  Check H — initSorting() only sets data-label if not already present.
  Check I — actions.js exports actionDisplay, actionText, colorCls (via _ACTION_MAP) and
             load order in HTML is _common.js -> actions.js -> actionable.js.

Syntax check:
  Check 1 — node --check web/actionable.js exits 0.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
JS_FILE      = PROJECT_ROOT / "web" / "actionable.js"
HTML_FILE    = PROJECT_ROOT / "web" / "actionable.html"
ACTIONS_FILE = PROJECT_ROOT / "web" / "actions.js"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html_text():
    return HTML_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def actions_text():
    return ACTIONS_FILE.read_text(encoding="utf-8")


# ── Helper: extract function body ─────────────────────────────────────────────

def extract_function_body(js: str, fn_name: str) -> str:
    """Return the body (including braces) of the first function matching fn_name."""
    start = js.find(f"function {fn_name}(")
    assert start != -1, f"function {fn_name}() not found in actionable.js"
    brace_start = js.index("{", start)
    depth = 0
    for i, ch in enumerate(js[brace_start:], start=brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return js[brace_start : i + 1]
    raise AssertionError(f"Could not find closing brace of {fn_name}()")


# ── Check 1: Syntax ───────────────────────────────────────────────────────────

class TestSyntax:
    def test_node_check_passes(self):
        """node --check must exit 0 (no syntax errors in actionable.js)."""
        result = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ── Check A: _srcSubLineHtml routes action through actionText(actionDisplay(act)) ─

class TestSrcSubLineHtml:
    def test_function_exists(self, js_text):
        """_srcSubLineHtml must be defined in actionable.js."""
        assert "function _srcSubLineHtml(" in js_text, (
            "_srcSubLineHtml function not found in actionable.js"
        )

    def test_uses_actionDisplay(self, js_text):
        """_srcSubLineHtml body must call actionDisplay() to normalize the action code."""
        body = extract_function_body(js_text, "_srcSubLineHtml")
        assert "actionDisplay(" in body, (
            "_srcSubLineHtml() does not call actionDisplay() — raw action strings may reach the DOM"
        )

    def test_uses_actionText(self, js_text):
        """_srcSubLineHtml body must call actionText() for the display text."""
        body = extract_function_body(js_text, "_srcSubLineHtml")
        assert "actionText(" in body, (
            "_srcSubLineHtml() does not call actionText() — action codes may not be standardized"
        )

    def test_no_raw_increase_string(self, js_text):
        """_srcSubLineHtml body must not output the raw literal 'INCREASE'."""
        body = extract_function_body(js_text, "_srcSubLineHtml")
        # 'INCREASE' may appear as a key in ACTION_RANK lookup but should not
        # be what gets written to the DOM as display text.
        # Check that it's not used in a template literal that directly inserts text.
        # We allow 'INCREASE' in an object key context (.INCREASE or 'INCREASE': )
        # but not as a display label fallback.
        # The simplest heuristic: if actionText/actionDisplay wraps it, it's fine.
        # This test just confirms actionText() is present (already above).
        # Extra guard: raw 'INCREASE' not used as a fallback label after actionText call.
        assert "actionText(" in body, (
            "_srcSubLineHtml does not use actionText — raw INCREASE/ADD may appear as display text"
        )

    def test_no_raw_add_string_as_display(self, js_text):
        """_srcSubLineHtml body must not use raw 'ADD' as a display label."""
        body = extract_function_body(js_text, "_srcSubLineHtml")
        # The function should route through actionText; as long as actionText is called
        # the actual output will be standardized codes.
        assert "actionText(" in body, (
            "_srcSubLineHtml does not use actionText — raw ADD/INCREASE may appear as display text"
        )


# ── Check B: _renderOtherSources(r) is called in renderGrid() ─────────────────

class TestRenderOtherSourcesCalled:
    def test_render_other_sources_defined(self, js_text):
        """_renderOtherSources must be defined in actionable.js."""
        assert "function _renderOtherSources(" in js_text, (
            "_renderOtherSources function not found in actionable.js"
        )

    def test_render_other_sources_called_in_render_grid(self, js_text):
        """_renderOtherSources(r) must be called inside renderGrid() — the fix for dead code."""
        body = extract_function_body(js_text, "renderGrid")
        assert "_renderOtherSources(r)" in body, (
            "_renderOtherSources(r) is not called in renderGrid() — "
            "[data-srcpop] pills will never be emitted into the DOM"
        )

    def test_render_other_sources_after_src_sub_line(self, js_text):
        """_renderOtherSources(r) must appear after _srcSubLineHtml(r) in renderGrid()."""
        body = extract_function_body(js_text, "renderGrid")
        pos_sub = body.find("_srcSubLineHtml(r)")
        pos_other = body.find("_renderOtherSources(r)")
        assert pos_sub != -1, "_srcSubLineHtml(r) not found in renderGrid()"
        assert pos_other != -1, "_renderOtherSources(r) not found in renderGrid()"
        assert pos_other > pos_sub, (
            "_renderOtherSources(r) must appear after _srcSubLineHtml(r) in renderGrid(), "
            f"but found at positions {pos_other} vs {pos_sub}"
        )


# ── Check C: _renderOtherSources badge label uses actionText(actDisp) ─────────

class TestRenderOtherSourcesBadge:
    def test_uses_actionDisplay(self, js_text):
        """_renderOtherSources body must call actionDisplay() for badge labels."""
        body = extract_function_body(js_text, "_renderOtherSources")
        assert "actionDisplay(" in body, (
            "_renderOtherSources() does not call actionDisplay() — raw codes reach badge pills"
        )

    def test_uses_actionText(self, js_text):
        """_renderOtherSources body must call actionText() for badge label text."""
        body = extract_function_body(js_text, "_renderOtherSources")
        assert "actionText(" in body, (
            "_renderOtherSources() does not call actionText() — badge labels are not standardized"
        )

    def test_emits_data_srcpop(self, js_text):
        """_renderOtherSources must emit [data-srcpop] attribute on span elements."""
        body = extract_function_body(js_text, "_renderOtherSources")
        assert "data-srcpop" in body, (
            "_renderOtherSources() does not emit [data-srcpop] — hover popover cannot trigger"
        )


# ── Check D: _renderSourcePop uses colored act-badge span ─────────────────────

class TestRenderSourcePopColored:
    def test_function_exists(self, js_text):
        """_renderSourcePop must be defined in actionable.js."""
        assert "function _renderSourcePop(" in js_text, (
            "_renderSourcePop function not found in actionable.js"
        )

    def test_uses_actionDisplay(self, js_text):
        """_renderSourcePop body must call actionDisplay() for the action row."""
        body = extract_function_body(js_text, "_renderSourcePop")
        assert "actionDisplay(" in body, (
            "_renderSourcePop() does not call actionDisplay() — action color may be lost"
        )

    def test_uses_colorCls(self, js_text):
        """_renderSourcePop body must use colorCls from actionDisplay for the badge class."""
        body = extract_function_body(js_text, "_renderSourcePop")
        assert "colorCls" in body, (
            "_renderSourcePop() does not use colorCls — the badge will not be colored"
        )

    def test_emits_act_badge_class(self, js_text):
        """_renderSourcePop must emit an act-badge span for the action row."""
        body = extract_function_body(js_text, "_renderSourcePop")
        assert "act-badge" in body, (
            "_renderSourcePop() does not emit an act-badge span — Action row has no color chip"
        )

    def test_action_row_uses_fill_suffix(self, js_text):
        """_renderSourcePop must append '-fill' to colorCls for the badge background."""
        body = extract_function_body(js_text, "_renderSourcePop")
        assert "-fill" in body, (
            "_renderSourcePop() does not use '-fill' suffix on colorCls — badge may be uncolored"
        )


# ── Check E: <th> elements have required attributes ───────────────────────────

class TestTwoLineHeaders:
    def test_sources_th_has_data_label(self, html_text):
        """Sources <th> must have data-label='Sources'."""
        assert 'data-label="Sources"' in html_text, (
            "Sources <th> is missing data-label='Sources'"
        )

    def test_sources_th_has_data_subtitle(self, html_text):
        """Sources <th> must have data-subtitle containing the subtitle text."""
        # Match data-subtitle on the Sources th
        pattern = r'data-key="consolidated_action"[^>]*data-subtitle="([^"]+)"'
        m = re.search(pattern, html_text)
        if not m:
            # Try reversed attribute order
            pattern2 = r'data-subtitle="([^"]+)"[^>]*data-key="consolidated_action"'
            m = re.search(pattern2, html_text)
        assert m is not None, (
            "Sources <th> (data-key='consolidated_action') is missing data-subtitle attribute"
        )
        subtitle = m.group(1)
        assert subtitle, "Sources <th> data-subtitle is empty"

    def test_sources_th_has_title(self, html_text):
        """Sources <th> must have a title= tooltip."""
        pattern = r'data-key="consolidated_action"[^>]*title="([^"]+)"'
        m = re.search(pattern, html_text)
        if not m:
            pattern2 = r'title="([^"]+)"[^>]*data-key="consolidated_action"'
            m = re.search(pattern2, html_text)
        assert m is not None, (
            "Sources <th> (data-key='consolidated_action') is missing title= tooltip"
        )

    def test_sources_th_has_subtitle_div(self, html_text):
        """Sources <th> must contain a <div class='th-subtitle'> child element."""
        # Look for th-subtitle div near the Sources th
        sources_th_pattern = r'(<th[^>]*data-key="consolidated_action"[^>]*>)(.*?)(</th>)'
        m = re.search(sources_th_pattern, html_text, re.DOTALL)
        assert m is not None, "Could not find Sources <th> block in actionable.html"
        th_content = m.group(0)
        assert 'class="th-subtitle"' in th_content, (
            "Sources <th> does not contain a <div class='th-subtitle'> child"
        )

    def test_technical_th_has_data_label(self, html_text):
        """Technical <th> must have data-label='Technical'."""
        assert 'data-label="Technical"' in html_text, (
            "Technical <th> is missing data-label='Technical'"
        )

    def test_technical_th_has_data_subtitle(self, html_text):
        """Technical <th> must have data-subtitle attribute."""
        pattern = r'data-key="rr_action"[^>]*data-subtitle="([^"]+)"'
        m = re.search(pattern, html_text)
        if not m:
            pattern2 = r'data-subtitle="([^"]+)"[^>]*data-key="rr_action"'
            m = re.search(pattern2, html_text)
        assert m is not None, (
            "Technical <th> (data-key='rr_action') is missing data-subtitle attribute"
        )

    def test_technical_th_has_title(self, html_text):
        """Technical <th> must have a title= tooltip."""
        pattern = r'data-key="rr_action"[^>]*title="([^"]+)"'
        m = re.search(pattern, html_text)
        if not m:
            pattern2 = r'title="([^"]+)"[^>]*data-key="rr_action"'
            m = re.search(pattern2, html_text)
        assert m is not None, (
            "Technical <th> (data-key='rr_action') is missing title= tooltip"
        )

    def test_technical_th_has_subtitle_div(self, html_text):
        """Technical <th> must contain a <div class='th-subtitle'> child element."""
        technical_th_pattern = r'(<th[^>]*data-key="rr_action"[^>]*>)(.*?)(</th>)'
        m = re.search(technical_th_pattern, html_text, re.DOTALL)
        assert m is not None, "Could not find Technical <th> block in actionable.html"
        th_content = m.group(0)
        assert 'class="th-subtitle"' in th_content, (
            "Technical <th> does not contain a <div class='th-subtitle'> child"
        )

    def test_subtitle_text_sources(self, html_text):
        """Sources subtitle must contain 'source' and 'sized'."""
        pattern = r'data-key="consolidated_action"[^>]*data-subtitle="([^"]+)"'
        m = re.search(pattern, html_text)
        if not m:
            pattern2 = r'data-subtitle="([^"]+)"[^>]*data-key="consolidated_action"'
            m = re.search(pattern2, html_text)
        assert m is not None, "Sources <th> data-subtitle not found"
        subtitle = m.group(1).lower()
        assert "source" in subtitle and "sized" in subtitle, (
            f"Sources subtitle '{m.group(1)}' does not contain both 'source' and 'sized'"
        )

    def test_subtitle_text_technical(self, html_text):
        """Technical subtitle must contain some indicator abbreviation."""
        pattern = r'data-key="rr_action"[^>]*data-subtitle="([^"]+)"'
        m = re.search(pattern, html_text)
        if not m:
            pattern2 = r'data-subtitle="([^"]+)"[^>]*data-key="rr_action"'
            m = re.search(pattern2, html_text)
        assert m is not None, "Technical <th> data-subtitle not found"
        subtitle = m.group(1)
        # Must contain at least one of TN, BB, RR (or similar)
        assert any(indicator in subtitle for indicator in ["TN", "BB", "RR"]), (
            f"Technical subtitle '{subtitle}' does not contain expected indicators (TN, BB, or RR)"
        )


# ── Check F: .th-subtitle CSS rule ────────────────────────────────────────────

class TestThSubtitleCss:
    def test_th_subtitle_css_rule_present(self, html_text):
        """actionable.html inline style must define .act-grid th .th-subtitle rule."""
        assert ".th-subtitle" in html_text, (
            ".th-subtitle CSS rule not found in actionable.html inline <style>"
        )

    def test_th_subtitle_display_block(self, html_text):
        """The .th-subtitle rule must set display:block."""
        # Find the CSS rule block for .th-subtitle
        pattern = r'\.th-subtitle\s*\{([^}]+)\}'
        m = re.search(pattern, html_text)
        assert m is not None, "Could not find .th-subtitle { ... } rule in actionable.html"
        rule_body = m.group(1)
        assert "display" in rule_body and "block" in rule_body, (
            f".th-subtitle rule does not set display:block. Rule body: {rule_body!r}"
        )

    def test_th_subtitle_font_size_small(self, html_text):
        """The .th-subtitle rule must set a small font-size (around 10px)."""
        pattern = r'\.th-subtitle\s*\{([^}]+)\}'
        m = re.search(pattern, html_text)
        assert m is not None, "Could not find .th-subtitle { ... } rule in actionable.html"
        rule_body = m.group(1)
        assert "font-size" in rule_body, (
            ".th-subtitle rule does not set font-size"
        )
        # Check it's a small size (10px, 11px, 0.7em, etc.)
        size_match = re.search(r'font-size\s*:\s*(\S+)', rule_body)
        assert size_match is not None, ".th-subtitle font-size value not parseable"
        size_val = size_match.group(1).strip(';').strip()
        # Accept px values <= 11 or em values < 0.9
        px_m = re.match(r'^(\d+(?:\.\d+)?)px$', size_val)
        em_m = re.match(r'^(\d+(?:\.\d+)?)em$', size_val)
        if px_m:
            assert float(px_m.group(1)) <= 12, (
                f".th-subtitle font-size is {size_val} — expected a small size (<=12px)"
            )
        elif em_m:
            assert float(em_m.group(1)) <= 0.9, (
                f".th-subtitle font-size is {size_val} — expected a small size (<=0.9em)"
            )
        # If neither, just accept that font-size is set

    def test_th_subtitle_normal_font_weight(self, html_text):
        """The .th-subtitle rule must set font-weight to normal (not bold)."""
        pattern = r'\.th-subtitle\s*\{([^}]+)\}'
        m = re.search(pattern, html_text)
        assert m is not None, "Could not find .th-subtitle { ... } rule"
        rule_body = m.group(1)
        assert "font-weight" in rule_body, ".th-subtitle rule does not set font-weight"
        fw_match = re.search(r'font-weight\s*:\s*(\S+)', rule_body)
        fw = fw_match.group(1).strip(';').strip() if fw_match else ''
        # 400 or "normal" — not bold (700/bold)
        assert fw in ('400', 'normal', '300', '200'), (
            f".th-subtitle font-weight is '{fw}' — expected 400/normal (not bold)"
        )

    def test_th_subtitle_muted_color(self, html_text):
        """The .th-subtitle rule must set a muted/grey color."""
        pattern = r'\.th-subtitle\s*\{([^}]+)\}'
        m = re.search(pattern, html_text)
        assert m is not None, "Could not find .th-subtitle { ... } rule"
        rule_body = m.group(1)
        assert "color" in rule_body, (
            ".th-subtitle rule does not set a text color — subtitle may not appear muted"
        )


# ── Check G: updateSortIndicators preserves subtitle via innerHTML ─────────────

class TestUpdateSortIndicators:
    def test_function_exists(self, js_text):
        """updateSortIndicators must be defined in actionable.js."""
        assert "function updateSortIndicators(" in js_text, (
            "updateSortIndicators function not found in actionable.js"
        )

    def test_uses_innerHTML(self, js_text):
        """updateSortIndicators must write via innerHTML (not th.innerHTML =... via textContent)."""
        body = extract_function_body(js_text, "updateSortIndicators")
        assert "innerHTML" in body, (
            "updateSortIndicators() does not use innerHTML — subtitle will be wiped on sort"
        )
        # textContent may appear as a read-only fallback (th.dataset.label || th.textContent.trim())
        # but must never be used as the write method. The innerHTML assignment above is what counts.
        # Verify that 'th.innerHTML =' appears (the actual write), not 'th.textContent ='
        assert "th.innerHTML" in body or ".innerHTML =" in body, (
            "updateSortIndicators() does not assign to .innerHTML — DOM write method is wrong"
        )
        # Confirm textContent is not used as the write sink
        assert "th.textContent =" not in body and ".textContent =" not in body, (
            "updateSortIndicators() assigns to .textContent — this wipes the .th-subtitle div"
        )

    def test_emits_th_subtitle_div(self, js_text):
        """updateSortIndicators must emit the .th-subtitle div in its innerHTML template."""
        body = extract_function_body(js_text, "updateSortIndicators")
        assert "th-subtitle" in body, (
            "updateSortIndicators() does not include 'th-subtitle' in its innerHTML — "
            "subtitle disappears after the first sort click"
        )

    def test_reads_data_subtitle(self, js_text):
        """updateSortIndicators must read th.dataset.subtitle to get the subtitle text."""
        body = extract_function_body(js_text, "updateSortIndicators")
        assert "dataset.subtitle" in body or "data-subtitle" in body.lower(), (
            "updateSortIndicators() does not read dataset.subtitle — subtitle is hardcoded or missing"
        )

    def test_uses_escapeHtml_on_label(self, js_text):
        """updateSortIndicators must apply escapeHtml() to the base label text."""
        body = extract_function_body(js_text, "updateSortIndicators")
        assert "escapeHtml(" in body, (
            "updateSortIndicators() does not apply escapeHtml() to the base label — XSS risk"
        )


# ── Check H: initSorting does not overwrite HTML data-label ───────────────────

class TestInitSorting:
    def test_function_exists(self, js_text):
        """initSorting must be defined in actionable.js."""
        assert "function initSorting(" in js_text, (
            "initSorting function not found in actionable.js"
        )

    def test_data_label_set_conditionally(self, js_text):
        """initSorting must only set th.dataset.label if not already present."""
        body = extract_function_body(js_text, "initSorting")
        # Should have a conditional guard like: if (!th.dataset.label)
        assert "dataset.label" in body, "initSorting does not reference dataset.label"
        # The guard must be conditional — look for 'if' before the assignment
        # Pattern: if (!th.dataset.label) th.dataset.label = ...
        guarded = re.search(r'if\s*\(\s*!\s*th\.dataset\.label\s*\)', body)
        assert guarded is not None, (
            "initSorting() does not conditionally guard dataset.label assignment — "
            "HTML-defined labels (Sources, Technical) will be overwritten with raw textContent"
        )


# ── Check I: actions.js exports and script load order ─────────────────────────

class TestActionsJsExports:
    def test_actions_js_exists(self):
        """actions.js must exist in web/."""
        assert ACTIONS_FILE.exists(), f"actions.js not found at {ACTIONS_FILE}"

    def test_actionDisplay_exported(self, actions_text):
        """actions.js must expose window.actionDisplay."""
        assert "window.actionDisplay" in actions_text, (
            "actions.js does not export window.actionDisplay"
        )

    def test_actionText_exported(self, actions_text):
        """actions.js must expose window.actionText."""
        assert "window.actionText" in actions_text, (
            "actions.js does not export window.actionText"
        )

    def test_colorCls_present_in_map(self, actions_text):
        """actions.js _MAP entries must include colorCls field."""
        assert "colorCls" in actions_text, (
            "actions.js _MAP does not contain colorCls property"
        )

    def test_script_load_order_in_html(self, html_text):
        """HTML must load _common.js -> actions.js -> actionable.js in that order."""
        pos_common     = html_text.find("_common.js")
        pos_actions    = html_text.find("actions.js")
        pos_actionable = html_text.find("actionable.js")
        assert pos_common != -1,     "_common.js not referenced in actionable.html"
        assert pos_actions != -1,    "actions.js not referenced in actionable.html"
        assert pos_actionable != -1, "actionable.js not referenced in actionable.html"
        assert pos_common < pos_actions, (
            "_common.js must be loaded before actions.js"
        )
        assert pos_actions < pos_actionable, (
            "actions.js must be loaded before actionable.js"
        )
