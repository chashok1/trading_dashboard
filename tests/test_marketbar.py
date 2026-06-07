"""
Tests for etl/marketbar.py (resolver + adapters) and GET /api/marketbar.

Acceptance criteria (AGENT_WORK_6):
  1. Fall-through: metric with ["realtime:X","tos:SPX"] — realtime stub returns
     None, resolver falls through to tos adapter and returns a tos result.
  2. Fred fallback: resolver uses fred adapter when tos has no symbol.
  3. Stale flag: stale=True when as_of < anchor_date, stale=False when equal.
  4. Endpoint smoke test (DB-dependent, auto-skips if Postgres absent):
     GET /api/marketbar returns 200, exactly 10 items, each with required keys.

Pure-Python tests (1-3) use mocked adapters — no DB needed.
Test 4 uses the project conftest `db_available` fixture.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers — build a minimal metric registry row
# ---------------------------------------------------------------------------

def _metric_row(
    metric_key: str = "SPX",
    label: str = "S&P 500",
    grp: str = "index",
    source_priority: list | None = None,
    value_format: str = "index",
    sort_order: int = 10,
) -> dict:
    return {
        "metric_key": metric_key,
        "label": label,
        "grp": grp,
        "source_priority": source_priority or [],
        "value_format": value_format,
        "sort_order": sort_order,
    }


def _tos_result(as_of: date = date(2026, 6, 5)) -> dict:
    return {
        "value": 5300.12,
        "chg": -12.5,
        "chg_pct": -0.24,
        "as_of": as_of,
        "source": "tos",
    }


def _fred_result(as_of: date = date(2026, 6, 4)) -> dict:
    return {
        "value": 4.32,
        "chg": 0.05,
        "chg_pct": 1.17,
        "as_of": as_of,
        "source": "fred",
    }


# ---------------------------------------------------------------------------
# 1. Fall-through: realtime returns None → resolver uses tos
# ---------------------------------------------------------------------------

class TestResolverFallThrough:
    """realtime stub always returns None; resolver must fall through to tos."""

    def test_realtime_none_falls_through_to_tos(self):
        from etl.marketbar import resolve_metric, _ADAPTERS

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=["realtime:X", "tos:SPX"])

        # Patch _ADAPTERS in-place so resolve_metric uses our fakes
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=anchor)

        with patch.dict(
            "etl.marketbar._ADAPTERS",
            {
                "realtime": lambda session, sym: None,
                "tos": lambda session, sym: tos_result if sym == "SPX" else None,
            },
        ):
            result = resolve_metric(row, mock_session, anchor)

        assert result["source"] == "tos", (
            f"Expected source='tos' after realtime fall-through, got {result['source']!r}"
        )
        assert result["value"] == 5300.12
        assert result["stale"] is False  # as_of == anchor

    def test_realtime_adapter_itself_returns_none(self):
        """The real _realtime_adapter stub must return None unconditionally."""
        from etl.marketbar import _realtime_adapter

        session = MagicMock()
        assert _realtime_adapter(session, "ANYTHING") is None
        assert _realtime_adapter(session, "") is None

    def test_all_adapters_return_none_gives_null_result(self):
        """When every adapter returns None, value/source are None and stale=True."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=["realtime:X", "tos:MISSING"])

        mock_session = MagicMock()

        with patch.dict(
            "etl.marketbar._ADAPTERS",
            {
                "realtime": lambda session, sym: None,
                "tos": lambda session, sym: None,
            },
        ):
            result = resolve_metric(row, mock_session, anchor)

        assert result["value"] is None
        assert result["source"] is None
        assert result["stale"] is True


# ---------------------------------------------------------------------------
# 2. Fred fallback: resolver picks fred when tos has no result
# ---------------------------------------------------------------------------

class TestFredFallback:
    """When tos adapter returns None, resolver must use fred adapter."""

    def test_tos_none_falls_back_to_fred(self):
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        fred_as_of = date(2026, 6, 4)
        row = _metric_row(
            metric_key="US10Y",
            source_priority=["fred:DGS10"],
        )

        mock_session = MagicMock()
        fred_result = _fred_result(as_of=fred_as_of)

        with patch.dict(
            "etl.marketbar._ADAPTERS",
            {
                "fred": lambda session, sym: fred_result if sym == "DGS10" else None,
            },
        ):
            result = resolve_metric(row, mock_session, anchor)

        assert result["source"] == "fred"
        assert result["value"] == 4.32
        # fred data is from prior day → stale
        assert result["stale"] is True

    def test_tos_none_then_fred_succeeds(self):
        """Priority list has tos first, then fred; tos returns None → fred wins."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        fred_as_of = date(2026, 6, 4)
        row = _metric_row(
            metric_key="VIX",
            source_priority=["tos:VIX", "fred:VIXCLS"],
        )

        mock_session = MagicMock()
        fred_result = _fred_result(as_of=fred_as_of)

        with patch.dict(
            "etl.marketbar._ADAPTERS",
            {
                "tos": lambda session, sym: None,
                "fred": lambda session, sym: fred_result,
            },
        ):
            result = resolve_metric(row, mock_session, anchor)

        assert result["source"] == "fred"
        assert result["value"] == 4.32

    def test_fred_symbol_passed_correctly(self):
        """Adapter receives the symbol that follows the colon."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=["fred:BAMLH0A0HYM2"])

        captured = {}
        mock_session = MagicMock()

        def fake_fred(session, sym):
            captured["sym"] = sym
            return _fred_result()

        with patch.dict("etl.marketbar._ADAPTERS", {"fred": fake_fred}):
            resolve_metric(row, mock_session, anchor)

        assert captured.get("sym") == "BAMLH0A0HYM2"


# ---------------------------------------------------------------------------
# 3. Stale flag
# ---------------------------------------------------------------------------

class TestStaleFlag:
    """stale=True when as_of < anchor_date; stale=False when as_of == anchor_date."""

    def test_stale_true_when_as_of_before_anchor(self):
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        as_of = date(2026, 6, 4)  # one day behind
        row = _metric_row(source_priority=["tos:SPX"])
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=as_of)

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor)

        assert result["stale"] is True, (
            f"Expected stale=True when as_of={as_of} < anchor={anchor}"
        )

    def test_stale_false_when_as_of_equals_anchor(self):
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        as_of = date(2026, 6, 5)  # matches anchor
        row = _metric_row(source_priority=["tos:SPX"])
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=as_of)

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor)

        assert result["stale"] is False, (
            f"Expected stale=False when as_of={as_of} == anchor={anchor}"
        )

    def test_stale_true_when_no_result(self):
        """No adapter returns a value → stale must be True."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=[])
        mock_session = MagicMock()

        result = resolve_metric(row, mock_session, anchor)

        assert result["stale"] is True

    def test_stale_true_when_anchor_is_none(self):
        """If anchor_date is None (empty DB), stale must be True."""
        from etl.marketbar import resolve_metric

        row = _metric_row(source_priority=["tos:SPX"])
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=date(2026, 6, 5))

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor=None)

        assert result["stale"] is True

    def test_stale_true_when_as_of_is_none(self):
        """If adapter returns as_of=None, stale must be True."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=["tos:SPX"])
        mock_session = MagicMock()
        tos_result = {
            "value": 5000.0,
            "chg": None,
            "chg_pct": None,
            "as_of": None,
            "source": "tos",
        }

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor)

        assert result["stale"] is True

    def test_stale_false_when_as_of_after_anchor(self):
        """as_of > anchor (e.g. intraday refresh) → not stale."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 4)
        as_of = date(2026, 6, 5)
        row = _metric_row(source_priority=["tos:SPX"])
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=as_of)

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor)

        assert result["stale"] is False


# ---------------------------------------------------------------------------
# Resolver output shape
# ---------------------------------------------------------------------------

class TestResolveMetricOutputShape:
    """resolve_metric must always return a dict with every required key."""

    REQUIRED_KEYS = {
        "metric_key", "label", "grp", "value_format", "sort_order",
        "value", "chg", "chg_pct", "as_of", "source", "stale",
    }

    def test_all_keys_present_with_data(self):
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=["tos:SPX"])
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=anchor)

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor)

        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys in resolve_metric output: {missing}"

    def test_all_keys_present_without_data(self):
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=[])
        mock_session = MagicMock()

        result = resolve_metric(row, mock_session, anchor)

        missing = self.REQUIRED_KEYS - set(result.keys())
        assert not missing, f"Missing keys when no adapter returns data: {missing}"

    def test_as_of_is_iso_string_or_none(self):
        """as_of in output must be an ISO-format string or None."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=["tos:SPX"])
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=anchor)

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor)

        as_of_val = result["as_of"]
        assert as_of_val is None or isinstance(as_of_val, str), (
            f"as_of should be str or None, got {type(as_of_val)}"
        )
        if as_of_val is not None:
            # Must be parseable as ISO date
            date.fromisoformat(as_of_val)

    def test_registry_fields_passed_through(self):
        """metric_key, label, grp, value_format, sort_order come from the row."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(
            metric_key="HY",
            label="HY spread",
            grp="credit",
            value_format="pct",
            sort_order=100,
            source_priority=[],
        )
        mock_session = MagicMock()

        result = resolve_metric(row, mock_session, anchor)

        assert result["metric_key"] == "HY"
        assert result["label"] == "HY spread"
        assert result["grp"] == "credit"
        assert result["value_format"] == "pct"
        assert result["sort_order"] == 100


# ---------------------------------------------------------------------------
# Edge cases for source_priority parsing
# ---------------------------------------------------------------------------

class TestSourcePriorityParsing:
    """Invalid or empty source_priority entries must not raise."""

    def test_empty_priority_list(self):
        from etl.marketbar import resolve_metric

        row = _metric_row(source_priority=[])
        mock_session = MagicMock()
        result = resolve_metric(row, mock_session, anchor=date(2026, 6, 5))
        assert result["value"] is None

    def test_none_priority_list(self):
        from etl.marketbar import resolve_metric

        row = _metric_row(source_priority=None)
        mock_session = MagicMock()
        result = resolve_metric(row, mock_session, anchor=date(2026, 6, 5))
        assert result["value"] is None

    def test_unknown_adapter_is_skipped(self):
        """An unknown adapter name logs a warning and is skipped."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=["unknown_adapter:SYM", "tos:SPX"])
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=anchor)

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor)

        # Should fall through to tos
        assert result["source"] == "tos"

    def test_entry_missing_colon_is_skipped(self):
        """Entry without a colon logs a warning and is skipped."""
        from etl.marketbar import resolve_metric

        anchor = date(2026, 6, 5)
        row = _metric_row(source_priority=["BADENTRY", "tos:SPX"])
        mock_session = MagicMock()
        tos_result = _tos_result(as_of=anchor)

        with patch.dict("etl.marketbar._ADAPTERS", {"tos": lambda s, sym: tos_result}):
            result = resolve_metric(row, mock_session, anchor)

        assert result["source"] == "tos"


# ---------------------------------------------------------------------------
# 4. Endpoint smoke test — DB-dependent, auto-skips if Postgres absent
# ---------------------------------------------------------------------------

class TestMarketbarEndpoint:
    """GET /api/marketbar smoke test: 200, 10 items, all required keys present."""

    REQUIRED_ITEM_KEYS = {
        "metric_key", "label", "grp", "value_format", "sort_order",
        "value", "chg", "chg_pct", "as_of", "source", "stale",
    }

    EXPECTED_METRIC_KEYS = {
        "SPX", "COMP", "DJI", "RUT", "VIX",
        "US10Y", "T2S10", "DXY", "WTI", "HY",
    }

    def test_endpoint_returns_200_with_10_items(self, db_available):
        """GET /api/marketbar must return 200 with exactly 10 items."""
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text[:200]}"
        )

        data = response.json()
        assert "items" in data, f"Response missing 'items' key: {data}"
        assert "as_of" in data, f"Response missing 'as_of' key: {data}"

        items = data["items"]
        assert len(items) == 10, (
            f"Expected 10 items, got {len(items)}. "
            "Did you run `python -m db.init_db` with the seed file?"
        )

    def test_items_have_required_keys(self, db_available):
        """Every item in the response must have all required keys."""
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200

        items = response.json()["items"]
        for item in items:
            missing = self.REQUIRED_ITEM_KEYS - set(item.keys())
            assert not missing, (
                f"Item {item.get('metric_key')} missing keys: {missing}"
            )

    def test_items_ordered_by_sort_order(self, db_available):
        """Items must be in ascending sort_order (10, 20, ..., 100)."""
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200

        items = response.json()["items"]
        sort_orders = [item["sort_order"] for item in items]
        assert sort_orders == sorted(sort_orders), (
            f"Items not sorted by sort_order: {sort_orders}"
        )
        # The 10 seeded rows have sort_order 10,20,...,100
        assert sort_orders == list(range(10, 101, 10)), (
            f"Expected sort_orders [10,20,...,100], got {sort_orders}"
        )

    def test_all_expected_metric_keys_present(self, db_available):
        """All 10 seeded metric keys must be present in the response."""
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200

        items = response.json()["items"]
        returned_keys = {item["metric_key"] for item in items}
        missing = self.EXPECTED_METRIC_KEYS - returned_keys
        assert not missing, f"Missing metric keys: {missing}"

    def test_stale_field_is_boolean(self, db_available):
        """stale field on every item must be a boolean."""
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200

        items = response.json()["items"]
        for item in items:
            assert isinstance(item["stale"], bool), (
                f"stale for {item['metric_key']} is not bool: {item['stale']!r}"
            )

    def test_ref_market_metric_table_has_10_rows(self, db_available):
        """Direct DB check: ref_market_metric must have exactly 10 enabled rows."""
        if not db_available:
            pytest.skip("Postgres not available")

        from etl.db import session_scope
        from sqlalchemy import text

        with session_scope() as s:
            row = s.execute(
                text("SELECT COUNT(*) AS n FROM ref_market_metric WHERE enabled")
            ).mappings().first()

        assert row["n"] == 10, (
            f"Expected 10 enabled rows in ref_market_metric, found {row['n']}. "
            "Run `python -m db.init_db` to apply seeds_market_metric.sql."
        )
