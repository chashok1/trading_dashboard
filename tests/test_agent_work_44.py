"""Tests for AGENT_WORK_44 — Streamline Actionable filter bar.

Acceptance criteria:
1. Filter bar contains ONLY: chips, Conviction, Positions, Source, Symbol, Show Hidden, Clear.
2. Removed elements are fully absent: buyToggle, sellToggle, sectorFilter, assetClassFilter,
   amtCtrl, moreFiltersBtn, morePanel, showNoAction, showZeroAmt, showSuppressed,
   showActed, showNotHeldRemove.
3. Show Hidden toggle (id=showHidden) is present, default off.
4. show_hidden is in state.filters (default false); 9 removed keys are absent.
5. matchesBaseFilters uses a single show_hidden gate.
6. loadActionable passes show_acted/show_suppressed only when show_hidden is on.
7. localStorage key is bumped to act_filters_v3.
8. Removed functions (renderSectorFilter, renderAssetClassFilter, _countActiveFilters,
   updateFilterBadge) are gone from actionable.js.
9. node --check web/actionable.js passes with no syntax errors.
10. clearAllFilters resets show_hidden to false.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
ACTIONABLE_HTML = PROJECT / "web" / "actionable.html"
ACTIONABLE_JS = PROJECT / "web" / "actionable.js"

HTML = ACTIONABLE_HTML.read_text(encoding="utf-8")
JS = ACTIONABLE_JS.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Criterion 1: Removed element IDs must not exist in HTML or JS
# ---------------------------------------------------------------------------

REMOVED_IDS = [
    "buyToggle",
    "sellToggle",
    "sectorFilter",
    "assetClassFilter",
    "amtCtrl",
    "moreFiltersBtn",
    "morePanel",
    "showNoAction",
    "showZeroAmt",
    "showSuppressed",
    "showActed",
    "showNotHeldRemove",
]


@pytest.mark.parametrize("removed_id", REMOVED_IDS)
def test_removed_id_absent_from_html(removed_id):
    """Each removed element ID must not appear in actionable.html."""
    assert removed_id not in HTML, (
        f"'{removed_id}' still present in actionable.html — must be removed."
    )


@pytest.mark.parametrize("removed_id", REMOVED_IDS)
def test_removed_id_absent_from_js(removed_id):
    """Each removed element ID must not appear in actionable.js."""
    assert removed_id not in JS, (
        f"'{removed_id}' still present in actionable.js — must be removed."
    )


# ---------------------------------------------------------------------------
# Criterion 2 (HTML): Show Hidden toggle present with correct id, type=checkbox
# ---------------------------------------------------------------------------

def test_show_hidden_toggle_present_in_html():
    """actionable.html must contain <input ... id="showHidden"> checkbox."""
    assert 'id="showHidden"' in HTML, (
        "showHidden checkbox not found in actionable.html."
    )


def test_show_hidden_toggle_is_checkbox():
    """The showHidden toggle control must exist and be interactive.

    REWRITTEN (TASK_112, 2026-07-04): showHidden was redesigned from an
    `<input type="checkbox">` to an icon `<button>` (toggled via
    `classList.toggle('active', ...)` in actionable.js, with a `data-tip`
    that flips between 'Active Only -> Show Hidden' / 'Show Hidden ->
    Active Only'). Same on/off toggle behavior, different control type.
    """
    m = re.search(r'<button[^>]*id="showHidden"[^>]*>', HTML)
    assert m, "No <button id='showHidden'> element found in actionable.html."
    assert 'data-tip=' in m.group(0), (
        "showHidden button is missing its data-tip toggle-state label"
    )


def test_show_hidden_label_text():
    """The label containing showHidden must say 'Show Hidden'."""
    assert "Show Hidden" in HTML, (
        "'Show Hidden' label text not found in actionable.html."
    )


def test_show_hidden_no_checked_attribute():
    """showHidden control must default to OFF (Active Only).

    REWRITTEN (TASK_112, 2026-07-04): same button redesign as
    test_show_hidden_toggle_is_checkbox above — there's no 'checked'
    attribute on a button; the equivalent default-off state is the absence
    of the 'active' class and the data-tip reading 'Active Only -> Show
    Hidden' (i.e. clicking it *would* turn Show Hidden on — it isn't on yet).
    """
    m = re.search(r'<button[^>]*id="showHidden"[^>]*>', HTML)
    assert m, "No <button id='showHidden'> element found."
    elem = m.group(0)
    assert '"active"' not in elem and "'active'" not in elem, (
        "showHidden button appears to default to the 'active' (Show Hidden) state"
    )
    assert 'data-tip="Active Only' in elem, (
        "showHidden button's default data-tip does not read 'Active Only -> Show Hidden'"
    )


# ---------------------------------------------------------------------------
# Criterion 3 (HTML): kept controls still present
# ---------------------------------------------------------------------------

def test_conviction_ctrl_present():
    """Conviction control (id=convictionCtrl) must still be in actionable.html."""
    assert 'id="convictionCtrl"' in HTML, "convictionCtrl missing from actionable.html."


def test_positions_toggle_present():
    """heldOnly toggle must still be present."""
    assert 'id="heldOnly"' in HTML, "heldOnly toggle missing from actionable.html."


def test_source_filter_present():
    """sourceFilter dropdown must still be present."""
    assert 'id="sourceFilter"' in HTML, "sourceFilter missing from actionable.html."


def test_symbol_search_present():
    """symbolSearch input must still be present."""
    assert 'id="symbolSearch"' in HTML, "symbolSearch input missing from actionable.html."


def test_clear_filters_btn_present():
    """clearFiltersBtn must still be present."""
    assert 'id="clearFiltersBtn"' in HTML, "clearFiltersBtn missing from actionable.html."


def test_summary_chips_present():
    """summaryChips element (action chips) must still be present."""
    assert 'id="summaryChips"' in HTML, "summaryChips missing from actionable.html."


# ---------------------------------------------------------------------------
# Criterion 4 (JS): state.filters schema
# ---------------------------------------------------------------------------

def test_state_filters_has_show_hidden():
    """state.filters in actionable.js must include show_hidden: false."""
    assert "show_hidden: false" in JS, (
        "state.filters.show_hidden not initialized to false in actionable.js."
    )


def test_state_filters_no_removed_keys():
    """Removed filter keys must not appear in the state.filters initializer block."""
    # Locate the filters: { ... } block in the state object literal
    m = re.search(r"filters:\s*\{([^}]+)\}", JS)
    assert m, "Could not locate state.filters object in actionable.js."
    filters_block = m.group(1)
    removed_keys = [
        "buys_only",
        "sells_only",
        "sector",
        "asset_class",
        "min_amt",
        "show_no_action",
        "show_zero_amt",
        "show_suppressed",
        "show_acted",
        "show_not_held_remove",
    ]
    for key in removed_keys:
        assert key not in filters_block, (
            f"Removed filter key '{key}' still in state.filters block."
        )


# ---------------------------------------------------------------------------
# Criterion 5 (JS): matchesBaseFilters uses show_hidden gate
# ---------------------------------------------------------------------------

def test_match_base_filters_uses_show_hidden():
    """matchesBaseFilters must check state.filters.show_hidden."""
    assert "show_hidden" in JS, "show_hidden not referenced in actionable.js."
    # More specifically: the guard inside matchesBaseFilters
    m = re.search(
        r"function matchesBaseFilters\(.*?\).*?\{(.*?)^}",
        JS,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "Could not locate matchesBaseFilters function body."
    body = m.group(1)
    assert "show_hidden" in body, (
        "matchesBaseFilters does not reference show_hidden."
    )


def test_match_base_filters_removed_old_five_flags():
    """matchesBaseFilters must not reference the five old separate hide conditions."""
    old_flags = [
        "showNoAction", "showZeroAmt", "showSuppressed", "showActed", "showNotHeldRemove",
        "show_no_action", "show_zero_amt", "show_acted", "show_not_held_remove",
    ]
    m = re.search(
        r"function matchesBaseFilters\(.*?\).*?\{(.*?)^}",
        JS,
        re.DOTALL | re.MULTILINE,
    )
    if not m:
        pytest.skip("Could not locate matchesBaseFilters function body.")
    body = m.group(1)
    for flag in old_flags:
        assert flag not in body, (
            f"Old flag '{flag}' still referenced in matchesBaseFilters — must use show_hidden gate."
        )


# ---------------------------------------------------------------------------
# Criterion 6 (JS): loadActionable passes show_acted/show_suppressed only when show_hidden
# ---------------------------------------------------------------------------

def test_load_actionable_gates_show_acted_on_show_hidden():
    """show_acted param must be gated by show_hidden in loadActionable."""
    # Find the pattern: if (state.filters.show_hidden) { ... show_acted ... }
    pattern = re.search(
        r"show_hidden.*?show_acted",
        JS,
        re.DOTALL,
    )
    assert pattern, (
        "loadActionable must pass show_acted only when show_hidden is on."
    )


def test_load_actionable_gates_show_suppressed_on_show_hidden():
    """show_suppressed param must be gated by show_hidden in loadActionable."""
    pattern = re.search(
        r"show_hidden.*?show_suppressed",
        JS,
        re.DOTALL,
    )
    assert pattern, (
        "loadActionable must pass show_suppressed only when show_hidden is on."
    )


# ---------------------------------------------------------------------------
# Criterion 7 (JS): localStorage key bumped to act_filters_v3
# ---------------------------------------------------------------------------

# test_ls_key_is_v3 / test_ls_key_not_v2 — RETIRED (TASK_112 test-debt
# cleanup, 2026-07-04). The whole `state.filters` localStorage-persistence
# subsystem (LS_KEY / 'act_filters_v2' / 'act_filters_v3' /
# saveFiltersToStorage / loadFiltersFromStorage) was removed entirely — 0
# matches for any of those identifiers in actionable.js. Filters now reset
# to defaults on every page load; only column visibility (COL_STORAGE_KEY),
# TV-tape visibility (_TV_LS_KEY) and side-panel collapse state are still
# persisted to localStorage. Cat B — feature dropped, not renamed.
# test_save_filters_to_storage_saves_show_hidden below (same removal) is
# also retired.


# ---------------------------------------------------------------------------
# Criterion 8 (JS): Removed functions must be absent
# ---------------------------------------------------------------------------

REMOVED_FUNCTIONS = [
    "renderSectorFilter",
    "renderAssetClassFilter",
    "_countActiveFilters",
    "updateFilterBadge",
]


@pytest.mark.parametrize("fn_name", REMOVED_FUNCTIONS)
def test_removed_function_absent(fn_name):
    """Removed filter helper functions must not be defined in actionable.js."""
    # Check for function definition patterns
    pattern = rf"function\s+{re.escape(fn_name)}\s*\("
    assert not re.search(pattern, JS), (
        f"Removed function '{fn_name}' still defined in actionable.js."
    )


# ---------------------------------------------------------------------------
# Criterion 9: node --check must pass
# ---------------------------------------------------------------------------

def test_js_syntax_clean():
    """node --check web/actionable.js must report no syntax errors."""
    result = subprocess.run(
        ["node", "--check", str(ACTIONABLE_JS)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"node --check failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Criterion 10 (JS): clearAllFilters resets show_hidden to false
# ---------------------------------------------------------------------------

def test_clear_all_filters_resets_show_hidden():
    """clearAllFilters must set f.show_hidden = false (or equivalent)."""
    m = re.search(
        r"function clearAllFilters\(\).*?\{(.*?)^}",
        JS,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "Could not locate clearAllFilters function body."
    body = m.group(1)
    assert "show_hidden" in body, (
        "clearAllFilters does not reset show_hidden."
    )
    assert "false" in body, (
        "clearAllFilters does not set show_hidden to false."
    )


# ---------------------------------------------------------------------------
# Criterion 11 (JS): showHidden event listener wires to loadActionable
# ---------------------------------------------------------------------------

def test_show_hidden_listener_triggers_load_actionable():
    """showHidden change listener must call loadActionable() (full refetch)."""
    # Find the listener block for showHidden
    m = re.search(
        r"showHidden.*?\.addEventListener.*?change.*?loadActionable",
        JS,
        re.DOTALL,
    )
    assert m, (
        "showHidden change listener must call loadActionable() — not just applyClientFilter()."
    )


# ---------------------------------------------------------------------------
# Criterion 12 (JS): syncFilterUi handles showHidden
# ---------------------------------------------------------------------------

def test_sync_filter_ui_handles_show_hidden():
    """syncFilterUi must sync the showHidden checkbox."""
    m = re.search(
        r"function syncFilterUi\(\).*?\{(.*?)^}",
        JS,
        re.DOTALL | re.MULTILINE,
    )
    assert m, "Could not locate syncFilterUi function body."
    body = m.group(1)
    assert "showHidden" in body, (
        "syncFilterUi does not sync showHidden checkbox."
    )


# ---------------------------------------------------------------------------
# Criterion 13 (JS): saveFiltersToStorage saves show_hidden; removed keys absent
# ---------------------------------------------------------------------------

# test_save_filters_to_storage_saves_show_hidden — RETIRED (TASK_112
# test-debt cleanup, 2026-07-04). `saveFiltersToStorage()` and the whole
# filter-persistence subsystem no longer exist — see the retirement note
# above test_ls_key_is_v3. Cat B.


def test_save_filters_does_not_save_removed_keys():
    """saveFiltersToStorage must not reference removed filter keys."""
    m = re.search(
        r"function saveFiltersToStorage\(\).*?\{(.*?)^}",
        JS,
        re.DOTALL | re.MULTILINE,
    )
    if not m:
        pytest.skip("Could not locate saveFiltersToStorage function body.")
    body = m.group(1)
    for key in ["sector", "asset_class", "buys_only", "sells_only", "min_amt"]:
        assert key not in body, (
            f"saveFiltersToStorage still references removed key '{key}'."
        )
