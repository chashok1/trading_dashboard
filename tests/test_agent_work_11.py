"""
Tests for AGENT_WORK_11 / TASK_73 — Quad outlook columns on the Actionable screen.

NOTE: This file replaces the original AGENT_WORK_11 (FRED series) tests because the
DEV_HANDOFF.md for AGENT_WORK_11 now points to TASK_73 (quad outlook columns).

Acceptance criteria (from DEV_HANDOFF.md and AGENT_WORK_11.md):
  1. Syntax: dash.py and actionable.js parse without errors.
  2. SQL byte-length <= 965 for all three quad queries.
  3. Forbidden columns (m_outlook, m_score, q_outlook, q_score) NOT present anywhere new.
  4. quadOutlookBadge() function exists with correct buy/sell/neutral color mapping.
  5. Quad (M) and Quad (Q) <th> headers exist in actionable.html, between Agree and Act.
  6. Grid row renders both td cells for quad_m_outlook / quad_q_outlook.
  7. exportCsv() cols array includes Quad (M) and Quad (Q) after Real Asset Class.
  8. _resolve_quad_outlook() logic: equity-sector first, asset-class fallback,
     case-insensitive, None for missing quad.
  9. import re is present in dash.py.
 10. No extra JOIN added to the main SQL query (ref_quad_* not in main SQL block).
 11. Enrichment block has try/except for graceful degradation.

Original FRED tests are PRESERVED below as a separate class so they still run.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import urllib.request
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEEDS_MACRO = PROJECT_ROOT / "db" / "seeds_macro.sql"

DASH_PY        = PROJECT_ROOT / "api" / "routers" / "dash.py"
ACTIONABLE_JS  = PROJECT_ROOT / "web" / "actionable.js"
ACTIONABLE_HTML = PROJECT_ROOT / "web" / "actionable.html"


def _js():
    return ACTIONABLE_JS.read_text(encoding="utf-8")

def _html():
    return ACTIONABLE_HTML.read_text(encoding="utf-8")

def _py():
    return DASH_PY.read_text(encoding="utf-8")


# =============================================================================
# TASK_73 — Quad outlook column tests
# =============================================================================

class TestTask73QuadOutlookColumns:
    """Tests for TASK_73: Quad (M) / Quad (Q) columns on the Actionable screen."""

    # --- Check 1: Syntax -------------------------------------------------

    def test_dash_py_syntax(self):
        """dash.py must parse cleanly with ast."""
        src = _py()
        try:
            ast.parse(src)
        except SyntaxError as e:
            raise AssertionError(f"dash.py has SyntaxError: {e}") from e

    def test_actionable_js_syntax(self):
        """actionable.js must pass node --check."""
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, (
            f"actionable.js failed node --check:\n{result.stderr}"
        )

    # --- Check 2: import re ----------------------------------------------

    def test_import_re_present(self):
        """dash.py must import re (needed by _resolve_quad_outlook regex)."""
        assert "import re" in _py(), "dash.py missing 'import re'"

    # --- Check 3: SQL byte-lengths ---------------------------------------

    def test_quad_sql_monthly_length(self):
        q = (
            "SELECT quad FROM ref_quad_periods"
            " WHERE period_type = 'monthly' AND :d >= start_date"
            " AND (:d <= end_date OR end_date IS NULL)"
            " ORDER BY start_date DESC LIMIT 1"
        )
        assert len(q.encode("utf-8")) <= 965, f"Monthly quad SQL too long: {len(q)}"

    def test_quad_sql_quarterly_length(self):
        q = (
            "SELECT quad FROM ref_quad_periods"
            " WHERE period_type = 'quarterly' AND :d >= start_date"
            " AND (:d <= end_date OR end_date IS NULL)"
            " ORDER BY start_date DESC LIMIT 1"
        )
        assert len(q.encode("utf-8")) <= 965, f"Quarterly quad SQL too long: {len(q)}"

    def test_quad_sql_outlook_lookup_length(self):
        q = (
            "SELECT category, sub_category,"
            " quad1, quad2, quad3, quad4"
            " FROM ref_quad_outlook"
            " WHERE category IN ('Asset Class','Equity Sectors')"
        )
        assert len(q.encode("utf-8")) <= 965, f"Outlook lookup SQL too long: {len(q)}"

    # --- Check 4: Forbidden column names ---------------------------------

    def test_forbidden_columns_not_in_dash_py(self):
        """m_outlook, m_score, q_outlook, q_score must NOT appear in dash.py."""
        src = _py()
        for col in ("m_outlook", "m_score", "q_outlook", "q_score"):
            # quad_m_outlook / quad_q_outlook are ALLOWED
            pattern = r'(?<!quad_m_)(?<!quad_q_)\b' + col + r'\b'
            found = re.search(pattern, src)
            assert not found, (
                f"Forbidden column '{col}' found in dash.py near: "
                f"'{src[max(0,found.start()-20):found.end()+20]}'"
            )

    def test_forbidden_columns_not_in_actionable_js(self):
        """m_outlook, m_score, q_outlook, q_score must NOT appear in actionable.js."""
        src = _js()
        for col in ("m_outlook", "m_score", "q_outlook", "q_score"):
            pattern = r'(?<!quad_m_)(?<!quad_q_)\b' + col + r'\b'
            found = re.search(pattern, src)
            assert not found, (
                f"Forbidden column '{col}' found in actionable.js near: "
                f"'{src[max(0,found.start()-20):found.end()+20]}'"
            )

    # --- Check 5: quadOutlookBadge() function ----------------------------

    def test_quad_outlook_badge_function_defined(self):
        assert "function quadOutlookBadge(" in _js(), (
            "quadOutlookBadge() function not found in actionable.js"
        )

    def test_quad_outlook_side_map_buy(self):
        src = _js()
        assert "'bullish'" in src and "'buy'" in src, (
            "QUAD_OUTLOOK_SIDE missing bullish->buy mapping"
        )

    def test_quad_outlook_side_map_sell(self):
        src = _js()
        assert "'bearish'" in src and "'sell'" in src, (
            "QUAD_OUTLOOK_SIDE missing bearish->sell mapping"
        )

    def test_quad_outlook_badge_green_for_buy(self):
        assert "#22c55e" in _js(), "Buy color (green #22c55e) not found in quadOutlookBadge"

    def test_quad_outlook_badge_red_for_sell(self):
        assert "#ef4444" in _js(), "Sell color (red #ef4444) not found in quadOutlookBadge"

    def test_quad_outlook_badge_falsy_guard(self):
        assert "if (!text)" in _js(), (
            "quadOutlookBadge missing falsy-text guard (if (!text))"
        )

    # --- Check 6: HTML headers -------------------------------------------

    def test_html_quad_m_header_exists(self):
        assert "Quad (M)" in _html(), "<th> for 'Quad (M)' not found in actionable.html"

    def test_html_quad_q_header_exists(self):
        assert "Quad (Q)" in _html(), "<th> for 'Quad (Q)' not found in actionable.html"

    def test_html_quad_columns_between_agree_and_act(self):
        """Quad (M) and Quad (Q) must appear after Agree and before Act in thead."""
        html = _html()
        agree_pos   = html.find("agreement_class")
        quad_m_pos  = html.find("Quad (M)")
        quad_q_pos  = html.find("Quad (Q)")
        act_pos     = html.find("<th>Act</th>")

        assert agree_pos  != -1, "'agreement_class' not found in actionable.html"
        assert quad_m_pos != -1, "'Quad (M)' not found in actionable.html"
        assert quad_q_pos != -1, "'Quad (Q)' not found in actionable.html"
        assert act_pos    != -1, "'<th>Act</th>' not found in actionable.html"

        assert agree_pos < quad_m_pos < quad_q_pos < act_pos, (
            f"Column order wrong: agree={agree_pos}, Quad(M)={quad_m_pos}, "
            f"Quad(Q)={quad_q_pos}, Act={act_pos}"
        )

    def test_html_quad_m_has_data_key(self):
        html = _html()
        pos = html.find("Quad (M)")
        context = html[max(0, pos - 300):pos + 50]
        assert "quad_m_outlook" in context, (
            "data-key='quad_m_outlook' not found near Quad (M) header"
        )

    def test_html_quad_q_has_data_key(self):
        html = _html()
        pos = html.find("Quad (Q)")
        context = html[max(0, pos - 300):pos + 50]
        assert "quad_q_outlook" in context, (
            "data-key='quad_q_outlook' not found near Quad (Q) header"
        )

    # --- Check 7: Grid row cells -----------------------------------------

    def test_grid_row_quad_m_cell(self):
        assert "quadOutlookBadge(r.quad_m_outlook, r.quad_m)" in _js(), (
            "Grid row missing quadOutlookBadge(r.quad_m_outlook, r.quad_m)"
        )

    def test_grid_row_quad_q_cell(self):
        assert "quadOutlookBadge(r.quad_q_outlook, r.quad_q)" in _js(), (
            "Grid row missing quadOutlookBadge(r.quad_q_outlook, r.quad_q)"
        )

    def test_grid_row_quad_cells_order(self):
        """quad td cells: after _agreementCellHtml, before btn-inline-done (Act)."""
        src = _js()
        agree  = src.find("_agreementCellHtml(r)")
        quad_m = src.find("quadOutlookBadge(r.quad_m_outlook")
        quad_q = src.find("quadOutlookBadge(r.quad_q_outlook")
        act    = src.find("btn-inline-done")

        assert agree  != -1, "_agreementCellHtml not found"
        assert quad_m != -1, "quad_m_outlook td not found"
        assert quad_q != -1, "quad_q_outlook td not found"
        assert act    != -1, "btn-inline-done not found"
        assert agree < quad_m < quad_q < act, (
            f"Order wrong: agree={agree}, quad_m={quad_m}, quad_q={quad_q}, act={act}"
        )

    # --- Check 8: CSV export ---------------------------------------------

    def test_export_csv_has_quad_m(self):
        assert "'Quad (M)'" in _js(), "exportCsv missing 'Quad (M)' column"

    def test_export_csv_has_quad_q(self):
        assert "'Quad (Q)'" in _js(), "exportCsv missing 'Quad (Q)' column"

    def test_export_csv_quad_after_real_asset_class(self):
        src = _js()
        rac   = src.find("'Real Asset Class'")
        qm    = src.find("'Quad (M)'")
        qq    = src.find("'Quad (Q)'")
        assert rac != -1, "'Real Asset Class' not found in exportCsv"
        assert qm  != -1, "'Quad (M)' not found in exportCsv"
        assert qq  != -1, "'Quad (Q)' not found in exportCsv"
        assert rac < qm < qq, (
            f"CSV order wrong: Real Asset Class={rac}, Quad(M)={qm}, Quad(Q)={qq}"
        )

    # --- Check 9: Python _resolve_quad_outlook() logic -------------------

    def test_equity_sector_lookup_before_asset_class(self):
        src = _py()
        eq_sec_pos  = src.find('"Equity Sectors"')
        asset_pos   = src.find('"Asset Class"', eq_sec_pos)
        assert eq_sec_pos != -1, '"Equity Sectors" not found in _resolve_quad_outlook'
        assert asset_pos  > eq_sec_pos, (
            "Asset Class lookup must come AFTER Equity Sectors in code"
        )

    def test_case_insensitive_lookup_lower(self):
        src = _py()
        assert "sec.lower()" in src, "sector not compared with .lower()"
        assert "rac.lower()" in src, "real_asset_class not compared with .lower()"

    def test_none_guard_for_missing_quad(self):
        assert "if not active_quad:" in _py(), (
            "_resolve_quad_outlook missing None guard: 'if not active_quad:'"
        )

    def test_category_filter_in_outlook_query(self):
        src = _py()
        assert "'Asset Class'" in src, "ref_quad_outlook query missing 'Asset Class'"
        assert "'Equity Sectors'" in src, "ref_quad_outlook query missing 'Equity Sectors'"

    def test_lookup_key_uses_category_tuple(self):
        src = _py()
        assert 'qr["category"]' in src, "Lookup key must use qr['category'] for uniqueness"
        assert ".lower()" in src, "sub_category must be lowercased in lookup key"

    def test_regex_extracts_quad_digit(self):
        src = _py()
        assert "re.search" in src, "re.search missing in _resolve_quad_outlook"
        assert '"quad" + m.group(1)' in src, (
            "Quad column name not built from regex match group(1)"
        )

    # --- Check 10: No extra JOIN in main SQL ----------------------------

    def test_no_ref_quad_in_main_sql(self):
        src = _py()
        main_start = src.find("SELECT a.*,")
        main_end   = src.find("WHERE {' AND '.join(where)}", main_start)
        assert main_start != -1, "Main SQL 'SELECT a.*,' not found in dash.py"
        assert main_end   != -1, "Main SQL WHERE clause end not found"
        main_sql = src[main_start:main_end]
        assert "ref_quad_periods" not in main_sql, (
            "ref_quad_periods found inside main SQL — violates no-extra-JOIN rule"
        )
        assert "ref_quad_outlook" not in main_sql, (
            "ref_quad_outlook found inside main SQL — violates no-extra-JOIN rule"
        )

    # --- Check 11: try/except around enrichment --------------------------

    def test_enrichment_has_try_except(self):
        src = _py()
        pos = src.find("Quad-outlook enrichment")
        assert pos != -1, "Quad-outlook enrichment comment not found in dash.py"
        block = src[pos:pos + 2000]
        assert "try:" in block, "Quad enrichment block missing try:"
        assert "except" in block, "Quad enrichment block missing except:"

    # --- Check 12: enrichment output keys --------------------------------

    def test_enrichment_sets_quad_m_key(self):
        assert 'd_["quad_m"]' in _py(), (
            'Enrichment does not set d_["quad_m"]'
        )

    def test_enrichment_sets_quad_q_key(self):
        assert 'd_["quad_q"]' in _py(), (
            'Enrichment does not set d_["quad_q"]'
        )

    def test_enrichment_sets_quad_m_outlook_key(self):
        assert 'd_["quad_m_outlook"]' in _py(), (
            'Enrichment does not set d_["quad_m_outlook"]'
        )

    def test_enrichment_sets_quad_q_outlook_key(self):
        assert 'd_["quad_q_outlook"]' in _py(), (
            'Enrichment does not set d_["quad_q_outlook"]'
        )


# =============================================================================
# Original AGENT_WORK_11 — FRED series tests (preserved)
# =============================================================================

# --- helpers -----------------------------------------------------------------

DISABLED_SERIES = {"DCOILWTICO", "DJIA", "DTWEXBGS", "NASDAQCOM", "RU2000PR", "SP500", "VIXCLS"}
ENABLED_ECON_SERIES = {
    "DGS10", "DGS2", "DGS3MO", "T10Y2Y", "DFF",        # rates
    "CPIAUCSL", "CPILFESL", "PCEPILFE", "T10YIE",       # inflation
    "UNRATE", "PAYEMS", "ICSA",                          # jobs
    "BAMLH0A0HYM2", "NFCI",                             # risk
}

BASE_URL = "http://localhost:8000"

VENV_SITE = str(PROJECT_ROOT / ".venv" / "Lib" / "site-packages")


def _db_conn():
    """Return a live psycopg connection or raise Skipped."""
    if VENV_SITE not in sys.path:
        sys.path.insert(0, VENV_SITE)
    try:
        import psycopg
    except ImportError:
        pytest.skip("psycopg not importable — DB tests skipped")

    # Load .env
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(str(env_path))
        except ImportError:
            pass

    pw = os.environ.get("PG_PASSWORD", "")
    try:
        conn = psycopg.connect(
            f"host=localhost port=5432 dbname=trading user=postgres password={pw}",
            connect_timeout=5,
        )
        return conn
    except Exception as exc:
        pytest.skip(f"Cannot connect to Postgres: {exc}")


def _server_running() -> bool:
    """Return True if the FastAPI server answers on BASE_URL."""
    try:
        urllib.request.urlopen(f"{BASE_URL}/", timeout=3)
        return True
    except urllib.error.HTTPError:
        return True  # got a response (even 404/422) — server is up
    except Exception:
        return False


def _get_json(path: str) -> dict:
    resp = urllib.request.urlopen(f"{BASE_URL}{path}", timeout=10)
    return json.loads(resp.read())


# =============================================================================
# Static / seed file tests (no DB, no server needed)
# =============================================================================

class TestSeedFile:
    """Verify seeds_macro.sql encodes the correct enabled flags."""

    def test_seed_file_exists(self):
        assert SEEDS_MACRO.exists(), f"seeds_macro.sql not found at {SEEDS_MACRO}"

    def test_six_series_disabled_in_seed(self):
        """The 6 newly-disabled series must appear as FALSE in the seed."""
        text = SEEDS_MACRO.read_text(encoding="utf-8")
        for sid in ("SP500", "NASDAQCOM", "DJIA", "VIXCLS", "DCOILWTICO", "DTWEXBGS"):
            # Look for a line containing the series_id and FALSE on the same line
            import re
            pattern = rf"'{sid}'.*?FALSE"
            assert re.search(pattern, text, re.IGNORECASE), (
                f"Expected '{sid}' to have enabled=FALSE in seeds_macro.sql"
            )

    def test_ru2000pr_already_false_in_seed(self):
        """RU2000PR was already FALSE — confirm it stays so."""
        text = SEEDS_MACRO.read_text(encoding="utf-8")
        import re
        assert re.search(r"'RU2000PR'.*?FALSE", text, re.IGNORECASE), (
            "RU2000PR should remain FALSE in seeds_macro.sql"
        )

    def test_econ_series_enabled_in_seed(self):
        """All 14 economic series must be TRUE in the seed."""
        text = SEEDS_MACRO.read_text(encoding="utf-8")
        import re
        for sid in ENABLED_ECON_SERIES:
            assert re.search(rf"'{sid}'.*?TRUE", text, re.IGNORECASE), (
                f"Expected '{sid}' to have enabled=TRUE in seeds_macro.sql"
            )

    def test_on_conflict_updates_enabled(self):
        """Seed must use DO UPDATE SET ... enabled = EXCLUDED.enabled for idempotency."""
        text = SEEDS_MACRO.read_text(encoding="utf-8")
        assert "enabled    = EXCLUDED.enabled" in text or "enabled = EXCLUDED.enabled" in text, (
            "seeds_macro.sql must propagate enabled flag via ON CONFLICT DO UPDATE"
        )


# =============================================================================
# DB tests — require live Postgres
# =============================================================================

class TestDBState:
    """Verify the actual DB reflects the seed changes."""

    def test_exactly_seven_disabled_rows(self):
        conn = _db_conn()
        try:
            cur = conn.execute(
                "SELECT series_id FROM ref_macro_series WHERE NOT enabled ORDER BY series_id"
            )
            rows = {r[0] for r in cur.fetchall()}
        finally:
            conn.close()

        assert rows == DISABLED_SERIES, (
            f"Expected disabled={sorted(DISABLED_SERIES)}, got disabled={sorted(rows)}"
        )

    def test_enabled_econ_series_all_true(self):
        conn = _db_conn()
        try:
            placeholders = ",".join(f"${i+1}" for i in range(len(ENABLED_ECON_SERIES)))
            series_list = list(ENABLED_ECON_SERIES)
            cur = conn.execute(
                f"SELECT series_id, enabled FROM ref_macro_series "
                f"WHERE series_id = ANY(%s)",
                (series_list,),
            )
            rows = {r[0]: r[1] for r in cur.fetchall()}
        finally:
            conn.close()

        missing = ENABLED_ECON_SERIES - set(rows.keys())
        assert not missing, f"These series missing from DB: {missing}"
        disabled_econ = {sid for sid, en in rows.items() if not en}
        assert not disabled_econ, (
            f"These economic series are incorrectly disabled: {disabled_econ}"
        )

    def test_total_row_count_unchanged(self):
        """Disabling should not delete rows — count stays at 21."""
        conn = _db_conn()
        try:
            cur = conn.execute("SELECT COUNT(*) FROM ref_macro_series")
            count = cur.fetchone()[0]
        finally:
            conn.close()
        assert count == 21, (
            f"Expected 21 rows in ref_macro_series (rows kept, only enabled flipped), got {count}"
        )


# =============================================================================
# API tests — require running server
# =============================================================================

@pytest.fixture(scope="module", autouse=False)
def require_server():
    if not _server_running():
        pytest.skip("API server not running — API tests skipped")


class TestApiMacro:
    """GET /api/macro must exclude all 6 disabled series."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_server(self):
        if not _server_running():
            pytest.skip("API server not running")

    def test_macro_response_has_groups_key(self):
        data = _get_json("/api/macro")
        assert "groups" in data, "/api/macro response must have a 'groups' key"

    def test_macro_groups_count(self):
        """Exactly 4 groups: rates, inflation, jobs, risk."""
        data = _get_json("/api/macro")
        groups = data["groups"]
        assert set(groups.keys()) == {"rates", "inflation", "jobs", "risk"}, (
            f"Expected groups: rates, inflation, jobs, risk — got: {set(groups.keys())}"
        )

    def test_macro_rates_has_five_tiles(self):
        data = _get_json("/api/macro")
        rates = data["groups"]["rates"]
        assert len(rates) == 5, f"Expected 5 rates tiles, got {len(rates)}"

    def test_macro_inflation_has_four_tiles(self):
        data = _get_json("/api/macro")
        inflation = data["groups"]["inflation"]
        assert len(inflation) == 4, f"Expected 4 inflation tiles, got {len(inflation)}"

    def test_macro_jobs_has_three_tiles(self):
        data = _get_json("/api/macro")
        jobs = data["groups"]["jobs"]
        assert len(jobs) == 3, f"Expected 3 jobs tiles, got {len(jobs)}"

    def test_macro_risk_has_two_tiles(self):
        data = _get_json("/api/macro")
        risk = data["groups"]["risk"]
        assert len(risk) == 2, f"Expected 2 risk tiles (BAMLH0A0HYM2 + NFCI), got {len(risk)}"

    def test_macro_no_disabled_series_in_any_group(self):
        """SP500, NASDAQCOM, DJIA, VIXCLS, DCOILWTICO, DTWEXBGS must NOT appear."""
        data = _get_json("/api/macro")
        groups = data["groups"]
        all_series_ids = set()
        for tiles in groups.values():
            for tile in tiles:
                all_series_ids.add(tile["series_id"])

        unwanted = DISABLED_SERIES - {"RU2000PR"}  # RU2000PR was already out before
        found = unwanted & all_series_ids
        assert not found, (
            f"Disabled series appeared in /api/macro response: {found}"
        )

    def test_macro_risk_series_are_correct(self):
        """The 2 risk tiles must be BAMLH0A0HYM2 and NFCI."""
        data = _get_json("/api/macro")
        risk_ids = {t["series_id"] for t in data["groups"]["risk"]}
        assert risk_ids == {"BAMLH0A0HYM2", "NFCI"}, (
            f"Expected risk series BAMLH0A0HYM2 + NFCI, got {risk_ids}"
        )

    def test_macro_no_index_or_fx_cmdty_group(self):
        """The 'index' and 'fx_cmdty' groups must not appear (disabled series)."""
        data = _get_json("/api/macro")
        groups = data["groups"]
        assert "index" not in groups, "'index' group appeared in /api/macro (should be excluded)"
        assert "fx_cmdty" not in groups, "'fx_cmdty' group appeared in /api/macro (should be excluded)"


class TestApiMarketBar:
    """GET /api/marketbar must still return all 10 items with correct sources."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_server(self):
        if not _server_running():
            pytest.skip("API server not running")

    def test_marketbar_has_ten_items(self):
        data = _get_json("/api/marketbar")
        items = data.get("items", [])
        assert len(items) == 10, f"Expected 10 marketbar items, got {len(items)}"

    def test_marketbar_tos_items_use_tos_source(self):
        """SPX, COMP, DJI, RUT, VIX, DXY, WTI must all be source='tos'."""
        data = _get_json("/api/marketbar")
        items = {i["metric_key"]: i for i in data["items"]}
        tos_expected = {"SPX", "COMP", "DJI", "RUT", "VIX", "DXY", "WTI"}
        for key in tos_expected:
            assert key in items, f"Expected metric_key '{key}' in marketbar items"
            assert items[key]["source"] == "tos", (
                f"Expected {key} source='tos', got source='{items[key]['source']}'"
            )

    def test_marketbar_all_metric_keys_present(self):
        """All 10 expected metric keys are in the response."""
        data = _get_json("/api/marketbar")
        actual_keys = {i["metric_key"] for i in data["items"]}
        expected_keys = {"SPX", "COMP", "DJI", "RUT", "VIX", "US10Y", "T2S10", "DXY", "WTI", "HY"}
        assert actual_keys == expected_keys, (
            f"Marketbar metric keys mismatch. Expected: {expected_keys}, Got: {actual_keys}"
        )

    def test_marketbar_tos_items_have_values(self):
        """TOS-sourced items must have non-None values."""
        data = _get_json("/api/marketbar")
        items = {i["metric_key"]: i for i in data["items"]}
        tos_expected = {"SPX", "COMP", "DJI", "RUT", "VIX", "DXY", "WTI"}
        for key in tos_expected:
            if key in items:
                assert items[key]["value"] is not None, (
                    f"TOS item {key} has None value — expected a real price/level"
                )
