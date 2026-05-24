"""
Tests for etl.derive._eval_precondition — the safe expression evaluator
that gates composite rules in derive_stks.

Covers:
  - SQL synonyms (AND/OR/NOT/IS NULL/IS NOT NULL/IN/<>)
  - Derived aliases (is_held, is_etf, is_equity, has_position)
  - Fails-OPEN on bad input

Pure-Python: no DB needed.
"""
from __future__ import annotations

import pytest

from etl.derive import _eval_precondition as evp


class TestBasicBoolean:
    def test_empty_is_true(self):
        assert evp("", {}) is True
        assert evp("   ", {}) is True
        assert evp(None, {}) is True

    def test_simple_eq(self):
        row = {"sector": "ETF"}
        assert evp("sector == 'ETF'", row) is True
        assert evp("sector == 'Equity'", row) is False

    def test_neq(self):
        row = {"sector": "ETF"}
        assert evp("sector != 'Equity'", row) is True

    def test_and_or(self):
        row = {"sector": "Equity", "last_price": 7.5}
        assert evp("sector == 'Equity' and last_price > 5", row) is True
        assert evp("sector == 'Equity' and last_price > 100", row) is False
        assert evp("sector == 'ETF' or last_price > 5", row) is True


class TestSqlSynonyms:
    def test_sql_and_or(self):
        row = {"sector": "Equity", "last_price": 7.5}
        assert evp("sector = 'Equity' AND last_price > 5", row) is True

    def test_sql_neq(self):
        row = {"sector": "Equity"}
        assert evp("sector <> 'ETF'", row) is True

    def test_is_null(self):
        row = {"rsi": None}
        assert evp("rsi IS NULL", row) is True
        assert evp("rsi IS NOT NULL", row) is False

    def test_in_clause(self):
        row = {"sector": "Health Care"}
        assert evp("sector in ('Information Technology', 'Health Care')", row) is True
        assert evp("sector in ('Energy', 'Materials')", row) is False


class TestDerivedAliases:
    def test_is_held_truthy(self):
        assert evp("is_held", {"held_today": True}) is True
        assert evp("is_held", {"held_today": False}) is False
        assert evp("is_held", {}) is False  # missing column → False

    def test_is_etf(self):
        assert evp("is_etf", {"sector": "ETF"}) is True
        assert evp("is_etf", {"asset_class": "ETF"}) is True
        assert evp("is_etf", {"sector": "Equity"}) is False

    def test_is_equity(self):
        assert evp("is_equity", {"asset_class": "Equity"}) is True
        assert evp("is_equity", {"asset_class": "Fixed Income"}) is False

    def test_has_position(self):
        assert evp("has_position", {"current_position_dollar": 100}) is True
        assert evp("has_position", {"current_position_dollar": 0}) is False
        assert evp("has_position", {}) is False

    def test_combined_aliases(self):
        row = {"asset_class": "Equity", "held_today": False}
        assert evp("is_equity and not is_held", row) is True
        row2 = {"asset_class": "Equity", "held_today": True}
        assert evp("is_equity and not is_held", row2) is False


class TestSafetyAndFailOpen:
    def test_undefined_name_is_none(self):
        # Missing names eval to None — comparison with None returns False
        # but `is None` returns True
        row = {}
        assert evp("nonexistent IS NULL", row) is True

    def test_disallowed_node_fails_open(self):
        # Function calls aren't whitelisted — should fail OPEN (return True)
        # rather than crash or silently kill the composite.
        assert evp("len(sector) > 0", {"sector": "ETF"}) is True

    def test_bad_syntax_fails_open(self):
        assert evp("sector == ", {}) is True

    def test_attribute_access_fails_open(self):
        # ast.Attribute isn't in ALLOWED — fail open
        assert evp("sector.upper() == 'ETF'", {"sector": "ETF"}) is True
