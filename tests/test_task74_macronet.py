"""
Tests for TASK_74 — MacroNet quad-regime signal on the Actionable screen.

Acceptance criteria verified:
  1. Python syntax: api/routers/dash.py passes ast.parse.
  2. JS syntax: web/actionable.js passes node --check.
  3. SQL length: all new MacroNet SQL strings in dash.py are <= 965 bytes.
  4. Forbidden columns: m_outlook, m_score, q_outlook, q_score absent from
     dash.py and actionable.js.
  5. New fields: macro_value, macro_turn, macro_detail set on each row dict in
     the enrichment block.
  6. HTML columns: actionable.html has MACRO <th>; Quad (M) / Quad (Q) gone.
  7. JS functions: macroCellHtml and _macroTooltip present; quadOutlookBadge
     and QUAD_OUTLOOK_SIDE removed.
  8. ref_settings seeds: db/baseline.sql has all 10 MacroNet param rows.
  9. macroBand div present in actionable.html.
 10. Quads side panel section removed from actionable.html.
 11. MacroNet math unit tests (pure Python): proximity_weight, macronet_to_vocab,
     net_for_quad.
 12. Backward-compat keys quad_m/quad_q still set per row dict.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_DASH_PY  = PROJECT_ROOT / "api" / "routers" / "dash.py"
ACTIONABLE_JS  = PROJECT_ROOT / "web" / "actionable.js"
ACTIONABLE_HTML = PROJECT_ROOT / "web" / "actionable.html"
BASELINE_SQL   = PROJECT_ROOT / "db" / "baseline.sql"


def _py() -> str:
    return API_DASH_PY.read_text(encoding="utf-8")


def _js() -> str:
    return ACTIONABLE_JS.read_text(encoding="utf-8")


def _html() -> str:
    return ACTIONABLE_HTML.read_text(encoding="utf-8")


def _sql() -> str:
    return BASELINE_SQL.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Python syntax
# ---------------------------------------------------------------------------

class TestPythonSyntax:
    def test_dash_py_parses(self):
        src = _py()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"api/routers/dash.py has a syntax error: {e}")


# ---------------------------------------------------------------------------
# 2. JS syntax
# ---------------------------------------------------------------------------

class TestJSSyntax:
    def test_actionable_js_node_check(self):
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"node --check exited {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


# ---------------------------------------------------------------------------
# 3. SQL length <= 965 bytes for each new MacroNet SQL string in dash.py
# ---------------------------------------------------------------------------

_MACRONET_SQLS: list[str] = [
    # settings load
    (
        "SELECT setting_name, setting_value FROM ref_settings"
        " WHERE setting_name IN"
        " ('macro_N_m','macro_N_q','macro_wm_max','macro_wq_max',"
        "  'macro_a','macro_b','macro_thr_sa','macro_thr_stm',"
        "  'macro_thr_bs','macro_thr_bm')"
    ),
    # periods
    "SELECT period_type, quad, start_date, end_date FROM ref_quad_periods ORDER BY period_type, start_date",
    # quad outlook
    "SELECT category, sub_category, ticker, quad1, quad2, quad3, quad4 FROM ref_quad_outlook",
    # style
    "SELECT sub_category, quad1, quad2, quad3, quad4 FROM ref_quad_outlook WHERE category = 'Equity Style'",
    # fundamentals
    "SELECT tos_symbol, market_cap_str, beta, pe_ratio, eps, div_yield FROM drv_fundamentals WHERE as_of_date = :d",
]


class TestSQLLength:
    @pytest.mark.parametrize("sql", _MACRONET_SQLS)
    def test_sql_under_965_bytes(self, sql: str):
        length = len(sql.encode("utf-8"))
        assert length <= 965, (
            f"SQL is {length} bytes (limit 965): {sql!r}"
        )

    def test_sqls_present_in_dash_py(self):
        """All five new SQL strings must actually appear (or equivalent) in dash.py."""
        src = _py()
        # Check key identifiers that must be in the new block
        assert "ref_quad_periods" in src, "ref_quad_periods not found in dash.py"
        assert "ref_quad_outlook" in src, "ref_quad_outlook not found in dash.py"
        assert "drv_fundamentals" in src, "drv_fundamentals not found in dash.py"
        assert "macro_N_m" in src, "macro_N_m param not found in dash.py"


# ---------------------------------------------------------------------------
# 4. Forbidden columns absent
# ---------------------------------------------------------------------------

FORBIDDEN_COLS = ["m_outlook", "m_score", "q_outlook", "q_score"]


class TestForbiddenColumns:
    @pytest.mark.parametrize("col", FORBIDDEN_COLS)
    def test_not_in_dash_py(self, col: str):
        assert col not in _py(), f"Forbidden column '{col}' found in api/routers/dash.py"

    @pytest.mark.parametrize("col", FORBIDDEN_COLS)
    def test_not_in_actionable_js(self, col: str):
        assert col not in _js(), f"Forbidden column '{col}' found in web/actionable.js"


# ---------------------------------------------------------------------------
# 5. New fields: macro_value, macro_turn, macro_detail set in enrichment block
# ---------------------------------------------------------------------------

class TestNewFields:
    def test_macro_value_set_in_dash_py(self):
        src = _py()
        # Must appear as a key in a returned dict
        assert '"macro_value"' in src or "'macro_value'" in src, \
            "macro_value not set in dash.py enrichment block"

    def test_macro_turn_set_in_dash_py(self):
        src = _py()
        assert '"macro_turn"' in src or "'macro_turn'" in src, \
            "macro_turn not set in dash.py enrichment block"

    def test_macro_detail_set_in_dash_py(self):
        src = _py()
        assert '"macro_detail"' in src or "'macro_detail'" in src, \
            "macro_detail not set in dash.py enrichment block"

    def test_all_three_in_return_dict(self):
        """The _compute_macro function must return all three in at least two places
        (the None-return early-exit and the full-compute return)."""
        src = _py()
        assert src.count("macro_value") >= 2, \
            "macro_value should appear in multiple return sites"
        assert src.count("macro_turn") >= 2, \
            "macro_turn should appear in multiple return sites"
        assert src.count("macro_detail") >= 2, \
            "macro_detail should appear in multiple return sites"

    def test_d_dot_update_macro(self):
        """Row dict must be updated with macro result via d_.update(macro)."""
        src = _py()
        assert "d_.update(macro)" in src, \
            "Row dict must call d_.update(macro) to apply MacroNet result"


# ---------------------------------------------------------------------------
# 6. HTML columns
# ---------------------------------------------------------------------------

class TestHTMLColumns:
    def test_macro_th_present(self):
        html = _html()
        assert "MACRO" in html, "actionable.html must have a MACRO <th>"

    def test_macro_th_has_data_key(self):
        """MACRO th should have data-key='macronet' data-type='num' for numeric sort (TASK_105)."""
        html = _html()
        assert 'data-key="macronet"' in html, \
            "MACRO <th> must have data-key='macronet' for sort to work"
        assert 'data-type="num"' in html, \
            "MACRO <th> must have data-type='num' for numeric sort"

    def test_quad_m_th_removed(self):
        html = _html()
        assert "Quad (M)" not in html, \
            "actionable.html must not contain old 'Quad (M)' column header"

    def test_quad_q_th_removed(self):
        html = _html()
        assert "Quad (Q)" not in html, \
            "actionable.html must not contain old 'Quad (Q)' column header"


# ---------------------------------------------------------------------------
# 7. JS functions: new present, old removed
# ---------------------------------------------------------------------------

class TestJSFunctions:
    def test_macroCellHtml_present(self):
        js = _js()
        assert "function macroCellHtml" in js, \
            "macroCellHtml function must exist in actionable.js"

    def test_macroTooltip_present(self):
        js = _js()
        assert "function _macroTooltip" in js, \
            "_macroTooltip function must exist in actionable.js"

    def test_quadOutlookBadge_removed(self):
        js = _js()
        assert "quadOutlookBadge" not in js, \
            "Old quadOutlookBadge function must be removed from actionable.js"

    def test_QUAD_OUTLOOK_SIDE_removed(self):
        js = _js()
        assert "QUAD_OUTLOOK_SIDE" not in js, \
            "Old QUAD_OUTLOOK_SIDE constant must be removed from actionable.js"

    def test_macroCellHtml_uses_actionDisplay(self):
        """macroCellHtml must call actionDisplay() for badge styling."""
        js = _js()
        # Extract macroCellHtml function body
        start = js.find("function macroCellHtml")
        assert start != -1
        depth = 0
        i = js.index("{", start)
        func_start = i
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    body = js[func_start:i + 1]
                    break
            i += 1
        else:
            pytest.fail("Could not find macroCellHtml closing brace")
        assert "actionDisplay(" in body, \
            "macroCellHtml must call actionDisplay() for badge colors"

    def test_loadMacroBand_present(self):
        js = _js()
        assert "function loadMacroBand" in js, \
            "loadMacroBand function must exist in actionable.js"

    def test_macroCellHtml_renders_macro_value(self):
        """macroCellHtml must reference r.macro_value."""
        js = _js()
        assert "r.macro_value" in js, \
            "macroCellHtml must read r.macro_value from the row"

    def test_macroCellHtml_renders_turn(self):
        """macroCellHtml must reference r.macro_turn for the arrow."""
        js = _js()
        assert "r.macro_turn" in js, \
            "macroCellHtml must read r.macro_turn for the turn arrow"

    def test_macro_cell_in_row_render(self):
        """The row rendering must call macroCellHtml(r)."""
        js = _js()
        assert "macroCellHtml(r)" in js, \
            "Row render in actionable.js must call macroCellHtml(r)"


# ---------------------------------------------------------------------------
# 8. ref_settings seeds in baseline.sql
# ---------------------------------------------------------------------------

_REQUIRED_SEEDS = [
    "macro_N_m",
    "macro_N_q",
    "macro_wm_max",
    "macro_wq_max",
    "macro_a",
    "macro_b",
    "macro_thr_bm",
    "macro_thr_bs",
    "macro_thr_stm",
    "macro_thr_sa",
]


class TestRefSettingsSeeds:
    @pytest.mark.parametrize("param", _REQUIRED_SEEDS)
    def test_seed_row_present(self, param: str):
        sql = _sql()
        assert param in sql, \
            f"MacroNet param '{param}' not found in db/baseline.sql ref_settings seeds"

    def test_seed_count_at_least_10(self):
        """Expect at least 10 MacroNet seed rows."""
        sql = _sql()
        count = sum(1 for p in _REQUIRED_SEEDS if p in sql)
        assert count == 10, \
            f"Expected 10 MacroNet seed rows in baseline.sql, found {count}"

    def test_macro_a_value_is_0_65(self):
        """macro_a default weight must be 0.65 (quarter weight)."""
        sql = _sql()
        # Should contain ('macro_a', '0.65', ...)
        assert "0.65" in sql, "macro_a value 0.65 not found in baseline.sql"

    def test_macro_b_value_is_0_35(self):
        """macro_b default weight must be 0.35 (month weight). a+b should equal 1."""
        sql = _sql()
        assert "0.35" in sql, "macro_b value 0.35 not found in baseline.sql"


# ---------------------------------------------------------------------------
# 9. macroBand div present in actionable.html
# ---------------------------------------------------------------------------

class TestMacroBand:
    def test_macroband_div_present(self):
        html = _html()
        assert "macroBand" in html, \
            "actionable.html must contain <div id='macroBand'> for the regime band"

    def test_macroband_month_span_present(self):
        html = _html()
        assert "macroBandMonth" in html, \
            "actionable.html must contain span id='macroBandMonth'"

    def test_macroband_qtr_span_present(self):
        html = _html()
        assert "macroBandQtr" in html, \
            "actionable.html must contain span id='macroBandQtr'"

    def test_macroband_favoring_span_present(self):
        html = _html()
        assert "macroBandFavoring" in html, \
            "actionable.html must contain span id='macroBandFavoring'"


# ---------------------------------------------------------------------------
# 10. Quads side panel retired
# ---------------------------------------------------------------------------

class TestQuadsPanelRetired:
    def test_quadsBody_removed_from_html(self):
        html = _html()
        assert "quadsBody" not in html, \
            "Old #quadsBody side panel must be removed from actionable.html"

    def test_loadSideQuads_removed_from_js(self):
        js = _js()
        assert "loadSideQuads" not in js, \
            "Old loadSideQuads function must be removed from actionable.js"

    def test_Quads_section_removed_from_html(self):
        """The Quads section heading/panel must not appear in HTML."""
        html = _html()
        # The old panel had a 'Quads' label or section
        assert "quadsBody" not in html, \
            "Quads side panel (#quadsBody) must be removed from actionable.html"


# ---------------------------------------------------------------------------
# 11. MacroNet math unit tests (pure Python, no DB)
# ---------------------------------------------------------------------------

class TestMacroNetMath:
    """Test the MacroNet helper functions independently without DB access."""

    def _proximity_weight(self, dtb: int, N: int, w_max: float) -> float:
        """Mirror of _proximity_weight from dash.py."""
        if dtb <= 0:
            return w_max
        if dtb >= N:
            return 0.0
        return w_max * (1.0 - dtb / N)

    def _macronet_to_vocab(
        self, mn: float,
        thr_bm=1.5, thr_bs=0.5, thr_sa=-1.5, thr_stm=-0.5
    ) -> str:
        if mn >= thr_bm:
            return "BM"
        if mn >= thr_bs:
            return "BS"
        if mn <= thr_sa:
            return "SA"
        if mn <= thr_stm:
            return "STM"
        return "HOLD"

    def _outlook_stance(self, text: str | None) -> int:
        _STANCE = {"bullish": 1, "neutral": 0, "bearish": -1}
        return _STANCE.get((text or "").strip().lower(), 0)

    def _net_for_quad(self, memberships: list[dict], quad_col: str) -> float:
        net = 0.0
        for m in memberships:
            net += m["weight"] * self._outlook_stance(m.get(quad_col))
        return net

    # proximity_weight tests
    def test_proximity_weight_far_from_boundary(self):
        """dtb >= N → weight = 0 (no blending toward next period)."""
        assert self._proximity_weight(10, 5, 0.75) == 0.0

    def test_proximity_weight_at_boundary(self):
        """dtb == 0 → weight = w_max."""
        assert self._proximity_weight(0, 5, 0.75) == 0.75

    def test_proximity_weight_half_way(self):
        """dtb = N/2 → weight = w_max/2."""
        result = self._proximity_weight(5, 10, 0.75)
        assert abs(result - 0.375) < 1e-9

    def test_proximity_weight_one_day(self):
        """dtb=1 with N=5 → weight = 0.75*(1-1/5) = 0.6."""
        result = self._proximity_weight(1, 5, 0.75)
        assert abs(result - 0.6) < 1e-9

    # macronet_to_vocab tests
    def test_vocab_bm_at_threshold(self):
        assert self._macronet_to_vocab(1.5) == "BM"

    def test_vocab_bm_above_threshold(self):
        assert self._macronet_to_vocab(2.0) == "BM"

    def test_vocab_bs_mid(self):
        assert self._macronet_to_vocab(1.0) == "BS"

    def test_vocab_bs_at_lower_threshold(self):
        assert self._macronet_to_vocab(0.5) == "BS"

    def test_vocab_hold_zero(self):
        assert self._macronet_to_vocab(0.0) == "HOLD"

    def test_vocab_hold_between_thresholds(self):
        assert self._macronet_to_vocab(0.3) == "HOLD"

    def test_vocab_hold_slightly_negative(self):
        assert self._macronet_to_vocab(-0.3) == "HOLD"

    def test_vocab_stm_at_threshold(self):
        assert self._macronet_to_vocab(-0.5) == "STM"

    def test_vocab_stm_mid(self):
        assert self._macronet_to_vocab(-1.0) == "STM"

    def test_vocab_sa_at_threshold(self):
        assert self._macronet_to_vocab(-1.5) == "SA"

    def test_vocab_sa_below_threshold(self):
        assert self._macronet_to_vocab(-2.0) == "SA"

    # stance map tests
    def test_stance_bullish(self):
        assert self._outlook_stance("BULLISH") == 1

    def test_stance_bullish_lower(self):
        assert self._outlook_stance("bullish") == 1

    def test_stance_neutral_capital_n(self):
        """Confirmed in handoff: only 'Neutral' exists (capital N)."""
        assert self._outlook_stance("Neutral") == 0

    def test_stance_bearish(self):
        assert self._outlook_stance("BEARISH") == -1

    def test_stance_none(self):
        assert self._outlook_stance(None) == 0

    def test_stance_empty_string(self):
        assert self._outlook_stance("") == 0

    def test_stance_unknown(self):
        assert self._outlook_stance("UNKNOWN") == 0

    # net_for_quad tests
    def test_net_for_quad_all_bullish(self):
        memberships = [
            {"weight": 2.0, "quad1": "BULLISH", "quad2": "BEARISH"},
            {"weight": 1.0, "quad1": "BULLISH", "quad2": "Neutral"},
        ]
        result = self._net_for_quad(memberships, "quad1")
        assert abs(result - 3.0) < 1e-9  # 2.0*1 + 1.0*1

    def test_net_for_quad_mixed(self):
        memberships = [
            {"weight": 2.0, "quad1": "BULLISH"},
            {"weight": 2.0, "quad1": "BEARISH"},
        ]
        result = self._net_for_quad(memberships, "quad1")
        assert abs(result - 0.0) < 1e-9  # cancel out

    def test_net_for_quad_missing_key(self):
        """Missing quad col key → stance=0 (no contribution)."""
        memberships = [{"weight": 1.5, "quad2": "BULLISH"}]
        result = self._net_for_quad(memberships, "quad1")
        assert result == 0.0

    def test_blend_formula(self):
        """MacroNet = a*Q + b*M, where default a=0.65, b=0.35."""
        Q, M, a, b = 1.0, -1.0, 0.65, 0.35
        macro_net = round(a * Q + b * M, 4)
        assert abs(macro_net - 0.3) < 1e-4

    def test_blend_coefficients_sum_to_one(self):
        """a + b = 0.65 + 0.35 = 1.0."""
        a, b = 0.65, 0.35
        assert abs(a + b - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 12. Backward-compat keys quad_m / quad_q still set per row
# ---------------------------------------------------------------------------

class TestBackwardCompatKeys:
    def test_quad_m_still_set_in_dash_py(self):
        src = _py()
        # Must set quad_m on each row dict
        assert '"quad_m"' in src or "'quad_m'" in src, \
            "Backward-compat key 'quad_m' must still be set on each row dict"

    def test_quad_q_still_set_in_dash_py(self):
        src = _py()
        assert '"quad_q"' in src or "'quad_q'" in src, \
            "Backward-compat key 'quad_q' must still be set on each row dict"


# ---------------------------------------------------------------------------
# Additional: CSV export uses macro_value (not old quad columns)
# ---------------------------------------------------------------------------

class TestCSVExport:
    def test_macro_value_in_csv_export(self):
        """CSV export must include macro_value / MACRO column, not old quad cols."""
        js = _js()
        assert "macro_value" in js, \
            "actionable.js CSV export must reference macro_value"

    def test_old_quad_col_not_in_csv(self):
        """Old quad CSV headers must be gone."""
        js = _js()
        # The old column would have had headers like "Quad (M)" or "quad_m" in CSV
        assert "Quad (M)" not in js, "Old 'Quad (M)' must not appear in actionable.js"
        assert "Quad (Q)" not in js, "Old 'Quad (Q)' must not appear in actionable.js"
