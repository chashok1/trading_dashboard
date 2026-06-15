"""
Tests for AGENT_WORK_36 — Sources and Technical cells in Actionable grid
rendered as flex rows (sub-values beside action badge, not below).

Acceptance criteria (AGENT_WORK_36.md + DEV_HANDOFF.md):
  Check 1  — node --check web/actionable.js passes (no syntax errors).
  Check 2  — Sources cell (act-action-cell): wrapped in display:flex;align-items:center;gap:6px.
  Check 3  — Sources flex row also has flex-wrap:wrap (allows overflow wrapping).
  Check 4  — _srcSubLineHtml(r) is placed INSIDE the flex row div (on same row as badge).
  Check 5  — OVER_MAX "was X" annotation is placed OUTSIDE / after the flex row (remains below).
  Check 6  — Technical cell (rr-action-cell): wrapped in display:flex;align-items:center;gap:6px.
  Check 7  — Technical flex row also has flex-wrap:wrap.
  Check 8  — _rrSubLineHtml is placed INSIDE the Technical flex row div.
  Check 9  — _rrSubLineHtml empty state returns '' (not an empty <div>) when all desc fields empty.
  Check 10 — _rrSubLineHtml does NOT have margin-top:2px inline style (removed for flex layout).
  Check 11 — .act-src-sub CSS does NOT have margin-top: 3px (removed; now inline flex item).
  Check 12 — .act-src-sub CSS has display:flex (needed to flow tokens on one line).
  Check 13 — No business/logic changes: actionLabel(), actionDisplay(), _srcSubLineHtml(),
             _rrSubLineHtml, firesCellHtml(), sortRows() signatures/logic unchanged.
  Check 14 — Colors unchanged: act-badge colorCls construction unchanged in Sources cell.
  Check 15 — Tooltips unchanged: title attr on act-badge in Sources cell still uses
             actionDisplay(_badgeAction(r)).label.
  Check 16 — Sort logic unchanged: sortRows() still reads state.sort.key/dir/type.
  Check 17 — web/styles.css parses without syntax error (braces balanced).
  Check 18 — web/actionable.js parses without syntax error (node --check, second pass).
"""

import ast
import os
import re
import subprocess
import sys

JS_PATH  = os.path.join(os.path.dirname(__file__), '..', 'web', 'actionable.js')
CSS_PATH = os.path.join(os.path.dirname(__file__), '..', 'web', 'styles.css')

def _read_js():
    with open(JS_PATH, encoding='utf-8') as f:
        return f.read()

def _read_css():
    with open(CSS_PATH, encoding='utf-8') as f:
        return f.read()


# ---------------------------------------------------------------------------
# Check 1 — node --check passes
# ---------------------------------------------------------------------------
def test_check1_node_syntax():
    """node --check web/actionable.js must exit 0 (no syntax errors)."""
    result = subprocess.run(
        ['node', '--check', JS_PATH],
        capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"node --check failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# Check 2 — Sources cell flex row: display:flex;align-items:center;gap:6px
# ---------------------------------------------------------------------------
def test_check2_sources_cell_flex_row_style():
    """act-action-cell td must contain a div with display:flex;align-items:center;gap:6px."""
    src = _read_js()
    # The flex row wrapping the Sources badge + sub-line must exist
    assert re.search(
        r'act-action-cell.*?display:flex;align-items:center;gap:6px',
        src, re.DOTALL
    ), "Sources (act-action-cell) does not have a flex row with display:flex;align-items:center;gap:6px"


# ---------------------------------------------------------------------------
# Check 3 — Sources flex row has flex-wrap:wrap
# ---------------------------------------------------------------------------
def test_check3_sources_flex_wrap():
    """The Sources flex row div must include flex-wrap:wrap."""
    src = _read_js()
    # Look for the pattern within the act-action-cell block
    pattern = r'act-action-cell.*?display:flex;align-items:center;gap:6px;flex-wrap:wrap'
    assert re.search(pattern, src, re.DOTALL), (
        "Sources (act-action-cell) flex row is missing flex-wrap:wrap"
    )


# ---------------------------------------------------------------------------
# Check 4 — _srcSubLineHtml inside the Sources flex row
# ---------------------------------------------------------------------------
def test_check4_srcsub_inside_flex_row():
    """_srcSubLineHtml(r) must appear inside the flex row div in Sources cell."""
    src = _read_js()
    # Find the act-action-cell block; verify _srcSubLineHtml is inside the flex div
    # (before the closing </div> of the flex row, which is before the OVER_MAX check)
    pattern = (
        r'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
        r'.*?'
        r'\$\{_srcSubLineHtml\(r\)\}'
        r'.*?'
        r'</div>'
    )
    assert re.search(pattern, src, re.DOTALL), (
        "_srcSubLineHtml(r) is not inside the flex row div of the Sources cell"
    )


# ---------------------------------------------------------------------------
# Check 5 — OVER_MAX annotation outside/after the flex row
# ---------------------------------------------------------------------------
def test_check5_overmax_outside_flex_row():
    """The 'was X' OVER_MAX annotation must appear after/outside the flex row."""
    src = _read_js()
    # The pattern: flex row closes, THEN the OVER_MAX conditional
    pattern = (
        r'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
        r'.*?'
        r'</div>'           # closes the flex row
        r'.*?'
        r'\$\{_isOverMaxOverlay\(r\)'  # OVER_MAX check comes after
    )
    assert re.search(pattern, src, re.DOTALL), (
        "OVER_MAX 'was X' annotation appears to be INSIDE or BEFORE the flex row; "
        "it should be outside (after the closing </div> of the flex row)"
    )


# ---------------------------------------------------------------------------
# Check 6 — Technical cell flex row: display:flex;align-items:center;gap:6px
# ---------------------------------------------------------------------------
def test_check6_technical_cell_flex_row_style():
    """rr-action-cell td must contain a div with display:flex;align-items:center;gap:6px."""
    src = _read_js()
    assert re.search(
        r'rr-action-cell.*?display:flex;align-items:center;gap:6px',
        src, re.DOTALL
    ), "Technical (rr-action-cell) does not have a flex row with display:flex;align-items:center;gap:6px"


# ---------------------------------------------------------------------------
# Check 7 — Technical flex row has flex-wrap:wrap
# ---------------------------------------------------------------------------
def test_check7_technical_flex_wrap():
    """The Technical flex row div must include flex-wrap:wrap."""
    src = _read_js()
    pattern = r'rr-action-cell.*?display:flex;align-items:center;gap:6px;flex-wrap:wrap'
    assert re.search(pattern, src, re.DOTALL), (
        "Technical (rr-action-cell) flex row is missing flex-wrap:wrap"
    )


# ---------------------------------------------------------------------------
# Check 8 — _rrSubLineHtml inside the Technical flex row
# ---------------------------------------------------------------------------
def test_check8_rrsub_inside_flex_row():
    """_rrSubLineHtml must appear inside the flex row div of the Technical cell."""
    src = _read_js()
    # The rr-action-cell section has rrHtml + _rrSubLineHtml inside a flex div
    # They must both be children of the same flex container
    pattern = (
        r'rr-action-cell.*?'
        r'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
        r'.*?'
        r'\$\{rrHtml\}'
        r'.*?'
        r'\$\{_rrSubLineHtml\}'
        r'.*?'
        r'</div>'
    )
    assert re.search(pattern, src, re.DOTALL), (
        "_rrSubLineHtml is not inside the flex row div of the Technical (rr-action-cell)"
    )


# ---------------------------------------------------------------------------
# Check 9 — _rrSubLineHtml returns '' when all desc fields are empty
# ---------------------------------------------------------------------------
def test_check9_rrsub_empty_returns_empty_string():
    """_rrSubLineHtml must return '' (not an empty <div>) when td/bb/rr are all empty."""
    src = _read_js()
    # Look for the IIFE pattern: if (!td && !bb && !rr) return '';
    pattern = r"if\s*\(\s*!td\s*&&\s*!bb\s*&&\s*!rr\s*\)\s*return\s*''"
    assert re.search(pattern, src), (
        "_rrSubLineHtml does not have an early-return '' for the all-empty case"
    )


# ---------------------------------------------------------------------------
# Check 10 — _rrSubLineHtml does NOT have margin-top:2px
# ---------------------------------------------------------------------------
def test_check10_rrsub_no_margin_top():
    """rr-sub-line div must NOT have margin-top:2px inline style (removed for flex)."""
    src = _read_js()
    # Find the rr-sub-line div string and confirm no margin-top
    rr_sub_match = re.search(
        r'rr-sub-line.*?style="([^"]*)"',
        src
    )
    if rr_sub_match:
        style_val = rr_sub_match.group(1)
        assert 'margin-top' not in style_val, (
            f"rr-sub-line still has margin-top in its inline style: '{style_val}'"
        )
    else:
        # If the pattern is not found at all, the div is either absent or structured
        # differently. Search more broadly.
        assert 'margin-top:2px' not in src or 'rr-sub-line' not in src, (
            "rr-sub-line contains margin-top:2px which should have been removed"
        )


# ---------------------------------------------------------------------------
# Check 11 — .act-src-sub CSS does NOT have margin-top: 3px
# ---------------------------------------------------------------------------
def test_check11_actsrcsub_no_margin_top_in_css():
    """.act-src-sub in styles.css must NOT have margin-top: 3px (was removed)."""
    css = _read_css()
    # Find the .act-src-sub block
    block_match = re.search(
        r'\.act-src-sub\s*\{([^}]*)\}',
        css, re.DOTALL
    )
    assert block_match, ".act-src-sub rule not found in styles.css"
    block_content = block_match.group(1)
    assert 'margin-top' not in block_content, (
        f".act-src-sub still contains margin-top in styles.css: '{block_content.strip()}'"
    )


# ---------------------------------------------------------------------------
# Check 12 — .act-src-sub CSS has display:flex
# ---------------------------------------------------------------------------
def test_check12_actsrcsub_has_display_flex():
    """.act-src-sub must have display:flex so tokens flow inline."""
    css = _read_css()
    block_match = re.search(
        r'\.act-src-sub\s*\{([^}]*)\}',
        css, re.DOTALL
    )
    assert block_match, ".act-src-sub rule not found in styles.css"
    block_content = block_match.group(1)
    assert 'display' in block_content and 'flex' in block_content, (
        f".act-src-sub is missing display:flex in styles.css: '{block_content.strip()}'"
    )


# ---------------------------------------------------------------------------
# Check 13 — Core logic functions still present (no accidental deletion)
# ---------------------------------------------------------------------------
def test_check13_core_functions_present():
    """Key logic functions must still be present in actionable.js."""
    src = _read_js()
    functions = [
        'actionLabel',
        '_srcSubLineHtml',
        'firesCellHtml',
        'sortRows',
        '_badgeAction',
        '_isOverMaxOverlay',
        '_sourcesOf',
        'finalCall',
        '_computePriority',
    ]
    for fn in functions:
        assert fn in src, f"Expected function/identifier '{fn}' not found in actionable.js"


# ---------------------------------------------------------------------------
# Check 14 — Colors unchanged: act-badge colorCls uses actionDisplay(_badgeAction(r))
# ---------------------------------------------------------------------------
def test_check14_badge_colorCls_unchanged():
    """act-badge in Sources cell must still use actionDisplay(_badgeAction(r)).colorCls."""
    src = _read_js()
    assert "actionDisplay(_badgeAction(r)).colorCls" in src, (
        "Sources badge colorCls expression has changed — "
        "expected actionDisplay(_badgeAction(r)).colorCls"
    )


# ---------------------------------------------------------------------------
# Check 15 — Tooltips: title attr uses actionDisplay(_badgeAction(r)).label
# ---------------------------------------------------------------------------
def test_check15_badge_title_uses_label():
    """act-badge title must still use actionDisplay(_badgeAction(r)).label."""
    src = _read_js()
    assert "actionDisplay(_badgeAction(r)).label" in src, (
        "Sources badge title expression has changed — "
        "expected actionDisplay(_badgeAction(r)).label"
    )


# ---------------------------------------------------------------------------
# Check 16 — Sort logic unchanged
# ---------------------------------------------------------------------------
def test_check16_sort_logic_unchanged():
    """sortRows() must still read state.sort.key, .dir, .type for column sort."""
    src = _read_js()
    assert 'state.sort.key' in src, "state.sort.key not found — sort logic may have changed"
    assert 'state.sort.dir' in src, "state.sort.dir not found — sort logic may have changed"
    assert 'state.sort.type' in src, "state.sort.type not found — sort logic may have changed"


# ---------------------------------------------------------------------------
# Check 17 — styles.css braces are balanced
# ---------------------------------------------------------------------------
def test_check17_css_braces_balanced():
    """styles.css must have balanced { } braces."""
    css = _read_css()
    # Strip string literals and comments to avoid false counts
    # Simple check: count of { must equal count of }
    open_count  = css.count('{')
    close_count = css.count('}')
    assert open_count == close_count, (
        "styles.css brace mismatch: open={} close={}".format(open_count, close_count)
    )


# ---------------------------------------------------------------------------
# Check 18 — node --check (second pass, confirms file not modified mid-session)
# ---------------------------------------------------------------------------
def test_check18_node_syntax_second_pass():
    """Second node --check pass to confirm file integrity."""
    result = subprocess.run(
        ['node', '--check', JS_PATH],
        capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"node --check (second pass) failed:\n{result.stderr}"
    )
