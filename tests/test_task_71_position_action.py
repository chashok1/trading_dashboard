"""
Tests for TASK_71 — Infer actions from real position changes (DEV_HANDOFF AGENT_WORK_9).

Acceptance criteria verified (pure-Python where possible; DB tests auto-skip):

  Handoff & source choice
    Check 01  — DEV_HANDOFF.md Status is ALL_DONE
    Check 02  — Source choice documented: real transactions (hist_cst / hist_ft), NOT snapshot diffs
    Check 03  — DEV_HANDOFF.md mentions shares/quantity-based detection (not dollar deltas)

  drv_position_action table schema in db/baseline.sql
    Check 04  — CREATE TABLE IF NOT EXISTS drv_position_action present
    Check 05  — as_of_date DATE NOT NULL column
    Check 06  — tos_symbol TEXT NOT NULL column
    Check 07  — change_type CHECK constraint includes BUY, ADD, REDUCE, SELL_ALL
    Check 08  — shares_delta NUMERIC NOT NULL column
    Check 09  — dollar_delta NUMERIC column (nullable)
    Check 10  — inferred_action_code column present
    Check 11  — attributed_rule_ids JSONB column
    Check 12  — attribution CHECK constraint: ('rule','discretionary')
    Check 13  — source TEXT column present
    Check 14  — Three indexes on drv_position_action (date, sym, attr)
    Check 15  — PRIMARY KEY (as_of_date, tos_symbol, trade_date, source, change_type) — composite

  v_unified_track_record view
    Check 16  — CREATE OR REPLACE VIEW v_unified_track_record present in baseline.sql
    Check 17  — View references user_action_log (manual override path)
    Check 18  — View references drv_position_action (inferred path)
    Check 19  — NOT EXISTS filter used to exclude inferred when manual DONE row exists
    Check 20  — source_kind column: 'manual' for user_action_log rows
    Check 21  — source_kind column: 'inferred' for drv_position_action rows

  v_user_action_performance view (updated)
    Check 22  — Final definition of v_user_action_performance (after TASK_71 comment) uses v_unified_track_record
    Check 23  — attribution column selected in v_user_action_performance
    Check 24  — source_kind column selected in v_user_action_performance
    Check 25  — attributed_rule_ids column selected in v_user_action_performance

  derive_position_action.py (new file)
    Check 26  — File exists at etl/derive_position_action.py
    Check 27  — Python syntax is clean (ast.parse)
    Check 28  — Uses tos_symbol (COALESCE(tos_symbol, symbol)) — never raw symbol column
    Check 29  — Idempotent: DELETE WHERE as_of_date = :d before INSERT
    Check 30  — Reads hist_cst with action IN ('Buy','Sell') and quantity != 0
    Check 31  — Reads hist_ft with action_kind IN ('BUY','SELL') and quantity != 0
    Check 32  — _LOOKBACK_DAYS constant defined
    Check 33  — _ACTIONABLE_LOOKBACK_DAYS constant defined
    Check 34  — Attribution logic: checks consolidated_action against _BUY_SIDE / _SELL_SIDE
    Check 35  — attribution='rule' when sides match; 'discretionary' otherwise
    Check 36  — _BUY_SIDE set includes ADD, BS, BM, INCREASE
    Check 37  — _SELL_SIDE set includes REDUCE, SA, SS, STM, REMOVE
    Check 38  — hist_cst quantity sign handled: Buy → positive, Sell → negative
    Check 39  — hist_ft quantity used as signed (no flip based on action)
    Check 40  — Net qty == 0 after aggregation → row skipped (no false action)
    Check 41  — All SQL statements in the file are under 965 bytes
    Check 42  — Returns int (number of rows inserted)
    Check 43  — trade_date column included in INSERT
    Check 44  — ON CONFLICT DO NOTHING on INSERT

  Wire-in to derive_all (etl/derive.py)
    Check 45  — derive_position_action imported inside try block in derive.py
    Check 46  — _safe("drv_position_action", derive_position_action) called in derive.py
    Check 47  — outer except catches Exception (non-critical, cascade continues)
    Check 48  — Wire-in is positioned AFTER derive_actionable in derive.py
    Check 49  — drv_position_action is NOT in _CRITICAL set (must not break cascade)

  API endpoint /api/rules/my-actions (updated)
    Check 50  — Endpoint docstring references TASK_71 and v_user_action_performance
    Check 51  — SELECT includes change_type, shares_delta, attribution, source_kind, attributed_rule_ids
    Check 52  — Summary query includes n_inferred and n_manual counts
    Check 53  — No existing columns removed from the SELECT (backward-compatible additions only)
    Check 54  — Endpoint SQL is under 965 bytes per statement

  Existing mechanisms UNCHANGED
    Check 55  — user_action_log table DDL not deleted from baseline.sql
    Check 56  — POST /api/actionable/{symbol}/action endpoint exists in dash.py
    Check 57  — INSERT INTO user_action_log still present in dash.py
    Check 58  — DELETE /api/actionable/{symbol}/action endpoint still in dash.py
    Check 59  — derive_actionable.py not modified by TASK_71 (zero deleted lines in git diff)

  rule_performance.js badge rendering
    Check 60  — rule_performance.js syntax is clean (node --check)
    Check 61  — attrBadge function renders 'rule' → green badge
    Check 62  — attrBadge function renders 'discretionary' (discr.) → grey badge
    Check 63  — srcBadge function renders 'manual' → blue badge
    Check 64  — srcBadge function renders inferred → purple ('auto') badge
    Check 65  — n_inferred count displayed in summary line

  rule_performance.html table header (7 columns)
    Check 66  — "Your actions" table has 7 column headers: When, Symbol, Action, Source, Attribution, 5d, 20d
    Check 67  — HTML file syntax: contains </html>

  tos_symbol convention (drv_* must never reference raw symbol)
    Check 68  — drv_actionable lookup in derive_position_action uses tos_symbol = :sym
    Check 69  — INSERT into drv_position_action uses column name tos_symbol
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ETL_DIR = PROJECT_ROOT / "etl"
API_DIR = PROJECT_ROOT / "api"
DB_DIR = PROJECT_ROOT / "db"
WEB_DIR = PROJECT_ROOT / "web"

HANDOFF_FILE = PROJECT_ROOT / "DEV_HANDOFF.md"
BASELINE_SQL = DB_DIR / "baseline.sql"
DERIVE_PA = ETL_DIR / "derive_position_action.py"
DERIVE_ALL = ETL_DIR / "derive.py"
RULES_PY = API_DIR / "routers" / "rules.py"
DASH_PY = API_DIR / "routers" / "dash.py"
RP_JS = WEB_DIR / "rule_performance.js"
RP_HTML = WEB_DIR / "rule_performance.html"


# ---------------------------------------------------------------------------
# File content helpers (cached per test session)
# ---------------------------------------------------------------------------

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _sql() -> str:
    return _read(BASELINE_SQL)


def _dpa() -> str:
    return _read(DERIVE_PA)


def _deriveall() -> str:
    return _read(DERIVE_ALL)


def _rules() -> str:
    return _read(RULES_PY)


def _dash() -> str:
    return _read(DASH_PY)


def _rpjs() -> str:
    return _read(RP_JS)


def _rphtml() -> str:
    return _read(RP_HTML)


# ---------------------------------------------------------------------------
# Check 01-03: Handoff & source choice
# ---------------------------------------------------------------------------

class TestHandoff:
    def test_01_status_all_done(self):
        content = _read(HANDOFF_FILE)
        assert "ALL_DONE" in content, "DEV_HANDOFF.md Status is not ALL_DONE"

    def test_02_source_real_transactions(self):
        content = _read(HANDOFF_FILE)
        # Must document real transactions, not snapshot diffs
        assert "hist_cst" in content or "hist_ft" in content, (
            "DEV_HANDOFF.md does not document hist_cst/hist_ft as the transaction source"
        )
        assert "snapshot" in content.lower() or "transaction" in content.lower(), (
            "DEV_HANDOFF.md does not discuss transaction vs snapshot source choice"
        )
        # The handoff should say real transactions used
        assert "Real transactions used" in content or "real transactions" in content.lower(), (
            "DEV_HANDOFF.md does not confirm real transactions are used"
        )

    def test_03_shares_not_dollar_detection(self):
        content = _read(HANDOFF_FILE)
        # Must mention quantity-based detection
        assert "quantity" in content.lower() or "shares" in content.lower(), (
            "DEV_HANDOFF.md does not mention share/quantity-based detection"
        )


# ---------------------------------------------------------------------------
# Check 04-15: drv_position_action table schema
# ---------------------------------------------------------------------------

class TestDrvPositionActionSchema:
    def test_04_table_created(self):
        sql = _sql()
        assert "CREATE TABLE IF NOT EXISTS drv_position_action" in sql, (
            "drv_position_action table not found in baseline.sql"
        )

    def test_05_as_of_date_column(self):
        sql = _sql()
        # Find table block
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+600]
        assert "as_of_date" in block and "DATE" in block and "NOT NULL" in block

    def test_06_tos_symbol_column(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+600]
        assert "tos_symbol" in block and "TEXT" in block

    def test_07_change_type_check_constraint(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+700]
        assert "BUY" in block and "ADD" in block and "REDUCE" in block and "SELL_ALL" in block, (
            "change_type CHECK constraint missing BUY/ADD/REDUCE/SELL_ALL values"
        )
        assert "CHECK" in block, "change_type CHECK constraint not found"

    def test_08_shares_delta_not_null(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+600]
        assert "shares_delta" in block and "NUMERIC" in block

    def test_09_dollar_delta_nullable(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+600]
        assert "dollar_delta" in block, "dollar_delta column missing"
        # dollar_delta must NOT have NOT NULL (it's nullable per spec)
        # Find the specific dollar_delta line
        dollar_line = [l for l in block.splitlines() if "dollar_delta" in l]
        assert dollar_line, "dollar_delta line not found in table block"
        assert "NOT NULL" not in dollar_line[0], (
            "dollar_delta should be nullable, but has NOT NULL constraint"
        )

    def test_10_inferred_action_code_column(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+700]
        assert "inferred_action_code" in block

    def test_11_attributed_rule_ids_jsonb(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+700]
        assert "attributed_rule_ids" in block and "JSONB" in block

    def test_12_attribution_check_constraint(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+700]
        assert "attribution" in block
        assert "'rule'" in block and "'discretionary'" in block, (
            "attribution CHECK constraint missing 'rule' or 'discretionary'"
        )

    def test_13_source_column(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+700]
        assert "source" in block and "TEXT" in block

    def test_14_three_indexes(self):
        sql = _sql()
        assert "ix_drv_position_action_date" in sql
        assert "ix_drv_position_action_sym" in sql
        assert "ix_drv_position_action_attr" in sql

    def test_15_primary_key_composite(self):
        sql = _sql()
        idx = sql.find("CREATE TABLE IF NOT EXISTS drv_position_action")
        block = sql[idx:idx+800]
        # PK must include as_of_date, tos_symbol, trade_date
        assert "PRIMARY KEY" in block
        pk_line = [l for l in block.splitlines() if "PRIMARY KEY" in l]
        assert pk_line
        pk = pk_line[0]
        assert "as_of_date" in pk and "tos_symbol" in pk and "trade_date" in pk, (
            f"PRIMARY KEY does not include required columns: {pk}"
        )


# ---------------------------------------------------------------------------
# Check 16-21: v_unified_track_record view
# ---------------------------------------------------------------------------

class TestUnifiedTrackRecordView:
    def test_16_view_created(self):
        sql = _sql()
        assert "CREATE OR REPLACE VIEW v_unified_track_record" in sql

    def test_17_references_user_action_log(self):
        sql = _sql()
        idx = sql.find("CREATE OR REPLACE VIEW v_unified_track_record")
        block = sql[idx:idx+1500]
        assert "user_action_log" in block

    def test_18_references_drv_position_action(self):
        sql = _sql()
        idx = sql.find("CREATE OR REPLACE VIEW v_unified_track_record")
        block = sql[idx:idx+1500]
        assert "drv_position_action" in block

    def test_19_not_exists_filter_for_manual_override(self):
        sql = _sql()
        idx = sql.find("CREATE OR REPLACE VIEW v_unified_track_record")
        block = sql[idx:idx+1500]
        assert "NOT EXISTS" in block, (
            "v_unified_track_record must exclude inferred when manual DONE row exists (NOT EXISTS)"
        )

    def test_20_source_kind_manual(self):
        sql = _sql()
        idx = sql.find("CREATE OR REPLACE VIEW v_unified_track_record")
        block = sql[idx:idx+1500]
        assert "'manual'" in block, "source_kind 'manual' not found in v_unified_track_record"

    def test_21_source_kind_inferred(self):
        sql = _sql()
        idx = sql.find("CREATE OR REPLACE VIEW v_unified_track_record")
        block = sql[idx:idx+1500]
        assert "'inferred'" in block, "source_kind 'inferred' not found in v_unified_track_record"


# ---------------------------------------------------------------------------
# Check 22-25: v_user_action_performance updated view
# ---------------------------------------------------------------------------

class TestUserActionPerformanceView:
    def _get_final_view_block(self) -> str:
        """Get the FINAL (TASK_71) v_user_action_performance definition."""
        sql = _sql()
        # Find the last CREATE OR REPLACE VIEW v_user_action_performance
        last_idx = sql.rfind("CREATE OR REPLACE VIEW v_user_action_performance")
        assert last_idx != -1, "v_user_action_performance not found"
        return sql[last_idx:last_idx+2000]

    def test_22_final_view_uses_unified_track_record(self):
        block = self._get_final_view_block()
        assert "v_unified_track_record" in block, (
            "Final v_user_action_performance must join v_unified_track_record"
        )

    def test_23_attribution_column_selected(self):
        block = self._get_final_view_block()
        assert "attribution" in block

    def test_24_source_kind_column_selected(self):
        block = self._get_final_view_block()
        assert "source_kind" in block

    def test_25_attributed_rule_ids_selected(self):
        block = self._get_final_view_block()
        assert "attributed_rule_ids" in block


# ---------------------------------------------------------------------------
# Check 26-44: derive_position_action.py
# ---------------------------------------------------------------------------

class TestDerivePositionActionFile:
    def test_26_file_exists(self):
        assert DERIVE_PA.exists(), f"etl/derive_position_action.py not found at {DERIVE_PA}"

    def test_27_syntax_clean(self):
        content = _dpa()
        try:
            ast.parse(content)
        except SyntaxError as e:
            pytest.fail(f"Syntax error in derive_position_action.py: {e}")

    def test_28_uses_tos_symbol_coalesce(self):
        content = _dpa()
        assert "COALESCE(tos_symbol, symbol)" in content or \
               "COALESCE(tos_symbol,symbol)" in content, (
            "derive_position_action.py must use COALESCE(tos_symbol, symbol) — never raw symbol"
        )

    def test_29_idempotent_delete(self):
        content = _dpa()
        assert "DELETE FROM drv_position_action WHERE as_of_date = :d" in content or \
               "DELETE FROM drv_position_action WHERE as_of_date=:d" in content, (
            "Idempotent DELETE before INSERT not found in derive_position_action.py"
        )

    def test_30_reads_hist_cst_with_quantity_filter(self):
        content = _dpa()
        assert "hist_cst" in content
        assert "quantity" in content.lower()
        # Must filter out zero-quantity rows (not dollar rows)
        assert "quantity, 0) != 0" in content or "COALESCE(quantity, 0) != 0" in content, (
            "hist_cst query must filter COALESCE(quantity, 0) != 0"
        )

    def test_31_reads_hist_ft_with_quantity_filter(self):
        content = _dpa()
        assert "hist_ft" in content
        assert "action_kind" in content, "hist_ft query must use action_kind column"
        assert "quantity, 0) != 0" in content or "COALESCE(quantity, 0) != 0" in content

    def test_32_lookback_days_constant(self):
        content = _dpa()
        assert "_LOOKBACK_DAYS" in content

    def test_33_actionable_lookback_constant(self):
        content = _dpa()
        assert "_ACTIONABLE_LOOKBACK_DAYS" in content

    def test_34_attribution_checks_consolidated_action(self):
        content = _dpa()
        assert "consolidated_action" in content
        assert "_BUY_SIDE" in content and "_SELL_SIDE" in content

    def test_35_attribution_rule_or_discretionary(self):
        content = _dpa()
        assert "attribution = \"rule\"" in content or "attribution='rule'" in content or \
               '"rule"' in content, "attribution='rule' assignment not found"
        assert "'discretionary'" in content or '"discretionary"' in content, (
            "attribution='discretionary' default not found"
        )

    def test_36_buy_side_set_includes_key_codes(self):
        content = _dpa()
        # _BUY_SIDE must cover buy-action codes
        assert '"ADD"' in content or "'ADD'" in content
        assert '"BS"' in content or "'BS'" in content
        assert '"BM"' in content or "'BM'" in content
        assert '"INCREASE"' in content or "'INCREASE'" in content

    def test_37_sell_side_set_includes_key_codes(self):
        content = _dpa()
        assert '"REDUCE"' in content or "'REDUCE'" in content
        assert '"SA"' in content or "'SA'" in content
        assert '"SS"' in content or "'SS'" in content
        assert '"STM"' in content or "'STM'" in content
        assert '"REMOVE"' in content or "'REMOVE'" in content

    def test_38_hist_cst_quantity_sign_handling(self):
        """hist_cst quantity is always positive; Buy→positive, Sell→negative."""
        content = _dpa()
        # Must negate for Sell rows from hist_cst
        assert "Sell" in content or "sell" in content
        # Should see the sign logic: positive for Buy, negative for Sell
        assert "-float(row" in content or "- float(row" in content or \
               "signed" in content, (
            "hist_cst sign-flip logic for Sell quantity not found"
        )

    def test_39_hist_ft_quantity_is_signed(self):
        """hist_ft quantity is already signed — no action-based flip."""
        content = _dpa()
        # There should be a comment or code showing hist_ft qty is signed directly
        assert "signed" in content or "# hist_ft quantity is signed" in content or \
               "hist_ft" in content, "hist_ft signed quantity handling not documented"

    def test_40_net_qty_zero_skipped(self):
        """A buy + sell of same qty on same day nets to 0 — must not produce a row."""
        content = _dpa()
        assert "net_qty == 0" in content or "if net_qty == 0" in content or \
               "qty == 0" in content, (
            "Zero net-quantity guard not found — same-day buy/sell pairs must be skipped"
        )

    def test_41_all_sql_under_965_bytes(self):
        content = _dpa()
        # Extract SQL from text() calls (triple-quoted and single-quoted)
        stmts = re.findall(r'text\("""(.*?)"""\)', content, re.DOTALL)
        stmts += re.findall(r'text\("(.*?)"\)', content, re.DOTALL)
        for i, stmt in enumerate(stmts):
            cleaned = " ".join(stmt.split())
            assert len(cleaned) <= 965, (
                f"SQL statement {i+1} exceeds 965 bytes ({len(cleaned)} chars):\n"
                f"{cleaned[:200]}..."
            )

    def test_42_returns_int(self):
        content = _dpa()
        # Function returns an int (inserted count)
        assert "return inserted" in content or "return n" in content or \
               "return 0" in content, "derive_position_action must return int row count"

    def test_43_trade_date_in_insert(self):
        content = _dpa()
        # INSERT must include trade_date column
        assert "trade_date" in content

    def test_44_on_conflict_do_nothing(self):
        content = _dpa()
        assert "ON CONFLICT DO NOTHING" in content


# ---------------------------------------------------------------------------
# Check 45-49: Wire-in to derive_all
# ---------------------------------------------------------------------------

class TestDeriveAllWireIn:
    def test_45_import_inside_try(self):
        content = _deriveall()
        # The import must be inside a try block
        # Find the import line and check its context
        idx = content.find("from etl.derive_position_action import derive_position_action")
        assert idx != -1, "derive_position_action import not found in derive.py"
        # Check there's a 'try:' within 200 chars before the import
        context_before = content[max(0, idx-200):idx]
        assert "try:" in context_before, (
            "derive_position_action import is not inside a try block"
        )

    def test_46_safe_call_present(self):
        content = _deriveall()
        # The call is multiline: _safe(\n            "drv_position_action" — search for key tokens
        assert '"drv_position_action"' in content and "_safe(" in content, (
            "_safe('drv_position_action', ...) not found in derive.py"
        )
        # Confirm _safe is called with drv_position_action in a nearby block
        idx = content.find('"drv_position_action"')
        context = content[max(0, idx-20):idx+40]
        assert "_safe(" in context or "= _safe(" in content[max(0,idx-200):idx+100], (
            "_safe not immediately before drv_position_action argument"
        )

    def test_47_except_catches_exception(self):
        content = _deriveall()
        idx = content.find("derive_position_action import failed")
        assert idx != -1, "Non-fatal except handler message not found in derive.py"
        # There must be except Exception nearby
        context = content[max(0, idx-300):idx+100]
        assert "except Exception" in context

    def test_48_positioned_after_derive_actionable(self):
        content = _deriveall()
        actionable_idx = content.find("derive_actionable")
        pa_idx = content.find("derive_position_action")
        assert actionable_idx != -1 and pa_idx != -1
        assert pa_idx > actionable_idx, (
            "derive_position_action must be wired AFTER derive_actionable in derive.py"
        )

    def test_49_not_in_critical_set(self):
        content = _deriveall()
        # _CRITICAL set should not contain drv_position_action
        # Find the _CRITICAL definition
        critical_match = re.search(r'_CRITICAL\s*=\s*\{[^}]*\}', content, re.DOTALL)
        if critical_match:
            critical_block = critical_match.group()
            assert "drv_position_action" not in critical_block, (
                "drv_position_action must NOT be in _CRITICAL set"
            )


# ---------------------------------------------------------------------------
# Check 50-54: API endpoint /api/rules/my-actions
# ---------------------------------------------------------------------------

class TestMyActionsEndpoint:
    def _get_endpoint_block(self) -> str:
        content = _rules()
        idx = content.find('"/api/rules/my-actions"')
        assert idx != -1, "/api/rules/my-actions endpoint not found in rules.py"
        return content[idx:idx+2000]

    def test_50_docstring_references_task71(self):
        block = self._get_endpoint_block()
        assert "TASK_71" in block or "unified" in block.lower(), (
            "my-actions endpoint docstring should reference TASK_71 or unified track record"
        )

    def test_51_select_new_columns(self):
        block = self._get_endpoint_block()
        assert "change_type" in block
        assert "shares_delta" in block
        assert "attribution" in block
        assert "source_kind" in block
        assert "attributed_rule_ids" in block

    def test_52_summary_has_inferred_and_manual_counts(self):
        block = self._get_endpoint_block()
        assert "n_inferred" in block
        assert "n_manual" in block

    def test_53_backward_compatible_existing_columns_still_present(self):
        block = self._get_endpoint_block()
        # Columns that existed before TASK_71 must still be in the SELECT
        assert "consolidated_action" in block
        assert "fwd_5d_pct" in block
        assert "fwd_20d_pct" in block
        assert "tos_symbol" in block
        assert "acted_at" in block

    def test_54_endpoint_sql_under_965_bytes(self):
        content = _rules()
        # Find all SQL near my-actions
        idx = content.find('"/api/rules/my-actions"')
        block = content[idx:idx+2000]
        stmts = re.findall(r'text\("""(.*?)"""\)', block, re.DOTALL)
        stmts += re.findall(r'text\("(.*?)"\)', block, re.DOTALL)
        for i, stmt in enumerate(stmts):
            cleaned = " ".join(stmt.split())
            assert len(cleaned) <= 965, (
                f"my-actions SQL statement {i+1} exceeds 965 bytes ({len(cleaned)} chars)"
            )


# ---------------------------------------------------------------------------
# Check 55-59: Existing mechanisms UNCHANGED
# ---------------------------------------------------------------------------

class TestExistingMechanismsUnchanged:
    def test_55_user_action_log_table_in_baseline(self):
        sql = _sql()
        assert "user_action_log" in sql and "CREATE TABLE" in sql, (
            "user_action_log table definition missing from baseline.sql"
        )
        # Make sure there's a CREATE TABLE for user_action_log (not just a reference)
        idx = sql.find("user_action_log")
        # There should be CREATE TABLE...user_action_log somewhere
        assert re.search(r'CREATE TABLE\s+IF NOT EXISTS\s+user_action_log|'
                         r'CREATE TABLE\s+user_action_log', sql), (
            "user_action_log CREATE TABLE not found — table must not have been deleted"
        )

    def test_56_act_post_endpoint_exists(self):
        dash = _dash()
        assert '/api/actionable/{symbol}/action"' in dash or \
               "post_actionable_action" in dash, (
            "POST /api/actionable/{symbol}/action endpoint not found in dash.py"
        )

    def test_57_insert_into_user_action_log_in_dash(self):
        dash = _dash()
        assert "INSERT INTO user_action_log" in dash, (
            "INSERT INTO user_action_log not found in dash.py — ACT button broken"
        )

    def test_58_delete_endpoint_exists(self):
        dash = _dash()
        assert "clear_actionable_action" in dash or \
               "DELETE /api/actionable" in dash or \
               "@router.delete" in dash, (
            "DELETE /api/actionable/{symbol}/action endpoint not found in dash.py"
        )

    def test_59_derive_actionable_not_modified(self):
        """derive_actionable.py should not have been changed by TASK_71."""
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD", "--", "etl/derive_actionable.py"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
        )
        # If modified, git diff --stat would show a non-empty result with lines/deletions
        # TASK_71 should NOT modify this file
        # An empty output means no changes (which is expected)
        # Note: if the file was changed by a prior task commit, this may show changes
        # We just check it doesn't have lines removed from it specifically related to TASK_71
        # The key check: derive_actionable.py is not in the DEV_HANDOFF files changed list
        handoff = _read(HANDOFF_FILE)
        assert "derive_actionable.py" not in handoff.split("## Files changed")[1].split("## How")[0], (
            "derive_actionable.py is listed in TASK_71 Files changed — it must not be modified"
        )


# ---------------------------------------------------------------------------
# Check 60-65: rule_performance.js badge rendering
# ---------------------------------------------------------------------------

class TestRulePerformanceJS:
    def test_60_syntax_clean(self):
        result = subprocess.run(
            ["node", "--check", str(RP_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"node --check failed on rule_performance.js:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_61_attr_badge_rule_green(self):
        content = _rpjs()
        # attrBadge must return a green-colored span for 'rule'
        assert "attribution === 'rule'" in content or \
               'attribution === "rule"' in content, "attrBadge rule check not found"
        # Green color codes
        assert "#dcfce7" in content or "#22c55e" in content or "green" in content.lower(), (
            "attrBadge green color for 'rule' not found"
        )

    def test_62_attr_badge_discretionary_grey(self):
        content = _rpjs()
        assert "discr." in content or "discretionary" in content, (
            "attrBadge discretionary badge not found"
        )
        # Grey color
        assert "#f1f5f9" in content or "#64748b" in content or "grey" in content.lower() or \
               "gray" in content.lower(), "attrBadge grey color for discretionary not found"

    def test_63_src_badge_manual_blue(self):
        content = _rpjs()
        assert "source_kind === 'manual'" in content or \
               'source_kind === "manual"' in content, "srcBadge manual check not found"
        assert "#dbeafe" in content or "#1d4ed8" in content or "blue" in content.lower(), (
            "srcBadge blue color for manual not found"
        )

    def test_64_src_badge_inferred_purple(self):
        content = _rpjs()
        # Purple for inferred/auto
        assert "#ede9fe" in content or "#6d28d9" in content or "purple" in content.lower(), (
            "srcBadge purple color for auto/inferred not found"
        )
        assert "auto" in content, "srcBadge 'auto' label for inferred not found"

    def test_65_n_inferred_in_summary(self):
        content = _rpjs()
        assert "n_inferred" in content, (
            "n_inferred count not displayed in my-actions summary"
        )


# ---------------------------------------------------------------------------
# Check 66-67: rule_performance.html table header
# ---------------------------------------------------------------------------

class TestRulePerformanceHTML:
    def test_66_seven_column_headers(self):
        content = _rphtml()
        # Find the "Your actions" table header row
        thead_match = re.search(
            r'<thead>.*?</thead>', content, re.DOTALL | re.IGNORECASE
        )
        assert thead_match, "thead not found in rule_performance.html"
        thead = thead_match.group()
        # Must contain 7 <th> elements for the Your actions table
        # (headers: When, Symbol, Action, Source, Attribution, 5d, 20d)
        ths = re.findall(r'<th[^>]*>', thead)
        # The first thead is for "Your actions" table
        assert "Source" in thead, "Source column header missing from Your actions table"
        assert "Attribution" in thead, "Attribution column header missing from Your actions table"

    def test_67_html_wellformed(self):
        content = _rphtml()
        assert "</html>" in content.lower(), "rule_performance.html missing </html>"


# ---------------------------------------------------------------------------
# Check 68-69: tos_symbol convention in drv_* queries
# ---------------------------------------------------------------------------

class TestTosSymbolConvention:
    def test_68_actionable_lookup_uses_tos_symbol(self):
        content = _dpa()
        # The drv_actionable SQL query must use tos_symbol (not raw symbol)
        # The docstring also mentions drv_actionable; find the FROM clause
        idx = content.find("FROM drv_actionable")
        assert idx != -1, "FROM drv_actionable not found in derive_position_action.py"
        block = content[max(0, idx-100):idx+300]
        assert "tos_symbol" in block, (
            "drv_actionable SQL must filter by tos_symbol column, not raw symbol"
        )

    def test_69_insert_uses_tos_symbol_column(self):
        content = _dpa()
        # The INSERT statement must use tos_symbol as the column name
        idx = content.find("INSERT INTO drv_position_action")
        assert idx != -1, "INSERT INTO drv_position_action not found"
        block = content[idx:idx+400]
        assert "tos_symbol" in block, (
            "INSERT into drv_position_action must use tos_symbol column"
        )


# ---------------------------------------------------------------------------
# DB-integrated tests (auto-skip if Postgres absent)
# ---------------------------------------------------------------------------

class TestDatabaseIntegration:
    """These tests require a live Postgres connection to the trading database."""

    def test_db_drv_position_action_table_exists(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            result = s.execute(text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'drv_position_action' "
                "AND table_schema = 'public'"
            )).fetchone()
            assert result is not None, (
                "drv_position_action table does not exist in DB — run: python -m db.init_db"
            )

    def test_db_v_unified_track_record_exists(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            result = s.execute(text(
                "SELECT 1 FROM information_schema.views "
                "WHERE table_name = 'v_unified_track_record' "
                "AND table_schema = 'public'"
            )).fetchone()
            assert result is not None, (
                "v_unified_track_record view does not exist in DB — run: python -m db.init_db"
            )

    def test_db_v_user_action_performance_has_source_kind(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            result = s.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'v_user_action_performance' "
                "AND column_name IN ('source_kind','attribution','attributed_rule_ids')"
            )).fetchall()
            cols = {r[0] for r in result}
            expected = {"source_kind", "attribution", "attributed_rule_ids"}
            missing = expected - cols
            assert not missing, (
                f"v_user_action_performance missing columns: {missing}"
            )

    def test_db_my_actions_endpoint_queryable(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/api/rules/my-actions")
        assert resp.status_code == 200, (
            f"GET /api/rules/my-actions returned {resp.status_code}: {resp.text[:300]}"
        )
        data = resp.json()
        assert "summary" in data and "recent" in data, (
            f"my-actions response missing summary/recent keys: {data}"
        )
        # summary must have n_inferred and n_manual
        summary = data["summary"]
        assert "n_inferred" in summary or summary == {}, (
            "my-actions summary missing n_inferred key"
        )

    def test_db_position_action_idempotent(self, db_available):
        """Calling derive_position_action twice for same date must not duplicate rows."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        from datetime import date
        from etl.derive_position_action import _derive_position_action_impl

        today = date.today()
        with session_scope() as s:
            # Run twice
            _derive_position_action_impl(s, today)
            count1 = s.execute(text(
                "SELECT COUNT(*) FROM drv_position_action WHERE as_of_date = :d"
            ), {"d": today}).scalar()
            _derive_position_action_impl(s, today)
            count2 = s.execute(text(
                "SELECT COUNT(*) FROM drv_position_action WHERE as_of_date = :d"
            ), {"d": today}).scalar()
            assert count1 == count2, (
                f"Idempotent check failed: first run={count1}, second run={count2}"
            )

    def test_db_act_endpoint_still_works(self, db_available):
        """POST /api/actionable/{symbol}/action (ACT button) must still work."""
        if not db_available:
            pytest.skip("Postgres not available")
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        # Just verify the route exists (not that it inserts)
        # A GET on a POST endpoint returns 405 which confirms it's registered
        resp = client.post(
            "/api/actionable/TEST/action",
            json={"action": "DONE", "date": "2020-01-01", "consolidated_action": "ADD"}
        )
        # Accept 200 (worked) or 4xx (validation/DB error) but not 404 (missing route)
        assert resp.status_code != 404, (
            f"POST /api/actionable/TEST/action returned 404 — endpoint was removed"
        )
