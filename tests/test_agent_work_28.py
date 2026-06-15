"""
Tests for AGENT_WORK_28 — Enrich Technical column with:
  1. A compact sub-line (rr-sub-line div) under the act-badge showing the
     tn_td_action · bb_action · rr_action integer triplet, populated lazily
     on first hover via the _rrDetailCache, guarded by dataset.filled.
  2. Current price (last_price) from state.rows shown prominently in the
     Technical hover tooltip header and in the Levels section label.

Acceptance criteria (from AGENT_WORK_28.md + DEV_HANDOFF.md):
  Check 1  — node --check web/actionable.js exits 0 (no syntax errors).
  Check 2  — rr-sub-line div is present in the rr-action-cell td in renderGrid().
  Check 3  — The triplet (tn_td_action · bb_action · rr_action) is assembled inside
             setupRRActionCol's mouseover handler.
  Check 4  — dataset.filled guard is set (prevents re-render on every hover).
  Check 5  — last_price is looked up from state.rows in setupRRActionCol.
  Check 6  — priceHtml is injected into the tooltip header line.
  Check 7  — Levels section label conditionally appends price via fmtUsd.
  Check 8  — Null-safety: last_price null check uses a conditional (no crash if missing).
  Check 9  — Null-safety: rr-sub-line values use a null-safe formatter (— fallback).
  Check 10 — Other columns' rendering code (Sources, Rules/fires, Final Call) unchanged.
  Check 11 — _rrDetailCache and _fetchRRDetail still present (not broken by edits).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
JS_FILE      = PROJECT_ROOT / "web" / "actionable.js"
HTML_FILE    = PROJECT_ROOT / "web" / "actionable.html"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html_text():
    return HTML_FILE.read_text(encoding="utf-8")


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


def extract_named_section(js: str, fn_name: str) -> str:
    """
    Try to find an arrow function or async event listener block named fn_name,
    falling back to extract_function_body.  Used for handlers embedded in
    addEventListener callbacks.
    """
    try:
        return extract_function_body(js, fn_name)
    except AssertionError:
        return ""


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


# ── Check 2: rr-sub-line div in rr-action-cell td ─────────────────────────────

class TestRrSubLinePlaceholder:
    def test_rr_sub_line_div_present_in_js(self, js_text):
        """renderGrid() must emit a div.rr-sub-line inside the rr-action-cell td."""
        body = extract_function_body(js_text, "renderGrid")
        assert 'rr-sub-line' in body, (
            "renderGrid() does not emit a div.rr-sub-line — sub-line placeholder is missing "
            "from the Technical cell HTML"
        )

    def test_rr_sub_line_inside_rr_action_cell(self, js_text):
        """The rr-sub-line div must appear inside the rr-action-cell td (not elsewhere)."""
        # Find the rr-action-cell td block in the file
        td_start = js_text.find('rr-action-cell')
        assert td_start != -1, "rr-action-cell not found in actionable.js"
        # The rr-sub-line should appear AFTER rr-action-cell definition
        subline_pos = js_text.find('rr-sub-line', td_start)
        assert subline_pos != -1, (
            "rr-sub-line div not found after the rr-action-cell td open tag"
        )

    def test_rr_sub_line_div_tag(self, js_text):
        """The rr-sub-line element must be a <div> tag."""
        # Must be emitted as <div class="rr-sub-line"...>
        assert '<div class="rr-sub-line"' in js_text or "class='rr-sub-line'" in js_text, (
            "rr-sub-line element is not a div — expected <div class='rr-sub-line'...>"
        )

    def test_rr_sub_line_has_style(self, js_text):
        """The rr-sub-line div must have inline style (font-size, color, etc.)."""
        # Look for style on the rr-sub-line div
        pattern = r'rr-sub-line[^>]*style='
        assert re.search(pattern, js_text), (
            "rr-sub-line div does not have an inline style attribute — "
            "sub-line may not appear compact and muted"
        )


# ── Check 3: Triplet (tn_td_action · bb_action · rr_action) in mouseover ──────

class TestTripletInMouseover:
    def test_setup_rr_action_col_exists(self, js_text):
        """setupRRActionCol() must be defined in actionable.js."""
        assert "function setupRRActionCol(" in js_text, (
            "setupRRActionCol function not found in actionable.js"
        )

    def test_tn_td_action_used(self, js_text):
        """setupRRActionCol must reference d.tn_td_action for the triplet sub-line."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "tn_td_action" in body, (
            "setupRRActionCol() does not reference d.tn_td_action — "
            "first triplet value missing from sub-line"
        )

    def test_bb_action_used(self, js_text):
        """setupRRActionCol must reference d.bb_action for the triplet sub-line."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "bb_action" in body, (
            "setupRRActionCol() does not reference d.bb_action — "
            "second triplet value missing from sub-line"
        )

    def test_rr_action_used_in_triplet(self, js_text):
        """setupRRActionCol must reference d.rr_action for the triplet sub-line."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "rr_action" in body, (
            "setupRRActionCol() does not reference d.rr_action — "
            "third triplet value missing from sub-line"
        )

    def test_subline_inner_html_set(self, js_text):
        """setupRRActionCol must set subLine.innerHTML with the triplet."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "subLine" in body and "innerHTML" in body, (
            "setupRRActionCol() does not set subLine.innerHTML — triplet never written to DOM"
        )

    def test_rr_sub_line_queried(self, js_text):
        """setupRRActionCol must query for .rr-sub-line in the cell."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "querySelector('.rr-sub-line')" in body or 'querySelector(".rr-sub-line")' in body, (
            "setupRRActionCol() does not querySelector('.rr-sub-line') — "
            "sub-line element is never found"
        )

    def test_triplet_separator_present(self, js_text):
        """The triplet display must use the '·' separator character."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "·" in body, (
            "setupRRActionCol() does not use '·' as separator between triplet values"
        )

    def test_green_color_for_positive(self, js_text):
        """Positive values must use a green color code in the triplet."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Green: #16a34a or similar
        has_green = "#16a34a" in body or "green" in body.lower()
        assert has_green, (
            "setupRRActionCol() triplet coloring does not include a green color for positive values"
        )

    def test_red_color_for_negative(self, js_text):
        """Negative values must use a red color code in the triplet."""
        body = extract_function_body(js_text, "setupRRActionCol")
        has_red = "#dc2626" in body or "red" in body.lower()
        assert has_red, (
            "setupRRActionCol() triplet coloring does not include a red color for negative values"
        )


# ── Check 4: dataset.filled guard ─────────────────────────────────────────────

class TestDataFilledGuard:
    def test_dataset_filled_set(self, js_text):
        """setupRRActionCol must set subLine.dataset.filled = '1' after populating."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "dataset.filled" in body, (
            "setupRRActionCol() does not set subLine.dataset.filled — "
            "sub-line will be re-rendered on every hover"
        )

    def test_dataset_filled_guards_block(self, js_text):
        """The sub-line population must be inside an 'if (!subLine.dataset.filled)' guard."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # The guard prevents re-rendering: check that dataset.filled is used as a condition
        filled_guard = re.search(
            r'if\s*\(\s*subLine\s*&&\s*!\s*subLine\.dataset\.filled\s*\)|'
            r'if\s*\(\s*!\s*subLine\.dataset\.filled\s*\)',
            body
        )
        assert filled_guard is not None, (
            "setupRRActionCol() does not guard sub-line population with "
            "'if (!subLine.dataset.filled)' — re-renders on every hover"
        )


# ── Check 5: last_price lookup from state.rows ────────────────────────────────

class TestLastPriceLookup:
    def test_state_rows_find(self, js_text):
        """setupRRActionCol must call state.rows.find() to locate the current row."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "state.rows.find(" in body or "state.rows.find (" in body, (
            "setupRRActionCol() does not call state.rows.find() to look up last_price"
        )

    def test_last_price_accessed(self, js_text):
        """setupRRActionCol must access rowData.last_price (or row.last_price)."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "last_price" in body, (
            "setupRRActionCol() does not reference last_price — price not available for tooltip"
        )

    def test_last_price_assigned_to_variable(self, js_text):
        """setupRRActionCol must assign last_price to a local variable for use in template."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Expect something like: const lastPrice = rowData && rowData.last_price != null ? ...
        assert "lastPrice" in body or "last_price" in body, (
            "setupRRActionCol() does not store last_price in a local variable"
        )


# ── Check 6: priceHtml injected into tooltip header ───────────────────────────

class TestPriceInTooltipHeader:
    def test_price_html_variable_defined(self, js_text):
        """setupRRActionCol must define a priceHtml variable."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "priceHtml" in body, (
            "setupRRActionCol() does not define priceHtml — price cannot be inserted in header"
        )

    def test_price_html_uses_fmtUsd(self, js_text):
        """priceHtml must format the price with fmtUsd()."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "fmtUsd(" in body, (
            "setupRRActionCol() priceHtml does not call fmtUsd() — price format inconsistent"
        )

    def test_price_html_injected_in_header(self, js_text):
        """The tooltip header must include ${priceHtml} in the div template."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # The header line with symbol name must also inject priceHtml
        assert "${priceHtml}" in body or "priceHtml}" in body, (
            "setupRRActionCol() tooltip header does not include ${priceHtml} — "
            "price will not appear in tooltip header"
        )

    def test_header_contains_sym_and_price(self, js_text):
        """The header div must contain both the symbol name and priceHtml."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # The header should have escapeHtml(sym) and priceHtml in the same line/section
        header_pattern = re.search(
            r'escapeHtml\(sym\).*?priceHtml|priceHtml.*?escapeHtml\(sym\)',
            body,
            re.DOTALL
        )
        assert header_pattern is not None, (
            "setupRRActionCol() tooltip header does not co-locate escapeHtml(sym) and priceHtml"
        )


# ── Check 7: Levels section label conditionally appends price ─────────────────

class TestLevelsSectionLabel:
    def test_levels_section_with_price(self, js_text):
        """The Levels section label must conditionally include the price."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Should contain something like: sec('Levels' + (lastPrice != null ? ' · Price ' + fmtUsd(lastPrice) : ''))
        assert "Levels" in body, (
            "setupRRActionCol() tooltip does not have a 'Levels' section"
        )
        # Check that the Levels label is dynamic (appends price)
        levels_region = body[body.find("Levels"):]
        has_dynamic = "lastPrice" in levels_region[:200] or "priceHtml" in levels_region[:200] or "fmtUsd" in levels_region[:200]
        assert has_dynamic, (
            "Levels section label in setupRRActionCol() does not conditionally append price — "
            "static 'Levels' text only"
        )

    def test_levels_contains_price_label(self, js_text):
        """The Levels section must include 'Price' text in the conditional."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Search for 'Price' near the Levels section
        levels_idx = body.find("'Levels'")
        if levels_idx == -1:
            levels_idx = body.find('"Levels"')
        assert levels_idx != -1, "Levels section not found in setupRRActionCol()"
        snippet = body[levels_idx:levels_idx + 300]
        assert "Price" in snippet, (
            f"Levels section label does not mention 'Price'. Snippet: {snippet!r}"
        )


# ── Check 8: Null-safety for last_price ──────────────────────────────────────

class TestLastPriceNullSafety:
    def test_null_check_before_use(self, js_text):
        """last_price must be null-checked before use (no crash on missing price)."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Expect: rowData && rowData.last_price != null  OR  lastPrice != null
        null_check = re.search(
            r'last_price\s*!=\s*null|lastPrice\s*!=\s*null|'
            r'rowData\s*&&\s*rowData\.last_price',
            body
        )
        assert null_check is not None, (
            "setupRRActionCol() does not null-check last_price before use — "
            "will crash if price is missing"
        )

    def test_price_html_empty_when_null(self, js_text):
        """priceHtml must be empty string '' when last_price is null."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Ternary: lastPrice != null ? ... : ''
        empty_fallback = re.search(r":\s*['\"]['\"]", body)
        assert empty_fallback is not None, (
            "setupRRActionCol() priceHtml ternary does not have an empty-string fallback — "
            "tooltip header may crash or show 'null'"
        )

    def test_rowdata_null_guarded(self, js_text):
        """state.rows.find() result must be guarded before accessing .last_price."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Guard: rowData && rowData.last_price  OR  rowData?.last_price
        guarded = re.search(
            r'rowData\s*&&\s*rowData\.last_price|rowData\?\.last_price',
            body
        )
        assert guarded is not None, (
            "setupRRActionCol() accesses rowData.last_price without null-guarding rowData — "
            "will crash if symbol is not found in state.rows"
        )


# ── Check 9: Null-safety for rr-sub-line triplet values ───────────────────────

class TestTripletNullSafety:
    def test_null_value_formatter_exists(self, js_text):
        """The triplet helper must handle null values with a '—' fallback."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Look for null-check with em dash fallback: v == null ? '—' : ...
        null_fmt = re.search(r'==\s*null\s*\?\s*[\'"]—[\'"]', body)
        assert null_fmt is not None, (
            "setupRRActionCol() triplet formatter does not provide a '—' fallback for null values — "
            "null scores will display as 'null' in the sub-line"
        )

    def test_subline_element_guarded(self, js_text):
        """The sub-line population block must check that subLine is not null."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # The querySelector result must be checked before use
        guarded = re.search(
            r'if\s*\(\s*subLine\s*&&',
            body
        )
        assert guarded is not None, (
            "setupRRActionCol() does not guard subLine existence before populating — "
            "will crash if .rr-sub-line element is not found"
        )


# ── Check 10: Other columns unchanged ─────────────────────────────────────────

class TestOtherColumnsUnchanged:
    def test_firesCellHtml_still_present(self, js_text):
        """firesCellHtml() must still be defined (Rules column unchanged)."""
        assert "function firesCellHtml(" in js_text, (
            "firesCellHtml() function is missing — Rules column may be broken"
        )

    def test_src_sub_line_html_still_present(self, js_text):
        """_srcSubLineHtml() must still be defined (Sources column unchanged)."""
        assert "function _srcSubLineHtml(" in js_text, (
            "_srcSubLineHtml() function is missing — Sources column sub-line may be broken"
        )

    def test_render_source_pop_still_present(self, js_text):
        """_renderSourcePop() must still be defined (Sources popover unchanged)."""
        assert "function _renderSourcePop(" in js_text, (
            "_renderSourcePop() function is missing — Sources popover may be broken"
        )

    def test_final_call_fn_still_present(self, js_text):
        """finalCall() must still be defined (Final Call column unchanged)."""
        assert "function finalCall(" in js_text, (
            "finalCall() function is missing — Final Call column may be broken"
        )

    def test_action_display_fn_available(self, js_text):
        """actionDisplay() must still be callable (Action column unchanged)."""
        # actionDisplay is defined in actions.js but referenced in actionable.js
        assert "actionDisplay(" in js_text, (
            "actionDisplay() is not referenced in actionable.js — Action column may be broken"
        )

    def test_render_grid_still_present(self, js_text):
        """renderGrid() must still be defined."""
        assert "function renderGrid(" in js_text, (
            "renderGrid() function is missing — table rendering is broken"
        )


# ── Check 11: _rrDetailCache and _fetchRRDetail still intact ──────────────────

class TestRrDetailInfrastructure:
    def test_rr_detail_cache_defined(self, js_text):
        """_rrDetailCache Map must still be defined (lazy fetch infrastructure)."""
        assert "_rrDetailCache" in js_text, (
            "_rrDetailCache is missing from actionable.js — rr-detail lazy cache is broken"
        )

    def test_fetch_rr_detail_defined(self, js_text):
        """_fetchRRDetail() must still be defined."""
        assert "function _fetchRRDetail(" in js_text, (
            "_fetchRRDetail() function is missing — rr-detail API fetch is broken"
        )

    def test_fetch_rr_detail_uses_cache(self, js_text):
        """_fetchRRDetail must check and populate the cache (avoid redundant fetches)."""
        body = extract_function_body(js_text, "_fetchRRDetail")
        assert "_rrDetailCache" in body, (
            "_fetchRRDetail() does not reference _rrDetailCache — caching is broken"
        )

    def test_fetch_rr_detail_called_in_setup(self, js_text):
        """setupRRActionCol must call _fetchRRDetail() in its mouseover handler."""
        body = extract_function_body(js_text, "setupRRActionCol")
        assert "_fetchRRDetail(" in body, (
            "setupRRActionCol() does not call _fetchRRDetail() — "
            "hover tooltip will never load rr-detail data"
        )

    def test_setup_rr_action_col_guards_null_response(self, js_text):
        """setupRRActionCol must guard against a null/falsy response from _fetchRRDetail."""
        body = extract_function_body(js_text, "setupRRActionCol")
        # Expect: if (!d) return;
        null_guard = re.search(r'if\s*\(\s*!d\s*\)\s*return', body)
        assert null_guard is not None, (
            "setupRRActionCol() does not guard against null _fetchRRDetail response — "
            "will crash if rr-detail API returns nothing"
        )
