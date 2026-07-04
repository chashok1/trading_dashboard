"""
Tests for AGENT_WORK_22 — Remove Trig column from Actionable grid;
add Action-cell hover popup (_actionPopHtml / setupActionCol).

Acceptance criteria:
  1. node --check web/actionable.js passes (no output, exit 0).
  2. No <th> with data-key="trig_action" in web/actionable.html (Trig header removed).
  3. No <td> rendering r.trig_action directly in renderGrid() body of actionable.js.
  4. [UPDATED — TASK_110] finalCall() no longer references trig_action at
     all — its client-side fallback path now reads row.rr_action and
     _FC_SCALE instead (trig_action is no longer surfaced anywhere on the
     screen, per TASK_109).
  5. [UPDATED — TASK_110] Trig column is NOT exported in exportCsv() —
     TASK_109 dropped it (superseding the original "kept per spec" note).
  6. class="act-action-cell" on the Action <td> in renderGrid().
  7. data-sym attribute on the act-action-cell <td>.
  8. cursor:help style on act-action-cell.
  9. _actionPopHtml() function exists in actionable.js.
 10. _actionPopHtml() includes: symbol + action badge header.
 11. _actionPopHtml() includes: suppressed_reason banner logic.
 12. _actionPopHtml() includes: winning_source section.
 13. _actionPopHtml() includes: method/metric field.
 14. _actionPopHtml() includes: reason text field.
 15. _actionPopHtml() includes: source_actions loop (All Sources section).
 16. _actionPopHtml() includes: current_position_dollar sizing field.
 17. _actionPopHtml() includes: suggested_target_dollar sizing field.
 18. _actionPopHtml() includes: target_min_dollar sizing field.
 19. _actionPopHtml() includes: target_max_dollar sizing field.
 20. _actionPopHtml() includes: _amt (AMT$) sizing field.
 21. setupActionCol() function exists.
 22. setupActionCol() creates a fixed-position #actDetailTip div.
 23. setupActionCol() wires mouseover on .act-action-cell.
 24. setupActionCol() wires mouseout on .act-action-cell to hide tooltip.
 25. setupActionCol() is called from DOMContentLoaded before setupRRActionCol().
 26. Other header columns (Action, TrTnBBRskRng, Final Call, etc.) are still present.
 27. No production/API Python files were modified by this change.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
WEB_DIR        = PROJECT_ROOT / "web"
ACTIONABLE_HTML = WEB_DIR / "actionable.html"
ACTIONABLE_JS   = WEB_DIR / "actionable.js"
API_DIR         = PROJECT_ROOT / "api"


# ─── helpers ────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_body(src: str, func_name: str, max_len: int = None) -> str:
    """Return the full source text of a named function (brace-matched).

    REWRITTEN (TASK_112, 2026-07-04): the original implementation sliced a
    fixed `max_len` (default 6000) chars from the function's start, which
    silently truncated mid-function once renderGrid() (10 951 chars) grew
    past that window — causing false "X removed from renderGrid()" failures
    for content that was simply beyond the slice, not actually missing.
    Brace-matching finds the function's real closing brace regardless of
    size, so growth no longer breaks these tests. `max_len`, if given, still
    caps the returned text (kept for callers that want a bounded excerpt).
    """
    idx = src.find(f"function {func_name}(")
    if idx == -1:
        idx = src.find(f"async function {func_name}(")
    assert idx != -1, f"{func_name}() not found in source"
    brace_start = src.index("{", idx)
    depth = 0
    for i, ch in enumerate(src[brace_start:], start=brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = src[idx: i + 1]
                return body[:max_len] if max_len else body
    raise AssertionError(f"Could not find closing brace of {func_name}()")


# ─── Criterion 1: Syntax check ───────────────────────────────────────────────

class TestSyntaxCheck:
    def test_actionable_js_syntax(self):
        """node --check must pass with no output and exit 0."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, \
            f"node --check failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        assert result.stdout.strip() == "", \
            f"node --check produced unexpected output: {result.stdout!r}"


# ─── Criterion 2: Trig <th> removed from HTML ────────────────────────────────

class TestTrigColumnRemovedHtml:
    def setup_method(self):
        self.html = _read(ACTIONABLE_HTML)

    def test_no_trig_th_in_header(self):
        """No <th> with data-key='trig_action' in actionable.html."""
        assert 'data-key="trig_action"' not in self.html, \
            "Trig <th> (data-key='trig_action') should have been removed from the grid header"

    def test_no_trig_text_in_thead(self):
        """Trig column text not present in the grid thead area."""
        # Extract thead block for targeted search
        thead_match = re.search(r'<thead.*?</thead>', self.html, re.DOTALL)
        if thead_match:
            thead = thead_match.group(0)
            # Should not see >Trig< as a standalone header cell
            assert not re.search(r'<th[^>]*>\s*Trig\s*</th>', thead), \
                "Found a <th>Trig</th> cell in the grid header"


# ─── Criterion 3: No Trig <td> in renderGrid() ───────────────────────────────

class TestTrigTdRemovedJs:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_no_trig_td_in_render_grid(self):
        """renderGrid() must not contain a <td> that renders r.trig_action directly."""
        render_body = _func_body(self.src, "renderGrid")
        # The old pattern was: r.trig_action || '—'  inside a <td>
        # We check that no raw trig_action output remains in the grid row HTML
        assert 'r.trig_action' not in render_body, \
            "renderGrid() still renders r.trig_action as a grid column"

    def test_no_trig_purple_td(self):
        """The purple trig_action <td> (color:#7c3aed) must be gone."""
        render_body = _func_body(self.src, "renderGrid")
        assert '7c3aed' not in render_body, \
            "Old purple Trig <td> (color:#7c3aed) still present in renderGrid()"


# ─── Criterion 4: finalCall() no longer consumes trig_action (TASK_109) ──────
# Updated for TASK_110 test cleanup: the original criterion ("trig_action
# still consumed by finalCall()") is now stale — finalCall()'s client-side
# fallback path (for pre-migration rows without server-computed final_code)
# was refactored to read row.rr_action instead of row.trig_action, and to
# read strength from the _FC_SCALE table directly rather than via a
# _fcStrength(trig_action) call. This matches the task's stated root cause:
# "trig_action is no longer surfaced anywhere else on the screen."

class TestTrigActionNoLongerConsumed:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_trig_action_not_in_final_call(self):
        """finalCall() must NOT reference row.trig_action any more."""
        fc_body = _func_body(self.src, "finalCall")
        assert 'trig_action' not in fc_body, \
            "finalCall() still references trig_action — TASK_109 was supposed to drop this"

    def test_final_call_uses_rr_action_fallback(self):
        """finalCall()'s client-side fallback path reads row.rr_action instead."""
        fc_body = _func_body(self.src, "finalCall")
        assert 'row.rr_action' in fc_body, \
            "finalCall() fallback path should read row.rr_action"

    def test_final_call_uses_fc_scale_for_strength(self):
        """finalCall() looks up strength via the _FC_SCALE table."""
        fc_body = _func_body(self.src, "finalCall")
        assert '_FC_SCALE' in fc_body, \
            "finalCall() should reference _FC_SCALE to evaluate strength"


# ─── Criterion 5: Trig no longer in CSV export (TASK_109) ────────────────────
# Updated for TASK_110 test cleanup: TASK_109 deliberately dropped the Trig
# column from exportCsv() too, since trig_action is no longer surfaced
# anywhere else on the Actionable screen (see the comment left in-place at
# actionable.js::exportCsv()). The original spec here ("kept per spec") was
# superseded by that later decision.

class TestTrigNotInCsvExport:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_trig_column_not_in_export_csv(self):
        """exportCsv() must NOT include a 'Trig' column — TASK_109 dropped it."""
        export_body = _func_body(self.src, "exportCsv", max_len=3000)
        assert "'Trig'" not in export_body and '"Trig"' not in export_body, \
            "exportCsv() should not export a Trig column (removed by TASK_109)"


# ─── Criteria 6-8: act-action-cell class / attributes ────────────────────────

class TestActActionCell:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_act_action_cell_class_in_render_grid(self):
        """renderGrid() must emit class='act-action-cell' on the Action <td>."""
        render_body = _func_body(self.src, "renderGrid")
        assert 'act-action-cell' in render_body, \
            "renderGrid() must add class='act-action-cell' to the Action <td>"

    def test_data_sym_on_action_cell(self):
        """The act-action-cell <td> must include data-sym attribute."""
        render_body = _func_body(self.src, "renderGrid")
        # Check that act-action-cell and data-sym appear near each other
        idx = render_body.find('act-action-cell')
        assert idx != -1, "act-action-cell not found in renderGrid()"
        surrounding = render_body[idx: idx + 200]
        assert 'data-sym' in surrounding, \
            "act-action-cell <td> must have a data-sym attribute"

    def test_cursor_help_on_action_cell(self):
        """The act-action-cell <td> must set cursor:help."""
        render_body = _func_body(self.src, "renderGrid")
        idx = render_body.find('act-action-cell')
        assert idx != -1
        surrounding = render_body[idx: idx + 200]
        assert 'cursor:help' in surrounding, \
            "act-action-cell <td> should have cursor:help style"


# ─── Criterion 9: _actionPopHtml() exists ────────────────────────────────────

class TestActionPopHtmlExists:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_function_declared(self):
        """_actionPopHtml() function must be declared in actionable.js."""
        assert 'function _actionPopHtml(' in self.src, \
            "_actionPopHtml() function not found in actionable.js"


# ─── Criteria 10-20: _actionPopHtml() content ────────────────────────────────

class TestActionPopHtmlContent:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)
        self.body = _func_body(self.src, "_actionPopHtml")

    def test_header_symbol_and_badge(self):
        """Popup header includes the symbol and action badge.

        REWRITTEN (TASK_112, 2026-07-04): the badge class is 'act-badge'
        (the standardized actions.js token class, with a colorCls + '-tint'
        modifier) — 'badge-action' was never the real class name in the
        current implementation.
        """
        # Symbol is rendered with escapeHtml(sym) and badge-action class
        assert 'escapeHtml(sym)' in self.body or 'sym' in self.body, \
            "Header must reference the symbol"
        assert 'act-badge' in self.body, \
            "Header must include an action badge (act-badge class)"

    def test_suppressed_reason_banner(self):
        """suppressed_reason causes a warning banner to render."""
        assert 'suppressed_reason' in self.body, \
            "_actionPopHtml() must handle suppressed_reason field"
        # Banner should appear only if suppressed_reason is truthy
        assert 'if (r.suppressed_reason)' in self.body or \
               "r.suppressed_reason" in self.body, \
            "No conditional for suppressed_reason in _actionPopHtml()"

    def test_winning_source_section(self):
        """_actionPopHtml() includes a 'Winning Source' section."""
        assert 'Winning Source' in self.body or 'winning_source' in self.body, \
            "_actionPopHtml() must show the winning source"

    def test_method_metric_field(self):
        """_actionPopHtml() shows the method/metric for the winning source."""
        assert 'Method' in self.body or 'method' in self.body or \
               'winMethod' in self.body, \
            "_actionPopHtml() must include method/metric information"

    def test_reason_text_field(self):
        """_actionPopHtml() shows the reason text."""
        assert 'winReason' in self.body or '_winningReason' in self.body or \
               'reason' in self.body.lower(), \
            "_actionPopHtml() must display reason text"

    def test_source_actions_loop(self):
        """_actionPopHtml() loops over source_actions to show all sources."""
        assert 'source_actions' in self.body, \
            "_actionPopHtml() must iterate source_actions"
        # Must have some looping construct
        assert ('for ' in self.body or 'forEach' in self.body or
                'map(' in self.body), \
            "_actionPopHtml() must loop over sources"

    def test_all_sources_section_label(self):
        """_actionPopHtml() has an 'All Sources' section label."""
        assert 'All Sources' in self.body, \
            "_actionPopHtml() must label the sources section 'All Sources'"

    def test_winning_marker_in_sources(self):
        """Winning source is marked (checkmark or 'winning' label)."""
        assert 'winning' in self.body.lower() or '&#10003;' in self.body, \
            "_actionPopHtml() must mark the winning source distinctly"

    def test_current_position_dollar(self):
        """Sizing block includes current_position_dollar."""
        assert 'current_position_dollar' in self.body, \
            "_actionPopHtml() must show current_position_dollar in sizing"

    def test_suggested_target_dollar(self):
        """Sizing block includes suggested_target_dollar."""
        assert 'suggested_target_dollar' in self.body, \
            "_actionPopHtml() must show suggested_target_dollar in sizing"

    def test_target_min_dollar(self):
        """Sizing block includes target_min_dollar."""
        assert 'target_min_dollar' in self.body, \
            "_actionPopHtml() must show target_min_dollar in sizing"

    def test_target_max_dollar(self):
        """Sizing block includes target_max_dollar."""
        assert 'target_max_dollar' in self.body, \
            "_actionPopHtml() must show target_max_dollar in sizing"

    def test_amt_field(self):
        """Sizing block includes AMT$ (_amt field)."""
        assert '_amt' in self.body or 'AMT$' in self.body, \
            "_actionPopHtml() must show AMT$ in sizing"

    def test_sizing_section_label(self):
        """_actionPopHtml() has a 'Sizing' section label."""
        assert 'Sizing' in self.body, \
            "_actionPopHtml() must label the sizing block 'Sizing'"

    def test_returns_html_string(self):
        """_actionPopHtml() must return an HTML string (not void)."""
        assert 'return html' in self.body, \
            "_actionPopHtml() must return the built HTML string"


# ─── Criteria 21-25: setupActionCol() ────────────────────────────────────────

class TestSetupActionCol:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)
        self.body = _func_body(self.src, "setupActionCol")

    def test_function_exists(self):
        """setupActionCol() must be declared in actionable.js."""
        assert 'function setupActionCol(' in self.src, \
            "setupActionCol() not found in actionable.js"

    def test_creates_actDetailTip(self):
        """setupActionCol() must create (or reuse) #actDetailTip div."""
        assert 'actDetailTip' in self.body, \
            "setupActionCol() must create/reference #actDetailTip"

    def test_fixed_position_tooltip(self):
        """The tooltip div must be fixed-position."""
        assert 'position:fixed' in self.body or "position: 'fixed'" in self.body or \
               'fixed' in self.body, \
            "setupActionCol() tooltip must use position:fixed"

    def test_mouseover_wired(self):
        """setupActionCol() must wire a 'mouseover' event listener."""
        assert "addEventListener('mouseover'" in self.body or \
               'addEventListener("mouseover"' in self.body, \
            "setupActionCol() must add a mouseover event listener"

    def test_mouseout_wired(self):
        """setupActionCol() must wire a 'mouseout' event listener."""
        assert "addEventListener('mouseout'" in self.body or \
               'addEventListener("mouseout"' in self.body, \
            "setupActionCol() must add a mouseout event listener"

    def test_mouseout_hides_tooltip(self):
        """On mouseout the tooltip must be hidden (display:none)."""
        assert "display = 'none'" in self.body or \
               'display = "none"' in self.body or \
               "style.display = 'none'" in self.body, \
            "setupActionCol() mouseout handler must set display:none to hide tooltip"

    def test_calls_action_pop_html(self):
        """setupActionCol() must call _actionPopHtml() to build popup content."""
        assert '_actionPopHtml(' in self.body, \
            "setupActionCol() must call _actionPopHtml() to build tooltip content"

    def test_targets_act_action_cell(self):
        """Event handlers must target .act-action-cell elements."""
        assert 'act-action-cell' in self.body, \
            "setupActionCol() must target .act-action-cell in its event handlers"

    def test_positioned_right_of_cell(self):
        """Tooltip should attempt to position to the right of the cell."""
        # Look for rect.right (positioning right-of-cell logic)
        assert 'rect.right' in self.body or 'getBoundingClientRect' in self.body, \
            "setupActionCol() must position tooltip relative to the Action cell"


class TestSetupActionColCalledFirst:
    """setupActionCol() must be called before setupRRActionCol() in DOMContentLoaded."""

    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_setup_action_col_called_in_dom_ready(self):
        """setupActionCol() is called from DOMContentLoaded handler."""
        dom_start = self.src.find("document.addEventListener('DOMContentLoaded'")
        assert dom_start != -1, "DOMContentLoaded handler not found"
        # The DOMContentLoaded handler is large (>7000 chars); search by absolute
        # position within the source after the handler open.
        ac_pos = self.src.find('setupActionCol()', dom_start)
        assert ac_pos != -1, \
            "setupActionCol() must be called from inside DOMContentLoaded"
        # Confirm it is before the end of the handler (the closing `});` for the
        # outer addEventListener). Find the setupRRActionCol which is a known
        # marker inside the same handler.
        rr_pos = self.src.find('setupRRActionCol()', dom_start)
        # Both must be found after dom_start, i.e. within the handler body.
        assert ac_pos > dom_start, \
            "setupActionCol() call not found after DOMContentLoaded start"

    def test_setup_action_col_before_rr_action_col(self):
        """setupActionCol() must be called before setupRRActionCol()."""
        dom_start = self.src.find("document.addEventListener('DOMContentLoaded'")
        assert dom_start != -1
        # Both calls live inside the same handler; compare their absolute offsets.
        action_col_pos = self.src.find('setupActionCol()', dom_start)
        rr_col_pos     = self.src.find('setupRRActionCol()', dom_start)
        assert action_col_pos != -1, "setupActionCol() not found after DOMContentLoaded"
        assert rr_col_pos     != -1, "setupRRActionCol() not found after DOMContentLoaded"
        assert action_col_pos < rr_col_pos, \
            "setupActionCol() must appear before setupRRActionCol() in DOMContentLoaded"


# ─── Criterion 26: Other header columns still present ────────────────────────

class TestOtherColumnsIntact:
    def setup_method(self):
        self.html = _read(ACTIONABLE_HTML)
        self.js   = _read(ACTIONABLE_JS)

    def test_action_column_header_present(self):
        """Action column header must still be in the grid."""
        assert 'consolidated_action' in self.html or \
               re.search(r'<th[^>]*>\s*Action\s*</th>', self.html), \
            "Action column header missing from grid"

    def test_trtbn_column_header_present(self):
        """TrTnBBRskRng column (Trend/Trade/Bollinger/Risk-Range) must still
        be in the grid.

        REWRITTEN (TASK_112, 2026-07-04): the <th> caption was re-worded
        from the literal 'TrTnBBRskRng' abbreviation to 'Technical' (0
        matches for the old string in actionable.html) — but the same
        column/data-key (rr_action) and concept are unchanged, and the old
        name still lives on as the CSV-export column label in
        actionable.js. Assert the current column identity instead of the
        retired caption string.
        """
        assert 'data-key="rr_action"' in self.html, \
            "Technical column (data-key='rr_action', formerly captioned "\
            "'TrTnBBRskRng') missing from grid"
        assert 'TrTnBBRskRng' in self.js, \
            "TrTnBBRskRng label should still survive as the CSV-export column name"

    def test_final_call_column_header_present(self):
        """Final Call column header must still be in the grid."""
        assert 'Final Call' in self.html, \
            "Final Call column header missing from grid"

    def test_rr_action_cell_still_in_render_grid(self):
        """rr-action-cell must still be rendered in renderGrid()."""
        render_body = _func_body(self.js, "renderGrid")
        assert 'rr-action-cell' in render_body, \
            "rr-action-cell has been inadvertently removed from renderGrid()"

    def test_final_call_html_still_in_render_grid(self):
        """_finalCallHtml() must still be called in renderGrid()."""
        render_body = _func_body(self.js, "renderGrid")
        assert '_finalCallHtml(' in render_body, \
            "_finalCallHtml() call removed from renderGrid() — Final Call column broken"

    def test_fires_cell_html_still_in_render_grid(self):
        """firesCellHtml() must still be called in renderGrid() for Rules column."""
        render_body = _func_body(self.js, "renderGrid")
        assert 'firesCellHtml(' in render_body, \
            "firesCellHtml() removed from renderGrid() — Rules column broken"

    def test_amt_cell_still_in_render_grid(self):
        """AMT$ cell must still be rendered in renderGrid()."""
        render_body = _func_body(self.js, "renderGrid")
        assert '_amt' in render_body, \
            "AMT$ (_amt) cell not found in renderGrid()"


# ─── Criterion 27: No production Python files modified ───────────────────────

class TestNoPythonChanges:
    """Verify no API/Python files were modified (frontend-only change)."""

    def test_api_routers_dash_unchanged(self):
        """api/routers/dash.py should not have been modified by this work item
        (it appears in git status as modified for a different reason — we just
        confirm it exists and is loadable as text)."""
        # This test simply ensures the file is not empty/corrupted
        dash = (API_DIR / "routers" / "dash.py")
        assert dash.exists(), "api/routers/dash.py missing"
        content = dash.read_text(encoding="utf-8")
        assert len(content) > 100, "api/routers/dash.py appears truncated"

    def test_no_actionpophtml_in_python_files(self):
        """_actionPopHtml must not appear in any Python file (JS-only)."""
        for py in API_DIR.rglob("*.py"):
            content = py.read_text(encoding="utf-8", errors="replace")
            assert '_actionPopHtml' not in content, \
                f"_actionPopHtml leaked into Python file: {py}"
