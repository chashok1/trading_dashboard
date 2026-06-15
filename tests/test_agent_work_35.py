"""
Tests for AGENT_WORK_35 — Actionable default sort uses ref_param_lookup SEQ
(buysell table) instead of hardcoded _FC_SCALE strength, with SA on top.

Acceptance criteria (AGENT_WORK_35.md + DEV_HANDOFF.md):
  Check 1  — node --check web/actionable.js passes (no syntax errors).
  Check 2  — api/routers/ref.py parses cleanly (ast.parse).
  Check 3  — GET /api/ref/buysell endpoint is defined in api/routers/ref.py.
  Check 4  — /api/ref/buysell appears BEFORE /api/ref/{table_name} (wildcard) in ref.py.
  Check 5  — buysellSeq: {} is initialised in the state object in actionable.js.
  Check 6  — loadSources() fetches /api/ref/buysell and stores into state.buysellSeq.
  Check 7  — loadSources() has a try/catch fallback so buysellSeq stays {} on fetch failure.
  Check 8  — _computePriority() uses state.buysellSeq (not _FC_SCALE) as primary sort key.
  Check 9  — _computePriority() uses Math.abs (|AMT$| tiebreaker is preserved).
  Check 10 — _computePriority() uses feasibility gate (infeasible → bottom).
  Check 11 — _computePriority() OVER_MAX is mapped to SO before seq lookup.
  Check 12 — _computePriority() returns seq * 1e12 + amt formula.
  Check 13 — _computePriority() unknown codes (HOLD / empty) fall back to seq = -1.
  Check 14 — _FC_SCALE is still defined (still used by finalCall() internals).
  Check 15 — _FC_SCALE is NOT used as the primary sort key in _computePriority().
  Check 16 — state.sort.dir = -1 (descending) is the default, so highest seq sorts to top.
  Check 17 — /api/ref/buysell live endpoint returns JSON dict with SA as the highest seq
             (DB test — skipped when Postgres is unavailable).
  Check 18 — /api/ref/buysell live endpoint returns only integer seq values (DB test).
  Check 19 — Sort order: SA (seq=21) > BM (seq=18) > BMN (seq=15) when sorted DESC
             using the formula seq*1e12 + amt (pure arithmetic, no DB needed).
  Check 20 — Infeasible row (fc.feasible=false) always sorts below any feasible row,
             regardless of amt.
  Check 21 — OVER_MAX code maps to SO for priority ordering (maps to seq=12 in real data).
  Check 22 — Codes absent from the buysell map (e.g. HOLD) receive seq=-1 and sink to bottom.
  Check 23 — No _agreeingSources fallback in _computePriority (old formula removed).
  Check 24 — The comment block above _computePriority documents the SEQ-based approach.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import urllib.request
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
JS_FILE      = PROJECT_ROOT / "web" / "actionable.js"
REF_PY       = PROJECT_ROOT / "api" / "routers" / "ref.py"

BUYSELL_API  = "http://127.0.0.1:8000/api/ref/buysell"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _js() -> str:
    return JS_FILE.read_text(encoding="utf-8")


def _refpy() -> str:
    return REF_PY.read_text(encoding="utf-8")


def _extract_function(js: str, name: str) -> str:
    """Extract a function body by name from JS source."""
    # Try plain function declaration
    start = js.find(f"function {name}(")
    if start == -1:
        # Try var/let/const assignment form
        start = js.find(f"{name} = function")
        if start == -1:
            raise AssertionError(f"Function '{name}' not found in actionable.js")
    brace_start = js.index("{", start)
    depth = 0
    i = brace_start
    while i < len(js):
        if js[i] == "{":
            depth += 1
        elif js[i] == "}":
            depth -= 1
            if depth == 0:
                return js[start: i + 1]
        i += 1
    raise AssertionError(f"Could not find closing brace for function '{name}'")


def _simulate_compute_priority(seq_map: dict, fc_code: str, fc_feasible: bool, amt: float) -> float:
    """
    Python simulation of the JS _computePriority logic (for arithmetic-only tests).

    seq_map    : dict mapping code (str) -> seq (int)  -- mirrors state.buysellSeq
    fc_code    : finalCall().code (str)
    fc_feasible: finalCall().feasible (bool)
    amt        : row._amt (float)
    """
    amt_abs = abs(amt)
    if not fc_feasible:
        return -1 * 1e12 + amt_abs
    code = (fc_code or "").upper()
    if code == "OVER_MAX":
        code = "SO"
    seq = seq_map.get(code, -1)
    return seq * 1e12 + amt_abs


# ---------------------------------------------------------------------------
# Check 1 — JS syntax
# ---------------------------------------------------------------------------

class TestJsSyntax:
    """node --check must exit 0 (no syntax errors)."""

    def test_node_check_passes(self):
        result = subprocess.run(
            ["node", "--check", str(JS_FILE)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check exited {result.returncode}:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert result.stderr.strip() == "", (
            f"node --check produced stderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# Check 2 — Python parse of ref.py
# ---------------------------------------------------------------------------

class TestRefPyParseable:
    """api/routers/ref.py must parse without syntax errors."""

    def test_ref_py_parses(self):
        src = _refpy()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"api/routers/ref.py has a syntax error: {e}")


# ---------------------------------------------------------------------------
# Checks 3 & 4 — /api/ref/buysell endpoint presence and ordering
# ---------------------------------------------------------------------------

class TestBuysellEndpointDefinition:
    """The buysell endpoint must be defined and come before the wildcard route."""

    def test_endpoint_defined(self):
        src = _refpy()
        assert '"/api/ref/buysell"' in src, (
            "GET /api/ref/buysell endpoint not found in api/routers/ref.py"
        )

    def test_endpoint_is_get(self):
        src = _refpy()
        assert '@router.get("/api/ref/buysell"' in src, (
            "The buysell endpoint must use @router.get"
        )

    def test_endpoint_before_wildcard(self):
        """buysell endpoint must appear before /api/ref/{table_name} to avoid shadowing."""
        src = _refpy()
        buysell_pos  = src.find('"/api/ref/buysell"')
        wildcard_pos = src.find('"/api/ref/{table_name}"')
        assert buysell_pos != -1, '"/api/ref/buysell" not found'
        assert wildcard_pos != -1, '"/api/ref/{table_name}" not found'
        assert buysell_pos < wildcard_pos, (
            f"/api/ref/buysell (pos {buysell_pos}) must appear BEFORE "
            f"/api/ref/{{table_name}} (pos {wildcard_pos}) in ref.py"
        )

    def test_endpoint_queries_buysell_table(self):
        """Endpoint SQL must filter on table_name='buysell'."""
        src = _refpy()
        assert "table_name='buysell'" in src or 'table_name=\'buysell\'' in src, (
            "get_buysell_seq() must query WHERE table_name='buysell'"
        )

    def test_endpoint_returns_code_seq_map(self):
        """Return expression must map code -> seq."""
        src = _refpy()
        # The return statement should reference both code and seq columns.
        assert '"code"' in src or "\"code\"" in src, (
            "get_buysell_seq() return must reference 'code' column"
        )
        assert '"seq"' in src or "\"seq\"" in src, (
            "get_buysell_seq() return must reference 'seq' column"
        )


# ---------------------------------------------------------------------------
# Check 5 — state.buysellSeq initial value
# ---------------------------------------------------------------------------

class TestStateInit:
    """buysellSeq: {} must be in the initial state object."""

    def test_buysell_seq_in_state(self):
        js = _js()
        assert "buysellSeq: {}" in js, (
            "state object must initialise buysellSeq: {} in actionable.js"
        )

    def test_buysell_seq_initialised_before_loadSources(self):
        """buysellSeq: {} must appear within the const state = {...} block."""
        js = _js()
        state_start = js.find("const state = {")
        if state_start == -1:
            state_start = js.find("var state = {")
        assert state_start != -1, "state object not found"
        # Find the closing brace of the state object
        brace_start = js.index("{", state_start)
        depth = 0
        i = brace_start
        while i < len(js):
            if js[i] == "{":
                depth += 1
            elif js[i] == "}":
                depth -= 1
                if depth == 0:
                    state_block = js[brace_start: i + 1]
                    break
            i += 1
        assert "buysellSeq:" in state_block, (
            "buysellSeq must be declared inside the state = {...} block"
        )


# ---------------------------------------------------------------------------
# Check 6 & 7 — loadSources() fetches buysell and has fallback
# ---------------------------------------------------------------------------

class TestLoadSourcesFetches:
    """loadSources must fetch /api/ref/buysell and store into state.buysellSeq."""

    def test_fetch_buysell_in_load_sources(self):
        js = _js()
        body = _extract_function(js, "loadSources")
        assert "/api/ref/buysell" in body, (
            "loadSources() must fetch '/api/ref/buysell'"
        )

    def test_stores_into_state_buysell_seq(self):
        js = _js()
        body = _extract_function(js, "loadSources")
        assert "state.buysellSeq" in body, (
            "loadSources() must store result into state.buysellSeq"
        )

    def test_has_try_catch_fallback(self):
        """loadSources must have a catch block that keeps state.buysellSeq as {}."""
        js = _js()
        body = _extract_function(js, "loadSources")
        # Must have try + catch wrapping the buysell fetch
        assert "try {" in body or "try{" in body, (
            "loadSources() buysell fetch must be wrapped in a try block"
        )
        assert "catch" in body, (
            "loadSources() must have a catch block for buysell fetch failure"
        )

    def test_fallback_to_empty_map(self):
        """Catch block must reset state.buysellSeq to {} on failure."""
        js = _js()
        body = _extract_function(js, "loadSources")
        # Look for the pattern: } catch (_) { state.buysellSeq = {}; }
        assert "buysellSeq = {}" in body or "buysellSeq={}" in body, (
            "loadSources() catch block must set state.buysellSeq = {} on fetch error"
        )


# ---------------------------------------------------------------------------
# Checks 8–13 — _computePriority() formula and structure
# ---------------------------------------------------------------------------

class TestComputePriorityFormula:
    """_computePriority must use seq*1e12+amt, not _FC_SCALE strength."""

    def test_function_exists(self):
        assert "_computePriority" in _js(), "_computePriority must be defined in actionable.js"

    def test_uses_buysell_seq_map(self):
        """_computePriority must read from state.buysellSeq (the DB-sourced map)."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "buysellSeq" in body, (
            "_computePriority must use state.buysellSeq as the sort key source"
        )

    def test_uses_math_abs_for_amt(self):
        """Dollar tiebreaker: Math.abs must be used on _amt."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "Math.abs" in body, (
            "_computePriority must use Math.abs(amt) for the dollar tiebreaker"
        )

    def test_uses_feasibility_gate(self):
        """Infeasible Final Call must sink to the bottom (feasibility check present)."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "fc.feasible" in body, (
            "_computePriority must check fc.feasible for the infeasibility gate"
        )

    def test_over_max_maps_to_so(self):
        """OVER_MAX synthetic code must be mapped to SO before seq lookup."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "OVER_MAX" in body, (
            "_computePriority must handle OVER_MAX code explicitly"
        )
        assert "'SO'" in body or '"SO"' in body, (
            "_computePriority must map OVER_MAX to SO for seq lookup"
        )

    def test_seq_times_1e12_formula(self):
        """Priority formula must be seq * 1e12 + amt."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "1e12" in body, (
            "_computePriority formula must use 1e12 multiplier (seq * 1e12 + amt)"
        )
        assert "seq" in body, (
            "_computePriority must use a seq variable in its formula"
        )

    def test_unknown_code_falls_back_to_minus_1(self):
        """Codes not in the map must resolve to seq = -1."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "-1" in body, (
            "_computePriority must assign seq = -1 when code is not in buysellSeq map"
        )

    def test_no_agreeing_sources_fallback(self):
        """Old formula fallback (_agreeingSources) must NOT be in _computePriority."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        assert "_agreeingSources" not in body, (
            "_computePriority must NOT reference _agreeingSources (old formula removed)"
        )


# ---------------------------------------------------------------------------
# Checks 14 & 15 — _FC_SCALE still present but NOT used as primary sort key
# ---------------------------------------------------------------------------

class TestFcScaleRole:
    """_FC_SCALE must still exist (for finalCall() internals) but NOT in _computePriority."""

    def test_fc_scale_still_defined(self):
        js = _js()
        assert "_FC_SCALE" in js, (
            "_FC_SCALE must still be defined — it is used by finalCall() strength logic"
        )

    def test_fc_scale_not_in_compute_priority(self):
        """_FC_SCALE must no longer be the primary key in _computePriority."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        # _FC_SCALE must not appear inside _computePriority at all
        assert "_FC_SCALE" not in body, (
            "_FC_SCALE must NOT appear in _computePriority (it was the OLD formula)"
        )

    def test_fc_scale_not_strength_as_sort_key(self):
        """The old multiplication 'fc.strength * 1e12' must not appear."""
        js = _js()
        body = _extract_function(js, "_computePriority")
        # Old formula: fc.strength * something or strength * 1e12
        assert "fc.strength" not in body or "strength * 1e12" not in body, (
            "_computePriority must not use fc.strength as the primary sort key"
        )
        # More specifically: the old formula was strength * 1e12 (no seq)
        assert "strength * 1e12" not in body, (
            "_computePriority old formula 'strength * 1e12' must be removed"
        )


# ---------------------------------------------------------------------------
# Check 16 — Default sort direction is -1 (descending)
# ---------------------------------------------------------------------------

class TestDefaultSortDirection:
    """Default sort must be _priority DESC so highest seq (SA=21) appears first."""

    def test_default_sort_dir_minus_1(self):
        js = _js()
        # Look for the initial state.sort definition
        assert "dir: -1" in js, (
            "Default sort direction must be -1 (descending) in state.sort"
        )

    def test_priority_column_default_sort(self):
        """The sort is on _priority by default."""
        js = _js()
        # The loadActionable function resets to _priority, dir: -1
        assert "key: '_priority'" in js or 'key: "_priority"' in js, (
            "Default sort key must be '_priority'"
        )

    def test_priority_comment_documents_desc_intent(self):
        """Comment near _computePriority function definition should document descending direction."""
        js = _js()
        # Find the function definition (not just any call to it)
        idx = js.find("function _computePriority(")
        assert idx != -1, "function _computePriority( not found"
        # Search in the 600 chars before AND inside the function (comment block)
        snippet = js[max(0, idx - 600): idx + 200]
        assert ("DESCENDING" in snippet.upper() or "DESC" in snippet.upper()), (
            "Comment near function _computePriority must document the DESCENDING sort direction"
        )


# ---------------------------------------------------------------------------
# Check 19–22 — Arithmetic correctness (pure Python simulation)
# ---------------------------------------------------------------------------

class TestPriorityArithmetic:
    """Arithmetic checks on the priority formula using a simulated seq map."""

    # Use the real seq values returned by the live API (confirmed: SA=21)
    REAL_SEQ_MAP = {
        "SA": 21, "STM": 20, "S": 19, "SS": 19, "BM": 18, "B": 17,
        "BS": 16, "BMN": 15, "BC": 14, "BR": 13, "SO": 12, "BW": 10,
        "BSW": 9, "BRW": 5, "BWW": 5, "SWW": 5, "SN": 3, "BN": 3, "N": 3,
    }

    def test_sa_ranks_highest_at_same_amt(self):
        """SA (seq=21) must score higher than any other code at the same AMT."""
        amt = 10000.0
        sa_priority = _simulate_compute_priority(self.REAL_SEQ_MAP, "SA", True, amt)
        for code, seq in self.REAL_SEQ_MAP.items():
            if code == "SA":
                continue
            other_priority = _simulate_compute_priority(self.REAL_SEQ_MAP, code, True, amt)
            assert sa_priority > other_priority, (
                f"SA priority ({sa_priority}) must exceed {code} priority ({other_priority})"
            )

    def test_sa_before_bm_regardless_of_amt(self):
        """SA row with small amt must rank above BM row with large amt if seqs differ enough."""
        # SA seq=21, BM seq=18. At 1e12 scale, even $1 vs $1e11 can't bridge the gap.
        sa_small  = _simulate_compute_priority(self.REAL_SEQ_MAP, "SA", True, 1.0)
        bm_large  = _simulate_compute_priority(self.REAL_SEQ_MAP, "BM", True, 1e11)
        # 21e12 + 1 vs 18e12 + 1e11  => 21e12+1 > 18e12+1e11 = 18.1e12
        assert sa_small > bm_large, (
            f"SA (small amt) priority {sa_small} must exceed BM (large amt) priority {bm_large}"
        )

    def test_dollar_tiebreak_within_same_seq(self):
        """Within the same seq tier, larger |amt| must rank higher."""
        p_small = _simulate_compute_priority(self.REAL_SEQ_MAP, "SA", True, 1000.0)
        p_large = _simulate_compute_priority(self.REAL_SEQ_MAP, "SA", True, 50000.0)
        assert p_large > p_small, (
            "Larger AMT must produce higher priority within the same seq tier"
        )

    def test_infeasible_row_sinks_below_all_feasible(self):
        """Infeasible row (feasible=False) must score below every feasible code."""
        infeasible = _simulate_compute_priority(self.REAL_SEQ_MAP, "SA", False, 1e12)
        for code, seq in self.REAL_SEQ_MAP.items():
            feasible = _simulate_compute_priority(self.REAL_SEQ_MAP, code, True, 0.0)
            assert infeasible < feasible, (
                f"Infeasible row priority {infeasible} must be less than "
                f"feasible {code} priority {feasible}"
            )

    def test_over_max_maps_to_so_seq(self):
        """OVER_MAX code must use SO's seq (12) for ordering."""
        over_max_p = _simulate_compute_priority(self.REAL_SEQ_MAP, "OVER_MAX", True, 0.0)
        so_p       = _simulate_compute_priority(self.REAL_SEQ_MAP, "SO", True, 0.0)
        assert over_max_p == so_p, (
            f"OVER_MAX priority {over_max_p} must equal SO priority {so_p} "
            "(OVER_MAX is mapped to SO before seq lookup)"
        )

    def test_unknown_code_gets_minus_1_seq(self):
        """HOLD (not in buysell map) must receive seq=-1, sinking to bottom."""
        p_hold = _simulate_compute_priority(self.REAL_SEQ_MAP, "HOLD", True, 9999.0)
        # seq=-1: -1e12 + 9999  (still very negative)
        assert p_hold < 0, (
            f"HOLD (unknown code) priority {p_hold} must be < 0 (seq=-1 assigned)"
        )
        # Must be below any real code with $0 AMT
        for code in self.REAL_SEQ_MAP:
            real_p = _simulate_compute_priority(self.REAL_SEQ_MAP, code, True, 0.0)
            if self.REAL_SEQ_MAP[code] >= 0:
                assert p_hold < real_p, (
                    f"HOLD priority {p_hold} must be below feasible {code} priority {real_p}"
                )

    def test_sort_descending_puts_sa_first(self):
        """When sorted descending (dir=-1), SA must appear before all other actions."""
        rows = [
            {"code": "BM",  "feasible": True,  "amt": 50000.0},
            {"code": "SA",  "feasible": True,  "amt": 1000.0},
            {"code": "BMN", "feasible": True,  "amt": 20000.0},
            {"code": "HOLD","feasible": True,  "amt": 9999.0},
            {"code": "SA",  "feasible": False, "amt": 5000.0},  # infeasible
        ]
        priorities = [
            _simulate_compute_priority(self.REAL_SEQ_MAP, r["code"], r["feasible"], r["amt"])
            for r in rows
        ]
        # Sort descending (dir=-1 means larger priority first)
        sorted_rows = sorted(zip(priorities, rows), key=lambda x: x[0], reverse=True)
        # SA (feasible) must be first
        first = sorted_rows[0][1]
        assert first["code"] == "SA" and first["feasible"] is True, (
            f"SA feasible must sort to the top in descending order, got: {first}"
        )
        # Infeasible SA must be last or near-last (HOLD also sinks)
        last_two_codes = {r["code"] for _, r in sorted_rows[-2:]}
        assert "SA" in last_two_codes or "HOLD" in last_two_codes, (
            f"Infeasible/HOLD rows must sort to the bottom. Bottom two: {list(last_two_codes)}"
        )


# ---------------------------------------------------------------------------
# Check 17 & 18 — Live API endpoint (DB test, skips if Postgres unavailable)
# ---------------------------------------------------------------------------

def _server_available() -> bool:
    """Return True if the API server is reachable."""
    try:
        urllib.request.urlopen(BUYSELL_API, timeout=2)
        return True
    except Exception:
        return False


SERVER_AVAILABLE = _server_available()


@pytest.mark.skipif(not SERVER_AVAILABLE, reason="API server not running at 127.0.0.1:8000")
class TestLiveApiEndpoint:
    """Tests against the running server — skipped when server is not available."""

    @pytest.fixture(scope="class")
    def buysell_data(self):
        """Fetch /api/ref/buysell once for the whole class."""
        with urllib.request.urlopen(BUYSELL_API, timeout=5) as r:
            return json.loads(r.read())

    def test_returns_dict(self, buysell_data):
        """Response must be a JSON object (dict)."""
        assert isinstance(buysell_data, dict), (
            f"Expected dict from /api/ref/buysell, got {type(buysell_data)}"
        )

    def test_non_empty(self, buysell_data):
        """Response must contain at least one code."""
        assert len(buysell_data) > 0, "Buysell map must not be empty"

    def test_sa_present(self, buysell_data):
        """SA code must be in the map."""
        assert "SA" in buysell_data, (
            f"SA must be in buysell map. Got keys: {sorted(buysell_data.keys())}"
        )

    def test_sa_is_highest_seq(self, buysell_data):
        """SA must have the highest seq value in the map (per spec: SA=21)."""
        max_seq = max(buysell_data.values())
        sa_seq  = buysell_data["SA"]
        assert sa_seq == max_seq, (
            f"SA seq ({sa_seq}) must be the highest in the map (max is {max_seq}). "
            f"Full map: {buysell_data}"
        )

    def test_all_values_are_integers(self, buysell_data):
        """All seq values must be integers (not strings, not floats)."""
        non_int = {k: v for k, v in buysell_data.items() if not isinstance(v, int)}
        assert not non_int, (
            f"All buysell seq values must be int. Non-int entries: {non_int}"
        )

    def test_known_codes_have_expected_seqs(self, buysell_data):
        """Spot-check a few known codes against expected seq values."""
        expected = {"SA": 21, "STM": 20, "BM": 18, "BMN": 15, "SO": 12}
        failures = []
        for code, expected_seq in expected.items():
            if code in buysell_data and buysell_data[code] != expected_seq:
                failures.append(
                    f"  {code}: expected seq={expected_seq}, got {buysell_data[code]}"
                )
        assert not failures, (
            "Known buysell codes have unexpected seq values:\n" + "\n".join(failures)
        )

    def test_sell_codes_rank_above_buy_codes(self, buysell_data):
        """Strong sell codes (SA/STM/SS) must have higher seq than strong buy codes (BM/BS).

        This encodes the SA-on-top business rule in a data-driven way.
        """
        sell_seqs = [buysell_data[c] for c in ["SA", "STM", "SS"] if c in buysell_data]
        buy_seqs  = [buysell_data[c] for c in ["BM", "BS", "BMN"] if c in buysell_data]
        if sell_seqs and buy_seqs:
            assert min(sell_seqs) > max(buy_seqs), (
                f"All sell codes must rank above all buy codes.\n"
                f"Sell seqs: {sell_seqs}, Buy seqs: {buy_seqs}"
            )


# ---------------------------------------------------------------------------
# Check 24 — Comment documents the SEQ-based approach
# ---------------------------------------------------------------------------

class TestDocumentation:
    """Comment block above _computePriority must mention SEQ / ref_param_lookup."""

    def test_comment_mentions_seq(self):
        js = _js()
        idx = js.find("function _computePriority(")
        assert idx != -1, "_computePriority function not found"
        # Look in the 400 characters before the function definition
        prefix = js[max(0, idx - 400): idx]
        assert "SEQ" in prefix.upper() or "seq" in prefix, (
            "Comment above _computePriority must reference 'SEQ' (the sort key)"
        )

    def test_comment_mentions_ref_param_lookup_or_buysell(self):
        js = _js()
        idx = js.find("function _computePriority(")
        prefix = js[max(0, idx - 400): idx]
        has_ref = "ref_param_lookup" in prefix.lower() or "buysell" in prefix.lower()
        assert has_ref, (
            "Comment above _computePriority should reference 'ref_param_lookup' or 'buysell' "
            "to document where the sort key comes from"
        )
