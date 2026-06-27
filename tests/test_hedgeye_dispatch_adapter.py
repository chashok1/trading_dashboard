"""
Tests for etl/hedgeye/dispatch.py::_adapt_rows() — pure-Python, no DB.

Verifies the column reconciliation logic added in TASK_93 Step 2:
  - hist_iichg / hist_etfchg: snapshot_date renamed to event_date
  - hist_macro: message_id stripped; source defaulted to 'HEDGEYE'
  - all other tables: rows pass through unchanged
  - empty input: returns empty list without crashing
"""
from __future__ import annotations

import pytest

from etl.hedgeye.dispatch import _adapt_rows


# ── hist_iichg ────────────────────────────────────────────────────────────────

def test_iichg_renames_snapshot_date_to_event_date():
    rows = [{"snapshot_date": "2026-06-26", "symbol": "RMD",
             "action": "add", "side": "short", "message_id": "<m@h>"}]
    adapted = _adapt_rows("hist_iichg", rows)
    assert len(adapted) == 1
    assert "event_date" in adapted[0]
    assert "snapshot_date" not in adapted[0]
    assert adapted[0]["event_date"] == "2026-06-26"


def test_iichg_preserves_other_columns():
    rows = [{"snapshot_date": "2026-06-26", "symbol": "RMD",
             "action": "add", "side": "short", "message_id": "<m@h>"}]
    adapted = _adapt_rows("hist_iichg", rows)[0]
    assert adapted["symbol"] == "RMD"
    assert adapted["action"] == "add"
    assert adapted["side"] == "short"
    assert adapted["message_id"] == "<m@h>"


def test_iichg_multi_row():
    rows = [
        {"snapshot_date": "2026-06-25", "symbol": "A"},
        {"snapshot_date": "2026-06-26", "symbol": "B"},
    ]
    adapted = _adapt_rows("hist_iichg", rows)
    assert len(adapted) == 2
    assert all("event_date" in r for r in adapted)
    assert all("snapshot_date" not in r for r in adapted)


# ── hist_etfchg ───────────────────────────────────────────────────────────────

def test_etfchg_renames_snapshot_date_to_event_date():
    rows = [{"snapshot_date": "2026-06-26", "symbol": "QTUM",
             "action": "remove", "side": "long", "message_id": "<e@h>"}]
    adapted = _adapt_rows("hist_etfchg", rows)
    assert len(adapted) == 1
    assert "event_date" in adapted[0]
    assert "snapshot_date" not in adapted[0]
    assert adapted[0]["event_date"] == "2026-06-26"


def test_etfchg_preserves_other_columns():
    rows = [{"snapshot_date": "2026-06-26", "symbol": "BUG",
             "action": "remove", "side": "long", "message_id": "<e@h>"}]
    adapted = _adapt_rows("hist_etfchg", rows)[0]
    assert adapted["symbol"] == "BUG"
    assert adapted["action"] == "remove"
    assert adapted["side"] == "long"


# ── hist_macro ────────────────────────────────────────────────────────────────

def test_macro_strips_message_id():
    rows = [{"series_id": "HE_CPI_NOWCAST", "obs_date": "2026-06-01",
             "value": 3.2, "message_id": "<m@h>"}]
    adapted = _adapt_rows("hist_macro", rows)
    assert "message_id" not in adapted[0]


def test_macro_adds_source_hedgeye_default():
    rows = [{"series_id": "HE_CPI_NOWCAST", "obs_date": "2026-06-01", "value": 3.2,
             "message_id": "<m@h>"}]
    adapted = _adapt_rows("hist_macro", rows)
    assert adapted[0]["source"] == "HEDGEYE"


def test_macro_does_not_overwrite_existing_source():
    """setdefault means an explicit source is kept unchanged."""
    rows = [{"series_id": "FRED_CPI", "obs_date": "2026-06-01", "value": 3.0,
             "source": "FRED", "message_id": "<m@h>"}]
    adapted = _adapt_rows("hist_macro", rows)
    assert adapted[0]["source"] == "FRED"


def test_macro_preserves_other_columns():
    rows = [{"series_id": "HE_CPI_NOWCAST", "obs_date": "2026-06-01",
             "value": 3.2, "message_id": "<m@h>", "extra": "x"}]
    adapted = _adapt_rows("hist_macro", rows)[0]
    assert adapted["series_id"] == "HE_CPI_NOWCAST"
    assert adapted["obs_date"] == "2026-06-01"
    assert adapted["value"] == 3.2
    assert adapted["extra"] == "x"


# ── passthrough tables ────────────────────────────────────────────────────────

@pytest.mark.parametrize("table", [
    "hist_rr", "hist_rta", "hist_call", "hist_call_top5",
    "hist_hedgeye_stance", "hist_sss_change", "hist_ps", "note_repo",
])
def test_other_tables_pass_through_unchanged(table):
    rows = [{"symbol": "AAPL", "outlook": "BULLISH", "message_id": "<m@h>"}]
    adapted = _adapt_rows(table, rows)
    assert adapted == rows


# ── edge cases ────────────────────────────────────────────────────────────────

def test_empty_rows_returns_empty_for_iichg():
    assert _adapt_rows("hist_iichg", []) == []


def test_empty_rows_returns_empty_for_macro():
    assert _adapt_rows("hist_macro", []) == []


def test_empty_rows_returns_empty_for_passthrough():
    assert _adapt_rows("hist_rr", []) == []


def test_original_row_not_mutated_iichg():
    """_adapt_rows must not modify the caller's original dict."""
    original = {"snapshot_date": "2026-06-26", "symbol": "X"}
    row = dict(original)
    _adapt_rows("hist_iichg", [row])
    assert row == original  # row was NOT mutated


def test_original_row_not_mutated_macro():
    original = {"series_id": "HE_CPI_NOWCAST", "value": 3.2, "message_id": "<m>"}
    row = dict(original)
    _adapt_rows("hist_macro", [row])
    # message_id should still be in the original dict
    assert "message_id" in row


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
