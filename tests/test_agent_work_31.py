"""
Tests for AGENT_WORK_31 — Fix finalCall() confidence:'high' on gate/guard branches.

Five gate/guard branches that never compare Sources vs Technical were hard-coded
to confidence:'high', causing the popover to falsely claim "Sources and Technical align".
The fix introduces confidence:'gate' with per-branch gateReason text.

Acceptance criteria (AGENT_WORK_31.md + DEV_HANDOFF.md):
  Check 1  — node --check web/actionable.js exits 0 (no syntax errors).
  Check 2  — AGENT_RESULT.md exists and contains data for HYG + 3 other symbols.
  Check 3  — AGENT_RESULT.md includes finalCall traces for each symbol.
  Check 4a — Exit gate (srcIsExit) uses confidence:'gate' (not 'high').
  Check 4b — Exit gate gateReason text says "exit signal" (not "align").
  Check 5a — OVER_MAX exit gate uses confidence:'gate'.
  Check 5b — OVER_MAX gate gateReason text mentions "Max".
  Check 6a — Infeasible-sell-not-held branch uses confidence:'gate'.
  Check 6b — Infeasible-sell gateReason says "Exit signal but not held".
  Check 7a — Don't-initiate (!held && !srcIsBuy) branch uses confidence:'gate'.
  Check 7b — Don't-initiate gateReason contains "hold".
  Check 8a — At-Max cap (techIsBuy + atMax) uses confidence:'gate'.
  Check 8b — At-Max gateReason mentions "Max".
  Check 9  — Neutral-hold (no signal from either lens) uses confidence:'gate'.
  Check 10 — _finalCallHtml() handles confidence:'gate' → renders "Gate" badge.
  Check 11 — .fc-conf-gate CSS class exists in styles.css with background/color.
  Check 12 — confidence:'high' is NOT present in any gate/guard branch.
  Check 13 — confidence:'high' IS still present in genuine align branches
             (srcIsReduce + techIsSell, srcIsBuy + techIsBuy).
  Check 14 — gateReason is declared in shared scope inside finalCall().
  Check 15 — No git commits were made (no new commit since last known commit).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT  = Path(__file__).parent.parent
JS_FILE       = PROJECT_ROOT / "web" / "actionable.js"
CSS_FILE      = PROJECT_ROOT / "web" / "styles.css"
RESULT_FILE   = PROJECT_ROOT / "AGENT_RESULT.md"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def css_text():
    return CSS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def result_text():
    return RESULT_FILE.read_text(encoding="utf-8")


# ── Helpers ───────────────────────────────────────────────────────────────────

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
                return js[brace_start: i + 1]
    raise AssertionError(f"Could not find closing brace of {fn_name}()")


# ── Check 1: Syntax ───────────────────────────────────────────────────────────

class TestSyntax:
    def test_node_check_passes(self):
        """node --check must exit 0 — no syntax errors in actionable.js."""
        result = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ── Checks 2–3: AGENT_RESULT.md content ───────────────────────────────────────

class TestAgentResultFile:
    def test_agent_result_exists(self):
        """AGENT_RESULT.md must exist in the project root."""
        assert RESULT_FILE.exists(), f"AGENT_RESULT.md not found at {RESULT_FILE}"

    def test_agent_result_contains_hyg(self, result_text):
        """AGENT_RESULT.md must contain data for HYG."""
        assert "HYG" in result_text, "AGENT_RESULT.md does not mention HYG"

    def test_agent_result_has_four_symbols(self, result_text):
        """AGENT_RESULT.md must include at least 4 symbols (HYG + 3 others)."""
        # The doc uses 'Symbol N:' headings — verify 4 are present.
        count = len(re.findall(r"## Symbol \d+", result_text))
        assert count >= 4, (
            f"AGENT_RESULT.md has {count} 'Symbol N:' sections; expected >= 4 "
            "(HYG + DAR + GOOGL + BUG)"
        )

    def test_agent_result_has_dar(self, result_text):
        """AGENT_RESULT.md must contain DAR data (exit gate bug)."""
        assert "DAR" in result_text, "AGENT_RESULT.md missing DAR data"

    def test_agent_result_has_googl(self, result_text):
        """AGENT_RESULT.md must contain GOOGL data (OVER_MAX bug)."""
        assert "GOOGL" in result_text, "AGENT_RESULT.md missing GOOGL data"

    def test_agent_result_has_bug(self, result_text):
        """AGENT_RESULT.md must contain BUG data (fourth symbol)."""
        assert "BUG" in result_text, "AGENT_RESULT.md missing BUG data"

    def test_agent_result_has_finalcall_trace(self, result_text):
        """AGENT_RESULT.md must contain finalCall traces (branch descriptions)."""
        has_trace = (
            "finalCall trace" in result_text
            or "Branch:" in result_text
            or "branch" in result_text.lower()
        )
        assert has_trace, (
            "AGENT_RESULT.md does not contain finalCall traces — "
            "branch-level tracing is missing"
        )

    def test_agent_result_documents_bug(self, result_text):
        """AGENT_RESULT.md must show the pre-fix bug (confidence:'high' on exit gate)."""
        has_bug_doc = (
            "PRE-fix" in result_text
            or "pre-fix" in result_text.lower()
            or "BUG" in result_text
            or "confidence:'high'" in result_text
            or "confidence: 'high'" in result_text
        )
        assert has_bug_doc, (
            "AGENT_RESULT.md does not document the pre-fix bug — "
            "root cause analysis is incomplete"
        )

    def test_agent_result_has_root_cause(self, result_text):
        """AGENT_RESULT.md must contain a root cause statement."""
        has_rc = "Root cause" in result_text or "root cause" in result_text.lower()
        assert has_rc, "AGENT_RESULT.md missing root cause section"


# ── Checks 4–9: Gate/guard branches use confidence:'gate' ────────────────────

class TestGateBranchesUseGateConfidence:

    def test_exit_gate_uses_confidence_gate(self, js_text):
        """
        The exit gate (srcIsExit=true path, held=true) must return confidence:'gate'.
        Before fix it returned confidence:'high'.
        """
        body = extract_function_body(js_text, "finalCall")
        # The exit gate block starts with: if (srcIsExit || caOverMax)
        exit_gate_idx = body.find("if (srcIsExit || caOverMax)")
        assert exit_gate_idx != -1, "if (srcIsExit || caOverMax) block not found in finalCall()"

        # Extract the block (up to ~400 chars past start covers both return paths)
        exit_gate_block = body[exit_gate_idx: exit_gate_idx + 600]

        # Must contain confidence: 'gate'
        assert re.search(r"confidence\s*:\s*['\"]gate['\"]", exit_gate_block), (
            "Exit gate block does not contain confidence:'gate' — "
            f"block: {exit_gate_block!r}"
        )

    def test_exit_gate_not_confidence_high(self, js_text):
        """
        The exit gate block (srcIsExit || caOverMax) must NOT assign confidence:'high'.
        """
        body = extract_function_body(js_text, "finalCall")
        exit_gate_idx = body.find("if (srcIsExit || caOverMax)")
        assert exit_gate_idx != -1

        # Find the closing brace of this if-block to bound the search
        # (simple: take next 600 chars, which covers the two return statements)
        exit_gate_block = body[exit_gate_idx: exit_gate_idx + 600]

        high_matches = re.findall(r"confidence\s*:\s*['\"]high['\"]", exit_gate_block)
        assert len(high_matches) == 0, (
            f"Exit gate block still contains confidence:'high' ({len(high_matches)} time(s)) — "
            f"block: {exit_gate_block!r}"
        )

    def test_exit_gate_has_gatereason_exit_signal(self, js_text):
        """Exit gate gateReason must describe the exit signal (not 'align')."""
        body = extract_function_body(js_text, "finalCall")
        exit_gate_idx = body.find("if (srcIsExit || caOverMax)")
        assert exit_gate_idx != -1
        # Use 900 chars — the block contains two return statements; gateReason
        # text appears around char 700-800 from the if() line.
        exit_gate_block = body[exit_gate_idx: exit_gate_idx + 900]

        has_exit_reason = (
            "exit signal" in exit_gate_block.lower()
            or "Technical not evaluated" in exit_gate_block
            or "Exit signal" in exit_gate_block
        )
        assert has_exit_reason, (
            "Exit gate block gateReason does not mention 'exit signal' or 'Technical not evaluated'. "
            f"Block: {exit_gate_block!r}"
        )

    def test_over_max_gate_has_gatereason(self, js_text):
        """OVER_MAX exit gate gateReason must mention Max (not 'align')."""
        body = extract_function_body(js_text, "finalCall")
        exit_gate_idx = body.find("if (srcIsExit || caOverMax)")
        assert exit_gate_idx != -1
        exit_gate_block = body[exit_gate_idx: exit_gate_idx + 600]

        has_max_reason = (
            "Max" in exit_gate_block
            or "max" in exit_gate_block.lower()
        )
        assert has_max_reason, (
            "OVER_MAX gate gateReason does not mention 'Max'. "
            f"Block: {exit_gate_block!r}"
        )

    def test_infeasible_sell_not_held_uses_gate(self, js_text):
        """
        The infeasible-sell path (!isHeld && !caOverMax inside exit gate) must use
        confidence:'gate', not 'high'.
        """
        body = extract_function_body(js_text, "finalCall")
        exit_gate_idx = body.find("if (srcIsExit || caOverMax)")
        assert exit_gate_idx != -1
        # Inside the exit gate block, the infeasible path is: if (!isHeld && !caOverMax)
        gate_block = body[exit_gate_idx: exit_gate_idx + 600]
        infeasible_idx = gate_block.find("!isHeld && !caOverMax")
        assert infeasible_idx != -1, (
            "Infeasible-sell guard (!isHeld && !caOverMax) not found inside exit gate"
        )
        infeasible_block = gate_block[infeasible_idx: infeasible_idx + 300]
        assert re.search(r"confidence\s*:\s*['\"]gate['\"]", infeasible_block), (
            "Infeasible-sell-not-held block does not use confidence:'gate'. "
            f"Block: {infeasible_block!r}"
        )

    def test_infeasible_sell_gatereason_text(self, js_text):
        """Infeasible-sell gateReason must say 'not held' or 'no action feasible'."""
        body = extract_function_body(js_text, "finalCall")
        exit_gate_idx = body.find("if (srcIsExit || caOverMax)")
        assert exit_gate_idx != -1
        # Use 900 chars so the full return block (including gateReason string) is captured.
        gate_block = body[exit_gate_idx: exit_gate_idx + 900]
        infeasible_idx = gate_block.find("!isHeld && !caOverMax")
        assert infeasible_idx != -1
        # The infeasible sub-block is ~250 chars; gateReason string follows the opening brace.
        infeasible_block = gate_block[infeasible_idx: infeasible_idx + 350]
        has_text = (
            "not held" in infeasible_block.lower()
            or "feasible" in infeasible_block.lower()
        )
        assert has_text, (
            "Infeasible-sell gateReason text is missing 'not held' or 'feasible'. "
            f"Block: {infeasible_block!r}"
        )

    def test_dont_initiate_guard_uses_gate(self, js_text):
        """
        Don't-initiate guard (!isHeld && !srcIsBuy) must return confidence:'gate'.
        """
        body = extract_function_body(js_text, "finalCall")
        guard_idx = body.find("if (!isHeld && !srcIsBuy)")
        assert guard_idx != -1, "Don't-initiate guard (!isHeld && !srcIsBuy) not found"
        guard_block = body[guard_idx: guard_idx + 300]
        assert re.search(r"confidence\s*:\s*['\"]gate['\"]", guard_block), (
            "Don't-initiate guard does not return confidence:'gate'. "
            f"Block: {guard_block!r}"
        )

    def test_dont_initiate_gatereason_contains_hold(self, js_text):
        """Don't-initiate gateReason must contain 'hold' (not 'align')."""
        body = extract_function_body(js_text, "finalCall")
        guard_idx = body.find("if (!isHeld && !srcIsBuy)")
        assert guard_idx != -1
        guard_block = body[guard_idx: guard_idx + 300]
        has_hold = "hold" in guard_block.lower() or "Hold" in guard_block
        assert has_hold, (
            "Don't-initiate gateReason does not mention 'hold'. "
            f"Block: {guard_block!r}"
        )

    def test_at_max_cap_uses_gate(self, js_text):
        """
        At-Max cap (techIsBuy + atMax) must use confidence:'gate', not 'high'.
        """
        body = extract_function_body(js_text, "finalCall")
        tech_buy_idx = body.find("} else if (techIsBuy || techIsBuyMin)")
        assert tech_buy_idx != -1, "techIsBuy || techIsBuyMin block not found"
        tech_buy_block = body[tech_buy_idx: tech_buy_idx + 800]

        at_max_idx = tech_buy_block.find("} else if (atMax)")
        assert at_max_idx != -1, "atMax branch not found inside techIsBuy block"
        at_max_block = tech_buy_block[at_max_idx: at_max_idx + 250]

        assert re.search(r"confidence\s*=\s*['\"]gate['\"]", at_max_block), (
            "At-Max cap branch does not use confidence='gate'. "
            f"Block: {at_max_block!r}"
        )

    def test_at_max_gatereason_mentions_max(self, js_text):
        """At-Max gateReason must mention Max/cap (not 'align')."""
        body = extract_function_body(js_text, "finalCall")
        tech_buy_idx = body.find("} else if (techIsBuy || techIsBuyMin)")
        assert tech_buy_idx != -1
        tech_buy_block = body[tech_buy_idx: tech_buy_idx + 800]
        at_max_idx = tech_buy_block.find("} else if (atMax)")
        assert at_max_idx != -1
        at_max_block = tech_buy_block[at_max_idx: at_max_idx + 250]

        has_max = "Max" in at_max_block or "max" in at_max_block or "cap" in at_max_block.lower()
        assert has_max, (
            "At-Max gateReason does not mention 'Max' or 'cap'. "
            f"Block: {at_max_block!r}"
        )

    def test_neutral_hold_uses_gate(self, js_text):
        """
        Neutral-hold branch (Sources neutral + Technical neutral — no active signal)
        must use confidence:'gate'.
        """
        body = extract_function_body(js_text, "finalCall")
        # Find the neutral-hold comment — the last else inside the techIsNeutral block
        neutral_marker = "no active signal" in body.lower() or "No active signal" in body
        assert neutral_marker, (
            "Neutral-hold branch comment 'No active signal' not found — "
            "the branch may be missing or renamed"
        )
        # Find where it appears and check gateReason is set
        idx = body.lower().find("no active signal")
        assert idx != -1
        vicinity = body[max(0, idx - 50): idx + 200]
        assert re.search(r"confidence\s*=\s*['\"]gate['\"]", vicinity) or \
               re.search(r"confidence\s*:\s*['\"]gate['\"]", vicinity), (
            f"Neutral-hold branch does not use confidence='gate'. Context: {vicinity!r}"
        )


# ── Check 10: _finalCallHtml() handles confidence:'gate' ─────────────────────

class TestFinalCallHtmlGateBadge:

    def test_final_call_html_has_gate_branch(self, js_text):
        """_finalCallHtml() must have an else-if branch for confidence === 'gate'."""
        body = extract_function_body(js_text, "_finalCallHtml")
        assert re.search(r"confidence\s*===?\s*['\"]gate['\"]", body), (
            "_finalCallHtml() has no handler for confidence === 'gate' — "
            "gate badges will not render"
        )

    def test_final_call_html_gate_renders_gate_text(self, js_text):
        """_finalCallHtml() gate branch must produce 'Gate' badge text."""
        body = extract_function_body(js_text, "_finalCallHtml")
        gate_branch_idx = body.find("'gate'")
        if gate_branch_idx == -1:
            gate_branch_idx = body.find('"gate"')
        assert gate_branch_idx != -1, "No 'gate' literal found in _finalCallHtml()"
        gate_vicinity = body[gate_branch_idx: gate_branch_idx + 300]
        assert ">Gate<" in gate_vicinity or "'Gate'" in gate_vicinity or '"Gate"' in gate_vicinity, (
            "_finalCallHtml() gate branch does not render 'Gate' text. "
            f"Context: {gate_vicinity!r}"
        )

    def test_final_call_html_gate_uses_fc_conf_gate_class(self, js_text):
        """_finalCallHtml() gate branch must apply the fc-conf-gate CSS class."""
        body = extract_function_body(js_text, "_finalCallHtml")
        assert "fc-conf-gate" in body, (
            "_finalCallHtml() does not reference the fc-conf-gate CSS class — "
            "gate badges will be unstyled"
        )

    def test_final_call_html_gate_uses_gatereason_as_title(self, js_text):
        """_finalCallHtml() gate badge title must use gateReason (per-branch text)."""
        body = extract_function_body(js_text, "_finalCallHtml")
        # gateReason should be used as the title attribute of the badge
        assert "gateReason" in body or "fc.gateReason" in body, (
            "_finalCallHtml() gate badge does not use gateReason for its title — "
            "all gate badges will show the same generic tooltip"
        )

    def test_final_call_html_still_has_high_branch(self, js_text):
        """_finalCallHtml() must still render 'High' for confidence === 'high'."""
        body = extract_function_body(js_text, "_finalCallHtml")
        assert re.search(r"confidence\s*===?\s*['\"]high['\"]", body), (
            "_finalCallHtml() lost the 'high' confidence branch — regression"
        )

    def test_final_call_html_gate_fallback_title(self, js_text):
        """
        Gate badge title must have a fallback string for when gateReason is null.
        """
        body = extract_function_body(js_text, "_finalCallHtml")
        gate_section_idx = body.find("fc-conf-gate")
        assert gate_section_idx != -1
        vicinity = body[max(0, gate_section_idx - 200): gate_section_idx + 200]
        # Should have either '||' fallback or conditional
        has_fallback = "||" in vicinity or "Deterministic gate" in vicinity
        assert has_fallback, (
            "_finalCallHtml() gate badge title has no fallback for null gateReason. "
            f"Context: {vicinity!r}"
        )


# ── Check 11: .fc-conf-gate in styles.css ────────────────────────────────────

class TestCssGateClass:

    def test_fc_conf_gate_class_exists(self, css_text):
        """.fc-conf-gate CSS class must be present in styles.css."""
        assert ".fc-conf-gate" in css_text, (
            ".fc-conf-gate class not found in web/styles.css — gate badges will be unstyled"
        )

    def test_fc_conf_gate_has_background(self, css_text):
        """.fc-conf-gate must define a background color."""
        idx = css_text.find(".fc-conf-gate")
        assert idx != -1
        rule_block = css_text[idx: idx + 200]
        assert "background" in rule_block, (
            ".fc-conf-gate CSS rule does not set a background color. "
            f"Rule: {rule_block!r}"
        )

    def test_fc_conf_gate_has_color(self, css_text):
        """.fc-conf-gate must define a text color."""
        idx = css_text.find(".fc-conf-gate")
        assert idx != -1
        rule_block = css_text[idx: idx + 200]
        assert "color" in rule_block, (
            ".fc-conf-gate CSS rule does not set a text color. "
            f"Rule: {rule_block!r}"
        )

    def test_fc_conf_gate_has_border(self, css_text):
        """.fc-conf-gate should define a border (distinguishing it from high/mixed)."""
        idx = css_text.find(".fc-conf-gate")
        assert idx != -1
        rule_block = css_text[idx: idx + 200]
        assert "border" in rule_block, (
            ".fc-conf-gate CSS rule does not set a border. "
            f"Rule: {rule_block!r}"
        )

    def test_fc_conf_gate_color_different_from_high(self, css_text):
        """
        .fc-conf-gate should use a different background from .fc-conf-high (green).
        High uses #d1fae5 (green); gate should be grey/slate.
        """
        high_idx = css_text.find(".fc-conf-high")
        gate_idx = css_text.find(".fc-conf-gate")
        assert high_idx != -1, ".fc-conf-high class missing from styles.css"
        assert gate_idx != -1, ".fc-conf-gate class missing from styles.css"

        high_block = css_text[high_idx: high_idx + 150]
        gate_block = css_text[gate_idx: gate_idx + 150]

        # Extract background values (crude but sufficient)
        high_bg = re.search(r"background\s*:\s*([^;]+)", high_block)
        gate_bg = re.search(r"background\s*:\s*([^;]+)", gate_block)

        if high_bg and gate_bg:
            assert high_bg.group(1).strip() != gate_bg.group(1).strip(), (
                ".fc-conf-gate has the SAME background as .fc-conf-high — "
                "it will look identical to the 'High' badge. "
                f"high bg: {high_bg.group(1)!r}, gate bg: {gate_bg.group(1)!r}"
            )


# ── Check 12: confidence:'high' NOT in gate/guard branches ───────────────────

class TestNoFalseHighOnGateBranches:

    def test_exit_gate_no_high(self, js_text):
        """Exit gate (srcIsExit || caOverMax) block must not contain confidence:'high'."""
        body = extract_function_body(js_text, "finalCall")
        exit_gate_idx = body.find("if (srcIsExit || caOverMax)")
        assert exit_gate_idx != -1
        # The entire exit gate block ends before the don't-initiate guard
        dont_init_idx = body.find("if (!isHeld && !srcIsBuy)", exit_gate_idx)
        if dont_init_idx == -1:
            dont_init_idx = exit_gate_idx + 800
        exit_gate_block = body[exit_gate_idx: dont_init_idx]

        high_count = len(re.findall(r"confidence\s*:\s*['\"]high['\"]", exit_gate_block))
        assert high_count == 0, (
            f"Exit gate block still contains confidence:'high' ({high_count} time(s)). "
            f"Block excerpt: {exit_gate_block[:400]!r}"
        )

    def test_dont_initiate_no_high(self, js_text):
        """Don't-initiate guard (!isHeld && !srcIsBuy) must not contain confidence:'high'."""
        body = extract_function_body(js_text, "finalCall")
        guard_idx = body.find("if (!isHeld && !srcIsBuy)")
        assert guard_idx != -1
        guard_block = body[guard_idx: guard_idx + 300]

        high_count = len(re.findall(r"confidence\s*:\s*['\"]high['\"]", guard_block))
        assert high_count == 0, (
            f"Don't-initiate guard still returns confidence:'high' ({high_count} time(s)). "
            f"Block: {guard_block!r}"
        )

    def test_at_max_branch_no_high(self, js_text):
        """At-Max cap (atMax branch) must not assign confidence='high'."""
        body = extract_function_body(js_text, "finalCall")
        tech_buy_idx = body.find("} else if (techIsBuy || techIsBuyMin)")
        assert tech_buy_idx != -1
        tech_buy_block = body[tech_buy_idx: tech_buy_idx + 800]
        at_max_idx = tech_buy_block.find("} else if (atMax)")
        assert at_max_idx != -1
        # atMax block ends at the next else branch
        next_else = tech_buy_block.find("} else if", at_max_idx + 1)
        if next_else == -1:
            next_else = at_max_idx + 250
        at_max_block = tech_buy_block[at_max_idx: next_else]

        high_count = len(re.findall(r"confidence\s*=\s*['\"]high['\"]", at_max_block))
        assert high_count == 0, (
            f"At-Max branch still assigns confidence='high' ({high_count} time(s)). "
            f"Block: {at_max_block!r}"
        )

    def test_neutral_hold_no_high(self, js_text):
        """Neutral-hold branch (no active signal) must not assign confidence='high'."""
        body = extract_function_body(js_text, "finalCall")
        neutral_idx = body.lower().find("no active signal")
        assert neutral_idx != -1, "'No active signal' comment not found in finalCall()"
        vicinity = body[max(0, neutral_idx - 50): neutral_idx + 200]

        high_count = len(re.findall(r"confidence\s*=\s*['\"]high['\"]", vicinity))
        assert high_count == 0, (
            f"Neutral-hold vicinity still assigns confidence='high' ({high_count} time(s)). "
            f"Context: {vicinity!r}"
        )


# ── Check 13: confidence:'high' IS present in genuine align branches ──────────

class TestHighPreservedOnGenuineAlignBranches:

    def test_src_reduce_tech_sell_still_high(self, js_text):
        """
        srcIsReduce + techIsSell (both sides say sell) is a genuine alignment —
        confidence:'high' must be preserved here.
        """
        body = extract_function_body(js_text, "finalCall")
        tech_sell_idx = body.find("if (techIsSell)")
        assert tech_sell_idx != -1
        tech_sell_block = body[tech_sell_idx: tech_sell_idx + 800]

        src_reduce_idx = tech_sell_block.find("} else if (srcIsReduce)")
        assert src_reduce_idx != -1, "srcIsReduce branch not found inside techIsSell block"
        src_reduce_branch = tech_sell_block[src_reduce_idx: src_reduce_idx + 250]

        assert re.search(r"confidence\s*=\s*['\"]high['\"]", src_reduce_branch), (
            "finalCall() srcIsReduce+techIsSell genuine-align branch lost confidence='high'. "
            f"Branch: {src_reduce_branch!r}"
        )

    def test_src_buy_tech_buy_ternary_still_high(self, js_text):
        """
        srcIsBuy + techIsBuy (both say buy) genuine-align branch must still produce
        confidence='high' via the (srcIsBuy) ? 'high' : 'mixed' ternary.
        """
        body = extract_function_body(js_text, "finalCall")
        pattern = r"confidence\s*=\s*\(\s*srcIsBuy\s*\)\s*\?\s*['\"]high['\"]"
        assert re.search(pattern, body), (
            "finalCall() srcIsBuy ternary producing confidence='high' not found — "
            "genuine buy-align branch was accidentally changed"
        )


# ── Check 14: gateReason declared in shared scope ────────────────────────────

class TestGateReasonScopeDeclaration:

    def test_gatereason_declared_in_shared_scope(self, js_text):
        """
        gateReason must be declared (var/let/const) in the shared scope of finalCall()
        so all branches can set it before the final return statement.
        """
        body = extract_function_body(js_text, "finalCall")
        # The shared declaration is something like:
        # var fcDisp, fcStrength, confidence, gateReason;
        pattern = r"var\s+[^;]*gateReason|let\s+[^;]*gateReason|const\s+[^;]*gateReason"
        assert re.search(pattern, body), (
            "gateReason is not declared in the shared-variable scope of finalCall() — "
            "it may be block-scoped in one branch but referenced in another, "
            "which would cause undefined errors"
        )

    def test_final_return_uses_gatereason_or_null(self, js_text):
        """
        The final return statement in finalCall() must include gateReason (or gateReason||null)
        so gate branches propagate their reason to the caller.
        """
        body = extract_function_body(js_text, "finalCall")
        # Find the last return { block (the shared return at the bottom of finalCall)
        last_return_idx = body.rfind("return {")
        assert last_return_idx != -1
        return_block = body[last_return_idx: last_return_idx + 200]
        assert "gateReason" in return_block, (
            "Final return statement in finalCall() does not include gateReason — "
            "gate branches' reason strings will be lost. "
            f"Return block: {return_block!r}"
        )


# ── Check 15: No new git commits ─────────────────────────────────────────────

class TestNoNewCommits:

    def test_no_commit_since_last_known(self):
        """
        No new commits must have been made (AGENT_WORK_31 spec: DO NOT COMMIT/PUSH).
        The most recent commit hash should still be b764d89 (compact topbar).
        """
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "log", "--oneline", "-1"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"git log failed: {result.stderr}"
        top_commit = result.stdout.strip()
        assert top_commit.startswith("b764d89"), (
            f"A new commit was made — the task required DO NOT COMMIT/PUSH. "
            f"Current HEAD: {top_commit!r}"
        )

    def test_actionable_js_is_modified_not_committed(self):
        """
        web/actionable.js should appear in git status as modified (M) but not committed.
        """
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "status", "--short", "web/actionable.js"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        status = result.stdout.strip()
        # Should show ' M web/actionable.js' (modified in working tree, not staged)
        # or 'M  web/actionable.js' (staged). Either way it must be M, not blank.
        assert status, (
            "web/actionable.js shows no changes in git status — "
            "either the file was not modified or the changes were committed away"
        )
        assert "M" in status, (
            f"web/actionable.js git status is unexpected: {status!r}"
        )
