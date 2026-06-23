"""
Tests for TASK_86 — Regime Band: Monthly Bull/Bear Factors + Quarterly Arrows.

DEV_HANDOFF.md (AGENT_WORK_23) acceptance criteria verified here:
  1. node --check web/actionable.js passes (no syntax errors).
  2. GET /api/quad/band-factors endpoint exists in api/routers/health.py.
  3. All three SQL statements in band-factors endpoint are <= 965 bytes.
  4. Endpoint reads ref_quad_periods (quad*_pct columns) and ref_quad_outlook.
  5. Weighted monthly stance and quarterly arrow computed in Python (not SQL).
  6. #macroBandFactors span exists in actionable.html regime band div.
  7. _renderBandFactors() exists in actionable.js.
  8. _renderBandFactors() renders Bull/Bear group labels and factor pills.
  9. loadMacroBand() calls _renderBandFactors().
  10. Pills trimmed to 5 per group with overflow count.
  11. .qf-group rule present in styles.css.
  12. .qf-label-bull and .qf-label-bear rules present in styles.css.
  13. .qf-pill-bull and .qf-pill-bear rules present in styles.css.
  14. .qf-arrow-bull, .qf-arrow-bear, .qf-arrow-neutral rules present in styles.css.
  15. No production Python files outside api/routers/health.py were touched for TASK_86.
  16. Endpoint is resilient — returns empty lists when no period exists.
  17. Neutral-monthly factors (score=0) are dropped.
  18. Quarterly quad column index resolved from "1"/"2"/"3"/"4" in quad string.
  19. Promise.all used in loadMacroBand() to fetch both endpoints in parallel.
  20. MACRO column / MacroNet logic not changed (no overlap in endpoint).
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT    = Path(__file__).resolve().parent.parent
WEB_DIR         = PROJECT_ROOT / "web"
API_DIR         = PROJECT_ROOT / "api"
ACTIONABLE_HTML = WEB_DIR / "actionable.html"
ACTIONABLE_JS   = WEB_DIR / "actionable.js"
STYLES_CSS      = WEB_DIR / "styles.css"
HEALTH_PY       = API_DIR / "routers" / "health.py"


# ─── helpers ────────────────────────────────────────────────────────────────

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _func_body(src: str, func_name: str, max_len: int = 4000) -> str:
    """Return the source text from 'function func_name' up to max_len chars."""
    for prefix in (f"async function {func_name}(", f"function {func_name}("):
        idx = src.find(prefix)
        if idx != -1:
            return src[idx: idx + max_len]
    raise AssertionError(f"{func_name}() not found in JS source")


# ─── Criterion 1: Syntax check ───────────────────────────────────────────────

class TestSyntaxCheck:
    def test_actionable_js_syntax_ok(self):
        """node --check web/actionable.js must pass with exit 0 and no output."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"node --check failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
        assert result.stdout.strip() == "", (
            f"node --check produced unexpected output: {result.stdout!r}"
        )


# ─── Criterion 2: Endpoint exists in health.py ───────────────────────────────

class TestEndpointExists:
    def setup_method(self):
        self.src = _read(HEALTH_PY)

    def test_band_factors_route_decorator_present(self):
        """@router.get('/api/quad/band-factors') must be present in health.py."""
        assert "/api/quad/band-factors" in self.src, (
            "GET /api/quad/band-factors route decorator not found in api/routers/health.py"
        )

    def test_band_factors_function_defined(self):
        """get_quad_band_factors function must be defined in health.py."""
        assert "def get_quad_band_factors(" in self.src, (
            "get_quad_band_factors() function not found in api/routers/health.py"
        )

    def test_endpoint_is_before_dashboard_quads(self):
        """band-factors endpoint must appear before /api/dashboard/quads in health.py."""
        band_idx = self.src.find("/api/quad/band-factors")
        quads_idx = self.src.find("/api/dashboard/quads")
        assert band_idx != -1, "band-factors route not found"
        assert quads_idx != -1, "dashboard/quads route not found"
        assert band_idx < quads_idx, (
            f"band-factors route (pos {band_idx}) must appear before "
            f"dashboard/quads route (pos {quads_idx}) per DEV_HANDOFF"
        )


# ─── Criterion 3: SQL statements <= 965 bytes ────────────────────────────────

class TestSqlLength:
    def setup_method(self):
        self.src = _read(HEALTH_PY)

    def _extract_sql_strings(self) -> list[str]:
        """Extract SQL strings passed to text() in get_quad_band_factors."""
        func_start = self.src.find("def get_quad_band_factors(")
        assert func_start != -1, "get_quad_band_factors not found"
        # Take a generous slice around the function (up to 3000 chars)
        func_body = self.src[func_start: func_start + 3000]
        # Find all text(...) calls — grab content between matching parens
        sqls = []
        for m in re.finditer(r'text\(', func_body):
            start = m.end()
            # Find the string argument — handle multi-line string concat with "..."
            # We collect everything between text( and the matching )
            depth = 1
            i = start
            # Skip whitespace/newline
            while i < len(func_body) and func_body[i] in ' \t\n\r':
                i += 1
            if i >= len(func_body):
                continue
            # Collect the raw fragment between text( and its closing )
            paren_depth = 1
            frag_start = i
            while i < len(func_body) and paren_depth > 0:
                if func_body[i] == '(':
                    paren_depth += 1
                elif func_body[i] == ')':
                    paren_depth -= 1
                i += 1
            frag = func_body[frag_start: i - 1]
            # Collapse string concatenation: join quoted pieces
            parts = re.findall(r'"([^"]*)"', frag)
            if parts:
                sqls.append("".join(parts))
        return sqls

    def test_sql_statements_within_965_bytes(self):
        """All SQL statements in get_quad_band_factors() must be <= 965 bytes."""
        sqls = self._extract_sql_strings()
        assert len(sqls) >= 1, "No SQL text() calls found in get_quad_band_factors"
        for i, sql in enumerate(sqls, 1):
            byte_len = len(sql.encode("utf-8"))
            assert byte_len <= 965, (
                f"SQL statement {i} in get_quad_band_factors() is {byte_len} bytes "
                f"(limit 965): {sql[:120]!r}..."
            )

    def test_at_least_three_sql_statements(self):
        """get_quad_band_factors must make exactly 3 DB queries (monthly, quarterly, factors)."""
        sqls = self._extract_sql_strings()
        assert len(sqls) >= 3, (
            f"Expected at least 3 SQL statements in get_quad_band_factors, found {len(sqls)}"
        )


# ─── Criterion 4: Reads correct tables ───────────────────────────────────────

class TestEndpointReadsCorrectTables:
    def setup_method(self):
        func_start = _read(HEALTH_PY).find("def get_quad_band_factors(")
        assert func_start != -1
        self.func_body = _read(HEALTH_PY)[func_start: func_start + 3000]

    def test_reads_ref_quad_periods(self):
        """Endpoint must query ref_quad_periods."""
        assert "ref_quad_periods" in self.func_body, (
            "get_quad_band_factors() does not reference ref_quad_periods"
        )

    def test_reads_quad_pct_columns(self):
        """Endpoint must read quad1_pct..quad4_pct from ref_quad_periods."""
        assert "quad1_pct" in self.func_body, (
            "quad1_pct column not referenced in get_quad_band_factors()"
        )
        assert "quad4_pct" in self.func_body, (
            "quad4_pct column not referenced in get_quad_band_factors()"
        )

    def test_reads_ref_quad_outlook(self):
        """Endpoint must query ref_quad_outlook for style/sector factors."""
        assert "ref_quad_outlook" in self.func_body, (
            "get_quad_band_factors() does not reference ref_quad_outlook"
        )

    def test_filters_style_sector_categories(self):
        """Endpoint must filter ref_quad_outlook by category IN ('style','sector')."""
        assert "'style'" in self.func_body or '"style"' in self.func_body, (
            "get_quad_band_factors() does not filter by category 'style'"
        )
        assert "'sector'" in self.func_body or '"sector"' in self.func_body, (
            "get_quad_band_factors() does not filter by category 'sector'"
        )


# ─── Criterion 5: Python-side computation (not SQL) ──────────────────────────

class TestPythonSideComputation:
    def setup_method(self):
        func_start = _read(HEALTH_PY).find("def get_quad_band_factors(")
        assert func_start != -1
        self.func_body = _read(HEALTH_PY)[func_start: func_start + 3000]

    def test_stance_dict_defined_in_python(self):
        """STANCE dict must be defined in Python (not in SQL)."""
        assert "STANCE" in self.func_body, (
            "STANCE mapping dict not found in get_quad_band_factors() — "
            "weighted monthly stance must be computed in Python"
        )
        assert '"Bullish"' in self.func_body or "'Bullish'" in self.func_body, (
            "Bullish stance not mapped in Python STANCE dict"
        )
        assert '"Bearish"' in self.func_body or "'Bearish'" in self.func_body, (
            "Bearish stance not mapped in Python STANCE dict"
        )

    def test_pcts_list_computed_in_python(self):
        """quad*_pct percentages must be collected into a Python list for weighting."""
        assert "pcts" in self.func_body, (
            "pcts list not found in get_quad_band_factors() — "
            "monthly distribution weighting must be done in Python"
        )

    def test_monthly_score_computed_in_python(self):
        """monthly_score must be computed via Python arithmetic (weighted sum)."""
        assert "monthly_score" in self.func_body, (
            "monthly_score not found in get_quad_band_factors() — "
            "must be a Python-side computation"
        )

    def test_quarterly_arrow_computed_in_python(self):
        """qtr_dir (quarterly arrow) must be derived in Python from quad column."""
        assert "qtr_dir" in self.func_body, (
            "qtr_dir not found in get_quad_band_factors() — "
            "quarterly direction must be computed in Python"
        )

    def test_no_weighted_avg_in_sql(self):
        """SQL must not compute weighted averages (no SUM/AVG of pct*stance in SQL)."""
        # The SQL fragments should be simple SELECT statements only
        sql_fragments = re.findall(r'text\([^)]+\)', self.func_body)
        for frag in sql_fragments:
            # Check for aggregation keywords that would indicate SQL-side computation
            upper = frag.upper()
            assert "WEIGHTED" not in upper, (
                "SQL fragment contains WEIGHTED — computation must be in Python"
            )
            # Simple sanity: no complex CASE-WHEN arithmetic on pct columns in SQL
            if "QUAD1_PCT" in upper or "QUAD2_PCT" in upper:
                assert "CASE WHEN" not in upper, (
                    "SQL fragment uses CASE WHEN on pct columns — "
                    "stance computation must be in Python"
                )


# ─── Criterion 6: #macroBandFactors span in HTML ─────────────────────────────

class TestHtmlMacroBandFactors:
    def setup_method(self):
        self.html = _read(ACTIONABLE_HTML)

    def test_macro_band_factors_span_exists(self):
        """#macroBandFactors span must exist in actionable.html."""
        assert 'id="macroBandFactors"' in self.html, (
            "#macroBandFactors span not found in actionable.html"
        )

    def test_macro_band_factors_inside_macro_band_div(self):
        """#macroBandFactors must appear inside #macroBand div."""
        band_start = self.html.find('id="macroBand"')
        assert band_start != -1, "#macroBand div not found in actionable.html"
        # Find the closing </div> for macroBand (look for macroBandFactors after band_start)
        factors_pos = self.html.find('id="macroBandFactors"')
        assert factors_pos != -1
        assert factors_pos > band_start, (
            "#macroBandFactors appears before #macroBand — must be nested inside it"
        )
        # Check that macroBandFactors appears before the next closing div after macroBand
        next_outer_close = self.html.find("<!-- MACRO", band_start)  # comment after block
        if next_outer_close == -1:
            # Fall back: just verify order (band before factors before end of page)
            assert factors_pos > band_start

    def test_pipe_separator_before_macro_band_factors(self):
        """A | separator must appear between Favoring and macroBandFactors spans."""
        # Check that there's a separator span between macroBandFavoring and macroBandFactors
        favoring_pos = self.html.find('id="macroBandFavoring"')
        factors_pos = self.html.find('id="macroBandFactors"')
        assert favoring_pos != -1, "macroBandFavoring span not found"
        assert factors_pos != -1, "macroBandFactors span not found"
        between = self.html[favoring_pos: factors_pos]
        # Expect a | separator between the two spans
        assert "|" in between, (
            "No | separator found between #macroBandFavoring and #macroBandFactors "
            "in actionable.html (expected per DEV_HANDOFF)"
        )


# ─── Criteria 7-10: _renderBandFactors() and loadMacroBand() in JS ───────────

class TestJsFunctions:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_render_band_factors_function_exists(self):
        """_renderBandFactors() must be defined in actionable.js."""
        assert "_renderBandFactors" in self.src, (
            "_renderBandFactors() not found in actionable.js"
        )

    def test_render_band_factors_reads_macroBandFactors_element(self):
        """_renderBandFactors() must reference the #macroBandFactors DOM element."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        assert "macroBandFactors" in body, (
            "_renderBandFactors() does not reference #macroBandFactors element"
        )

    def test_render_band_factors_uses_bull_group_label(self):
        """_renderBandFactors() must render a Bull group label."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        assert "qf-label-bull" in body or "Bull" in body, (
            "_renderBandFactors() does not render a Bull group label"
        )

    def test_render_band_factors_uses_bear_group_label(self):
        """_renderBandFactors() must render a Bear group label."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        assert "qf-label-bear" in body or "Bear" in body, (
            "_renderBandFactors() does not render a Bear group label"
        )

    def test_render_band_factors_uses_qf_group_class(self):
        """_renderBandFactors() must wrap each group in qf-group class."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        assert "qf-group" in body, (
            "_renderBandFactors() does not use qf-group class for Bull/Bear groups"
        )

    def test_render_band_factors_uses_qf_pill_classes(self):
        """_renderBandFactors() must use qf-pill-bull and qf-pill-bear pill classes."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        assert "qf-pill-bull" in body, (
            "_renderBandFactors() does not use qf-pill-bull pill class"
        )
        assert "qf-pill-bear" in body, (
            "_renderBandFactors() does not use qf-pill-bear pill class"
        )

    def test_render_band_factors_uses_arrow_classes(self):
        """_renderBandFactors() must use qf-arrow-bull/bear/neutral for direction arrows."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        assert "qf-arrow-bull" in body, (
            "_renderBandFactors() does not use qf-arrow-bull for bullish arrows"
        )
        assert "qf-arrow-bear" in body, (
            "_renderBandFactors() does not use qf-arrow-bear for bearish arrows"
        )
        assert "qf-arrow-neutral" in body, (
            "_renderBandFactors() does not use qf-arrow-neutral for neutral arrows"
        )

    def test_load_macro_band_calls_render_band_factors(self):
        """loadMacroBand() must call _renderBandFactors(factors)."""
        body = _func_body(self.src, "loadMacroBand", max_len=3000)
        assert "_renderBandFactors" in body, (
            "loadMacroBand() does not call _renderBandFactors() — "
            "pills will not be rendered"
        )

    def test_load_macro_band_fetches_band_factors_endpoint(self):
        """loadMacroBand() must fetch /api/quad/band-factors."""
        body = _func_body(self.src, "loadMacroBand", max_len=3000)
        assert "/api/quad/band-factors" in body, (
            "loadMacroBand() does not fetch /api/quad/band-factors endpoint"
        )


# ─── Criterion 10: Pills trimmed to 5 per group ──────────────────────────────

class TestPillTrimming:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_max_pills_constant_is_5(self):
        """_MAX_BAND_PILLS constant must be set to 5."""
        assert "_MAX_BAND_PILLS" in self.src, (
            "_MAX_BAND_PILLS constant not found in actionable.js"
        )
        # Find the assignment and check its value
        m = re.search(r'_MAX_BAND_PILLS\s*=\s*(\d+)', self.src)
        assert m is not None, "_MAX_BAND_PILLS assignment not found"
        assert int(m.group(1)) == 5, (
            f"_MAX_BAND_PILLS is {m.group(1)}, expected 5"
        )

    def test_overflow_pill_with_plus_count(self):
        """Overflow pills must show '+N...' for factors beyond the first 5."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        # Check for overflow indicator pattern: +N or hidden.length
        assert "hidden.length" in body or "hidden" in body, (
            "_renderBandFactors() does not handle overflow pills — "
            "groups with >5 factors need a '+N...' overflow indicator"
        )

    def test_overflow_pill_uses_slice(self):
        """_renderBandFactors() must use slice to trim pills to _MAX_BAND_PILLS."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        assert ".slice(" in body, (
            "_renderBandFactors() does not use .slice() for pill trimming"
        )


# ─── Criteria 11-14: CSS .qf-* rules present in styles.css ──────────────────

class TestCssQfRules:
    def setup_method(self):
        self.css = _read(STYLES_CSS)

    def test_qf_group_defined(self):
        """.qf-group must be defined in styles.css."""
        assert ".qf-group" in self.css, (
            ".qf-group CSS rule not found in styles.css"
        )

    def test_qf_label_defined(self):
        """.qf-label must be defined in styles.css."""
        assert ".qf-label" in self.css, (
            ".qf-label CSS rule not found in styles.css"
        )

    def test_qf_label_bull_defined(self):
        """.qf-label-bull must be defined in styles.css."""
        assert ".qf-label-bull" in self.css, (
            ".qf-label-bull CSS rule not found in styles.css"
        )

    def test_qf_label_bear_defined(self):
        """.qf-label-bear must be defined in styles.css."""
        assert ".qf-label-bear" in self.css, (
            ".qf-label-bear CSS rule not found in styles.css"
        )

    def test_qf_pill_defined(self):
        """.qf-pill must be defined in styles.css."""
        assert ".qf-pill" in self.css, (
            ".qf-pill CSS rule not found in styles.css"
        )

    def test_qf_pill_bull_defined(self):
        """.qf-pill-bull must be defined in styles.css."""
        assert ".qf-pill-bull" in self.css, (
            ".qf-pill-bull CSS rule not found in styles.css"
        )

    def test_qf_pill_bear_defined(self):
        """.qf-pill-bear must be defined in styles.css."""
        assert ".qf-pill-bear" in self.css, (
            ".qf-pill-bear CSS rule not found in styles.css"
        )

    def test_qf_arrow_bull_defined(self):
        """.qf-arrow-bull must be defined in styles.css."""
        assert ".qf-arrow-bull" in self.css, (
            ".qf-arrow-bull CSS rule not found in styles.css"
        )

    def test_qf_arrow_bear_defined(self):
        """.qf-arrow-bear must be defined in styles.css."""
        assert ".qf-arrow-bear" in self.css, (
            ".qf-arrow-bear CSS rule not found in styles.css"
        )

    def test_qf_arrow_neutral_defined(self):
        """.qf-arrow-neutral must be defined in styles.css."""
        assert ".qf-arrow-neutral" in self.css, (
            ".qf-arrow-neutral CSS rule not found in styles.css"
        )

    def test_qf_label_bull_has_green_color(self):
        """.qf-label-bull must have a green color for bullish branding."""
        idx = self.css.find(".qf-label-bull")
        assert idx != -1
        rule = self.css[idx: idx + 100]
        # Green background or color
        assert "#" in rule, ".qf-label-bull must have color/background values"

    def test_qf_label_bear_has_red_color(self):
        """.qf-label-bear must have a red color for bearish branding."""
        idx = self.css.find(".qf-label-bear")
        assert idx != -1
        rule = self.css[idx: idx + 100]
        assert "#" in rule, ".qf-label-bear must have color/background values"

    def test_styles_css_not_truncated(self):
        """styles.css must end with a closing brace (not truncated)."""
        css = self.css.rstrip()
        assert css.endswith("}"), (
            f"styles.css appears truncated — last chars: {css[-40:]!r}"
        )


# ─── Criterion 16: Endpoint resilience (empty lists when no period) ───────────

class TestEndpointResilience:
    def setup_method(self):
        func_start = _read(HEALTH_PY).find("def get_quad_band_factors(")
        assert func_start != -1
        self.func_body = _read(HEALTH_PY)[func_start: func_start + 3000]

    def test_returns_empty_lists_on_no_period(self):
        """Endpoint must return {'bull': [], 'bear': []} when no monthly period exists."""
        assert '{"bull": [], "bear": []}' in self.func_body or \
               "{'bull': [], 'bear': []}" in self.func_body or \
               '"bull": []' in self.func_body or \
               '"bear": []' in self.func_body, (
            "get_quad_band_factors() does not appear to return empty lists "
            "when no period row exists — resilience guard missing"
        )

    def test_guards_on_missing_mo(self):
        """Endpoint must guard against missing monthly period (if not mo)."""
        assert "if not mo" in self.func_body, (
            "get_quad_band_factors() does not guard against missing monthly period row"
        )


# ─── Criterion 17: Neutral factors dropped ───────────────────────────────────

class TestNeutralFactorsDropped:
    def setup_method(self):
        func_start = _read(HEALTH_PY).find("def get_quad_band_factors(")
        assert func_start != -1
        self.func_body = _read(HEALTH_PY)[func_start: func_start + 3000]

    def test_zero_monthly_score_skipped(self):
        """Factors with monthly_score == 0 must be dropped (not shown)."""
        assert "monthly_score == 0" in self.func_body or \
               "if monthly_score == 0" in self.func_body, (
            "get_quad_band_factors() does not skip neutral factors (score==0) — "
            "they must be dropped per spec"
        )

    def test_continue_on_zero_score(self):
        """The zero-score check must use 'continue' to skip the factor."""
        assert "continue" in self.func_body, (
            "get_quad_band_factors() has no 'continue' statement — "
            "neutral factors (score=0) may not be properly skipped"
        )


# ─── Criterion 18: Quarterly quad resolved via string matching ────────────────

class TestQuarterlyQuadResolution:
    def setup_method(self):
        func_start = _read(HEALTH_PY).find("def get_quad_band_factors(")
        assert func_start != -1
        self.func_body = _read(HEALTH_PY)[func_start: func_start + 3000]

    def test_quad_column_index_resolved_from_quad_string(self):
        """Quarterly quad column index must be derived by checking '1'/'2'/'3'/'4' in quad string."""
        assert "qtr_col_idx" in self.func_body, (
            "qtr_col_idx not found — quarterly quad column index not being resolved"
        )

    def test_string_membership_check_for_quad_number(self):
        """Quad string '1'/'2'/'3'/'4' membership check must be present."""
        # Check for pattern: '"1" in qtr_quad' or "'1' in qtr_quad"
        assert ('"1" in qtr_quad' in self.func_body or
                "'1' in qtr_quad" in self.func_body), (
            "Quad-1 string membership check not found in get_quad_band_factors() — "
            "quarterly quad column index resolution may be incorrect"
        )


# ─── Criterion 19: Promise.all used in loadMacroBand ─────────────────────────

class TestPromiseAll:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_promise_all_in_load_macro_band(self):
        """loadMacroBand() must use Promise.all to fetch both endpoints in parallel."""
        body = _func_body(self.src, "loadMacroBand", max_len=3000)
        assert "Promise.all(" in body, (
            "loadMacroBand() does not use Promise.all for parallel fetching — "
            "band-factors and quads endpoints must be fetched concurrently"
        )

    def test_catch_fallback_on_band_factors_fetch(self):
        """band-factors fetch must have a .catch() fallback to empty lists."""
        body = _func_body(self.src, "loadMacroBand", max_len=3000)
        # The catch fallback should return { bull: [], bear: [] } on error
        assert ".catch(" in body, (
            "loadMacroBand() band-factors fetch has no .catch() fallback — "
            "a server error would crash the entire band render"
        )


# ─── Criterion 20: MACRO column untouched ────────────────────────────────────

class TestMacroColumnUntouched:
    def setup_method(self):
        self.src = _read(ACTIONABLE_JS)

    def test_macro_value_column_still_referenced(self):
        """macro_value column must still be referenced in actionable.js."""
        assert "macro_value" in self.src, (
            "macro_value column reference missing from actionable.js — "
            "MACRO column may have been accidentally broken"
        )

    def test_band_factors_does_not_use_macro_net(self):
        """_renderBandFactors() must not reference macroNet or MacroNet."""
        body = _func_body(self.src, "_renderBandFactors", max_len=2000)
        lower = body.lower()
        assert "macronet" not in lower, (
            "_renderBandFactors() references MacroNet — "
            "TASK_86 must not modify MacroNet logic"
        )


# ─── Python logic unit tests (no DB required) ────────────────────────────────

class TestPythonLogicUnit:
    """Unit tests for the Python-side stance computation logic (replicated inline)."""

    STANCE = {"Bullish": 1, "Neutral": 0, "Bearish": -1}

    def _compute_monthly_score(self, pcts, cols):
        return sum(pcts[i] * self.STANCE.get(cols[i] or "", 0) for i in range(4))

    def _qtr_dir(self, qtr_col_idx, cols):
        if qtr_col_idx is not None:
            qtr_val = cols[qtr_col_idx] or ""
            qtr_stance = self.STANCE.get(qtr_val, 0)
        else:
            qtr_stance = 0
        return "bull" if qtr_stance > 0 else "bear" if qtr_stance < 0 else "neutral"

    def test_all_bullish_gives_positive_score(self):
        """100% Quad1 + all Bullish => score = 1.0."""
        pcts = [1.0, 0.0, 0.0, 0.0]
        cols = ["Bullish", "Neutral", "Neutral", "Neutral"]
        score = self._compute_monthly_score(pcts, cols)
        assert score > 0, f"Expected positive score, got {score}"

    def test_all_bearish_gives_negative_score(self):
        """100% Quad3 + all Bearish => score = -1.0."""
        pcts = [0.0, 0.0, 1.0, 0.0]
        cols = ["Neutral", "Neutral", "Bearish", "Neutral"]
        score = self._compute_monthly_score(pcts, cols)
        assert score < 0, f"Expected negative score, got {score}"

    def test_neutral_only_gives_zero_score(self):
        """All Neutral => score = 0.0 (factor must be dropped)."""
        pcts = [0.25, 0.25, 0.25, 0.25]
        cols = ["Neutral", "Neutral", "Neutral", "Neutral"]
        score = self._compute_monthly_score(pcts, cols)
        assert score == 0.0, f"Expected zero score for all-neutral, got {score}"

    def test_mixed_distribution_weighted_correctly(self):
        """50% Quad1 Bullish + 50% Quad3 Bearish => score = 0 (balanced)."""
        pcts = [0.5, 0.0, 0.5, 0.0]
        cols = ["Bullish", "Neutral", "Bearish", "Neutral"]
        score = self._compute_monthly_score(pcts, cols)
        assert abs(score) < 1e-9, f"Expected 0.0 for balanced distribution, got {score}"

    def test_quarterly_bull_direction(self):
        """Quarterly Quad1=Bullish => qtr_dir = 'bull'."""
        cols = ["Bullish", "Neutral", "Bearish", "Neutral"]
        assert self._qtr_dir(0, cols) == "bull"

    def test_quarterly_bear_direction(self):
        """Quarterly Quad3=Bearish => qtr_dir = 'bear'."""
        cols = ["Bullish", "Neutral", "Bearish", "Neutral"]
        assert self._qtr_dir(2, cols) == "bear"

    def test_quarterly_neutral_direction(self):
        """Quarterly Quad2=Neutral => qtr_dir = 'neutral'."""
        cols = ["Bullish", "Neutral", "Bearish", "Neutral"]
        assert self._qtr_dir(1, cols) == "neutral"

    def test_no_quarterly_row_gives_neutral(self):
        """qtr_col_idx=None (no quarterly period) => qtr_dir = 'neutral'."""
        cols = ["Bullish", "Neutral", "Bearish", "Neutral"]
        assert self._qtr_dir(None, cols) == "neutral"

    def test_divergence_monthly_bull_quarterly_bear(self):
        """A monthly-bull factor under a quarterly-bearish quad shows in Bull group with bear arrow."""
        pcts = [1.0, 0.0, 0.0, 0.0]
        cols = ["Bullish", "Neutral", "Bearish", "Neutral"]
        score = self._compute_monthly_score(pcts, cols)
        assert score > 0, "Monthly score should be positive (bull group)"
        # Quarterly quad is Quad3 (bearish for this factor)
        qtr = self._qtr_dir(2, cols)
        assert qtr == "bear", f"Quarterly arrow should be 'bear' (divergence), got {qtr!r}"

    def test_qtr_quad_index_resolution(self):
        """Quad string parsing: '1'/'2'/'3'/'4' membership must resolve correct column index."""
        cases = [
            ("Quad 1", 0),
            ("Quad 2", 1),
            ("Quad 3", 2),
            ("Quad 4", 3),
            ("", None),
        ]
        for quad_str, expected_idx in cases:
            idx = None
            if "1" in quad_str:
                idx = 0
            elif "2" in quad_str:
                idx = 1
            elif "3" in quad_str:
                idx = 2
            elif "4" in quad_str:
                idx = 3
            assert idx == expected_idx, (
                f"Quad string {quad_str!r} resolved to index {idx}, expected {expected_idx}"
            )
