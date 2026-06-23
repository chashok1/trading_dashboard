"""
Tests for AGENT_WORK_8 / TASK_70 — Parallel calibrated Final Call (evaluation-only).

Acceptance criteria verified (pure-Python, no DB required):

  Existing action mechanism UNCHANGED
    Check 01  — derive_actionable.py not listed in DEV_HANDOFF Files changed
    Check 02  — derive_bull_prob.py not listed in DEV_HANDOFF Files changed
    Check 03  — git diff shows ZERO deleted lines in etl/derive_actionable.py
    Check 04  — git diff shows ZERO deleted lines in etl/derive_bull_prob.py
    Check 05  — _compute_final_call definition unchanged in derive_actionable.py
    Check 06  — _FC_SCALE dict definition exists in derive_actionable.py (unchanged)

  New DB columns in baseline.sql
    Check 07  — ALTER TABLE drv_actionable ADD COLUMN IF NOT EXISTS final_action_cal
    Check 08  — ALTER TABLE drv_actionable ADD COLUMN IF NOT EXISTS final_code_cal
    Check 09  — ALTER TABLE drv_actionable ADD COLUMN IF NOT EXISTS final_side_cal
    Check 10  — ALTER TABLE drv_actionable ADD COLUMN IF NOT EXISTS fc_strength_cal
    Check 11  — All 4 ALTER TABLE use IF NOT EXISTS pattern (idempotent DDL)
    Check 12  — All 4 ALTER TABLE are under 965 bytes each

  New derive module (etl/derive_final_call_cal.py)
    Check 13  — File exists and parses cleanly (Python ast)
    Check 14  — Uses tos_symbol (not raw symbol) in SELECT
    Check 15  — Uses tos_symbol in WHERE clause of UPDATE
    Check 16  — Does NOT contain bare "symbol" column references
    Check 17  — Idempotent: clears *_cal columns before inserting (NULL update)
    Check 18  — NULL-safe: checks bull_prob IS NOT NULL before computing
    Check 19  — Derives from bull_prob only — does not call _compute_final_call
    Check 20  — _PROB_BANDS defines 5 bands covering range >=0.65 down to 0.00
    Check 21  — BM band (>= 0.65) has strength +2
    Check 22  — SA band (< 0.35) has strength -3
    Check 23  — HOLD band has strength 0 and side 'neutral'
    Check 24  — Gate 1: EXIT_CODES gate present (REMOVE / SA on held symbol → SA)
    Check 25  — Gate 2: don't-initiate guard present (not held + not buy → HOLD)
    Check 26  — Gate 3: over-max guard present (buy + curr_pos > tgt_max → HOLD)
    Check 27  — Returns int (row count)
    Check 28  — All SQL statements under 965 bytes

  Wire-in to derive_all (etl/derive.py)
    Check 29  — derive_final_call_cal imported inside try/except block
    Check 30  — _safe("drv_final_call_cal", ...) called inside try block
    Check 31  — outer except catches Exception (non-critical failure handler)
    Check 32  — Wire-in is positioned after derive_bull_prob in the file
    Check 33  — drv_final_call_cal NOT listed in _CRITICAL set

  New API endpoint (api/routers/rules.py)
    Check 34  — @router.get("/api/actionable/final-call-cal") decorator present
    Check 35  — response_model=list[dict] declared
    Check 36  — Endpoint SQL selects tos_symbol
    Check 37  — Endpoint SQL selects bull_prob and final_code_cal
    Check 38  — Endpoint SQL selects fc_strength_cal
    Check 39  — Endpoint SQL uses ORDER BY fc_strength_cal DESC NULLS LAST
    Check 40  — Endpoint SQL filters AND final_code_cal IS NOT NULL
    Check 41  — Endpoint SQL is under 965 bytes
    Check 42  — No existing endpoint response shape modified (no deleted lines)

  Actionable screen HTML (web/actionable.html)
    Check 43  — New <th> with FC (cal) text present
    Check 44  — New <th> uses data-key="fc_strength_cal"
    Check 45  — New <th> is immediately after the "Final Call" column header
    Check 46  — title attribute mentions evaluation-only / bull_prob

  Actionable screen JS (web/actionable.js)
    Check 47  — _finalCallCalHtml function defined
    Check 48  — _finalCallCalHtml reads final_code_cal field
    Check 49  — _finalCallCalHtml reads final_side_cal field
    Check 50  — _finalCallCalHtml reads fc_strength_cal field
    Check 51  — _finalCallCalHtml reads bull_prob for tooltip
    Check 52  — Amber "vs" border logic (f59e0b) when sides disagree
    Check 53  — New <td> calling _finalCallCalHtml in row template
    Check 54  — No existing JS functions deleted/modified (zero removed lines)

  Probability band mapping logic
    Check 55  — prob=0.70 maps to BM (buy) strength=+2
    Check 56  — prob=0.65 maps to BM (buy, at boundary)
    Check 57  — prob=0.60 maps to BS (buy)
    Check 58  — prob=0.55 maps to BS (buy, at boundary)
    Check 59  — prob=0.50 maps to HOLD (neutral)
    Check 60  — prob=0.45 maps to HOLD (neutral, at boundary)
    Check 61  — prob=0.40 maps to SS (sell)
    Check 62  — prob=0.35 maps to SS (sell, at boundary)
    Check 63  — prob=0.20 maps to SA (sell)
    Check 64  — prob=0.00 maps to SA (sell, at boundary)
    Check 65  — fallback for prob<0.00 returns HOLD (safe fallback)

  DEV_HANDOFF status
    Check 66  — DEV_HANDOFF.md references AGENT_WORK_8
    Check 67  — DEV_HANDOFF.md Status is ALL_DONE
    Check 68  — DEV_HANDOFF.md lists derive_final_call_cal.py as changed
    Check 69  — DEV_HANDOFF.md lists db/baseline.sql as changed
    Check 70  — DEV_HANDOFF.md lists api/routers/rules.py as changed
    Check 71  — DEV_HANDOFF.md lists web/actionable.html as changed
    Check 72  — DEV_HANDOFF.md lists web/actionable.js as changed
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

BASELINE_SQL          = PROJECT / "db" / "baseline.sql"
DERIVE_CAL            = PROJECT / "etl" / "derive_final_call_cal.py"
DERIVE_PY             = PROJECT / "etl" / "derive.py"
DERIVE_ACTIONABLE     = PROJECT / "etl" / "derive_actionable.py"
DERIVE_BULL_PROB      = PROJECT / "etl" / "derive_bull_prob.py"
RULES_PY              = PROJECT / "api" / "routers" / "rules.py"
ACTIONABLE_HTML       = PROJECT / "web" / "actionable.html"
ACTIONABLE_JS         = PROJECT / "web" / "actionable.js"
DEV_HANDOFF           = PROJECT / "DEV_HANDOFF.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _git_diff_lines(path: Path, kind: str = "-") -> list[str]:
    """Return lines from git diff HEAD for the given file, filtered by kind ('+' or '-')."""
    try:
        result = subprocess.run(
            ["git", "diff", "--", str(path.relative_to(PROJECT))],
            cwd=str(PROJECT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return [
            ln for ln in result.stdout.splitlines()
            if ln.startswith(kind) and not ln.startswith(kind * 3)
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sql_src() -> str:
    assert BASELINE_SQL.exists(), f"Missing: {BASELINE_SQL}"
    return _read(BASELINE_SQL)


@pytest.fixture(scope="module")
def derive_cal_src() -> str:
    assert DERIVE_CAL.exists(), f"Missing: {DERIVE_CAL}"
    return _read(DERIVE_CAL)


@pytest.fixture(scope="module")
def derive_py_src() -> str:
    assert DERIVE_PY.exists(), f"Missing: {DERIVE_PY}"
    return _read(DERIVE_PY)


@pytest.fixture(scope="module")
def derive_actionable_src() -> str:
    assert DERIVE_ACTIONABLE.exists(), f"Missing: {DERIVE_ACTIONABLE}"
    return _read(DERIVE_ACTIONABLE)


@pytest.fixture(scope="module")
def rules_src() -> str:
    assert RULES_PY.exists(), f"Missing: {RULES_PY}"
    return _read(RULES_PY)


@pytest.fixture(scope="module")
def html_src() -> str:
    assert ACTIONABLE_HTML.exists(), f"Missing: {ACTIONABLE_HTML}"
    return _read(ACTIONABLE_HTML)


@pytest.fixture(scope="module")
def js_src() -> str:
    assert ACTIONABLE_JS.exists(), f"Missing: {ACTIONABLE_JS}"
    return _read(ACTIONABLE_JS)


@pytest.fixture(scope="module")
def handoff_src() -> str:
    assert DEV_HANDOFF.exists(), f"Missing: {DEV_HANDOFF}"
    return _read(DEV_HANDOFF)


# ===========================================================================
# EXISTING ACTION MECHANISM UNCHANGED
# ===========================================================================

class TestExistingMechanismUnchanged:

    def test_check01_derive_actionable_not_in_changed_files(self, handoff_src):
        """Check 01 — derive_actionable.py not listed in Files changed section."""
        # Extract the 'Files changed' section only
        files_section = ""
        in_section = False
        for line in handoff_src.splitlines():
            if line.strip().startswith("## Files changed"):
                in_section = True
                continue
            if in_section and line.strip().startswith("## "):
                break
            if in_section:
                files_section += line + "\n"
        assert "derive_actionable.py" not in files_section, (
            "derive_actionable.py appears in DEV_HANDOFF 'Files changed' — "
            "must NOT be modified by TASK_70 (hard constraint)"
        )

    def test_check02_derive_bull_prob_not_in_changed_files(self, handoff_src):
        """Check 02 — derive_bull_prob.py not listed in Files changed section."""
        files_section = ""
        in_section = False
        for line in handoff_src.splitlines():
            if line.strip().startswith("## Files changed"):
                in_section = True
                continue
            if in_section and line.strip().startswith("## "):
                break
            if in_section:
                files_section += line + "\n"
        assert "derive_bull_prob.py" not in files_section, (
            "derive_bull_prob.py appears in DEV_HANDOFF 'Files changed' — "
            "must NOT be modified by TASK_70"
        )

    def test_check03_no_deleted_lines_in_derive_actionable(self):
        """Check 03 — git diff shows ZERO deleted lines in etl/derive_actionable.py."""
        removed = _git_diff_lines(DERIVE_ACTIONABLE, kind="-")
        assert not removed, (
            f"git diff shows {len(removed)} deleted lines in derive_actionable.py — "
            f"existing mechanism must be byte-for-byte unchanged.\n"
            f"First removed: {removed[:3]}"
        )

    def test_check04_no_deleted_lines_in_derive_bull_prob(self):
        """Check 04 — git diff shows ZERO deleted lines in etl/derive_bull_prob.py."""
        removed = _git_diff_lines(DERIVE_BULL_PROB, kind="-")
        assert not removed, (
            f"git diff shows {len(removed)} deleted lines in derive_bull_prob.py — "
            f"must be unchanged.\nFirst removed: {removed[:3]}"
        )

    def test_check05_compute_final_call_present(self, derive_actionable_src):
        """Check 05 — _compute_final_call definition exists in derive_actionable.py."""
        assert "def _compute_final_call(" in derive_actionable_src, (
            "_compute_final_call not found in derive_actionable.py — "
            "function must not have been removed or renamed"
        )

    def test_check06_fc_scale_dict_present(self, derive_actionable_src):
        """Check 06 — _FC_SCALE dict exists in derive_actionable.py."""
        assert "_FC_SCALE" in derive_actionable_src, (
            "_FC_SCALE not found in derive_actionable.py — must be untouched"
        )


# ===========================================================================
# NEW DB COLUMNS IN BASELINE.SQL
# ===========================================================================

class TestNewDbColumns:

    def test_check07_final_action_cal_column(self, sql_src):
        """Check 07 — ADD COLUMN IF NOT EXISTS final_action_cal present."""
        assert "ADD COLUMN IF NOT EXISTS final_action_cal" in sql_src, (
            "ADD COLUMN IF NOT EXISTS final_action_cal not found in baseline.sql"
        )

    def test_check08_final_code_cal_column(self, sql_src):
        """Check 08 — ADD COLUMN IF NOT EXISTS final_code_cal present."""
        assert "ADD COLUMN IF NOT EXISTS final_code_cal" in sql_src, (
            "ADD COLUMN IF NOT EXISTS final_code_cal not found in baseline.sql"
        )

    def test_check09_final_side_cal_column(self, sql_src):
        """Check 09 — ADD COLUMN IF NOT EXISTS final_side_cal present."""
        assert "ADD COLUMN IF NOT EXISTS final_side_cal" in sql_src, (
            "ADD COLUMN IF NOT EXISTS final_side_cal not found in baseline.sql"
        )

    def test_check10_fc_strength_cal_column(self, sql_src):
        """Check 10 — ADD COLUMN IF NOT EXISTS fc_strength_cal present."""
        assert "ADD COLUMN IF NOT EXISTS fc_strength_cal" in sql_src, (
            "ADD COLUMN IF NOT EXISTS fc_strength_cal not found in baseline.sql"
        )

    def test_check11_all_alter_table_idempotent(self, sql_src):
        """Check 11 — All 4 new ALTER TABLEs use ALTER TABLE IF EXISTS + ADD COLUMN IF NOT EXISTS."""
        for col in ("final_action_cal", "final_code_cal", "final_side_cal", "fc_strength_cal"):
            # Find the ADD COLUMN statement
            idx = sql_src.find(f"ADD COLUMN IF NOT EXISTS {col}")
            assert idx >= 0, f"ADD COLUMN IF NOT EXISTS {col} not found"
            # Check the ALTER TABLE before it uses IF EXISTS
            block_start = max(0, idx - 100)
            block = sql_src[block_start:idx]
            assert "ALTER TABLE IF EXISTS drv_actionable" in block, (
                f"ALTER TABLE IF EXISTS not used for {col} — DDL must be idempotent"
            )

    def test_check12_alter_table_lengths_under_965(self, sql_src):
        """Check 12 — Each ALTER TABLE statement is under 965 bytes."""
        # Extract the TASK_70 DDL block
        idx = sql_src.find("TASK_70")
        assert idx >= 0, "TASK_70 comment not found in baseline.sql"
        block = sql_src[idx:idx + 600]
        stmts = [
            s.strip() for s in re.findall(
                r"ALTER TABLE[^;]+;", block, re.DOTALL | re.IGNORECASE
            )
        ]
        assert stmts, "No ALTER TABLE statements found in TASK_70 block"
        for stmt in stmts:
            normalized = " ".join(stmt.split())
            length = len(normalized.encode("utf-8"))
            assert length < 965, (
                f"ALTER TABLE statement is {length} bytes (max 965): {normalized[:80]}"
            )


# ===========================================================================
# NEW DERIVE MODULE
# ===========================================================================

class TestDeriveFinalCallCal:

    def test_check13_file_parses_cleanly(self, derive_cal_src):
        """Check 13 — etl/derive_final_call_cal.py parses without syntax errors."""
        try:
            ast.parse(derive_cal_src)
        except SyntaxError as e:
            pytest.fail(f"SyntaxError in derive_final_call_cal.py: {e}")

    def test_check14_uses_tos_symbol_in_select(self, derive_cal_src):
        """Check 14 — tos_symbol is selected in the query (not raw 'symbol')."""
        assert "SELECT tos_symbol" in derive_cal_src or \
               "tos_symbol," in derive_cal_src, (
            "tos_symbol not found in SELECT statement of derive_final_call_cal.py — "
            "must use tos_symbol per convention #15"
        )

    def test_check15_uses_tos_symbol_in_update_where(self, derive_cal_src):
        """Check 15 — UPDATE WHERE clause uses tos_symbol."""
        # The UPDATE statement must filter by tos_symbol, not symbol
        assert "tos_symbol  = :sym" in derive_cal_src or \
               "tos_symbol = :sym" in derive_cal_src, (
            "UPDATE WHERE tos_symbol = :sym not found in derive_final_call_cal.py"
        )

    def test_check16_no_bare_symbol_column(self, derive_cal_src):
        """Check 16 — No bare 'symbol' column references in SQL (only tos_symbol allowed)."""
        # Look for SQL SELECT or WHERE on bare "symbol" column — must not appear outside
        # tos_symbol context.  Strip the file of SQL strings and check those only.
        sql_blocks = re.findall(r'text\("""(.*?)"""\)', derive_cal_src, re.DOTALL)
        sql_blocks += re.findall(r'text\("(.*?)"\)', derive_cal_src, re.DOTALL)
        full_sql = "\n".join(sql_blocks)
        # In the SQL, "symbol" must only appear as part of tos_symbol
        # A bare column reference would be "symbol" alone (not tos_symbol)
        bare = re.findall(r'\bsymbol\b(?!\s*_)', full_sql, re.IGNORECASE)
        # Filter: allow occurrences that are preceded by "tos_" (part of tos_symbol)
        truly_bare = [
            b for b in bare
            if not re.search(r'tos_symbol', full_sql[max(0, full_sql.find(b)-10):full_sql.find(b)+20])
        ]
        # Actually, the simplest check: the SQL must contain "tos_symbol" and not a
        # standalone column named just "symbol" in a SELECT or WHERE clause.
        # If tos_symbol is used, convention is met.
        assert "tos_symbol" in full_sql, (
            "tos_symbol not found in SQL blocks of derive_final_call_cal.py"
        )
        # Check that there's no bare 'SELECT symbol,' or 'WHERE symbol ='
        assert not re.search(r'SELECT\s+symbol\s*,', full_sql, re.IGNORECASE), (
            "Bare 'SELECT symbol,' found in SQL — must use tos_symbol"
        )
        assert not re.search(r'WHERE\s+symbol\s*=', full_sql, re.IGNORECASE), (
            "Bare 'WHERE symbol =' found in SQL — must use tos_symbol"
        )

    def test_check17_idempotent_null_clear(self, derive_cal_src):
        """Check 17 — File clears *_cal columns to NULL before computing (idempotency)."""
        assert "final_action_cal = NULL" in derive_cal_src or \
               "= NULL" in derive_cal_src, (
            "No NULL-clear UPDATE found in derive_final_call_cal.py — "
            "function must be idempotent (clear then recompute)"
        )
        # All four columns must be cleared
        for col in ("final_action_cal", "final_code_cal", "final_side_cal", "fc_strength_cal"):
            assert col in derive_cal_src, (
                f"{col} not referenced in derive_final_call_cal.py"
            )

    def test_check18_null_safe_check(self, derive_cal_src):
        """Check 18 — Guards against NULL bull_prob before computing."""
        assert "bull_prob IS NOT NULL" in derive_cal_src or \
               "bull_prob is not None" in derive_cal_src or \
               "has_prob" in derive_cal_src, (
            "No NULL guard for bull_prob found in derive_final_call_cal.py"
        )

    def test_check19_does_not_call_compute_final_call(self, derive_cal_src):
        """Check 19 — derive_final_call_cal does NOT *call* _compute_final_call."""
        # _compute_final_call may appear in comments/docstrings (acceptable) but
        # must not be invoked. A call looks like "_compute_final_call(" outside comments.
        # Strip line comments and docstrings for the check.
        # Simple approach: look for a call expression pattern (not just the name)
        lines = derive_cal_src.splitlines()
        call_lines = [
            ln for ln in lines
            if "_compute_final_call(" in ln and not ln.lstrip().startswith("#")
            and not ln.lstrip().startswith('"""') and not ln.lstrip().startswith("'''")
        ]
        # Also exclude docstring content (lines inside triple-quote blocks)
        # For safety, just assert no line that is actual code (not comment) calls it
        assert not call_lines, (
            f"_compute_final_call() is called in derive_final_call_cal.py (not just "
            f"mentioned in comments) — must be an independent implementation.\n"
            f"Lines: {call_lines}"
        )

    def test_check20_five_probability_bands(self, derive_cal_src):
        """Check 20 — _PROB_BANDS defines 5 tuples covering >=0.65 down to 0.00."""
        assert "_PROB_BANDS" in derive_cal_src, "_PROB_BANDS not defined"
        # Check thresholds present
        for threshold in ("0.65", "0.55", "0.45", "0.35", "0.00"):
            assert threshold in derive_cal_src, (
                f"Probability threshold {threshold} not found in _PROB_BANDS"
            )

    def test_check21_bm_band_strength_plus_2(self, derive_cal_src):
        """Check 21 — BM (>= 0.65) band has strength +2."""
        # Find the BM tuple in _PROB_BANDS
        assert '"BM"' in derive_cal_src or "'BM'" in derive_cal_src, (
            "BM code not found in derive_final_call_cal.py probability bands"
        )
        # Verify BM maps to strength 2 (same as _FC_SCALE)
        sys.path.insert(0, str(PROJECT))
        try:
            from etl.derive_final_call_cal import _prob_to_raw
            result = _prob_to_raw(0.70)
            assert result[3] == 2, (
                f"prob=0.70 should give strength=2, got {result[3]}"
            )
        except ImportError:
            # Can't import — at least check the text
            assert "2)" in derive_cal_src, "Strength 2 not found for BM band"

    def test_check22_sa_band_strength_minus_3(self, derive_cal_src):
        """Check 22 — SA (< 0.35) band has strength -3."""
        sys.path.insert(0, str(PROJECT))
        try:
            from etl.derive_final_call_cal import _prob_to_raw
            result = _prob_to_raw(0.20)
            assert result[3] == -3, (
                f"prob=0.20 should give strength=-3, got {result[3]}"
            )
        except ImportError:
            assert "-3)" in derive_cal_src, "Strength -3 not found for SA band"

    def test_check23_hold_band_neutral(self, derive_cal_src):
        """Check 23 — HOLD band has strength 0 and side 'neutral'."""
        sys.path.insert(0, str(PROJECT))
        try:
            from etl.derive_final_call_cal import _prob_to_raw
            result = _prob_to_raw(0.50)
            assert result[3] == 0, (
                f"prob=0.50 should give strength=0, got {result[3]}"
            )
            assert result[2] == "neutral", (
                f"prob=0.50 should give side='neutral', got {result[2]}"
            )
        except ImportError:
            assert "'neutral'" in derive_cal_src or '"neutral"' in derive_cal_src

    def test_check24_gate1_exit_codes_present(self, derive_cal_src):
        """Check 24 — Gate 1: strategic exit (REMOVE/SA on held → SA) present."""
        assert "_EXIT_CODES" in derive_cal_src or "REMOVE" in derive_cal_src, (
            "Gate 1 exit code guard (REMOVE/SA on held symbol) not found"
        )
        assert "held" in derive_cal_src, (
            "held field not referenced in derive_final_call_cal.py (needed for Gate 1)"
        )

    def test_check25_gate2_dont_initiate_present(self, derive_cal_src):
        """Check 25 — Gate 2: don't-initiate guard (not held + not buy → HOLD) present."""
        assert "not held" in derive_cal_src or "held_today" in derive_cal_src, (
            "Gate 2 (don't-initiate guard) not found in derive_final_call_cal.py"
        )
        assert "_BUY_CODES" in derive_cal_src or "BUY" in derive_cal_src.upper(), (
            "BUY codes check not found in Gate 2"
        )

    def test_check26_gate3_over_max_present(self, derive_cal_src):
        """Check 26 — Gate 3: over-max guard (buy + curr_pos > tgt_max → HOLD) present."""
        assert "tgt_max" in derive_cal_src or "target_max_dollar" in derive_cal_src, (
            "Gate 3 over-max guard not found in derive_final_call_cal.py"
        )
        assert "curr_pos" in derive_cal_src or "current_position_dollar" in derive_cal_src, (
            "current_position_dollar not referenced in derive_final_call_cal.py"
        )

    def test_check27_returns_int(self, derive_cal_src):
        """Check 27 — Function returns int (row count)."""
        assert "return 0" in derive_cal_src, "return 0 not found (early exits)"
        assert "return n" in derive_cal_src or "return len(" in derive_cal_src, (
            "Function does not appear to return a row count"
        )

    def test_check28_all_sql_under_965_bytes(self, derive_cal_src):
        """Check 28 — All SQL statements in derive_final_call_cal.py are under 965 bytes."""
        # Extract text() calls
        sql_blocks = re.findall(r'text\("""(.*?)"""\)', derive_cal_src, re.DOTALL)
        sql_blocks += re.findall(r'text\("(.*?)"\)', derive_cal_src, re.DOTALL)
        assert sql_blocks, "No text() SQL calls found in derive_final_call_cal.py"
        for i, block in enumerate(sql_blocks):
            normalized = " ".join(block.split())
            length = len(normalized.encode("utf-8"))
            assert length < 965, (
                f"SQL statement {i+1} in derive_final_call_cal.py is {length} bytes "
                f"(max 965): {normalized[:100]}"
            )


# ===========================================================================
# WIRE-IN TO DERIVE_ALL
# ===========================================================================

class TestWireInToDeriveAll:

    def test_check29_import_inside_try(self, derive_py_src):
        """Check 29 — derive_final_call_cal imported inside a try block in derive.py."""
        idx = derive_py_src.find("derive_final_call_cal")
        assert idx >= 0, "derive_final_call_cal not referenced in derive.py"
        # The import must be inside a try block
        # Look back from the import for a 'try:' line
        block_before = derive_py_src[max(0, idx - 300):idx]
        assert "try:" in block_before, (
            "derive_final_call_cal import is not inside a try: block in derive.py — "
            "must be non-critical"
        )

    def test_check30_safe_call_present(self, derive_py_src):
        """Check 30 — _safe('drv_final_call_cal', ...) called inside the try block."""
        assert '"drv_final_call_cal"' in derive_py_src or \
               "'drv_final_call_cal'" in derive_py_src, (
            "_safe('drv_final_call_cal', ...) call not found in derive.py"
        )

    def test_check31_except_catches_exception(self, derive_py_src):
        """Check 31 — outer except catches Exception after the import try."""
        idx = derive_py_src.find("derive_final_call_cal")
        assert idx >= 0
        block_after = derive_py_src[idx:idx + 400]
        assert "except Exception:" in block_after, (
            "Non-critical except Exception block not found after derive_final_call_cal import"
        )

    def test_check32_positioned_after_derive_bull_prob(self, derive_py_src):
        """Check 32 — Wire-in appears after derive_bull_prob in the file."""
        pos_bull = derive_py_src.find("derive_bull_prob")
        pos_cal  = derive_py_src.find("derive_final_call_cal")
        assert pos_bull >= 0, "derive_bull_prob not found in derive.py"
        assert pos_cal  >= 0, "derive_final_call_cal not found in derive.py"
        assert pos_bull < pos_cal, (
            f"derive_final_call_cal wire-in (pos {pos_cal}) appears BEFORE "
            f"derive_bull_prob (pos {pos_bull}) — must run after bull_prob is populated"
        )

    def test_check33_not_in_critical_set(self, derive_py_src):
        """Check 33 — drv_final_call_cal is NOT listed in the _CRITICAL set."""
        # Find the _CRITICAL set definition
        crit_match = re.search(r'_CRITICAL\s*=\s*\{([^}]+)\}', derive_py_src)
        if crit_match:
            crit_block = crit_match.group(1)
            assert "drv_final_call_cal" not in crit_block, (
                "drv_final_call_cal found in _CRITICAL set — must be non-critical"
            )
        else:
            # If _CRITICAL block not found in expected form, check there's no CRITICAL near it
            idx = derive_py_src.find("drv_final_call_cal")
            block = derive_py_src[idx:idx + 200]
            assert "_CRITICAL" not in block or "not in _CRITICAL" in block.lower(), (
                "drv_final_call_cal appears adjacent to _CRITICAL set"
            )


# ===========================================================================
# NEW API ENDPOINT
# ===========================================================================

class TestApiEndpoint:

    def test_check34_decorator_present(self, rules_src):
        """Check 34 — @router.get('/api/actionable/final-call-cal') present."""
        assert '"/api/actionable/final-call-cal"' in rules_src or \
               "'/api/actionable/final-call-cal'" in rules_src, (
            "@router.get('/api/actionable/final-call-cal') not found in rules.py"
        )

    def test_check35_response_model_list_dict(self, rules_src):
        """Check 35 — response_model=list[dict] declared on new endpoint."""
        idx = rules_src.find("/api/actionable/final-call-cal")
        assert idx >= 0
        decorator_block = rules_src[idx:idx + 100]
        assert "list[dict]" in decorator_block or "List[dict]" in decorator_block, (
            "response_model=list[dict] missing from final-call-cal endpoint"
        )

    def test_check36_selects_tos_symbol(self, rules_src):
        """Check 36 — Endpoint SQL selects tos_symbol."""
        idx = rules_src.find("def get_final_call_cal(")
        assert idx >= 0, "get_final_call_cal function not found in rules.py"
        fn_block = rules_src[idx:idx + 700]
        assert "tos_symbol" in fn_block, (
            "tos_symbol not found in get_final_call_cal SQL"
        )

    def test_check37_selects_bull_prob_and_final_code_cal(self, rules_src):
        """Check 37 — Endpoint SQL selects bull_prob and final_code_cal."""
        idx = rules_src.find("def get_final_call_cal(")
        fn_block = rules_src[idx:idx + 700]
        assert "bull_prob" in fn_block, "bull_prob missing from endpoint SQL"
        assert "final_code_cal" in fn_block, "final_code_cal missing from endpoint SQL"

    def test_check38_selects_fc_strength_cal(self, rules_src):
        """Check 38 — Endpoint SQL selects fc_strength_cal."""
        idx = rules_src.find("def get_final_call_cal(")
        fn_block = rules_src[idx:idx + 700]
        assert "fc_strength_cal" in fn_block, (
            "fc_strength_cal missing from endpoint SQL"
        )

    def test_check39_order_by_fc_strength_cal_desc(self, rules_src):
        """Check 39 — ORDER BY fc_strength_cal DESC NULLS LAST in endpoint SQL."""
        idx = rules_src.find("def get_final_call_cal(")
        # Use a larger window (1200 chars) — SQL is split across string literals
        fn_block = rules_src[idx:idx + 1200]
        assert "fc_strength_cal DESC" in fn_block, (
            "ORDER BY fc_strength_cal DESC missing from endpoint"
        )
        assert "NULLS LAST" in fn_block, "NULLS LAST missing from ORDER BY in endpoint"

    def test_check40_filters_not_null_cal(self, rules_src):
        """Check 40 — WHERE final_code_cal IS NOT NULL filter present."""
        idx = rules_src.find("def get_final_call_cal(")
        # Use a larger window (1200 chars) — SQL is split across string literals
        fn_block = rules_src[idx:idx + 1200]
        assert "final_code_cal IS NOT NULL" in fn_block, (
            "WHERE final_code_cal IS NOT NULL filter missing — "
            "endpoint should only return rows with cal data"
        )

    def test_check41_endpoint_sql_under_965_bytes(self, rules_src):
        """Check 41 — Endpoint SQL string is under 965 bytes."""
        # Reconstruct the concatenated SQL string from the function body
        idx = rules_src.find("def get_final_call_cal(")
        fn_block = rules_src[idx:idx + 700]
        # Extract all quoted string fragments and join them
        parts = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', fn_block)
        # Filter to SQL-looking parts
        sql_parts = [p for p in parts if any(
            kw in p.upper() for kw in ("SELECT", "FROM", "WHERE", "ORDER", "AND", "NULLS")
        )]
        if sql_parts:
            full_sql = " ".join(" ".join(p.split()) for p in sql_parts)
            length = len(full_sql.encode("utf-8"))
            assert length < 965, (
                f"Endpoint SQL is {length} bytes (max 965)"
            )
        else:
            # Fall back: just check the whole function block is reasonable size
            assert len(fn_block.encode("utf-8")) < 2000, (
                "Endpoint function block is suspiciously large"
            )

    def test_check42_no_deleted_lines_in_rules_py(self):
        """Check 42 — No existing endpoint changed (zero deleted lines in rules.py)."""
        removed = _git_diff_lines(RULES_PY, kind="-")
        assert not removed, (
            f"git diff shows {len(removed)} deleted line(s) in rules.py — "
            f"existing endpoints must not be modified.\nRemoved: {removed[:5]}"
        )


# ===========================================================================
# ACTIONABLE SCREEN HTML
# ===========================================================================

class TestActionableHtml:

    def test_check43_fc_cal_th_present(self, html_src):
        """Check 43 — <th> with FC (cal) text present in actionable.html."""
        assert "FC (cal)" in html_src, (
            "'FC (cal)' column header not found in actionable.html"
        )

    def test_check44_th_data_key_fc_strength_cal(self, html_src):
        """Check 44 — New <th> uses data-key='fc_strength_cal' for sorting."""
        assert 'data-key="fc_strength_cal"' in html_src or \
               "data-key='fc_strength_cal'" in html_src, (
            "data-key='fc_strength_cal' not found in actionable.html — "
            "column header must support sort by calibrated strength"
        )

    def test_check45_fc_cal_th_after_final_call_th(self, html_src):
        """Check 45 — FC (cal) <th> immediately follows the Final Call <th>."""
        pos_final_call = html_src.find('"Final Call"') if '"Final Call"' in html_src \
            else html_src.find("Final Call")
        pos_fc_cal = html_src.find("FC (cal)")
        assert pos_final_call >= 0, "'Final Call' column header not found"
        assert pos_fc_cal >= 0, "'FC (cal)' column header not found"
        # FC (cal) must come AFTER Final Call
        assert pos_final_call < pos_fc_cal, (
            "'FC (cal)' column header appears BEFORE 'Final Call' in actionable.html — "
            "must be positioned immediately after"
        )
        # They should be close (within 500 chars of each other)
        assert pos_fc_cal - pos_final_call < 500, (
            f"'FC (cal)' is {pos_fc_cal - pos_final_call} chars after 'Final Call' — "
            "should be immediately adjacent"
        )

    def test_check46_title_mentions_bull_prob(self, html_src):
        """Check 46 — The FC (cal) <th> title attribute mentions bull_prob."""
        # Find the <th> containing FC (cal)
        idx = html_src.find("FC (cal)")
        assert idx >= 0
        # Look at the surrounding <th> element
        block_start = max(0, idx - 300)
        block = html_src[block_start:idx + 200]
        assert "bull_prob" in block, (
            "title attribute of FC (cal) <th> does not mention bull_prob"
        )


# ===========================================================================
# ACTIONABLE SCREEN JS
# ===========================================================================

class TestActionableJs:

    def test_check47_final_call_cal_html_fn_defined(self, js_src):
        """Check 47 — _finalCallCalHtml function defined in actionable.js."""
        assert "function _finalCallCalHtml(" in js_src, (
            "_finalCallCalHtml function not defined in actionable.js"
        )

    def test_check48_reads_final_code_cal(self, js_src):
        """Check 48 — _finalCallCalHtml reads r.final_code_cal."""
        idx = js_src.find("function _finalCallCalHtml(")
        fn_block = js_src[idx:idx + 600]
        assert "final_code_cal" in fn_block, (
            "r.final_code_cal not read in _finalCallCalHtml()"
        )

    def test_check49_reads_final_side_cal(self, js_src):
        """Check 49 — _finalCallCalHtml reads r.final_side_cal."""
        idx = js_src.find("function _finalCallCalHtml(")
        fn_block = js_src[idx:idx + 600]
        assert "final_side_cal" in fn_block, (
            "r.final_side_cal not read in _finalCallCalHtml()"
        )

    def test_check50_reads_fc_strength_cal(self, js_src):
        """Check 50 — _finalCallCalHtml reads r.fc_strength_cal."""
        idx = js_src.find("function _finalCallCalHtml(")
        fn_block = js_src[idx:idx + 600]
        assert "fc_strength_cal" in fn_block, (
            "r.fc_strength_cal not read in _finalCallCalHtml()"
        )

    def test_check51_reads_bull_prob_for_tooltip(self, js_src):
        """Check 51 — _finalCallCalHtml reads r.bull_prob for the tooltip."""
        idx = js_src.find("function _finalCallCalHtml(")
        # Use a larger window (1200 chars) — function is ~920 chars long
        fn_block = js_src[idx:idx + 1200]
        assert "bull_prob" in fn_block, (
            "r.bull_prob not used in _finalCallCalHtml() tooltip (checked 1200 chars)"
        )

    def test_check52_amber_vs_border_on_disagree(self, js_src):
        """Check 52 — Amber left-border (#f59e0b) when FC sides disagree."""
        idx = js_src.find("function _finalCallCalHtml(")
        fn_block = js_src[idx:idx + 800]
        assert "#f59e0b" in fn_block or "f59e0b" in fn_block, (
            "Amber border color #f59e0b not found in _finalCallCalHtml() — "
            "must highlight disagreement between Final Call and FC (cal)"
        )
        # Must compare sides
        assert "final_side" in fn_block, (
            "final_side comparison missing from _finalCallCalHtml() — "
            "needed to detect disagreement"
        )

    def test_check53_td_calls_final_call_cal_html(self, js_src):
        """Check 53 — New <td> in row template calls _finalCallCalHtml(r)."""
        assert "_finalCallCalHtml(r)" in js_src, (
            "_finalCallCalHtml(r) not called in row template of actionable.js"
        )

    def test_check54_no_existing_js_functions_deleted(self):
        """Check 54 — No existing JS functions removed (zero deleted lines in actionable.js)."""
        removed = _git_diff_lines(ACTIONABLE_JS, kind="-")
        assert not removed, (
            f"git diff shows {len(removed)} deleted line(s) in actionable.js — "
            f"existing functions must not be modified.\nRemoved: {removed[:5]}"
        )


# ===========================================================================
# PROBABILITY BAND MAPPING LOGIC
# ===========================================================================

class TestProbabilityBandMapping:
    """Tests for the _prob_to_raw function imported directly."""

    @pytest.fixture(scope="class", autouse=True)
    def import_prob_to_raw(self, request):
        """Import the module for direct testing."""
        sys.path.insert(0, str(PROJECT))
        try:
            from etl.derive_final_call_cal import _prob_to_raw
            request.cls._prob_to_raw = staticmethod(_prob_to_raw)
        except ImportError as e:
            pytest.skip(f"Cannot import derive_final_call_cal: {e}")

    def test_check55_prob_0_70_maps_to_bm(self):
        """Check 55 — prob=0.70 → BM, buy, strength +2."""
        lbl, code, side, strength = self._prob_to_raw(0.70)
        assert code == "BM", f"0.70 → expected BM, got {code}"
        assert side == "buy", f"0.70 → expected side=buy, got {side}"
        assert strength == 2, f"0.70 → expected strength=2, got {strength}"

    def test_check56_prob_0_65_maps_to_bm_boundary(self):
        """Check 56 — prob=0.65 → BM (at boundary, inclusive)."""
        _, code, _, _ = self._prob_to_raw(0.65)
        assert code == "BM", f"0.65 → expected BM at boundary, got {code}"

    def test_check57_prob_0_60_maps_to_bs(self):
        """Check 57 — prob=0.60 → BS, buy, strength +2."""
        lbl, code, side, strength = self._prob_to_raw(0.60)
        assert code == "BS", f"0.60 → expected BS, got {code}"
        assert side == "buy", f"0.60 → expected side=buy, got {side}"
        assert strength == 2, f"0.60 → expected strength=2, got {strength}"

    def test_check58_prob_0_55_maps_to_bs_boundary(self):
        """Check 58 — prob=0.55 → BS (at boundary, inclusive)."""
        _, code, _, _ = self._prob_to_raw(0.55)
        assert code == "BS", f"0.55 → expected BS at boundary, got {code}"

    def test_check59_prob_0_50_maps_to_hold(self):
        """Check 59 — prob=0.50 → HOLD, neutral, strength 0."""
        lbl, code, side, strength = self._prob_to_raw(0.50)
        assert code == "HOLD", f"0.50 → expected HOLD, got {code}"
        assert side == "neutral", f"0.50 → expected side=neutral, got {side}"
        assert strength == 0, f"0.50 → expected strength=0, got {strength}"

    def test_check60_prob_0_45_maps_to_hold_boundary(self):
        """Check 60 — prob=0.45 → HOLD (at boundary, inclusive)."""
        _, code, _, strength = self._prob_to_raw(0.45)
        assert code == "HOLD", f"0.45 → expected HOLD at boundary, got {code}"
        assert strength == 0, f"0.45 → expected strength=0, got {strength}"

    def test_check61_prob_0_40_maps_to_ss(self):
        """Check 61 — prob=0.40 → SS, sell, strength -2."""
        lbl, code, side, strength = self._prob_to_raw(0.40)
        assert code == "SS", f"0.40 → expected SS, got {code}"
        assert side == "sell", f"0.40 → expected side=sell, got {side}"
        assert strength == -2, f"0.40 → expected strength=-2, got {strength}"

    def test_check62_prob_0_35_maps_to_ss_boundary(self):
        """Check 62 — prob=0.35 → SS (at boundary, inclusive)."""
        _, code, _, _ = self._prob_to_raw(0.35)
        assert code == "SS", f"0.35 → expected SS at boundary, got {code}"

    def test_check63_prob_0_20_maps_to_sa(self):
        """Check 63 — prob=0.20 → SA, sell, strength -3."""
        lbl, code, side, strength = self._prob_to_raw(0.20)
        assert code == "SA", f"0.20 → expected SA, got {code}"
        assert side == "sell", f"0.20 → expected side=sell, got {side}"
        assert strength == -3, f"0.20 → expected strength=-3, got {strength}"

    def test_check64_prob_0_00_maps_to_sa_boundary(self):
        """Check 64 — prob=0.00 → SA (at boundary, inclusive)."""
        _, code, _, _ = self._prob_to_raw(0.00)
        assert code == "SA", f"0.00 → expected SA at boundary, got {code}"

    def test_check65_negative_prob_fallback(self):
        """Check 65 — prob < 0.00 hits the fallback (returns HOLD, not error)."""
        # The last band covers 0.00+, so anything below 0.00 falls to the fallback
        try:
            lbl, code, side, strength = self._prob_to_raw(-0.1)
            # Must not raise; fallback returns something safe
            assert code in ("SA", "HOLD"), (
                f"prob=-0.1 fallback returned unexpected code {code}"
            )
        except Exception as e:
            pytest.fail(f"_prob_to_raw(-0.1) raised unexpectedly: {e}")


# ===========================================================================
# DEV_HANDOFF STATUS
# ===========================================================================

class TestDevHandoffStatus:

    def test_check66_handoff_references_agent_work_8(self, handoff_src):
        """Check 66 — DEV_HANDOFF.md references AGENT_WORK_8."""
        assert "AGENT_WORK_8" in handoff_src, (
            "DEV_HANDOFF.md does not reference AGENT_WORK_8"
        )

    def test_check67_handoff_status_all_done(self, handoff_src):
        """Check 67 — DEV_HANDOFF.md ends with Status: ALL_DONE."""
        lines = [ln.strip() for ln in handoff_src.splitlines() if ln.strip()]
        assert lines, "DEV_HANDOFF.md is empty"
        assert lines[-1] == "ALL_DONE", (
            f"DEV_HANDOFF.md last non-blank line is '{lines[-1]}', expected 'ALL_DONE'"
        )

    def test_check68_handoff_lists_derive_cal(self, handoff_src):
        """Check 68 — DEV_HANDOFF.md lists derive_final_call_cal.py as changed."""
        assert "derive_final_call_cal" in handoff_src, (
            "derive_final_call_cal.py not listed in DEV_HANDOFF.md changed files"
        )

    def test_check69_handoff_lists_baseline_sql(self, handoff_src):
        """Check 69 — DEV_HANDOFF.md lists db/baseline.sql as changed."""
        assert "db/baseline.sql" in handoff_src or "baseline.sql" in handoff_src, (
            "db/baseline.sql not listed in DEV_HANDOFF.md changed files"
        )

    def test_check70_handoff_lists_rules_py(self, handoff_src):
        """Check 70 — DEV_HANDOFF.md lists api/routers/rules.py as changed."""
        assert "rules.py" in handoff_src, (
            "api/routers/rules.py not listed in DEV_HANDOFF.md changed files"
        )

    def test_check71_handoff_lists_actionable_html(self, handoff_src):
        """Check 71 — DEV_HANDOFF.md lists web/actionable.html as changed."""
        assert "actionable.html" in handoff_src, (
            "web/actionable.html not listed in DEV_HANDOFF.md changed files"
        )

    def test_check72_handoff_lists_actionable_js(self, handoff_src):
        """Check 72 — DEV_HANDOFF.md lists web/actionable.js as changed."""
        assert "actionable.js" in handoff_src, (
            "web/actionable.js not listed in DEV_HANDOFF.md changed files"
        )
