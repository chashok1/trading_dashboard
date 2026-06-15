"""
Tests for AGENT_WORK_29 — Fix Final Call / Technical inconsistency.

Two changes in web/actionable.js:
  1. finalCall() ~line 907: confidence changed from 'high' to 'mixed' in the
     techIsSell && !isHeld branch.  When Sources=BUY and Technical=SELL but
     the position is not held, the directions genuinely conflict; 'high' was wrong.
  2. setupRRActionCol() ~line 2402: QR decision path reconstruction now uses
     d.final_score (QR, ground truth from Pass 2) to drive the path, and flags
     divergence with "QO=X but score overridden (see Score)" when QO != QR.

Acceptance criteria (from AGENT_WORK_29.md + DEV_HANDOFF.md):
  Check 1  — node --check web/actionable.js exits 0 (no syntax errors).
  Check 2  — finalCall() techIsSell && !isHeld branch sets confidence = 'mixed'.
  Check 3  — finalCall() techIsBuy && atMax branch still uses confidence = 'high' (unchanged).
  Check 4  — finalCall() srcIsReduce && techIsSell branch still uses confidence = 'high' (genuine align).
  Check 5  — finalCall() srcIsBuy && techIsBuy && !atMax branch still uses confidence = 'high' (genuine align).
  Check 6  — setupRRActionCol() uses d.final_score as the qr ground-truth variable.
  Check 7  — setupRRActionCol() divergence note "but score overridden" is present.
  Check 8  — setupRRActionCol() QR path uses qo !== qr comparison for divergence.
  Check 9  — setupRRActionCol() labels include "(QF)" / "(QK)" / "(QO)" identifiers.
  Check 10 — setupRRActionCol() still renders the RR path when qf > 0 and qk not bearish.
  Check 11 — finalCall() function signature and structure are intact (no regression).
  Check 12 — No new confidence='high' text introduced inside the techIsSell block.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
JS_FILE      = PROJECT_ROOT / "web" / "actionable.js"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


# ── Helper: extract function body by name ─────────────────────────────────────

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


def find_branch(body: str, condition_pattern: str, window: int = 400) -> str:
    """
    Locate the first match of condition_pattern in body and return the
    surrounding window of text (to inspect what follows that branch).
    """
    m = re.search(condition_pattern, body)
    if m is None:
        return ""
    start = m.start()
    return body[start : start + window]


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


# ── Check 2: techIsSell && !isHeld branch uses confidence = 'mixed' ──────────

class TestFinalCallMixedConfidence:
    def test_tech_sell_not_held_confidence_is_mixed(self, js_text):
        """
        In the techIsSell && !isHeld branch, confidence must be set to 'mixed'.
        This is the core fix: Sources=BUY + Technical=SELL + !held is a genuine conflict.
        """
        body = extract_function_body(js_text, "finalCall")
        # Find the !isHeld sub-branch inside the techIsSell block.
        # The comment inserted by the fix is distinctive.
        has_mixed_comment = (
            "srcIsBuy must be true" in body
            or "Sources says buy but Technical says sell" in body
            or "Use 'mixed', not 'high'" in body
        )
        assert has_mixed_comment, (
            "finalCall() does not contain the explanatory comment for the mixed branch — "
            "the fix may not have been applied"
        )

    def test_tech_sell_not_held_sets_mixed_not_high(self, js_text):
        """
        The !isHeld sub-branch within techIsSell must assign confidence = 'mixed',
        NOT confidence = 'high'.  Locate the sub-branch by its context.
        """
        body = extract_function_body(js_text, "finalCall")

        # Locate the techIsSell block start
        tech_sell_idx = body.find("if (techIsSell)")
        assert tech_sell_idx != -1, "if (techIsSell) not found in finalCall()"

        # Within the techIsSell block, find the !isHeld sub-branch
        tech_sell_block = body[tech_sell_idx : tech_sell_idx + 800]
        not_held_idx = tech_sell_block.find("if (!isHeld)")
        assert not_held_idx != -1, "if (!isHeld) not found inside techIsSell block"

        # The sub-branch text (up to the next else-if)
        sub_branch = tech_sell_block[not_held_idx : not_held_idx + 400]

        # Must contain 'mixed'
        assert "'mixed'" in sub_branch or '"mixed"' in sub_branch, (
            "finalCall() techIsSell && !isHeld branch does not set confidence = 'mixed'. "
            f"Branch text: {sub_branch!r}"
        )

        # Must NOT contain confidence = 'high' in this specific sub-branch
        # (high is set in sibling branches but not here)
        high_in_branch = re.search(r"confidence\s*=\s*['\"]high['\"]", sub_branch)
        assert high_in_branch is None, (
            "finalCall() techIsSell && !isHeld branch sets confidence = 'high' — "
            "the fix was not applied (should be 'mixed'). "
            f"Branch text: {sub_branch!r}"
        )

    def test_not_held_branch_returns_hold_action(self, js_text):
        """
        The !isHeld sub-branch within techIsSell must also produce a HOLD action
        (not a sell) since selling is infeasible when not held.
        """
        body = extract_function_body(js_text, "finalCall")
        tech_sell_idx = body.find("if (techIsSell)")
        tech_sell_block = body[tech_sell_idx : tech_sell_idx + 800]
        not_held_idx = tech_sell_block.find("if (!isHeld)")
        sub_branch = tech_sell_block[not_held_idx : not_held_idx + 400]

        assert "actionDisplay('HOLD')" in sub_branch or 'actionDisplay("HOLD")' in sub_branch, (
            "finalCall() techIsSell && !isHeld branch must render HOLD "
            "(infeasible sell — nothing to sell). "
            f"Branch text: {sub_branch!r}"
        )


# ── Check 3: techIsBuy && atMax branch still returns 'high' (unchanged) ───────

class TestFinalCallAtMaxBranchUnchanged:
    def test_tech_buy_at_max_confidence_still_high(self, js_text):
        """
        techIsBuy && atMax should still return confidence = 'high'.
        Directions agree (both want to add) but can't because of position limit.
        This branch was explicitly listed as unchanged in DEV_HANDOFF.md.
        """
        body = extract_function_body(js_text, "finalCall")

        # Find the atMax branch inside the techIsBuy block
        tech_buy_idx = body.find("} else if (techIsBuy || techIsBuyMin)")
        assert tech_buy_idx != -1, "techIsBuy || techIsBuyMin branch not found in finalCall()"

        tech_buy_block = body[tech_buy_idx : tech_buy_idx + 800]
        at_max_idx = tech_buy_block.find("} else if (atMax)")
        assert at_max_idx != -1, "atMax branch not found inside techIsBuy block"

        at_max_branch = tech_buy_block[at_max_idx : at_max_idx + 200]
        assert "'high'" in at_max_branch or '"high"' in at_max_branch, (
            "finalCall() techIsBuy && atMax branch no longer sets confidence = 'high' — "
            "this branch should be unchanged. "
            f"Branch text: {at_max_branch!r}"
        )


# ── Check 4: srcIsReduce && techIsSell returns 'high' (genuine align) ─────────

class TestFinalCallGenuineAlignUnchanged:
    def test_src_reduce_tech_sell_held_confidence_high(self, js_text):
        """
        When Sources=REDUCE (sell) AND Technical=SELL AND position IS held,
        both directions agree → confidence = 'high'.  This branch should be unchanged.
        """
        body = extract_function_body(js_text, "finalCall")

        # Find the techIsSell block
        tech_sell_idx = body.find("if (techIsSell)")
        tech_sell_block = body[tech_sell_idx : tech_sell_idx + 800]

        # The srcIsReduce sub-branch (comes after the !isHeld sub-branch)
        src_reduce_idx = tech_sell_block.find("} else if (srcIsReduce)")
        assert src_reduce_idx != -1, (
            "srcIsReduce branch not found inside techIsSell block"
        )
        src_reduce_branch = tech_sell_block[src_reduce_idx : src_reduce_idx + 200]
        assert "'high'" in src_reduce_branch or '"high"' in src_reduce_branch, (
            "finalCall() srcIsReduce && techIsSell branch no longer returns confidence='high' — "
            "this genuine-align branch should be unchanged. "
            f"Branch text: {src_reduce_branch!r}"
        )


# ── Check 5: srcIsBuy && techIsBuy && !atMax returns 'high' (unchanged) ───────

class TestFinalCallBuyAlignUnchanged:
    def test_src_buy_tech_buy_no_conflict_confidence_high(self, js_text):
        """
        When srcIsBuy is true and techIsBuy is true and not atMax,
        both drivers agree → confidence = 'high'.  Unchanged by this fix.
        """
        body = extract_function_body(js_text, "finalCall")

        # Locate the inner-most else branch of the techIsBuy block
        # (after srcIsReduce, atMax, !isHeld && srcIsAdd checks)
        # It contains: confidence = (srcIsBuy) ? 'high' : 'mixed';
        pattern = r"confidence\s*=\s*\(\s*srcIsBuy\s*\)\s*\?\s*['\"]high['\"]"
        assert re.search(pattern, body), (
            "finalCall() does not contain the srcIsBuy ternary producing 'high' in the "
            "techIsBuy path — this branch appears to have been accidentally changed. "
        )


# ── Check 6: setupRRActionCol() uses d.final_score as qr ─────────────────────

class TestSetupRRActionColQrGroundTruth:
    def test_final_score_assigned_to_qr(self, js_text):
        """
        setupRRActionCol() must assign d.final_score to qr (ground truth from Pass 2).
        This is the key change: qr drives path reconstruction instead of reconstructing
        the path purely from qf/qk/qo.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        # Must see d.final_score assigned (e.g. qr = d.final_score)
        pattern = r"qr\s*=\s*d\.final_score"
        assert re.search(pattern, body), (
            "setupRRActionCol() does not assign d.final_score to qr — "
            "the ground-truth fix was not applied. "
            "Expected: const qf = d.tn_td_action, qk = d.bb_action, qo = d.rr_action, qr = d.final_score"
        )

    def test_qf_qk_qo_also_captured(self, js_text):
        """
        setupRRActionCol() must still capture qf, qk, qo from the data object
        alongside qr.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "d.tn_td_action" in body, "setupRRActionCol() no longer reads d.tn_td_action (qf)"
        assert "d.bb_action"    in body, "setupRRActionCol() no longer reads d.bb_action (qk)"
        assert "d.rr_action"    in body, "setupRRActionCol() no longer reads d.rr_action (qo)"
        assert "d.final_score"  in body, "setupRRActionCol() no longer reads d.final_score (qr)"

    def test_qr_null_check_guards_path(self, js_text):
        """
        The decision path block must be inside an 'if (qr != null)' guard,
        using qr as the primary driver.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "if (qr != null)" in body, (
            "setupRRActionCol() does not guard the decision path with 'if (qr != null)' — "
            "qr-based path reconstruction is not the primary branch"
        )


# ── Check 7: Divergence note "but score overridden" is present ───────────────

class TestDivergenceNote:
    def test_score_overridden_note_present(self, js_text):
        """
        When QO diverges from QR, the tooltip must show
        'but score overridden (see Score)' instead of the silent '→ Score'.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "but score overridden" in body, (
            "setupRRActionCol() does not contain the divergence note "
            "'but score overridden (see Score)' — HYG-style contradictions will "
            "still silently mislead the user"
        )

    def test_see_score_note_present(self, js_text):
        """The full divergence note must include 'see Score' for user guidance."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "see Score" in body, (
            "setupRRActionCol() divergence note does not contain 'see Score' — "
            "user has no pointer to where the ground truth lives"
        )


# ── Check 8: qo !== qr comparison for divergence ─────────────────────────────

class TestDivergenceComparison:
    def test_qo_not_equal_qr_comparison(self, js_text):
        """
        The divergence detection must compare qo !== qr (or qo != qr) to decide
        whether to show the override note.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        pattern = r"qo\s*!==?\s*qr|qr\s*!==?\s*qo"
        assert re.search(pattern, body), (
            "setupRRActionCol() does not compare qo !== qr to detect divergence — "
            "the override note will never (or always) appear"
        )

    def test_rrNote_variable_used(self, js_text):
        """
        The divergence conditional result should be stored in a variable
        (e.g. rrNote) and rendered in the step() call for the RR (QO) node.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        # rrNote (or equivalent) must exist
        has_rr_note = "rrNote" in body or "rr_note" in body or "overrideNote" in body
        assert has_rr_note, (
            "setupRRActionCol() does not define an rrNote (or equivalent) variable for "
            "the divergence note — the note may not be passed to the step() renderer"
        )

    def test_qo_prefix_shown_in_divergence(self, js_text):
        """
        The divergence note must start with 'QO=' (to show the actual QO value)
        so the user can see both the override and the original QO value.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "'QO=' +" in body or '"QO=" +' in body or "'QO='" in body or '"QO="' in body, (
            "setupRRActionCol() divergence note does not interpolate 'QO=<value>' — "
            "user cannot see what QO was before the override"
        )


# ── Check 9: Labels include (QF) / (QK) / (QO) identifiers ───────────────────

class TestQualifiedLabels:
    def test_qf_label_present(self, js_text):
        """
        Step labels for the Trend/Trade node must include '(QF)' so the user can
        cross-reference with the column names.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "(QF)" in body, (
            "setupRRActionCol() step labels do not include '(QF)' — "
            "Trend/Trade node is unlabeled"
        )

    def test_qk_label_present(self, js_text):
        """Step labels for the BB Range Streak node must include '(QK)'."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "(QK)" in body, (
            "setupRRActionCol() step labels do not include '(QK)' — "
            "BB Range Streak node is unlabeled"
        )

    def test_qo_label_present(self, js_text):
        """Step labels for the RR node must include '(QO)'."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "(QO)" in body, (
            "setupRRActionCol() step labels do not include '(QO)' — "
            "RR node is unlabeled"
        )


# ── Check 10: RR path still rendered when qf > 0 and qk not bearish ──────────

class TestRRPathStillRendered:
    def test_rr_path_condition_exists(self, js_text):
        """
        The RR path (qf > 0, qk >= 0 or null) must still be rendered in the
        decision path — this is the normal happy path for symbols like HYG.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        # The condition for the RR path includes qf > 0 and qk >= 0 / qk == null
        pattern = r"qf\s*(!=\s*null\s*&&\s*)?>\s*0"
        assert re.search(pattern, body), (
            "setupRRActionCol() does not have a condition for qf > 0 — "
            "the RR decision path is missing"
        )

    def test_not_bearish_label_present(self, js_text):
        """The RR path step should include 'not bearish → use RR' label text."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "not bearish" in body and "use RR" in body, (
            "setupRRActionCol() RR path step does not contain 'not bearish → use RR' — "
            "the decision path label is missing or changed"
        )

    def test_rr_step_rendered_with_qo(self, js_text):
        """
        The step() call for the RR node must pass qo (the stored rr_action) as its
        value argument, so the displayed value is the RR score, not a derived value.
        """
        body = extract_function_body(js_text, "setupRRActionCol")
        # We expect something like: step(2, 'RR (QO)', qo, rrNote, true)
        pattern = r"step\s*\(\s*2\s*,\s*['\"]RR"
        assert re.search(pattern, body), (
            "setupRRActionCol() RR step (indent level 2) is missing — "
            "step(2, 'RR ...', qo, ...) expected"
        )


# ── Check 11: finalCall() function structure is intact ────────────────────────

class TestFinalCallIntegrity:
    def test_final_call_defined(self, js_text):
        """finalCall() function must still be defined."""
        assert "function finalCall(" in js_text, (
            "finalCall() function is missing from actionable.js"
        )

    def test_final_call_has_tech_is_sell_branch(self, js_text):
        """finalCall() must still have the if (techIsSell) branch."""
        body = extract_function_body(js_text, "finalCall")
        assert "if (techIsSell)" in body, (
            "finalCall() no longer has the if (techIsSell) branch — function structure broken"
        )

    def test_final_call_has_tech_is_buy_branch(self, js_text):
        """finalCall() must still have the techIsBuy || techIsBuyMin branch."""
        body = extract_function_body(js_text, "finalCall")
        assert "techIsBuy || techIsBuyMin" in body, (
            "finalCall() no longer has the techIsBuy || techIsBuyMin branch"
        )

    def test_final_call_returns_object(self, js_text):
        """finalCall() must return an object with confidence and code fields."""
        body = extract_function_body(js_text, "finalCall")
        assert "confidence:" in body, (
            "finalCall() does not produce a confidence: field in its return object"
        )
        assert "code:" in body, (
            "finalCall() does not produce a code: field in its return object"
        )

    def test_final_call_html_renders_mixed_badge(self, js_text):
        """
        _finalCallHtml() must produce a 'Mixed' badge when confidence != 'high'.
        Verify the badge text and tooltip are present.
        """
        body = extract_function_body(js_text, "_finalCallHtml")
        assert "Mixed" in body, (
            "_finalCallHtml() does not produce a 'Mixed' badge — "
            "the 'mixed' confidence value will not be visible in the UI"
        )
        assert "conflict" in body, (
            "_finalCallHtml() mixed badge does not contain 'conflict' in its tooltip — "
            "user gets no guidance on why it's mixed"
        )


# ── Check 12: No accidental confidence='high' in techIsSell block ─────────────

class TestNoFalseHighInTechSellBlock:
    def test_no_high_in_not_held_sub_branch(self, js_text):
        """
        The !isHeld sub-branch of techIsSell must contain ZERO occurrences of
        confidence = 'high' — the sole fix was changing this to 'mixed'.
        """
        body = extract_function_body(js_text, "finalCall")

        tech_sell_idx = body.find("if (techIsSell)")
        assert tech_sell_idx != -1, "if (techIsSell) not found"

        tech_sell_block = body[tech_sell_idx : tech_sell_idx + 800]
        not_held_idx = tech_sell_block.find("if (!isHeld)")
        assert not_held_idx != -1, "if (!isHeld) not found inside techIsSell"

        # The not-held sub-branch ends at the next "} else if"
        else_after = tech_sell_block.find("} else if", not_held_idx + 1)
        if else_after == -1:
            else_after = not_held_idx + 400
        sub_branch = tech_sell_block[not_held_idx:else_after]

        high_matches = list(re.finditer(r"confidence\s*=\s*['\"]high['\"]", sub_branch))
        assert len(high_matches) == 0, (
            f"finalCall() techIsSell && !isHeld sub-branch still contains "
            f"confidence = 'high' ({len(high_matches)} occurrence(s)) — fix was not applied. "
            f"Sub-branch text: {sub_branch!r}"
        )

    def test_mixed_confidence_count_in_tech_sell(self, js_text):
        """
        Inside the techIsSell block, exactly the right branches use 'high' vs 'mixed':
          - !isHeld     → 'mixed'  (the fix)
          - srcIsReduce → 'high'   (genuine align)
          - else (src buys, tech sells, held) → 'mixed'
        Total 'mixed' occurrences in the techIsSell block = 2 (not 1, not 3).
        """
        body = extract_function_body(js_text, "finalCall")

        tech_sell_idx = body.find("if (techIsSell)")
        assert tech_sell_idx != -1

        # The techIsSell block ends before the } else if (techIsBuy || techIsBuyMin)
        tech_buy_idx = body.find("} else if (techIsBuy || techIsBuyMin)", tech_sell_idx)
        if tech_buy_idx == -1:
            tech_buy_idx = tech_sell_idx + 1200
        tech_sell_block = body[tech_sell_idx:tech_buy_idx]

        mixed_count = len(re.findall(r"confidence\s*=\s*['\"]mixed['\"]", tech_sell_block))
        assert mixed_count == 2, (
            f"finalCall() techIsSell block should have exactly 2 'mixed' assignments "
            f"(!isHeld branch + the else/conflict branch), found {mixed_count}. "
            f"Block excerpt: {tech_sell_block[:600]!r}"
        )
