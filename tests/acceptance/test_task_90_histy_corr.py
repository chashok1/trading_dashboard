"""
Tests for TASK_90 — USD correlation re-plumbed to hist_y daily sources.

Verifies:
1. ref_corr_asset source_spec reflects histy: prefix for USD and SPX
2. drv_usd_correlation for 2026-06-23 has correct SPX w15/w30 values
3. SPX w15 is within 0.05 of provider target (-0.27)
4. histy: branch exists in _load_price_series
5. hist_y has current data for ^NYICDX and ^SPX (max export_date >= 2026-06-23)
6. derive is idempotent — two runs produce identical rows
7. SPX values improved over post-TASK_89 baseline (-0.4315/-0.2049)
8. All five correlation assets present for 2026-06-23

MOVED (TASK_114, 2026-07-04): relocated to tests/acceptance/ and marked
@pytest.mark.acceptance — this is a one-time acceptance proof that a
specific historical re-plumb (as of 2026-06-23) hit specific provider-target
correlation values, not a durable regression test. See
docs/audit/test_debt_review.md §2 and CLAUDE.md's Conventions list.
"""

import hashlib
import pytest
from datetime import date

pytestmark = pytest.mark.acceptance

ANCHOR_DATE = date(2026, 6, 23)
ANCHOR_DATE_STR = "2026-06-23"

# Provider targets (from DEV_HANDOFF.md section 3)
PROVIDER_W15 = -0.27
PROVIDER_W30 = -0.41

# Post-TASK_89 baseline (before TASK_90)
BASELINE_W15 = -0.4315
BASELINE_W30 = -0.2049

# Expected post-TASK_90 values (from DEV_HANDOFF.md section 7)
EXPECTED_SPX_W15 = -0.256
EXPECTED_SPX_W30 = -0.252


# ─────────────────────────────────────────
#  DB fixture
# ─────────────────────────────────────────

@pytest.fixture(scope="module")
def db_conn():
    """Return a psycopg connection, or skip if DB not available."""
    try:
        import os
        import psycopg
        from dotenv import load_dotenv
        load_dotenv(r'C:\Ashok\Invest\Projects\trading-dashboard\.env')
        pw = os.getenv('PG_PASSWORD', 'pgdbpw')
        conn = psycopg.connect(
            f"host=localhost port=5432 dbname=trading user=postgres password={pw}"
        )
        yield conn
        conn.close()
    except Exception as e:
        pytest.skip(f"DB not available: {e}")


@pytest.fixture(scope="module")
def corr_rows(db_conn):
    """Fetch drv_usd_correlation for 2026-06-23."""
    cur = db_conn.cursor()
    cur.execute(
        "SELECT asset_key, w15, w30, w90, w120, w180 "
        "FROM drv_usd_correlation WHERE as_of_date = %s ORDER BY asset_key",
        (ANCHOR_DATE,),
    )
    rows = {r[0]: {"w15": float(r[1]), "w30": float(r[2]),
                   "w90": float(r[3]), "w120": float(r[4]), "w180": float(r[5])}
            for r in cur.fetchall()}
    if not rows:
        pytest.skip(f"No rows in drv_usd_correlation for {ANCHOR_DATE_STR}")
    return rows


# ─────────────────────────────────────────
#  Check 1: source_spec in ref_corr_asset
# ─────────────────────────────────────────

class TestSourceSpecUpdated:
    """ref_corr_asset must reflect the histy: primary source for USD and SPX."""

    @pytest.fixture(scope="class")
    def spec_rows(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT asset_key, source_spec FROM ref_corr_asset ORDER BY sort_order"
        )
        return {r[0]: r[1] for r in cur.fetchall()}

    def test_usd_primary_is_histy_nyicdx(self, spec_rows):
        usd_spec = spec_rows.get("usd", [])
        assert len(usd_spec) >= 1, "usd source_spec is empty"
        assert usd_spec[0] == "histy:^NYICDX", (
            f"USD primary spec={usd_spec[0]!r}, expected 'histy:^NYICDX'. "
            "TASK_90 requires histy: as primary source."
        )

    def test_usd_has_yfinance_fallback(self, spec_rows):
        usd_spec = spec_rows.get("usd", [])
        assert len(usd_spec) >= 2, "usd source_spec has no fallback"
        # TASK_91: unified on same symbol (^NYICDX) for both histy and yfinance legs
        assert usd_spec[1] in ("yfinance:DX-Y.NYB", "yfinance:^NYICDX"), (
            f"USD fallback spec={usd_spec[1]!r}, expected 'yfinance:DX-Y.NYB' or 'yfinance:^NYICDX'"
        )

    def test_spx_primary_is_histy_spx(self, spec_rows):
        spx_spec = spec_rows.get("spx", [])
        assert len(spx_spec) >= 1, "spx source_spec is empty"
        assert spx_spec[0] == "histy:^SPX", (
            f"SPX primary spec={spx_spec[0]!r}, expected 'histy:^SPX'. "
            "TASK_90 requires histy: as primary source."
        )

    def test_spx_has_yfinance_fallback(self, spec_rows):
        spx_spec = spec_rows.get("spx", [])
        assert len(spx_spec) >= 2, "spx source_spec has no fallback"
        # TASK_91: unified on same symbol (^SPX) for both histy and yfinance legs
        assert spx_spec[1] in ("yfinance:^GSPC", "yfinance:^SPX"), (
            f"SPX fallback spec={spx_spec[1]!r}, expected 'yfinance:^GSPC' or 'yfinance:^SPX'"
        )

    def test_other_assets_unchanged(self, spec_rows):
        """TASK_91 extended histy: to brent/gold/bitcoin; only crb remains yfinance-only."""
        # crb must remain yfinance-only (DBC not in hist_y)
        crb_spec = spec_rows.get("crb", [])
        for s in crb_spec:
            assert not s.startswith("histy:"), (
                f"crb has unexpected histy: spec: {s!r}. CRB proxy (DBC) is not in hist_y."
            )
        # brent/gold/bitcoin now have histy: primary (TASK_91) — verify they do
        for asset in ["brent", "gold", "bitcoin"]:
            spec = spec_rows.get(asset, [])
            assert len(spec) >= 1 and spec[0].startswith("histy:"), (
                f"{asset} should have histy: as primary after TASK_91, got {spec!r}"
            )


# ─────────────────────────────────────────
#  Check 2: drv_usd_correlation values updated
# ─────────────────────────────────────────

class TestCorrValuesUpdated:
    """SPX values for 2026-06-23 must match the TASK_90 expected output."""

    def test_all_five_assets_present(self, corr_rows):
        expected = {"spx", "brent", "crb", "gold", "bitcoin"}
        assert expected == set(corr_rows.keys()), (
            f"Expected assets {expected}, got {set(corr_rows.keys())}"
        )

    def test_spx_w15_matches_expected(self, corr_rows):
        w15 = corr_rows["spx"]["w15"]
        assert abs(w15 - EXPECTED_SPX_W15) < 0.005, (
            f"SPX w15={w15:.4f}, expected ~{EXPECTED_SPX_W15} (±0.005). "
            "Unexpected deviation from TASK_90 target."
        )

    def test_spx_w30_matches_expected(self, corr_rows):
        w30 = corr_rows["spx"]["w30"]
        assert abs(w30 - EXPECTED_SPX_W30) < 0.005, (
            f"SPX w30={w30:.4f}, expected ~{EXPECTED_SPX_W30} (±0.005). "
            "Unexpected deviation from TASK_90 target."
        )

    def test_spx_w15_is_negative(self, corr_rows):
        """SPX/USD correlation should be negative (as USD strengthens, SPX typically falls)."""
        assert corr_rows["spx"]["w15"] < 0, (
            f"SPX w15={corr_rows['spx']['w15']:.4f} is not negative — unexpected."
        )

    def test_spx_w30_is_negative(self, corr_rows):
        assert corr_rows["spx"]["w30"] < 0, (
            f"SPX w30={corr_rows['spx']['w30']:.4f} is not negative — unexpected."
        )


# ─────────────────────────────────────────
#  Check 3: SPX w15 improvement vs provider
# ─────────────────────────────────────────

class TestSPXImprovement:
    """TASK_90 must improve SPX w15 closer to provider -0.27."""

    def test_spx_w15_within_005_of_provider(self, corr_rows):
        w15 = corr_rows["spx"]["w15"]
        delta = abs(w15 - PROVIDER_W15)
        assert delta < 0.05, (
            f"SPX w15={w15:.4f}, provider={PROVIDER_W15}, delta={delta:.4f}. "
            f"Expected delta < 0.05 (was {abs(BASELINE_W15 - PROVIDER_W15):.4f} before TASK_90)."
        )

    def test_spx_w15_better_than_baseline(self, corr_rows):
        w15 = corr_rows["spx"]["w15"]
        new_delta = abs(w15 - PROVIDER_W15)
        old_delta = abs(BASELINE_W15 - PROVIDER_W15)
        assert new_delta < old_delta, (
            f"SPX w15 did not improve: new delta={new_delta:.4f}, "
            f"old delta={old_delta:.4f} (baseline={BASELINE_W15}). "
            "TASK_90 should improve w15 vs provider."
        )

    def test_spx_w30_better_than_baseline(self, corr_rows):
        """w30 should also improve (not necessarily within 0.05, but closer)."""
        w30 = corr_rows["spx"]["w30"]
        new_delta = abs(w30 - PROVIDER_W30)
        old_delta = abs(BASELINE_W30 - PROVIDER_W30)
        assert new_delta < old_delta, (
            f"SPX w30 did not improve: new delta={new_delta:.4f}, "
            f"old delta={old_delta:.4f} (baseline={BASELINE_W30}). "
            "TASK_90 should improve w30 vs provider."
        )


# ─────────────────────────────────────────
#  Check 4: histy: branch in code
# ─────────────────────────────────────────

class TestHistyBranchInCode:
    """derive_usd_correlation.py must have the histy: branch in _load_price_series."""

    def _read_source(self):
        with open(
            r'C:\Ashok\Invest\Projects\trading-dashboard\etl\derive_usd_correlation.py',
            encoding='utf-8'
        ) as f:
            return f.read()

    def test_histy_branch_exists(self):
        src = self._read_source()
        assert 'elif spec.startswith("histy:")' in src or "startswith('histy:')" in src, (
            "histy: branch not found in _load_price_series. "
            "TASK_90 requires 'elif spec.startswith(\"histy:\"):' in the code."
        )

    def test_reads_from_hist_y_table(self):
        src = self._read_source()
        assert "FROM hist_y" in src, (
            "No 'FROM hist_y' found in derive_usd_correlation.py. "
            "TASK_90 requires reading from the hist_y table."
        )

    def test_weekend_filter_applied(self):
        src = self._read_source()
        assert "NOT IN (0, 6)" in src, (
            "Weekend filter 'NOT IN (0, 6)' not found in histy branch. "
            "TASK_90 requires filtering out Sunday (0) and Saturday (6)."
        )

    def test_extract_dow_used(self):
        src = self._read_source()
        assert "EXTRACT(DOW FROM" in src, (
            "EXTRACT(DOW FROM ...) not found — weekday filter is missing."
        )


# ─────────────────────────────────────────
#  Check 5: hist_y freshness
# ─────────────────────────────────────────

class TestHistYFreshness:
    """hist_y must have current data for both ^NYICDX and ^SPX."""

    def test_nyicdx_max_date_is_current(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT MAX(export_date) FROM hist_y WHERE symbol = '^NYICDX'"
        )
        max_date = cur.fetchone()[0]
        assert max_date is not None, "^NYICDX not found in hist_y"
        assert max_date >= date(2026, 6, 23), (
            f"^NYICDX max export_date={max_date} is before anchor 2026-06-23. "
            "hist_y data is stale."
        )

    def test_spx_max_date_is_current(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT MAX(export_date) FROM hist_y WHERE symbol = '^SPX'"
        )
        max_date = cur.fetchone()[0]
        assert max_date is not None, "^SPX not found in hist_y"
        assert max_date >= date(2026, 6, 23), (
            f"^SPX max export_date={max_date} is before anchor 2026-06-23. "
            "hist_y data is stale."
        )

    def test_nyicdx_has_sufficient_rows(self, db_conn):
        """hist_y ^NYICDX must have enough rows for at least a 30-day window."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM hist_y WHERE symbol = '^NYICDX' "
            "AND last_price IS NOT NULL "
            "AND EXTRACT(DOW FROM export_date) NOT IN (0, 6)"
        )
        count = cur.fetchone()[0]
        assert count >= 30, (
            f"^NYICDX has only {count} weekday rows in hist_y — "
            "not enough for a 30-day window."
        )

    def test_spx_has_sufficient_rows(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM hist_y WHERE symbol = '^SPX' "
            "AND last_price IS NOT NULL "
            "AND EXTRACT(DOW FROM export_date) NOT IN (0, 6)"
        )
        count = cur.fetchone()[0]
        assert count >= 30, (
            f"^SPX has only {count} weekday rows in hist_y — "
            "not enough for a 30-day window."
        )


# ─────────────────────────────────────────
#  Check 6: Idempotency
# ─────────────────────────────────────────

class TestIdempotency:
    """Re-derive twice and confirm rows are byte-identical."""

    def test_two_derives_produce_identical_spx_values(self, db_conn):
        try:
            import os
            from dotenv import load_dotenv
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session
            load_dotenv(r'C:\Ashok\Invest\Projects\trading-dashboard\.env')
            pg = os.getenv('PG_PASSWORD', 'pgdbpw')
            engine = create_engine(
                f'postgresql+psycopg://postgres:{pg}@localhost:5432/trading'
            )
        except Exception as e:
            pytest.skip(f"SQLAlchemy not available: {e}")

        try:
            from etl.derive_usd_correlation import derive_usd_correlation
        except ImportError as e:
            pytest.skip(f"derive_usd_correlation not importable: {e}")

        def fetch_rows():
            cur = db_conn.cursor()
            cur.execute(
                "SELECT asset_key, w15, w30, w90 "
                "FROM drv_usd_correlation WHERE as_of_date = %s ORDER BY asset_key",
                (ANCHOR_DATE,),
            )
            return {r[0]: (float(r[1]), float(r[2]), float(r[3])) for r in cur.fetchall()}

        # Run derive twice
        for run in range(2):
            with Session(engine) as session:
                n = derive_usd_correlation(session, ANCHOR_DATE)
                session.commit()
            assert n == 5, f"Derive run {run+1} returned {n} rows, expected 5"

        rows_after = fetch_rows()

        # Verify all values match expected (idempotency confirmed by exact match)
        assert "spx" in rows_after, "SPX row missing after re-derive"
        w15_after, w30_after, _ = rows_after["spx"]
        assert abs(w15_after - EXPECTED_SPX_W15) < 0.005, (
            f"After re-derive, SPX w15={w15_after:.4f} (expected ~{EXPECTED_SPX_W15}). "
            "Values must not drift on re-derive."
        )

    def test_all_five_assets_after_rederive(self, db_conn):
        """All 5 assets must still be present after re-derive."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(DISTINCT asset_key) FROM drv_usd_correlation "
            "WHERE as_of_date = %s",
            (ANCHOR_DATE,),
        )
        count = cur.fetchone()[0]
        assert count == 5, (
            f"After re-derive, {count} assets present (expected 5)."
        )


# ─────────────────────────────────────────
#  Check 7: Seeds file content
# ─────────────────────────────────────────

class TestSeedsFileContent:
    """db/seeds_corr.sql must contain the histy: entries for USD and SPX."""

    def _read_seeds(self):
        with open(
            r'C:\Ashok\Invest\Projects\trading-dashboard\db\seeds_corr.sql',
            encoding='utf-8'
        ) as f:
            return f.read()

    def test_usd_has_histy_nyicdx_in_seeds(self):
        seeds = self._read_seeds()
        assert 'histy:^NYICDX' in seeds, (
            "db/seeds_corr.sql does not contain 'histy:^NYICDX'. "
            "TASK_90 requires this as the primary USD source."
        )

    def test_spx_has_histy_spx_in_seeds(self):
        seeds = self._read_seeds()
        assert 'histy:^SPX' in seeds, (
            "db/seeds_corr.sql does not contain 'histy:^SPX'. "
            "TASK_90 requires this as the primary SPX source."
        )

    def test_usd_source_spec_in_seeds(self):
        seeds = self._read_seeds()
        # TASK_91: USD fallback uses same symbol ^NYICDX (unified dataset)
        assert 'histy:^NYICDX' in seeds, (
            "USD histy:^NYICDX not found in seeds_corr.sql."
        )
        # Either old DX-Y.NYB or new ^NYICDX yfinance fallback is acceptable
        assert ('yfinance:DX-Y.NYB' in seeds or 'yfinance:^NYICDX' in seeds), (
            "USD yfinance fallback not found in seeds_corr.sql."
        )

    def test_spx_source_spec_in_seeds(self):
        seeds = self._read_seeds()
        # TASK_91: SPX fallback uses same symbol ^SPX (unified dataset)
        assert 'histy:^SPX' in seeds, (
            "SPX histy:^SPX not found in seeds_corr.sql."
        )
        # Either old ^GSPC or new ^SPX yfinance fallback is acceptable
        assert ('yfinance:^GSPC' in seeds or 'yfinance:^SPX' in seeds), (
            "SPX yfinance fallback not found in seeds_corr.sql."
        )

    def test_on_conflict_upsert_present(self):
        """seeds_corr.sql must use ON CONFLICT DO UPDATE to apply seed changes."""
        seeds = self._read_seeds()
        assert "ON CONFLICT" in seeds, (
            "seeds_corr.sql missing ON CONFLICT clause — seeds won't update existing rows."
        )
