"""
Tests for AGENT_WORK_3 — TASK_61: RVOL magnitude circle on the Actionable grid.

Acceptance criteria (from TASK_61_rvol_magnitude_circle.md and DEV_HANDOFF.md):

  Part A (API / DB)
    A1  — drv_tw has columns w_vlm_expn_ratio and w_prior_day_vlm_expn_ratio in baseline.sql
    A2  — /api/actionable query in dash.py joins drv_tw (LATERAL) and selects rvol+rvol_prior
    A3  — dash.py aliases w_vlm_expn_ratio AS rvol and w_prior_day_vlm_expn_ratio AS rvol_prior
    A4  — dash.py python-syntax clean

  Part B (front-end)
    B1  — _common.js has var _RVOL_BANDS with correct 5-band array
    B2  — _common.js has var _RVOL_FLAT = 0.10
    B3  — _common.js defines function rvolDot(value, prior, opts)
    B4  — rvolDot exposes window.rvolDot
    B5  — rvolDot is also in window.td_common object
    B6  — Band 0: v < 0.5 → hollow, color #B4B2A9  (filled=false)
    B7  — Band 1: 0.5 <= v < 0.8 → hollow, color #888780  (filled=false)
    B8  — Band 2: 0.8 <= v < 1.2 → solid, color #D3D1C7  (filled=true)
    B9  — Band 3: 1.2 <= v < 1.8 → solid, color #EF9F27  (filled=true)
    B10 — Band 4: v >= 1.8 → solid, color #639922  (filled=true)
    B11 — null value → dotted ring with stroke-dasharray
    B12 — caret up path (M15 6 L12 1 L18 1 Z) when dir='up'
    B13 — caret down path (M15 1 L12 6 L18 6 Z) when dir='down'
    B14 — flat dash rect when dir='flat'
    B15 — caret fill colors: up=#3B6D11, down=#A32D2D, flat=#888780
    B16 — aria-label includes RVOL value with × unit
    B17 — title matches aria-label
    B18 — _common.js node --check passes
    B19 — actionable.js node --check passes

  Part C (actionable.html / actionable.js column wiring)
    C1  — actionable.html has <th data-key="rvol" data-type="num"> header
    C2  — header text is "Vol"
    C3  — .rvol-cell CSS rule present in actionable.html
    C4  — actionable.js has <td class="num rvol-cell"> row cell
    C5  — cell title shows r.rvol.toFixed(2)+'x' when rvol != null
    C6  — cell calls rvolDot(r.rvol, r.rvol_prior)
    C7  — column header has class="num sortable"

  DEV_HANDOFF
    D1  — DEV_HANDOFF.md last non-blank line is ALL_DONE
    D2  — DEV_HANDOFF.md mentions rvol / w_vlm_expn_ratio
    D3  — DEV_HANDOFF.md references AGENT_WORK_3
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

DASH_PY          = PROJECT / "api"  / "routers" / "dash.py"
COMMON_JS        = PROJECT / "web"  / "_common.js"
ACTIONABLE_JS    = PROJECT / "web"  / "actionable.js"
ACTIONABLE_HTML  = PROJECT / "web"  / "actionable.html"
BASELINE_SQL     = PROJECT / "db"   / "baseline.sql"
DEV_HANDOFF      = PROJECT / "DEV_HANDOFF.md"


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1")


# ---------------------------------------------------------------------------
# Part A — DB/API: dash.py
# ---------------------------------------------------------------------------

class TestPartA_API:
    """A: /api/actionable surfaces rvol + rvol_prior from drv_tw."""

    def test_A1_drv_tw_has_rvol_column(self):
        sql = _read(BASELINE_SQL)
        assert "w_vlm_expn_ratio" in sql, \
            "baseline.sql must declare w_vlm_expn_ratio for drv_tw"

    def test_A1b_drv_tw_has_prior_rvol_column(self):
        sql = _read(BASELINE_SQL)
        assert "w_prior_day_vlm_expn_ratio" in sql, \
            "baseline.sql must declare w_prior_day_vlm_expn_ratio for drv_tw"

    def test_A2_actionable_query_joins_drv_tw(self):
        src = _read(DASH_PY)
        assert "drv_tw" in src, \
            "dash.py must join drv_tw to surface RVOL"

    def test_A2b_uses_lateral_join_for_drv_tw(self):
        """The drv_tw join should be LATERAL (picks latest sequence DESC)."""
        src = _read(DASH_PY)
        # LATERAL followed by drv_tw somewhere
        has_lateral = bool(re.search(r'LATERAL[^)]{0,200}drv_tw', src, re.DOTALL))
        has_drv_tw_with_lateral = bool(re.search(r'FROM\s+drv_tw', src, re.DOTALL))
        assert has_lateral or has_drv_tw_with_lateral, \
            "dash.py must use a LATERAL or subquery join on drv_tw"

    def test_A3_rvol_alias_in_select(self):
        src = _read(DASH_PY)
        assert "AS rvol" in src or "w_vlm_expn_ratio AS rvol" in src or \
               re.search(r'w_vlm_expn_ratio\s+AS\s+rvol', src), \
            "dash.py must alias w_vlm_expn_ratio AS rvol"

    def test_A3b_rvol_prior_alias_in_select(self):
        src = _read(DASH_PY)
        assert re.search(r'w_prior_day_vlm_expn_ratio\s+AS\s+rvol_prior', src) or \
               "AS rvol_prior" in src, \
            "dash.py must alias w_prior_day_vlm_expn_ratio AS rvol_prior"

    def test_A3c_tw_alias_references_rvol_and_rvol_prior(self):
        """The final SELECT must include tw.rvol and tw.rvol_prior."""
        src = _read(DASH_PY)
        assert "tw.rvol" in src, \
            "dash.py main SELECT must include tw.rvol"
        assert "tw.rvol_prior" in src, \
            "dash.py main SELECT must include tw.rvol_prior"

    def test_A4_dash_py_python_syntax(self):
        src = _read(DASH_PY)
        ast.parse(src)   # raises SyntaxError if broken

    def test_A4b_drv_tw_lateral_uses_sequence_desc(self):
        """LATERAL subquery must ORDER BY sequence DESC so we get the latest row."""
        src = _read(DASH_PY)
        # Find the drv_tw LATERAL block
        m = re.search(r'FROM\s+drv_tw[^)]+ORDER BY sequence DESC', src, re.DOTALL)
        assert m is not None, \
            "drv_tw LATERAL must ORDER BY sequence DESC LIMIT 1"

    def test_A4c_drv_tw_lateral_filters_snapshot_date(self):
        """LATERAL must filter snapshot_date = a.as_of_date (EXACT_MATCH semantic)."""
        src = _read(DASH_PY)
        m = re.search(r'FROM\s+drv_tw[^)]+snapshot_date\s*=\s*a\.as_of_date', src, re.DOTALL)
        assert m is not None, \
            "drv_tw LATERAL must filter snapshot_date = a.as_of_date"


# ---------------------------------------------------------------------------
# Part B — _common.js: rvolDot helper
# ---------------------------------------------------------------------------

class TestPartB_CommonJs:
    """B: rvolDot SVG helper in web/_common.js."""

    def test_B1_rvol_bands_const_exists(self):
        src = _read(COMMON_JS)
        assert "_RVOL_BANDS" in src, \
            "_common.js must define _RVOL_BANDS constant"

    def test_B1b_rvol_bands_has_5_entries(self):
        src = _read(COMMON_JS)
        # _RVOL_BANDS is a multi-line array of inner arrays; capture from 'var _RVOL_BANDS = ['
        # to the matching closing '];'
        m = re.search(r'var\s+_RVOL_BANDS\s*=\s*\[(.*?)\];', src, re.DOTALL)
        assert m, "_RVOL_BANDS array not found in _common.js"
        content = m.group(1)
        # Each band is a sub-array like [numericThreshold, bool, '#hexcolor']
        # Match sub-arrays that start with a number (not comments like '// [maxExclusive ...')
        # Count booleans — each band has exactly one true/false entry
        booleans = re.findall(r'\b(?:true|false)\b', content)
        assert len(booleans) == 5, \
            f"_RVOL_BANDS must have 5 entries (one bool each), found {len(booleans)}"

    def test_B2_rvol_flat_const_exists(self):
        src = _read(COMMON_JS)
        assert "_RVOL_FLAT" in src, \
            "_common.js must define _RVOL_FLAT constant"

    def test_B2b_rvol_flat_is_0_10(self):
        src = _read(COMMON_JS)
        assert re.search(r'_RVOL_FLAT\s*=\s*0\.10', src), \
            "_RVOL_FLAT must be 0.10 (±10% flat threshold)"

    def test_B3_rvolDot_function_defined(self):
        src = _read(COMMON_JS)
        assert "function rvolDot" in src, \
            "_common.js must define function rvolDot"

    def test_B4_rvolDot_exposed_on_window(self):
        src = _read(COMMON_JS)
        assert "window.rvolDot" in src, \
            "_common.js must expose window.rvolDot"

    def test_B5_rvolDot_in_td_common_object(self):
        src = _read(COMMON_JS)
        # Must appear inside the window.td_common = { ... } assignment
        td_block = re.search(r'window\.td_common\s*=\s*\{([^}]+)\}', src, re.DOTALL)
        assert td_block, "window.td_common object not found in _common.js"
        assert "rvolDot" in td_block.group(1), \
            "rvolDot must be included in window.td_common"

    def _get_bands_content(self, src: str) -> str:
        """Extract the full content of the _RVOL_BANDS array."""
        m = re.search(r'var\s+_RVOL_BANDS\s*=\s*\[(.*?)\];', src, re.DOTALL)
        assert m, "_RVOL_BANDS array not found in _common.js"
        return m.group(1)

    def test_B6_band0_hollow_B4B2A9(self):
        src = _read(COMMON_JS)
        content = self._get_bands_content(src)
        assert "0.5" in content and "false" in content and "#B4B2A9" in content.upper(), \
            "Band 0 must be [0.5, false, '#B4B2A9']"

    def test_B7_band1_hollow_888780(self):
        src = _read(COMMON_JS)
        content = self._get_bands_content(src)
        assert "0.8" in content and "#888780" in content.upper(), \
            "Band 1 must be [0.8, false, '#888780']"

    def test_B8_band2_solid_D3D1C7(self):
        src = _read(COMMON_JS)
        content = self._get_bands_content(src)
        assert "1.2" in content and "#D3D1C7" in content.upper(), \
            "Band 2 must be [1.2, true, '#D3D1C7']"

    def test_B9_band3_solid_EF9F27(self):
        src = _read(COMMON_JS)
        content = self._get_bands_content(src)
        assert "1.8" in content and "#EF9F27" in content.upper(), \
            "Band 3 must be [1.8, true, '#EF9F27']"

    def test_B10_band4_solid_green_639922(self):
        src = _read(COMMON_JS)
        content = self._get_bands_content(src)
        assert "Infinity" in content and "#639922" in content.upper(), \
            "Band 4 must be [Infinity, true, '#639922']"

    def test_B11_null_value_uses_dasharray(self):
        """Null RVOL must render a dotted ring (stroke-dasharray)."""
        src = _read(COMMON_JS)
        assert "stroke-dasharray" in src or "dasharray" in src, \
            "_common.js rvolDot must use stroke-dasharray for null/unknown ring"

    def test_B12_caret_up_path(self):
        src = _read(COMMON_JS)
        # Up triangle: M15 6 L12 1 L18 1 Z
        assert "M15 6 L12 1 L18 1 Z" in src or "M15 6 L12 1 L18 1 Z" in src, \
            "_common.js rvolDot must include up-caret path 'M15 6 L12 1 L18 1 Z'"

    def test_B13_caret_down_path(self):
        src = _read(COMMON_JS)
        assert "M15 1 L12 6 L18 6 Z" in src, \
            "_common.js rvolDot must include down-caret path 'M15 1 L12 6 L18 6 Z'"

    def test_B14_flat_dash_rect(self):
        src = _read(COMMON_JS)
        # Flat is a <rect> element
        assert re.search(r'<rect[^>]+fill.*#888780|flat.*<rect|rect.*flat', src, re.DOTALL), \
            "_common.js rvolDot must include flat dash as <rect> when dir='flat'"

    def test_B15_caret_colors(self):
        src = _read(COMMON_JS)
        assert "#3B6D11" in src.upper() or "3b6d11" in src, \
            "Up-caret color must be #3B6D11 (dark green)"
        assert "#A32D2D" in src.upper() or "a32d2d" in src, \
            "Down-caret color must be #A32D2D (dark red)"

    def test_B16_aria_label_includes_rvol(self):
        src = _read(COMMON_JS)
        assert "aria-label" in src, \
            "_common.js rvolDot SVG must include aria-label attribute"
        # aria-label should contain something like 'RVOL ...'
        assert re.search(r'aria-label.*RVOL|RVOL.*aria-label', src, re.DOTALL), \
            "aria-label must contain 'RVOL' for accessibility"

    def test_B17_title_element_present(self):
        src = _read(COMMON_JS)
        # SVG <title> element for tooltip
        assert "<title>" in src and "</title>" in src, \
            "_common.js rvolDot SVG must include <title>...</title>"

    def test_B18_common_js_node_check(self):
        result = subprocess.run(
            ["node", "--check", str(COMMON_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, \
            f"_common.js failed node --check: {result.stderr}"

    def test_B19_actionable_js_node_check(self):
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, \
            f"actionable.js failed node --check: {result.stderr}"


# ---------------------------------------------------------------------------
# Part C — actionable.html / actionable.js column wiring
# ---------------------------------------------------------------------------

class TestPartC_ColumnWiring:
    """C: 'Vol' column in Actionable grid header + cell."""

    def test_C1_th_data_key_rvol(self):
        src = _read(ACTIONABLE_HTML)
        assert 'data-key="rvol"' in src, \
            "actionable.html must have <th data-key=\"rvol\"> header"

    def test_C2_th_text_is_vol(self):
        src = _read(ACTIONABLE_HTML)
        # Look for >Vol< in proximity to data-key="rvol"
        m = re.search(r'data-key="rvol"[^>]*>[^<]*Vol[^<]*<', src)
        assert m is not None, \
            "actionable.html Vol column header must have text content 'Vol'"

    def test_C3_rvol_cell_css(self):
        src = _read(ACTIONABLE_HTML)
        assert ".rvol-cell" in src, \
            "actionable.html must define .rvol-cell CSS rule"

    def test_C4_td_rvol_cell_in_actionable_js(self):
        src = _read(ACTIONABLE_JS)
        assert 'class="num rvol-cell"' in src or "rvol-cell" in src, \
            "actionable.js row template must include <td class=\"num rvol-cell\">"

    def test_C5_cell_title_shows_rvol_value(self):
        src = _read(ACTIONABLE_JS)
        # title should show r.rvol.toFixed(2) when rvol is not null
        assert "r.rvol" in src and "toFixed" in src, \
            "actionable.js rvol cell must show r.rvol.toFixed(2)+'x' in title"

    def test_C6_cell_calls_rvolDot(self):
        src = _read(ACTIONABLE_JS)
        assert re.search(r'rvolDot\s*\(\s*r\.rvol\s*,\s*r\.rvol_prior', src), \
            "actionable.js must call rvolDot(r.rvol, r.rvol_prior) in the row cell"

    def test_C7_th_is_sortable(self):
        src = _read(ACTIONABLE_HTML)
        # The <th> for rvol must have class="num sortable"
        m = re.search(r'<th[^>]*class="[^"]*sortable[^"]*"[^>]*data-key="rvol"', src) or \
            re.search(r'<th[^>]*data-key="rvol"[^>]*class="[^"]*sortable[^"]*"', src)
        assert m is not None, \
            "actionable.html Vol column header must be class=\"num sortable\""

    def test_C8_th_data_type_is_num(self):
        src = _read(ACTIONABLE_HTML)
        m = re.search(r'data-key="rvol"[^>]*data-type="num"', src) or \
            re.search(r'data-type="num"[^>]*data-key="rvol"', src)
        assert m is not None, \
            "actionable.html Vol th must have data-type=\"num\" for numeric sort"


# ---------------------------------------------------------------------------
# DEV_HANDOFF checks
# ---------------------------------------------------------------------------

class TestDevHandoff:
    """D: DEV_HANDOFF.md is complete and documents the change."""

    def test_D1_all_done(self):
        content = _read(DEV_HANDOFF)
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        assert lines[-1] == "ALL_DONE", \
            f"DEV_HANDOFF.md last non-blank line must be ALL_DONE, got {lines[-1]!r}"

    def test_D2_documents_rvol_source(self):
        content = _read(DEV_HANDOFF)
        assert "w_vlm_expn_ratio" in content, \
            "DEV_HANDOFF.md must document the source column w_vlm_expn_ratio"

    def test_D2b_documents_rvol_prior_source(self):
        content = _read(DEV_HANDOFF)
        assert "w_prior_day_vlm_expn_ratio" in content, \
            "DEV_HANDOFF.md must document the source column w_prior_day_vlm_expn_ratio"

    def test_D3_references_agent_work_3(self):
        content = _read(DEV_HANDOFF)
        assert "AGENT_WORK_3" in content, \
            "DEV_HANDOFF.md must reference AGENT_WORK_3"

    def test_D4_mentions_drv_tw(self):
        content = _read(DEV_HANDOFF)
        assert "drv_tw" in content, \
            "DEV_HANDOFF.md must mention drv_tw as the join table"


# ---------------------------------------------------------------------------
# Regression: ensure other key JS files still pass syntax check
# ---------------------------------------------------------------------------

class TestRegressionSyntax:
    """Verify no regressions introduced in changed files."""

    @pytest.mark.parametrize("js_file", [
        "_common.js",
        "actionable.js",
    ])
    def test_js_syntax_clean(self, js_file):
        path = PROJECT / "web" / js_file
        if not path.exists():
            pytest.skip(f"{js_file} not found")
        result = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, \
            f"{js_file} has syntax errors: {result.stderr}"

    def test_dash_py_syntax_clean(self):
        src = _read(DASH_PY)
        ast.parse(src)

    def test_rvolDot_not_duplicated_in_actionable_js(self):
        """rvolDot must NOT be defined in actionable.js — only in _common.js."""
        src = _read(ACTIONABLE_JS)
        assert "function rvolDot" not in src, \
            "rvolDot must be defined only in _common.js, not duplicated in actionable.js"

    def test_RVOL_BANDS_not_in_actionable_js(self):
        """_RVOL_BANDS must NOT be duplicated in actionable.js."""
        src = _read(ACTIONABLE_JS)
        assert "_RVOL_BANDS" not in src, \
            "_RVOL_BANDS must not be duplicated in actionable.js (only in _common.js)"
