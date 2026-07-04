"""
Tests for AGENT_WORK_1 / TASK_89 — USD correlation freshness fix (2026-06-23).

Verifies that after running etl.fetch_quotes and re-deriving:
1. MAX(as_of_date) in drv_usd_correlation = 2026-06-23
2. yfinance has both 6/22 and 6/23 for ^GSPC and DX-Y.NYB
3. Panel values updated to the 6/23 window (SPX w15 ~-0.43, w30 ~-0.20)
4. 6/09 gap filled by yfinance
5. Re-derive is idempotent (same values after second run)
6. All five assets present for 6/23

MOVED (TASK_114, 2026-07-04): relocated to tests/acceptance/ and marked
@pytest.mark.acceptance — this is a one-time acceptance proof that a
specific historical re-derive (as of 2026-06-23) produced specific
correlation values, not a durable regression test (every later date makes
the exact anchor/value pins fail by construction). See
docs/audit/test_debt_review.md §2 and CLAUDE.md's Conventions list.
"""
import pytest
from datetime import date

pytestmark = pytest.mark.acceptance

ANCHOR_DATE = "2026-06-23"
ANCHOR_DATE_OBJ = date(2026, 6, 23)

# Pre-fix stale values (to confirm they changed)
STALE_SPX_W15 = -0.5992
STALE_SPX_W30 = 0.0243

# Expected fresh values (from DEV_HANDOFF.md Step 5)
EXPECTED_SPX_W15 = -0.4315
EXPECTED_SPX_W30 = -0.2049


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
def corr_rows_6_23(db_conn):
    """Fetch drv_usd_correlation for 2026-06-23."""
    cur = db_conn.cursor()
    cur.execute(
        "SELECT asset_key, w15, w30, w90 FROM drv_usd_correlation "
        "WHERE as_of_date = %s ORDER BY asset_key",
        (ANCHOR_DATE_OBJ,),
    )
    rows = {r[0]: {"w15": float(r[1]), "w30": float(r[2]), "w90": float(r[3])}
            for r in cur.fetchall()}
    if not rows:
        pytest.skip(f"No rows in drv_usd_correlation for {ANCHOR_DATE}")
    return rows


class TestCheck1MaxAsOfDate:
    """Check 1: MAX(as_of_date) = 2026-06-23."""

    def test_max_as_of_date_is_2026_06_23(self, db_conn):
        cur = db_conn.cursor()
        cur.execute("SELECT MAX(as_of_date) FROM drv_usd_correlation;")
        result = cur.fetchone()[0]
        assert result == ANCHOR_DATE_OBJ, (
            f"MAX(as_of_date) = {result!r}, expected {ANCHOR_DATE_OBJ!r}. "
            "Correlation table was not re-derived to 6/23."
        )


class TestCheck2YfinanceCoverage:
    """Check 2: yfinance has 6/22 and 6/23 for ^GSPC and DX-Y.NYB."""

    def test_gspc_has_6_22(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT obs_date FROM hist_quote_daily "
            "WHERE source='yfinance' AND symbol='^GSPC' AND obs_date='2026-06-22'"
        )
        row = cur.fetchone()
        assert row is not None, "^GSPC yfinance row for 2026-06-22 is missing."

    def test_gspc_has_6_23(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT obs_date, close FROM hist_quote_daily "
            "WHERE source='yfinance' AND symbol='^GSPC' AND obs_date='2026-06-23'"
        )
        row = cur.fetchone()
        assert row is not None, "^GSPC yfinance row for 2026-06-23 is missing."

    def test_dxy_has_6_22(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT obs_date FROM hist_quote_daily "
            "WHERE source='yfinance' AND symbol='DX-Y.NYB' AND obs_date='2026-06-22'"
        )
        row = cur.fetchone()
        assert row is not None, "DX-Y.NYB yfinance row for 2026-06-22 is missing."

    def test_dxy_has_6_23(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT obs_date, close FROM hist_quote_daily "
            "WHERE source='yfinance' AND symbol='DX-Y.NYB' AND obs_date='2026-06-23'"
        )
        row = cur.fetchone()
        assert row is not None, "DX-Y.NYB yfinance row for 2026-06-23 is missing."


class TestCheck3PanelValuesUpdated:
    """Check 3: 6/23 panel values are fresh, not stale 6/18 values."""

    def test_all_five_assets_present_for_6_23(self, corr_rows_6_23):
        expected = {"spx", "brent", "crb", "gold", "bitcoin"}
        assert expected == set(corr_rows_6_23.keys()), (
            f"Expected assets {expected!r}, got {set(corr_rows_6_23.keys())!r}"
        )

    def test_spx_w15_is_not_stale(self, corr_rows_6_23):
        """SPX w15 stale value was -0.5992; fresh should be ~-0.43."""
        w15 = corr_rows_6_23["spx"]["w15"]
        assert abs(w15 - STALE_SPX_W15) > 0.05, (
            f"SPX w15={w15:.4f} is too close to the stale value "
            f"{STALE_SPX_W15}. Possible re-derive not applied."
        )

    def test_spx_w15_close_to_expected_fresh(self, corr_rows_6_23):
        """SPX w15 fresh value should be ~-0.4315 (±0.02 for minor data variations)."""
        w15 = corr_rows_6_23["spx"]["w15"]
        assert abs(w15 - EXPECTED_SPX_W15) < 0.02, (
            f"SPX w15={w15:.4f}, expected ~{EXPECTED_SPX_W15} (±0.02). "
            "Unexpected deviation from post-fix value."
        )

    def test_spx_w30_sign_fixed(self, corr_rows_6_23):
        """SPX w30 stale was +0.02 (wrong sign); fresh should be negative ~-0.20."""
        w30 = corr_rows_6_23["spx"]["w30"]
        assert w30 < 0, (
            f"SPX w30={w30:.4f} is not negative. "
            "Pre-fix stale value was +0.02; should now be negative."
        )

    def test_spx_w30_is_not_stale(self, corr_rows_6_23):
        """SPX w30 stale was +0.0243; fresh should be ~-0.20."""
        w30 = corr_rows_6_23["spx"]["w30"]
        assert abs(w30 - STALE_SPX_W30) > 0.10, (
            f"SPX w30={w30:.4f} is too close to stale value "
            f"{STALE_SPX_W30}. Possible re-derive not applied."
        )

    def test_spx_w30_close_to_expected_fresh(self, corr_rows_6_23):
        """SPX w30 fresh value should be ~-0.2049 (±0.02)."""
        w30 = corr_rows_6_23["spx"]["w30"]
        assert abs(w30 - EXPECTED_SPX_W30) < 0.02, (
            f"SPX w30={w30:.4f}, expected ~{EXPECTED_SPX_W30} (±0.02)."
        )


class TestCheck4IdempotentFetchQuotes:
    """Check 4: Re-running fetch_quotes inserts 0 new rows for previously loaded dates.

    Note: fetch_quotes may insert today's (6/24) intraday data if it became available
    since the developer's last run at ~9:23 AM. We scope the idempotency check to
    rows through 6/23 (the anchor date), which must not change.
    """

    def test_fetch_quotes_anchor_date_rows_unchanged(self, db_conn):
        """Rows through 2026-06-23 must not increase after a second fetch_quotes run."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM hist_quote_daily "
            "WHERE source='yfinance' AND obs_date <= '2026-06-23'"
        )
        count_before = cur.fetchone()[0]

        import subprocess
        result = subprocess.run(
            ["python", "-m", "etl.fetch_quotes"],
            capture_output=True, text=True,
            cwd=r"C:\Ashok\Invest\Projects\trading-dashboard",
            timeout=60,
        )
        assert result.returncode == 0, (
            f"fetch_quotes exited with {result.returncode}: {result.stderr[:500]}"
        )

        cur.execute(
            "SELECT COUNT(*) FROM hist_quote_daily "
            "WHERE source='yfinance' AND obs_date <= '2026-06-23'"
        )
        count_after = cur.fetchone()[0]
        assert count_before == count_after, (
            f"fetch_quotes changed row count for obs_date <= 6/23 on re-run: "
            f"before={count_before}, after={count_after}. "
            "ON CONFLICT DO NOTHING should prevent duplicates for already-loaded dates."
        )

    def test_fetch_quotes_runs_without_error(self, db_conn):
        """fetch_quotes must exit 0 on re-run."""
        import subprocess
        result = subprocess.run(
            ["python", "-m", "etl.fetch_quotes"],
            capture_output=True, text=True,
            cwd=r"C:\Ashok\Invest\Projects\trading-dashboard",
            timeout=60,
        )
        assert result.returncode == 0, (
            f"fetch_quotes exited with {result.returncode}: {result.stderr[:500]}"
        )


class TestCheck5ReDeriveSameValues:
    """Check 5: Re-deriving produces identical values."""

    def test_rederive_produces_identical_w15_w30(self, db_conn, corr_rows_6_23):
        """Re-run derive_usd_correlation and confirm SPX values unchanged."""
        import sys
        sys.path.insert(0, r'C:\Ashok\Invest\Projects\trading-dashboard')
        try:
            from sqlalchemy import create_engine, text
            from sqlalchemy.orm import Session
            import os
            from dotenv import load_dotenv
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
            pytest.skip(f"derive_usd_correlation module not importable: {e}")

        with Session(engine) as session:
            derive_usd_correlation(session, ANCHOR_DATE_OBJ)
            session.commit()

        cur = db_conn.cursor()
        cur.execute(
            "SELECT asset_key, w15, w30 FROM drv_usd_correlation "
            "WHERE as_of_date = %s ORDER BY asset_key",
            (ANCHOR_DATE_OBJ,),
        )
        after = {r[0]: {"w15": float(r[1]), "w30": float(r[2])} for r in cur.fetchall()}

        for asset in ["spx", "brent", "crb", "gold", "bitcoin"]:
            before_w15 = corr_rows_6_23[asset]["w15"]
            after_w15 = after[asset]["w15"]
            assert abs(before_w15 - after_w15) < 0.0001, (
                f"{asset} w15 changed after re-derive: "
                f"before={before_w15:.4f}, after={after_w15:.4f}"
            )
            before_w30 = corr_rows_6_23[asset]["w30"]
            after_w30 = after[asset]["w30"]
            assert abs(before_w30 - after_w30) < 0.0001, (
                f"{asset} w30 changed after re-derive: "
                f"before={before_w30:.4f}, after={after_w30:.4f}"
            )


class TestCheck7June09Gap:
    """Check 7: yfinance has 2026-06-09 data for ^GSPC (fills TOS gap)."""

    def test_gspc_june09_present_in_yfinance(self, db_conn):
        cur = db_conn.cursor()
        cur.execute(
            "SELECT obs_date, close FROM hist_quote_daily "
            "WHERE source='yfinance' AND symbol='^GSPC' AND obs_date='2026-06-09'"
        )
        row = cur.fetchone()
        assert row is not None, (
            "^GSPC yfinance row for 2026-06-09 is missing. "
            "DEV_HANDOFF says yfinance filled this TOS gap."
        )

    def test_gspc_june09_close_value(self, db_conn):
        """DEV_HANDOFF says ^GSPC close on 6/09 = 7386.65 from yfinance."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT close FROM hist_quote_daily "
            "WHERE source='yfinance' AND symbol='^GSPC' AND obs_date='2026-06-09'"
        )
        row = cur.fetchone()
        if row is None:
            pytest.skip("^GSPC 2026-06-09 not present — run Check 7 first")
        close = float(row[0])
        assert abs(close - 7386.65) < 5.0, (
            f"^GSPC 6/09 close={close:.2f}, expected ~7386.65. "
            "Unexpected data value."
        )

    def test_dxy_june09_present_in_yfinance(self, db_conn):
        """DEV_HANDOFF says DX-Y.NYB 6/09 = 99.91 from yfinance."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT obs_date, close FROM hist_quote_daily "
            "WHERE source='yfinance' AND symbol='DX-Y.NYB' AND obs_date='2026-06-09'"
        )
        row = cur.fetchone()
        assert row is not None, (
            "DX-Y.NYB yfinance row for 2026-06-09 is missing."
        )
