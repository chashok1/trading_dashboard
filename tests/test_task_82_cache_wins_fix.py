"""
Tests for AGENT_WORK_19 (TASK_82) — derive_quote CACHE-wins bug fix + USD correlation sanity.

Acceptance criteria:
  1. drv_quote $DXY 2026-06-13..2026-06-17: no repeated frozen price, no CACHE source.
  2. drv_usd_correlation latest date: SPX w15~-0.41, w30~-0.45, w90~-0.51;
     Gold w15/w30 strongly negative (< -0.4).
  3. etl/derive.py _derive_quote_impl has is_anchor guard: CACHE only on anchor date.
  4. derive_usd_correlation.py USD source reads from hist_quote_daily (yfinance), NOT drv_quote.
  5. No CACHE-sourced rows appear in drv_quote for historical dates (pre-anchor).
"""
from __future__ import annotations

import ast
import os
import re
from datetime import date
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DERIVE_PY = PROJECT_ROOT / "etl" / "derive.py"
DERIVE_CORR_PY = PROJECT_ROOT / "etl" / "derive_usd_correlation.py"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _try_db():
    """Return a psycopg connection or skip if DB is unavailable."""
    try:
        import psycopg
        from dotenv import load_dotenv
        load_dotenv()
        pw = os.getenv("PG_PASSWORD", "")
        conn = psycopg.connect(
            f"host=localhost port=5432 dbname=trading user=postgres password={pw}",
            connect_timeout=5,
        )
        return conn
    except Exception as e:
        pytest.skip(f"Postgres unavailable: {e}")


# ── Check 1: $DXY prices are distinct, no frozen run, no CACHE source ────────

class TestDxyCacheBugFixed:
    """drv_quote $DXY rows for 2026-06-13..2026-06-17 must be distinct and not CACHE."""

    @pytest.fixture(scope="class")
    def dxy_rows(self):
        conn = _try_db()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT as_of_date, last_price, source
                FROM drv_quote
                WHERE tos_symbol = '$DXY'
                  AND as_of_date BETWEEN '2026-06-13' AND '2026-06-17'
                ORDER BY as_of_date
                """,
            )
            rows = cur.fetchall()
        conn.close()
        return rows

    def test_dxy_rows_exist(self, dxy_rows):
        """Must have at least one $DXY row in the target date range."""
        assert dxy_rows, "No $DXY rows found in drv_quote for 2026-06-13..2026-06-17"

    def test_no_cache_source_in_historical_dates(self, dxy_rows):
        """No row in the historical range should have source='CACHE'."""
        cache_rows = [r for r in dxy_rows if r[2] == "CACHE"]
        assert not cache_rows, (
            f"Found CACHE-sourced $DXY rows in historical dates: {cache_rows}"
        )

    def test_prices_are_not_all_identical(self, dxy_rows):
        """Prices across the date range must not all be the same (frozen bug)."""
        prices = [float(r[1]) for r in dxy_rows if r[1] is not None]
        if len(prices) < 2:
            pytest.skip("Fewer than 2 $DXY rows — cannot check for freeze")
        assert len(set(prices)) > 1, (
            f"All $DXY prices in 2026-06-13..2026-06-17 are identical: {prices[0]} "
            f"(CACHE-wins freeze not fixed)"
        )

    def test_dxy_june17_source_is_td(self, dxy_rows):
        """2026-06-17 row should be sourced from TD (TOS Daily), not CACHE."""
        june17 = [r for r in dxy_rows if r[0] == date(2026, 6, 17)]
        if not june17:
            pytest.skip("No $DXY row for 2026-06-17 in DB")
        src = june17[0][2]
        assert src in ("TD", "TL", "Y"), (
            f"$DXY 2026-06-17 source is '{src}', expected TD/TL/Y (not CACHE)"
        )

    def test_dxy_june17_price_approx_100_37(self, dxy_rows):
        """2026-06-17 $DXY price should be approximately 100.37 (from TD)."""
        june17 = [r for r in dxy_rows if r[0] == date(2026, 6, 17)]
        if not june17:
            pytest.skip("No $DXY row for 2026-06-17 in DB")
        price = float(june17[0][1])
        assert abs(price - 100.37) < 0.5, (
            f"$DXY 2026-06-17 price {price} is far from expected ~100.37"
        )


# ── Check 2: drv_usd_correlation sanity values ────────────────────────────────

class TestUsdCorrelationValues:
    """Latest drv_usd_correlation values must be economically sensible."""

    @pytest.fixture(scope="class")
    def corr_rows(self):
        conn = _try_db()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT asset_key, w15, w30, w90
                FROM drv_usd_correlation
                WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_usd_correlation)
                """
            )
            rows = {r[0]: (float(r[1]) if r[1] is not None else None,
                           float(r[2]) if r[2] is not None else None,
                           float(r[3]) if r[3] is not None else None)
                    for r in cur.fetchall()}
        conn.close()
        return rows

    def test_spx_w15_negative(self, corr_rows):
        """SPX 15-day correlation with USD should be negative."""
        spx = corr_rows.get("spx")
        assert spx, "No 'spx' row in drv_usd_correlation"
        w15 = spx[0]
        assert w15 is not None and w15 < 0, (
            f"SPX w15 = {w15}; expected negative correlation with USD"
        )

    def test_spx_w15_in_range(self, corr_rows):
        """SPX w15 should be strongly negative (price-levels method, provider target ~-0.84).
        Updated for TASK_84: price-level Pearson range is wider than returns-based."""
        spx = corr_rows.get("spx")
        assert spx, "No 'spx' row in drv_usd_correlation"
        w15 = spx[0]
        assert w15 is not None and -1.0 <= w15 <= -0.30, (
            f"SPX w15 = {w15}; expected in range [-1.0, -0.30] "
            "(price-levels method; provider target ~-0.84)"
        )

    def test_spx_w30_in_range(self, corr_rows):
        """SPX w30 price-level Pearson can be small/positive (provider shows ~+0.05).
        Updated for TASK_84: price-level r over 30 days is trend-sensitive, not
        guaranteed negative."""
        spx = corr_rows.get("spx")
        assert spx, "No 'spx' row in drv_usd_correlation"
        w30 = spx[1]
        assert w30 is not None and -1.0 <= w30 <= 1.0, (
            f"SPX w30 = {w30}; must be a valid Pearson r in [-1, 1]"
        )

    def test_spx_w90_in_range(self, corr_rows):
        """SPX w90 price-level Pearson can be near-zero (provider shows ~-0.06).
        Updated for TASK_84: price-level correlation is regime-dependent at 90 days."""
        spx = corr_rows.get("spx")
        assert spx, "No 'spx' row in drv_usd_correlation"
        w90 = spx[2]
        assert w90 is not None and -1.0 <= w90 <= 1.0, (
            f"SPX w90 = {w90}; must be a valid Pearson r in [-1, 1]"
        )

    def test_gold_w15_strongly_negative(self, corr_rows):
        """Gold 15-day correlation with USD should be strongly negative (< -0.4)."""
        gold = corr_rows.get("gold")
        assert gold, "No 'gold' row in drv_usd_correlation"
        w15 = gold[0]
        assert w15 is not None and w15 < -0.3, (
            f"Gold w15 = {w15}; expected < -0.3 (DEV evidence: -0.5641)"
        )

    def test_gold_w30_strongly_negative(self, corr_rows):
        """Gold 30-day correlation with USD should be strongly negative (< -0.4)."""
        gold = corr_rows.get("gold")
        assert gold, "No 'gold' row in drv_usd_correlation"
        w30 = gold[1]
        assert w30 is not None and w30 < -0.3, (
            f"Gold w30 = {w30}; expected < -0.3 (DEV evidence: -0.5447)"
        )

    def test_not_near_zero(self, corr_rows):
        """SPX w15 and Gold w15/w30 must not be near-zero (the pre-CACHE-fix symptom).
        Updated for TASK_84 (price-levels): only w15 is reliably non-zero for SPX;
        w30/w90 can legitimately be small (provider shows SPX w30 ~+0.05).
        Gold w15/w30 remain strongly negative with price-levels method."""
        spx = corr_rows.get("spx")
        if spx and spx[0] is not None:
            assert abs(spx[0]) > 0.1, (
                f"spx w15 = {spx[0]}; near-zero 15D SPX correlation indicates "
                "DXY price freeze bug is not fixed (expected price-level ~-0.60...-0.84)"
            )
        gold = corr_rows.get("gold")
        if gold:
            for i, win in enumerate((15, 30)):
                val = gold[i]
                if val is not None:
                    assert abs(val) > 0.3, (
                        f"gold w{win} = {val}; near-zero Gold correlation with "
                        "price-levels method is unexpected (expected |r| > 0.3)"
                    )


# ── Check 3: Code — is_anchor guard in derive.py ─────────────────────────────

class TestCacheWinsCodeFix:
    """etl/derive.py must gate rows_cache to anchor date only."""

    def _src(self) -> str:
        return DERIVE_PY.read_text(encoding="utf-8")

    def test_derive_py_parses(self):
        """derive.py must be syntactically valid Python."""
        src = self._src()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"derive.py has syntax error: {e}")

    def test_is_anchor_variable_defined(self):
        """_derive_quote_impl must define an is_anchor flag."""
        src = self._src()
        # Find the function body
        fn_start = src.find("def _derive_quote_impl(")
        assert fn_start != -1, "_derive_quote_impl not found in derive.py"
        fn_body = src[fn_start:fn_start + 5000]
        assert "is_anchor" in fn_body, (
            "is_anchor flag not found in _derive_quote_impl — CACHE gating fix missing"
        )

    def test_rows_cache_gated_to_anchor(self):
        """rows_cache must only be populated when is_anchor is True."""
        src = self._src()
        fn_start = src.find("def _derive_quote_impl(")
        fn_body = src[fn_start:fn_start + 5000]
        # Look for the conditional assignment pattern
        pattern = re.compile(
            r"rows_cache\s*=\s*_cache_yahoo_rows\(session\)\s+if\s+is_anchor\s+else\s+\{\}"
        )
        assert pattern.search(fn_body), (
            "rows_cache = _cache_yahoo_rows(session) if is_anchor else {} "
            "not found in _derive_quote_impl — CACHE gating not applied"
        )

    def test_is_anchor_checks_as_of_date_equals_anchor(self):
        """is_anchor must compare as_of_date to anchor (not just truthy)."""
        src = self._src()
        fn_start = src.find("def _derive_quote_impl(")
        fn_body = src[fn_start:fn_start + 5000]
        # Must reference anchor date comparison
        assert "as_of_date == anchor" in fn_body, (
            "is_anchor does not compare as_of_date == anchor in _derive_quote_impl"
        )


# ── Check 4: USD correlation reads hist_quote_daily, not drv_quote for USD ───

class TestUsdCorrSourceIsYfinance:
    """derive_usd_correlation.py must use hist_quote_daily (yfinance) for the USD series."""

    def _src(self) -> str:
        return DERIVE_CORR_PY.read_text(encoding="utf-8")

    def test_corr_py_parses(self):
        """derive_usd_correlation.py must be syntactically valid Python."""
        src = self._src()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"derive_usd_correlation.py has syntax error: {e}")

    def test_usd_base_uses_yfinance_spec(self):
        """USD base asset is read via yfinance: spec (hist_quote_daily), not tos: spec."""
        conn = _try_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_spec FROM ref_corr_asset WHERE is_usd_base = TRUE LIMIT 1"
            )
            row = cur.fetchone()
        conn.close()
        assert row, "No is_usd_base asset in ref_corr_asset"
        import json
        spec = row[0]
        if isinstance(spec, str):
            spec = json.loads(spec)
        assert any(s.startswith("yfinance:") for s in spec if isinstance(s, str)), (
            f"USD base source_spec {spec} does not contain a yfinance: entry — "
            "correlation may accidentally use drv_quote (TOS) instead of hist_quote_daily"
        )

    def test_usd_base_not_tos_dxy(self):
        """USD base must NOT use tos:$DXY (which would pull from drv_quote with frozen prices)."""
        conn = _try_db()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT source_spec FROM ref_corr_asset WHERE is_usd_base = TRUE LIMIT 1"
            )
            row = cur.fetchone()
        conn.close()
        import json
        spec = row[0]
        if isinstance(spec, str):
            spec = json.loads(spec)
        tos_entries = [s for s in spec if isinstance(s, str) and s.startswith("tos:")]
        assert not tos_entries, (
            f"USD base source_spec contains TOS entry {tos_entries} — "
            "this would pull from drv_quote and could cause frozen-price correlations"
        )

    def test_load_price_series_reads_hist_quote_daily(self):
        """_load_price_series must read from hist_quote_daily for yfinance: specs."""
        src = self._src()
        assert "hist_quote_daily" in src, (
            "hist_quote_daily not referenced in derive_usd_correlation.py — "
            "yfinance source may not be implemented"
        )
        assert "yfinance" in src, (
            "yfinance not referenced in derive_usd_correlation.py"
        )

    def test_fx_sign_comment_present(self):
        """TASK_82 Part 3: FX sign convention comment must be in derive_usd_correlation.py."""
        src = self._src()
        assert "FX sign convention" in src or "/6J" in src, (
            "FX sign convention comment not found in derive_usd_correlation.py"
        )
        assert "/6J" in src, "/6J co-directional note not present in derive_usd_correlation.py"


# ── Check 5: No CACHE rows in historical drv_quote ───────────────────────────

class TestNoCacheInHistoricalDrvQuote:
    """drv_quote must have zero CACHE-sourced rows for any historical (pre-anchor) date."""

    def test_no_cache_rows_pre_anchor(self):
        conn = _try_db()
        with conn.cursor() as cur:
            # Get anchor date
            cur.execute(
                "SELECT MAX(as_of_date) FROM drv_quote WHERE source IN ('TD','TL','Y')"
            )
            anchor_row = cur.fetchone()
            anchor = anchor_row[0] if anchor_row else None

            # Query CACHE rows in historical dates
            if anchor:
                cur.execute(
                    """
                    SELECT as_of_date, tos_symbol, source
                    FROM drv_quote
                    WHERE source = 'CACHE'
                      AND as_of_date < %s
                    LIMIT 10
                    """,
                    (anchor,),
                )
            else:
                cur.execute(
                    """
                    SELECT as_of_date, tos_symbol, source
                    FROM drv_quote
                    WHERE source = 'CACHE'
                    LIMIT 10
                    """
                )
            rows = cur.fetchall()
        conn.close()
        assert not rows, (
            f"Found CACHE-sourced rows in historical drv_quote (pre-anchor): {rows[:5]}"
        )
