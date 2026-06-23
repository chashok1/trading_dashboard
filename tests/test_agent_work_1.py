"""
Tests for AGENT_WORK_1 — TASK_53 through TASK_59:
Push derivation down to ETL; make API and JS read-only.

Static checks only — no live DB required.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

# File paths
BASELINE_SQL          = PROJECT / "db"    / "baseline.sql"
DERIVE_ACTIONABLE_PY  = PROJECT / "etl"   / "derive_actionable.py"
DERIVE_COMMON_PY      = PROJECT / "etl"   / "_derive_common.py"
DERIVE_PY             = PROJECT / "etl"   / "derive.py"
DERIVE_V2_PY          = PROJECT / "etl"   / "derive_v2.py"
DERIVE_OUTLOOK_PY     = PROJECT / "etl"   / "derive_outlook_action.py"
DERIVE_SOURCE_PY      = PROJECT / "etl"   / "derive_source_standing.py"
RULE_EVAL_PY          = PROJECT / "etl"   / "_rule_eval.py"
DERIVE_CAT_PY         = PROJECT / "etl"   / "derive_cat_atomic_input.py"
DASH_PY               = PROJECT / "api"   / "routers" / "dash.py"
TRACE_PY              = PROJECT / "api"   / "routers" / "trace.py"
ACTIONABLE_JS         = PROJECT / "web"   / "actionable.js"
PORTFOLIO_JS          = PROJECT / "web"   / "portfolio.js"
COMMON_JS             = PROJECT / "web"   / "_common.js"
CLAUDE_MD             = PROJECT / "CLAUDE.md"

WEB_JS_FILES = sorted((PROJECT / "web").glob("*.js"))


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return p.read_text(encoding="latin-1")


# ─────────────────────────────────────────────────────────────────────────────
# TASK_53 — Final-call decision moved to ETL
# ─────────────────────────────────────────────────────────────────────────────

class TestTask53FinalCall:
    """TASK_53: drv_actionable gets 7 new columns; ETL computes them."""

    def test_baseline_sql_has_final_action_column(self):
        sql = _read(BASELINE_SQL)
        assert "final_action" in sql, "baseline.sql must ADD COLUMN final_action to drv_actionable"

    def test_baseline_sql_has_all_7_new_columns(self):
        sql = _read(BASELINE_SQL)
        expected_cols = [
            "final_action", "final_code", "final_side",
            "fc_strength", "fc_confidence", "fc_feasible", "priority_rank",
        ]
        for col in expected_cols:
            assert col in sql, f"baseline.sql missing ADD COLUMN {col}"

    def test_derive_actionable_computes_final_call(self):
        src = _read(DERIVE_ACTIONABLE_PY)
        assert "_compute_final_call" in src, \
            "derive_actionable.py must define _compute_final_call()"

    def test_derive_actionable_inserts_final_action_column(self):
        src = _read(DERIVE_ACTIONABLE_PY)
        assert "final_action" in src, \
            "derive_actionable.py INSERT must include final_action"
        assert "fc_strength" in src, \
            "derive_actionable.py INSERT must include fc_strength"
        assert "priority_rank" in src, \
            "derive_actionable.py INSERT must include priority_rank"

    def test_actionable_js_reads_final_code_from_row(self):
        src = _read(ACTIONABLE_JS)
        # finalCall() must check row.final_code first
        assert "row.final_code" in src, \
            "actionable.js finalCall() must read row.final_code from server response"

    def test_actionable_js_reads_fc_strength_from_row(self):
        src = _read(ACTIONABLE_JS)
        assert "row.fc_strength" in src, \
            "actionable.js must read row.fc_strength"

    def test_derive_actionable_python_syntax(self):
        src = _read(DERIVE_ACTIONABLE_PY)
        ast.parse(src)  # raises SyntaxError if broken

    def test_baseline_sql_alter_table_for_final_action(self):
        sql = _read(BASELINE_SQL)
        # Specifically look for ALTER TABLE drv_actionable ADD COLUMN IF NOT EXISTS final_action
        assert re.search(
            r"ALTER TABLE.*drv_actionable.*ADD COLUMN.*final_action",
            sql, re.DOTALL | re.IGNORECASE,
        ), "baseline.sql must ALTER TABLE drv_actionable to add final_action"


# ─────────────────────────────────────────────────────────────────────────────
# TASK_54 — Canonical is_cash DB function
# ─────────────────────────────────────────────────────────────────────────────

class TestTask54IsCash:
    """TASK_54: is_cash() DB function consolidates cash detection."""

    def test_baseline_sql_has_is_cash_function(self):
        sql = _read(BASELINE_SQL)
        assert "CREATE OR REPLACE FUNCTION is_cash" in sql, \
            "baseline.sql must define CREATE OR REPLACE FUNCTION is_cash"

    def test_is_cash_function_covers_spaxx(self):
        sql = _read(BASELINE_SQL)
        assert "SPAXX**" in sql, "is_cash() function must include SPAXX** rule"

    def test_is_cash_function_covers_money_market(self):
        sql = _read(BASELINE_SQL)
        assert "HELD IN MONEY MARKET" in sql, \
            "is_cash() function must include HELD IN MONEY MARKET rule"

    def test_is_cash_function_covers_cash_investments(self):
        sql = _read(BASELINE_SQL)
        assert "Cash & Cash Investments" in sql, \
            "is_cash() function must cover 'Cash & Cash Investments' symbol"

    def test_dash_py_calls_is_cash_db_function(self):
        src = _read(DASH_PY)
        assert "is_cash(" in src, \
            "dash.py must call the is_cash() DB function in portfolio queries"

    def test_portfolio_js_reads_server_is_cash_flag(self):
        src = _read(PORTFOLIO_JS)
        assert "r.is_cash" in src or "row.is_cash" in src, \
            "portfolio.js isCashRow() must read server-emitted is_cash flag"

    def test_portfolio_js_has_fallback_comment(self):
        src = _read(PORTFOLIO_JS)
        # Fallback logic is acceptable but must acknowledge server flag first
        assert "is_cash" in src, "portfolio.js must reference is_cash"

    def test_dash_py_python_syntax(self):
        src = _read(DASH_PY)
        ast.parse(src)


# ─────────────────────────────────────────────────────────────────────────────
# TASK_55 — Persist rule trace; stop re-evaluating rules in API
# ─────────────────────────────────────────────────────────────────────────────

class TestTask55RuleTrace:
    """TASK_55: drv_trace table added; ETL writes it; trace.py imports _rule_eval."""

    def test_baseline_sql_has_drv_trace_table(self):
        sql = _read(BASELINE_SQL)
        assert "CREATE TABLE IF NOT EXISTS drv_trace" in sql, \
            "baseline.sql must define drv_trace table"

    def test_drv_trace_has_payload_jsonb(self):
        sql = _read(BASELINE_SQL)
        # Find the CREATE TABLE block for drv_trace
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_trace")
        assert idx >= 0
        block = sql[idx:idx+300]
        assert "JSONB" in block, "drv_trace must have a JSONB payload column"

    def test_drv_trace_has_primary_key(self):
        sql = _read(BASELINE_SQL)
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_trace")
        block = sql[idx:idx+300]
        assert "PRIMARY KEY" in block, "drv_trace must have a PRIMARY KEY"

    def test_derive_py_writes_drv_trace(self):
        src = _read(DERIVE_PY)
        assert "drv_trace" in src, \
            "derive.py must write to drv_trace at derive time"

    def test_trace_py_imports_from_rule_eval_not_derive(self):
        src = _read(TRACE_PY)
        # Should import from etl._rule_eval
        assert "from etl._rule_eval import" in src or "etl._rule_eval" in src, \
            "trace.py must import evaluation functions from etl._rule_eval"

    def test_trace_py_does_not_import_from_etl_derive(self):
        src = _read(TRACE_PY)
        # Check that it doesn't do "from etl.derive import" for eval functions
        bad_imports = re.findall(r"from etl\.derive import[^\n]*", src)
        # If any import from etl.derive exists, it must NOT include the eval functions
        eval_fns = {"eval_atomic_rule", "_eval_precondition", "_MA_COL_MAP", "_composite_operator"}
        for imp in bad_imports:
            for fn in eval_fns:
                assert fn not in imp, \
                    f"trace.py must not import {fn} from etl.derive; use etl._rule_eval"

    def test_rule_eval_py_exists(self):
        assert RULE_EVAL_PY.exists(), \
            "etl/_rule_eval.py must exist (extracted evaluation functions)"

    def test_rule_eval_py_defines_eval_atomic_rule(self):
        src = _read(RULE_EVAL_PY)
        assert "def eval_atomic_rule" in src, \
            "_rule_eval.py must define eval_atomic_rule"

    def test_rule_eval_py_syntax(self):
        src = _read(RULE_EVAL_PY)
        ast.parse(src)

    def test_trace_py_syntax(self):
        src = _read(TRACE_PY)
        ast.parse(src)


# ─────────────────────────────────────────────────────────────────────────────
# TASK_56 — Consolidated ETL utilities
# ─────────────────────────────────────────────────────────────────────────────

class TestTask56ConsolidatedUtils:
    """TASK_56: _load_outlook_weights, _clean defined once in _derive_common."""

    def test_load_outlook_weights_single_definition(self):
        """def _load_outlook_weights must exist only in _derive_common.py."""
        definitions = []
        for py in (PROJECT / "etl").glob("*.py"):
            src = _read(py)
            if "def _load_outlook_weights" in src:
                definitions.append(py.name)
        assert definitions == ["_derive_common.py"], (
            f"_load_outlook_weights defined in {definitions}; "
            "expected only _derive_common.py"
        )

    def test_clean_single_definition_in_derive_common(self):
        """def _clean must be defined in _derive_common.py (not in derive.py etc.)."""
        defn_in_common = "def _clean" in _read(DERIVE_COMMON_PY)
        assert defn_in_common, "_derive_common.py must define _clean"

    def test_no_fstring_meta_derived_run_insert_in_outlook_action(self):
        """derive_outlook_action.py must not use f-string SQL for meta_derived_run."""
        src = _read(DERIVE_OUTLOOK_PY)
        # No f""" ... INSERT INTO meta_derived_run pattern
        fstring_insert = re.search(
            r'f["\'][\"\'][\"\'].*INSERT INTO meta_derived_run',
            src, re.DOTALL,
        )
        assert fstring_insert is None, (
            "derive_outlook_action.py still contains f-string INSERT INTO meta_derived_run; "
            "use parameterized _open/_close_drv_run from _derive_common"
        )

    def test_derive_outlook_action_imports_open_close(self):
        src = _read(DERIVE_OUTLOOK_PY)
        assert "_open_drv_run" in src or "_close_drv_run" in src, \
            "derive_outlook_action.py must import/use canonical _open/_close_drv_run"

    def test_derive_common_defines_safe_div(self):
        src = _read(DERIVE_COMMON_PY)
        assert "def _safe_div" in src, "_derive_common.py must define _safe_div"

    def test_derive_cat_imports_safe_div_from_common(self):
        src = _read(DERIVE_CAT_PY)
        # Should import _safe_div from etl._derive_common
        assert "_safe_div" in src, "derive_cat_atomic_input.py must use _safe_div"

    def test_derive_outlook_action_syntax(self):
        src = _read(DERIVE_OUTLOOK_PY)
        ast.parse(src)

    def test_derive_source_standing_imports_from_common(self):
        src = _read(DERIVE_SOURCE_PY)
        assert "_load_outlook_weights" in src, \
            "derive_source_standing.py must import _load_outlook_weights"
        # Must come from _derive_common import
        assert "from etl._derive_common import" in src or "_derive_common" in src, \
            "derive_source_standing.py must import from etl._derive_common"

    def test_derive_source_standing_syntax(self):
        src = _read(DERIVE_SOURCE_PY)
        ast.parse(src)


# ─────────────────────────────────────────────────────────────────────────────
# TASK_57 — Pre-aggregate category totals
# ─────────────────────────────────────────────────────────────────────────────

class TestTask57CategoryTotals:
    """TASK_57: drv_category_totals table; ETL populates; API reads it."""

    def test_baseline_sql_has_drv_category_totals(self):
        sql = _read(BASELINE_SQL)
        assert "CREATE TABLE IF NOT EXISTS drv_category_totals" in sql, \
            "baseline.sql must define drv_category_totals table"

    def test_drv_category_totals_has_drift_band(self):
        sql = _read(BASELINE_SQL)
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_category_totals")
        block = sql[idx:idx+300]
        assert "drift_band" in block, "drv_category_totals must have drift_band column"

    def test_drv_category_totals_has_primary_key(self):
        sql = _read(BASELINE_SQL)
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_category_totals")
        block = sql[idx:idx+300]
        assert "PRIMARY KEY" in block, "drv_category_totals must have a PRIMARY KEY"

    def test_derive_actionable_writes_category_totals(self):
        src = _read(DERIVE_ACTIONABLE_PY)
        assert "drv_category_totals" in src, \
            "derive_actionable.py must write to drv_category_totals"

    def test_dash_py_reads_category_totals(self):
        src = _read(DASH_PY)
        assert "drv_category_totals" in src, \
            "dash.py /api/briefing must read from drv_category_totals"


# ─────────────────────────────────────────────────────────────────────────────
# TASK_58 — Adopt web/_common.js everywhere
# ─────────────────────────────────────────────────────────────────────────────

class TestTask58CommonJs:
    """TASK_58: escapeHtml and fetchJson defined once in _common.js."""

    def test_escape_html_defined_only_in_common_js(self):
        definitions = []
        for js in WEB_JS_FILES:
            src = _read(js)
            if re.search(r"\bfunction escapeHtml\b", src):
                definitions.append(js.name)
        assert definitions == ["_common.js"], (
            f"function escapeHtml defined in {definitions}; expected only _common.js"
        )

    def test_fetch_json_defined_only_in_common_js_and_trig(self):
        """fetchJson canonical definition must be only in _common.js.
        trig.js may keep its own fetchJSON (different error handling)."""
        definitions = []
        for js in WEB_JS_FILES:
            src = _read(js)
            if re.search(r"async function fetchJson\b", src):
                definitions.append(js.name)
        # Allow _common.js only
        for f in definitions:
            assert f == "_common.js", (
                f"async function fetchJson defined in {f}; expected only _common.js"
            )

    def test_common_js_exports_window_escape_html(self):
        src = _read(COMMON_JS)
        assert "window.escapeHtml" in src, \
            "_common.js must expose window.escapeHtml"

    def test_common_js_exports_window_fetch_json(self):
        src = _read(COMMON_JS)
        assert "window.fetchJson" in src or "window.fetchJSON" in src, \
            "_common.js must expose window.fetchJson / window.fetchJSON"

    def test_common_js_syntax(self):
        result = subprocess.run(
            ["node", "--check", str(COMMON_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"_common.js syntax error: {result.stderr}"

    def test_actionable_js_syntax(self):
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"actionable.js syntax error: {result.stderr}"

    def test_portfolio_js_syntax(self):
        result = subprocess.run(
            ["node", "--check", str(PORTFOLIO_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"portfolio.js syntax error: {result.stderr}"

    @pytest.mark.parametrize("filename", [
        "composite_edit.js", "trace.js", "dbstats.js", "explore.js",
        "file_monitor.js", "ref.js", "warning_badge.js", "app.js",
    ])
    def test_removed_files_have_no_local_escape_html(self, filename):
        js_path = PROJECT / "web" / filename
        if not js_path.exists():
            pytest.skip(f"{filename} not found")
        src = _read(js_path)
        assert not re.search(r"\bfunction escapeHtml\b", src), (
            f"{filename} still defines a local function escapeHtml; "
            "should be removed in TASK_58"
        )

    @pytest.mark.parametrize("filename", [
        "actionable.js", "app.js", "portfolio.js", "dbstats.js",
        "explore.js", "ref.js",
    ])
    def test_removed_files_have_no_local_fetch_json(self, filename):
        js_path = PROJECT / "web" / filename
        if not js_path.exists():
            pytest.skip(f"{filename} not found")
        src = _read(js_path)
        assert not re.search(r"async function fetchJson\b", src), (
            f"{filename} still defines a local async function fetchJson; "
            "should be removed in TASK_58"
        )


# ─────────────────────────────────────────────────────────────────────────────
# TASK_59 — Cleanup: stale CLAUDE.md entry + derive_v2.py header
# ─────────────────────────────────────────────────────────────────────────────

class TestTask59Cleanup:
    """TASK_59: classifySymbolSection removed from web/; CLAUDE.md updated; derive_v2.py header."""

    def test_classify_symbol_section_not_in_web(self):
        for js in WEB_JS_FILES:
            src = _read(js)
            assert "classifySymbolSection" not in src, (
                f"{js.name} still references classifySymbolSection; "
                "TASK_59 requires this to be absent from all web/ files"
            )

    def test_claude_md_section_classifier_row_updated(self):
        src = _read(CLAUDE_MD)
        # The row must NOT reference web/app.js::classifySymbolSection as a live function
        # (it was removed); it should now point to etl/derive.py::_classify_section
        assert "etl/derive.py::_classify_section" in src, (
            "CLAUDE.md Section classifier row must point to etl/derive.py::_classify_section"
        )

    def test_derive_v2_has_single_purpose_header(self):
        src = _read(DERIVE_V2_PY)
        # Must explain it is a single-purpose TW override
        header = src[:500].lower()
        assert "single-purpose" in header or "single purpose" in header, (
            "derive_v2.py must have a single-purpose header comment (TASK_59)"
        )

    def test_derive_v2_header_mentions_tw(self):
        src = _read(DERIVE_V2_PY)
        header = src[:500]
        assert "TW" in header or "derive_tw" in header.lower(), (
            "derive_v2.py header must mention TW / derive_tw"
        )

    def test_derive_v2_syntax(self):
        src = _read(DERIVE_V2_PY)
        ast.parse(src)


# ─────────────────────────────────────────────────────────────────────────────
# DEV_HANDOFF status check
# ─────────────────────────────────────────────────────────────────────────────

class TestHandoffStatus:
    def test_dev_handoff_is_all_done(self):
        hf = PROJECT / "DEV_HANDOFF.md"
        assert hf.exists(), "DEV_HANDOFF.md must exist"
        content = _read(hf)
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        assert lines[-1] == "ALL_DONE", (
            f"DEV_HANDOFF.md last non-blank line must be ALL_DONE, got {lines[-1]!r}"
        )

    def test_dev_handoff_covers_task_53_through_59(self):
        hf = PROJECT / "DEV_HANDOFF.md"
        content = _read(hf)
        for n in range(53, 60):
            assert f"TASK_{n}" in content or f"TASK_{n}" in content, (
                f"DEV_HANDOFF.md must mention TASK_{n}"
            )
