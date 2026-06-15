"""Tests for AGENT_WORK_41 — drv_sss retirement completion + byte-limit verification.

Checks:
  A1. drv_sss is absent from baseline.sql CREATE TABLE block (schema clean)
  A2. baseline.sql has a DO-block migration that DROPs drv_sss
  A3. ix_drv_sss_tos_symbol index is absent from baseline.sql
  A4. derive_v2.py has no _derive_sss_v2_impl function definition
  A5. derive_v2.py has no derive_sss = _wrap(...) line
  A6. derive.py imports only derive_tw from derive_v2 (no derive_sss)
  A7. derive.py _derive_ma_impl uses NULL::NUMERIC casts (no drv_sss JOIN)
  A8. derive.py derive_all() has no active derive_sss call
  A9. All SQL in _derive_outlooks_impl is within the 965-byte limit
  B1. DB: drv_sss table does not exist (live check)
  B2. DB: drv_source_standing has all 6 expected source codes
  B3. DB: drv_source_standing counts match expected ranges

Pure Python / AST tests run without Postgres. DB tests auto-skip if Postgres absent.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

SQL_BASELINE = (PROJECT / "db" / "baseline.sql").read_text(encoding="utf-8-sig")


def _src(path: str) -> str:
    return (PROJECT / path).read_text(encoding="utf-8-sig")


# ===========================================================================
# A. Schema / code retirement checks (pure Python, no DB required)
# ===========================================================================

class TestDrvSssRemovedFromSchema:
    """baseline.sql must not define drv_sss as a table."""

    def test_no_create_table_drv_sss(self):
        """CREATE TABLE drv_sss must be absent from baseline.sql."""
        assert "CREATE TABLE IF NOT EXISTS drv_sss" not in SQL_BASELINE, \
            "drv_sss still defined as CREATE TABLE in baseline.sql"
        assert "CREATE TABLE drv_sss" not in SQL_BASELINE, \
            "drv_sss still defined as CREATE TABLE in baseline.sql"

    def test_drop_migration_present(self):
        """A DO-block migration that drops drv_sss must be present in baseline.sql."""
        assert "DROP TABLE drv_sss CASCADE" in SQL_BASELINE or \
               "DROP TABLE IF EXISTS drv_sss" in SQL_BASELINE, \
            "Migration to DROP drv_sss not found in baseline.sql"

    def test_drop_migration_is_conditional(self):
        """The drv_sss drop must be wrapped in a table-existence check (DO block)."""
        assert "table_name = 'drv_sss'" in SQL_BASELINE, \
            "drv_sss drop migration does not check for table existence first"

    def test_ix_drv_sss_not_created(self):
        """ix_drv_sss_tos_symbol must not be created (only mentioned as retired)."""
        # The ONLY mention of the index in the file must be in a comment or retired note
        lines = SQL_BASELINE.splitlines()
        active_index_lines = [
            l for l in lines
            if "ix_drv_sss" in l
            and not l.strip().startswith("--")
            and "CREATE INDEX" in l
        ]
        assert len(active_index_lines) == 0, \
            f"ix_drv_sss index still being created: {active_index_lines}"


class TestDeriveV2SssRetired:
    """derive_v2.py must have no live _derive_sss_v2_impl or derive_sss."""

    src = _src("etl/derive_v2.py")

    def test_no_sss_function_definition(self):
        """_derive_sss_v2_impl function must not be defined."""
        assert "def _derive_sss_v2_impl" not in self.src, \
            "_derive_sss_v2_impl still defined in derive_v2.py"

    def test_no_derive_sss_wrap_line(self):
        """derive_sss = _wrap(...) assignment must not exist."""
        lines = self.src.splitlines()
        active_wrap = [
            l for l in lines
            if "derive_sss" in l
            and "_wrap" in l
            and not l.strip().startswith("#")
        ]
        assert len(active_wrap) == 0, \
            f"derive_sss = _wrap(...) still active in derive_v2.py: {active_wrap}"

    def test_file_parses(self):
        """derive_v2.py must still be valid Python after the removal."""
        try:
            ast.parse(self.src)
        except SyntaxError as e:
            pytest.fail(f"derive_v2.py SyntaxError at line {e.lineno}: {e.msg}")


class TestDerivePySssRetired:
    """derive.py must not import or call derive_sss."""

    src = _src("etl/derive.py")

    def test_import_has_no_derive_sss(self):
        """derive_sss must not appear in the import from derive_v2."""
        # Find the specific import line
        import_line = next(
            (l for l in self.src.splitlines() if "from etl.derive_v2 import" in l),
            None
        )
        assert import_line is not None, "Could not find 'from etl.derive_v2 import' in derive.py"
        assert "derive_sss" not in import_line, \
            f"derive_sss still imported from derive_v2: {import_line}"

    def test_derive_all_has_no_active_sss_call(self):
        """No active (non-comment) call to derive_sss in derive_all body."""
        # Find derive_all body
        derive_all_start = self.src.find("def derive_all(")
        assert derive_all_start >= 0
        body = self.src[derive_all_start:]
        active_calls = [
            l for l in body.splitlines()
            if "derive_sss" in l and not l.strip().startswith("#")
        ]
        assert len(active_calls) == 0, \
            f"Active derive_sss call(s) found in derive_all: {active_calls}"

    def test_dead_cte_sh_uses_null_casts(self):
        """_derive_ma_impl dead CTE 'sh' must use NULL::NUMERIC (not drv_sss JOIN)."""
        assert "NULL::NUMERIC AS SSS_signal" in self.src or \
               "NULL::NUMERIC" in self.src, \
            "Dead CTE 'sh' does not use NULL::NUMERIC casts"
        assert "LEFT JOIN drv_sss" not in self.src, \
            "_derive_ma_impl still has a JOIN on the dropped drv_sss table"

    def test_file_parses(self):
        """derive.py must still be valid Python."""
        try:
            ast.parse(self.src)
        except SyntaxError as e:
            pytest.fail(f"derive.py SyntaxError at line {e.lineno}: {e.msg}")


class TestOutlooksSQLByteLimits:
    """Every SQL statement in _derive_outlooks_impl must be <= 965 bytes."""

    src = _src("etl/derive.py")

    def _get_fn_body(self) -> str:
        fn_start = self.src.find("def _derive_outlooks_impl")
        assert fn_start >= 0, "_derive_outlooks_impl not found in derive.py"
        lines = self.src[fn_start:].splitlines()
        fn_lines = []
        for i, line in enumerate(lines):
            if i > 0 and re.match(r"^def |^class ", line):
                break
            fn_lines.append(line)
        return "\n".join(fn_lines)

    def test_all_sql_blocks_under_965_bytes(self):
        """All triple-quoted SQL strings in _derive_outlooks_impl must be <= 965 bytes."""
        fn_body = self._get_fn_body()
        sql_blocks = re.findall(r'"""(.*?)"""', fn_body, re.DOTALL)
        sql_blocks += re.findall(r"'''(.*?)'''", fn_body, re.DOTALL)

        oversized = []
        for i, blk in enumerate(sql_blocks):
            stripped = blk.strip()
            b = len(stripped.encode("utf-8"))
            if b > 965:
                oversized.append((i + 1, b, stripped[:80]))

        assert not oversized, \
            "SQL blocks exceeding 965 bytes: " + str([(i, b) for i, b, _ in oversized])

    def test_function_present(self):
        """_derive_outlooks_impl function must exist in derive.py."""
        assert "def _derive_outlooks_impl" in self.src

    def test_at_least_one_sql_block(self):
        """At least one SQL block must exist in _derive_outlooks_impl."""
        fn_body = self._get_fn_body()
        sql_blocks = re.findall(r'"""(.*?)"""', fn_body, re.DOTALL)
        sql_blocks += re.findall(r"'''(.*?)'''", fn_body, re.DOTALL)
        assert len(sql_blocks) >= 1, \
            "No triple-quoted SQL blocks found in _derive_outlooks_impl"


# ===========================================================================
# B. DB live checks (auto-skip if Postgres is absent)
# ===========================================================================

def _get_engine():
    """Return a SQLAlchemy engine or None if DB unavailable."""
    try:
        from config.settings import settings
        from sqlalchemy import create_engine, text
        eng = create_engine(settings.sqlalchemy_url, connect_args={"connect_timeout": 3})
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        return eng
    except Exception:
        return None


@pytest.fixture(scope="module")
def db_engine():
    eng = _get_engine()
    if eng is None:
        pytest.skip("Postgres not available — DB tests skipped")
    return eng


class TestDBDrvSssGone:
    """drv_sss table must not exist in the live DB."""

    def test_drv_sss_table_absent(self, db_engine):
        from sqlalchemy import text
        with db_engine.connect() as c:
            exists = c.execute(text(
                "SELECT EXISTS(SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'drv_sss')"
            )).scalar()
        assert exists is False, \
            "drv_sss table still exists in the database — retirement migration did not run"


class TestDBSourceStanding6Sources:
    """drv_source_standing must have exactly the 6 expected source codes at anchor date."""

    EXPECTED_SOURCES = {"CALL", "ETF", "II", "PS", "RR", "SSS"}

    def test_all_six_sources_present(self, db_engine):
        from sqlalchemy import text
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT source_code, COUNT(*) AS cnt "
                "FROM drv_source_standing "
                "WHERE as_of_date = (SELECT MAX(export_date) FROM hist_td) "
                "GROUP BY 1 ORDER BY 1"
            )).fetchall()

        if not rows:
            pytest.skip("drv_source_standing is empty at anchor date — no data loaded")

        actual = {r[0] for r in rows}
        missing = self.EXPECTED_SOURCES - actual
        assert not missing, \
            f"Source codes missing from drv_source_standing at anchor date: {missing}"

    def test_no_extra_sources(self, db_engine):
        from sqlalchemy import text
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT DISTINCT source_code FROM drv_source_standing "
                "WHERE as_of_date = (SELECT MAX(export_date) FROM hist_td)"
            )).fetchall()
        if not rows:
            pytest.skip("drv_source_standing is empty")
        actual = {r[0] for r in rows}
        unexpected = actual - self.EXPECTED_SOURCES
        assert not unexpected, \
            f"Unexpected source codes in drv_source_standing: {unexpected}"

    def test_source_counts_in_range(self, db_engine):
        """Each source must have a plausible row count (> 0)."""
        from sqlalchemy import text
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT source_code, COUNT(*) AS cnt "
                "FROM drv_source_standing "
                "WHERE as_of_date = (SELECT MAX(export_date) FROM hist_td) "
                "GROUP BY 1 ORDER BY 1"
            )).fetchall()
        if not rows:
            pytest.skip("drv_source_standing is empty")
        for code, cnt in rows:
            assert cnt > 0, f"source_code={code} has 0 rows in drv_source_standing"

    def test_rr_is_largest_source(self, db_engine):
        """RR is expected to be the largest source (analyst coverage is wide)."""
        from sqlalchemy import text
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT source_code, COUNT(*) AS cnt "
                "FROM drv_source_standing "
                "WHERE as_of_date = (SELECT MAX(export_date) FROM hist_td) "
                "GROUP BY 1 ORDER BY 2 DESC"
            )).fetchall()
        if not rows:
            pytest.skip("drv_source_standing is empty")
        top_source = rows[0][0]
        assert top_source == "RR", \
            f"Expected RR to be the largest source; got {top_source} with {rows[0][1]} rows"
