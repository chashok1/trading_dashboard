"""
Tests for AGENT_WORK_33 — Replace numeric sub-value (9/0/8) in TrTnBBRskRng column
with readable TnTd/BB/RR text descriptions.

Acceptance criteria (AGENT_WORK_33.md + DEV_HANDOFF.md):
  Check 1  — node --check web/actionable.js exits 0 (no syntax errors).
  Check 2  — python ast.parse on api/routers/dash.py succeeds.
  Check 3  — /api/actionable SELECT contains tn_td_rule_desc AS tn_td_desc.
  Check 4  — /api/actionable SELECT contains bb_rng_strk_desc AS bb_desc.
  Check 5  — /api/actionable SELECT contains rr.rr_desc (bare, no alias needed).
  Check 6  — The JOIN to drv_tn_td_bb_rr is present and aliased 'rr'.
  Check 7  — _rrSubLineHtml IIFE exists in actionable.js.
  Check 8  — _rrSubLineHtml reads r.tn_td_desc from the row.
  Check 9  — _rrSubLineHtml reads r.bb_desc from the row.
  Check 10 — _rrSubLineHtml reads r.rr_desc from the row.
  Check 11 — _rrSubLineHtml renders "TnTd: " label.
  Check 12 — _rrSubLineHtml renders "BB: " label.
  Check 13 — _rrSubLineHtml renders "RR: " label.
  Check 14 — _rrSubLineHtml uses ~9px font-size.
  Check 15 — _rrSubLineHtml sets data-filled="1" when descriptions are present.
  Check 16 — Hover code guards sub-line update with !subLine.dataset.filled.
  Check 17 — The rendered sub-line div uses class rr-sub-line.
  Check 18 — The numeric pattern 9/0/8 is NOT the default sub-value render.
  Check 19 — drv_tn_td_bb_rr table in baseline.sql has tn_td_rule_desc column.
  Check 20 — drv_tn_td_bb_rr table in baseline.sql has bb_rng_strk_desc column.
  Check 21 — drv_tn_td_bb_rr table in baseline.sql has rr_desc column.
  Check 22 — Other columns (Sources / Final Call / Position) are not disturbed.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
JS_FILE      = PROJECT_ROOT / "web" / "actionable.js"
PY_FILE      = PROJECT_ROOT / "api" / "routers" / "dash.py"
SQL_FILE     = PROJECT_ROOT / "db" / "baseline.sql"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def py_text():
    return PY_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_text():
    return SQL_FILE.read_text(encoding="utf-8")


# ── Syntax checks ──────────────────────────────────────────────────────────────

class TestSyntax:
    def test_actionable_js_node_check(self):
        """Check 1 — node --check web/actionable.js exits 0."""
        result = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"node --check failed:\n{result.stderr}"
        )

    def test_dash_py_ast_parse(self, py_text):
        """Check 2 — ast.parse on api/routers/dash.py succeeds."""
        try:
            ast.parse(py_text)
        except SyntaxError as e:
            pytest.fail(f"ast.parse failed on dash.py: {e}")


# ── API query field verification ───────────────────────────────────────────────

class TestApiQueryFields:
    def test_tn_td_desc_in_select(self, py_text):
        """Check 3 — SELECT contains tn_td_rule_desc AS tn_td_desc."""
        assert "tn_td_rule_desc AS tn_td_desc" in py_text, (
            "Expected 'tn_td_rule_desc AS tn_td_desc' in /api/actionable SELECT"
        )

    def test_bb_desc_in_select(self, py_text):
        """Check 4 — SELECT contains bb_rng_strk_desc AS bb_desc."""
        assert "bb_rng_strk_desc AS bb_desc" in py_text, (
            "Expected 'bb_rng_strk_desc AS bb_desc' in /api/actionable SELECT"
        )

    def test_rr_desc_in_select(self, py_text):
        """Check 5 — SELECT contains rr.rr_desc."""
        assert "rr.rr_desc" in py_text, (
            "Expected 'rr.rr_desc' in /api/actionable SELECT"
        )

    def test_drv_tn_td_bb_rr_join_present(self, py_text):
        """Check 6 — LEFT JOIN to drv_tn_td_bb_rr aliased as rr is present."""
        assert re.search(
            r"LEFT JOIN drv_tn_td_bb_rr\s+rr",
            py_text
        ), "Expected 'LEFT JOIN drv_tn_td_bb_rr rr' in the actionable query"

    def test_three_new_fields_adjacent_to_existing_rr_action(self, py_text):
        """All three new fields appear near rr.td_tn_bb_action_desc (already existing join)."""
        # rr.td_tn_bb_action_desc AS rr_action was already there; new fields piggyback
        assert "rr.td_tn_bb_action_desc AS rr_action" in py_text, (
            "The existing rr_action alias must still be present"
        )
        # The three new fields should all appear in the same SELECT block
        tn = py_text.find("rr.tn_td_rule_desc AS tn_td_desc")
        bb = py_text.find("rr.bb_rng_strk_desc AS bb_desc")
        rr = py_text.find("rr.rr_desc")
        assert all(pos != -1 for pos in [tn, bb, rr]), (
            "All three new SELECT fields must be present"
        )
        # They should all be within 500 chars of each other (same SELECT block)
        positions = sorted([tn, bb, rr])
        assert positions[-1] - positions[0] < 500, (
            "New fields should be grouped together in the SELECT"
        )


# ── Frontend _rrSubLineHtml logic verification ─────────────────────────────────

class TestRrSubLineHtml:
    def test_iife_exists(self, js_text):
        """Check 7 — _rrSubLineHtml IIFE is declared in actionable.js."""
        assert "const _rrSubLineHtml = (() => {" in js_text, (
            "Expected _rrSubLineHtml IIFE declaration"
        )

    def test_reads_tn_td_desc(self, js_text):
        """Check 8 — IIFE reads r.tn_td_desc."""
        assert "r.tn_td_desc" in js_text, (
            "Expected r.tn_td_desc in _rrSubLineHtml"
        )

    def test_reads_bb_desc(self, js_text):
        """Check 9 — IIFE reads r.bb_desc."""
        assert "r.bb_desc" in js_text, (
            "Expected r.bb_desc in _rrSubLineHtml"
        )

    def test_reads_rr_desc(self, js_text):
        """Check 10 — IIFE reads r.rr_desc."""
        assert "r.rr_desc" in js_text, (
            "Expected r.rr_desc in _rrSubLineHtml"
        )

    def test_renders_tntd_label(self, js_text):
        """Check 11 — renders 'TnTd: ' label."""
        assert "TnTd: " in js_text, (
            "Expected 'TnTd: ' label in _rrSubLineHtml"
        )

    def test_renders_bb_label(self, js_text):
        """Check 12 — renders 'BB: ' label."""
        assert "'BB: '" in js_text or '"BB: "' in js_text, (
            "Expected 'BB: ' label in _rrSubLineHtml"
        )

    def test_renders_rr_label(self, js_text):
        """Check 13 — renders 'RR: ' label."""
        assert "'RR: '" in js_text or '"RR: "' in js_text, (
            "Expected 'RR: ' label in _rrSubLineHtml"
        )

    def test_uses_9px_font(self, js_text):
        """Check 14 — _rrSubLineHtml uses font-size:9px (or similar small size)."""
        # Look for font-size:9px or font-size: 9px within the IIFE block
        iife_start = js_text.find("const _rrSubLineHtml = (() => {")
        iife_end   = js_text.find("})();", iife_start)
        assert iife_end > iife_start, "Could not locate _rrSubLineHtml IIFE end"
        iife_block = js_text[iife_start:iife_end]
        assert re.search(r"font-size\s*:\s*9px", iife_block), (
            "Expected font-size:9px in _rrSubLineHtml block"
        )

    def test_sets_data_filled_1(self, js_text):
        """Check 15 — IIFE sets data-filled="1" when descriptions are present."""
        assert 'data-filled="1"' in js_text, (
            "Expected data-filled=\"1\" attribute in _rrSubLineHtml"
        )

    def test_hover_guard_uses_dataset_filled(self, js_text):
        """Check 16 — Hover handler only updates sub-line when !subLine.dataset.filled."""
        assert "!subLine.dataset.filled" in js_text, (
            "Expected hover guard '!subLine.dataset.filled' to prevent overwrite"
        )

    def test_rr_sub_line_class_used(self, js_text):
        """Check 17 — The rendered sub-line div uses class 'rr-sub-line'."""
        # Count occurrences — should appear in both _rrSubLineHtml and the hover code
        count = js_text.count("rr-sub-line")
        assert count >= 2, (
            f"Expected 'rr-sub-line' to appear at least twice; found {count}"
        )

    def test_raw_9_0_8_pattern_not_the_default_subvalue(self, js_text):
        """Check 18 — The old 9/0/8 numeric pattern is NOT the default sub-value render."""
        # The sub-value should NOT produce hardcoded numbers like "9/0/8" or
        # the old pattern "tn_td_action / bb_action / rr_action" as the visible text
        # when descriptions are available. Instead it uses labeled text.
        # The numeric fallback (in the hover) is fine but should be behind the guard.
        iife_start = js_text.find("const _rrSubLineHtml = (() => {")
        iife_end   = js_text.find("})();", iife_start)
        iife_block = js_text[iife_start:iife_end]
        # The IIFE should not output raw action-score numbers (like 9 / 0 / 8)
        # without labels. Verify TnTd: label IS present as the display format.
        assert "TnTd: " in iife_block, (
            "The IIFE should render 'TnTd: ' label, not raw numbers"
        )
        # Verify the IIFE does NOT attempt to use tn_td_action (numeric score) directly
        assert "tn_td_action" not in iife_block, (
            "The IIFE must not reference numeric tn_td_action; it should use tn_td_desc"
        )

    def test_iife_result_is_interpolated_into_cell(self, js_text):
        """_rrSubLineHtml is used in the TD cell template literal."""
        assert "${_rrSubLineHtml}" in js_text, (
            "Expected ${_rrSubLineHtml} to be interpolated into the rr-action-cell"
        )


# ── Database schema verification ───────────────────────────────────────────────

class TestDatabaseSchema:
    def test_drv_tn_td_bb_rr_table_defined(self, sql_text):
        """baseline.sql defines drv_tn_td_bb_rr table."""
        assert "CREATE TABLE IF NOT EXISTS drv_tn_td_bb_rr" in sql_text, (
            "Expected drv_tn_td_bb_rr table definition in baseline.sql"
        )

    def test_tn_td_rule_desc_column_exists(self, sql_text):
        """Check 19 — drv_tn_td_bb_rr has tn_td_rule_desc column."""
        assert "tn_td_rule_desc" in sql_text, (
            "Expected tn_td_rule_desc column in drv_tn_td_bb_rr"
        )

    def test_bb_rng_strk_desc_column_exists(self, sql_text):
        """Check 20 — drv_tn_td_bb_rr has bb_rng_strk_desc column."""
        assert "bb_rng_strk_desc" in sql_text, (
            "Expected bb_rng_strk_desc column in drv_tn_td_bb_rr"
        )

    def test_rr_desc_column_exists(self, sql_text):
        """Check 21 — drv_tn_td_bb_rr has rr_desc column."""
        # Verify it is under the drv_tn_td_bb_rr block
        table_start = sql_text.find("CREATE TABLE IF NOT EXISTS drv_tn_td_bb_rr")
        table_end   = sql_text.find("PRIMARY KEY (as_of_date, tos_symbol)", table_start)
        table_block = sql_text[table_start:table_end + 50]
        assert "rr_desc" in table_block, (
            "Expected rr_desc column in drv_tn_td_bb_rr table definition"
        )


# ── Other columns not disturbed ────────────────────────────────────────────────

class TestOtherColumnsIntact:
    def test_src_sub_line_still_present(self, js_text):
        """Check 22a — Source sub-line (_srcSubLineHtml) is still present."""
        assert "_srcSubLineHtml" in js_text, (
            "Source sub-line function _srcSubLineHtml was removed — regression"
        )

    def test_final_call_html_still_present(self, js_text):
        """Check 22b — _finalCallHtml function is still present."""
        assert "_finalCallHtml" in js_text, (
            "_finalCallHtml function was removed — regression"
        )

    def test_fires_cell_html_still_present(self, js_text):
        """Check 22c — firesCellHtml for the Rules column is still present."""
        assert "firesCellHtml" in js_text, (
            "firesCellHtml function was removed — regression"
        )

    def test_conviction_html_still_present(self, js_text):
        """Check 22d — _convictionHtml is still present."""
        assert "_convictionHtml" in js_text, (
            "_convictionHtml function was removed — regression"
        )

    def test_existing_rr_action_alias_intact(self, py_text):
        """Check 22e — rr.td_tn_bb_action_desc AS rr_action still in the SELECT."""
        assert "rr.td_tn_bb_action_desc AS rr_action" in py_text, (
            "The pre-existing rr_action alias was removed — regression in dash.py"
        )

    def test_drv_actionable_join_intact(self, py_text):
        """Check 22f — FROM drv_actionable a is still the base table."""
        assert "FROM drv_actionable a" in py_text, (
            "drv_actionable base table removed from query — regression"
        )

    def test_drv_quote_join_intact(self, py_text):
        """Check 22g — LEFT JOIN drv_quote q is still in the SELECT."""
        assert "LEFT JOIN drv_quote q" in py_text, (
            "drv_quote join removed — regression in dash.py"
        )
