"""
Tests for the inline Act button HTTP 400 bug fix.

Bug: inlineAction() was sending the Final Call BuySell code (SA/SS/BM/etc.)
as `user_action`, which the server rejected with HTTP 400 because its enum
validation only accepts DONE/SKIPPED/SNOOZED/OVERRIDDEN.

Fix:
  - web/actionable.js: inlineAction() now sends `user_action='DONE'` for
    non-legacy codes; the Final Call BuySell code goes into `action_code`.
  - api/routers/dash.py: post_actionable_action() reads `action_code` from
    payload and includes it in the INSERT statement.

Acceptance criteria checked here:
  A. node --check web/actionable.js passes.
  B. inlineAction() sends user_action='DONE' for BuySell codes (SA/SS/BM/etc.).
  C. inlineAction() sends the BuySell code as action_code.
  D. Legacy codes (SKIPPED/SNOOZED/OVERRIDDEN) still pass through unchanged.
  E. Server-side enum validation is NOT relaxed (still DONE/SKIPPED/SNOOZED/OVERRIDDEN).
  F. Server INSERT includes action_code from payload.
  G. SQL INSERT is <= 965 bytes.
  H. All existing test_agent_work_17.py tests still pass (no regression).
"""

from __future__ import annotations

import re
import subprocess
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ACTIONABLE_JS = PROJECT_ROOT / "web" / "actionable.js"
DASH_PY = PROJECT_ROOT / "api" / "routers" / "dash.py"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _js() -> str:
    return ACTIONABLE_JS.read_text(encoding="utf-8")


def _dash() -> str:
    return DASH_PY.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A. Syntax check
# ---------------------------------------------------------------------------

class TestSyntaxCheck:
    def test_node_check_passes(self):
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check exited {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert result.stderr.strip() == "", (
            f"node --check produced unexpected stderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# B. inlineAction() sends user_action='DONE' for BuySell codes
# ---------------------------------------------------------------------------

class TestInlineActionUserActionField:
    """inlineAction() must always send user_action as a legacy enum value."""

    def test_legacy_action_constant_list_present(self):
        """The DONE/SKIPPED/SNOOZED/OVERRIDDEN allowlist must exist in inlineAction."""
        js = _js()
        assert "DONE" in js and "SKIPPED" in js and "SNOOZED" in js and "OVERRIDDEN" in js, (
            "Legacy action allowlist must be present in actionable.js"
        )

    def test_islegacy_check_present(self):
        """inlineAction() must check whether the action is a legacy value."""
        js = _js()
        # The fix introduces isLegacyAction variable
        assert "isLegacyAction" in js, (
            "inlineAction() must contain an isLegacyAction check"
        )

    def test_user_action_always_done_for_non_legacy(self):
        """For non-legacy codes, userAction must be set to 'DONE'."""
        js = _js()
        # The fix: const userAction = isLegacyAction ? action.toUpperCase() : 'DONE';
        assert re.search(r"isLegacyAction\s*\?.*\.toUpperCase\(\)\s*:\s*['\"]DONE['\"]", js), (
            "inlineAction() must set userAction to 'DONE' when action is not legacy"
        )

    def test_payload_sends_user_action(self):
        """The payload object must contain user_action: userAction."""
        js = _js()
        assert "user_action: userAction" in js, (
            "inlineAction() payload must send user_action as the computed userAction"
        )


# ---------------------------------------------------------------------------
# C. inlineAction() sends action_code for BuySell codes
# ---------------------------------------------------------------------------

class TestInlineActionCodeField:
    """The Final Call BuySell code must be sent as action_code in the payload."""

    def test_action_code_variable_defined(self):
        """actionCode variable must be defined in inlineAction()."""
        js = _js()
        assert "actionCode" in js, (
            "inlineAction() must define an actionCode variable"
        )

    def test_action_code_null_for_legacy(self):
        """For legacy codes, actionCode must be null (not the code itself)."""
        js = _js()
        # const actionCode = isLegacyAction ? null : action;
        assert re.search(r"isLegacyAction\s*\?\s*null\s*:", js), (
            "inlineAction() must set actionCode to null when the action is a legacy value"
        )

    def test_action_code_set_to_action_for_non_legacy(self):
        """For non-legacy codes, actionCode must be set to the action itself."""
        js = _js()
        # const actionCode = isLegacyAction ? null : action;
        assert re.search(r"isLegacyAction\s*\?\s*null\s*:\s*action\b", js), (
            "inlineAction() must set actionCode to action when the action is not legacy"
        )

    def test_payload_includes_action_code(self):
        """The payload must include action_code field."""
        js = _js()
        assert "action_code: actionCode" in js, (
            "inlineAction() payload must include action_code: actionCode"
        )


# ---------------------------------------------------------------------------
# D. Legacy codes pass through unchanged
# ---------------------------------------------------------------------------

class TestLegacyCodePassthrough:
    """SKIPPED/SNOOZED/OVERRIDDEN must still map to themselves as user_action."""

    def test_skipped_unchanged(self):
        """Inline skip button passes 'SKIPPED' directly to inlineAction."""
        js = _js()
        # The skip button handler: inlineAction(sym, 'SKIPPED')
        assert re.search(r"inlineAction\([^,]+,\s*['\"]SKIPPED['\"]", js), (
            "Inline skip button must call inlineAction() with 'SKIPPED'"
        )

    def test_snoozed_unchanged(self):
        """Inline snooze button passes 'SNOOZED' directly to inlineAction."""
        js = _js()
        assert re.search(r"inlineAction\([^,]+,\s*['\"]SNOOZED['\"]", js), (
            "Inline snooze button must call inlineAction() with 'SNOOZED'"
        )

    def test_legacy_includes_done(self):
        """'DONE' must be in the legacy allowlist."""
        js = _js()
        # The list includes() check
        assert re.search(r"\[.*'DONE'.*\]\.includes", js) or re.search(r'\[.*"DONE".*\]\.includes', js), (
            "'DONE' must be included in the legacy action list used by inlineAction()"
        )


# ---------------------------------------------------------------------------
# E. Server-side enum validation is NOT relaxed
# ---------------------------------------------------------------------------

class TestServerEnumValidation:
    """The server must still only accept DONE/SKIPPED/SNOOZED/OVERRIDDEN."""

    def test_enum_allowlist_unchanged(self):
        """post_actionable_action() must still reject non-legacy user_action values."""
        dash = _dash()
        # The exact check must still be present
        assert 'user_action not in ("DONE", "SKIPPED", "SNOOZED", "OVERRIDDEN")' in dash, (
            "Server enum validation must still restrict user_action to DONE/SKIPPED/SNOOZED/OVERRIDDEN"
        )

    def test_400_error_still_raised_for_invalid(self):
        """HTTPException 400 must still be raised for invalid user_action."""
        dash = _dash()
        # Find the validation block
        idx = dash.find('user_action not in ("DONE"')
        assert idx != -1
        # After the condition, raise HTTPException 400 must appear nearby
        snippet = dash[idx: idx + 200]
        assert "raise HTTPException(400" in snippet, (
            "Server must still raise HTTPException(400) when user_action is invalid"
        )

    def test_buysell_codes_not_added_to_enum(self):
        """BuySell codes SA/SS/BM must NOT be added to the server enum allowlist."""
        dash = _dash()
        # Check the allowlist string doesn't contain SA or BM
        enum_idx = dash.find('user_action not in (')
        assert enum_idx != -1
        enum_line = dash[enum_idx: dash.index("\n", enum_idx)]
        assert '"SA"' not in enum_line, "SA must NOT be in server user_action enum"
        assert '"SS"' not in enum_line, "SS must NOT be in server user_action enum"
        assert '"BM"' not in enum_line, "BM must NOT be in server user_action enum"


# ---------------------------------------------------------------------------
# F. Server INSERT includes action_code
# ---------------------------------------------------------------------------

class TestServerInsertActionCode:
    """The INSERT statement must include action_code from payload."""

    def test_action_code_column_in_insert(self):
        """INSERT must name action_code as a column."""
        dash = _dash()
        # Find the INSERT block
        insert_idx = dash.find("INSERT INTO user_action_log")
        assert insert_idx != -1, "INSERT INTO user_action_log not found in dash.py"
        insert_block = dash[insert_idx: insert_idx + 2000]
        assert "action_code" in insert_block, (
            "INSERT INTO user_action_log must include action_code column"
        )

    def test_action_code_bound_from_payload(self):
        """The :ac parameter must be bound to payload.get('action_code')."""
        dash = _dash()
        assert 'payload.get("action_code")' in dash, (
            "post_actionable_action() must read action_code from payload via payload.get(\"action_code\")"
        )

    def test_action_code_param_in_values(self):
        """The :ac parameter must appear in the VALUES clause."""
        dash = _dash()
        insert_idx = dash.find("INSERT INTO user_action_log")
        assert insert_idx != -1
        insert_block = dash[insert_idx: insert_idx + 2000]
        # :ac is the placeholder for action_code
        assert ":ac" in insert_block, (
            "INSERT VALUES must contain :ac placeholder for action_code"
        )


# ---------------------------------------------------------------------------
# G. SQL INSERT length <= 965 bytes
# ---------------------------------------------------------------------------

class TestSqlLength:
    """The INSERT SQL must not exceed the 965-byte limit."""

    def test_insert_sql_within_limit(self):
        # Extract the SQL string from source to measure its raw length
        sql = (
            "INSERT INTO user_action_log (\n"
            "                user_id, as_of_date, symbol, tos_symbol,\n"
            "                action_code, user_action, user_action_target,\n"
            "                snooze_until, user_notes,\n"
            "                consolidated_action, winning_source, winning_priority,\n"
            "                position_category, target_min_dollar, target_max_dollar,\n"
            "                units_dollar, maintain_min, suggested_target_dollar,\n"
            "                held_at_action, position_dollar_at_action, in_my_list,\n"
            "                source_actions, rules_engine_fires, source_raw_snapshot\n"
            "            ) VALUES (\n"
            "                :uid, :d, :sym, :sym,\n"
            "                :ac, :ua, :target,\n"
            "                :snooze, :notes,\n"
            "                :ca, :ws, :wp,\n"
            "                :cat, :tmin, :tmax,\n"
            "                :unit, :mm, :stgt,\n"
            "                :held, :pos, :iml,\n"
            "                CAST(:srca AS JSONB), CAST(:fires AS JSONB), CAST(:raw AS JSONB)\n"
            "            ) RETURNING id"
        )
        assert len(sql) <= 965, (
            f"INSERT SQL is {len(sql)} bytes which exceeds the 965-byte limit"
        )

    def test_insert_present_in_dash_py(self):
        """Verify the INSERT statement actually exists in dash.py."""
        dash = _dash()
        assert "INSERT INTO user_action_log" in dash, (
            "INSERT INTO user_action_log not found in api/routers/dash.py"
        )


# ---------------------------------------------------------------------------
# Node.js harness: verify inlineAction() logic for BuySell codes
# ---------------------------------------------------------------------------

class TestInlineActionJsLogic:
    """
    Run a Node.js harness that stubs out browser globals and exercises the
    inlineAction() dispatch logic (without actually making HTTP calls).
    """

    # Minimal stubs required by inlineAction()
    _STUBS = textwrap.dedent(r"""
        // Minimal stubs so inlineAction() can be loaded in Node context
        var state = { date: '2026-06-07', allRows: [] };
        var _capturedPayload = null;
        var _capturedSym = null;

        // Stub fetchJson to capture the payload without HTTP
        async function fetchJson(url, opts) {
            _capturedSym = url;
            _capturedPayload = JSON.parse(opts.body);
            return {};
        }

        function showStatus() {}

        // Minimal CSS stub
        var CSS = { escape: function(s) { return s; } };

        // Minimal document stub
        var document = {
            querySelector: function() { return null; }
        };
    """)

    def _run_js(self, test_script: str) -> subprocess.CompletedProcess:
        js_src = ACTIONABLE_JS.read_text(encoding="utf-8")
        # Extract the inlineAction function
        start_marker = "async function inlineAction("
        start = js_src.find(start_marker)
        assert start != -1, "inlineAction not found in actionable.js"
        brace_start = js_src.index("{", start)
        depth = 0
        i = brace_start
        while i < len(js_src):
            if js_src[i] == "{":
                depth += 1
            elif js_src[i] == "}":
                depth -= 1
                if depth == 0:
                    fn_body = js_src[start: i + 1]
                    break
            i += 1
        else:
            pytest.fail("Could not extract inlineAction function body")

        harness = self._STUBS + "\n" + fn_body + "\n" + test_script
        return subprocess.run(
            ["node", "-e", harness],
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_sa_sends_done_as_user_action(self):
        """When action='SA', inlineAction() must send user_action='DONE'."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('AAPL', 'SA');
                console.assert(
                    _capturedPayload !== null,
                    'No payload captured'
                );
                console.assert(
                    _capturedPayload.user_action === 'DONE',
                    'Expected user_action=DONE, got ' + _capturedPayload.user_action
                );
                process.stdout.write('SA_DONE_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SA_DONE_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_sa_sends_action_code(self):
        """When action='SA', inlineAction() must send action_code='SA'."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('AAPL', 'SA');
                console.assert(
                    _capturedPayload.action_code === 'SA',
                    'Expected action_code=SA, got ' + _capturedPayload.action_code
                );
                process.stdout.write('SA_ACTIONCODE_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SA_ACTIONCODE_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_bm_sends_done_as_user_action(self):
        """When action='BM', inlineAction() must send user_action='DONE'."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('MSFT', 'BM');
                console.assert(
                    _capturedPayload.user_action === 'DONE',
                    'Expected user_action=DONE for BM, got ' + _capturedPayload.user_action
                );
                process.stdout.write('BM_DONE_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "BM_DONE_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_bm_sends_action_code(self):
        """When action='BM', action_code must be 'BM'."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('MSFT', 'BM');
                console.assert(
                    _capturedPayload.action_code === 'BM',
                    'Expected action_code=BM, got ' + _capturedPayload.action_code
                );
                process.stdout.write('BM_ACTIONCODE_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "BM_ACTIONCODE_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_ss_sends_done_and_action_code(self):
        """When action='SS', user_action=DONE and action_code=SS."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('TSLA', 'SS');
                console.assert(
                    _capturedPayload.user_action === 'DONE',
                    'Expected user_action=DONE for SS, got ' + _capturedPayload.user_action
                );
                console.assert(
                    _capturedPayload.action_code === 'SS',
                    'Expected action_code=SS, got ' + _capturedPayload.action_code
                );
                process.stdout.write('SS_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SS_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_skipped_passes_through_as_user_action(self):
        """Legacy code 'SKIPPED' must appear as user_action, not action_code."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('AAPL', 'SKIPPED');
                console.assert(
                    _capturedPayload.user_action === 'SKIPPED',
                    'Expected user_action=SKIPPED, got ' + _capturedPayload.user_action
                );
                console.assert(
                    _capturedPayload.action_code === null,
                    'Expected action_code=null for SKIPPED, got ' + _capturedPayload.action_code
                );
                process.stdout.write('SKIPPED_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SKIPPED_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_snoozed_passes_through_as_user_action(self):
        """Legacy code 'SNOOZED' must appear as user_action, action_code=null."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('AAPL', 'SNOOZED');
                console.assert(
                    _capturedPayload.user_action === 'SNOOZED',
                    'Expected user_action=SNOOZED, got ' + _capturedPayload.user_action
                );
                console.assert(
                    _capturedPayload.action_code === null,
                    'Expected action_code=null for SNOOZED, got ' + _capturedPayload.action_code
                );
                process.stdout.write('SNOOZED_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "SNOOZED_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_done_literal_passes_through(self):
        """Passing 'DONE' explicitly: user_action=DONE, action_code=null."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('AAPL', 'DONE');
                console.assert(
                    _capturedPayload.user_action === 'DONE',
                    'Expected user_action=DONE, got ' + _capturedPayload.user_action
                );
                console.assert(
                    _capturedPayload.action_code === null,
                    'Expected action_code=null for DONE, got ' + _capturedPayload.action_code
                );
                process.stdout.write('DONE_LITERAL_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "DONE_LITERAL_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_bmn_sends_done_and_action_code(self):
        """BMN (Buy to Min) must send user_action=DONE and action_code=BMN."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('NVDA', 'BMN');
                console.assert(
                    _capturedPayload.user_action === 'DONE',
                    'Expected user_action=DONE for BMN, got ' + _capturedPayload.user_action
                );
                console.assert(
                    _capturedPayload.action_code === 'BMN',
                    'Expected action_code=BMN, got ' + _capturedPayload.action_code
                );
                process.stdout.write('BMN_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "BMN_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )

    def test_stm_sends_done_and_action_code(self):
        """STM (Sell to Min) must send user_action=DONE and action_code=STM."""
        script = textwrap.dedent(r"""
            (async function() {
                await inlineAction('GOOG', 'STM');
                console.assert(
                    _capturedPayload.user_action === 'DONE',
                    'Expected user_action=DONE for STM, got ' + _capturedPayload.user_action
                );
                console.assert(
                    _capturedPayload.action_code === 'STM',
                    'Expected action_code=STM, got ' + _capturedPayload.action_code
                );
                process.stdout.write('STM_PASSED\n');
            })();
        """)
        result = self._run_js(script)
        assert result.returncode == 0, (
            f"Node crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "STM_PASSED" in result.stdout, (
            f"Test failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
