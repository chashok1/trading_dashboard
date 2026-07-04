"""Tests for AGENT_WORK_47 (TASK 47 + TASK 48).

TASK 47: Route all screen-facing price reads through drv_quote
         (remove raw hist_td / hist_rr price fallbacks in API layer).

TASK 48: Fix F/CS position carry-forward ceiling so weekend/holiday exports
         (snapshot_date > D) are picked up on the live anchor.

Acceptance criteria:
  A. Python syntax — all 6 changed files parse cleanly.
  B. TASK 47 — get_rr_analysis: hist_td SELECT contains only a_trend_value,
     a_trade_value (no last_price); drv_quote provides prev_close + price.
  C. TASK 47 — get_rr_history: uses drv_quote via LATERAL; no hist_td in that query.
  D. TASK 47 — marketbar: drv_quote OHLC wins; hist_rr fallback only when drv_quote
     has no row; source field set to 'drv_quote' or 'hist_rr'.
  E. TASK 47 — no raw hist_td last_price SELECTs remain anywhere in api/routers/.
  F. TASK 47 — dash.py line 835: prev_close comment confirms no raw hist_td price.
  G. TASK 48 — position_ceiling helper present in _derive_common.py.
  H. TASK 48 — position_ceiling imported and called in derive.py, derive_outlook_action.py,
     derive_actionable.py.
  I. TASK 48 — _derive_portfolio_impl uses :ceil param in both temp-table CTEs.
  J. TASK 48 — _load_holdings uses :ceil param.
  K. TASK 48 — _load_holdings_with_dollars uses :ceil param.
  L. TASK 48 — position_ceiling logic: live anchor => today; historical => as_of_date.
  M. TASK 48 — position_ceiling is a pure function (unit-testable via mock session).
  N. marketbar.py SQL strings do not exceed 965 bytes.
  O. Synthetic bar items source field: 'drv_quote' when ohlc present, 'hist_rr' when not.
  P. DEV_HANDOFF.md exists and contains ALL_DONE.

All tests are pure-Python (no DB required) unless marked with db_available.
"""
from __future__ import annotations

import ast
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DASH_PY       = PROJECT_ROOT / "api" / "routers" / "dash.py"
MARKETBAR_PY  = PROJECT_ROOT / "api" / "routers" / "marketbar.py"
DERIVE_PY     = PROJECT_ROOT / "etl" / "derive.py"
DERIVE_COMMON = PROJECT_ROOT / "etl" / "_derive_common.py"
DERIVE_OA     = PROJECT_ROOT / "etl" / "derive_outlook_action.py"
DERIVE_ACT    = PROJECT_ROOT / "etl" / "derive_actionable.py"


# ---------------------------------------------------------------------------
# A. Python syntax — all changed files parse cleanly
# ---------------------------------------------------------------------------

class TestPythonSyntax:
    """All six changed files must have valid Python syntax."""

    FILES = [
        DASH_PY,
        MARKETBAR_PY,
        DERIVE_PY,
        DERIVE_COMMON,
        DERIVE_OA,
        DERIVE_ACT,
    ]

    @pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
    def test_file_parses(self, path):
        src = path.read_text(encoding="utf-8")
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"{path.name} has a syntax error: {e}")


# ---------------------------------------------------------------------------
# B. TASK 47 — get_rr_analysis: hist_td reads only a_trend_value, a_trade_value
# ---------------------------------------------------------------------------

class TestRrAnalysisNoPriceFromHistTd:
    """get_rr_analysis in dash.py must not SELECT last_price FROM hist_td."""

    def _src(self) -> str:
        return DASH_PY.read_text(encoding="utf-8")

    def _get_rr_analysis_block(self) -> str:
        """Extract the text of get_rr_analysis up to the next @router.get."""
        src = self._src()
        start = src.find("def get_rr_analysis(")
        assert start != -1, "get_rr_analysis not found in dash.py"
        # Find next function definition at module level
        end = src.find("\n@router", start + 1)
        return src[start:end] if end != -1 else src[start:]

    def test_hist_td_select_has_no_last_price(self):
        """The hist_td query in get_rr_analysis must NOT select last_price.

        Strategy: find all text() SQL strings in the function block that mention
        hist_td, and verify none of them also contain last_price in the column list.
        """
        block = self._get_rr_analysis_block()
        # Extract SQL strings inside text(""" ... """) calls
        sql_hits = list(re.finditer(r'text\("""(.*?)"""\)', block, re.DOTALL))
        hist_td_sqls = [m.group(1) for m in sql_hits if "hist_td" in m.group(1)]
        assert hist_td_sqls, "No text() SQL referencing hist_td found in get_rr_analysis block"
        for sql in hist_td_sqls:
            # Within the SELECT column list (before FROM hist_td) check for last_price
            col_match = re.search(
                r"SELECT\s+(.*?)\s+FROM hist_td",
                sql,
                re.DOTALL | re.IGNORECASE,
            )
            if col_match:
                cols = col_match.group(1).lower()
                assert "last_price" not in cols, (
                    f"get_rr_analysis hist_td SELECT still contains last_price.\n"
                    f"Column list: {cols[:200]}"
                )

    def test_hist_td_select_has_a_trend_value(self):
        """hist_td query must still select a_trend_value (non-price data, intentionally kept)."""
        block = self._get_rr_analysis_block()
        match = re.search(
            r"SELECT\s+(.*?)\s+FROM hist_td",
            block,
            re.DOTALL | re.IGNORECASE,
        )
        assert match, "No SELECT ... FROM hist_td found inside get_rr_analysis"
        cols = match.group(1).lower()
        assert "a_trend_value" in cols, (
            "get_rr_analysis hist_td SELECT is missing a_trend_value"
        )

    def test_hist_td_select_has_a_trade_value(self):
        """hist_td query must still select a_trade_value."""
        block = self._get_rr_analysis_block()
        match = re.search(
            r"SELECT\s+(.*?)\s+FROM hist_td",
            block,
            re.DOTALL | re.IGNORECASE,
        )
        assert match, "No SELECT ... FROM hist_td found inside get_rr_analysis"
        cols = match.group(1).lower()
        assert "a_trade_value" in cols, (
            "get_rr_analysis hist_td SELECT is missing a_trade_value"
        )

    def test_prev_close_comes_from_drv_quote(self):
        """prev_close must be sourced from drv_quote (dq), not hist_td."""
        block = self._get_rr_analysis_block()
        # The assignment line should reference dq (drv_quote result), not td
        assert re.search(r"prev_close\s*=\s*_f\(dq\[", block), (
            "prev_close must be set from dq (drv_quote), not td (hist_td)"
        )

    def test_price_current_comes_from_drv_quote(self):
        """The 'current' price must be sourced from drv_quote (dq)."""
        block = self._get_rr_analysis_block()
        assert re.search(r"cur\s*=\s*_f\(dq\[", block), (
            "cur (current price) must be set from dq (drv_quote)"
        )

    def test_drv_quote_select_in_rr_analysis(self):
        """get_rr_analysis must SELECT last_price FROM drv_quote."""
        block = self._get_rr_analysis_block()
        assert re.search(r"SELECT.*last_price.*FROM drv_quote", block, re.DOTALL | re.IGNORECASE), (
            "get_rr_analysis must have a SELECT last_price ... FROM drv_quote query"
        )

    def test_tuple_indices_aligned_with_two_column_hist_td(self):
        """td[0] is a_trend_value, td[1] is a_trade_value — no td[2] access after removing last_price."""
        block = self._get_rr_analysis_block()
        # td[0] and td[1] must be used
        assert "td[0]" in block, "td[0] (a_trend_value) must be accessed"
        assert "td[1]" in block, "td[1] (a_trade_value) must be accessed"
        # td[2] must NOT be accessed (would be out-of-range for 2-column SELECT)
        assert "td[2]" not in block, (
            "td[2] accessed in get_rr_analysis but SELECT only returns 2 columns now"
        )


# ---------------------------------------------------------------------------
# C. TASK 47 — get_rr_history: drv_quote via LATERAL; no hist_td price fallback
# ---------------------------------------------------------------------------

class TestRrHistoryNoPriceFromHistTd:
    """get_rr_history in dash.py must use drv_quote for prices; no hist_td fallback."""

    def _get_rr_history_block(self) -> str:
        src = DASH_PY.read_text(encoding="utf-8")
        start = src.find("def get_rr_history(")
        assert start != -1, "get_rr_history not found in dash.py"
        end = src.find("\n@router", start + 1)
        return src[start:end] if end != -1 else src[start:]

    def test_drv_quote_lateral_present(self):
        """get_rr_history must use a LATERAL join to drv_quote."""
        block = self._get_rr_history_block()
        assert "drv_quote" in block, "drv_quote must be referenced in get_rr_history"
        assert "LATERAL" in block.upper(), (
            "get_rr_history must use a LATERAL subquery for drv_quote OHLC"
        )

    def test_no_hist_td_in_rr_history(self):
        """get_rr_history SQL must NOT reference hist_td (no COALESCE fallback).
        Only SQL strings inside text() calls are checked, not the docstring.
        """
        block = self._get_rr_history_block()
        # Check only SQL strings inside text() calls, not docstrings/comments
        for m in re.finditer(r'text\("""(.*?)"""\)', block, re.DOTALL):
            sql = m.group(1)
            assert "hist_td" not in sql, (
                f"get_rr_history SQL still references hist_td:\n{sql[:300]}"
            )

    def test_dq_last_price_used_as_close(self):
        """get_rr_history must select dq.last_price AS close."""
        block = self._get_rr_history_block()
        assert re.search(r"dq\.last_price\s+AS\s+close", block, re.IGNORECASE), (
            "get_rr_history must alias dq.last_price AS close"
        )

    def test_ohlc_columns_selected(self):
        """get_rr_history must select open/high/low from drv_quote."""
        block = self._get_rr_history_block()
        assert "open_price" in block.lower() or "dq.open_price" in block.lower(), (
            "get_rr_history must select open_price from drv_quote"
        )
        assert "high_price" in block.lower(), (
            "get_rr_history must select high_price from drv_quote"
        )
        assert "low_price" in block.lower(), (
            "get_rr_history must select low_price from drv_quote"
        )

    def test_no_coalesce_with_hist_td_in_rr_history(self):
        """No COALESCE(dq.X, td.X) patterns should remain in get_rr_history."""
        block = self._get_rr_history_block()
        # Check for COALESCE with td. prefix (old hist_td fallback)
        assert not re.search(r"COALESCE\s*\(.*dq\..*,\s*td\.", block, re.IGNORECASE | re.DOTALL), (
            "COALESCE(dq.X, td.X) hist_td fallback still present in get_rr_history"
        )


# ---------------------------------------------------------------------------
# D. TASK 47 — marketbar: drv_quote wins; hist_rr fallback only when needed
# ---------------------------------------------------------------------------

class TestMarketbarPriceRouting:
    """marketbar.py must prefer drv_quote; fall back to hist_rr only for FRED/CGI tickers."""

    def _src(self) -> str:
        return MARKETBAR_PY.read_text(encoding="utf-8")

    def test_drv_quote_ohlc_lookup_built(self):
        """marketbar.py must build an ohlc_lookup dict from drv_quote."""
        src = self._src()
        assert "ohlc_lookup" in src, "ohlc_lookup dict missing from marketbar.py"
        assert "FROM drv_quote" in src, "marketbar.py must query drv_quote for OHLC"

    def test_hist_rr_fallback_comment_present(self):
        """There must be a comment documenting the FRED/CGI gap for hist_rr fallback."""
        src = self._src()
        assert "DGS2:FRED" in src or "FRED" in src, (
            "FRED/CGI gap comment missing — marketbar.py should document why hist_rr fallback exists"
        )
        assert "hist_rr" in src, "hist_rr fallback must still exist for uncovered symbols"

    def test_drv_quote_price_preferred_in_synthetic(self):
        """Synthetic items must use ohlc['c'] (drv_quote) over hist_rr price."""
        src = self._src()
        # The preference logic: ohlc['c'] if ohlc and ohlc['c'] is not None
        assert re.search(
            r"ohlc\s*and\s*ohlc\[.c.\]\s*is not None",
            src,
        ), (
            "Synthetic item price selection must prefer ohlc['c'] (drv_quote) when present"
        )

    def test_price_source_field_set(self):
        """Each synthetic item must carry a price_source / source field."""
        src = self._src()
        assert "price_source" in src, (
            "marketbar.py must compute price_source to distinguish drv_quote vs hist_rr"
        )
        assert "'drv_quote'" in src, "source='drv_quote' must be emitted for covered symbols"
        assert "'hist_rr'" in src, "source='hist_rr' must still be emitted for FRED/CGI symbols"

    def test_source_field_assigned_in_dict(self):
        """The 'd' dict for synthetic items must include 'source': price_source."""
        src = self._src()
        assert re.search(r"'source'\s*:\s*price_source", src), (
            "Synthetic item dict must set 'source': price_source"
        )

    def test_hist_rr_query_unchanged_for_fallback(self):
        """hist_rr_price fallback dict must still be built from hist_rr."""
        src = self._src()
        assert re.search(
            r"SELECT tos_symbol, last_price FROM hist_rr",
            src,
        ), (
            "hist_rr_price fallback query missing from marketbar.py"
        )


# ---------------------------------------------------------------------------
# E. TASK 47 — No raw hist_td last_price in api/routers/ (comprehensive sweep)
# ---------------------------------------------------------------------------

class TestNoRawHistTdPriceInApi:
    """No SELECT last_price FROM hist_td (or last_price in a hist_td context) in API layer."""

    API_ROUTERS = list((PROJECT_ROOT / "api" / "routers").glob("*.py"))

    def test_api_routers_exist(self):
        assert self.API_ROUTERS, "No API router files found"

    def test_no_hist_td_last_price_select(self):
        """No text() SQL in any API router should SELECT last_price from hist_td.

        Only SQL strings inside text() calls are examined, not docstrings/comments.
        """
        violations = []
        for path in self.API_ROUTERS:
            src = path.read_text(encoding="utf-8")
            # Extract triple-quoted SQL strings from text() calls
            for m in re.finditer(r'text\("""(.*?)"""\)', src, re.DOTALL):
                sql = m.group(1)
                if "hist_td" not in sql:
                    continue
                # Now check if last_price appears in the SELECT column list
                col_match = re.search(
                    r"SELECT\s+(.*?)\s+FROM hist_td",
                    sql,
                    re.DOTALL | re.IGNORECASE,
                )
                if col_match:
                    cols = col_match.group(1).lower()
                    if "last_price" in cols:
                        violations.append(
                            f"{path.name}: last_price in SELECT...FROM hist_td SQL"
                        )
            # Also check single-line text() calls
            for m in re.finditer(r'text\("(SELECT[^"]+FROM hist_td[^"]*)"\)', src, re.IGNORECASE):
                sql = m.group(1)
                col_match = re.search(r"SELECT\s+(.*?)\s+FROM hist_td", sql, re.IGNORECASE | re.DOTALL)
                if col_match and "last_price" in col_match.group(1).lower():
                    violations.append(f"{path.name}: last_price in single-line SELECT...FROM hist_td")
        assert not violations, (
            "Raw hist_td last_price reads found in API layer SQL:\n" + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# F. TASK 47 — dash.py comment: prev_close sourced from drv_quote
# ---------------------------------------------------------------------------

class TestPrevCloseComment:
    """The prev_close line in get_rr_analysis must have a comment confirming drv_quote source."""

    def test_prev_close_comment(self):
        src = DASH_PY.read_text(encoding="utf-8")
        # Look for the comment on the prev_close line
        match = re.search(r"prev_close\s*=.*#.*drv_quote.*last_price", src, re.IGNORECASE)
        assert match, (
            "prev_close assignment missing drv_quote comment — "
            "dash.py should document that this is no longer from hist_td"
        )


# ---------------------------------------------------------------------------
# G. TASK 48 — position_ceiling helper exists in _derive_common.py
# ---------------------------------------------------------------------------

class TestPositionCeilingHelper:
    """position_ceiling must exist in _derive_common.py with correct logic."""

    def _src(self) -> str:
        return DERIVE_COMMON.read_text(encoding="utf-8")

    def test_function_defined(self):
        src = self._src()
        assert "def position_ceiling(" in src, (
            "position_ceiling function not found in _derive_common.py"
        )

    def test_queries_hist_td_for_anchor(self):
        """position_ceiling must query MAX(export_date) FROM hist_td."""
        src = self._src()
        assert re.search(
            r"SELECT MAX\(export_date\) FROM hist_td",
            src,
            re.IGNORECASE,
        ), "position_ceiling must query MAX(export_date) FROM hist_td"

    def test_returns_today_on_live_anchor(self):
        """When as_of_date == anchor, ceiling must be date.today()."""
        src = self._src()
        assert "date.today()" in src, (
            "position_ceiling must return date.today() for live anchor"
        )

    def test_returns_as_of_date_for_historical(self):
        """When as_of_date != anchor, ceiling must be as_of_date."""
        src = self._src()
        assert "as_of_date" in src, (
            "position_ceiling must return as_of_date for historical re-derives"
        )

    def test_from_sqlalchemy_text_imported(self):
        """_derive_common.py must import text from sqlalchemy (needed for position_ceiling)."""
        src = self._src()
        assert re.search(r"from sqlalchemy import.*text", src), (
            "_derive_common.py must import 'text' from sqlalchemy"
        )

    def test_docstring_mentions_weekend_holiday(self):
        """position_ceiling docstring should mention weekend/holiday use case."""
        src = self._src()
        assert re.search(r"weekend|holiday|non-trading", src, re.IGNORECASE), (
            "position_ceiling docstring must explain the weekend/holiday use case"
        )


# ---------------------------------------------------------------------------
# H. TASK 48 — position_ceiling imported and used in all three derive files
# ---------------------------------------------------------------------------

class TestPositionCeilingImported:
    """position_ceiling must be imported and called in all three derive files."""

    CALLERS = [
        (DERIVE_PY,       "_derive_portfolio_impl"),
        (DERIVE_OA,       "_load_holdings"),
        (DERIVE_ACT,      "_load_holdings_with_dollars"),
    ]

    @pytest.mark.parametrize("path,func_name", CALLERS, ids=lambda x: x if isinstance(x, str) else x.name)
    def test_import_present(self, path, func_name):
        """REWRITTEN (TASK_112, 2026-07-04): both derive.py and
        derive_outlook_action.py now import position_ceiling via a
        multi-line parenthesized `from etl._derive_common import (...)`
        block, which a `.`-based (no-DOTALL) regex can't span. Added
        re.DOTALL — same import, same source, just a multi-line statement.
        """
        src = path.read_text(encoding="utf-8")
        assert "position_ceiling" in src, (
            f"position_ceiling not found in {path.name}"
        )
        assert re.search(r"from etl\._derive_common import.*position_ceiling", src, re.DOTALL), (
            f"position_ceiling not imported from etl._derive_common in {path.name}"
        )

    @pytest.mark.parametrize("path,func_name", CALLERS, ids=lambda x: x if isinstance(x, str) else x.name)
    def test_call_present(self, path, func_name):
        """position_ceiling(...) must be called inside the relevant function."""
        src = path.read_text(encoding="utf-8")
        start = src.find(f"def {func_name}(")
        assert start != -1, f"def {func_name} not found in {path.name}"
        # Get the function body (next 60 lines should be sufficient)
        block = src[start:start + 3000]
        assert "position_ceiling(" in block, (
            f"position_ceiling() not called inside {func_name} in {path.name}"
        )


# ---------------------------------------------------------------------------
# I. TASK 48 — _derive_portfolio_impl uses :ceil in BOTH temp-table CTEs
# ---------------------------------------------------------------------------

class TestDerivPortfolioCeil:
    """_derive_portfolio_impl must use :ceil param in both hist_f and hist_cs CTEs."""

    def _get_portfolio_block(self) -> str:
        src = DERIVE_PY.read_text(encoding="utf-8")
        start = src.find("def _derive_portfolio_impl(")
        assert start != -1, "_derive_portfolio_impl not found in derive.py"
        end = src.find("\ndef ", start + 1)
        return src[start:end] if end != -1 else src[start:]

    def test_hist_f_uses_ceil(self):
        """The hist_f CTE must use :ceil in its WHERE clause."""
        block = self._get_portfolio_block()
        assert re.search(
            r"FROM hist_f.*WHERE snapshot_date\s*<=\s*:ceil",
            block,
            re.DOTALL | re.IGNORECASE,
        ), "_t_port_fid must filter hist_f WHERE snapshot_date <= :ceil"

    def test_hist_cs_uses_ceil(self):
        """The hist_cs CTE must use :ceil in its WHERE clause."""
        block = self._get_portfolio_block()
        assert re.search(
            r"FROM hist_cs.*WHERE snapshot_date\s*<=\s*:ceil",
            block,
            re.DOTALL | re.IGNORECASE,
        ), "_t_port_cs must filter hist_cs WHERE snapshot_date <= :ceil"

    def test_ceil_param_passed_to_hist_f_execute(self):
        """The hist_f temp table execute must receive {'ceil': ceil}."""
        block = self._get_portfolio_block()
        # Check that 'ceil' appears in the params dict for hist_f
        assert '"ceil"' in block or "'ceil'" in block, (
            "_derive_portfolio_impl must pass 'ceil' key to execute()"
        )

    def test_no_old_d_based_window_in_portfolio(self):
        """hist_f/hist_cs CTEs must NOT use snapshot_date <= :d (old pattern)."""
        block = self._get_portfolio_block()
        # The old pattern would be 'snapshot_date <= :d' inside the hist_f/hist_cs subqueries
        # Note: :d is still used for other things (DELETE + INSERT), so we look specifically
        # at the MAX(snapshot_date) subquery context
        matches = list(re.finditer(
            r"SELECT MAX\(snapshot_date\) FROM hist_[fc]s?\s+WHERE snapshot_date\s*<=\s*:d",
            block,
            re.DOTALL | re.IGNORECASE,
        ))
        assert not matches, (
            "_derive_portfolio_impl still uses :d in hist_f/hist_cs snapshot window "
            "(should be :ceil)"
        )


# ---------------------------------------------------------------------------
# J. TASK 48 — _load_holdings uses :ceil
# ---------------------------------------------------------------------------

class TestLoadHoldingsCeil:
    """_load_holdings in derive_outlook_action.py must use :ceil."""

    def _get_load_holdings_block(self) -> str:
        src = DERIVE_OA.read_text(encoding="utf-8")
        start = src.find("def _load_holdings(")
        assert start != -1, "_load_holdings not found in derive_outlook_action.py"
        end = src.find("\ndef ", start + 1)
        return src[start:end] if end != -1 else src[start:]

    def test_hist_f_uses_ceil(self):
        block = self._get_load_holdings_block()
        assert re.search(
            r"FROM hist_f.*WHERE snapshot_date\s*<=\s*:ceil",
            block,
            re.DOTALL | re.IGNORECASE,
        ), "_load_holdings hist_f CTE must use snapshot_date <= :ceil"

    def test_hist_cs_uses_ceil(self):
        block = self._get_load_holdings_block()
        assert re.search(
            r"FROM hist_cs.*WHERE snapshot_date\s*<=\s*:ceil",
            block,
            re.DOTALL | re.IGNORECASE,
        ), "_load_holdings hist_cs CTE must use snapshot_date <= :ceil"

    def test_ceil_passed_to_execute(self):
        block = self._get_load_holdings_block()
        assert re.search(r"\{.*['\"]ceil['\"].*:.*ceil", block, re.DOTALL), (
            "_load_holdings must pass {'ceil': ceil} to session.execute()"
        )

    def test_parameterised_not_f_string(self):
        """SQL strings inside text() must be parameterised (no f-string interpolation).

        We only check f-strings inside actual text() calls, not surrounding module code.
        """
        block = self._get_load_holdings_block()
        # Check that text() calls don't use f-strings for SQL interpolation
        # Pattern: text(f"""...""") or text(f"...")
        assert not re.search(r'text\s*\(f"""', block), (
            "_load_holdings uses f-string in text() SQL call — must use :ceil parameter"
        )
        assert not re.search(r"text\s*\(f'", block), (
            "_load_holdings uses f-string in text() SQL call — must use :ceil parameter"
        )


# ---------------------------------------------------------------------------
# K. TASK 48 — _load_holdings_with_dollars uses :ceil
# ---------------------------------------------------------------------------

class TestLoadHoldingsWithDollarsCeil:
    """_load_holdings_with_dollars in derive_actionable.py must use :ceil."""

    def _get_block(self) -> str:
        src = DERIVE_ACT.read_text(encoding="utf-8")
        start = src.find("def _load_holdings_with_dollars(")
        assert start != -1, "_load_holdings_with_dollars not found in derive_actionable.py"
        end = src.find("\ndef ", start + 1)
        return src[start:end] if end != -1 else src[start:]

    def test_hist_f_uses_ceil(self):
        block = self._get_block()
        assert re.search(
            r"FROM hist_f.*WHERE snapshot_date\s*<=\s*:ceil",
            block,
            re.DOTALL | re.IGNORECASE,
        ), "_load_holdings_with_dollars hist_f must use snapshot_date <= :ceil"

    def test_hist_cs_uses_ceil(self):
        block = self._get_block()
        assert re.search(
            r"FROM hist_cs.*WHERE snapshot_date\s*<=\s*:ceil",
            block,
            re.DOTALL | re.IGNORECASE,
        ), "_load_holdings_with_dollars hist_cs must use snapshot_date <= :ceil"

    def test_ceil_passed_to_execute(self):
        block = self._get_block()
        assert re.search(r"\{.*['\"]ceil['\"].*:.*ceil", block, re.DOTALL), (
            "_load_holdings_with_dollars must pass {'ceil': ceil} to execute()"
        )


# ---------------------------------------------------------------------------
# L & M. TASK 48 — position_ceiling logic (unit test via mock session)
# ---------------------------------------------------------------------------

class TestPositionCeilingLogic:
    """Unit-test position_ceiling behaviour without a real DB."""

    def _make_mock_session(self, anchor_date):
        """Return a mock SQLAlchemy session that returns anchor_date for MAX(export_date)."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: anchor_date if i == 0 else None
        mock_row.__bool__ = lambda self: True

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        mock_session = MagicMock()
        mock_session.execute.return_value = mock_result
        return mock_session

    def test_live_anchor_returns_today(self):
        """When as_of_date == anchor, position_ceiling must return date.today()."""
        from etl._derive_common import position_ceiling

        anchor = date.today()
        session = self._make_mock_session(anchor)
        result = position_ceiling(session, anchor)
        assert result == date.today(), (
            f"position_ceiling on live anchor should return today={date.today()}, "
            f"got {result}"
        )

    def test_historical_returns_as_of_date(self):
        """When as_of_date < anchor, position_ceiling must return as_of_date."""
        from etl._derive_common import position_ceiling

        anchor = date.today()
        historical = anchor - timedelta(days=5)
        session = self._make_mock_session(anchor)
        result = position_ceiling(session, historical)
        assert result == historical, (
            f"position_ceiling on historical date should return {historical}, "
            f"got {result}"
        )

    def test_future_as_of_date_returns_as_of_date(self):
        """When as_of_date > anchor (edge case), ceiling is as_of_date (not today)."""
        from etl._derive_common import position_ceiling

        anchor = date.today() - timedelta(days=2)
        future_date = date.today() + timedelta(days=1)  # hypothetical future re-derive
        session = self._make_mock_session(anchor)
        result = position_ceiling(session, future_date)
        assert result == future_date, (
            f"position_ceiling when as_of_date > anchor should return as_of_date={future_date}"
        )

    def test_none_anchor_returns_as_of_date(self):
        """When hist_td is empty (anchor=None), ceiling falls back to as_of_date."""
        from etl._derive_common import position_ceiling

        # Simulate empty hist_td: row[0] is None
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: None
        mock_row.__bool__ = lambda self: True

        mock_result = MagicMock()
        mock_result.first.return_value = mock_row

        session = MagicMock()
        session.execute.return_value = mock_result

        d = date(2026, 1, 15)
        result = position_ceiling(session, d)
        assert result == d, (
            f"position_ceiling with no anchor should return as_of_date={d}, got {result}"
        )

    def test_session_execute_called_with_hist_td_query(self):
        """position_ceiling must call session.execute with a hist_td MAX(export_date) query."""
        from etl._derive_common import position_ceiling

        anchor = date.today()
        session = self._make_mock_session(anchor)
        position_ceiling(session, anchor)

        assert session.execute.called, "session.execute must be called"
        call_args = session.execute.call_args
        # First arg is the text() object; its string should contain hist_td
        sql_obj = call_args[0][0]
        assert "hist_td" in str(sql_obj), (
            f"position_ceiling SQL must reference hist_td, got: {sql_obj}"
        )


# ---------------------------------------------------------------------------
# N. SQL length check — no SQL string > 965 bytes in marketbar.py
# ---------------------------------------------------------------------------

class TestSQLLength:
    """All SQL strings in marketbar.py must be <= 965 bytes."""

    def _extract_sql_strings(self) -> list[str]:
        src = MARKETBAR_PY.read_text(encoding="utf-8")
        found = []
        # Triple-quoted text() calls
        for m in re.finditer(r'text\("""(.*?)"""\)', src, re.DOTALL):
            found.append(" ".join(m.group(1).strip().split()))
        # Double-quoted standalone text() calls
        for m in re.finditer(r'text\("(SELECT\s[^"]{10,})"\)', src):
            found.append(" ".join(m.group(1).strip().split()))
        return found

    def test_no_sql_exceeds_965_bytes(self):
        sqls = self._extract_sql_strings()
        assert sqls, "No SQL strings found in marketbar.py — check extraction regex"
        violations = [(len(s), s[:120]) for s in sqls if len(s) > 965]
        assert not violations, (
            f"SQL strings exceeding 965 bytes in marketbar.py: {violations}"
        )


# ---------------------------------------------------------------------------
# O. Synthetic bar items: source logic produces correct strings
# ---------------------------------------------------------------------------

class TestSyntheticBarSourceField:
    """_SYNTHETIC_BAR1 items must carry source='drv_quote' or 'hist_rr'."""

    def test_source_drv_quote_string_present(self):
        src = MARKETBAR_PY.read_text(encoding="utf-8")
        assert "'drv_quote'" in src, (
            "marketbar.py must emit source='drv_quote' for covered symbols"
        )

    def test_source_hist_rr_string_present(self):
        src = MARKETBAR_PY.read_text(encoding="utf-8")
        assert "'hist_rr'" in src, (
            "marketbar.py must emit source='hist_rr' as fallback for FRED/CGI symbols"
        )

    def test_synthetic_items_use_price_source_variable(self):
        """The 'source' key in synthetic item dict must use the price_source variable."""
        src = MARKETBAR_PY.read_text(encoding="utf-8")
        assert re.search(r"'source'\s*:\s*price_source", src), (
            "Synthetic item must set 'source': price_source (not a hardcoded string)"
        )

    def test_fallback_logic_uses_hist_rr_price_dict(self):
        """Price fallback must look up hist_rr_price dict, not query hist_rr inline."""
        src = MARKETBAR_PY.read_text(encoding="utf-8")
        assert "hist_rr_price.get(" in src, (
            "Synthetic item must use hist_rr_price.get(rr_sym) for fallback"
        )


# ---------------------------------------------------------------------------
# P. DEV_HANDOFF.md exists and contains ALL_DONE
# ---------------------------------------------------------------------------

class TestDevHandoff:
    """DEV_HANDOFF.md must exist and signal completion."""

    def test_handoff_exists(self):
        assert (PROJECT_ROOT / "DEV_HANDOFF.md").exists(), "DEV_HANDOFF.md not found"

    def test_handoff_all_done(self):
        content = (PROJECT_ROOT / "DEV_HANDOFF.md").read_text(encoding="utf-8")
        assert "ALL_DONE" in content, "DEV_HANDOFF.md does not contain ALL_DONE"

    # test_handoff_mentions_task_47 / test_handoff_mentions_task_48 —
    # RETIRED (TASK_112 test-debt cleanup, 2026-07-04). DEV_HANDOFF.md is a
    # rolling file, overwritten fresh by every task's developer pass —
    # pinning it to AGENT_WORK_47/48-specific content is permanently stale
    # by design. Cat A per docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# Live-DB tests (auto-skip when Postgres is not available)
# ---------------------------------------------------------------------------

class TestLiveDB:
    """Live DB checks — auto-skip if Postgres is absent."""

    def test_position_ceiling_against_real_db(self, db_available):
        """position_ceiling must execute without error against the real DB."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl._derive_common import position_ceiling
        from etl.db import session_scope
        from datetime import date as date_type
        with session_scope() as s:
            result = position_ceiling(s, date_type.today())
        assert isinstance(result, date_type), (
            f"position_ceiling must return a date, got {type(result)}"
        )

    def test_rr_analysis_endpoint_returns_200(self, db_available):
        """GET /api/actionable/rr-analysis must return 200 for any known symbol."""
        if not db_available:
            pytest.skip("Postgres not available")
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        # Use a date that's likely to exist; endpoint gracefully handles missing data
        response = client.get("/api/actionable/rr-analysis?symbol=SPX&date=2026-01-01")
        assert response.status_code in (200, 404), (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )

    def test_rr_history_endpoint_returns_200(self, db_available):
        """GET /api/actionable/rr-history must return 200."""
        if not db_available:
            pytest.skip("Postgres not available")
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.get("/api/actionable/rr-history?symbol=SPX&date=2026-01-01")
        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )

    def test_marketbar_endpoint_returns_200(self, db_available):
        """GET /api/marketbar must return 200 and have as_of + items keys."""
        if not db_available:
            pytest.skip("Postgres not available")
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200, (
            f"Unexpected status {response.status_code}: {response.text[:200]}"
        )
        data = response.json()
        assert "as_of"  in data
        assert "items"  in data

    def test_synthetic_items_have_source_field(self, db_available):
        """Synthetic bar items in /api/marketbar must have 'source' field."""
        if not db_available:
            pytest.skip("Postgres not available")
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200
        data = response.json()
        synthetic_keys = {'US2Y', 'US10Y', 'US30Y', 'BZ', 'BTC', 'HYG', 'LQD'}
        for item in data.get("items", []):
            if item.get("metric_key") in synthetic_keys:
                assert "source" in item, (
                    f"Synthetic item {item.get('metric_key')!r} missing 'source' field"
                )
                # REWRITTEN (TASK_113, 2026-07-04): 'fred' added as a
                # legitimate source alongside drv_quote/hist_rr — later
                # synthetic items (macro/rate series) are sourced from FRED
                # rather than TOS quotes/RR. Legitimate new data-source
                # integration, not drift to revert.
                assert item["source"] in ("drv_quote", "hist_rr", "fred"), (
                    f"Synthetic item source must be 'drv_quote', 'hist_rr' or 'fred', "
                    f"got {item['source']!r}"
                )
