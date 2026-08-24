"""
Regression coverage for the Dashboard screen's (`web/index.html`, route "/")
middle column (`.cat-col`) — 6 grids total:

  1-3. `$` grids (Sector / Asset Class / Style) — client: `web/app.js::loadFactorScorecard()`
       → `GET /api/cockpit/factor-scorecard?axis=...` (api/routers/cockpit.py::get_factor_scorecard)
  4-6. Market View grids (Sector / Asset Class / Style, count-based, "no $, no
       holdings") — client: `web/app.js::loadMarketView()`
       → `GET /api/quad/factor-stance?axis=...` (api/routers/dash.py::get_quad_factor_stance)
       (`loadMarketView` also re-fetches the factor-scorecard endpoint purely
       to join in `bench_*` figures by category — no separate bench endpoint.)

This is *behavior/schema* coverage per CLAUDE.md's test-debt policy (§ "Test-
debt policy"): every assertion below checks field presence/type/shape, never
a specific point-in-time number, palette hex, or inline style. Point-in-time
$ figures move every trading session; asserting an exact number here would be
guaranteed test debt.

The client-side "Returns column total row" (`loadFactorScorecard()`'s
`_retTotalDollar`/`_retTotalRow` math) is rendered entirely in the browser —
this repo has no JS test runner (confirmed: no `package.json`/jest/mocha/
node test config anywhere in the tree, and CLAUDE.md's cheat sheet lists only
`pytest`). That specific client-side arithmetic therefore needs a manual/
browser check (load `/`, switch the "Returns" period radio, eyeball the
Total row); this file instead locks down that the *inputs* to that math
(`market_value`, `twr_<period>` per row, for every one of the 5 windows the
period selector cycles through: today/yesterday/mtd/qtd/ytd) are present and
correctly typed on every row — since that's what the total row sums.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


AXES = ["sector", "asset_class", "style"]

# The 5 "Returns" period windows the dashboard's period-selector radio group
# cycles through (web/app.js::_FS_WINDOWS) — twr_<key>/bench_<key> pairs.
RETURN_WINDOWS = ["today", "yesterday", "mtd", "qtd", "ytd"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client() -> TestClient:
    from api.main import app
    return TestClient(app)


def _get_factor_scorecard(client: TestClient, axis: str, **params) -> dict:
    resp = client.get("/api/cockpit/factor-scorecard", params={"axis": axis, **params})
    assert resp.status_code == 200, (
        f"GET /api/cockpit/factor-scorecard?axis={axis} -> {resp.status_code}: {resp.text[:300]}"
    )
    return resp.json()


def _get_factor_stance(client: TestClient, axis: str, **params) -> dict:
    resp = client.get("/api/quad/factor-stance", params={"axis": axis, **params})
    assert resp.status_code == 200, (
        f"GET /api/quad/factor-stance?axis={axis} -> {resp.status_code}: {resp.text[:300]}"
    )
    return resp.json()


def _is_null_or_number(v) -> bool:
    return v is None or isinstance(v, (int, float)) and not isinstance(v, bool)


# ---------------------------------------------------------------------------
# Grids 1-3 — $ grids: GET /api/cockpit/factor-scorecard?axis=...
# ---------------------------------------------------------------------------

class TestFactorScorecardTopLevelShape:
    """Response envelope loadFactorScorecard() reads: as_of/axis/risk_budget/
    accounts/rows/unmapped."""

    @pytest.mark.parametrize("axis", AXES)
    def test_top_level_keys_present(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        for key in ("as_of", "axis", "risk_budget", "accounts", "rows", "unmapped"):
            assert key in data, f"axis={axis}: missing top-level key {key!r}"
        assert data["axis"] == axis
        assert isinstance(data["rows"], list)

    @pytest.mark.parametrize("axis", AXES)
    def test_rows_non_empty_on_a_normal_day(self, db_available, axis):
        """Not a hard schema requirement, but a portfolio with zero rows for
        any of the 3 axes on the anchor date would itself be a red flag worth
        surfacing rather than silently passing an empty-list schema check."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        assert len(data["rows"]) > 0, f"axis={axis}: expected at least one category row"


class TestFactorScorecardRowFields:
    """Per-row field presence/type — category, weight_pct, market_value,
    twr_<w>/bench_<w> for w in today/yesterday/mtd/qtd/ytd."""

    @pytest.mark.parametrize("axis", AXES)
    def test_category_is_non_empty_string(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        for row in data["rows"]:
            assert isinstance(row["category"], str) and row["category"].strip(), (
                f"axis={axis}: row has non-string/empty category: {row.get('category')!r}"
            )

    @pytest.mark.parametrize("axis", AXES)
    def test_weight_pct_is_null_or_0_to_100(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        for row in data["rows"]:
            v = row["weight_pct"]
            assert _is_null_or_number(v), f"axis={axis} cat={row['category']}: weight_pct not null/number: {v!r}"
            if v is not None:
                assert -0.01 <= v <= 100.01, f"axis={axis} cat={row['category']}: weight_pct out of 0-100: {v}"

    @pytest.mark.parametrize("axis", AXES)
    def test_market_value_is_null_or_numeric(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        for row in data["rows"]:
            assert _is_null_or_number(row["market_value"]), (
                f"axis={axis} cat={row['category']}: market_value not null/number: {row['market_value']!r}"
            )

    @pytest.mark.parametrize("axis", AXES)
    def test_twr_and_bench_period_fields_are_null_or_numeric(self, db_available, axis):
        """The 5 windows the Returns-period radio group and every window
        column in the $ grids read: twr_today/yesterday/mtd/qtd/ytd and the
        matching bench_* counterparts (web/app.js::_FS_WINDOWS)."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        for row in data["rows"]:
            for w in RETURN_WINDOWS:
                for prefix in ("twr_", "bench_"):
                    key = f"{prefix}{w}"
                    assert key in row, f"axis={axis} cat={row['category']}: missing field {key!r}"
                    assert _is_null_or_number(row[key]), (
                        f"axis={axis} cat={row['category']}: {key}={row[key]!r} not null/number"
                    )

    def test_asset_class_rows_have_no_weight_pct_equities(self, db_available):
        """asset_class IS the total-portfolio view (that's the axis whose
        weight_pct denominator already covers cash/bonds/etc), so
        weight_pct_equities (a re-basing against the equity sleeve only) is
        never populated for it — see etl/derive_category_perf.py's own
        schema comment on drv_category_perf.weight_pct_equities."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), "asset_class")
        for row in data["rows"]:
            assert row.get("weight_pct_equities") is None, (
                f"asset_class cat={row['category']}: expected weight_pct_equities=None, "
                f"got {row.get('weight_pct_equities')!r}"
            )

    @pytest.mark.parametrize("axis", ["sector", "style"])
    def test_sector_style_rows_carry_weight_pct_equities(self, db_available, axis):
        """Sector/Style are equity-only axes re-based against the equity
        sleeve; at least one row on a normal day should carry a numeric
        weight_pct_equities (not universally null/absent, i.e. the field is
        actually wired up, not just present-but-always-null)."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        for row in data["rows"]:
            assert "weight_pct_equities" in row, (
                f"axis={axis} cat={row['category']}: weight_pct_equities key missing entirely"
            )
        numeric_rows = [r for r in data["rows"] if r["weight_pct_equities"] is not None]
        assert numeric_rows, f"axis={axis}: expected at least one row with a numeric weight_pct_equities"
        for row in numeric_rows:
            assert -0.01 <= row["weight_pct_equities"] <= 100.01, (
                f"axis={axis} cat={row['category']}: weight_pct_equities out of 0-100: "
                f"{row['weight_pct_equities']}"
            )


class TestFactorScorecardUnmapped:
    """`unmapped` — a synthetic row for holdings that didn't resolve to a
    category, pulled out of `rows` by the API layer (api/routers/cockpit.py::
    get_factor_scorecard) into its own top-level key."""

    @pytest.mark.parametrize("axis", AXES)
    def test_unmapped_is_null_or_dict_with_weight_and_value_fields(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        u = data["unmapped"]
        if u is None:
            return  # a portfolio with zero unmapped $ for this axis is valid
        assert isinstance(u, dict)
        for key in ("weight_pct", "weight_pct_equities", "market_value"):
            assert key in u, f"axis={axis}: unmapped missing {key!r}"
            assert _is_null_or_number(u[key]), f"axis={axis}: unmapped.{key}={u[key]!r} not null/number"

    @pytest.mark.parametrize("axis", AXES)
    def test_unmapped_category_label(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        u = data["unmapped"]
        if u is None:
            return
        assert u.get("category") == "Unmapped"

    @pytest.mark.parametrize("axis", AXES)
    def test_unmapped_DOES_carry_twr_and_bench_fields(self, db_available, axis):
        """Confirmed against the live endpoint (not assumed): `unmapped` is
        pulled out of the SAME `drv_category_perf` row set as every other
        category (api/routers/cockpit.py::get_factor_scorecard — `if
        rd["category"] == "Unmapped": unmapped = rd`), so it carries the
        identical column set as a normal row, including twr_*/bench_* — it
        is NOT a stripped-down $-only summary object. bench_* is null in
        practice (Unmapped has no single benchmark ETF proxy), but the KEYS
        are present either way, same as every other row."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        u = data["unmapped"]
        if u is None:
            return
        for w in RETURN_WINDOWS:
            for prefix in ("twr_", "bench_"):
                key = f"{prefix}{w}"
                assert key in u, f"axis={axis}: unmapped missing {key!r} (expected present, even if null)"
                assert _is_null_or_number(u[key])


class TestFactorScorecardBadAxis:
    def test_invalid_axis_returns_400(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        resp = _client().get("/api/cockpit/factor-scorecard", params={"axis": "bogus"})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Cash special case (asset_class axis only) — regression test for the
# "Cash should not have gain or loss" fix in etl/derive_category_perf.py.
# Before the fix, unnetted cash-balance movements (sweeps, dividends landing
# in cash, wires) could masquerade as Cash "performance."
# ---------------------------------------------------------------------------

class TestCashHasNoReturn:
    def test_cash_row_all_twr_and_bench_null_via_live_recompute(self, db_session):
        """Authoritative check of the FIX ITSELF: calls
        etl.derive_category_perf._compute_category_rows(session, anchor_date)
        directly — the exact function both the nightly full-portfolio derive
        and the API's live per-account recompute path share (see that
        function's own docstring: "accounts=None means unfiltered ... byte-
        identical queries"). This exercises current on-disk code against
        live data without depending on whether `drv_category_perf` (a
        precomputed, DELETE+INSERT-per-derive-run table) has been re-derived
        for today since the fix landed — i.e. it can't produce a false pass
        OR a false fail purely due to precomputed-table staleness."""
        from etl.derive import get_anchor_date
        from etl.derive_category_perf import _compute_category_rows

        d = get_anchor_date(db_session)
        if d is None:
            pytest.skip("No anchor date resolvable (empty hist_td) — cannot compute category rows")
        rows = _compute_category_rows(db_session, d)
        cash_rows = [r for r in rows if r["axis"] == "asset_class" and r["category"] == "Cash"]
        assert cash_rows, "Expected a 'Cash' row on the asset_class axis"
        cash = cash_rows[0]
        for w in RETURN_WINDOWS:
            for prefix in ("twr_", "bench_"):
                key = f"{prefix}{w}"
                assert cash.get(key) is None, (
                    f"Cash.{key} expected None (Cash must not show gain/loss), got {cash.get(key)!r}"
                )

    def test_cash_row_present_via_live_api(self, db_available):
        """API-level smoke check that the Cash row itself is reachable
        through the real HTTP path (schema presence only — the definitive
        null-value assertion is the direct-function test above, which is
        immune to precomputed-table staleness; see TEST_REPORT for a note on
        whether the live default (no-`accounts`) endpoint's currently-stored
        `drv_category_perf` data reflects this fix as of test time)."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), "asset_class")
        cash_rows = [r for r in data["rows"] if r["category"] == "Cash"]
        assert cash_rows, "Expected a 'Cash' row in GET /api/cockpit/factor-scorecard?axis=asset_class"

    def test_cash_row_all_twr_and_bench_null_via_live_api_default_path(self, db_available):
        """Same assertion as the direct-function test above, but through the
        actual default (no `accounts` filter) HTTP path a real page load
        uses — i.e. reading straight from the precomputed `drv_category_perf`
        table rather than recomputing live. This can only pass once that
        table has been (re-)derived for the current as_of_date AFTER the fix
        landed in etl/derive_category_perf.py; see TEST_REPORT for whether
        that was true at test time."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), "asset_class")
        cash_rows = [r for r in data["rows"] if r["category"] == "Cash"]
        assert cash_rows, "Expected a 'Cash' row in GET /api/cockpit/factor-scorecard?axis=asset_class"
        cash = cash_rows[0]
        bad = {f"{p}{w}": cash.get(f"{p}{w}")
               for w in RETURN_WINDOWS for p in ("twr_", "bench_")
               if cash.get(f"{p}{w}") is not None}
        assert not bad, (
            f"Cash row via the default (precomputed-table) API path still has non-null "
            f"twr_*/bench_* fields: {bad} — drv_category_perf likely needs a re-derive "
            f"for the current as_of_date to pick up the Cash-nulling fix"
        )

    def test_cash_row_via_accounts_filter_live_recompute_path(self, db_available):
        """Same assertion via the OTHER live path the API already exposes —
        `?accounts=<n>` triggers _compute_category_rows() live (bypassing
        the precomputed table entirely), so this should pass regardless of
        drv_category_perf staleness as long as the requested account holds
        any cash."""
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        accts = client.get("/api/actionable/accounts")
        if accts.status_code != 200 or not accts.json():
            pytest.skip("No accounts available from /api/actionable/accounts")
        for acct in accts.json():
            data = _get_factor_scorecard(client, "asset_class", accounts=acct["account_number"])
            cash_rows = [r for r in data["rows"] if r["category"] == "Cash"]
            if not cash_rows:
                continue  # this account may hold no cash at all
            cash = cash_rows[0]
            for w in RETURN_WINDOWS:
                for prefix in ("twr_", "bench_"):
                    key = f"{prefix}{w}"
                    assert cash.get(key) is None, (
                        f"account={acct['account_number']}: Cash.{key} expected None, got {cash.get(key)!r}"
                    )
            return  # found and checked at least one account with a Cash row
        pytest.skip("No account in this portfolio currently holds a Cash position to check")


# ---------------------------------------------------------------------------
# Grids 4-6 — Market View: GET /api/quad/factor-stance?axis=...
# ---------------------------------------------------------------------------

class TestFactorStanceTopLevelShape:
    @pytest.mark.parametrize("axis", AXES)
    def test_top_level_keys_present(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_stance(_client(), axis)
        for key in ("as_of_date", "axis", "rows", "total_count"):
            assert key in data, f"axis={axis}: missing top-level key {key!r}"
        assert data["axis"] == axis
        assert isinstance(data["rows"], list)
        assert isinstance(data["total_count"], int)

    @pytest.mark.parametrize("axis", AXES)
    def test_rows_non_empty_on_a_normal_day(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_stance(_client(), axis)
        assert len(data["rows"]) > 0, f"axis={axis}: expected at least one category row"


class TestFactorStanceRowFields:
    """Market View is explicitly "zero dependency on what you hold" — count-
    based, not $-based. Verify the actual shape rather than assuming."""

    @pytest.mark.parametrize("axis", AXES)
    def test_category_and_count_present_and_typed(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_stance(_client(), axis)
        for row in data["rows"]:
            assert isinstance(row["category"], str) and row["category"].strip()
            assert isinstance(row["count"], int), (
                f"axis={axis} cat={row['category']}: count not int: {row['count']!r}"
            )
            assert row["count"] >= 0

    @pytest.mark.parametrize("axis", AXES)
    def test_rows_have_no_market_value_or_weight_pct_keys(self, db_available, axis):
        """Confirmed against the live endpoint: Market View rows carry no
        $-based fields at all — count replaces weight_pct as the sizing
        signal, matching the "no money involved" design (web/app.js's own
        comment above loadMarketView())."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_stance(_client(), axis)
        for row in data["rows"]:
            assert "market_value" not in row, f"axis={axis} cat={row['category']}: unexpected market_value key"
            assert "weight_pct" not in row, f"axis={axis} cat={row['category']}: unexpected weight_pct key"

    @pytest.mark.parametrize("axis", AXES)
    def test_rows_have_no_twr_or_mine_fields(self, db_available, axis):
        """Market View has no "mine" data by design (web/app.js comment:
        "_fsReturnsBarCell gets mine=null"). bench_* comes from a SEPARATE
        join against /api/cockpit/factor-scorecard done client-side in
        loadMarketView() — this endpoint's own rows carry no bench_*/twr_*
        fields of their own."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_stance(_client(), axis)
        for row in data["rows"]:
            for w in RETURN_WINDOWS:
                assert f"twr_{w}" not in row, f"axis={axis} cat={row['category']}: unexpected twr_{w} key"
                assert f"bench_{w}" not in row, f"axis={axis} cat={row['category']}: unexpected bench_{w} key"

    @pytest.mark.parametrize("axis", AXES)
    def test_score_stance_and_caret_cluster_fields(self, db_available, axis):
        """Fields _quadCaretCluster() (web/app.js) reads to render the caret
        row: score (number or null), stance (string), months (list),
        qtr/next_qtr (dict or null)."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_stance(_client(), axis)
        for row in data["rows"]:
            assert _is_null_or_number(row.get("score")), (
                f"axis={axis} cat={row['category']}: score not null/number: {row.get('score')!r}"
            )
            assert isinstance(row.get("stance"), str) and row["stance"], (
                f"axis={axis} cat={row['category']}: stance not a non-empty string"
            )
            assert isinstance(row.get("months"), list), (
                f"axis={axis} cat={row['category']}: months not a list"
            )
            for key in ("qtr", "next_qtr"):
                v = row.get(key)
                assert v is None or isinstance(v, dict), (
                    f"axis={axis} cat={row['category']}: {key} not null/dict: {v!r}"
                )


class TestFactorStanceJoinsBenchFromScorecard:
    """web/app.js::loadMarketView() joins this endpoint's rows against
    GET /api/cockpit/factor-scorecard (same axis) by lower/trim(category) to
    pull in bench_<period> for the Returns column and per-window cells. This
    confirms the join key actually lines up between the two endpoints (a
    silent category-name-casing mismatch would make every Market View
    Returns cell render as the "no bench" dash)."""

    @pytest.mark.parametrize("axis", AXES)
    def test_category_names_overlap_between_endpoints(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        client = _client()
        stance = _get_factor_stance(client, axis)
        scorecard = _get_factor_scorecard(client, axis)
        stance_keys = {r["category"].strip().lower() for r in stance["rows"]}
        scorecard_keys = {r["category"].strip().lower() for r in scorecard["rows"]}
        overlap = stance_keys & scorecard_keys
        assert overlap, (
            f"axis={axis}: no overlapping category names between /api/quad/factor-stance "
            f"({sorted(stance_keys)[:5]}...) and /api/cockpit/factor-scorecard "
            f"({sorted(scorecard_keys)[:5]}...) — the client-side bench_* join would silently "
            f"produce zero matches"
        )


class TestFactorStanceBadAxis:
    def test_invalid_axis_returns_200_with_error_field_and_empty_rows(self, db_available):
        """Documented actual behavior (not a 400, unlike the $ grid endpoint
        — api/routers/dash.py::get_quad_factor_stance returns a 200 with an
        `error` field + empty `rows` when the axis doesn't map to a known
        ref_quad_outlook category)."""
        if not db_available:
            pytest.skip("Postgres not available")
        resp = _client().get("/api/quad/factor-stance", params={"axis": "bogus"})
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data
        assert data["rows"] == []

    def test_missing_axis_returns_422(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        resp = _client().get("/api/quad/factor-stance")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Returns-column total row (web/app.js::loadFactorScorecard) — client-side
# math only; see module docstring. This section locks down the API-side
# inputs that math depends on.
# ---------------------------------------------------------------------------

class TestReturnsColumnTotalRowInputs:
    """`loadFactorScorecard()`'s total row sums, per row:
        rowMineDollar = market_value * twr_<selected period> / 100
    across all non-Unmapped rows, for whichever of the 5 RETURN_WINDOWS the
    period radio group has selected — see the module docstring for why the
    arithmetic itself isn't covered by an automated test here."""

    @pytest.mark.parametrize("axis", AXES)
    def test_every_row_has_market_value_and_all_5_period_twr_fields(self, db_available, axis):
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        for row in data["rows"]:
            assert _is_null_or_number(row["market_value"])
            for w in RETURN_WINDOWS:
                assert _is_null_or_number(row[f"twr_{w}"])

    @pytest.mark.parametrize("axis", AXES)
    def test_total_row_dollar_math_is_computable_from_typed_fields(self, db_available, axis):
        """Reproduces loadFactorScorecard()'s total-row arithmetic in Python
        against the live API response, for every one of the 5 periods, as a
        sanity check that the inputs never contain a type that would make
        the client-side sum silently produce NaN (e.g. a string instead of a
        number) — not a check of any specific total value."""
        if not db_available:
            pytest.skip("Postgres not available")
        data = _get_factor_scorecard(_client(), axis)
        for w in RETURN_WINDOWS:
            total_dollar = 0.0
            total_mv = 0.0
            for row in data["rows"]:
                mv = row["market_value"]
                twr = row[f"twr_{w}"]
                if mv is None or twr is None:
                    continue
                row_dollar = mv * twr / 100.0
                assert row_dollar == row_dollar, (  # NaN check (NaN != NaN)
                    f"axis={axis} w={w} cat={row['category']}: total-row math produced NaN "
                    f"from market_value={mv!r}, twr_{w}={twr!r}"
                )
                total_dollar += row_dollar
                total_mv += mv
            assert total_dollar == total_dollar  # never NaN overall
