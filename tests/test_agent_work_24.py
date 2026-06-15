"""
Tests for AGENT_WORK_24 — Source-actions sub-line beneath main action badge
in the Actionable screen's Action column.

Acceptance criteria:
  1. node --check web/actionable.js passes (syntax OK).
  2. _srcSubLineHtml() exists in actionable.js.
  3. _srcSubLineHtml() reads source_actions (via _sourcesOf).
  4. _srcSubLineHtml() puts the winning source first (reads r.winning_source).
  5. _srcSubLineHtml() applies colorCls via actionDisplay() — not hardcoded.
  6. _srcSubLineHtml() uses muted label style (act-src-label).
  7. _srcSubLineHtml() returns '' when source_actions is empty/null (no stray separators).
  8. _srcSubLineHtml() is called inside the act-action-cell td after the main badge.
  9. _srcSubLineHtml() sorts non-winning sources by ACTION_RANK severity.
 10. CSS: .act-src-sub defined in styles.css with small font (9px), flex display, flex-wrap.
 11. CSS: .act-src-token defined in styles.css.
 12. CSS: .act-src-label defined in styles.css with muted grey color (#94a3b8).
 13. No Python/API files were modified by this change (frontend only).
 14. No new git commit was made (status check via git log comparison to known HEAD).
 15. Files are not truncated.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT  = Path(__file__).resolve().parent.parent
WEB_DIR       = PROJECT_ROOT / "web"
ACTIONABLE_JS = WEB_DIR / "actionable.js"
STYLES_CSS    = WEB_DIR / "styles.css"
API_DIR       = PROJECT_ROOT / "api"
ETL_DIR       = PROJECT_ROOT / "etl"


# ─── helpers ────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_body(src: str, func_name: str, max_len: int = 4000) -> str:
    """Return source text from 'function func_name' up to max_len chars."""
    idx = src.find(f"function {func_name}(")
    if idx == -1:
        idx = src.find(f"async function {func_name}(")
    assert idx != -1, f"{func_name}() not found in source"
    return src[idx: idx + max_len]


def _css_rule_block(css: str, selector: str, max_len: int = 300) -> str:
    """Return the CSS rule block text for a selector (from '{' to '}')."""
    idx = css.find(selector)
    assert idx != -1, f"CSS selector {selector!r} not found in styles.css"
    brace_open = css.find("{", idx)
    assert brace_open != -1
    brace_close = css.find("}", brace_open)
    assert brace_close != -1
    return css[brace_open: brace_close + 1]


# ─── Criterion 1: Syntax check ───────────────────────────────────────────────

class TestSyntaxCheck:
    def test_actionable_js_syntax(self):
        """node --check must pass with exit code 0."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"node --check failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )


# ─── Criterion 2: Function exists ────────────────────────────────────────────

class TestFunctionExists:
    def test_src_sub_line_html_defined(self):
        """_srcSubLineHtml must be defined as a function in actionable.js."""
        src = _read(ACTIONABLE_JS)
        assert "function _srcSubLineHtml(" in src, (
            "_srcSubLineHtml() is not defined in actionable.js"
        )


# ─── Criteria 3–9: _srcSubLineHtml() logic ───────────────────────────────────

class TestSrcSubLineHtmlLogic:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)
        self.body = _func_body(self.src, "_srcSubLineHtml", max_len=2000)

    def test_reads_source_actions_via_sources_of(self):
        """_srcSubLineHtml() must call _sourcesOf() to obtain source_actions."""
        assert "_sourcesOf(" in self.body, (
            "_srcSubLineHtml() must call _sourcesOf() to parse source_actions. "
            "Direct access to row.source_actions without _sourcesOf() is not acceptable."
        )

    def test_winning_source_first(self):
        """_srcSubLineHtml() must read r.winning_source to put winner first."""
        assert "winning_source" in self.body, (
            "_srcSubLineHtml() must reference r.winning_source to place winning source first"
        )

    def test_uses_action_display_for_color(self):
        """_srcSubLineHtml() must call actionDisplay() for color — not hardcoded."""
        assert "actionDisplay(" in self.body, (
            "_srcSubLineHtml() must call actionDisplay() to get the colorCls token. "
            "Do not hardcode hex colors inside the function."
        )

    def test_uses_color_cls(self):
        """_srcSubLineHtml() must use colorCls (token from actions.js)."""
        assert "colorCls" in self.body, (
            "_srcSubLineHtml() must use the colorCls property from actionDisplay()"
        )

    def test_uses_muted_label_class(self):
        """_srcSubLineHtml() must apply act-src-label for the muted source code."""
        assert "act-src-label" in self.body, (
            "_srcSubLineHtml() must use the 'act-src-label' CSS class for the grey source label"
        )

    def test_returns_empty_string_when_no_sources(self):
        """_srcSubLineHtml() must return '' when source_actions is empty/null."""
        # The guard pattern: if (!sources.length) return '';
        assert "return ''" in self.body or 'return ""' in self.body, (
            "_srcSubLineHtml() must return an empty string when there are no sources "
            "(no stray separators / empty sub-line rendered)"
        )

    def test_uses_action_rank_for_sort(self):
        """_srcSubLineHtml() must use ACTION_RANK to sort non-winning sources by severity."""
        assert "ACTION_RANK" in self.body, (
            "_srcSubLineHtml() must use ACTION_RANK to sort remaining sources by severity"
        )

    def test_escapes_html(self):
        """_srcSubLineHtml() must call escapeHtml() to protect source codes with special chars."""
        assert "escapeHtml(" in self.body, (
            "_srcSubLineHtml() must call escapeHtml() to escape source codes "
            "that may contain special HTML characters"
        )

    def test_returns_div_with_act_src_sub(self):
        """_srcSubLineHtml() must wrap output in a div.act-src-sub container."""
        assert "act-src-sub" in self.body, (
            "_srcSubLineHtml() must produce a <div class='act-src-sub'> wrapper"
        )

    def test_uses_act_src_token(self):
        """_srcSubLineHtml() must use act-src-token class for each individual token span."""
        assert "act-src-token" in self.body, (
            "_srcSubLineHtml() must use the 'act-src-token' CSS class for each source token"
        )


# ─── Criterion 8: Called inside act-action-cell td after main badge ───────────

class TestCallSite:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_called_inside_action_cell_td(self):
        """_srcSubLineHtml(r) call must appear inside the act-action-cell td markup."""
        # Find the act-action-cell td block in renderGrid
        cell_idx = self.src.find("act-action-cell")
        assert cell_idx != -1, "act-action-cell not found in actionable.js"
        # The call must follow the main badge within the same td block
        # Look for the pattern inside a reasonable window (2000 chars)
        cell_block = self.src[cell_idx: cell_idx + 2000]
        assert "_srcSubLineHtml(r)" in cell_block, (
            "_srcSubLineHtml(r) must be called inside the act-action-cell td block. "
            "It was not found within 2000 chars of 'act-action-cell'."
        )

    def test_called_after_main_badge(self):
        """_srcSubLineHtml(r) must appear after the main act-badge in the td."""
        cell_idx = self.src.find("act-action-cell")
        assert cell_idx != -1
        cell_block = self.src[cell_idx: cell_idx + 2000]
        badge_pos = cell_block.find("act-badge")
        sub_pos   = cell_block.find("_srcSubLineHtml(r)")
        assert badge_pos != -1, "Main act-badge not found in act-action-cell block"
        assert sub_pos   != -1, "_srcSubLineHtml(r) not found in act-action-cell block"
        assert sub_pos > badge_pos, (
            "_srcSubLineHtml(r) must appear AFTER the main act-badge in the cell markup, "
            f"but sub_pos ({sub_pos}) <= badge_pos ({badge_pos})"
        )

    def test_called_after_over_max_annotation(self):
        """_srcSubLineHtml(r) must appear after the OVER_MAX 'was X' annotation."""
        cell_idx = self.src.find("act-action-cell")
        assert cell_idx != -1
        cell_block = self.src[cell_idx: cell_idx + 2000]
        over_max_pos = cell_block.find("_isOverMaxOverlay")
        sub_pos      = cell_block.find("_srcSubLineHtml(r)")
        assert sub_pos != -1, "_srcSubLineHtml(r) not found in act-action-cell block"
        if over_max_pos != -1:
            assert sub_pos > over_max_pos, (
                "_srcSubLineHtml(r) must appear AFTER the OVER_MAX overlay annotation, "
                f"but sub_pos ({sub_pos}) <= over_max_pos ({over_max_pos})"
            )


# ─── Criteria 10–12: CSS classes ─────────────────────────────────────────────

class TestCssStyles:
    def setup_method(self):
        self.css = _read(STYLES_CSS)

    def test_act_src_sub_defined(self):
        """.act-src-sub must be defined as a CSS rule in styles.css."""
        assert ".act-src-sub" in self.css, (
            ".act-src-sub CSS class not found in styles.css"
        )

    def test_act_src_sub_font_size_9px(self):
        """.act-src-sub must set font-size to 9px (compact sub-line)."""
        block = _css_rule_block(self.css, ".act-src-sub")
        assert "9px" in block, (
            f".act-src-sub must set font-size:9px for the compact sub-line. "
            f"Rule block found: {block!r}"
        )

    def test_act_src_sub_display_flex(self):
        """.act-src-sub must use display:flex."""
        block = _css_rule_block(self.css, ".act-src-sub")
        assert "flex" in block, (
            f".act-src-sub must set display:flex. Rule block: {block!r}"
        )

    def test_act_src_sub_flex_wrap(self):
        """.act-src-sub must use flex-wrap for graceful wrapping in narrow columns."""
        block = _css_rule_block(self.css, ".act-src-sub")
        assert "flex-wrap" in block, (
            f".act-src-sub must set flex-wrap so tokens wrap in narrow Action columns. "
            f"Rule block: {block!r}"
        )

    def test_act_src_token_defined(self):
        """.act-src-token must be defined in styles.css."""
        assert ".act-src-token" in self.css, (
            ".act-src-token CSS class not found in styles.css"
        )

    def test_act_src_label_defined(self):
        """.act-src-label must be defined in styles.css."""
        assert ".act-src-label" in self.css, (
            ".act-src-label CSS class not found in styles.css"
        )

    def test_act_src_label_muted_color(self):
        """.act-src-label must use the muted grey color #94a3b8."""
        block = _css_rule_block(self.css, ".act-src-label")
        assert "#94a3b8" in block, (
            f".act-src-label must set color:#94a3b8 (muted grey) for the source code label. "
            f"Rule block: {block!r}"
        )


# ─── Criterion 13: Frontend-only (no Python/API changes from this task) ───────

class TestFrontendOnly:
    def test_new_function_not_in_python(self):
        """_srcSubLineHtml must not appear in any Python file."""
        for py in list(API_DIR.rglob("*.py")) + list(ETL_DIR.rglob("*.py")):
            content = py.read_text(encoding="utf-8", errors="replace")
            assert "_srcSubLineHtml" not in content, (
                f"_srcSubLineHtml leaked into Python file: {py}"
            )

    def test_act_src_sub_not_in_python(self):
        """act-src-sub class must not appear in any Python file (CSS/JS only)."""
        for py in list(API_DIR.rglob("*.py")) + list(ETL_DIR.rglob("*.py")):
            content = py.read_text(encoding="utf-8", errors="replace")
            assert "act-src-sub" not in content, (
                f"act-src-sub leaked into Python file: {py}"
            )


# ─── Criterion 14: No new commit was made ────────────────────────────────────

class TestNoCommit:
    def test_files_are_uncommitted(self):
        """actionable.js and styles.css must be in working-tree (not committed) state."""
        result = subprocess.run(
            ["git", "status", "--short", "web/actionable.js", "web/styles.css"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT)
        )
        assert result.returncode == 0, f"git status failed: {result.stderr}"
        output = result.stdout
        # Files should show as modified (' M' = staged/tracked-unstaged) — not '??' or empty
        # If both appear in git status --short they are NOT committed; if output is empty
        # they are clean (committed and unchanged).
        # We check that the most recent commit hash is b764d89 (pre-task commit)
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            capture_output=True, text=True, cwd=str(PROJECT_ROOT)
        )
        assert log_result.returncode == 0
        assert log_result.stdout.strip().startswith("b764d89"), (
            f"Expected HEAD to still be b764d89 (pre-task commit). "
            f"Current HEAD: {log_result.stdout.strip()!r} — a new commit may have been made."
        )


# ─── Criterion 15: File integrity / no truncation ────────────────────────────

class TestFileIntegrity:
    def test_actionable_js_ends_with_closing_brace(self):
        """actionable.js must end with a valid closing brace (not truncated)."""
        js = _read(ACTIONABLE_JS)
        stripped = js.rstrip()
        assert stripped.endswith("}"), (
            f"actionable.js appears truncated — last 40 chars: {stripped[-40:]!r}"
        )

    def test_styles_css_ends_with_closing_brace(self):
        """styles.css must end with a valid closing brace (not truncated)."""
        css = _read(STYLES_CSS)
        stripped = css.rstrip()
        assert stripped.endswith("}"), (
            f"styles.css appears truncated — last 40 chars: {stripped[-40:]!r}"
        )

    def test_actionable_js_minimum_length(self):
        """actionable.js must be at least 50 000 chars (sanity guard)."""
        js = _read(ACTIONABLE_JS)
        assert len(js) >= 50_000, (
            f"actionable.js is suspiciously short ({len(js)} chars)"
        )

    def test_styles_css_minimum_length(self):
        """styles.css must be at least 25 000 chars (sanity guard)."""
        css = _read(STYLES_CSS)
        assert len(css) >= 25_000, (
            f"styles.css is suspiciously short ({len(css)} chars)"
        )

    def test_src_sub_line_html_function_complete(self):
        """_srcSubLineHtml() function body must be complete (has a closing return)."""
        src = _read(ACTIONABLE_JS)
        body = _func_body(src, "_srcSubLineHtml", max_len=2000)
        # A complete function must have both 'return' statements
        return_count = body.count("return ")
        assert return_count >= 2, (
            f"_srcSubLineHtml() appears incomplete — only {return_count} return statement(s) "
            "found (expected at least 2: early-exit return '' and final return)"
        )
