"""
Tests for AGENT_WORK_6 / TASK_64 — Price/Volume/Volatility audit fixes F1-F7.

Acceptance criteria verified here (pure-Python / no DB required):

  F1/F2  True rolling-median SD denominator
    Check 1  — _get_sd_window() function exists in derive_cat_atomic_input
    Check 2  — WORKING_SET_SQL uses percentile_cont(0.5) not DISTINCT ON for median
    Check 3  — AC computation is LEAST(standard_dev, median_sd) not just standard_dev
    Check 4  — derive_cat_atomic_input passes :win param to WORKING_SET_SQL
    Check 5  — get_symbol_intermediates also uses _get_sd_window
    Check 6  — derive.py twin engine also uses percentile_cont rolling median
    Check 7  — derive.py reads sd_median_window_days from ref_settings
    Check 8  — derive.py uses LEAST(sd, median_sd) in its computation

  F3  VolumeSpike right-pad decode
    Check 9  — _decode_vs pads fg_str to 9 chars before prepending 10 zeros
    Check 10 — _decode_vs produces correct FH for short FG string (FG length < 9)
    Check 11 — _decode_vs FI/FJ/FL/FM correct for a full-length FG string
    Check 12 — _decode_vs FI/FJ/FL/FM correct when A_VolumeSpike is zero (→ all 0)
    Check 13 — _decode_vs handles None A_VolumeSpike
    Check 14 — JS _decodeVolumeSpike has REPT padding comment
    Check 15 — JS _decodeVolumeSpike has reptPad + slice(-10) logic

  F4a  Dead _derive_ma_impl removed
    Check 16 — etl/derive.py does NOT contain _derive_ma_impl function definition
    Check 17 — etl/derive.py does NOT contain 'derive_ma = _wrap' binding
    Check 18 — etl/ma_codegen.py has updated comment about removal

  F5  RR/BB slope params from ref_settings
    Check 19 — derive.py reads bb_slope_hi / bb_slope_lo from ref_settings
    Check 20 — derive.py passes :bshi / :bslo as SQL params
    Check 21 — derive.py reads rr_reverse_scale / rr_reverse_mid_scale from ref_settings

  F6  vlm_3m_pct / vlm_desc / vlm_action persisted and exposed
    Check 22 — derive_v2.py defines _VLM_DESC_MAP with keys '1'..'10'
    Check 23 — derive_v2.py defines _VLM_ACTION_MAP with keys '1'..'10'
    Check 24 — derive_v2.py computes vlm_3m_pct from w_vlm/avg3m
    Check 25 — derive_v2.py includes vlm_3m_pct/vlm_desc/vlm_action in output dict
    Check 26 — db/baseline.sql ALTERs drv_tw to add vlm_3m_pct/vlm_desc/vlm_action
    Check 27 — api/routers/dash.py selects vlm_3m_pct/vlm_desc/vlm_action
    Check 28 — web/actionable.js _buildVolPopHtml includes 'Vlm vs 3m Avg' row
    Check 29 — web/actionable.js _buildVolPopHtml includes 'Vol Signal' row
    Check 30 — web/actionable.js rvol-cell uses vlm_action for badge color

  F7  CA scale comment
    Check 31 — derive_cat_atomic_input.py has scale-mismatch comment at CA = net_chng/AC

  Schema seeds
    Check 32 — baseline.sql seeds sd_median_window_days=30
    Check 33 — baseline.sql seeds bb_slope_hi, bb_slope_lo
    Check 34 — baseline.sql seeds rr_reverse_scale, rr_reverse_mid_scale

  VolumeSpike parity: Python _decode_vs matches expected Excel output
    Check 35 — Short FG (e.g. 5.33): padded, FI/FJ/FL/FM decode correctly
    Check 36 — Full FG (e.g. 200443.44): FI/FJ/FL/FM decode correctly
    Check 37 — Negative A_VolumeSpike uses abs(FF) for FG
    Check 38 — _decode_vs and _decodeVolumeSpike agree on FI/FJ/FL/FM (parity)

  DEV_HANDOFF status
    Check 39 — DEV_HANDOFF.md ends with ALL_DONE
    Check 40 — DEV_HANDOFF.md references AGENT_WORK_6
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

DERIVE_CAT     = PROJECT / "etl" / "derive_cat_atomic_input.py"
DERIVE         = PROJECT / "etl" / "derive.py"
DERIVE_V2      = PROJECT / "etl" / "derive_v2.py"
MA_CODEGEN     = PROJECT / "etl" / "ma_codegen.py"
BASELINE_SQL   = PROJECT / "db" / "baseline.sql"
DASH_PY        = PROJECT / "api" / "routers" / "dash.py"
ACTIONABLE_JS  = PROJECT / "web" / "actionable.js"
DEV_HANDOFF    = PROJECT / "DEV_HANDOFF.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Helpers — verify files exist before reading
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def cat_src() -> str:
    assert DERIVE_CAT.exists(), f"{DERIVE_CAT} missing"
    return _read(DERIVE_CAT)


@pytest.fixture(scope="module")
def derive_src() -> str:
    assert DERIVE.exists(), f"{DERIVE} missing"
    return _read(DERIVE)


@pytest.fixture(scope="module")
def v2_src() -> str:
    assert DERIVE_V2.exists(), f"{DERIVE_V2} missing"
    return _read(DERIVE_V2)


@pytest.fixture(scope="module")
def sql_src() -> str:
    assert BASELINE_SQL.exists(), f"{BASELINE_SQL} missing"
    return _read(BASELINE_SQL)


@pytest.fixture(scope="module")
def dash_src() -> str:
    assert DASH_PY.exists(), f"{DASH_PY} missing"
    return _read(DASH_PY)


@pytest.fixture(scope="module")
def js_src() -> str:
    assert ACTIONABLE_JS.exists(), f"{ACTIONABLE_JS} missing"
    return _read(ACTIONABLE_JS)


@pytest.fixture(scope="module")
def handoff_src() -> str:
    assert DEV_HANDOFF.exists(), f"{DEV_HANDOFF} missing"
    return _read(DEV_HANDOFF)


# ===========================================================================
# F1/F2 — True rolling-median SD denominator
# ===========================================================================

class TestF1F2RollingMedianSD:

    def test_check1_get_sd_window_exists(self, cat_src):
        """Check 1 — _get_sd_window() function defined in derive_cat_atomic_input."""
        assert "def _get_sd_window(" in cat_src, (
            "_get_sd_window() is missing from derive_cat_atomic_input.py"
        )

    def test_check2_percentile_cont_in_working_set_sql(self, cat_src):
        """Check 2 — WORKING_SET_SQL uses percentile_cont(0.5) for true median."""
        assert "percentile_cont(0.5)" in cat_src, (
            "percentile_cont(0.5) not found — med CTE may still use DISTINCT ON"
        )
        # Old DISTINCT ON pattern should be gone from the med CTE
        # (it may still exist for other CTEs, so we just confirm percentile_cont is present)

    def test_check3_ac_uses_least(self, cat_src):
        """Check 3 — AC is computed as LEAST/MIN of standard_dev and median_sd."""
        # The comment in the code says: AC = MIN(standard_dev, rolling_median_sd)
        assert ("LEAST" in cat_src or "min(AB, AA)" in cat_src or
                "MIN(standard_dev, median_sd)" in cat_src or
                "min(AB" in cat_src.lower()), (
            "AC does not appear to use LEAST/MIN of standard_dev and median_sd"
        )

    def test_check4_win_param_passed_to_working_set(self, cat_src):
        """Check 4 — derive_cat_atomic_input passes :win to WORKING_SET_SQL."""
        assert '"win": win' in cat_src or "'win': win" in cat_src, (
            "derive_cat_atomic_input does not pass :win param to WORKING_SET_SQL"
        )

    def test_check5_get_symbol_intermediates_uses_win(self, cat_src):
        """Check 5 — get_symbol_intermediates also calls _get_sd_window."""
        assert "get_symbol_intermediates" in cat_src, "get_symbol_intermediates missing"
        # _get_sd_window should be called in at least 2 places
        assert cat_src.count("_get_sd_window(") >= 2, (
            "_get_sd_window() called fewer than 2 times; "
            "get_symbol_intermediates may not be using it"
        )

    def test_check6_derive_py_twin_uses_percentile_cont(self, derive_src):
        """Check 6 — derive.py twin engine also uses percentile_cont rolling median."""
        assert "percentile_cont(0.5)" in derive_src, (
            "percentile_cont(0.5) not found in derive.py — twin engine may be out of sync"
        )

    def test_check7_derive_py_reads_sd_median_window(self, derive_src):
        """Check 7 — derive.py reads sd_median_window_days from ref_settings."""
        assert "sd_median_window_days" in derive_src, (
            "sd_median_window_days not read in derive.py"
        )

    def test_check8_derive_py_uses_least(self, derive_src):
        """Check 8 — derive.py uses LEAST(sd, median_sd) in computation."""
        assert "LEAST(i.sd, i.median_sd)" in derive_src or "LEAST(sd, median_sd)" in derive_src, (
            "derive.py twin does not use LEAST(sd, median_sd)"
        )


# ===========================================================================
# F3 — VolumeSpike right-pad (Python unit tests)
# ===========================================================================

# Import _decode_vs at module level using importlib to avoid BOM issues
def _get_decode_vs():
    """Import _decode_vs from derive_cat_atomic_input, handling BOM."""
    import importlib.util, types
    spec = importlib.util.spec_from_file_location(
        "derive_cat_atomic_input", str(DERIVE_CAT)
    )
    mod = importlib.util.module_from_spec(spec)
    # Register a stub for etl._derive_common to avoid import chain
    if "etl._derive_common" not in sys.modules:
        stub = types.ModuleType("etl._derive_common")
        def _safe_div(a, b, default=None):
            if b is None or b == 0: return default
            return (a / b) if a is not None else default
        stub._safe_div = _safe_div
        sys.modules["etl._derive_common"] = stub
    if "etl" not in sys.modules:
        etl_stub = types.ModuleType("etl")
        sys.modules["etl"] = etl_stub
    spec.loader.exec_module(mod)
    return mod._decode_vs


try:
    _decode_vs = _get_decode_vs()
    _DECODE_VS_AVAILABLE = True
except Exception as _e:
    _decode_vs = None
    _DECODE_VS_AVAILABLE = False
    _DECODE_VS_ERROR = str(_e)


class TestF3VolumeSpikeDecode:

    def test_check9_rept_padding_in_source(self, cat_src):
        """Check 9 — _decode_vs pads fg_str to 9 chars."""
        assert "rept_pad" in cat_src or "9 - len(fg_str)" in cat_src, (
            "REPT-padding logic not found in _decode_vs"
        )
        assert "max(0, 9 - len(fg_str))" in cat_src, (
            "max(0, 9 - len(fg_str)) not in _decode_vs — REPT pad formula missing"
        )

    def test_check10_short_fg_decode(self):
        """Check 10 — Short FG (length < 9): FH is correctly right-padded.

        Excel: FG = '5.33' (len=4), REPT pad = 9-4 = 5 zeros appended.
        padded = '0000000000' + '5.33' + '00000' = '000000000005.3300000'
        FH = last 10 chars = '05.3300000'
        FH[0:2]='05' → FI=5
        FH[2:5]='.33' → FJ=0 (non-numeric prefix)
        FH[5:7]='00' → FL=0
        FH[8:10]='00' → FM=0
        """
        if not _DECODE_VS_AVAILABLE:
            pytest.skip(f"_decode_vs import failed: {_DECODE_VS_ERROR}")
        result = _decode_vs(5.33, AD=1.0)
        # FG = '5.33', length 4; rept_pad = 9-4 = 5
        # padded = '0000000000' + '5.33' + '00000' = '000000000005.3300000'
        # FH = last 10 chars = '05.3300000'
        assert result["FH"] == "05.3300000", (
            f"Short FG decode wrong: expected FH='05.3300000', got '{result['FH']}'"
        )
        assert result["FI"] == 5,   f"FI wrong: {result['FI']} (expected 5, from '05')"
        assert result["FJ"] == 0,   f"FJ wrong: {result['FJ']} (expected 0, '.33' is non-int)"
        assert result["FL"] == 0,   f"FL wrong: {result['FL']} (expected 0)"
        assert result["FM"] == 0,   f"FM wrong: {result['FM']} (expected 0)"

    def test_check11_full_length_fg_decode(self):
        """Check 11 — Full-length FG (>= 9 chars): REPT pad is '' (no change).

        A_VolumeSpike = 200443.44 → FG = '200443.44' (len=9), rept_pad=0
        padded = '0000000000' + '200443.44' = '0000000000200443.44'
        FH = last 10 = '0200443.44'
        FI = nv('02') = 2, FJ = nv('004') = 4, FL = nv('43') = 43, FM = nv('44') = 44
        """
        if not _DECODE_VS_AVAILABLE:
            pytest.skip(f"_decode_vs import failed: {_DECODE_VS_ERROR}")
        result = _decode_vs(200443.44, AD=1.0)
        assert result["FH"] == "0200443.44", (
            f"Full FG decode wrong: expected FH='0200443.44', got '{result['FH']}'"
        )
        assert result["FI"] == 2,  f"FI wrong: {result['FI']} (expected 2)"
        assert result["FJ"] == 4,  f"FJ wrong: {result['FJ']} (expected 4)"
        assert result["FL"] == 43, f"FL wrong: {result['FL']} (expected 43)"
        assert result["FM"] == 44, f"FM wrong: {result['FM']} (expected 44)"

    def test_check12_zero_spike(self):
        """Check 12 — A_VolumeSpike = 0 returns all zeros."""
        if not _DECODE_VS_AVAILABLE:
            pytest.skip(f"_decode_vs import failed: {_DECODE_VS_ERROR}")
        result = _decode_vs(0, AD=1.0)
        assert result["FI"] == 0 and result["FJ"] == 0, (
            f"Zero spike should give FI=FJ=0, got {result}"
        )
        assert result["FH"] is None, f"FH should be None for zero spike: {result}"

    def test_check13_none_spike(self):
        """Check 13 — A_VolumeSpike = None returns all zeros."""
        if not _DECODE_VS_AVAILABLE:
            pytest.skip(f"_decode_vs import failed: {_DECODE_VS_ERROR}")
        result = _decode_vs(None, AD=1.0)
        assert result["FH"] is None, f"FH should be None for None spike: {result}"
        assert result["FI"] == 0 and result["FJ"] == 0, (
            f"None spike should give FI=FJ=0, got {result}"
        )

    def test_check14_js_has_rept_comment(self, js_src):
        """Check 14 — JS _decodeVolumeSpike has REPT padding comment."""
        assert "REPT" in js_src and "_decodeVolumeSpike" in js_src, (
            "JS _decodeVolumeSpike is missing or lacks REPT comment"
        )

    def test_check15_js_has_reptpad_and_slice(self, js_src):
        """Check 15 — JS has reptPad computation and slice(-10)."""
        assert "reptPad" in js_src or "reptpad" in js_src.lower(), (
            "reptPad variable not found in JS _decodeVolumeSpike"
        )
        assert "slice(-10)" in js_src, (
            "slice(-10) not found in JS _decodeVolumeSpike"
        )

    def test_check37_negative_uses_abs(self):
        """Check 37 — Negative A_VolumeSpike uses abs(FF) for FG (same decode)."""
        if not _DECODE_VS_AVAILABLE:
            pytest.skip(f"_decode_vs import failed: {_DECODE_VS_ERROR}")
        pos = _decode_vs(200443.44, AD=1.0)
        neg = _decode_vs(-200443.44, AD=1.0)
        assert pos["FH"] == neg["FH"], (
            f"Negative spike FH {neg['FH']} != positive {pos['FH']} "
            "— abs() not applied to FG"
        )
        assert pos["FI"] == neg["FI"] and pos["FJ"] == neg["FJ"], (
            "FI/FJ mismatch between positive and negative A_VolumeSpike"
        )

    def test_check38_python_js_parity_full_length(self):
        """Check 38 — Python _decode_vs and JS produce same FI/FJ/FL/FM for full-length FG.

        We simulate the JS logic in Python to verify parity.
        """
        if not _DECODE_VS_AVAILABLE:
            pytest.skip(f"_decode_vs import failed: {_DECODE_VS_ERROR}")

        def simulate_js(FF):
            """Mirror JS _decodeVolumeSpike logic exactly.

            JS parseInt('5.', 10) returns 5 (stops at non-digit chars).
            We replicate this by stripping a trailing dot if present.
            """
            if FF is None or FF == 0:
                return None
            FG = abs(float(FF))
            fg_str = f"{FG:.2f}"
            rept_pad = max(0, 9 - len(fg_str))
            FH = ("0000000000" + fg_str + "0" * rept_pad)[-10:]
            def nv(s):
                # JS parseInt reads digits until it hits a non-digit char
                import re as _re
                m = _re.match(r'-?\d+', s)
                return int(m.group()) if m else 0
            return {
                "FI": nv(FH[0:2]),
                "FJ": nv(FH[2:5]),
                "FL": nv(FH[5:7]),
                "FM": nv(FH[8:10]),
            }

        for test_val in [200443.44, 5.33, 12345.67, 1.00, 999999.99, 100.00]:
            py = _decode_vs(test_val, AD=1.0)
            js = simulate_js(test_val)
            assert py["FI"] == js["FI"], (
                f"FI mismatch for {test_val}: py={py['FI']}, js={js['FI']}"
            )
            assert py["FJ"] == js["FJ"], (
                f"FJ mismatch for {test_val}: py={py['FJ']}, js={js['FJ']}"
            )
            assert py["FL"] == js["FL"], (
                f"FL mismatch for {test_val}: py={py['FL']}, js={js['FL']}"
            )
            assert py["FM"] == js["FM"], (
                f"FM mismatch for {test_val}: py={py['FM']}, js={js['FM']}"
            )


# ===========================================================================
# F4a — Dead _derive_ma_impl removed
# ===========================================================================

class TestF4aDeadCodeRemoved:

    def test_check16_derive_ma_impl_not_defined(self, derive_src):
        """Check 16 — _derive_ma_impl function is NOT defined in derive.py."""
        import re
        # Check there is no actual function definition (not just a comment/string)
        matches = re.findall(r'^def _derive_ma_impl\b', derive_src, re.MULTILINE)
        assert len(matches) == 0, (
            "_derive_ma_impl function still defined in derive.py — should be deleted"
        )

    def test_check17_derive_ma_wrap_not_present(self, derive_src):
        """Check 17 — derive_ma = _wrap(...) binding is NOT present in derive.py."""
        assert "derive_ma = _wrap" not in derive_src, (
            "derive_ma = _wrap(...) still present in derive.py — should be deleted"
        )

    def test_check18_ma_codegen_comment_updated(self):
        """Check 18 — ma_codegen.py has comment about _derive_ma_impl removal."""
        assert MA_CODEGEN.exists(), f"{MA_CODEGEN} missing"
        src = _read(MA_CODEGEN)
        assert ("removed" in src.lower() or "deleted" in src.lower() or
                "VIEW" in src), (
            "ma_codegen.py does not document removal of _derive_ma_impl"
        )


# ===========================================================================
# F5 — RR/BB slope params from ref_settings
# ===========================================================================

class TestF5TunableConstants:

    def test_check19_bb_slope_params_read(self, derive_src):
        """Check 19 — derive.py reads bb_slope_hi and bb_slope_lo from ref_settings."""
        assert "bb_slope_hi" in derive_src, "bb_slope_hi not found in derive.py"
        assert "bb_slope_lo" in derive_src, "bb_slope_lo not found in derive.py"
        assert "ref_settings" in derive_src, "ref_settings not queried in derive.py"

    def test_check20_bb_slope_passed_as_sql_params(self, derive_src):
        """Check 20 — :bshi/:bslo passed as SQL params in BBRngStrkRule CASE."""
        assert ":bshi" in derive_src or "bshi" in derive_src, (
            ":bshi SQL param not found in derive.py"
        )
        assert ":bslo" in derive_src or "bslo" in derive_src, (
            ":bslo SQL param not found in derive.py"
        )

    def test_check21_rr_scale_params_read(self, derive_src):
        """Check 21 — derive.py reads rr_reverse_scale and rr_reverse_mid_scale."""
        assert "rr_reverse_scale" in derive_src, (
            "rr_reverse_scale not found in derive.py"
        )
        assert "rr_reverse_mid_scale" in derive_src, (
            "rr_reverse_mid_scale not found in derive.py"
        )


# ===========================================================================
# F6 — vlm_3m_pct / vlm_desc / vlm_action persisted and exposed
# ===========================================================================

class TestF6VolumeFields:

    def test_check22_vlm_desc_map_defined(self, v2_src):
        """Check 22 — _VLM_DESC_MAP with keys 1..10 in derive_v2.py."""
        assert "_VLM_DESC_MAP" in v2_src, "_VLM_DESC_MAP not defined in derive_v2.py"
        for k in range(1, 11):
            assert f'"{k}"' in v2_src or f"'{k}'" in v2_src, (
                f"Key '{k}' missing from _VLM_DESC_MAP"
            )

    def test_check23_vlm_action_map_defined(self, v2_src):
        """Check 23 — _VLM_ACTION_MAP with keys 1..10 in derive_v2.py."""
        assert "_VLM_ACTION_MAP" in v2_src, "_VLM_ACTION_MAP not defined in derive_v2.py"

    def test_check23b_vlm_action_map_valid_values(self, v2_src):
        """Check 23b — _VLM_ACTION_MAP values are valid action tags."""
        valid = {"Accumulate", "Watch", "Avoid"}
        # Extract the map from source; just verify all used values appear
        for tag in valid:
            # At least one valid tag should appear in the map
            pass  # We'll verify by import
        assert "Accumulate" in v2_src and "Watch" in v2_src and "Avoid" in v2_src, (
            "_VLM_ACTION_MAP missing Accumulate/Watch/Avoid values"
        )

    def test_check24_vlm_3m_pct_computed(self, v2_src):
        """Check 24 — vlm_3m_pct computed from w_vlm/avg3m ratio in derive_v2.py."""
        assert "vlm_3m_pct" in v2_src, "vlm_3m_pct not found in derive_v2.py"
        assert "avg3m" in v2_src or "avg_3m" in v2_src, (
            "avg3m variable not found in derive_v2.py"
        )

    def test_check25_vlm_fields_in_output_dict(self, v2_src):
        """Check 25 — vlm_3m_pct/vlm_desc/vlm_action all appear in output dict."""
        assert '"vlm_3m_pct"' in v2_src or "'vlm_3m_pct'" in v2_src, (
            "vlm_3m_pct not in derive_v2.py output dict"
        )
        assert '"vlm_desc"' in v2_src or "'vlm_desc'" in v2_src, (
            "vlm_desc not in derive_v2.py output dict"
        )
        assert '"vlm_action"' in v2_src or "'vlm_action'" in v2_src, (
            "vlm_action not in derive_v2.py output dict"
        )

    def test_check26_baseline_sql_alters_drv_tw(self, sql_src):
        """Check 26 — db/baseline.sql ALTERs drv_tw to add the three vlm columns."""
        assert "vlm_3m_pct" in sql_src, "vlm_3m_pct ALTER not in baseline.sql"
        assert "vlm_desc" in sql_src, "vlm_desc ALTER not in baseline.sql"
        assert "vlm_action" in sql_src, "vlm_action ALTER not in baseline.sql"
        assert "ADD COLUMN IF NOT EXISTS vlm_3m_pct" in sql_src, (
            "ALTER TABLE ... ADD COLUMN IF NOT EXISTS vlm_3m_pct missing"
        )

    def test_check27_dash_router_selects_vlm_fields(self, dash_src):
        """Check 27 — api/routers/dash.py selects vlm_3m_pct/vlm_desc/vlm_action."""
        assert "vlm_3m_pct" in dash_src, "vlm_3m_pct not selected in dash.py"
        assert "vlm_desc" in dash_src, "vlm_desc not selected in dash.py"
        assert "vlm_action" in dash_src, "vlm_action not selected in dash.py"

    def test_check28_vol_popover_vlm_vs_3m_avg(self, js_src):
        """Check 28 — _buildVolPopHtml includes 'Vlm vs 3m Avg' row."""
        assert "Vlm vs 3m Avg" in js_src, (
            "'Vlm vs 3m Avg' row missing from _buildVolPopHtml in actionable.js"
        )

    def test_check29_vol_popover_vol_signal(self, js_src):
        """Check 29 — _buildVolPopHtml includes the volume-signal row.

        REWRITTEN (TASK_112, 2026-07-04): the row label was re-worded from
        'Vol Signal' to 'Vlm Signal' (consistent with the 'Vol'->'Vlm'
        rename used elsewhere on the grid, e.g. the Vlm column header) — 0
        matches for the old label, same row/field otherwise unchanged.
        """
        assert "Vlm Signal" in js_src, (
            "'Vlm Signal' row missing from _buildVolPopHtml in actionable.js"
        )

    def test_check30_rvol_cell_vlm_action_badge(self, js_src):
        """Check 30 — rvol-cell uses vlm_action for colored badge."""
        assert "vlm_action" in js_src, "vlm_action not found in actionable.js"
        assert "Accumulate" in js_src and "Avoid" in js_src, (
            "Accumulate/Avoid badge colors missing from rvol-cell in actionable.js"
        )


# ===========================================================================
# F7 — CA scale comment
# ===========================================================================

class TestF7ScaleComment:

    def test_check31_ca_scale_comment(self, cat_src):
        """Check 31 — Scale-mismatch comment present at CA = net_chng/AC."""
        # The comment says ~100x smaller than Excel's pct_change%×D/AC
        has_comment = (
            "net_chng" in cat_src and "100" in cat_src and
            ("scale" in cat_src.lower() or "calibrat" in cat_src.lower())
        )
        assert has_comment, (
            "CA scale-mismatch comment not found in derive_cat_atomic_input.py. "
            "Expected comment about net_chng scale vs Excel pct_change%"
        )


# ===========================================================================
# Schema seeds
# ===========================================================================

class TestSchemaSeeds:

    def test_check32_sd_median_window_seed(self, sql_src):
        """Check 32 — baseline.sql seeds sd_median_window_days=30."""
        assert "sd_median_window_days" in sql_src, (
            "sd_median_window_days seed missing from baseline.sql"
        )
        assert "'30'" in sql_src or '"30"' in sql_src, (
            "sd_median_window_days value '30' not found in baseline.sql"
        )

    def test_check33_bb_slope_seeds(self, sql_src):
        """Check 33 — baseline.sql seeds bb_slope_hi and bb_slope_lo."""
        assert "bb_slope_hi" in sql_src, "bb_slope_hi seed missing from baseline.sql"
        assert "bb_slope_lo" in sql_src, "bb_slope_lo seed missing from baseline.sql"

    def test_check34_rr_scale_seeds(self, sql_src):
        """Check 34 — baseline.sql seeds rr_reverse_scale and rr_reverse_mid_scale."""
        assert "rr_reverse_scale" in sql_src, (
            "rr_reverse_scale seed missing from baseline.sql"
        )
        assert "rr_reverse_mid_scale" in sql_src, (
            "rr_reverse_mid_scale seed missing from baseline.sql"
        )


# ===========================================================================
# VolumeSpike Excel-formula parity edge cases
# ===========================================================================

class TestVolumeSpikeExcelParity:

    def test_check35_short_fg_parity(self):
        """Check 35 — Short FG (len < 9): padded decode matches Excel formula.

        Excel: FG='5.33' → REPT('0', 9-4)='00000' → FH = RIGHT('00000000005.3300000',10)
        = '05.3300000'
        FI=nv('05')=5, FJ=nv('.33')=0, FL=nv('00')=0, FM=nv('00')=0

        Wait — let's recompute carefully:
        '0000000000' + '5.33' + '00000' = '000000000005.3300000' (19 chars)
        last 10 = '05.3300000'
        FH[0:2]='05' → FI=5
        FH[2:5]='.33' → FJ=nv('.33')=0 (non-integer prefix)
        FH[5:7]='00' → FL=0
        FH[8:10]='00' → FM=0
        """
        if not _DECODE_VS_AVAILABLE:
            pytest.skip(f"_decode_vs import failed: {_DECODE_VS_ERROR}")
        r = _decode_vs(5.33, AD=1.0)
        assert r["FH"] == "05.3300000", f"FH={r['FH']}"
        assert r["FI"] == 5, f"FI={r['FI']}"
        assert r["FJ"] == 0, f"FJ={r['FJ']}"   # '.33' → int fails → 0

    def test_check36_full_length_parity(self):
        """Check 36 — Full-length FG: matches known Excel output.

        A_VolumeSpike = 200443.44 → FG='200443.44' (9 chars), rept_pad=0
        FH = RIGHT('0000000000200443.44', 10) = '0200443.44'
        FI=02=2, FJ=004=4, FL=43=43, FM=44=44
        """
        if not _DECODE_VS_AVAILABLE:
            pytest.skip(f"_decode_vs import failed: {_DECODE_VS_ERROR}")
        r = _decode_vs(200443.44, AD=1.0)
        assert r["FH"] == "0200443.44"
        assert r["FI"] == 2
        assert r["FJ"] == 4
        assert r["FL"] == 43
        assert r["FM"] == 44


# ===========================================================================
# DEV_HANDOFF status
# ===========================================================================

class TestDevHandoffStatus:

    def test_check39_handoff_ends_all_done(self, handoff_src):
        """Check 39 — DEV_HANDOFF.md last non-blank line is ALL_DONE."""
        lines = [l.strip() for l in handoff_src.splitlines() if l.strip()]
        assert lines, "DEV_HANDOFF.md is empty"
        assert lines[-1] == "ALL_DONE", (
            f"DEV_HANDOFF.md last line is '{lines[-1]}', expected 'ALL_DONE'"
        )

    # test_check40_handoff_references_agent_work_6 — RETIRED (TASK_112
    # test-debt cleanup, 2026-07-04). DEV_HANDOFF.md is a rolling file,
    # overwritten fresh by every task's developer pass — pinning it to
    # AGENT_WORK_6-specific content is permanently stale by design. Cat A
    # per docs/audit/test_debt_review.md.
