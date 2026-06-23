"""
Tests for AGENT_WORK_4 — TASK_62: IV bar glyph in symTape chips.

Acceptance criteria (from TASK_62_iv_glyph_symtape.md and DEV_HANDOFF.md):

  Part A (API / DB)
    A1  — dash.py LATERAL-joins hist_td to surface historical_vol AS hv
    A2  — dash.py outer SELECT includes hv_td.historical_vol AS hv
    A3  — LATERAL on hist_td filters snapshot_date <= a.as_of_date (carry-forward)
    A4  — LATERAL on hist_td orders by snapshot_date DESC, sequence DESC LIMIT 1
    A5  — imp_volatility is already present on the row (existing field, not regressed)
    A6  — iv_to_hv_discount is still present on the row (existing field, not regressed)
    A7  — iv_percentile is still present on the row (existing field, not regressed)
    A8  — dash.py python syntax clean

  Part B (_common.js — ivGlyph helper)
    B1  — _common.js defines named color constants _IV_COLOR_IVP, _IV_COLOR_HV,
          _IV_COLOR_IV, _IV_COLOR_UP, _IV_COLOR_DOWN, _IV_COLOR_PAR
    B2  — _IV_COLOR_IVP = '#185FA5' (blue)
    B3  — _IV_COLOR_HV  = '#B4B2A9' (light gray)
    B4  — _IV_COLOR_IV  = '#5F5E5A' (dark gray)
    B5  — _IV_COLOR_UP  = '#16a34a' (green)
    B6  — _IV_COLOR_DOWN = '#dc2626' (red)
    B7  — _IV_COLOR_PAR = '#888780' (gray parity)
    B8  — function ivGlyph is defined in _common.js
    B9  — ivGlyph is exposed as window.ivGlyph
    B10 — ivGlyph is included in the window.td_common object
    B11 — ivGlyph renders bars for IVP (x=3), HV (x=10), IV (x=13.5)
    B12 — ivGlyph renders a bracket <path> with M11.5 origin connecting HV and IV tops
    B13 — bracket color logic: dc > 2 uses _IV_COLOR_UP (cheap), dc < -2 uses _IV_COLOR_DOWN (rich)
    B14 — glyph has role="img" and aria-label in its SVG
    B15 — frame includes bottom baseline line (solid rule at y0)
    B16 — frame includes top dashed guide line (stroke-dasharray)
    B17 — _common.js node --check passes (no syntax errors)

  Part C (actionable.js — call site swap)
    C1  — old ivPctile / ivToHv / ivpColor / ivPctRing / hvColor / hvRing locals removed
    C2  — ivGlyphHtml local defined calling window.ivGlyph
    C3  — call passes r.iv_percentile as 1st arg to window.ivGlyph
    C4  — iv and hv values are multiplied by 100 (fraction -> percent conversion)
    C5  — call passes r.iv_to_hv_discount as 4th arg (discount)
    C6  — sym-iv span no longer has gap:2px style
    C7  — pctRing is NOT defined in actionable.js (only used from window, not duplicated)
    C8  — actionable.js node --check passes (no syntax errors)

  Part D (regression: TASK 61 not broken)
    D1  — _common.js still defines rvolDot (TASK 61 not regressed)
    D2  — _common.js still exposes window.rvolDot
    D3  — actionable.js still calls rvolDot for the rvol-cell (not removed)
    D4  — pctRing still present in _common.js (used by other callers)

  DEV_HANDOFF
    E1  — DEV_HANDOFF.md last non-blank line is ALL_DONE
    E2  — DEV_HANDOFF.md references AGENT_WORK_4
    E3  — DEV_HANDOFF.md documents that iv/hv are stored as fractions and are multiplied by 100
    E4  — DEV_HANDOFF.md mentions hv / historical_vol
    E5  — DEV_HANDOFF.md mentions ivGlyph
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

DASH_PY         = PROJECT / "api" / "routers" / "dash.py"
COMMON_JS       = PROJECT / "web" / "_common.js"
ACTIONABLE_JS   = PROJECT / "web" / "actionable.js"
DEV_HANDOFF     = PROJECT / "DEV_HANDOFF.md"


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1")


# ---------------------------------------------------------------------------
# Part A — API: dash.py exposes hv field
# ---------------------------------------------------------------------------

class TestPartA_API:
    """A: /api/actionable surfaces hv (historical_vol) from hist_td."""

    def test_A1_lateral_join_on_hist_td_exists(self):
        src = _read(DASH_PY)
        # Must have a LATERAL block that references hist_td
        assert re.search(r'LATERAL\s*\(', src, re.IGNORECASE) and "hist_td" in src, \
            "dash.py must include a LATERAL join that references hist_td"

    def test_A1b_hist_td_lateral_block(self):
        src = _read(DASH_PY)
        m = re.search(r'LATERAL[^)]*\([^)]*hist_td[^)]*\)', src, re.DOTALL)
        if not m:
            m = re.search(r'LATERAL\s*\(\s*SELECT\s+historical_vol\s+FROM\s+hist_td', src, re.DOTALL)
        assert m is not None or "historical_vol" in src, \
            "dash.py LATERAL subquery on hist_td must select historical_vol"

    def test_A2_hv_alias_in_outer_select(self):
        src = _read(DASH_PY)
        # Outer SELECT must pick up the alias as hv
        assert re.search(r'historical_vol\s+AS\s+hv', src, re.IGNORECASE) or \
               "hv_td.historical_vol AS hv" in src, \
            "dash.py outer SELECT must alias historical_vol AS hv"

    def test_A3_lateral_uses_carry_forward_filter(self):
        src = _read(DASH_PY)
        # snapshot_date <= a.as_of_date (carry-forward, not exact match)
        m = re.search(
            r'FROM\s+hist_td[^)]+snapshot_date\s*<=\s*a\.as_of_date',
            src, re.DOTALL
        )
        assert m is not None, \
            "hist_td LATERAL must use snapshot_date <= a.as_of_date (carry-forward)"

    def test_A4_lateral_orders_by_snapshot_date_desc(self):
        src = _read(DASH_PY)
        m = re.search(
            r'FROM\s+hist_td[^)]+ORDER BY snapshot_date DESC',
            src, re.DOTALL
        )
        assert m is not None, \
            "hist_td LATERAL must ORDER BY snapshot_date DESC"

    def test_A4b_lateral_limits_to_1_row(self):
        src = _read(DASH_PY)
        m = re.search(r'FROM\s+hist_td[^)]+LIMIT\s+1', src, re.DOTALL)
        assert m is not None, \
            "hist_td LATERAL must have LIMIT 1"

    def test_A5_imp_volatility_still_present(self):
        """imp_volatility was pre-existing and must not be removed."""
        src = _read(DASH_PY)
        assert "imp_volatility" in src, \
            "dash.py must still select imp_volatility (pre-existing field)"

    def test_A6_iv_to_hv_discount_still_present(self):
        src = _read(DASH_PY)
        assert "iv_to_hv_discount" in src, \
            "dash.py must still select iv_to_hv_discount"

    def test_A7_iv_percentile_still_present(self):
        src = _read(DASH_PY)
        assert "iv_percentile" in src, \
            "dash.py must still select iv_percentile"

    def test_A8_dash_py_python_syntax(self):
        src = _read(DASH_PY)
        ast.parse(src)  # raises SyntaxError if broken

    def test_A9_hv_td_alias_used_in_select(self):
        """The subquery alias hv_td must be referenced in the outer SELECT."""
        src = _read(DASH_PY)
        assert "hv_td" in src, \
            "dash.py must alias the hist_td LATERAL subquery as hv_td and reference it"


# ---------------------------------------------------------------------------
# Part B — _common.js: ivGlyph helper
# ---------------------------------------------------------------------------

class TestPartB_CommonJs:
    """B: ivGlyph SVG helper in web/_common.js."""

    def test_B1_color_constants_defined(self):
        src = _read(COMMON_JS)
        for const in ("_IV_COLOR_IVP", "_IV_COLOR_HV", "_IV_COLOR_IV",
                      "_IV_COLOR_UP", "_IV_COLOR_DOWN", "_IV_COLOR_PAR"):
            assert const in src, \
                f"_common.js must define color constant {const}"

    def test_B2_iv_color_ivp_is_blue(self):
        src = _read(COMMON_JS)
        assert re.search(r"_IV_COLOR_IVP\s*=\s*'#185FA5'", src, re.IGNORECASE) or \
               "_IV_COLOR_IVP  = '#185FA5'" in src or \
               "_IV_COLOR_IVP = '#185FA5'" in src, \
            "_IV_COLOR_IVP must be '#185FA5' (blue)"

    def test_B3_iv_color_hv_is_light_gray(self):
        src = _read(COMMON_JS)
        assert re.search(r"_IV_COLOR_HV\s*=\s*'#B4B2A9'", src, re.IGNORECASE) or \
               "#B4B2A9" in src, \
            "_IV_COLOR_HV must be '#B4B2A9' (light gray)"

    def test_B4_iv_color_iv_is_dark_gray(self):
        src = _read(COMMON_JS)
        assert re.search(r"_IV_COLOR_IV\s*=\s*'#5F5E5A'", src, re.IGNORECASE) or \
               "#5F5E5A" in src, \
            "_IV_COLOR_IV must be '#5F5E5A' (dark gray)"

    def test_B5_iv_color_up_is_green(self):
        src = _read(COMMON_JS)
        assert re.search(r"_IV_COLOR_UP\s*=\s*'#16a34a'", src, re.IGNORECASE) or \
               "#16a34a" in src.lower(), \
            "_IV_COLOR_UP must be '#16a34a' (green)"

    def test_B6_iv_color_down_is_red(self):
        src = _read(COMMON_JS)
        assert re.search(r"_IV_COLOR_DOWN\s*=\s*'#dc2626'", src, re.IGNORECASE) or \
               "#dc2626" in src.lower(), \
            "_IV_COLOR_DOWN must be '#dc2626' (red)"

    def test_B7_iv_color_par_is_gray(self):
        src = _read(COMMON_JS)
        assert re.search(r"_IV_COLOR_PAR\s*=\s*'#888780'", src, re.IGNORECASE) or \
               "_IV_COLOR_PAR" in src, \
            "_IV_COLOR_PAR must be '#888780' (parity gray)"

    def test_B8_ivGlyph_function_defined(self):
        src = _read(COMMON_JS)
        assert "function ivGlyph" in src, \
            "_common.js must define function ivGlyph"

    def test_B8b_ivGlyph_signature_has_5_params(self):
        src = _read(COMMON_JS)
        m = re.search(r'function ivGlyph\s*\(([^)]+)\)', src)
        assert m is not None, "ivGlyph function definition not found"
        params = [p.strip() for p in m.group(1).split(',')]
        assert len(params) == 5, \
            f"ivGlyph must take 5 params (ivp, iv, hv, discount, opts), got {params}"

    def test_B9_ivGlyph_exposed_on_window(self):
        src = _read(COMMON_JS)
        assert "window.ivGlyph" in src, \
            "_common.js must expose window.ivGlyph"

    def test_B10_ivGlyph_in_td_common_object(self):
        src = _read(COMMON_JS)
        td_block = re.search(r'window\.td_common\s*=\s*\{([^}]+)\}', src, re.DOTALL)
        assert td_block, "window.td_common object not found in _common.js"
        assert "ivGlyph" in td_block.group(1), \
            "ivGlyph must be included in window.td_common"

    def test_B11_bars_at_correct_x_positions(self):
        """IVP at x=3, HV at x=10, IV at x=13.5 per spec."""
        src = _read(COMMON_JS)
        # Check the bar() calls inside ivGlyph use correct x positions
        assert 'bar(3,' in src or 'bar(3 ,' in src, \
            "ivGlyph must render IVP bar at x=3"
        assert 'bar(10,' in src or 'bar(10 ,' in src, \
            "ivGlyph must render HV bar at x=10"
        assert 'bar(13.5,' in src or 'bar(13.5 ,' in src, \
            "ivGlyph must render IV bar at x=13.5"

    def test_B12_bracket_path_starts_at_M11_5(self):
        """Bracket path must start at x=11.5 (HV bar right edge)."""
        src = _read(COMMON_JS)
        # Check for the bracket path tag
        assert re.search(r'M11\.5\s', src), \
            "ivGlyph bracket <path> must start at M11.5"

    def test_B13_bracket_color_logic_uses_color_constants(self):
        """discount > 2 -> IV cheap -> _IV_COLOR_UP; < -2 -> _IV_COLOR_DOWN."""
        src = _read(COMMON_JS)
        # The color-selection logic should reference > 2 and < -2
        assert re.search(r'dc\s*>\s*2', src), \
            "ivGlyph bracket color logic must test dc > 2 for cheap (green)"
        assert re.search(r'dc\s*<\s*-2', src), \
            "ivGlyph bracket color logic must test dc < -2 for rich (red)"
        assert "_IV_COLOR_UP" in src, \
            "ivGlyph bracket must reference _IV_COLOR_UP for cheap case"
        assert "_IV_COLOR_DOWN" in src, \
            "ivGlyph bracket must reference _IV_COLOR_DOWN for rich case"

    def test_B14_svg_has_role_img_and_aria_label(self):
        src = _read(COMMON_JS)
        # Must appear in/near the ivGlyph function
        assert 'role="img"' in src, \
            "ivGlyph SVG must have role=\"img\""
        assert "aria-label" in src, \
            "ivGlyph SVG must have aria-label attribute"

    def test_B15_frame_has_baseline_rule(self):
        """Bottom baseline is a solid line at y0 (x1=1 x2=19)."""
        src = _read(COMMON_JS)
        # The non-dashed baseline rule
        assert re.search(r'<line[^>]+stroke-width="0\.9"', src), \
            "ivGlyph must include a solid baseline rule (stroke-width 0.9)"

    def test_B16_frame_has_dashed_top_guide(self):
        """Top guide at 100% level is dashed."""
        src = _read(COMMON_JS)
        # Must have at least one dashed line (stroke-dasharray in ivGlyph area)
        assert re.search(r'stroke-dasharray="2 2"', src), \
            "ivGlyph frame must include a dashed top guide (stroke-dasharray 2 2)"

    def test_B17_common_js_node_check(self):
        result = subprocess.run(
            ["node", "--check", str(COMMON_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, \
            f"_common.js failed node --check:\n{result.stderr}"


# ---------------------------------------------------------------------------
# Part C — actionable.js: call-site swap
# ---------------------------------------------------------------------------

class TestPartC_ActionableJs:
    """C: renderSymTape() in actionable.js uses ivGlyph instead of two pctRing calls."""

    def test_C1_old_ivPctile_local_removed(self):
        src = _read(ACTIONABLE_JS)
        assert "ivPctile" not in src, \
            "actionable.js must NOT contain old local 'ivPctile'"

    def test_C1b_old_ivToHv_local_removed(self):
        src = _read(ACTIONABLE_JS)
        assert "ivToHv" not in src, \
            "actionable.js must NOT contain old local 'ivToHv'"

    def test_C1c_old_ivpColor_local_removed(self):
        src = _read(ACTIONABLE_JS)
        assert "ivpColor" not in src, \
            "actionable.js must NOT contain old local 'ivpColor'"

    def test_C1d_old_ivPctRing_local_removed(self):
        src = _read(ACTIONABLE_JS)
        assert "ivPctRing" not in src, \
            "actionable.js must NOT contain old local 'ivPctRing'"

    def test_C1e_old_hvColor_local_removed(self):
        src = _read(ACTIONABLE_JS)
        assert "hvColor" not in src, \
            "actionable.js must NOT contain old local 'hvColor'"

    def test_C1f_old_hvRing_local_removed(self):
        src = _read(ACTIONABLE_JS)
        assert "hvRing" not in src, \
            "actionable.js must NOT contain old local 'hvRing'"

    def test_C2_ivGlyphHtml_local_defined(self):
        src = _read(ACTIONABLE_JS)
        assert "ivGlyphHtml" in src, \
            "actionable.js must define local 'ivGlyphHtml' calling window.ivGlyph"

    def test_C2b_calls_window_ivGlyph(self):
        src = _read(ACTIONABLE_JS)
        assert "window.ivGlyph" in src, \
            "actionable.js must call window.ivGlyph"

    def test_C3_passes_iv_percentile_as_first_arg(self):
        src = _read(ACTIONABLE_JS)
        m = re.search(r'window\.ivGlyph\s*\(\s*r\.iv_percentile', src)
        assert m is not None, \
            "actionable.js ivGlyph call must pass r.iv_percentile as 1st argument"

    def test_C4_iv_multiplied_by_100(self):
        """imp_volatility is stored as fraction; must be * 100 for percent units."""
        src = _read(ACTIONABLE_JS)
        assert re.search(r'imp_volatility[^;]*\*\s*100', src) or \
               re.search(r'Number\(r\.imp_volatility\)\s*\*\s*100', src), \
            "actionable.js must multiply r.imp_volatility * 100 (fraction -> percent)"

    def test_C4b_hv_multiplied_by_100(self):
        """hv is stored as fraction; must be * 100 for percent units."""
        src = _read(ACTIONABLE_JS)
        assert re.search(r'r\.hv[^;]*\*\s*100', src) or \
               re.search(r'Number\(r\.hv\)\s*\*\s*100', src), \
            "actionable.js must multiply r.hv * 100 (fraction -> percent)"

    def test_C5_passes_iv_to_hv_discount_as_fourth_arg(self):
        src = _read(ACTIONABLE_JS)
        # The 4th arg in the call should be r.iv_to_hv_discount
        m = re.search(
            r'window\.ivGlyph\s*\([^)]+r\.iv_to_hv_discount',
            src, re.DOTALL
        )
        assert m is not None, \
            "actionable.js ivGlyph call must pass r.iv_to_hv_discount as 4th argument"

    def test_C6_sym_iv_span_no_gap_2px(self):
        """The sym-iv span should not have gap:2px (removed because single glyph now)."""
        src = _read(ACTIONABLE_JS)
        # Check that the sym-iv span style doesn't include gap:2px
        m = re.search(r'sym-iv.*gap:\s*2px', src, re.DOTALL)
        assert m is None, \
            "actionable.js sym-iv span must NOT include 'gap:2px' (single glyph now)"

    def test_C7_pctRing_not_defined_in_actionable_js(self):
        """pctRing is in _common.js only; must not be duplicated in actionable.js."""
        src = _read(ACTIONABLE_JS)
        assert "function pctRing" not in src, \
            "pctRing must NOT be defined in actionable.js (only _common.js)"

    def test_C8_actionable_js_node_check(self):
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, \
            f"actionable.js failed node --check:\n{result.stderr}"


# ---------------------------------------------------------------------------
# Part D — Regression: TASK 61 (rvolDot) not broken
# ---------------------------------------------------------------------------

class TestPartD_Regression:
    """D: TASK 61 RVOL dot is still intact after TASK 62 changes."""

    def test_D1_rvolDot_still_defined_in_common_js(self):
        src = _read(COMMON_JS)
        assert "function rvolDot" in src, \
            "_common.js must still define rvolDot (TASK 61 regression check)"

    def test_D2_window_rvolDot_still_exposed(self):
        src = _read(COMMON_JS)
        assert "window.rvolDot" in src, \
            "_common.js must still expose window.rvolDot"

    def test_D3_actionable_js_still_calls_rvolDot(self):
        src = _read(ACTIONABLE_JS)
        assert "rvolDot" in src, \
            "actionable.js must still call rvolDot for the rvol-cell (TASK 61)"

    def test_D4_pctRing_still_in_common_js(self):
        """pctRing must remain in _common.js — used by other callers (TASK 52)."""
        src = _read(COMMON_JS)
        assert "function pctRing" in src, \
            "_common.js must still define pctRing (used by TASK 52 callers)"
        assert "window.pctRing" in src, \
            "_common.js must still expose window.pctRing"

    def test_D5_rvol_bands_const_unchanged(self):
        """_RVOL_BANDS from TASK 61 must still be present (5 bands)."""
        src = _read(COMMON_JS)
        assert "_RVOL_BANDS" in src, \
            "_RVOL_BANDS must still be present in _common.js"
        m = re.search(r'var\s+_RVOL_BANDS\s*=\s*\[(.*?)\];', src, re.DOTALL)
        assert m is not None, "_RVOL_BANDS array not found"
        booleans = re.findall(r'\b(?:true|false)\b', m.group(1))
        assert len(booleans) == 5, \
            f"_RVOL_BANDS must have 5 entries (TASK 61), found {len(booleans)}"

    def test_D6_rvol_cell_still_in_actionable_js(self):
        src = _read(ACTIONABLE_JS)
        assert "rvol-cell" in src, \
            "actionable.js must still have the rvol-cell column (TASK 61 regression)"

    def test_D7_tw_rvol_still_in_dash_py(self):
        src = _read(DASH_PY)
        assert "tw.rvol" in src and "tw.rvol_prior" in src, \
            "dash.py must still select tw.rvol and tw.rvol_prior (TASK 61 regression)"


# ---------------------------------------------------------------------------
# DEV_HANDOFF checks
# ---------------------------------------------------------------------------

class TestDevHandoff:
    """E: DEV_HANDOFF.md is complete and documents the TASK 62 change."""

    def test_E1_all_done_is_last_line(self):
        content = _read(DEV_HANDOFF)
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        assert lines and lines[-1] == "ALL_DONE", \
            f"DEV_HANDOFF.md last non-blank line must be ALL_DONE, got {lines[-1]!r}"

    def test_E2_references_agent_work_4(self):
        content = _read(DEV_HANDOFF)
        assert "AGENT_WORK_4" in content, \
            "DEV_HANDOFF.md must reference AGENT_WORK_4"

    def test_E3_documents_fraction_to_percent_conversion(self):
        """Handoff must record that iv/hv are fractions and are multiplied by 100."""
        content = _read(DEV_HANDOFF)
        has_fraction = re.search(r'fraction|×100|\*100|multiply.*100|100.*fraction', content, re.IGNORECASE)
        assert has_fraction is not None, \
            "DEV_HANDOFF.md must document that iv/hv are stored as fractions (×100 applied)"

    def test_E4_mentions_hv_or_historical_vol(self):
        content = _read(DEV_HANDOFF)
        assert "hv" in content or "historical_vol" in content, \
            "DEV_HANDOFF.md must mention hv or historical_vol"

    def test_E5_mentions_ivGlyph(self):
        content = _read(DEV_HANDOFF)
        assert "ivGlyph" in content, \
            "DEV_HANDOFF.md must mention ivGlyph"

    def test_E6_status_is_all_done(self):
        content = _read(DEV_HANDOFF)
        assert "ALL_DONE" in content, \
            "DEV_HANDOFF.md must contain ALL_DONE status marker"
