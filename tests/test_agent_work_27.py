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


# ── Check A (REWRITTEN, TASK_112, 2026-07-04): Sources cell rendering ─────────
# _srcSubLineHtml() and _renderOtherSources() no longer exist in
# actionable.js (confirmed via grep — 0 matches for either name). The
# feature they implemented — colored, standardized per-source display in
# the Sources column — still exists, just consolidated into a single
# function, _srcReasonsHtml(r): it renders one always-visible reason line
# per source (winning source first, others by severity), each colored via
# actionIcon() rather than a compact actionText(actionDisplay()) subline +
# separate hover-triggered "other sources" pills. Rewritten against the
# current function/call site rather than retired, since the underlying
# behavior (standardized, colored, winner-first source breakdown in the
# Sources column) is unchanged — only the implementation shape moved.

class TestSrcReasonsHtml:
    def test_function_exists(self, js_text):
        """_srcReasonsHtml must be defined in actionable.js."""
        assert "function _srcReasonsHtml(" in js_text, (
            "_srcReasonsHtml function not found in actionable.js"
        )

    def test_called_in_render_grid_sources_cell(self, js_text):
        """_srcReasonsHtml(r) must be called inside renderGrid()'s Sources cell."""
        body = extract_function_body(js_text, "renderGrid")
        assert "_srcReasonsHtml(r)" in body, (
            "_srcReasonsHtml(r) is not called in renderGrid() — "
            "the Sources cell reason lines will never render"
        )

    def test_uses_sourcesOf(self, js_text):
        """_srcReasonsHtml must pull the row's parsed sources via _sourcesOf()."""
        body = extract_function_body(js_text, "_srcReasonsHtml")
        assert "_sourcesOf(" in body, (
            "_srcReasonsHtml() does not call _sourcesOf() — source_actions may not be parsed"
        )

    def test_winning_source_first(self, js_text):
        """The winning source must be placed first, others appended after (severity-sorted)."""
        body = extract_function_body(js_text, "_srcReasonsHtml")
        assert "winner.concat(others)" in body, (
            "_srcReasonsHtml() does not place the winning source first via winner.concat(others)"
        )

    def test_uses_actionIcon_for_color(self, js_text):
        """Each source's icon/color must come from actionIcon() (standardized palette)."""
        body = extract_function_body(js_text, "_srcReasonsHtml")
        assert "actionIcon(" in body, (
            "_srcReasonsHtml() does not call actionIcon() — source rows won't be color-coded"
        )

    def test_escapes_html(self, js_text):
        """Source tag and reason text must be escaped before insertion into the DOM."""
        body = extract_function_body(js_text, "_srcReasonsHtml")
        assert "escapeHtml(" in body, (
            "_srcReasonsHtml() does not escape source/reason text — XSS risk"
        )

    def test_returns_empty_string_when_no_sources(self, js_text):
        """No sources on the row -> the cell renders nothing."""
        body = extract_function_body(js_text, "_srcReasonsHtml")
        assert "if (!sources.length) return ''" in body, (
            "_srcReasonsHtml() does not short-circuit to '' when there are no sources"
        )

    def test_wraps_output_in_src_reasons_container(self, js_text):
        """Output must be wrapped in a .src-reasons container (styling hook)."""
        body = extract_function_body(js_text, "_srcReasonsHtml")
        assert 'class="src-reasons"' in body, (
            "_srcReasonsHtml() does not wrap its output in a .src-reasons container"
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

    def test_action_row_uses_tint_suffix(self, js_text):
        """_renderSourcePop must append a color-modifier suffix to colorCls for the badge
        background. REWRITTEN (TASK_112, 2026-07-04): the suffix is now '-tint' (was
        '-fill') — same standardized-badge-coloring behavior, different CSS naming."""
        body = extract_function_body(js_text, "_renderSourcePop")
        assert "-tint" in body, (
            "_renderSourcePop() does not use '-tint' suffix on colorCls — badge may be uncolored"
        )


# ── Check E: <th> elements have required attributes ───────────────────────────

class TestTwoLineHeaders:
    def test_sources_th_has_data_label(self, html_text):
        """Sources <th> must have data-label='Sources'."""
        assert 'data-label="Sources"' in html_text, (
            "Sources <th> is missing data-label='Sources'"
        )

    # test_sources_th_has_data_subtitle — RETIRED (TASK_112 test-debt cleanup,
    # 2026-07-04). The two-line header (data-subtitle + a visible
    # <div class="th-subtitle">) was superseded by a single-line header with
    # its detail moved into the `title=` tooltip instead (confirmed via grep:
    # 0 matches for `data-subtitle=` anywhere in actionable.html). Cat B —
    # superseded feature, not a renamed one; no data-subtitle to rewrite
    # against. test_sources_th_has_title below covers the tooltip that
    # replaced it.

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

    # test_sources_th_has_subtitle_div — RETIRED (TASK_112 test-debt cleanup,
    # 2026-07-04). Same superseded two-line-header feature as
    # test_sources_th_has_data_subtitle above — no <div class="th-subtitle">
    # is emitted anywhere in actionable.html anymore. Cat B.

    def test_technical_th_has_data_label(self, html_text):
        """Technical <th> must have data-label='Technical'."""
        assert 'data-label="Technical"' in html_text, (
            "Technical <th> is missing data-label='Technical'"
        )

    # test_technical_th_has_data_subtitle — RETIRED (TASK_112 test-debt
    # cleanup, 2026-07-04). Same superseded two-line-header feature — see
    # test_sources_th_has_data_subtitle above. Cat B.

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

    # test_technical_th_has_subtitle_div — RETIRED (TASK_112 test-debt
    # cleanup, 2026-07-04). Same superseded two-line-header feature — see
    # test_sources_th_has_subtitle_div above. Cat B.

    # test_subtitle_text_sources / test_subtitle_text_technical — RETIRED
    # (TASK_112 test-debt cleanup, 2026-07-04). Both asserted content of the
    # now-nonexistent data-subtitle attribute. The Sources tooltip text does
    # still convey the same "sourced + sized" meaning (see
    # test_sources_th_has_title / actual title text, which contains
    # "then sized to your min/max/holdings"), but the Technical tooltip's
    # replacement wording ("Trend-vs-Trade crossover + Bollinger range streak
    # + Risk-Range position") does not literally contain the TN/BB/RR
    # abbreviations the old subtitle used — those abbreviations now only
    # appear in the separate in-cell Technical sub-line (_rrSubLineHtml,
    # 'TnTd: '/'BB: '/'RR: ' prefixes), not the header. No clean 1:1 rewrite
    # target in the header text itself. Cat B.


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

    # test_emits_th_subtitle_div / test_reads_data_subtitle — RETIRED
    # (TASK_112 test-debt cleanup, 2026-07-04). Both asserted the two-line
    # header subtitle feature that TestTwoLineHeaders documents as
    # superseded above (0 matches for 'th-subtitle'/'data-subtitle' in
    # updateSortIndicators() or anywhere in actionable.html/js). Cat B.

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
