"""Tests for AGENT_WORK_46 — Market bar tile restyle (symbol button + range bar + candle).

Acceptance criteria:
  A. DB: drv_rr.outlook column exists in baseline.sql CREATE TABLE and ALTER statement.
  B. ETL: derive.py _derive_rr_impl inserts `outlook` from hist_rr lateral join;
     BB-fallback rows get NULL outlook (no hist_rr join match).
  C. API: /api/marketbar response items include open/high/low/close + rr_outlook keys
     when drv_rr + drv_quote rows are present.
  D. API: /api/rr-bar response items include open/high/low/close, buy, sell, outlook keys.
  E. API: _build_rr_response returns 'close' == q_price (last_price).
  F. API: _build_rr_response uses row.get('name') safely (no KeyError).
  G. API: SQL strings in marketbar.py do not exceed 965 bytes.
  H. JS: web/market_bar.js passes node --check (no syntax errors).
  I. JS: market_bar.js contains outlookBg, candleSvg, rangeBarTick, tileHtml helpers.
  J. JS: market_bar.js contains renderOneItemTile (replaced renderOnePair).
  K. JS: market_bar.js contains buildRrHtml (bar 2 tile loop).
  L. CSS: styles.css contains all .mt-tile* classes required by spec.
  M. CSS: market-tape and rr-tape heights updated to 58px.
  N. CSS: rr-tape sticky top offset is 58px.

Pure-Python tests (A, C–K) need no DB. B and C/D live-DB variants auto-skip.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

WEB_DIR = PROJECT_ROOT / "web"
DB_SQL  = PROJECT_ROOT / "db" / "baseline.sql"


# ---------------------------------------------------------------------------
# A. baseline.sql — drv_rr.outlook column present
# ---------------------------------------------------------------------------

class TestBaselineSQL:
    """drv_rr.outlook must appear in both CREATE TABLE and ALTER TABLE."""

    def _read_sql(self) -> str:
        return DB_SQL.read_text(encoding="utf-8", errors="replace")

    def test_create_table_has_outlook_column(self):
        """drv_rr CREATE TABLE block must contain 'outlook TEXT'."""
        sql = self._read_sql()
        # Find the drv_rr CREATE TABLE block
        match = re.search(
            r"CREATE TABLE IF NOT EXISTS drv_rr\s*\((.*?)\);",
            sql,
            re.DOTALL | re.IGNORECASE,
        )
        assert match, "Could not find CREATE TABLE IF NOT EXISTS drv_rr in baseline.sql"
        block = match.group(1)
        assert "outlook" in block.lower(), (
            "drv_rr CREATE TABLE block does not contain 'outlook' column"
        )
        assert "TEXT" in block.upper(), (
            "drv_rr CREATE TABLE block should define outlook as TEXT"
        )

    def test_alter_table_adds_outlook(self):
        """There must be an ALTER TABLE drv_rr ADD COLUMN IF NOT EXISTS outlook statement."""
        sql = self._read_sql()
        assert re.search(
            r"ALTER TABLE drv_rr ADD COLUMN IF NOT EXISTS outlook",
            sql,
            re.IGNORECASE,
        ), "baseline.sql missing ALTER TABLE drv_rr ADD COLUMN IF NOT EXISTS outlook"

    def test_outlook_column_between_mrr_and_source(self):
        """outlook column must appear between mrr and source (per spec ordering).

        Uses line-by-line scan because the CREATE TABLE block contains comments
        with ')' which can confuse greedy regex.
        """
        sql = self._read_sql()
        # Find the start of the drv_rr table
        start = sql.lower().find("create table if not exists drv_rr")
        assert start != -1, "drv_rr CREATE TABLE not found in baseline.sql"

        # Collect lines of the block until we hit the PRIMARY KEY line which signals end
        lines = sql[start:start + 2000].splitlines()
        col_order = []
        for line in lines:
            stripped = line.strip().lower()
            if stripped.startswith("mrr"):
                col_order.append("mrr")
            elif stripped.startswith("outlook"):
                col_order.append("outlook")
            elif stripped.startswith("source") and not stripped.startswith("source_run_id"):
                col_order.append("source")

        assert "mrr"     in col_order, "mrr column not found in drv_rr block"
        assert "outlook" in col_order, "outlook column not found in drv_rr block"
        assert "source"  in col_order, "source column not found in drv_rr block"

        mrr_pos     = col_order.index("mrr")
        outlook_pos = col_order.index("outlook")
        source_pos  = col_order.index("source")
        assert mrr_pos < outlook_pos < source_pos, (
            f"Expected mrr < outlook < source. Order found: {col_order}"
        )


# ---------------------------------------------------------------------------
# B. etl/derive.py — _derive_rr_impl inserts outlook column
# ---------------------------------------------------------------------------

class TestDeriveRrImpl:
    """_derive_rr_impl must include outlook in INSERT and LATERAL subquery."""

    def _read_derive(self) -> str:
        return (PROJECT_ROOT / "etl" / "derive.py").read_text(encoding="utf-8")

    def test_insert_includes_outlook(self):
        """INSERT INTO drv_rr column list must include outlook."""
        src = self._read_derive()
        # Find the INSERT INTO drv_rr statement
        match = re.search(
            r"INSERT INTO drv_rr\s*\((.*?)\)",
            src,
            re.DOTALL,
        )
        assert match, "Could not find INSERT INTO drv_rr in derive.py"
        cols = match.group(1)
        assert "outlook" in cols, (
            f"INSERT INTO drv_rr column list does not include 'outlook': {cols}"
        )

    def test_lateral_subquery_selects_outlook(self):
        """The hist_rr LATERAL subquery must SELECT outlook."""
        src = self._read_derive()
        # Find the LATERAL subquery that selects from hist_rr
        lat_match = re.search(
            r"LEFT JOIN LATERAL\s*\(\s*SELECT buy_trade,\s*sell_trade,\s*outlook\s*FROM hist_rr",
            src,
            re.IGNORECASE | re.DOTALL,
        )
        assert lat_match, (
            "derive.py LATERAL subquery for hist_rr must SELECT buy_trade, sell_trade, outlook"
        )

    def test_outlook_selected_as_outlook(self):
        """rr.outlook AS outlook must appear in the SELECT of _derive_rr_impl."""
        src = self._read_derive()
        assert re.search(r"rr\.outlook\s+AS\s+outlook", src, re.IGNORECASE), (
            "derive.py must select rr.outlook AS outlook in _derive_rr_impl"
        )

    def test_python_syntax_valid(self):
        """etl/derive.py must parse cleanly (no syntax errors)."""
        import ast
        src = self._read_derive()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"etl/derive.py has a syntax error: {e}")


# ---------------------------------------------------------------------------
# C. API: _build_rr_response — output shape (pure Python, no DB)
# ---------------------------------------------------------------------------

class TestBuildRrResponse:
    """_build_rr_response must include OHLC keys, buy/sell, outlook, name-safety."""

    def _make_row(self, sym="AAPL", buy=150.0, sell=200.0,
                  q_price=170.0, pct=1.5, outlook="Bullish",
                  open_p=165.0, high_p=172.0, low_p=163.0):
        """Return a dict simulating a DB mapping row as produced by _RR_SQL."""
        # Use a dict that supports .get() — mirrors sqlalchemy RowMapping behaviour
        return {
            "tos_symbol":  sym,
            "buy_trade":   buy,
            "sell_trade":  sell,
            "outlook":     outlook,
            "q_price":     q_price,
            "pct":         pct,
            "open_price":  open_p,
            "high_price":  high_p,
            "low_price":   low_p,
        }

    def _call_builder(self, rows, meta=None, cat_order=None, exclude=None):
        from api.routers.marketbar import _build_rr_response, _RR_META, _CATEGORY_ORDER
        m = meta or _RR_META
        co = cat_order or _CATEGORY_ORDER
        return _build_rr_response(rows, m, co, exclude)

    def test_output_contains_open_high_low_close(self):
        """Each item in response must have open, high, low, close keys."""
        row = self._make_row(sym="AAPL", q_price=170.0, open_p=165.0,
                             high_p=172.0, low_p=163.0)
        meta = {"AAPL": ("Tech", "AAPL")}
        result = self._call_builder([row], meta=meta, cat_order=["Tech"])

        items = [item for group in result["groups"].values() for item in group]
        assert items, "No items in response"
        item = items[0]
        assert "open"  in item, f"'open' missing from item: {item}"
        assert "high"  in item, f"'high' missing from item: {item}"
        assert "low"   in item, f"'low' missing from item: {item}"
        assert "close" in item, f"'close' missing from item: {item}"

    def test_close_equals_q_price(self):
        """close must equal q_price (last_price from drv_quote)."""
        row = self._make_row(sym="AAPL", q_price=170.0)
        meta = {"AAPL": ("Tech", "AAPL")}
        result = self._call_builder([row], meta=meta, cat_order=["Tech"])

        items = [item for group in result["groups"].values() for item in group]
        item = items[0]
        assert item["close"] == pytest.approx(170.0), (
            f"Expected close==170.0 (q_price), got {item['close']}"
        )

    def test_buy_sell_outlook_present(self):
        """Each item must have buy, sell, outlook keys."""
        row = self._make_row(sym="AAPL", buy=150.0, sell=200.0, outlook="Bullish")
        meta = {"AAPL": ("Tech", "AAPL")}
        result = self._call_builder([row], meta=meta, cat_order=["Tech"])

        items = [item for group in result["groups"].values() for item in group]
        item = items[0]
        assert item["buy"]  == pytest.approx(150.0)
        assert item["sell"] == pytest.approx(200.0)
        assert item["outlook"] == "Bullish"

    def test_name_falls_back_to_sym_when_missing(self):
        """row.get('name') must not raise KeyError; falls back to sym."""
        # Row dict has no 'name' key — simulates drv_rr rows where hist_rr LEFT JOIN found nothing
        row = self._make_row(sym="AAPL")
        # Confirm there's no 'name' key in our test row
        assert "name" not in row, "Test setup error: row should not have 'name'"
        meta = {"AAPL": ("Tech", "AAPL")}
        # Must not raise KeyError
        result = self._call_builder([row], meta=meta, cat_order=["Tech"])
        items = [item for group in result["groups"].values() for item in group]
        item = items[0]
        # name should fall back to sym
        assert item["name"] == "AAPL", f"Expected name='AAPL', got {item['name']!r}"

    def test_null_ohlc_becomes_none(self):
        """When open_price/high_price/low_price are None, item keys are None."""
        row = self._make_row(sym="AAPL", open_p=None, high_p=None, low_p=None)
        meta = {"AAPL": ("Tech", "AAPL")}
        result = self._call_builder([row], meta=meta, cat_order=["Tech"])

        items = [item for group in result["groups"].values() for item in group]
        item = items[0]
        assert item["open"] is None
        assert item["high"] is None
        assert item["low"]  is None

    def test_exclude_filter_works(self):
        """Symbols in exclude set must not appear in response."""
        rows = [
            self._make_row(sym="AAPL"),
            self._make_row(sym="SPX"),
        ]
        meta = {"AAPL": ("Tech", "AAPL"), "SPX": ("Indexes", "SPX")}
        result = self._call_builder(rows, meta=meta,
                                    cat_order=["Tech", "Indexes"],
                                    exclude={"SPX"})
        all_syms = [
            item["symbol"]
            for group in result["groups"].values()
            for item in group
        ]
        assert "SPX" not in all_syms, "SPX should be excluded from bar-2 response"
        assert "AAPL" in all_syms, "AAPL should still be present"

    def test_unknown_symbol_goes_to_other(self):
        """Symbol not in meta dict should land in 'Other' group."""
        row = self._make_row(sym="UNKNOWN_SYM")
        meta = {"AAPL": ("Tech", "AAPL")}
        result = self._call_builder([row], meta=meta, cat_order=["Tech"])
        assert "Other" in result["groups"], (
            "'Other' group missing; unknown symbol should land there"
        )
        syms = [it["symbol"] for it in result["groups"]["Other"]]
        assert "UNKNOWN_SYM" in syms

    def test_response_has_groups_key(self):
        """Top-level response must have 'groups' key."""
        result = self._call_builder([], meta={}, cat_order=[])
        assert "groups" in result, f"Response missing 'groups': {result}"


# ---------------------------------------------------------------------------
# D. API: /api/marketbar response shape (pure-Python, no DB)
# ---------------------------------------------------------------------------

class TestMarketbarEndpointShape:
    """GET /api/marketbar must return as_of + items with correct new keys."""

    def test_marketbar_response_structure(self, db_available):
        """items may contain rr_buy, rr_sell, rr_outlook, open, high, low, close."""
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
        assert "as_of"  in data
        assert "items"  in data
        assert isinstance(data["items"], list)

    def test_items_have_no_unexpected_errors(self, db_available):
        """Verify no item raises on access (stale, value_format, metric_key present)."""
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200

        required_base_keys = {"metric_key", "label", "stale"}
        for item in response.json()["items"]:
            missing = required_base_keys - set(item.keys())
            assert not missing, (
                f"Item {item.get('metric_key')!r} missing required keys: {missing}"
            )

    def test_rr_bar_endpoint_returns_groups(self, db_available):
        """GET /api/rr-bar must return 200 with 'groups' key."""
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/rr-bar")
        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text[:200]}"
        )
        data = response.json()
        assert "groups" in data, f"Response missing 'groups': {data}"
        assert isinstance(data["groups"], dict)


# ---------------------------------------------------------------------------
# E. API: SQL length check — no SQL string > 965 bytes
# ---------------------------------------------------------------------------

class TestSQLLength:
    """All SQL strings in api/routers/marketbar.py must be <= 965 bytes."""

    def _extract_sql_strings(self) -> list[str]:
        src = (PROJECT_ROOT / "api" / "routers" / "marketbar.py").read_text(encoding="utf-8")
        found = []
        # Triple-quoted text() calls
        for m in re.finditer(r'text\("""(.*?)"""\)', src, re.DOTALL):
            found.append(" ".join(m.group(1).strip().split()))
        # Regular double-quoted SELECT strings (inline)
        for m in re.finditer(r'"(SELECT\s[^"]{10,})"', src):
            found.append(" ".join(m.group(1).strip().split()))
        return found

    def test_no_sql_exceeds_965_bytes(self):
        """Every SQL string must be <= 965 bytes when whitespace-normalized."""
        sqls = self._extract_sql_strings()
        assert sqls, "No SQL strings found — check extraction regex"
        violations = []
        for s in sqls:
            if len(s) > 965:
                violations.append((len(s), s[:100]))
        assert not violations, (
            f"SQL strings exceeding 965 bytes: {violations}"
        )

    def test_rr_sql_well_under_limit(self):
        """_RR_SQL (the largest SQL) must be well under 965 bytes."""
        src = (PROJECT_ROOT / "api" / "routers" / "marketbar.py").read_text(encoding="utf-8")
        matches = list(re.finditer(r'text\("""(.*?)"""\)', src, re.DOTALL))
        assert matches, "No triple-quoted text() call found in marketbar.py"
        largest = max(
            (" ".join(m.group(1).strip().split()) for m in matches),
            key=len
        )
        assert len(largest) <= 965, (
            f"Largest SQL is {len(largest)} bytes (limit 965): {largest[:100]}"
        )


# ---------------------------------------------------------------------------
# F. JS: market_bar.js syntax and content
# ---------------------------------------------------------------------------

class TestMarketBarJS:
    """web/market_bar.js must be syntactically valid and contain required helpers."""

    def _get_js(self) -> str:
        return (WEB_DIR / "market_bar.js").read_text(encoding="utf-8")

    def test_js_exists(self):
        assert (WEB_DIR / "market_bar.js").exists(), "web/market_bar.js not found"

    def test_js_syntax_via_node(self):
        """node --check web/market_bar.js must exit 0 with no output."""
        result = subprocess.run(
            ["node", "--check", str(WEB_DIR / "market_bar.js")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check failed (exit {result.returncode}):\n"
            f"stderr: {result.stderr}\nstdout: {result.stdout}"
        )

    def test_outlookBg_function_present(self):
        js = self._get_js()
        assert "function outlookBg" in js, (
            "market_bar.js missing outlookBg() helper"
        )

    def test_outlookBg_bullish_green(self):
        """outlookBg must map 'Bullish' → '#15803d'."""
        js = self._get_js()
        assert "'bullish' ? '#15803d'" in js or "=== 'bullish' ? '#15803d'" in js or \
               "bullish" in js and "#15803d" in js, (
            "outlookBg must map bullish → #15803d"
        )

    def test_outlookBg_bearish_red(self):
        """outlookBg must map 'Bearish' → '#b91c1c'."""
        js = self._get_js()
        assert "#b91c1c" in js, "outlookBg must map bearish → #b91c1c"

    def test_candleSvg_function_present(self):
        js = self._get_js()
        assert "function candleSvg" in js, (
            "market_bar.js missing candleSvg() helper"
        )

    def test_candleSvg_has_wicks(self):
        """candleSvg must draw wick lines (upper = high→bodyTop, lower = bodyBot→low)."""
        js = self._get_js()
        # Should have two <line> elements for the wicks
        assert js.count("<line") >= 2 or 'x1="8"' in js, (
            "candleSvg must draw wick lines (SVG <line> elements)"
        )

    def test_candleSvg_has_rect_body(self):
        """candleSvg must draw a <rect> body."""
        js = self._get_js()
        assert "<rect" in js, "candleSvg must include a <rect> for the candle body"

    def test_candleSvg_null_guard(self):
        """candleSvg must return '' when any of o/h/l/c is null or h<=l."""
        js = self._get_js()
        assert "h <= l" in js or "h<=l" in js or "return ''" in js, (
            "candleSvg must guard against h<=l and null values"
        )

    def test_rangeBarTick_function_present(self):
        js = self._get_js()
        assert "function rangeBarTick" in js, (
            "market_bar.js missing rangeBarTick() helper"
        )

    def test_rangeBarTick_uses_mt_rb_tick(self):
        """rangeBarTick must emit the .mt-rb-tick span."""
        js = self._get_js()
        assert "mt-rb-tick" in js, (
            "rangeBarTick must emit .mt-rb-tick span"
        )

    def test_tileHtml_function_present(self):
        js = self._get_js()
        assert "function tileHtml" in js, (
            "market_bar.js missing tileHtml() helper"
        )

    def test_tileHtml_uses_mt_tile(self):
        js = self._get_js()
        assert "mt-tile" in js, (
            "tileHtml must use .mt-tile CSS class"
        )

    def test_renderOneItemTile_present(self):
        """renderOneItemTile must replace old renderOnePair."""
        js = self._get_js()
        assert "renderOneItemTile" in js, (
            "market_bar.js must have renderOneItemTile() (replaced renderOnePair)"
        )

    def test_renderOnePair_removed(self):
        """renderOnePair is the old function and should not exist."""
        js = self._get_js()
        assert "function renderOnePair" not in js, (
            "renderOnePair() still present — should be removed or replaced by renderOneItemTile"
        )

    def test_buildRrHtml_uses_tileHtml(self):
        """buildRrHtml (bar 2) must call tileHtml for each item."""
        js = self._get_js()
        assert "buildRrHtml" in js, "market_bar.js missing buildRrHtml()"
        assert "tileHtml" in js,    "buildRrHtml must call tileHtml()"

    def test_fetches_rr_bar_endpoint(self):
        js = self._get_js()
        assert "/api/rr-bar" in js, (
            "market_bar.js must fetch /api/rr-bar for bar 2"
        )

    def test_econ_expander_preserved(self):
        """Econ ▾ expander button must still be present."""
        js = self._get_js()
        assert "Econ" in js and "mtExpandBtn" in js, (
            "Econ expander button was removed; it must be preserved"
        )

    def test_inverted_vix_logic_preserved(self):
        """VIX must still be in the INVERTED set (inversion logic preserved)."""
        js = self._get_js()
        assert "VIX" in js and "INVERTED" in js, (
            "VIX INVERTED direction logic must be preserved in renderOneItemTile"
        )

    def test_dirClass_function_present(self):
        """dirClass() function must still exist (used by renderOneItemTile)."""
        js = self._get_js()
        assert "function dirClass" in js, (
            "dirClass() helper must still be present"
        )

    def test_mtBarTrack_kept_for_compat(self):
        """mtBarTrack must still be defined (backwards compat, per handoff)."""
        js = self._get_js()
        assert "mtBarTrack" in js, (
            "mtBarTrack must still be defined for backwards compat (per DEV_HANDOFF)"
        )

    def test_open_high_low_close_keys_referenced(self):
        """JS must read item.open, item.high, item.low, item.close from API response."""
        js = self._get_js()
        assert "item.open"  in js, "JS must reference item.open"
        assert "item.high"  in js, "JS must reference item.high"
        assert "item.low"   in js, "JS must reference item.low"
        assert "item.close" in js, "JS must reference item.close"


# ---------------------------------------------------------------------------
# G. CSS: required tile classes present
# ---------------------------------------------------------------------------

class TestTileCSS:
    """web/styles.css must contain all .mt-tile* classes from spec."""

    REQUIRED_TILE_CLASSES = [
        ".mt-tile",
        ".mt-tile-body",
        ".mt-tile-top",
        ".mt-sym",
        ".mt-rb",
        ".mt-rb-fill",
        ".mt-rb-tick",
        ".mt-tile-candle",
        ".mt-candle",
    ]

    def _get_css(self) -> str:
        return (WEB_DIR / "styles.css").read_text(encoding="utf-8")

    def test_all_tile_classes_present(self):
        css = self._get_css()
        missing = [cls for cls in self.REQUIRED_TILE_CLASSES if cls not in css]
        assert not missing, (
            f"Missing CSS tile classes in styles.css: {missing}"
        )

    def test_mt_tile_width_is_180px(self):
        """Tiles must be fixed at ~180px wide (flex: 0 0 auto; width: 180px)."""
        css = self._get_css()
        mt_tile_block = re.search(
            r"\.mt-tile\s*\{([^}]*)\}",
            css,
            re.DOTALL,
        )
        assert mt_tile_block, ".mt-tile CSS block not found"
        block = mt_tile_block.group(1)
        assert "180px" in block, (
            f".mt-tile block must set width: 180px. Block: {block}"
        )

    def test_mt_tile_flex_no_shrink(self):
        """mt-tile must use flex: 0 0 auto (non-shrinking)."""
        css = self._get_css()
        mt_tile_block = re.search(
            r"\.mt-tile\s*\{([^}]*)\}",
            css,
            re.DOTALL,
        )
        assert mt_tile_block, ".mt-tile CSS block not found"
        block = mt_tile_block.group(1)
        assert "flex:" in block or "flex " in block, (
            ".mt-tile must have 'flex' property"
        )

    def test_market_tape_height_58px(self):
        """market-tape height must be updated to 58px (from old 38px)."""
        css = self._get_css()
        tape_block = re.search(
            r"\.market-tape\s*\{([^}]*)\}",
            css,
            re.DOTALL,
        )
        assert tape_block, ".market-tape CSS block not found"
        block = tape_block.group(1)
        assert "58px" in block, (
            f".market-tape height must be 58px. Block: {block}"
        )
        # Old height must NOT be present in this block
        assert "38px" not in block, (
            "Old 38px height still present in .market-tape block"
        )

    def test_rr_tape_height_58px(self):
        """rr-tape height must be updated to 58px."""
        css = self._get_css()
        rr_block = re.search(
            r"\.rr-tape\s*\{([^}]*)\}",
            css,
            re.DOTALL,
        )
        assert rr_block, ".rr-tape CSS block not found"
        block = rr_block.group(1)
        assert "58px" in block, (
            f".rr-tape height must be 58px. Block: {block}"
        )

    def test_rr_tape_sticky_top_58px(self):
        """rr-tape sticky top offset must be 58px to match new bar-1 height."""
        css = self._get_css()
        rr_block = re.search(
            r"\.rr-tape\s*\{([^}]*)\}",
            css,
            re.DOTALL,
        )
        assert rr_block, ".rr-tape CSS block not found"
        block = rr_block.group(1)
        # top: 58px must be present (was top: 38px)
        assert re.search(r"top\s*:\s*58px", block), (
            f".rr-tape must have top: 58px. Block: {block}"
        )

    def test_mt_rb_tick_is_positioned(self):
        """.mt-rb-tick must be absolutely positioned."""
        css = self._get_css()
        tick_block = re.search(
            r"\.mt-rb-tick\s*\{([^}]*)\}",
            css,
            re.DOTALL,
        )
        assert tick_block, ".mt-rb-tick CSS block not found"
        block = tick_block.group(1)
        assert "position" in block and "absolute" in block, (
            f".mt-rb-tick must be position: absolute. Block: {block}"
        )

    def test_mt_sym_has_white_color(self):
        """.mt-sym (symbol button) must have white text color (#fff)."""
        css = self._get_css()
        sym_block = re.search(
            r"\.mt-sym\s*\{([^}]*)\}",
            css,
            re.DOTALL,
        )
        assert sym_block, ".mt-sym CSS block not found"
        block = sym_block.group(1)
        assert "#fff" in block or "white" in block.lower(), (
            f".mt-sym must have color: #fff (white text). Block: {block}"
        )


# ---------------------------------------------------------------------------
# H. API Python files parse cleanly
# ---------------------------------------------------------------------------

class TestPythonSyntax:
    """All changed Python files must parse without syntax errors."""

    FILES = [
        "api/routers/marketbar.py",
        "etl/derive.py",
    ]

    @pytest.mark.parametrize("rel_path", FILES)
    def test_file_parses(self, rel_path):
        import ast
        path = PROJECT_ROOT / rel_path
        src = path.read_text(encoding="utf-8")
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"{rel_path} has a syntax error: {e}")


# ---------------------------------------------------------------------------
# I. API Python: _METRIC_TO_RR_SYMBOL mapping present
# ---------------------------------------------------------------------------

class TestMetricToRrSymbol:
    """_METRIC_TO_RR_SYMBOL must still map key index metrics to tos_symbols."""

    EXPECTED_MAPPINGS = {
        "SPX":  "SPX",
        "VIX":  "VIX",
        "COMP": "$COMP",
        "RUT":  "RUT",
    }

    def test_mapping_keys_present(self):
        from api.routers.marketbar import _METRIC_TO_RR_SYMBOL
        for k, v in self.EXPECTED_MAPPINGS.items():
            assert k in _METRIC_TO_RR_SYMBOL, (
                f"_METRIC_TO_RR_SYMBOL missing key {k!r}"
            )
            assert _METRIC_TO_RR_SYMBOL[k] == v, (
                f"_METRIC_TO_RR_SYMBOL[{k!r}] = {_METRIC_TO_RR_SYMBOL[k]!r}, expected {v!r}"
            )


# ---------------------------------------------------------------------------
# J. DEV_HANDOFF status check
# ---------------------------------------------------------------------------

class TestDevHandoff:
    """DEV_HANDOFF.md must exist and end with ALL_DONE."""

    def test_handoff_exists(self):
        handoff = PROJECT_ROOT / "DEV_HANDOFF.md"
        assert handoff.exists(), "DEV_HANDOFF.md not found"

    def test_handoff_status_all_done(self):
        handoff = PROJECT_ROOT / "DEV_HANDOFF.md"
        content = handoff.read_text(encoding="utf-8")
        assert "ALL_DONE" in content, (
            "DEV_HANDOFF.md does not contain ALL_DONE status marker"
        )

    def test_handoff_mentions_task_46(self):
        handoff = PROJECT_ROOT / "DEV_HANDOFF.md"
        content = handoff.read_text(encoding="utf-8")
        assert "46" in content or "market bar" in content.lower(), (
            "DEV_HANDOFF.md doesn't reference AGENT_WORK_46"
        )
