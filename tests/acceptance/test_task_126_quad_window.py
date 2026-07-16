"""
Acceptance checks for TASK_126 — MACRO sliding look-ahead window.

Verifies:
1. `drv_macro_score.detail` JSONB column defined in db/baseline.sql.
2. `etl/derive_macro.py` exposes the pure window functions and no longer
   reads the retired ramp/lead settings.
3. `/api/actionable/macro-detail` and the new `/api/quad-window` endpoints
   are wired in api/routers/dash.py.
4. `node --check web/actionable.js` passes; window tooltip/regime-band
   wiring present.
5. If a live Postgres is reachable: drv_macro_score has `detail` populated
   for the current anchor date, macro_action distribution is within a sane
   band of the recalibrated percentile targets, and per-symbol month
   weights sum to ~1 / effective quad pcts sum to ~100.
6. If a live server is reachable: macro-detail API returns a `window` block
   with a `months` array.

One-time acceptance proof for TASK_126's "How to verify" list, not a durable
regression test — tests/acceptance/ per docs/audit/test_debt_review.md.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SQL_FILE = PROJECT_ROOT / "db" / "baseline.sql"
DERIVE_MACRO_PY = PROJECT_ROOT / "etl" / "derive_macro.py"
DASH_PY = PROJECT_ROOT / "api" / "routers" / "dash.py"
JS_FILE = PROJECT_ROOT / "web" / "actionable.js"


@pytest.fixture(scope="module")
def sql_text():
    return SQL_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def derive_macro_text():
    return DERIVE_MACRO_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def dash_py_text():
    return DASH_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js_text():
    return JS_FILE.read_text(encoding="utf-8")


# ── Schema ───────────────────────────────────────────────────────────────

class TestSchema:
    def test_drv_macro_score_detail_column(self, sql_text):
        assert "ALTER TABLE drv_macro_score ADD COLUMN IF NOT EXISTS detail JSONB" in sql_text

    def test_lookahead_settings_seeded(self, sql_text):
        assert "quad_lookahead_days" in sql_text
        assert "quad_lookahead_decay_hl" in sql_text

    def test_quarterly_weight_minimized(self, sql_text):
        assert "quad_horizon_weight_qtr'" in sql_text
        # a migration UPDATE resets the key to the new (minimized) default
        assert (
            "UPDATE ref_settings SET setting_value = '0.05'\n"
            "    WHERE setting_name = 'quad_horizon_weight_qtr';" in sql_text
        )


# ── ETL wiring ───────────────────────────────────────────────────────────

class TestEtlWiring:
    def test_derive_macro_syntax(self):
        import ast
        ast.parse(DERIVE_MACRO_PY.read_text(encoding="utf-8"))

    def test_pure_functions_importable(self):
        from etl.derive_macro import (
            build_effective_distribution, near_far_split, to_action,
            tracking_tag, window_weights,
        )
        assert callable(window_weights)
        assert callable(build_effective_distribution)
        assert callable(near_far_split)
        assert callable(tracking_tag)
        assert callable(to_action)

    def test_retired_ramp_settings_not_read(self, derive_macro_text):
        for retired in ("quad_month_ramp_begin_days", "quad_month_lead_days",
                        "quad_qtr_ramp_begin_days", "quad_qtr_lead_days"):
            assert retired not in derive_macro_text, (
                f"{retired} should no longer be read by etl/derive_macro.py (TASK_126)"
            )

    def test_wired_into_derive_all(self):
        derive_py = (PROJECT_ROOT / "etl" / "derive.py").read_text(encoding="utf-8")
        assert "_derive_macro_impl" in derive_py
        assert "drv_macro_score" in derive_py


# ── API ──────────────────────────────────────────────────────────────────

class TestApiWiring:
    def test_macro_detail_endpoint_reads_drv_macro_score_detail(self, dash_py_text):
        idx = dash_py_text.find('@router.get("/api/actionable/macro-detail")')
        assert idx != -1
        body = dash_py_text[idx: idx + 4000]
        assert "drv_macro_score" in body
        assert '"window"' in body

    def test_quad_window_endpoint_exists(self, dash_py_text):
        assert '@router.get("/api/quad-window")' in dash_py_text

    def test_live_macro_detail_has_window_if_reachable(self):
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:8000/api/actionable", timeout=8
            ) as resp:
                rows = json.loads(resp.read().decode())
        except Exception as e:
            pytest.skip(f"Live server not reachable: {e}")
        if not rows:
            pytest.skip("No rows returned for default date")
        sym = rows[0].get("tos_symbol")
        if not sym:
            pytest.skip("No tos_symbol on first row")
        qs = urllib.parse.urlencode({"symbol": sym})
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:8000/api/actionable/macro-detail?{qs}", timeout=8
            ) as resp:
                detail = json.loads(resp.read().decode())
        except Exception as e:
            pytest.skip(f"macro-detail not reachable: {e}")
        md = detail.get("macro_detail")
        if md is None:
            pytest.skip(f"No macro_detail for {sym} (no drv_macro_score row?)")
        win = md.get("window")
        assert win is not None, "macro_detail.window missing (TASK_126)"
        assert "months" in win


# ── UI ───────────────────────────────────────────────────────────────────

class TestUiWiring:
    def test_node_check_passes(self):
        result = subprocess.run(["node", "--check", str(JS_FILE)],
                                 capture_output=True, text=True)
        assert result.returncode == 0, (
            f"node --check failed: {result.stdout}\n{result.stderr}"
        )

    def test_tooltip_uses_window(self, js_text):
        idx = js_text.find("function _macroTooltip(")
        assert idx != -1
        body = js_text[idx: idx + 3000]
        assert "det.window" in body

    def test_regime_band_fetches_quad_window(self, js_text):
        idx = js_text.find("async function loadMacroBand(")
        assert idx != -1
        body = js_text[idx: idx + 3000]
        assert "/api/quad-window" in body


# ── DB / live data (skips gracefully if no DB / server) ────────────────────

class TestLiveData:
    def test_drv_macro_score_detail_populated_for_anchor_if_reachable(self):
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
                    SELECT tos_symbol, macronet, macro_action, detail
                    FROM drv_macro_score WHERE as_of_date = :d
                """), {"d": anchor}).fetchall()
        except Exception as e:
            pytest.skip(f"DB not available: {e}")
        if not rows:
            pytest.skip(
                "drv_macro_score has no rows for the current anchor date — "
                "run derive_all() (or the scheduler) after this change lands."
            )
        n = len(rows)
        with_detail = [r for r in rows if r[3] is not None]
        assert with_detail, "no drv_macro_score row has a populated detail JSONB (TASK_126)"

        actions = {}
        for r in rows:
            if r[2]:
                actions[r[2]] = actions.get(r[2], 0) + 1
        # Sanity band around the recalibrated percentile targets — not an
        # exact match (the near/far override puts a structural floor under
        # SA independent of the raw score thresholds; see docs/quad_design.md).
        hold_pct = actions.get('HOLD', 0) / n * 100
        assert 40 <= hold_pct <= 90, f"HOLD share {hold_pct:.1f}% outside sane band"

        sample = with_detail[0]
        det = sample[3]
        if isinstance(det, str):
            det = json.loads(det)
        months = det.get("months") or []
        assert months, "detail.months empty for a symbol with populated detail"
        w_sum = sum(m["w"] for m in months)
        assert abs(w_sum - 1.0) < 1e-3, f"window weights don't sum to 1 ({w_sum})"
        eff = det.get("eff") or {}
        eff_sum = sum(eff.values())
        assert abs(eff_sum - 100.0) < 1.0, f"effective quad pcts don't sum to ~100 ({eff_sum})"
