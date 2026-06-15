"""
Tests for AGENT_WORK_11 — disable 6 FRED series (SP500, NASDAQCOM, DJIA, VIXCLS,
DCOILWTICO, DTWEXBGS) that are duplicated by the TOS feed; only the Econ expander
should appear in /api/macro; market tape (/api/marketbar) must be unaffected.

Acceptance criteria:
  1. DB: ref_macro_series has exactly 7 disabled rows (DCOILWTICO, DJIA, DTWEXBGS,
     NASDAQCOM, RU2000PR, SP500, VIXCLS).
  2. DB: The 14 FRED-only economic series all remain enabled (rates x5, inflation x4,
     jobs x3, risk x2 — BAMLH0A0HYM2, NFCI).
  3. seeds_macro.sql: the 6 newly-disabled series are written as FALSE in the seed
     (so init_db is idempotent).
  4. API /api/macro: response contains NO tiles for SP500, NASDAQCOM, DJIA, VIXCLS,
     DCOILWTICO, DTWEXBGS in any group.
  5. API /api/macro: exactly 4 groups present — rates, inflation, jobs, risk.
  6. API /api/macro: rates=5, inflation=4, jobs=3, risk=2 tiles.
  7. API /api/marketbar: all 10 items present.
  8. API /api/marketbar: SPX, COMP, DJI, RUT, VIX, DXY, WTI items use source="tos".

DB tests auto-skip when Postgres is unreachable.
API tests auto-skip when the server is not running.
"""
from __future__ import annotations

import os
import sys
import urllib.request
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEEDS_MACRO = PROJECT_ROOT / "db" / "seeds_macro.sql"

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
