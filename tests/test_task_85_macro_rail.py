"""
Tests for TASK_85 — Macro areas + USD correlations as a compact right side rail
on /actionable (AGENT_WORK_22).

Acceptance criteria:
  1.  node --check web/macro_areas.js passes (no syntax errors).
  2.  node --check web/macro_usd_corr.js passes (no syntax errors).
  3.  actionable.html: #macroRailSection exists inside #actSidePanel.
  4.  actionable.html: #macroRailAreas exists inside #macroRailSection.
  5.  actionable.html: #macroRailCorr exists inside #macroRailSection.
  6.  actionable.html: #macroRailSection is the first <section> inside #actSidePanel.
  7.  macro_areas.js: deep-arch SVG up-path present (M2,12.5 L8,3 L14,12.5 Q8,7).
  8.  macro_areas.js: deep-arch SVG down-path present (M2,3.5 L8,13 L14,3.5 Q8,9).
  9.  macro_areas.js: green (Long) arrowhead class msr-arrow-long.
  10. macro_areas.js: red (Short) arrowhead class msr-arrow-short.
  11. macro_areas.js: neutral (gray) arrowhead class msr-arrow-neut.
  12. macro_areas.js: Td/Tn durArrow() function with up/down/flat variants.
  13. macro_areas.js: railRangeBar() renders .msr-rb-tick.extreme at extremes.
  14. macro_areas.js: % label (msr-pct) rendered for normal rows.
  15. macro_areas.js: Volatility row uses gauge pill (msr-gauge).
  16. macro_areas.js: Sectors row renders leaders/laggards summary (.msr-sec-line).
  17. macro_areas.js: tooltip built with stance / conviction / RR pos / members.
  18. macro_areas.js: reads /api/macro-areas.
  19. macro_areas.js: dispatches macroReadReady event.
  20. macro_usd_corr.js: renders heatmap into #macroRailCorr (renderRail function).
  21. macro_usd_corr.js: 5 windows [15, 30, 90, 120, 180].
  22. macro_usd_corr.js: green threshold >= +0.50.
  23. macro_usd_corr.js: amber threshold <= -0.40.
  24. macro_usd_corr.js: strong-red threshold <= -0.70.
  25. macro_usd_corr.js: NULL cells render as "--" or "—".
  26. macro_usd_corr.js: hover row shows 52-wk Hi/Lo/%pos/%neg in tooltip.
  27. macro_usd_corr.js: reads /api/correlations.
  28. macro_usd_corr.js: listens for macroReadReady event.
  29. styles.css: TASK_85 block present with .msr-section-hdr.
  30. styles.css: .msr-row defined.
  31. styles.css: .msr-arrow / .msr-arrow-long / .msr-arrow-short / .msr-arrow-neut.
  32. styles.css: .msr-dur / .msr-dur-up / .msr-dur-down / .msr-dur-flat.
  33. styles.css: .msr-rb / .msr-rb-tick.extreme (red at extremes).
  34. styles.css: .msr-pct defined.
  35. styles.css: .msr-gauge / .msr-gauge-g / .msr-gauge-a / .msr-gauge-r.
  36. styles.css: .msr-sec-line defined.
  37. styles.css: .msr-tooltip defined.
  38. styles.css: .msr-ucr-table defined.
  39. styles.css: .msr-loading and .msr-err defined.
  40. No backend Python files modified by this change.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
MACRO_AREAS_JS = WEB_DIR / "macro_areas.js"
MACRO_CORR_JS = WEB_DIR / "macro_usd_corr.js"
ACTIONABLE_HTML = WEB_DIR / "actionable.html"
STYLES_CSS = WEB_DIR / "styles.css"
API_DIR = PROJECT_ROOT / "api"
ETL_DIR = PROJECT_ROOT / "etl"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_body(src: str, func_name: str, max_len: int = 4000) -> str:
    """Return source text from 'function func_name' up to max_len chars."""
    idx = src.find(f"function {func_name}(")
    if idx == -1:
        idx = src.find(f"async function {func_name}(")
    assert idx != -1, f"{func_name}() not found in source"
    return src[idx: idx + max_len]


# ── Criteria 1-2: Syntax checks ─────────────────────────────────────────────

class TestSyntaxChecks:
    def test_macro_areas_js_syntax(self):
        """node --check web/macro_areas.js must pass (exit 0, no output)."""
        result = subprocess.run(
            ["node", "--check", str(MACRO_AREAS_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"node --check macro_areas.js failed:\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    def test_macro_usd_corr_js_syntax(self):
        """node --check web/macro_usd_corr.js must pass (exit 0, no output)."""
        result = subprocess.run(
            ["node", "--check", str(MACRO_CORR_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"node --check macro_usd_corr.js failed:\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )


# ── Criteria 3-6: HTML structure ────────────────────────────────────────────

class TestHtmlStructure:
    def setup_method(self):
        self.html = _read(ACTIONABLE_HTML)

    def test_actSidePanel_exists(self):
        """#actSidePanel aside element must be present."""
        assert 'id="actSidePanel"' in self.html or "id='actSidePanel'" in self.html, \
            "#actSidePanel not found in actionable.html"

    def test_macroRailSection_inside_actSidePanel(self):
        """#macroRailSection must appear after #actSidePanel (inside it)."""
        side_idx = self.html.find('id="actSidePanel"')
        assert side_idx != -1, "#actSidePanel not found"
        rail_idx = self.html.find('id="macroRailSection"')
        assert rail_idx != -1, "#macroRailSection not found in actionable.html"
        assert rail_idx > side_idx, \
            "#macroRailSection must appear after (inside) #actSidePanel"

    def test_macroRailAreas_inside_macroRailSection(self):
        """#macroRailAreas must exist inside #macroRailSection."""
        section_idx = self.html.find('id="macroRailSection"')
        assert section_idx != -1, "#macroRailSection not found"
        areas_idx = self.html.find('id="macroRailAreas"')
        assert areas_idx != -1, "#macroRailAreas not found in actionable.html"
        assert areas_idx > section_idx, \
            "#macroRailAreas must appear after (inside) #macroRailSection"

    def test_macroRailCorr_inside_macroRailSection(self):
        """#macroRailCorr must exist inside #macroRailSection."""
        section_idx = self.html.find('id="macroRailSection"')
        assert section_idx != -1, "#macroRailSection not found"
        corr_idx = self.html.find('id="macroRailCorr"')
        assert corr_idx != -1, "#macroRailCorr not found in actionable.html"
        assert corr_idx > section_idx, \
            "#macroRailCorr must appear after (inside) #macroRailSection"

    def test_macroRailSection_is_first_section_in_actSidePanel(self):
        """#macroRailSection must be the first <section> inside #actSidePanel."""
        side_idx = self.html.find('id="actSidePanel"')
        assert side_idx != -1, "#actSidePanel not found"
        # Find the first <section inside actSidePanel
        first_section = self.html.find('<section', side_idx)
        assert first_section != -1, "No <section> found inside #actSidePanel"
        macro_section_idx = self.html.find('id="macroRailSection"')
        # The first section tag must contain macroRailSection within ~50 chars
        surrounding = self.html[first_section: first_section + 100]
        assert 'macroRailSection' in surrounding, (
            "#macroRailSection must be the first <section> inside #actSidePanel; "
            f"first section found at char {first_section}: {surrounding!r}"
        )

    def test_macroRailAreas_before_macroRailCorr(self):
        """#macroRailAreas must appear before #macroRailCorr (areas above correlations)."""
        areas_idx = self.html.find('id="macroRailAreas"')
        corr_idx = self.html.find('id="macroRailCorr"')
        assert areas_idx != -1, "#macroRailAreas not found"
        assert corr_idx != -1, "#macroRailCorr not found"
        assert areas_idx < corr_idx, \
            "#macroRailAreas must appear before #macroRailCorr in HTML"

    def test_econ_panel_still_present(self):
        """Existing Econ Indicators panel must still be present (no regression)."""
        assert 'Econ Indicators' in self.html or 'econBody' in self.html, \
            "Econ Indicators panel missing from actionable.html — regression"


# ── Criteria 7-19: macro_areas.js ───────────────────────────────────────────

class TestMacroAreasJs:
    def setup_method(self):
        self.src = _read(MACRO_AREAS_JS)

    def test_svg_up_path_present(self):
        """Deep-arch UP arrowhead SVG path must match spec exactly."""
        # Spec: M2,12.5 L8,3 L14,12.5 Q8,7 2,12.5 Z
        assert 'M2,12.5 L8,3 L14,12.5 Q8,7' in self.src, (
            "UP arrowhead SVG path 'M2,12.5 L8,3 L14,12.5 Q8,7' not found in macro_areas.js"
        )

    def test_svg_down_path_present(self):
        """Deep-arch DOWN arrowhead SVG path must match spec exactly."""
        # Spec: M2,3.5 L8,13 L14,3.5 Q8,9 2,3.5 Z
        assert 'M2,3.5 L8,13 L14,3.5 Q8,9' in self.src, (
            "DOWN arrowhead SVG path 'M2,3.5 L8,13 L14,3.5 Q8,9' not found in macro_areas.js"
        )

    def test_arrow_long_class(self):
        """msr-arrow-long class used for Long (green) stance."""
        assert 'msr-arrow-long' in self.src, \
            "msr-arrow-long class not found in macro_areas.js"

    def test_arrow_short_class(self):
        """msr-arrow-short class used for Short (red) stance."""
        assert 'msr-arrow-short' in self.src, \
            "msr-arrow-short class not found in macro_areas.js"

    def test_arrow_neut_class(self):
        """msr-arrow-neut class used for neutral stance."""
        assert 'msr-arrow-neut' in self.src, \
            "msr-arrow-neut class not found in macro_areas.js"

    def test_stance_colors(self):
        """Long -> green, Short -> red colors applied to arrows."""
        assert "'Long'" in self.src or '"Long"' in self.src, \
            "Long stance check missing from macro_areas.js"
        assert "'Short'" in self.src or '"Short"' in self.src, \
            "Short stance check missing from macro_areas.js"

    def test_durArrow_function_exists(self):
        """durArrow() function (Td/Tn diagonal labels) must exist."""
        assert 'function durArrow(' in self.src, \
            "durArrow() function not found in macro_areas.js"

    def test_durArrow_up_arrow_unicode(self):
        """durArrow() must use up-right diagonal arrow (↗ = &#8599;) for positive."""
        body = _func_body(self.src, 'durArrow')
        assert '&#8599;' in body or '↗' in body, \
            "durArrow() must use up-right arrow (&#8599;) for positive values"

    def test_durArrow_down_arrow_unicode(self):
        """durArrow() must use down-right diagonal arrow (↘ = &#8600;) for negative."""
        body = _func_body(self.src, 'durArrow')
        assert '&#8600;' in body or '↘' in body, \
            "durArrow() must use down-right arrow (&#8600;) for negative values"

    def test_durArrow_Td_Tn_labels(self):
        """durArrow() is called with 'Td' and 'Tn' labels."""
        assert "'Td'" in self.src or '"Td"' in self.src, \
            "'Td' label not found in macro_areas.js"
        assert "'Tn'" in self.src or '"Tn"' in self.src, \
            "'Tn' label not found in macro_areas.js"

    def test_railRangeBar_function_exists(self):
        """railRangeBar() function must exist."""
        assert 'function railRangeBar(' in self.src, \
            "railRangeBar() function not found in macro_areas.js"

    def test_extreme_class_on_tick(self):
        """railRangeBar() must add .extreme class to msr-rb-tick at extremes."""
        body = _func_body(self.src, 'railRangeBar')
        assert 'extreme' in body, \
            "railRangeBar() does not apply 'extreme' class to tick at range extremes"

    def test_msr_pct_label_rendered(self):
        """railRangeBar() must render the % label with msr-pct class."""
        body = _func_body(self.src, 'railRangeBar')
        assert 'msr-pct' in body, \
            "railRangeBar() must render a .msr-pct % label"

    def test_volatility_gauge_logic(self):
        """Volatility row must use gauge pill (msr-gauge class)."""
        rail_row_body = _func_body(self.src, 'railAreaRow')
        assert 'msr-gauge' in rail_row_body, \
            "railAreaRow() Volatility branch must use msr-gauge class"
        assert 'volatility' in rail_row_body or 'isVol' in rail_row_body, \
            "railAreaRow() must have a volatility-specific branch"

    def test_volatility_vix_value_shown(self):
        """Volatility row must show VIX value."""
        body = _func_body(self.src, 'railAreaRow')
        assert 'VIX' in body or 'vixVal' in body, \
            "Volatility rail row must show VIX value"

    def test_sectors_row_renders_leaders(self):
        """railSectorsRow() must render leaders in the summary line."""
        body = _func_body(self.src, 'railSectorsRow')
        assert 'leaders' in body, \
            "railSectorsRow() must render leaders"
        assert 'msr-sec-line' in body, \
            "railSectorsRow() must use .msr-sec-line for the summary"

    def test_sectors_row_renders_laggards(self):
        """railSectorsRow() must render laggards in the summary line."""
        body = _func_body(self.src, 'railSectorsRow')
        assert 'laggards' in body, \
            "railSectorsRow() must render laggards"

    def test_tooltip_builds_stance(self):
        """buildTooltip() must include stance field."""
        body = _func_body(self.src, 'buildTooltip')
        assert 'Stance' in body or 'stance' in body, \
            "buildTooltip() must include the stance field"

    def test_tooltip_builds_conviction(self):
        """buildTooltip() must include conviction field."""
        body = _func_body(self.src, 'buildTooltip')
        assert 'conviction' in body or 'Conviction' in body, \
            "buildTooltip() must include conviction"

    def test_tooltip_builds_rr_pos(self):
        """buildTooltip() must include RR pos field."""
        body = _func_body(self.src, 'buildTooltip')
        assert 'rr_pos' in body or 'RR pos' in body, \
            "buildTooltip() must include RR pos"

    def test_tooltip_builds_members(self):
        """buildTooltip() must include members list."""
        body = _func_body(self.src, 'buildTooltip')
        assert 'members' in body or 'Members' in body, \
            "buildTooltip() must include the members list"

    def test_reads_api_macro_areas(self):
        """load() must fetch from /api/macro-areas."""
        assert '/api/macro-areas' in self.src, \
            "macro_areas.js must read /api/macro-areas endpoint"

    def test_dispatches_macroReadReady(self):
        """After loading, must dispatch 'macroReadReady' CustomEvent."""
        assert 'macroReadReady' in self.src, \
            "macro_areas.js must dispatch macroReadReady event for USD-corr to follow"

    def test_renders_into_macroRailAreas(self):
        """renderRail() must target the #macroRailAreas container."""
        body = _func_body(self.src, 'renderRail')
        assert 'macroRailAreas' in body, \
            "renderRail() must render into #macroRailAreas"

    def test_datePicker_change_triggers_reload(self):
        """Date picker change event must trigger reload."""
        assert "datePicker" in self.src, \
            "macro_areas.js must listen to datePicker change"
        assert "'change'" in self.src or '"change"' in self.src, \
            "macro_areas.js must wire a 'change' event listener on datePicker"

    def test_error_rendered_to_rail(self):
        """Errors must render into #macroRailAreas with msr-err class."""
        assert 'msr-err' in self.src, \
            "macro_areas.js must use .msr-err class for error states"


# ── Criteria 20-28: macro_usd_corr.js ───────────────────────────────────────

class TestMacroUsdCorrJs:
    def setup_method(self):
        self.src = _read(MACRO_CORR_JS)

    def test_renderRail_targets_macroRailCorr(self):
        """renderRail() must render into #macroRailCorr."""
        body = _func_body(self.src, 'renderRail')
        assert 'macroRailCorr' in body, \
            "renderRail() must target #macroRailCorr container"

    def test_five_windows_defined(self):
        """All 5 windows [15, 30, 90, 120, 180] must be configured."""
        assert '15' in self.src and '30' in self.src and '90' in self.src, \
            "macro_usd_corr.js missing some window values"
        assert '120' in self.src and '180' in self.src, \
            "macro_usd_corr.js missing 120 or 180 window"
        # Check the WINDOWS array is properly defined
        assert 'WINDOWS' in self.src or 'windows' in self.src.lower(), \
            "macro_usd_corr.js must define the list of windows"

    def test_windows_array_has_five_entries(self):
        """WINDOWS constant must list exactly [15, 30, 90, 120, 180]."""
        # Find the WINDOWS array
        match = re.search(r'var WINDOWS\s*=\s*\[([^\]]+)\]', self.src)
        assert match, "WINDOWS array not found in macro_usd_corr.js"
        contents = match.group(1)
        nums = [int(x.strip()) for x in contents.split(',') if x.strip().isdigit()]
        assert sorted(nums) == [15, 30, 90, 120, 180], (
            f"WINDOWS array expected [15,30,90,120,180], got {nums}"
        )

    def test_green_threshold(self):
        """Green threshold must be >= +0.50."""
        assert '0.50' in self.src or 'CORR_GREEN' in self.src, \
            "Green threshold (+0.50) not found in macro_usd_corr.js"
        match = re.search(r'CORR_GREEN\s*=\s*([\d.]+)', self.src)
        if match:
            val = float(match.group(1))
            assert val == 0.50, f"CORR_GREEN expected 0.50, got {val}"

    def test_amber_threshold(self):
        """Amber (moderate) threshold must be <= -0.40."""
        assert '-0.40' in self.src or 'CORR_RED_MOD' in self.src, \
            "Amber threshold (-0.40) not found in macro_usd_corr.js"
        match = re.search(r'CORR_RED_MOD\s*=\s*(-[\d.]+)', self.src)
        if match:
            val = float(match.group(1))
            assert val == -0.40, f"CORR_RED_MOD expected -0.40, got {val}"

    def test_strong_red_threshold(self):
        """Strong-red threshold must be <= -0.70."""
        assert '-0.70' in self.src or 'CORR_RED_STR' in self.src, \
            "Strong-red threshold (-0.70) not found in macro_usd_corr.js"
        match = re.search(r'CORR_RED_STR\s*=\s*(-[\d.]+)', self.src)
        if match:
            val = float(match.group(1))
            assert val == -0.70, f"CORR_RED_STR expected -0.70, got {val}"

    def test_corrClass_function_exists(self):
        """corrClass() function must map r values to CSS class names."""
        assert 'function corrClass(' in self.src, \
            "corrClass() function not found in macro_usd_corr.js"

    def test_null_cells_render_dash(self):
        """NULL r values must render as '--' or '—'."""
        # fmtR handles null
        fmtR_body = _func_body(self.src, 'fmtR')
        assert "'—'" in fmtR_body or '"—"' in fmtR_body or \
               "'--'" in fmtR_body or '"--"' in fmtR_body, \
            "fmtR() must render null values as '—' or '--'"

    def test_nil_class_for_null(self):
        """NULL cells must get ucr-nil class."""
        assert 'ucr-nil' in self.src, \
            "macro_usd_corr.js must use ucr-nil class for NULL cells"

    def test_hover_shows_52wk_stats(self):
        """Row hover tooltip must show 52-wk Hi/Lo/%pos/%neg."""
        render_body = _func_body(self.src, 'renderRail')
        # Check tooltip creation and wiring
        assert 'data-tip' in self.src or 'msrUcrTooltip' in self.src, \
            "macro_usd_corr.js must build a hover tooltip"
        # Check the 52-wk stats fields are referenced
        assert 'roll30_high' in self.src or '52' in self.src, \
            "hover tooltip must include 52-wk stats"

    def test_tooltip_52wk_hi_lo_pct(self):
        """Tooltip must include 52-wk Hi, Lo, %pos, %neg fields."""
        assert 'roll30_high' in self.src, \
            "52-wk Hi (roll30_high) missing from macro_usd_corr.js tooltip"
        assert 'roll30_low' in self.src, \
            "52-wk Lo (roll30_low) missing from macro_usd_corr.js tooltip"
        assert 'roll30_pct_pos' in self.src, \
            "52-wk %pos (roll30_pct_pos) missing from macro_usd_corr.js tooltip"
        assert 'roll30_pct_neg' in self.src, \
            "52-wk %neg (roll30_pct_neg) missing from macro_usd_corr.js tooltip"

    def test_reads_api_correlations(self):
        """load() must fetch from /api/correlations."""
        assert '/api/correlations' in self.src, \
            "macro_usd_corr.js must read /api/correlations endpoint"

    def test_listens_for_macroReadReady(self):
        """init() must listen for macroReadReady event before loading."""
        assert 'macroReadReady' in self.src, \
            "macro_usd_corr.js must listen for macroReadReady event"
        # Verify it's used as an event listener trigger
        assert "addEventListener('macroReadReady'" in self.src or \
               'addEventListener("macroReadReady"' in self.src, \
            "macro_usd_corr.js must addEventListener for macroReadReady"

    def test_heatmap_uses_msr_ucr_table(self):
        """Rail heatmap must use .msr-ucr-table class."""
        assert 'msr-ucr-table' in self.src, \
            "macro_usd_corr.js must use .msr-ucr-table for the rail heatmap"

    def test_win_labels_defined(self):
        """Window labels (15D/30D/90D/120D/180D) must be defined."""
        assert '15D' in self.src and '30D' in self.src and '90D' in self.src, \
            "Window labels (15D, 30D, 90D) missing from macro_usd_corr.js"
        assert '120D' in self.src and '180D' in self.src, \
            "Window labels (120D, 180D) missing from macro_usd_corr.js"

    def test_datePicker_change_triggers_reload(self):
        """Date picker change event must trigger reload."""
        assert 'datePicker' in self.src, \
            "macro_usd_corr.js must listen to datePicker change"

    def test_error_rendered_to_rail(self):
        """Errors must render into #macroRailCorr with msr-err class."""
        assert 'msr-err' in self.src, \
            "macro_usd_corr.js must use .msr-err class for error states"

    def test_method_note_price_levels(self):
        """The 'price-levels' method note must still be referenced."""
        assert 'price-levels' in self.src or 'price_levels' in self.src, \
            "macro_usd_corr.js must include price-levels method note"


# ── Criteria 29-39: styles.css TASK_85 block ────────────────────────────────

class TestStylesCss:
    def setup_method(self):
        self.css = _read(STYLES_CSS)

    def test_task85_block_comment(self):
        """TASK_85 CSS block comment must be present."""
        assert 'TASK_85' in self.css, \
            "TASK_85 block comment not found in styles.css"

    def test_msr_section_hdr_defined(self):
        """.msr-section-hdr must be defined."""
        assert '.msr-section-hdr' in self.css, \
            ".msr-section-hdr not defined in styles.css"

    def test_msr_row_defined(self):
        """.msr-row must be defined."""
        assert '.msr-row' in self.css, \
            ".msr-row not defined in styles.css"

    def test_msr_arrow_variants_defined(self):
        """.msr-arrow / .msr-arrow-long / .msr-arrow-short / .msr-arrow-neut must all be defined."""
        for cls in ['.msr-arrow', '.msr-arrow-long', '.msr-arrow-short', '.msr-arrow-neut']:
            assert cls in self.css, f"{cls} not defined in styles.css"

    def test_msr_arrow_long_green(self):
        """.msr-arrow-long must use a green color (#166534)."""
        idx = self.css.find('.msr-arrow-long')
        assert idx != -1, ".msr-arrow-long not in CSS"
        block = self.css[idx: idx + 80]
        assert '#166534' in block or 'green' in block.lower(), \
            ".msr-arrow-long must use green color"

    def test_msr_arrow_short_red(self):
        """.msr-arrow-short must use a red color (#991b1b)."""
        idx = self.css.find('.msr-arrow-short')
        assert idx != -1, ".msr-arrow-short not in CSS"
        block = self.css[idx: idx + 80]
        assert '#991b1b' in block or 'red' in block.lower(), \
            ".msr-arrow-short must use red color"

    def test_msr_dur_variants_defined(self):
        """.msr-dur / .msr-dur-up / .msr-dur-down / .msr-dur-flat must all be defined."""
        for cls in ['.msr-dur', '.msr-dur-up', '.msr-dur-down', '.msr-dur-flat']:
            assert cls in self.css, f"{cls} not defined in styles.css"

    def test_msr_rb_defined(self):
        """.msr-rb (compact range bar) must be defined."""
        assert '.msr-rb' in self.css, \
            ".msr-rb (range bar) not defined in styles.css"

    def test_msr_rb_width_44px(self):
        """.msr-rb track width must be 44px (spec requirement)."""
        idx = self.css.find('.msr-rb {')
        if idx == -1:
            idx = self.css.find('.msr-rb\n')
        assert idx != -1, ".msr-rb rule not found in CSS"
        block = self.css[idx: idx + 200]
        assert '44px' in block, \
            ".msr-rb must have width: 44px per spec"

    def test_msr_rb_tick_extreme_red(self):
        """.msr-rb-tick.extreme must use red (#ef4444)."""
        assert '.msr-rb-tick.extreme' in self.css, \
            ".msr-rb-tick.extreme not defined in styles.css"
        idx = self.css.find('.msr-rb-tick.extreme')
        block = self.css[idx: idx + 60]
        assert '#ef4444' in block or 'red' in block.lower(), \
            ".msr-rb-tick.extreme must use red color"

    def test_msr_pct_defined(self):
        """.msr-pct must be defined."""
        assert '.msr-pct' in self.css, \
            ".msr-pct (percent label) not defined in styles.css"

    def test_msr_gauge_variants_defined(self):
        """.msr-gauge / .msr-gauge-g / .msr-gauge-a / .msr-gauge-r must all be defined."""
        for cls in ['.msr-gauge', '.msr-gauge-g', '.msr-gauge-a', '.msr-gauge-r']:
            assert cls in self.css, f"{cls} not defined in styles.css"

    def test_msr_sec_line_defined(self):
        """.msr-sec-line must be defined."""
        assert '.msr-sec-line' in self.css, \
            ".msr-sec-line (sectors summary line) not defined in styles.css"

    def test_msr_tooltip_defined(self):
        """.msr-tooltip must be defined and use position:fixed."""
        assert '.msr-tooltip' in self.css, \
            ".msr-tooltip not defined in styles.css"
        idx = self.css.find('.msr-tooltip {')
        if idx == -1:
            idx = self.css.find('.msr-tooltip\n')
        assert idx != -1
        block = self.css[idx: idx + 300]
        assert 'fixed' in block, \
            ".msr-tooltip must use position: fixed"

    def test_msr_ucr_table_defined(self):
        """.msr-ucr-table must be defined for the compact heatmap."""
        assert '.msr-ucr-table' in self.css, \
            ".msr-ucr-table not defined in styles.css"

    def test_msr_loading_defined(self):
        """.msr-loading must be defined."""
        assert '.msr-loading' in self.css, \
            ".msr-loading not defined in styles.css"

    def test_msr_err_defined(self):
        """.msr-err must be defined."""
        assert '.msr-err' in self.css, \
            ".msr-err not defined in styles.css"


# ── Criterion 40: No backend Python files modified ───────────────────────────

class TestNoPythonBackendChanges:
    """TASK_85 is front-end only — verify no backend artifacts leaked."""

    def test_macroRailAreas_not_in_python(self):
        """macroRailAreas must not appear in any Python file."""
        for py in list(API_DIR.rglob("*.py")) + list(ETL_DIR.rglob("*.py")):
            content = py.read_text(encoding="utf-8", errors="replace")
            assert 'macroRailAreas' not in content, \
                f"macroRailAreas leaked into Python file: {py}"

    def test_macroRailCorr_not_in_python(self):
        """macroRailCorr must not appear in any Python file."""
        for py in list(API_DIR.rglob("*.py")) + list(ETL_DIR.rglob("*.py")):
            content = py.read_text(encoding="utf-8", errors="replace")
            assert 'macroRailCorr' not in content, \
                f"macroRailCorr leaked into Python file: {py}"

    def test_msr_prefix_not_in_python(self):
        """CSS .msr- prefix must not appear in Python files."""
        for py in list(API_DIR.rglob("*.py")) + list(ETL_DIR.rglob("*.py")):
            content = py.read_text(encoding="utf-8", errors="replace")
            assert 'msr-' not in content, \
                f"msr- CSS prefix leaked into Python file: {py}"


# ── Integration-style: cross-file consistency ────────────────────────────────

class TestCrossFileConsistency:
    """CSS classes used in JS must be defined in styles.css."""

    def setup_method(self):
        self.areas_src = _read(MACRO_AREAS_JS)
        self.corr_src = _read(MACRO_CORR_JS)
        self.css = _read(STYLES_CSS)

    def test_msr_row_used_in_areas_js(self):
        """macro_areas.js must use .msr-row (which is defined in CSS)."""
        assert 'msr-row' in self.areas_src, \
            "macro_areas.js does not use .msr-row class"

    def test_msr_gauge_used_in_areas_js(self):
        """macro_areas.js must use .msr-gauge for Volatility rows."""
        assert 'msr-gauge' in self.areas_src, \
            "macro_areas.js does not use .msr-gauge class"

    def test_msr_ucr_table_used_in_corr_js(self):
        """macro_usd_corr.js must use .msr-ucr-table."""
        assert 'msr-ucr-table' in self.corr_src, \
            "macro_usd_corr.js does not use .msr-ucr-table class"

    def test_ucr_pos_class_defined_in_css(self):
        """.ucr-pos (green cell) must be defined in CSS (used by corr JS)."""
        assert '.ucr-pos' in self.css, \
            ".ucr-pos class missing from styles.css"

    def test_ucr_neg_s_class_defined_in_css(self):
        """.ucr-neg-s (strong red cell) must be defined in CSS."""
        assert '.ucr-neg-s' in self.css, \
            ".ucr-neg-s class missing from styles.css"

    def test_ucr_neg_m_class_defined_in_css(self):
        """.ucr-neg-m (amber cell) must be defined in CSS."""
        assert '.ucr-neg-m' in self.css, \
            ".ucr-neg-m class missing from styles.css"

    def test_msr_divider_in_html_and_css(self):
        """#macroRailSection must use .msr-divider, which is defined in CSS."""
        html = _read(ACTIONABLE_HTML)
        assert 'msr-divider' in html, \
            ".msr-divider not used in actionable.html"
        assert '.msr-divider' in self.css, \
            ".msr-divider not defined in styles.css"
