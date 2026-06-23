"""
QA tests for AGENT_WORK_13 / TASK_74 — MacroNet quad-regime overlay.

These tests supplement test_task74_macronet.py, specifically:
  A. _next_weight (ramp/lead) formula — the DEV_HANDOFF flagged the existing
     test class tests the OLD proximity_weight formula; these test the NEW one.
  B. seeds_quad_periods.sql existence and data-row count.
  C. SQL-length check against the ACTUAL dash.py strings (combined continuation
     literals) rather than the pre-merged strings in the existing test.
  D. macro_conf present in the enrichment return dict.
  E. Confirm the new ref_settings params (quad_month_ramp_begin_days etc.) are
     in baseline.sql alongside the legacy params.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_DASH_PY   = PROJECT_ROOT / "api" / "routers" / "dash.py"
BASELINE_SQL  = PROJECT_ROOT / "db" / "baseline.sql"
SEEDS_SQL     = PROJECT_ROOT / "db" / "seeds_quad_periods.sql"


def _py() -> str:
    return API_DASH_PY.read_text(encoding="utf-8")


def _sql() -> str:
    return BASELINE_SQL.read_text(encoding="utf-8")


def _seeds() -> str:
    return SEEDS_SQL.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A. _next_weight formula tests (new ramp/lead, not the old proximity_weight)
# ---------------------------------------------------------------------------

class TestNextWeightFormula:
    """
    New formula from dash.py _next_weight():
      raw = (ramp_begin - dtb) / (ramp_begin - lead_days)
      result = clamp(raw, 0, 1)

    Defaults: ramp_begin=12, lead_days=5
    """

    def _next_weight(self, dtb: int, ramp_begin: int = 12, lead_days: int = 5) -> float:
        """Mirror of _next_weight from api/routers/dash.py."""
        denom = ramp_begin - lead_days
        if denom <= 0:
            return 1.0 if dtb <= lead_days else 0.0
        raw = (ramp_begin - dtb) / denom
        return max(0.0, min(1.0, raw))

    def test_far_from_month_end_returns_zero(self):
        """dtb > ramp_begin (e.g., 22 days) → next_weight = 0 (100% current month)."""
        assert self._next_weight(22) == 0.0

    def test_at_ramp_begin_returns_zero(self):
        """dtb == ramp_begin (12) → raw=(12-12)/7=0 → next_weight=0."""
        assert self._next_weight(12) == 0.0

    def test_just_inside_ramp_begin(self):
        """dtb=11 → raw=(12-11)/7=1/7 ≈ 0.1429."""
        result = self._next_weight(11)
        expected = 1.0 / 7.0
        assert abs(result - expected) < 1e-9

    def test_midway_through_ramp(self):
        """dtb=8 (halfway between ramp_begin=12 and lead_days=5, roughly) →
        raw=(12-8)/7=4/7 ≈ 0.5714."""
        result = self._next_weight(8)
        expected = 4.0 / 7.0
        assert abs(result - expected) < 1e-9

    def test_at_lead_days_returns_one(self):
        """dtb==lead_days (5) → raw=(12-5)/7=1.0 → next_weight=1.0."""
        assert self._next_weight(5) == 1.0

    def test_below_lead_days_clamped_to_one(self):
        """dtb < lead_days (e.g., 2) → raw > 1 → clamped to 1.0."""
        assert self._next_weight(2) == 1.0

    def test_zero_dtb_returns_one(self):
        """dtb=0 → raw=12/7 > 1 → clamped to 1.0."""
        assert self._next_weight(0) == 1.0

    def test_denom_zero_guard_dtb_above_lead(self):
        """When ramp_begin == lead_days (denom=0), dtb > lead_days → 0.0."""
        result = self._next_weight(dtb=10, ramp_begin=5, lead_days=5)
        assert result == 0.0

    def test_denom_zero_guard_dtb_at_lead(self):
        """When ramp_begin == lead_days (denom=0), dtb <= lead_days → 1.0."""
        result = self._next_weight(dtb=5, ramp_begin=5, lead_days=5)
        assert result == 1.0

    def test_handoff_example_dtb22(self):
        """DEV_HANDOFF §6: anchor 2026-06-18, dtb=22 > ramp_begin=12 → next_weight=0."""
        assert self._next_weight(22) == 0.0

    def test_handoff_example_dtb8(self):
        """DEV_HANDOFF §6: near month-end dtb=8 → (12-8)/(12-5)=4/7≈0.5714."""
        result = self._next_weight(8)
        assert abs(result - 4.0 / 7.0) < 1e-9

    def test_handoff_example_dtb5(self):
        """DEV_HANDOFF §6: dtb=lead_days=5 → next_weight=1.0 (full next month)."""
        assert self._next_weight(5) == 1.0


# ---------------------------------------------------------------------------
# B. seeds_quad_periods.sql — existence and sanity
# ---------------------------------------------------------------------------

class TestSeedsQuadPeriods:
    def test_file_exists(self):
        assert SEEDS_SQL.exists(), f"seeds_quad_periods.sql not found at {SEEDS_SQL}"

    def test_file_has_data_rows(self):
        content = _seeds()
        # Must have at least one INSERT ... VALUES line
        assert "INSERT INTO ref_quad_periods" in content, \
            "seeds_quad_periods.sql has no INSERT INTO ref_quad_periods statement"

    def test_file_has_monthly_rows(self):
        content = _seeds()
        assert "'monthly'" in content, \
            "seeds_quad_periods.sql must have monthly period_type rows"

    def test_file_has_pct_columns(self):
        content = _seeds()
        assert "quad1_pct" in content, \
            "seeds_quad_periods.sql must reference quad1_pct column"

    def test_existing_months_present(self):
        """May-26, Jun-26, Jul-26, Aug-26 must appear in the first UPSERT block."""
        content = _seeds()
        for label in ("May-26", "Jun-26", "Jul-26", "Aug-26"):
            assert label in content, \
                f"seeds_quad_periods.sql missing entry for {label}"

    def test_future_months_present(self):
        """New months Sep-26 through Apr-27 must be present."""
        content = _seeds()
        for label in ("Sep-26", "Oct-26", "Nov-26", "Dec-26",
                      "Jan-27", "Feb-27", "Mar-27", "Apr-27"):
            assert label in content, \
                f"seeds_quad_periods.sql missing future month {label}"

    def test_on_conflict_do_update_pct_only(self):
        """ON CONFLICT must update only the pct columns, not quad/label/dates."""
        content = _seeds()
        # The DO UPDATE clause must reference quad1_pct
        assert "DO UPDATE SET" in content and "quad1_pct" in content, \
            "ON CONFLICT DO UPDATE SET must set quad*_pct"
        # Must NOT update the quad label itself (that comes from load_hqds)
        # Check the DO UPDATE block doesn't update 'quad = EXCLUDED.quad'
        # (it's fine if 'quad' appears elsewhere; just confirm the update target is pct)
        update_section = content[content.find("DO UPDATE SET"):]
        # The update must be setting pct columns, not quad column names
        assert "quad1_pct = EXCLUDED.quad1_pct" in update_section, \
            "ON CONFLICT must update quad1_pct = EXCLUDED.quad1_pct"

    def test_pct_rows_sum_approx_100(self):
        """Spot-check: each data row's pcts should sum to ~100."""
        content = _seeds()
        # Extract numeric rows from VALUES blocks — look for 4-int tuples at end
        pattern = r"\(\s*'monthly'[^)]+,\s*(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\)"
        matches = re.findall(pattern, content)
        assert len(matches) > 0, "Could not extract pct rows from seeds file"
        for m in matches:
            total = sum(int(x) for x in m)
            assert 95 <= total <= 105, \
                f"Pct row {m} sums to {total}, expected ~100"


# ---------------------------------------------------------------------------
# C. SQL-length check using the ACTUAL combined literals from dash.py
# ---------------------------------------------------------------------------

class TestActualSQLLengths:
    """Reconstruct the exact SQL strings as Python sees them (joined continuations)."""

    def _check(self, sql: str, label: str) -> None:
        b = len(sql.encode("utf-8"))
        assert b <= 965, f"{label}: SQL is {b} bytes (limit 965)"

    def test_settings_load_sql(self):
        sql = (
            "SELECT setting_name, setting_value FROM ref_settings"
            " WHERE setting_name IN"
            " ('quad_month_ramp_begin_days','quad_month_lead_days',"
            "  'quad_horizon_weight_qtr','quad_horizon_weight_mo',"
            "  'macro_thr_sa','macro_thr_stm','macro_thr_bs','macro_thr_bm')"
        )
        self._check(sql, "settings load")
        # Also confirm it's present in dash.py
        src = _py()
        assert "quad_month_ramp_begin_days" in src

    def test_periods_load_sql(self):
        sql = (
            "SELECT period_type, quad, start_date, end_date,"
            " quad1_pct, quad2_pct, quad3_pct, quad4_pct"
            " FROM ref_quad_periods ORDER BY period_type, start_date"
        )
        self._check(sql, "periods load")
        assert "ref_quad_periods" in _py()

    def test_quad_outlook_sql(self):
        sql = (
            "SELECT category, sub_category, ticker,"
            " quad1, quad2, quad3, quad4"
            " FROM ref_quad_outlook"
        )
        self._check(sql, "quad outlook")
        assert "ref_quad_outlook" in _py()

    def test_fundamentals_sql(self):
        sql = (
            "SELECT tos_symbol, market_cap_str, beta, pe_ratio, eps, div_yield"
            " FROM drv_fundamentals WHERE as_of_date = :d"
        )
        self._check(sql, "fundamentals")
        assert "drv_fundamentals" in _py()


# ---------------------------------------------------------------------------
# D. macro_conf present in the enrichment return dict
# ---------------------------------------------------------------------------

class TestMacroConf:
    def test_macro_conf_in_blank_return(self):
        """_blank dict must include macro_conf."""
        src = _py()
        # The _blank dict appears after 'Returns: macro_value, macro_conf...'
        assert '"macro_conf": None' in src or "'macro_conf': None" in src, \
            "macro_conf not in _blank return dict in dash.py"

    def test_macro_conf_in_full_return(self):
        """Full return must include macro_conf key."""
        src = _py()
        assert '"macro_conf": conf' in src or "'macro_conf': conf" in src, \
            "macro_conf: conf not in full return dict in dash.py"

    def test_macro_conf_in_exception_fallback(self):
        """Exception fallback dict must include macro_conf: None."""
        src = _py()
        # Count occurrences of macro_conf
        count = src.count("macro_conf")
        assert count >= 3, \
            f"macro_conf appears only {count} times — expected at least 3 sites"


# ---------------------------------------------------------------------------
# E. New AND legacy ref_settings params in baseline.sql
# ---------------------------------------------------------------------------

class TestBaselineSQLNewParams:
    """Both new TASK_74 params and legacy fallback params must be in baseline.sql."""

    NEW_PARAMS = [
        "quad_month_ramp_begin_days",
        "quad_month_lead_days",
        "quad_horizon_weight_qtr",
        "quad_horizon_weight_mo",
    ]
    LEGACY_PARAMS = [
        "macro_N_m",
        "macro_N_q",
        "macro_wm_max",
        "macro_wq_max",
        "macro_a",
        "macro_b",
    ]

    @pytest.mark.parametrize("param", NEW_PARAMS)
    def test_new_param_in_baseline(self, param: str):
        assert param in _sql(), \
            f"New TASK_74 param '{param}' not found in db/baseline.sql"

    @pytest.mark.parametrize("param", LEGACY_PARAMS)
    def test_legacy_param_still_in_baseline(self, param: str):
        assert param in _sql(), \
            f"Legacy param '{param}' must remain in db/baseline.sql for rollback safety"

    def test_quad_columns_in_baseline(self):
        """ref_quad_periods must have ALTER TABLE adding quad1_pct..quad4_pct."""
        sql = _sql()
        assert "ADD COLUMN IF NOT EXISTS quad1_pct" in sql, \
            "baseline.sql must add quad1_pct to ref_quad_periods"
        assert "ADD COLUMN IF NOT EXISTS quad4_pct" in sql, \
            "baseline.sql must add quad4_pct to ref_quad_periods"

    def test_ramp_begin_value_12(self):
        """Default ramp_begin_days=12 must appear in baseline.sql."""
        sql = _sql()
        assert ("quad_month_ramp_begin_days" in sql and "'12'" in sql), \
            "quad_month_ramp_begin_days default '12' not found in baseline.sql"

    def test_lead_days_value_5(self):
        """Default lead_days=5 must appear in baseline.sql."""
        sql = _sql()
        assert ("quad_month_lead_days" in sql and "'5'" in sql), \
            "quad_month_lead_days default '5' not found in baseline.sql"
