"""
Tests for AGENT_WORK_21 — Actionable-screen: codes-only labels, default-sort,
AND-filter coordination.

Acceptance criteria:
  1. node --check passes on web/actions.js and web/actionable.js.
  2. actionText() returns codes only:
       actionText(actionDisplay('SA'))       -> 'SA'
       actionText(actionDisplay('OVER_MAX')) -> 'SO'
       actionText(actionDisplay('HOLD'))     -> 'HOLD'
       actionText(null)                      -> '--'
       actionText(actionDisplay('BN'))       -> 'HOLD'
       actionText(actionDisplay('SN'))       -> 'HOLD'
       actionText(actionDisplay('REMOVE'))   -> 'SA'
       actionText(actionDisplay('NONE'))     -> '--'
  3. HOLD / BN / SN entries have code: 'HOLD' (not '').
  4. OVER_MAX entry has code: 'SO' (not '').
  5. actionDisplay(k).label is non-empty for SA, OVER_MAX, HOLD (tooltip source).
  6. loadActionable() resets state.sort to _priority DESC on every data load.
  7. clearAllFilters() also resets state.sort to _priority DESC.
  8. renderGrid() calls updateSortIndicators().
  9. matchesBaseFilters() includes the buys_sells check.
 10. applyClientFilter() uses baseRows + action chip only as extra filter.
 11. Chip onclick does NOT clear buys_sells (AND logic preserved).
 12. Chip counts come from baseRows (which already apply buys_sells).
 13. Action badge in grid has title= attribute with plain-English label.
 14. Final Call badge has title= attribute with the action label.
 15. TrTnBBRskRng and Trig cells have title= attributes.
 16. No Python or API router files changed by this work item
     (api/routers/dash.py change is outside scope — noted as concern).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR      = PROJECT_ROOT / "web"
ACTIONS_JS   = WEB_DIR / "actions.js"
ACTIONABLE_JS = WEB_DIR / "actionable.js"


# ─── helpers ────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _node_eval(js_expr: str, setup: str = "") -> str:
    """Evaluate a JS expression in Node with the action map loaded."""
    script = f"""
var window = {{}};
{_read(ACTIONS_JS)}
var actionDisplay = window.actionDisplay;
var actionText    = window.actionText;
{setup}
console.log(JSON.stringify({js_expr}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f"Node error: {result.stderr}"
    return result.stdout.strip()


# ─── Test 1: Syntax check ─────────────────────────────────────────────────

class TestSyntaxCheck:
    def test_actions_js_syntax(self):
        """node --check must exit 0 for actions.js."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONS_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_actionable_js_syntax(self):
        """node --check must exit 0 for actionable.js."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"


# ─── Test 2-5: actionText() output ──────────────────────────────────────────

class TestActionText:
    def _eval(self, expr: str) -> str:
        return _node_eval(expr).strip('"')

    def test_sa_returns_sa(self):
        assert self._eval("actionText(actionDisplay('SA'))") == "SA"

    def test_over_max_returns_so(self):
        assert self._eval("actionText(actionDisplay('OVER_MAX'))") == "SO"

    def test_hold_returns_hold(self):
        assert self._eval("actionText(actionDisplay('HOLD'))") == "HOLD"

    def test_null_returns_dash(self):
        result = self._eval("actionText(null)")
        assert result in ("--", "—", "&mdash;"), f"Expected '--' or em-dash, got: {result!r}"

    def test_bn_returns_hold(self):
        assert self._eval("actionText(actionDisplay('BN'))") == "HOLD"

    def test_sn_returns_hold(self):
        assert self._eval("actionText(actionDisplay('SN'))") == "HOLD"

    def test_remove_returns_sa(self):
        assert self._eval("actionText(actionDisplay('REMOVE'))") == "SA"

    def test_none_returns_dash(self):
        result = self._eval("actionText(actionDisplay('NONE'))")
        assert result in ("--", "—"), f"Expected '--' or em-dash, got: {result!r}"

    def test_stm_returns_stm(self):
        assert self._eval("actionText(actionDisplay('STM'))") == "STM"

    def test_bmn_returns_bmn(self):
        assert self._eval("actionText(actionDisplay('BMN'))") == "BMN"

    def test_bs_returns_bs(self):
        assert self._eval("actionText(actionDisplay('BS'))") == "BS"

    def test_bm_returns_bm(self):
        assert self._eval("actionText(actionDisplay('BM'))") == "BM"

    def test_ss_returns_ss(self):
        assert self._eval("actionText(actionDisplay('SS'))") == "SS"


class TestCodeFields:
    def _code(self, key: str) -> str:
        raw = _node_eval(f"actionDisplay('{key}').code")
        return raw.strip('"')

    def test_hold_code_is_hold_not_empty(self):
        assert self._code("HOLD") == "HOLD"

    def test_over_max_code_is_so_not_empty(self):
        assert self._code("OVER_MAX") == "SO"

    def test_bn_code_is_hold(self):
        assert self._code("BN") == "HOLD"

    def test_sn_code_is_hold(self):
        assert self._code("SN") == "HOLD"


class TestLabels:
    """Labels must be non-empty plain-English (used in title= tooltips)."""
    def _label(self, key: str) -> str:
        raw = _node_eval(f"actionDisplay('{key}').label")
        return raw.strip('"')

    def test_sa_label(self):
        assert self._label("SA") == "SELL ALL"

    def test_over_max_label(self):
        lbl = self._label("OVER_MAX")
        assert lbl and lbl != "SO", f"Expected plain-English label, got: {lbl!r}"

    def test_hold_label(self):
        lbl = self._label("HOLD")
        assert lbl, "HOLD label should not be empty"

    def test_ss_label(self):
        assert self._label("SS") == "SELL SOME"


# ─── Test 6-8: Default sort ──────────────────────────────────────────────────

class TestDefaultSort:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_load_actionable_resets_sort(self):
        """loadActionable() must set state.sort to _priority DESC."""
        # Find the loadActionable function body and look for the sort reset
        # The key pattern from the handoff: state.sort = { key: '_priority', dir: -1, type: 'num' }
        pattern = r"state\.sort\s*=\s*\{\s*key\s*:\s*['\"]_priority['\"],\s*dir\s*:\s*-1"
        matches = re.findall(pattern, self.src)
        assert len(matches) >= 1, "loadActionable() must reset sort to _priority DESC"

    def test_load_actionable_sort_inside_function(self):
        """Verify the sort reset is inside loadActionable(), not just somewhere else.

        REWRITTEN (TASK_112, 2026-07-04): loadActionable() now takes an
        `opts` parameter (`async function loadActionable(opts)`), so the
        exact zero-arg signature string no longer matches. Search for the
        function name with an open paren instead of the exact signature.
        """
        # Check that the sort reset appears in loadActionable context
        load_func_start = self.src.find("async function loadActionable(")
        assert load_func_start != -1, "loadActionable() not found"
        # Find the next occurrence of state.sort = {key: '_priority' after loadActionable
        sort_pattern = "state.sort = { key: '_priority', dir: -1, type: 'num' }"
        first_reset = self.src.find(sort_pattern)
        assert first_reset != -1, f"Sort reset pattern not found verbatim; check code"
        assert first_reset > load_func_start, "Sort reset must be inside loadActionable"
        # Also confirm it's before the fetch call
        fetch_call = self.src.find("fetchJson('/api/actionable?'", load_func_start)
        assert first_reset < fetch_call, "Sort reset should precede fetchJson in loadActionable"

    def test_clear_all_filters_resets_sort(self):
        """clearAllFilters() must also reset sort to _priority DESC.

        REWRITTEN (TASK_112, 2026-07-04): widened the search window — more
        filter fields (bull_prob_min, agreement_class + their UI resets)
        were added ahead of the sort reset, pushing it to ~513 chars in
        (was within 500). Same assertion, wider window to tolerate growth.
        """
        clear_func_start = self.src.find("function clearAllFilters()")
        assert clear_func_start != -1, "clearAllFilters() not found"
        # Find the end of clearAllFilters (next function declaration)
        # Look for state.sort reset within the next ~30 lines
        snippet = self.src[clear_func_start:clear_func_start + 800]
        assert "_priority" in snippet, "clearAllFilters() must reset sort to _priority"
        assert "dir: -1" in snippet, "clearAllFilters() must set dir: -1"

    def test_render_grid_calls_update_sort_indicators(self):
        """renderGrid() must call updateSortIndicators()."""
        render_func_start = self.src.find("\nfunction renderGrid()")
        assert render_func_start != -1, "renderGrid() not found"
        # Find end of renderGrid (approximately — look for next top-level function)
        snippet = self.src[render_func_start:render_func_start + 3000]
        assert "updateSortIndicators()" in snippet, \
            "renderGrid() must call updateSortIndicators()"

    def test_init_sorting_runs_before_load_dates(self):
        """initSorting() must be called before loadDates() in DOMContentLoaded.

        REWRITTEN (TASK_112, 2026-07-04): widened the search window —
        loadDates() now sits ~2670 chars into the (larger) DOMContentLoaded
        handler, past the original 1000-char snippet. Same ordering
        assertion, wider window to tolerate growth.
        """
        dom_start = self.src.find("document.addEventListener('DOMContentLoaded'")
        assert dom_start != -1
        snippet = self.src[dom_start:dom_start + 4000]
        init_pos  = snippet.find("initSorting()")
        dates_pos = snippet.find("loadDates()")
        assert init_pos != -1, "initSorting() not found in DOMContentLoaded"
        assert dates_pos != -1, "loadDates() not found in DOMContentLoaded"
        assert init_pos < dates_pos, \
            "initSorting() must run before loadDates() in DOMContentLoaded"


# ─── Test 9-12: AND filter coordination ─────────────────────────────────────

class TestAndFilterCoordination:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    # test_matches_base_filters_contains_buys_sells /
    # test_buys_sells_check_inside_matches_base_filters — RETIRED (TASK_112
    # test-debt cleanup, 2026-07-04). The `buys_sells` toggle filter no
    # longer exists anywhere in actionable.js (0 matches) — matchesBaseFilters()
    # was superseded by a richer, differently-shaped filter set (source,
    # account, held_only, conviction, symbol_search, bull_prob_min,
    # agreement_class), none of which is a direct buy/sell toggle. Cat B —
    # superseded filter architecture, not a rename. The AND-combination
    # *principle* this class is really about (baseRows applies every filter
    # except the action chip, so chip counts reflect all other active
    # filters) is still directly covered by test_apply_client_filter_uses_
    # base_rows and test_chip_counts_from_base_rows below, unaffected.

    def test_apply_client_filter_uses_base_rows(self):
        """applyClientFilter() must filter baseRows with only action chip.

        REWRITTEN (TASK_112, 2026-07-04): applyClientFilter() now takes an
        `opts` parameter (`function applyClientFilter(opts)` — supports
        preserveSelection for the auto-poll refresh path), so the exact
        zero-arg signature string no longer matches. Search for the function
        name with an open paren instead.
        """
        func_start = self.src.find("\nfunction applyClientFilter(")
        assert func_start != -1, "applyClientFilter() not found"
        snippet = self.src[func_start:func_start + 800]
        assert "state.baseRows" in snippet, \
            "applyClientFilter() must build baseRows"
        # rows = baseRows.filter(...) — action chip only
        assert "state.baseRows.filter" in snippet, \
            "rows must be built as baseRows.filter() in applyClientFilter"

    def test_chip_onclick_does_not_clear_buys_sells(self):
        """Action chip onclick must NOT set buys_sells='' (AND logic)."""
        render_summary_start = self.src.find("function renderSummary()")
        assert render_summary_start != -1
        # Find the chip.onclick handler
        onclick_start = self.src.find("chip.onclick = () => {", render_summary_start)
        assert onclick_start != -1, "chip.onclick not found in renderSummary"
        # Get the closure body (until its closing brace)
        brace_start = self.src.find("{", onclick_start + len("chip.onclick = () => "))
        depth = 0
        onclick_end = brace_start
        for i, ch in enumerate(self.src[brace_start:], start=brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    onclick_end = i
                    break
        onclick_body = self.src[brace_start:onclick_end + 1]
        assert "buys_sells" not in onclick_body, \
            "Action chip onclick must NOT clear buys_sells (would break AND logic)"

    def test_chip_counts_from_base_rows(self):
        """Chip counts must iterate state.baseRows, not state.allRows."""
        render_summary_start = self.src.find("function renderSummary()")
        assert render_summary_start != -1
        # Find the counting loop — should use baseRows
        func_end = self.src.find("\nfunction ", render_summary_start + 10)
        snippet = self.src[render_summary_start:func_end]
        # The count loop must use baseRows
        assert "state.baseRows" in snippet, \
            "renderSummary() must count from state.baseRows for chip counts"
        # Must NOT iterate allRows for counting (it would bypass the buys_sells filter)
        count_loop_pat = r"for\s*\(\s*const\s+\w+\s+of\s+state\.allRows\s*\)"
        assert not re.search(count_loop_pat, snippet), \
            "renderSummary chip-count loop must iterate baseRows, not allRows"


# ─── Test 13-15: Tooltip coverage ───────────────────────────────────────────

class TestTooltipCoverage:
    """Grid cells must surface a plain-English tooltip on hover.

    REWRITTEN/RETIRED (TASK_112, 2026-07-04) — see per-test notes below.
    Across the board, static `title=` attributes were superseded by
    dynamic, JS-driven hover popovers (the same evolutionary pattern
    followed by the Sources-column and IV/RR popovers elsewhere in this
    file): `.badge-action-*` classes are gone entirely (superseded by
    `.act-action-cell` + `setupActionCol()` -> `_actionPopHtml()`, already
    covered by test_agent_work_22.py::TestSetupActionCol /
    TestActionPopHtmlContent), and the Technical (rr) cell's tooltip moved
    from a static `title=` to a `#rrDetailTip` popover built dynamically on
    `.rr-action-cell` mouseover.
    """

    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_action_badge_has_title(self):
        """REWRITTEN (TASK_112, 2026-07-04): the action badge no longer uses
        a static title= — it's covered by a hover popover instead (see class
        docstring). Assert the current mechanism (act-action-cell + the
        setupActionCol/hover-popup wiring) is present, rather than the
        retired title= pattern (already thoroughly covered by
        test_agent_work_22.py, so just a presence check here)."""
        assert 'act-action-cell' in self.src, \
            "action badge cell (act-action-cell) not found in actionable.js"
        assert 'setupActionCol' in self.src, \
            "setupActionCol() hover-tooltip wiring not found in actionable.js"

    def test_final_call_badge_has_title(self):
        """_finalCallHtml() must include title= with the plain-English label."""
        fc_func_start = self.src.find("function _finalCallHtml(")
        assert fc_func_start != -1
        func_end = self.src.find("\nfunction ", fc_func_start + 10)
        snippet = self.src[fc_func_start:func_end]
        assert "title=" in snippet, \
            "_finalCallHtml() must include a title= attribute on the Final Call badge"
        # The title should use fc.label (the plain-English label)
        assert "fc.label" in snippet, \
            "_finalCallHtml() title= should reference fc.label for the plain-English name"

    def test_rr_cell_has_title(self):
        """Technical (formerly TrTnBBRskRng) cell must surface a tooltip.

        REWRITTEN (TASK_112, 2026-07-04): `rrDisp` is still computed but its
        title= usage was dropped — the tooltip moved to a dynamic
        `#rrDetailTip` popover built on `.rr-action-cell` mouseover (see
        class docstring). Assert the current hover-popover mechanism is
        wired, rather than the retired static title=/rrDisp.label pattern.
        """
        assert "rrDetailTip" in self.src, \
            "rr-action-cell hover popover (#rrDetailTip) not found in actionable.js"
        assert "rr-action-cell" in self.src, \
            "rr-action-cell class not found in actionable.js"

    # test_trig_cell_has_title — RETIRED (TASK_112 test-debt cleanup,
    # 2026-07-04). The Trig column was removed entirely from the grid
    # (TASK_109 — trig_action is no longer surfaced anywhere on the
    # Actionable screen); see test_agent_work_22.py::
    # TestTrigColumnRemovedHtml, where this removal is itself under test.
    # Cat B — there is no Trig cell left to have a tooltip on.


# ─── Test 16: Production-code changes scope ──────────────────────────────────

class TestProductionCodeScope:
    """Verify which production files were changed — flag anything unexpected."""

    def test_actions_js_is_new_file(self):
        """web/actions.js should exist on disk (created for this work item)."""
        assert ACTIONS_JS.exists(), "web/actions.js must exist"

    def test_actionable_js_exists_and_modified(self):
        """web/actionable.js must exist."""
        assert ACTIONABLE_JS.exists(), "web/actionable.js must exist"

    # test_no_py_files_in_core_etl_changed / test_actionable_html_and_styles_
    # are_also_changed — RETIRED (TASK_112 test-debt cleanup, 2026-07-04).
    # Both asserted a `git diff --name-only HEAD` working-tree snapshot from
    # the moment AGENT_WORK_21 was authored; every file involved has long
    # since been committed and the working tree reflects whatever unrelated
    # task is running today, not AGENT_WORK_21's scope. Same Cat A
    # git-status pattern as `TestNoGitCommit`, already retired in
    # test_agent_work_18.py (TASK_111).
