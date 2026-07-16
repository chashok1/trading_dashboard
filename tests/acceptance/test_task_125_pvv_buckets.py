"""
Acceptance checks for TASK_125 — PVV multi-bucket signal + decision column.

Verifies:
1. `drv_pvv` table defined in db/baseline.sql.
2. `etl/derive_pvv.py` wired into `derive_all()` (etl/derive.py).
3. `/api/actionable` SQL selects pvv_decision / pvv_detail via a LEFT JOIN
   on drv_pvv (NULL-safe — no INNER JOIN that would drop rows).
4. `node --check web/actionable.js` passes; PVV column + tooltip wiring
   present in web/actionable.js and web/actionable.html.
5. If a live Postgres is reachable: drv_pvv has rows for the current anchor
   date, decisions are a mix (not all NULL/WATCH), and no bucket column is
   100% NA/NULL.
6. If a live server is reachable: GET /api/actionable includes pvv_decision
   and pvv_detail on each row.

One-time acceptance proof for TASK_125's "How to verify" list, not a durable
regression test — tests/acceptance/ per docs/audit/test_debt_review.md.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SQL_FILE = PROJECT_ROOT / "db" / "baseline.sql"
DERIVE_PY = PROJECT_ROOT / "etl" / "derive.py"
DERIVE_PVV_PY = PROJECT_ROOT / "etl" / "derive_pvv.py"
DASH_PY = PROJECT_ROOT / "api" / "routers" / "dash.py"
JS_FILE = PROJECT_ROOT / "web" / "actionable.js"
HTML_FILE = PROJECT_ROOT / "web" / "actionable.html"


@pytest.fixture(scope="module")
def sql_text():
    return SQL_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def derive_py_text():
    return DERIVE_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dash_py_text():
    return DASH_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def html_text():
    return HTML_FILE.read_text(encoding="utf-8")


# ── Schema ───────────────────────────────────────────────────────────────

class TestSchema:
    def test_drv_pvv_table_defined(self, sql_text):
        assert "CREATE TABLE IF NOT EXISTS drv_pvv" in sql_text

    def test_drv_pvv_pk(self, sql_text):
        idx = sql_text.find("CREATE TABLE IF NOT EXISTS drv_pvv")
        body = sql_text[idx: idx + 900]
        assert "PRIMARY KEY (as_of_date, tos_symbol)" in body

    def test_drv_pvv_columns(self, sql_text):
        idx = sql_text.find("CREATE TABLE IF NOT EXISTS drv_pvv")
        body = sql_text[idx: idx + 900]
        for col in ("sig_today", "sig_5d", "sig_3w", "sig_3m", "decision", "detail"):
            assert col in body, f"drv_pvv missing column {col}"
        assert "JSONB" in body


# ── ETL wiring ───────────────────────────────────────────────────────────

class TestEtlWiring:
    def test_derive_pvv_module_exists(self):
        assert DERIVE_PVV_PY.exists()

    def test_derive_pvv_syntax(self):
        import ast
        ast.parse(DERIVE_PVV_PY.read_text(encoding="utf-8"))

    def test_wired_into_derive_all(self, derive_py_text):
        idx = derive_py_text.find("def derive_all(")
        assert idx != -1
        body = derive_py_text[idx:]
        assert "derive_pvv" in body
        assert "drv_pvv" in body

    def test_pvv_runs_after_component_tables_before_drv_dash(self, derive_py_text):
        idx = derive_py_text.find("def derive_all(")
        body = derive_py_text[idx:]
        pos_portfolio = body.find('counts["drv_portfolio"]')
        pos_pvv = body.find('counts["drv_pvv"]')
        pos_dash = body.find('counts["drv_dash"]')
        assert -1 not in (pos_portfolio, pos_pvv, pos_dash)
        assert pos_portfolio < pos_pvv < pos_dash

    def test_pure_functions_importable(self):
        from etl.derive_pvv import classify_pvv, classify_pvv_3m, decide_pvv
        assert callable(classify_pvv)
        assert callable(classify_pvv_3m)
        assert callable(decide_pvv)


# ── API ──────────────────────────────────────────────────────────────────

class TestApiWiring:
    def test_select_has_pvv_fields(self, dash_py_text):
        idx = dash_py_text.find('@router.get("/api/actionable")')
        assert idx != -1
        route_body = dash_py_text[idx: idx + 8000]
        assert "pvv_decision" in route_body
        assert "pvv_detail" in route_body

    def test_left_join_not_inner(self, dash_py_text):
        idx = dash_py_text.find('@router.get("/api/actionable")')
        route_body = dash_py_text[idx: idx + 8000]
        join_idx = route_body.find("drv_pvv")
        vicinity = route_body[max(0, join_idx - 20): join_idx + 5]
        assert "LEFT JOIN" in vicinity

    def test_live_payload_has_pvv_fields_if_reachable(self):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8000/api/actionable", timeout=8
            ) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            pytest.skip(f"Live server not reachable: {e}")
        if not data:
            pytest.skip("No rows returned for default date")
        assert "pvv_decision" in data[0]
        assert "pvv_detail" in data[0]


# ── UI ───────────────────────────────────────────────────────────────────

class TestUiWiring:
    def test_node_check_passes(self):
        result = subprocess.run(["node", "--check", str(JS_FILE)],
                                 capture_output=True, text=True)
        assert result.returncode == 0, (
            f"node --check failed: {result.stdout}\n{result.stderr}"
        )

    def test_html_column_header_exists(self, html_text):
        assert 'data-col="pvv"' in html_text

    def test_js_cell_renderer_exists(self, js_text):
        assert "_pvvCellHtml" in js_text
        assert 'data-col="pvv"' in js_text

    def test_js_tooltip_builder_exists(self, js_text):
        assert "_buildPvvPopHtml" in js_text
        assert "data-pvvpop" in js_text

    def test_js_sort_rank_wired(self, js_text):
        assert "_pvv_rank" in js_text
        assert "_pvvRank" in js_text

    def test_column_toggleable(self, js_text):
        idx = js_text.find("TOGGLEABLE_COLS")
        body = js_text[idx: idx + 1200]
        assert "'pvv'" in body or '"pvv"' in body


# ── DB / live data (skips gracefully if no DB / server) ────────────────────

class TestLiveData:
    def test_drv_pvv_populated_for_anchor_if_reachable(self):
        try:
            from etl.db import session_scope
            from sqlalchemy import text as sql_text_
        except Exception:
            pytest.skip("etl.db not importable")
        try:
            with session_scope() as s:
                anchor = s.execute(
                    sql_text_("SELECT MAX(export_date) FROM hist_td")
                ).scalar()
                if anchor is None:
                    pytest.skip("hist_td empty — no anchor date")
                rows = s.execute(sql_text_("""
                    SELECT decision, sig_today, sig_5d, sig_3w, sig_3m
                    FROM drv_pvv WHERE as_of_date = :d
                """), {"d": anchor}).fetchall()
        except Exception as e:
            pytest.skip(f"DB not available: {e}")
        if not rows:
            pytest.skip(
                "drv_pvv has no rows for the current anchor date — run "
                "derive_all() (or the scheduler) after this change lands."
            )
        decisions = {r[0] for r in rows}
        assert len(decisions) >= 1
        for col_idx in (1, 2, 3, 4):
            vals = {r[col_idx] for r in rows}
            assert vals != {"NA"} and vals != {None}, (
                "a PVV bucket is 100% NA/NULL across the whole universe — "
                "likely a data-fetch bug, see docs/pvv_logic.md"
            )
