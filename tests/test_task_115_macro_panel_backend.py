"""
Tests for TASK_115 — Market panel consolidation, backend payload.

GET /api/macro-areas becomes a superset of what the three market tapes
(/api/marketbar + /api/rr-bar) render, so TASK_116's frontend merge needs no
second fetch. This is behavior/schema style (no point-in-time values —
prices/pct_change move every session): we assert *keys exist* and *shape*,
never specific numbers.

Acceptance criteria covered:
  1. Every member row carries open/high/low (candle) alongside last/pct_change
     (already present pre-TASK_115; asserted here too so a future regression
     is caught).
  2. Volatility-area (gauge role) members carry vol_low/vol_high.
  3. A dedicated 'credit' area exists, with HYG + LQD members (matching
     /api/rr-bar's Credit group).
  4. HYG carries inverted: true (mirrors web/market_bar.js's INVERTED set);
     LQD does not.
  5. Every member — across every area — has an 'inverted' boolean key
     (additive, always present, never breaks the existing renderer which
     ignores unknown fields).
  6. ref_macro_area member counts per area match what the API returns (no
     row dropped/duplicated by the new enrichment code).

Pure-schema tests only; no point-in-time price/pct assertions.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_macro_areas():
    from fastapi.testclient import TestClient
    from api.main import app

    client = TestClient(app)
    resp = client.get("/api/macro-areas")
    assert resp.status_code == 200, (
        f"Expected 200 from /api/macro-areas, got {resp.status_code}: {resp.text[:200]}"
    )
    return resp.json()


def _all_members(data: dict) -> list[dict]:
    out = []
    for area in data.get("areas", []):
        out.extend(area.get("members", []))
    return out


# ---------------------------------------------------------------------------
# 1 & 5. Per-member enrichment — open/high/low + last/pct_change + inverted
# ---------------------------------------------------------------------------

class TestPerMemberEnrichment:
    REQUIRED_KEYS = {"symbol", "role", "last", "pct_change", "open", "high",
                      "low", "inverted"}

    def test_every_member_has_ohlc_and_pct_and_inverted_keys(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        members = _all_members(data)
        assert members, "No members returned from /api/macro-areas"
        for m in members:
            missing = self.REQUIRED_KEYS - set(m.keys())
            assert not missing, (
                f"Member {m.get('symbol')!r} missing keys: {missing}"
            )

    def test_inverted_is_always_boolean(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        for m in _all_members(data):
            assert isinstance(m["inverted"], bool), (
                f"Member {m.get('symbol')!r} inverted is not bool: {m['inverted']!r}"
            )

    def test_sampled_major_markets_member_has_ohlc(self, db_available):
        """A dual-role Major Markets member (e.g. SPY) carries open/high/low
        keys — additive candle fields for the future rail candle."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        areas = {a["area_key"]: a for a in data["areas"]}
        assert "top9" in areas, "Expected 'top9' (Major Markets) area in response"
        dual_members = [m for m in areas["top9"]["members"] if m.get("role") == "dual"]
        assert dual_members, "No dual-role members found in Major Markets area"
        for m in dual_members:
            assert "open" in m and "high" in m and "low" in m


# ---------------------------------------------------------------------------
# 2. Volatility members carry vol_low/vol_high
# ---------------------------------------------------------------------------

class TestVolatilityThresholds:
    def test_gauge_members_have_vol_threshold_keys(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        areas = {a["area_key"]: a for a in data["areas"]}
        assert "volatility" in areas, "Expected 'volatility' area in response"
        gauge_members = [m for m in areas["volatility"]["members"]
                          if m.get("role") == "gauge"]
        assert gauge_members, "No gauge-role members found in Volatility area"
        for m in gauge_members:
            assert "vol_low" in m and "vol_high" in m, (
                f"Volatility member {m.get('symbol')!r} missing vol_low/vol_high keys"
            )

    def test_vix_has_non_null_vol_thresholds(self, db_available):
        """VIX has a seeded ref_vol_threshold row, so its vol_low/vol_high
        should resolve to actual numbers (not just present-but-null)."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        areas = {a["area_key"]: a for a in data["areas"]}
        vix = next((m for m in areas["volatility"]["members"] if m["symbol"] == "VIX"),
                   None)
        assert vix is not None, "VIX member not found in Volatility area"
        assert vix["vol_low"] is not None
        assert vix["vol_high"] is not None


# ---------------------------------------------------------------------------
# 3 & 4. Credit area + inverted flag
# ---------------------------------------------------------------------------

class TestCreditArea:
    def test_credit_area_present(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        area_keys = {a["area_key"] for a in data["areas"]}
        assert "credit" in area_keys, "'credit' area missing from /api/macro-areas"

    def test_credit_area_has_hyg_and_lqd(self, db_available):
        """Credit area membership matches /api/rr-bar's Credit group exactly."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        areas = {a["area_key"]: a for a in data["areas"]}
        symbols = {m["symbol"] for m in areas["credit"]["members"]}
        assert symbols == {"HYG", "LQD"}, (
            f"Expected Credit area members {{'HYG', 'LQD'}}, got {symbols}"
        )

    def test_hyg_is_inverted(self, db_available):
        """HYG (HY Bond) must carry inverted: true, mirroring market_bar.js's
        INVERTED set (HY spread color convention flips vs. plain price)."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        areas = {a["area_key"]: a for a in data["areas"]}
        hyg = next(m for m in areas["credit"]["members"] if m["symbol"] == "HYG")
        assert hyg["inverted"] is True

    def test_lqd_is_not_inverted(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_macro_areas()
        areas = {a["area_key"]: a for a in data["areas"]}
        lqd = next(m for m in areas["credit"]["members"] if m["symbol"] == "LQD")
        assert lqd["inverted"] is False


# ---------------------------------------------------------------------------
# 6. Member counts match ref_macro_area (no rows dropped/duplicated)
# ---------------------------------------------------------------------------

class TestMemberCountsMatchTable:
    def test_area_member_counts_match_ref_macro_area(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text

        with session_scope() as s:
            rows = s.execute(text(
                "SELECT area_key, COUNT(*) AS n FROM ref_macro_area "
                "WHERE enabled = TRUE GROUP BY area_key"
            )).mappings().all()
        expected = {r["area_key"]: r["n"] for r in rows}

        data = _get_macro_areas()
        for area in data["areas"]:
            key = area["area_key"]
            assert key in expected, f"Area {key!r} in response but not in ref_macro_area"
            assert len(area["members"]) == expected[key], (
                f"Area {key!r}: expected {expected[key]} members, "
                f"got {len(area['members'])}"
            )
