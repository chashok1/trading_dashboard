"""
Tests for AGENT_WORK_17 — Final Call column in the Actionable screen.

Acceptance criteria:
  1. node --check web/actionable.js passes (no syntax errors).
  2. Final Call column header is present in actionable.html with correct
     data-key="_fc_strength" and data-type="num".
  3. _FC_SCALE maps sell actions to negative values and buy actions to
     positive values; hold/none map to 0.
  4. finalCall() returns feasible=false (and strength=0) when
     consolidated_action is empty/null.
  5. finalCall() returns feasible=true and a non-zero strength/code when
     consolidated_action is non-empty.
  6. Risk-off bias: when sell and buy lenses conflict, adjustedScore is
     pulled toward the more bearish side (min * 0.5 pull logic present).
  7. Confidence badge: 3/3 agree → 'high'; 2/3 → 'med'; conflict → 'mixed'.
  8. _computePriority() uses |finalCallStrength| * |AMT$| formula.
  9. Inline done button carries data-fc attribute and uses it as the logged
     action (the click handler reads doneBtn.dataset.fc).
 10. CSS classes fc-conf-badge, fc-conf-high, fc-conf-med, fc-conf-mixed
     are present in web/styles.css.
 11. No regression: existing column headers (Action, TrTnBBRskRng, Trig,
     AMT$, Pri) are still present in actionable.html.
 12. The "Pri" column header (renamed from "Conv") uses data-key="_priority".
 13. JS-level: finalCall() with all-agree scenario → confidence='high'.
 14. JS-level: finalCall() with sell consolidated + buy trig → risk-off
     produces a sell-side or neutral final call (not a buy).
 15. JS-level: _computePriority() > 0 for a feasible non-zero final call.
"""

from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
ACTIONABLE_JS = WEB_DIR / "actionable.js"
ACTIONABLE_HTML = WEB_DIR / "actionable.html"
STYLES_CSS = WEB_DIR / "styles.css"


def _js() -> str:
    return ACTIONABLE_JS.read_text(encoding="utf-8")


def _html() -> str:
    return ACTIONABLE_HTML.read_text(encoding="utf-8")


def _css() -> str:
    return STYLES_CSS.read_text(encoding="utf-8")


def _extract_function(js: str, name: str) -> str:
    """Extract a named function body (var/let/const fn = ... or function fn(...)).

    Returns the entire function source from 'function NAME(' or 'NAME = function'
    through its matching closing brace.
    """
    # Try plain function declaration first
    pat1 = f"function {name}("
    start = js.find(pat1)
    if start == -1:
        # Try var/let/const assignment
        pat2 = f"{name} = function"
        start = js.find(pat2)
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
# 2. Final Call column header in HTML
# ---------------------------------------------------------------------------

class TestHtmlColumnPresent:
    """Final Call column must exist with correct data-key and data-type."""

    def test_html_file_exists(self):
        assert ACTIONABLE_HTML.exists(), f"actionable.html not found at {ACTIONABLE_HTML}"

    def test_final_call_header_present(self):
        html = _html()
        assert "Final Call" in html, (
            "actionable.html must contain a 'Final Call' column header"
        )

    def test_data_key_fc_strength(self):
        html = _html()
        assert 'data-key="_fc_strength"' in html, (
            "Final Call <th> must have data-key=\"_fc_strength\""
        )

    def test_data_type_num(self):
        html = _html()
        # Find the th that contains Final Call and check it has data-type="num"
        # We look for a th element that contains both _fc_strength and data-type="num"
        assert re.search(r'data-key="_fc_strength"[^>]*data-type="num"'
                         r'|data-type="num"[^>]*data-key="_fc_strength"',
                         html), (
            "Final Call <th> must have data-type=\"num\""
        )

    # test_final_call_between_trig_and_pos — RETIRED (TASK_112 test-debt
    # cleanup, 2026-07-04). Both anchor columns are gone: the Trig column was
    # removed entirely from the grid (TASK_109 — trig_action is no longer
    # surfaced anywhere on the screen, confirmed in test_agent_work_22.py's
    # TestTrigColumnRemovedHtml), and the column caption is now 'POS$' not
    # 'Pos $' (see test_agent_work_38.py::TestNoLayoutChanges, rewritten to
    # check data-col identifiers instead of caption text). With both
    # reference points gone, there's no meaningful "is Final Call between
    # them" check left to perform. Cat B.


# ---------------------------------------------------------------------------
# 3. _FC_SCALE values
# ---------------------------------------------------------------------------

class TestFcScale:
    """_FC_SCALE must map sell < 0, buy > 0, hold/none = 0."""

    def test_fc_scale_defined(self):
        js = _js()
        assert "_FC_SCALE" in js, "_FC_SCALE variable must be defined in actionable.js"

    def test_sell_values_negative(self):
        """SA/REMOVE/SS/STM/REDUCE must have negative values in _FC_SCALE."""
        js = _js()
        # Extract the _FC_SCALE object literal
        idx = js.find("_FC_SCALE")
        assert idx != -1
        brace_start = js.index("{", idx)
        depth = 0
        i = brace_start
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    scale_str = js[brace_start: i + 1]
                    break
            i += 1
        # SA:-3 or SA: -3
        assert re.search(r"SA\s*:\s*-\d", scale_str), "SA must map to negative in _FC_SCALE"
        assert re.search(r"REMOVE\s*:\s*-\d", scale_str), "REMOVE must map to negative"
        assert re.search(r"SS\s*:\s*-\d", scale_str), "SS must map to negative"
        assert re.search(r"REDUCE\s*:\s*-\d", scale_str), "REDUCE must map to negative"

    def test_buy_values_positive(self):
        """BM/INCREASE/ADD/BS/BMN must have positive values in _FC_SCALE."""
        js = _js()
        idx = js.find("_FC_SCALE")
        brace_start = js.index("{", idx)
        depth = 0
        i = brace_start
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    scale_str = js[brace_start: i + 1]
                    break
            i += 1
        assert re.search(r"INCREASE\s*:\s*\d", scale_str), "INCREASE must map to positive"
        assert re.search(r"ADD\s*:\s*\d", scale_str), "ADD must map to positive"
        assert re.search(r"BM\s*:\s*\d", scale_str), "BM must map to positive"

    def test_hold_maps_to_zero(self):
        """HOLD and NONE must map to 0 in _FC_SCALE."""
        js = _js()
        idx = js.find("_FC_SCALE")
        brace_start = js.index("{", idx)
        depth = 0
        i = brace_start
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    scale_str = js[brace_start: i + 1]
                    break
            i += 1
        assert re.search(r"HOLD\s*:\s*0", scale_str), "HOLD must map to 0 in _FC_SCALE"
        assert re.search(r"NONE\s*:\s*0", scale_str), "NONE must map to 0 in _FC_SCALE"


# ---------------------------------------------------------------------------
# 4. finalCall() feasibility gate
# ---------------------------------------------------------------------------

class TestFeasibilityGate:
    """finalCall() must return feasible=false for empty/null consolidated_action."""

    def test_feasible_false_on_empty_action_in_source(self):
        js = _js()
        body = _extract_function(js, "finalCall")
        # The function must check for empty/null consolidated_action
        assert ("ca === 'NONE'" in body or "ca === \"NONE\"" in body or
                "!ca" in body), (
            "finalCall() must check for empty/NONE consolidated_action"
        )
        assert "feasible: false" in body, (
            "finalCall() must return feasible: false when consolidated_action is empty"
        )

    def test_feasibility_returns_zero_strength(self):
        """When feasible=false, strength must be 0."""
        js = _js()
        body = _extract_function(js, "finalCall")
        # When feasible=false, strength: 0 must appear in that return path
        assert "strength: 0" in body, (
            "finalCall() must return strength: 0 when feasible=false"
        )

    def test_confidence_none_on_infeasible(self):
        """feasible=false should also carry confidence: 'none'."""
        js = _js()
        body = _extract_function(js, "finalCall")
        assert "confidence: 'none'" in body or 'confidence: "none"' in body, (
            "finalCall() must return confidence: 'none' on infeasible/empty action"
        )


# ---------------------------------------------------------------------------
# 5. finalCall() non-empty action path
# ---------------------------------------------------------------------------

class TestFinalCallFeasiblePath:
    """finalCall() must compute a strength and code when consolidated_action is set."""

    def test_fcstrength_function_present(self):
        """REWRITTEN (TASK_112, 2026-07-04): `_fcStrengthToAction()` no
        longer exists — finalCall() was redesigned (documented in its own
        header comment as a 'D6' change) from a strength-scored/clamped
        model to a two-lens hierarchical gate (Sources=strategic,
        Technical=tactical) that picks an explicit actionDisplay() code per
        branch instead of mapping a continuous strength back to an action.
        `_fcStrength()` (code -> numeric strength via `_FC_SCALE`) still
        exists and is still used. Cat B for the reverse-mapping half.
        """
        js = _js()
        assert "_fcStrength" in js, "_fcStrength function must be defined"

    def test_final_call_returns_feasible_true(self):
        js = _js()
        body = _extract_function(js, "finalCall")
        assert "feasible:   true" in body or "feasible: true" in body, (
            "finalCall() must return feasible: true for the successful path"
        )

    # test_strength_clamped_to_feasible_range — RETIRED (TASK_112 test-debt
    # cleanup, 2026-07-04). finalCall()'s continuous-strength clamping
    # (fcMin/fcMax + Math.max/Math.min) was replaced by the same D6
    # hierarchical-gate redesign noted in test_fcstrength_function_present
    # above — each branch now returns one of a small set of exact
    # actionDisplay() codes (SA/SS/BM/BS/BMN/HOLD) with its exact
    # `_FC_SCALE` value, so there is no continuous range left to clamp.
    # Feasibility is now a boolean gate per branch, not a numeric clamp. Cat B.


# ---------------------------------------------------------------------------
# 6. Risk-off bias
# ---------------------------------------------------------------------------

class TestRiskOffBias:
    """When sell and buy signals conflict, risk-off must pull toward bearish.

    RETIRED both tests below (TASK_112 test-debt cleanup, 2026-07-04). The
    vote-tallying risk-off mechanism (sellVotes/buyVotes conflict detection,
    mostBearish * 0.5 pull) was replaced by the D6 hierarchical-gate
    redesign (see test_fcstrength_function_present above): Sources
    (consolidated_action) now acts as a strategic gate that Technical
    (rr_action) can only tactically adjust within, rather than three lenses
    voting and being pulled toward the most-bearish score. The equivalent
    "never let a sell signal get overridden into a buy" behavior is now
    covered directly by test_agent_work_31.py's finalCall() gate/guard
    tests (e.g. the exit-gate / infeasible-sell tests) rather than a
    vote-count mechanism. Cat B — superseded architecture, not a rename.
    """

    # test_risk_off_logic_present / test_most_bearish_used_in_conflict —
    # see class docstring above.


# ---------------------------------------------------------------------------
# 7. Confidence badge logic
# ---------------------------------------------------------------------------

class TestConfidenceBadge:
    """Confidence badge logic.

    REWRITTEN (TASK_112, 2026-07-04): the original 3-lens "agrees" counter
    (3 agree -> high; 2 -> med; conflict -> mixed) was replaced by the D6
    hierarchical-gate redesign — confidence is now one of 'gate' (a
    deterministic branch fired, Technical not meaningfully consulted),
    'high' (Sources and Technical genuinely align), 'mixed' (they
    conflict), or 'none' (infeasible/no signal). There is no 'agrees'
    counter and no 'med' tier at all anymore (0 matches for either). The
    current confidence-tier behavior (gate/high/mixed) is already covered
    by test_agent_work_31.py's TestGateBranchesUseGateConfidence /
    TestHighPreservedOnGenuineAlignBranches, and _finalCallHtml()'s current
    badge rendering (inline-styled, not CSS-classed — see
    test_agent_work_31.py::TestFinalCallHtmlGateBadge, also rewritten in
    this same task) by TestFinalCallHtmlGateBadge there. Cat B — superseded
    architecture, not a rename; retiring here rather than duplicating that
    existing coverage.
    """

    # test_agrees_counter_present / test_high_confidence_at_three /
    # test_med_confidence_at_two / test_html_badge_uses_correct_classes —
    # see class docstring above.

    def test_mixed_confidence_otherwise(self):
        js = _js()
        body = _extract_function(js, "finalCall")
        assert ("'mixed'" in body or '"mixed"' in body), (
            "finalCall() must assign confidence='mixed' when lenses conflict"
        )


# ---------------------------------------------------------------------------
# 8. _computePriority() formula
# ---------------------------------------------------------------------------

class TestComputePriority:
    """Priority = |finalCallStrength| × |AMT$|."""

    def test_compute_priority_present(self):
        js = _js()
        assert "_computePriority" in js, "_computePriority function must be defined"

    def test_priority_uses_fc_strength(self):
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "fc.strength" in body or "fc.feasible" in body, (
            "_computePriority must use the finalCall strength"
        )

    def test_priority_uses_abs_amt(self):
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "Math.abs" in body, (
            "_computePriority must use Math.abs for the |AMT$| value"
        )

    def test_priority_formula_strength_times_amt(self):
        """The priority formula must combine an action-severity rank with |AMT$|.

        REWRITTEN (TASK_112, 2026-07-04): the formula no longer multiplies
        `fc.strength` by amt — it now prefers the server-computed
        `priority_rank` when present (TASK_53/106), falling back to a
        `state.buysellSeq` severity-rank lookup by `fc.code`, scaled by
        1e6 and offset by |AMT$| (`seq * 1e6 + amt`) so tiers never cross.
        Same conceptual formula (severity-rank combined with dollar size to
        break ties within a tier), different exact terms.
        """
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "buysellSeq" in body, (
            "_computePriority must rank by state.buysellSeq severity"
        )
        assert "1e6" in body and "amt" in body, (
            "_computePriority must combine the severity rank with |AMT$| (seq * 1e6 + amt)"
        )

    def test_priority_fallback_to_conviction(self):
        """When finalCall is infeasible, priority must sink to the bottom.

        REWRITTEN (TASK_112, 2026-07-04): the fallback is no longer
        `_agreeingSources` conviction scoring — infeasible/unranked rows now
        get seq = -1 (sinks below all real severity tiers), and the server-
        computed `priority_rank` is preferred over any client fallback when
        present. Same intent (infeasible rows never outrank real actions),
        different mechanism.
        """
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "priority_rank" in body, (
            "_computePriority must prefer the server-computed priority_rank when available"
        )
        assert re.search(r"-1\s*\*\s*1e6", body), (
            "_computePriority must sink infeasible rows to the bottom via seq = -1"
        )


# ---------------------------------------------------------------------------
# 9. Inline done button data-fc attribute
# ---------------------------------------------------------------------------

class TestInlineDoneButton:
    """Done button must carry data-fc and handler must read it."""

    def test_data_fc_on_done_button(self):
        """The btn-inline-done button must have data-fc attribute in renderGrid."""
        js = _js()
        body = _extract_function(js, "renderGrid")
        assert "data-fc=" in body, (
            "renderGrid() must set data-fc attribute on the inline done button"
        )

    def test_click_handler_reads_dataset_fc(self):
        """The click handler for btn-inline-done must read doneBtn.dataset.fc."""
        js = _js()
        assert "doneBtn.dataset.fc" in js, (
            "Click handler must read doneBtn.dataset.fc as the action code"
        )

    def test_fc_act_code_used_in_action(self):
        """The click handler must use the fc code (not hardcoded 'DONE') when available."""
        js = _js()
        # The handler: const actCode = doneBtn.dataset.fc || 'DONE'; inlineAction(sym, actCode)
        assert ("dataset.fc" in js and "inlineAction" in js), (
            "Click handler must call inlineAction() with the dataset.fc code"
        )


# ---------------------------------------------------------------------------
# 10. CSS classes for confidence badge
# ---------------------------------------------------------------------------

class TestCssConfidenceBadge:
    """All four fc-conf-* CSS classes must exist in styles.css."""

    def test_css_file_exists(self):
        assert STYLES_CSS.exists(), f"styles.css not found at {STYLES_CSS}"

    def test_fc_conf_badge_present(self):
        css = _css()
        assert ".fc-conf-badge" in css, ".fc-conf-badge rule missing from styles.css"

    def test_fc_conf_high_present(self):
        css = _css()
        assert ".fc-conf-high" in css, ".fc-conf-high rule missing from styles.css"

    def test_fc_conf_med_present(self):
        css = _css()
        assert ".fc-conf-med" in css, ".fc-conf-med rule missing from styles.css"

    def test_fc_conf_mixed_present(self):
        css = _css()
        assert ".fc-conf-mixed" in css, ".fc-conf-mixed rule missing from styles.css"

    def test_high_uses_green_palette(self):
        """fc-conf-high should use a green background (d1fae5 or similar)."""
        css = _css()
        idx = css.find(".fc-conf-high")
        block_start = css.find("{", idx)
        block_end = css.find("}", block_start)
        block = css[block_start: block_end + 1]
        # Green tones: #d1fae5 or similar, or contains '6c30' from #065f46
        assert ("d1fae5" in block or "e6f4ea" in block or "065f46" in block
                or "6ee7b7" in block), (
            f".fc-conf-high must use a green palette, got: {block!r}"
        )

    def test_mixed_uses_red_palette(self):
        """fc-conf-mixed should use a red/warning background."""
        css = _css()
        idx = css.find(".fc-conf-mixed")
        block_start = css.find("{", idx)
        block_end = css.find("}", block_start)
        block = css[block_start: block_end + 1]
        assert ("fee2e2" in block or "fbeaea" in block or "7f1d1d" in block
                or "fca5a5" in block), (
            f".fc-conf-mixed must use a red/warning palette, got: {block!r}"
        )


# ---------------------------------------------------------------------------
# 11 & 12. Regression: existing column headers still present
# ---------------------------------------------------------------------------

class TestNoRegression:
    """Existing column headers must not have been removed."""

    def test_action_column_present(self):
        html = _html()
        assert ">Action<" in html, "Action column header must still be present"

    def test_tr_tn_bb_column_present(self):
        """REWRITTEN (TASK_112, 2026-07-04): caption re-worded 'TrTnBBRskRng'
        -> 'Technical' (same data-key='rr_action' column) — see
        test_agent_work_22.py::TestOtherColumnsIntact::test_trtbn_column_
        header_present, which already covers this rename in detail."""
        html = _html()
        assert 'data-key="rr_action"' in html, (
            "Technical column (formerly captioned TrTnBBRskRng) header must still be present"
        )

    # test_trig_column_present — RETIRED (TASK_112 test-debt cleanup,
    # 2026-07-04). The Trig column was removed entirely from the grid
    # (TASK_109 — trig_action is no longer surfaced anywhere on the
    # Actionable screen); see test_agent_work_22.py::
    # TestTrigColumnRemovedHtml (this removal is itself under test there).
    # Cat B.

    def test_amt_column_present(self):
        html = _html()
        assert "AMT$" in html, "AMT$ column header must still be present"

    def test_pri_column_present(self):
        """Pri column (renamed from Conv) must be present with data-key='_priority'."""
        html = _html()
        assert ">Pri<" in html or "Pri</th>" in html or ">Pri " in html, (
            "Pri column header must be present (renamed from Conv)"
        )

    # test_pri_uses_priority_key — RETIRED (TASK_112 test-debt cleanup,
    # 2026-07-04). There is no longer a dedicated, clickable "Pri" <th> in
    # the grid (0 matches for data-key="_priority" in actionable.html) — the
    # `_priority` value survives only as the grid's internal default sort
    # key (`state.sort = { key: '_priority', ... }` in actionable.js), not a
    # visible/sortable column. Cat B — the standalone Priority column was
    # dropped, not renamed.

    def test_rules_edge_column_present(self):
        html = _html()
        assert "Rules (edge)" in html, "Rules (edge) column must still be present"

    def test_act_column_present(self):
        html = _html()
        assert ">Act<" in html, "Act column header must still be present"


# ---------------------------------------------------------------------------
# 13-15. JS-level logic tests via Node.js
# ---------------------------------------------------------------------------

class TestFinalCallJsLogic:
    """
    Execute finalCall() and _computePriority() via Node.js with synthetic row
    data and assert expected behaviour.
    """

    # Minimal stub for the functions from actions.js that finalCall() depends on
    _ACTIONS_STUB = textwrap.dedent(r"""
        // Minimal stubs for functions defined in actions.js / _common.js
        function actionDisplay(code) {
          var c = (code || '').toUpperCase();
          var map = {
            'SA':       { label: 'Sell All',      code: 'SA',  side: 'sell', cls: 'remove' },
            'REMOVE':   { label: 'Sell All',      code: 'SA',  side: 'sell', cls: 'remove' },
            'SS':       { label: 'Sell Some',     code: 'SS',  side: 'sell', cls: 'reduce' },
            'STM':      { label: 'Sell to Min',   code: 'STM', side: 'sell', cls: 'reduce' },
            'REDUCE':   { label: 'Sell Some',     code: 'SS',  side: 'sell', cls: 'reduce' },
            'HOLD':     { label: 'Hold',          code: 'HOLD',side: 'neutral', cls: 'hold' },
            'NONE':     { label: 'Hold',          code: 'HOLD',side: 'neutral', cls: 'hold' },
            'OVER_MAX': { label: 'Sell Overage',  code: 'SS',  side: 'sell', cls: 'reduce' },
            'BS':       { label: 'Buy Some',      code: 'BS',  side: 'buy',  cls: 'increase' },
            'INCREASE': { label: 'Buy Some',      code: 'BS',  side: 'buy',  cls: 'increase' },
            'BMN':      { label: 'Buy to Min',    code: 'BMN', side: 'buy',  cls: 'add' },
            'ADD':      { label: 'Buy to Min',    code: 'BMN', side: 'buy',  cls: 'add' },
            'BM':       { label: 'Buy More',      code: 'BM',  side: 'buy',  cls: 'increase' },
          };
          return map[c] || { label: c, code: c, side: 'neutral', cls: 'hold' };
        }
        function actionText(disp) { return disp ? disp.label : ''; }
        function escapeHtml(s) {
          return String(s ?? '').replace(/[&<>"']/g, c => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
          }[c]));
        }
        // Minimal state stub for scorecard (needed by _hasPositiveEdge)
        var state = { scorecard: {} };
    """)

    def _run_js(self, js_code: str) -> subprocess.CompletedProcess:
        js = _js()
        # Extract the functions we need
        functions_to_extract = [
            "_FC_SCALE",  # it's a var, not a function — we'll grab it differently
        ]
        func_names = [
            "_fcStrength", "_fcStrengthToAction", "finalCall",
            "_finalCallHtml", "_computePriority",
            "_isOverMaxOverlay", "_hasPositiveEdge", "_sourcesOf",
            "_agreeingSources",
        ]
        func_bodies = []
        for name in func_names:
            try:
                body = _extract_function(js, name)
                func_bodies.append(body)
            except AssertionError:
                pass

        # Also grab _FC_SCALE variable definition
        idx = js.find("var _FC_SCALE")
        if idx == -1:
            idx = js.find("const _FC_SCALE")
        if idx == -1:
            idx = js.find("let _FC_SCALE")
        if idx != -1:
            end = js.index(";", js.index("}", idx)) + 1
            fc_scale_def = js[idx: end]
        else:
            fc_scale_def = ""

        harness = (
            self._ACTIONS_STUB
            + "\n"
            + fc_scale_def
            + "\n"
            + "\n".join(func_bodies)
            + "\n"
            + js_code
        )
        return subprocess.run(
            ["node", "-e", harness],
            capture_output=True,
            text=True,
        )

    def test_tc13_all_agree_high_confidence(self):
        """
        TC13: consolidated=INCREASE, rr=INCREASE, trig=INCREASE →
        all three map to +2; expects confidence='high', feasible=true, side='buy'.
        """
        script = textwrap.dedent(r"""
            var row = {
              consolidated_action: 'INCREASE',
              rr_action: 'INCREASE',
              trig_action: 'INCREASE',
              current_position_dollar: 10000,
              target_max_dollar: null,
              rules_engine_fires: [],
              _amt: 5000,
            };
            var fc = finalCall(row);
            console.assert(fc.feasible === true,
              'TC13: expected feasible=true, got ' + JSON.stringify(fc));
            console.assert(fc.confidence === 'high',
              'TC13: expected confidence=high, got ' + JSON.stringify(fc));
            console.assert(fc.side === 'buy',
              'TC13: expected side=buy, got ' + JSON.stringify(fc));
            process.stdout.write("TC13_PASSED\n");
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node harness crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "TC13_PASSED" in result.stdout, (
            f"TC13 failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_tc14_risk_off_sell_wins_over_buy(self):
        """
        TC14: consolidated=REDUCE (sell), rr=INCREASE (buy), trig=HOLD →
        risk-off must produce a sell-side or neutral final call (not buy).
        """
        script = textwrap.dedent(r"""
            var row = {
              consolidated_action: 'REDUCE',
              rr_action: 'INCREASE',
              trig_action: 'HOLD',
              current_position_dollar: 20000,
              target_max_dollar: null,
              target_min_dollar: null,
              suggested_target_dollar: 10000,
              rules_engine_fires: [],
              _amt: 10000,
            };
            var fc = finalCall(row);
            console.assert(fc.feasible === true,
              'TC14: expected feasible=true, got ' + JSON.stringify(fc));
            // Risk-off: conflict must lean sell-side or neutral, NOT buy
            console.assert(fc.side !== 'buy',
              'TC14: expected sell-side or neutral on conflict, got side=' + fc.side +
              ' full=' + JSON.stringify(fc));
            process.stdout.write("TC14_PASSED\n");
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node harness crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "TC14_PASSED" in result.stdout, (
            f"TC14 failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_tc14b_feasibility_clamp_sell_consolidated(self):
        """
        TC14b: consolidated=REDUCE, rr=REMOVE, trig=REMOVE →
        all sell-side, feasibility clamp to max sell strength of consolidated.
        finalCall strength must be negative (sell-side).
        """
        script = textwrap.dedent(r"""
            var row = {
              consolidated_action: 'REDUCE',
              rr_action: 'REMOVE',
              trig_action: 'REMOVE',
              current_position_dollar: 20000,
              target_max_dollar: null,
              target_min_dollar: null,
              suggested_target_dollar: 10000,
              rules_engine_fires: [],
              _amt: 10000,
            };
            var fc = finalCall(row);
            console.assert(fc.feasible === true,
              'TC14b: expected feasible=true, got ' + JSON.stringify(fc));
            console.assert(fc.strength < 0,
              'TC14b: expected negative strength (sell), got strength=' + fc.strength);
            process.stdout.write("TC14b_PASSED\n");
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node harness crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "TC14b_PASSED" in result.stdout, (
            f"TC14b failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_tc_empty_action_infeasible(self):
        """
        finalCall() with empty consolidated_action must return feasible=false,
        strength=0.
        """
        script = textwrap.dedent(r"""
            var row = {
              consolidated_action: '',
              rr_action: 'INCREASE',
              trig_action: 'INCREASE',
              current_position_dollar: 10000,
              target_max_dollar: null,
              rules_engine_fires: [],
              _amt: 5000,
            };
            var fc = finalCall(row);
            console.assert(fc.feasible === false,
              'TC_INFEASIBLE: expected feasible=false, got ' + JSON.stringify(fc));
            console.assert(fc.strength === 0,
              'TC_INFEASIBLE: expected strength=0, got ' + JSON.stringify(fc));
            process.stdout.write("TC_INFEASIBLE_PASSED\n");
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node harness crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "TC_INFEASIBLE_PASSED" in result.stdout, (
            f"TC_INFEASIBLE failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_tc15_priority_positive_for_feasible(self):
        """
        TC15: _computePriority() must return > 0 for a row with a non-zero
        final call and non-zero _amt.
        """
        script = textwrap.dedent(r"""
            var row = {
              consolidated_action: 'INCREASE',
              rr_action: 'INCREASE',
              trig_action: 'INCREASE',
              current_position_dollar: 5000,
              target_max_dollar: null,
              rules_engine_fires: [],
              _amt: 8000,
              source_actions: [],
            };
            var priority = _computePriority(row);
            console.assert(priority > 0,
              'TC15: expected priority > 0, got ' + priority);
            process.stdout.write("TC15_PASSED\n");
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node harness crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "TC15_PASSED" in result.stdout, (
            f"TC15 failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_tc_med_confidence_two_agree(self):
        """
        consolidated=INCREASE (+), rr=INCREASE (+), trig=HOLD (0) →
        only 2 of 3 signal buy → confidence='med'.
        """
        script = textwrap.dedent(r"""
            var row = {
              consolidated_action: 'INCREASE',
              rr_action: 'INCREASE',
              trig_action: 'HOLD',
              current_position_dollar: 10000,
              target_max_dollar: null,
              rules_engine_fires: [],
              _amt: 5000,
            };
            var fc = finalCall(row);
            console.assert(fc.feasible === true,
              'TC_MED: expected feasible=true, got ' + JSON.stringify(fc));
            // 2 of 3 agree on buy side → med
            console.assert(fc.confidence === 'med' || fc.confidence === 'high',
              'TC_MED: expected med or high confidence with 2 buy + 1 neutral, got ' +
              JSON.stringify(fc));
            process.stdout.write("TC_MED_PASSED\n");
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node harness crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "TC_MED_PASSED" in result.stdout, (
            f"TC_MED failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_tc_mixed_confidence_sell_vs_buy(self):
        """
        consolidated=REDUCE (sell), rr=INCREASE (buy), trig=REMOVE (sell) →
        conflict → Mixed, and final call must lean sell-side (risk-off).
        """
        script = textwrap.dedent(r"""
            var row = {
              consolidated_action: 'REDUCE',
              rr_action: 'INCREASE',
              trig_action: 'REMOVE',
              current_position_dollar: 20000,
              target_max_dollar: null,
              suggested_target_dollar: 10000,
              rules_engine_fires: [],
              _amt: 10000,
            };
            var fc = finalCall(row);
            console.assert(fc.feasible === true,
              'TC_MIXED: expected feasible=true, got ' + JSON.stringify(fc));
            console.assert(fc.confidence === 'mixed',
              'TC_MIXED: expected confidence=mixed, got ' + JSON.stringify(fc));
            // Risk-off: must be sell-side or neutral
            console.assert(fc.side === 'sell' || fc.side === 'neutral',
              'TC_MIXED: risk-off should produce sell or neutral, got side=' + fc.side +
              ' full=' + JSON.stringify(fc));
            process.stdout.write("TC_MIXED_PASSED\n");
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node harness crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "TC_MIXED_PASSED" in result.stdout, (
            f"TC_MIXED failed:\n{result.stdout}\n{result.stderr}"
        )

    def test_tc_feasibility_clamp_no_buy_on_sell_consolidated(self):
        """
        Feasibility gate (hard): consolidated=REDUCE → Final Call must never
        be buy-side even if rr+trig are both INCREASE.
        """
        script = textwrap.dedent(r"""
            var row = {
              consolidated_action: 'REDUCE',
              rr_action: 'INCREASE',
              trig_action: 'INCREASE',
              current_position_dollar: 20000,
              target_max_dollar: null,
              suggested_target_dollar: 10000,
              rules_engine_fires: [],
              _amt: 10000,
            };
            var fc = finalCall(row);
            console.assert(fc.side !== 'buy',
              'TC_CLAMP: feasibility gate must prevent buy when consolidated=REDUCE, got ' +
              JSON.stringify(fc));
            process.stdout.write("TC_CLAMP_PASSED\n");
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node harness crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "TC_CLAMP_PASSED" in result.stdout, (
            f"TC_CLAMP failed:\n{result.stdout}\n{result.stderr}"
        )
