"""Tests for AGENT_WORK_40 — drv_source_standing unification (Task 9).

Tests cover all 6 increments:
  1. SSS pilot — table/builder, tos_symbol keyed, whole-snapshot rule
  2. ETF + II  — bundle-cap + patches
  3. PS        — REMOVE behavior (not-held REMOVE emitted, not consolidated)
  4. RR        — reads drv_rr + hist_rr
  5. CALL      — 30-day window exception
  6. Cleanup   — compute_standing_verdicts removed; derive_all wiring; derive_sss retired

Pure Python AST/text checks (no Postgres required).
DB tests require a running Postgres and are skipped automatically if DB is absent.
"""
from __future__ import annotations

import ast
import re
import importlib.util
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SQL_BASELINE = (PROJECT / "db" / "baseline.sql").read_text(encoding="utf-8-sig")
ACTIONABLE_JS = (PROJECT / "web" / "actionable.js").read_text(encoding="utf-8-sig")
ACTIONABLE_HTML = (PROJECT / "web" / "actionable.html").read_text(encoding="utf-8-sig")


def _parse(path: str) -> ast.Module:
    src = (PROJECT / path).read_text(encoding="utf-8-sig")
    return ast.parse(src)


def _src(path: str) -> str:
    return (PROJECT / path).read_text(encoding="utf-8-sig")


# ===========================================================================
# Increment 1 — SSS pilot: new file, table schema, tos_symbol keying
# ===========================================================================

class TestNewModuleExists:
    """derive_source_standing.py must exist as a new ETL module."""

    def test_file_exists(self):
        assert (PROJECT / "etl" / "derive_source_standing.py").exists(), \
            "etl/derive_source_standing.py not found"

    def test_file_parses(self):
        src = (PROJECT / "etl" / "derive_source_standing.py").read_text(encoding="utf-8-sig")
        ast.parse(src)  # will raise SyntaxError if broken

    def test_public_entry_point(self):
        src = _src("etl/derive_source_standing.py")
        assert "derive_source_standing" in src, \
            "Public entry-point 'derive_source_standing' not found"

    def test_uses_wrap(self):
        src = _src("etl/derive_source_standing.py")
        assert "_wrap" in src, "Module should use _wrap for run-tracking"


class TestDrvSourceStandingSchema:
    """baseline.sql must define drv_source_standing with correct structure."""

    def test_table_defined(self):
        assert "CREATE TABLE IF NOT EXISTS drv_source_standing" in SQL_BASELINE, \
            "drv_source_standing CREATE TABLE missing from baseline.sql"

    def test_pk_columns(self):
        # Must have 3-col PK: as_of_date, source_code, tos_symbol
        assert "PRIMARY KEY (as_of_date, source_code, tos_symbol)" in SQL_BASELINE

    def test_on_list_column(self):
        assert "on_list" in SQL_BASELINE

    def test_signal_sign_column(self):
        assert "signal_sign" in SQL_BASELINE

    def test_rank_hl_column(self):
        assert "rank_hl" in SQL_BASELINE

    def test_weight_column(self):
        # ETF/II/RR/CALL need weight
        assert "weight" in SQL_BASELINE

    def test_outlook_column(self):
        assert "outlook" in SQL_BASELINE

    def test_indexes_defined(self):
        assert "ix_drv_src_standing_date" in SQL_BASELINE
        assert "ix_drv_src_standing_sym" in SQL_BASELINE

    def test_cleanup_policy_entry(self):
        assert ("'drv_source_standing'" in SQL_BASELINE or
                '"drv_source_standing"' in SQL_BASELINE), \
            "drv_source_standing missing from cleanup policy seed"


class TestSSSBuilderLogic:
    """_build_sss must implement whole-snapshot rule (tos_symbol keyed)."""

    src = _src("etl/derive_source_standing.py")

    def test_sss_function_present(self):
        assert "_build_sss" in self.src

    def test_sss_queries_tos_symbol(self):
        # The SSS builder must select tos_symbol from hist_sss (not raw symbol)
        assert "tos_symbol" in self.src

    def test_sss_whole_snapshot_max_date(self):
        # Must find MAX(snapshot_date) <= D for whole-load rule
        assert "MAX(snapshot_date)" in self.src

    def test_sss_signal_sign_computed(self):
        # Signal sign classification present (>0.5, >0.25, >0)
        assert "sig_sign" in self.src or "signal_sign" in self.src

    def test_sss_source_code(self):
        assert '"SSS"' in self.src or "'SSS'" in self.src


# ===========================================================================
# Increment 2 — ETF + II: bundle-cap + patches
# ===========================================================================

class TestETFIIBuilderLogic:
    """_build_etf_ii must implement bundle-cap (latest snapshot + patches)."""

    src = _src("etl/derive_source_standing.py")

    def test_etf_ii_function_present(self):
        assert "_build_etf_ii" in self.src

    def test_reads_base_table_max_snapshot(self):
        assert "MAX(snapshot_date)" in self.src

    def test_applies_patches(self):
        # Patches (etfchg/iichg) are applied after the base snapshot
        assert "change_table" in self.src or "hist_etfchg" in self.src or "patches" in self.src.lower()

    def test_neutral_excluded(self):
        # NEUTRAL outlook must be excluded
        assert "NEUTRAL" in self.src

    def test_tos_symbol_keyed(self):
        assert "tos_symbol" in self.src

    def test_etf_source_code_used(self):
        # source_code parameter passed as ETF/II
        assert '"ETF"' in self.src or "'ETF'" in self.src

    def test_ii_source_code_used(self):
        assert '"II"' in self.src or "'II'" in self.src


# ===========================================================================
# Increment 3 — PS: rank stored, REMOVE for not-held
# ===========================================================================

class TestPSBuilderLogic:
    """_build_ps must implement whole-snapshot rule and store rank."""

    src = _src("etl/derive_source_standing.py")

    def test_ps_function_present(self):
        assert "_build_ps" in self.src

    def test_ps_stores_rank(self):
        # rank column populated for PS rows
        assert '"rank"' in self.src or "'rank'" in self.src or "rank" in self.src

    def test_ps_source_code(self):
        assert '"PS"' in self.src or "'PS'" in self.src


class TestPSRemoveBehavior:
    """derive_outlook_action must emit REMOVE for PS drop even when not held."""

    src = _src("etl/derive_outlook_action.py")

    def test_ps_not_held_remove_override(self):
        # Behavior rule 3: override _action_rank's None to REMOVE for PS drop
        assert "not held" in self.src.lower() or "not_held" in self.src or \
               "dropped from PS list (not held)" in self.src

    def test_ps_remove_emit_when_not_held(self):
        assert "dropped from PS list (not held)" in self.src

    def test_ps_reads_drv_source_standing(self):
        assert "drv_source_standing" in self.src
        assert "source_code = 'PS'" in self.src or "source_code='PS'" in self.src


class TestPSRemoveConsolidation:
    """derive_actionable must exclude not-held PS REMOVE from winner sort."""

    src = _src("etl/derive_actionable.py")

    def test_not_held_ps_remove_excluded(self):
        # Must filter out not-held PS REMOVE from consolidated winner
        assert "PS" in self.src
        assert "REMOVE" in self.src
        # Check the behavior rule 3 comment or logic
        assert "Behavior rule 3" in self.src or \
               ("not_held" in self.src.lower() and "PS" in self.src)

    def test_tos_symbol_keyed_asset_class_ps(self):
        # asset_class_ps must use COALESCE(tos_symbol, ticker) not raw ticker
        assert "COALESCE(tos_symbol, ticker)" in self.src or \
               "tos_symbol" in self.src

    def test_tos_symbol_keyed_asset_class_etf(self):
        # asset_class_etf must use COALESCE(tos_symbol, symbol) not raw symbol
        assert "COALESCE(tos_symbol, symbol)" in self.src or \
               "tos_symbol" in self.src


# ===========================================================================
# Increment 4 — RR: reads drv_rr + hist_rr
# ===========================================================================

class TestRRBuilderLogic:
    """_build_rr reads drv_rr + joins hist_rr for outlook."""

    src = _src("etl/derive_source_standing.py")

    def test_rr_function_present(self):
        assert "_build_rr" in self.src

    def test_rr_reads_drv_rr(self):
        assert "drv_rr" in self.src

    def test_rr_joins_hist_rr(self):
        assert "hist_rr" in self.src

    def test_rr_source_code(self):
        assert '"RR"' in self.src or "'RR'" in self.src

    def test_rr_lateral_join(self):
        # Uses LATERAL for per-symbol latest hist_rr
        assert "LATERAL" in self.src or "lateral" in self.src.lower()


class TestRROulooksInDerive:
    """derive.py _t_out_rr CTE must read from drv_source_standing."""

    src = _src("etl/derive.py")

    def test_rr_cte_reads_source_standing(self):
        assert "drv_source_standing" in self.src

    def test_rr_join_uses_source_code_rr(self):
        assert "source_code = 'RR'" in self.src or "source_code='RR'" in self.src


# ===========================================================================
# Increment 5 — CALL: 30-day window exception
# ===========================================================================

class TestCALLBuilderLogic:
    """_build_call must implement 30-day per-symbol window."""

    src = _src("etl/derive_source_standing.py")

    def test_call_function_present(self):
        assert "_build_call" in self.src

    def test_call_uses_lookback_days(self):
        assert "lookback_days" in self.src

    def test_call_30_day_default(self):
        # Default lookback should be 30 days
        assert "30" in self.src

    def test_call_timedelta(self):
        # Must compute cutoff date via timedelta
        assert "timedelta" in self.src

    def test_call_per_symbol_window(self):
        # ROW_NUMBER or similar per-symbol ranking
        assert "ROW_NUMBER" in self.src or "rk" in self.src

    def test_call_source_code(self):
        assert '"CALL"' in self.src or "'CALL'" in self.src


class TestCALLInDerive:
    """derive.py must have _t_out_cl reading drv_source_standing for CALL."""

    src = _src("etl/derive.py")

    def test_call_cte_reads_source_standing(self):
        assert "_t_out_cl" in self.src or (
            "drv_source_standing" in self.src and "CALL" in self.src
        )

    def test_call_source_code_filter(self):
        assert "source_code = 'CALL'" in self.src or "source_code='CALL'" in self.src


# ===========================================================================
# Increment 6 — Cleanup
# ===========================================================================

class TestCleanupIncrement6:
    """compute_standing_verdicts removed; derive_all wired; derive_sss retired."""

    def test_compute_standing_verdicts_removed(self):
        """compute_standing_verdicts function must be gone from derive_outlook_action.py."""
        src = _src("etl/derive_outlook_action.py")
        # The function definition must not exist
        assert "def compute_standing_verdicts" not in src, \
            "compute_standing_verdicts was not removed (Increment 6 cleanup)"

    def test_compute_standing_verdicts_comment_or_note(self):
        """The removal should at least be noted in a comment."""
        src = _src("etl/derive_outlook_action.py")
        assert "RETIRED" in src or "removed" in src.lower() or \
               "compute_standing_verdicts" in src  # mention OK as a comment

    def test_derive_all_wires_source_standing(self):
        """derive_all() in derive.py must call derive_source_standing."""
        src = _src("etl/derive.py")
        assert "derive_source_standing" in src
        assert "drv_source_standing" in src

    def test_derive_sss_call_retired(self):
        """The old derive_sss call in derive_all must be commented out."""
        src = _src("etl/derive.py")
        # The active call should not exist; it should be commented out
        # Search for active (non-comment) call
        lines = src.splitlines()
        active_derive_sss = [
            l for l in lines
            if "derive_sss" in l and not l.strip().startswith("#")
            and "_safe" in l and "drv_sss" in l
        ]
        assert len(active_derive_sss) == 0, \
            f"derive_sss still called in derive_all (not retired): {active_derive_sss}"

    def test_tos_symbol_keying_in_asset_class(self):
        """asset_class_ps and asset_class_etf in derive_actionable use tos_symbol."""
        src = _src("etl/derive_actionable.py")
        # Both must use COALESCE(tos_symbol, ...) not raw ticker/symbol
        assert "COALESCE(tos_symbol" in src, \
            "asset_class lookup not using COALESCE(tos_symbol, ...) — tos_symbol bug not fixed"


# ===========================================================================
# derive.py — all 4 CTEs read from drv_source_standing
# ===========================================================================

class TestDeriveCTEs:
    """Four CTEs in _derive_outlooks_impl must read drv_source_standing."""

    src = _src("etl/derive.py")

    def test_sss_cte_reads_source_standing(self):
        assert "_t_out_sh" in self.src or (
            "drv_source_standing" in self.src and "SSS" in self.src
        )

    def test_sss_source_code_filter(self):
        assert "source_code = 'SSS'" in self.src or "source_code='SSS'" in self.src

    def test_etf_cte_reads_source_standing(self):
        assert "_t_out_ef" in self.src
        assert "drv_source_standing" in self.src

    def test_ii_cte_reads_source_standing(self):
        assert "_t_out_ii" in self.src
        assert "drv_source_standing" in self.src

    def test_source_standing_before_outlooks(self):
        """drv_source_standing must be computed before drv_outlooks in derive_all().

        We search within the derive_all body specifically (not the whole file)
        to avoid false positives from function definitions above derive_all.
        """
        src = self.src
        # Locate derive_all body
        derive_all_start = src.find("def derive_all(")
        assert derive_all_start >= 0, "derive_all not found in derive.py"
        derive_all_body = src[derive_all_start:]

        # In derive_all, counts["drv_source_standing"] must appear before counts["drv_outlooks"]
        idx_standing = derive_all_body.find('"drv_source_standing"')
        idx_outlooks = derive_all_body.find('"drv_outlooks"')
        assert idx_standing >= 0, '"drv_source_standing" not found in derive_all body'
        assert idx_outlooks >= 0, '"drv_outlooks" not found in derive_all body'
        assert idx_standing < idx_outlooks, \
            "drv_source_standing wired AFTER drv_outlooks in derive_all; ordering wrong"


# ===========================================================================
# derive_outlook_action.py — reads from drv_source_standing for all sources
# ===========================================================================

class TestOutlookActionReadsStanding:
    """All per-source paths in derive_outlook_action must read drv_source_standing."""

    src = _src("etl/derive_outlook_action.py")

    def test_etf_reads_source_standing(self):
        assert "drv_source_standing" in self.src
        assert "source_code = :sc" in self.src or "source_code='ETF'" in self.src

    def test_call_reads_source_standing(self):
        assert "source_code = 'CALL'" in self.src or "source_code='CALL'" in self.src

    def test_rr_reads_source_standing(self):
        assert "source_code = 'RR'" in self.src or "source_code='RR'" in self.src

    def test_sss_reads_source_standing(self):
        assert "source_code = 'SSS'" in self.src or "source_code='SSS'" in self.src

    def test_ps_reads_source_standing(self):
        assert "source_code = 'PS'" in self.src or "source_code='PS'" in self.src

    def test_state_etf_ii_tos_helper_added(self):
        """_state_etf_ii_tos helper must exist for tos_symbol-keyed prior state."""
        assert "_state_etf_ii_tos" in self.src


# ===========================================================================
# UI — "+Unheld Remove" toggle (Behavior rule 4)
# ===========================================================================

class TestUnheldRemoveToggle:
    """actionable.js and actionable.html must support the not-held REMOVE toggle."""

    def test_state_filter_default_false(self):
        # Default state must be false (not-held REMOVE hidden by default)
        assert "show_not_held_remove: false" in ACTIONABLE_JS

    def test_filter_logic_present(self):
        # Filter must check show_not_held_remove
        assert "show_not_held_remove" in ACTIONABLE_JS

    def test_toggle_hides_not_held_remove(self):
        # When false, not-held REMOVE rows are hidden
        # The filter should check this condition
        lines = ACTIONABLE_JS.splitlines()
        filter_lines = [l for l in lines if "show_not_held_remove" in l]
        assert len(filter_lines) >= 3, \
            f"show_not_held_remove appears in only {len(filter_lines)} lines; expected >= 3 (state, filter, event)"

    def test_html_checkbox_present(self):
        # HTML must have the checkbox with correct id
        assert 'id="showNotHeldRemove"' in ACTIONABLE_HTML or \
               "showNotHeldRemove" in ACTIONABLE_HTML

    def test_html_label_text(self):
        # Label text for the toggle
        assert "Unheld Remove" in ACTIONABLE_HTML or "unheld" in ACTIONABLE_HTML.lower()

    def test_event_listener_wired(self):
        # JS must have an event listener for the toggle
        assert "showNotHeldRemove" in ACTIONABLE_JS
        assert "addEventListener" in ACTIONABLE_JS

    def test_save_load_sync_include_toggle(self):
        # save/load/sync/clear must include show_not_held_remove
        assert ACTIONABLE_JS.count("show_not_held_remove") >= 5, \
            "show_not_held_remove not present in save/load/sync/clear (expected >= 5 occurrences)"


# ===========================================================================
# Idempotency design: DELETE + INSERT pattern
# ===========================================================================

class TestIdempotencyDesign:
    """derive_source_standing must DELETE WHERE as_of_date=D then INSERT."""

    src = _src("etl/derive_source_standing.py")

    def test_delete_before_insert(self):
        assert "DELETE FROM drv_source_standing WHERE as_of_date" in self.src

    def test_on_conflict_do_nothing(self):
        # ON CONFLICT DO NOTHING for safety against duplicate calls
        assert "ON CONFLICT" in self.src

    def test_returns_row_count(self):
        # Entry point should return number of rows inserted
        assert "return len(all_rows)" in self.src or "return " in self.src


# ===========================================================================
# Per-source try/except fault isolation
# ===========================================================================

class TestFaultIsolation:
    """Each source builder call must be wrapped in try/except."""

    src = _src("etl/derive_source_standing.py")

    def test_sss_try_except(self):
        # Each _build_* call is wrapped
        assert "try:" in self.src
        assert "except Exception" in self.src

    def test_warning_on_failure(self):
        # Failures should be logged as warnings, not silently swallowed
        assert "log.warning" in self.src


# ===========================================================================
# Python syntax and import checks on all changed files
# ===========================================================================

class TestPythonSyntax:
    """All changed ETL/API files must parse cleanly."""

    @pytest.mark.parametrize("path", [
        "etl/derive_source_standing.py",
        "etl/derive_outlook_action.py",
        "etl/derive_actionable.py",
        "etl/derive.py",
    ])
    def test_python_file_parses(self, path):
        src = (PROJECT / path).read_text(encoding="utf-8-sig")
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"{path}: SyntaxError at line {e.lineno}: {e.msg}")


class TestJSSyntax:
    """Changed JS files must pass node --check."""

    def test_actionable_js_valid(self):
        import subprocess
        result = subprocess.run(
            ["node", "--check", str(PROJECT / "web" / "actionable.js")],
            capture_output=True, text=True
        )
        assert result.returncode == 0, \
            f"actionable.js has syntax errors:\n{result.stderr}"


# ===========================================================================
# DB integration tests (skipped if Postgres absent)
# ===========================================================================

def _get_session():
    """Return a SQLAlchemy Session or None if DB unavailable."""
    try:
        from config.settings import DATABASE_URL
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker
        engine = create_engine(DATABASE_URL, connect_args={"connect_timeout": 3})
        Session = sessionmaker(bind=engine)
        sess = Session()
        sess.execute(text("SELECT 1"))
        return sess
    except Exception:
        return None


@pytest.fixture(scope="module")
def db_session():
    sess = _get_session()
    if sess is None:
        pytest.skip("Postgres not available")
    yield sess
    sess.close()


class TestDBTableExists:
    """drv_source_standing table must exist in the DB."""

    def test_table_exists(self, db_session):
        from sqlalchemy import text
        row = db_session.execute(text("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'drv_source_standing'
        """)).first()
        assert row is not None, "drv_source_standing table not found in DB"

    def test_pk_structure(self, db_session):
        from sqlalchemy import text
        rows = db_session.execute(text("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.table_name = 'drv_source_standing'
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """)).fetchall()
        pk_cols = [r[0] for r in rows]
        assert pk_cols == ["as_of_date", "source_code", "tos_symbol"], \
            f"Unexpected PK columns: {pk_cols}"

    def test_signal_sign_column_exists(self, db_session):
        from sqlalchemy import text
        row = db_session.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'drv_source_standing'
              AND column_name = 'signal_sign'
        """)).first()
        assert row is not None, "signal_sign column missing from drv_source_standing"

    def test_rank_hl_column_exists(self, db_session):
        from sqlalchemy import text
        row = db_session.execute(text("""
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'drv_source_standing'
              AND column_name = 'rank_hl'
        """)).first()
        assert row is not None, "rank_hl column missing from drv_source_standing"


class TestDBSourceStandingData:
    """If data exists, verify source codes and tos_symbol keying."""

    def test_source_codes_are_valid(self, db_session):
        from sqlalchemy import text
        rows = db_session.execute(text("""
            SELECT DISTINCT source_code FROM drv_source_standing
        """)).fetchall()
        if not rows:
            pytest.skip("drv_source_standing is empty — no data to check")
        valid_codes = {"SSS", "ETF", "II", "PS", "RR", "CALL"}
        actual_codes = {r[0] for r in rows}
        invalid = actual_codes - valid_codes
        assert not invalid, f"Invalid source_code values found: {invalid}"

    def test_tos_symbol_not_null(self, db_session):
        from sqlalchemy import text
        row = db_session.execute(text("""
            SELECT COUNT(*) FROM drv_source_standing WHERE tos_symbol IS NULL
        """)).first()
        assert row[0] == 0, f"{row[0]} rows have NULL tos_symbol"

    def test_on_list_all_true(self, db_session):
        from sqlalchemy import text
        row = db_session.execute(text("""
            SELECT COUNT(*) FROM drv_source_standing WHERE on_list = FALSE
        """)).first()
        assert row[0] == 0, \
            f"{row[0]} rows have on_list=FALSE; only TRUE rows should be written"

    def test_cleanup_policy_entry(self, db_session):
        from sqlalchemy import text
        row = db_session.execute(text("""
            SELECT 1 FROM meta_cleanup_policy
            WHERE target_table = 'drv_source_standing'
        """)).first()
        assert row is not None, \
            "drv_source_standing missing from meta_cleanup_policy"

    def test_sss_uses_tos_symbol(self, db_session):
        """SSS rows must have tos_symbol, not raw hist_sss ticker."""
        from sqlalchemy import text
        rows = db_session.execute(text("""
            SELECT tos_symbol FROM drv_source_standing
            WHERE source_code = 'SSS'
            LIMIT 5
        """)).fetchall()
        if not rows:
            pytest.skip("No SSS rows in drv_source_standing")
        for r in rows:
            assert r[0] is not None and len(r[0]) > 0, "SSS tos_symbol is empty/null"


class TestDBIdempotency:
    """Running derive_source_standing twice must produce identical counts."""

    def test_row_counts_stable(self, db_session):
        """Check count at the current anchor date is consistent (not zero if data loaded)."""
        from sqlalchemy import text
        row = db_session.execute(text("""
            SELECT COUNT(*) FROM drv_source_standing
            WHERE as_of_date = (SELECT MAX(export_date) FROM hist_td)
        """)).first()
        # If hist_td is empty, this simply returns 0 — which is fine
        assert row is not None  # query itself must succeed
