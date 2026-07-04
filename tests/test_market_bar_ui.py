"""
Tests for AGENT_WORK_8 — global market tape UI implementation.

Acceptance criteria (AGENT_WORK_8):
  1. web/market_bar.js exists and is valid JS (no syntax errors).
  2. Every HTML page that loads warning_badge.js also loads market_bar.js
     (script tag parity — same 15 files).
  3. [RETIRED — TASK_110] web/cockpit.html no longer loads macro_band.js and
     has no macroCard div. cockpit.html was deleted outright in TASK_109
     (/cockpit is now a bare 301 redirect); see the retirement note below.
  4. web/styles.css contains the tape CSS classes (.market-tape, .mt-cell,
     .mt-up, .mt-down, .mt-stale, etc.).
  5. market_bar.js injection pattern mirrors warning_badge.js
     (script tag placed immediately before warning_badge.js on each page).
  6. GET /api/marketbar endpoint regression (DB-dependent, auto-skips if absent).
  7. market_bar.js contains required structural elements:
     - INVERTED set with VIX/HY keys
     - /api/marketbar fetch
     - /api/macro fetch (econ expander)
     - 60s auto-refresh
     - DOMContentLoaded guard
"""
from __future__ import annotations

import glob
import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_html(filename: str) -> str:
    path = WEB_DIR / filename
    return path.read_text(encoding="utf-8")


def _all_html_files() -> list[Path]:
    return sorted(WEB_DIR.glob("*.html"))


# ---------------------------------------------------------------------------
# 1. JS syntax check
# ---------------------------------------------------------------------------

class TestJSSyntax:
    """web/market_bar.js must pass node --check (zero syntax errors)."""

    def test_market_bar_js_exists(self):
        js_path = WEB_DIR / "market_bar.js"
        assert js_path.exists(), f"market_bar.js not found at {js_path}"

    def test_market_bar_js_syntax(self):
        js_path = WEB_DIR / "market_bar.js"
        result = subprocess.run(
            ["node", "--check", str(js_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"node --check failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        # node --check outputs nothing on success
        assert result.stdout.strip() == "", (
            f"node --check produced unexpected output: {result.stdout!r}"
        )

    def test_market_bar_js_not_empty(self):
        js_path = WEB_DIR / "market_bar.js"
        content = js_path.read_text(encoding="utf-8")
        assert len(content) > 200, "market_bar.js is suspiciously short"


# ---------------------------------------------------------------------------
# 2. Script tag parity — market_bar.js must be on same pages as warning_badge.js
# ---------------------------------------------------------------------------

class TestScriptTagParity:
    """Every HTML page with warning_badge.js must also have market_bar.js."""

    def _files_with_script(self, tag_pattern: str) -> set[str]:
        result = set()
        for html_file in _all_html_files():
            try:
                content = html_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = html_file.read_text(encoding="cp1252")
            if tag_pattern in content:
                result.add(html_file.name)
        return result

    def test_parity_count_matches(self):
        wb_files = self._files_with_script("warning_badge.js")
        mb_files = self._files_with_script("market_bar.js")
        assert len(wb_files) == len(mb_files), (
            f"File count mismatch: warning_badge.js in {len(wb_files)} files, "
            f"market_bar.js in {len(mb_files)} files"
        )

    def test_same_exact_files(self):
        wb_files = self._files_with_script("warning_badge.js")
        mb_files = self._files_with_script("market_bar.js")

        has_wb_not_mb = wb_files - mb_files
        has_mb_not_wb = mb_files - wb_files

        assert not has_wb_not_mb, (
            f"Files with warning_badge.js but NOT market_bar.js: {sorted(has_wb_not_mb)}"
        )
        assert not has_mb_not_wb, (
            f"Files with market_bar.js but NOT warning_badge.js: {sorted(has_mb_not_wb)}"
        )

    def test_market_bar_covers_the_large_majority_of_pages(self):
        """REWRITTEN (TASK_112, 2026-07-04): the page set has grown past 18
        (now 21+ web/*.html files) as new screens were added, so an exact
        frozen count is the wrong invariant — it breaks on every legitimate
        new page. Assert market_bar.js covers the large majority of pages
        (a floor, not an exact count) instead of pinning a stale total."""
        all_files = _all_html_files()
        mb_files = self._files_with_script("market_bar.js")
        assert len(all_files) >= 18, (
            f"Page count regressed below the historical floor of 18: {len(all_files)}"
        )
        coverage = len(mb_files) / len(all_files)
        assert coverage >= 0.8, (
            f"market_bar.js covers only {coverage:.0%} of {len(all_files)} pages "
            f"({len(mb_files)} have it) — expected broad (>=80%) coverage. "
            f"Pages missing it: {sorted(set(f.name for f in all_files) - mb_files)}"
        )

    def test_market_bar_tag_before_warning_badge_tag(self):
        """market_bar.js script tag must appear before warning_badge.js on each page."""
        pages_with_wrong_order = []
        for html_file in _all_html_files():
            try:
                content = html_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = html_file.read_text(encoding="cp1252")
            if "warning_badge.js" not in content or "market_bar.js" not in content:
                continue
            mb_pos = content.find("market_bar.js")
            wb_pos = content.find("warning_badge.js")
            if mb_pos > wb_pos:
                pages_with_wrong_order.append(html_file.name)

        assert not pages_with_wrong_order, (
            f"market_bar.js appears AFTER warning_badge.js on: {pages_with_wrong_order}. "
            "market_bar.js must be loaded before warning_badge.js."
        )


# ---------------------------------------------------------------------------
# 3. Macro band retired from cockpit — RETIRED (TASK_110 test cleanup)
# ---------------------------------------------------------------------------
# TASK_109 deleted web/cockpit.html outright (the route is now a bare 301
# redirect to /actionable — see api/routers/pages.py::page_cockpit). There is
# no cockpit.html left to read, so every assertion below that opened the file
# raised FileNotFoundError. Since the whole page (not just the macro_band.js
# script tag) is gone, there is no meaningful "did cockpit.html drop
# macro_band.js" check left to perform, and no clean /actionable equivalent —
# /actionable's own macro-band wiring is already covered by
# test_agent_work_39.py::TestTask7_CockpitRetirement. Retired rather than
# rewritten.


# ---------------------------------------------------------------------------
# 4. CSS classes present in styles.css
# ---------------------------------------------------------------------------

class TestCSSClasses:
    """web/styles.css must contain the market tape CSS classes."""

    # REWRITTEN (TASK_112, 2026-07-04): '.mt-asof' removed from the required
    # list — the as-of timestamp is no longer a dedicated CSS-classed
    # element; market_bar.js now renders it as a plain inline-styled string
    # ("as of " + date, see the tape-item builder), confirmed via grep (0
    # matches for '.mt-asof' anywhere in styles.css or market_bar.js). Every
    # other required class below still exists (in styles.css and/or
    # market_bar.js) and was verified via grep before this rewrite.
    REQUIRED_CLASSES = [
        ".market-tape",
        ".mt-cell",
        ".mt-label",
        ".mt-value",
        ".mt-chg",
        ".mt-up",
        ".mt-down",
        ".mt-flat",
        ".mt-stale",
        ".mt-expander",
        ".mt-econ-panel",
    ]

    def _get_css(self) -> str:
        css_path = WEB_DIR / "styles.css"
        assert css_path.exists(), f"styles.css not found at {css_path}"
        return css_path.read_text(encoding="utf-8")

    def test_required_css_classes_present(self):
        css = self._get_css()
        missing = [cls for cls in self.REQUIRED_CLASSES if cls not in css]
        assert not missing, (
            f"Missing CSS classes in styles.css: {missing}"
        )

    def test_market_tape_has_sticky_or_relative_positioning(self):
        """The tape strip should have position defined (sticky or relative)."""
        css = self._get_css()
        # Find the .market-tape block — look for position anywhere near the class
        tape_section = re.search(
            r'\.market-tape\s*\{[^}]*\}', css, re.DOTALL
        )
        assert tape_section is not None, ".market-tape CSS block not found"
        block = tape_section.group()
        assert "position" in block, (
            f".market-tape block has no 'position' property:\n{block}"
        )


# ---------------------------------------------------------------------------
# 5. market_bar.js structural elements
# ---------------------------------------------------------------------------

class TestMarketBarJSContent:
    """market_bar.js must contain the required implementation elements."""

    def _get_js(self) -> str:
        js_path = WEB_DIR / "market_bar.js"
        return js_path.read_text(encoding="utf-8")

    def test_inverted_set_contains_vix(self):
        js = self._get_js()
        assert "VIX" in js, "market_bar.js must define VIX as an inverted metric"

    def test_inverted_set_contains_hy(self):
        js = self._get_js()
        assert "HY" in js, "market_bar.js must define HY as an inverted metric"

    def test_fetches_marketbar_api(self):
        js = self._get_js()
        assert "/api/marketbar" in js, (
            "market_bar.js must fetch /api/marketbar"
        )

    def test_fetches_macro_api_for_expander(self):
        js = self._get_js()
        assert "/api/macro" in js, (
            "market_bar.js must fetch /api/macro for the econ expander panel"
        )

    def test_has_60s_refresh(self):
        js = self._get_js()
        # 60 * 1000 = 60000ms
        has_60s = "60 * 1000" in js or "60000" in js
        assert has_60s, (
            "market_bar.js must set a 60-second auto-refresh interval"
        )

    def test_has_dom_content_loaded_guard(self):
        js = self._get_js()
        assert "DOMContentLoaded" in js, (
            "market_bar.js must guard initialization behind DOMContentLoaded"
        )

    def test_has_iife_wrapper(self):
        """Should be wrapped in an IIFE to avoid global scope pollution."""
        js = self._get_js()
        # IIFE pattern: (function() { or (() => {
        has_iife = bool(re.search(r'\(function\s*\(', js)) or bool(re.search(r'\(\(\s*\)\s*=>', js))
        assert has_iife, (
            "market_bar.js should be wrapped in an IIFE to avoid polluting global scope"
        )

    def test_use_strict_present(self):
        js = self._get_js()
        assert "'use strict'" in js or '"use strict"' in js, (
            "market_bar.js should include 'use strict'"
        )

    def test_injects_after_topbar(self):
        """Must inject the tape after the topbar, not inside it."""
        js = self._get_js()
        assert "header.topbar" in js or "topbar" in js, (
            "market_bar.js must reference the topbar header for injection"
        )
        assert "afterend" in js, (
            "market_bar.js must use insertAdjacentElement('afterend', ...) to inject after topbar"
        )

    def test_market_tape_class_used_in_js(self):
        js = self._get_js()
        assert "market-tape" in js, (
            "market_bar.js must assign the 'market-tape' CSS class"
        )

    def test_econ_expander_button_present(self):
        js = self._get_js()
        assert "Econ" in js, (
            "market_bar.js must render an 'Econ' toggle button for the expander"
        )

    def test_stale_styling_referenced(self):
        js = self._get_js()
        assert "mt-stale" in js or "stale" in js, (
            "market_bar.js must handle stale items with visual styling"
        )

    def test_color_direction_logic_present(self):
        """Color logic must handle direction (mt-up/mt-down) and inverted metrics."""
        js = self._get_js()
        assert "mt-up" in js, "market_bar.js must use 'mt-up' CSS class"
        assert "mt-down" in js, "market_bar.js must use 'mt-down' CSS class"

    def test_setinterval_used_for_refresh(self):
        js = self._get_js()
        assert "setInterval" in js, (
            "market_bar.js must use setInterval for periodic refresh"
        )


# ---------------------------------------------------------------------------
# 6. API regression — DB-dependent, auto-skips if Postgres absent
# ---------------------------------------------------------------------------

class TestMarketbarAPIRegression:
    """GET /api/marketbar must return 200 with as_of and items."""

    def test_endpoint_200_with_required_keys(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")

        assert response.status_code == 200, (
            f"Expected 200 from /api/marketbar, got {response.status_code}: {response.text[:300]}"
        )

        data = response.json()
        assert "as_of" in data, f"Response missing 'as_of': {data}"
        assert "items" in data, f"Response missing 'items': {data}"
        assert isinstance(data["items"], list), "items must be a list"
        assert len(data["items"]) > 0, "items list must not be empty"

    def test_items_have_stale_boolean(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200

        for item in response.json()["items"]:
            assert isinstance(item.get("stale"), bool), (
                f"stale field missing or not bool for metric {item.get('metric_key')!r}"
            )

    def test_items_have_metric_key_label_value(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")

        from fastapi.testclient import TestClient
        from api.main import app

        client = TestClient(app)
        response = client.get("/api/marketbar")
        assert response.status_code == 200

        # REWRITTEN (TASK_113, 2026-07-04): 'sort_order' removed — a new
        # `grp: 'synthetic'` item class (e.g. BZ/Brent, sourced from
        # drv_quote/RR data rather than the seeded ref_market_metric rows)
        # doesn't carry a sort_order at all. See test_marketbar.py::
        # TestMarketbarEndpoint for the fuller rewrite of this same shape.
        required_keys = {"metric_key", "label", "value_format"}
        for item in response.json()["items"]:
            missing = required_keys - set(item.keys())
            assert not missing, (
                f"Item {item.get('metric_key')!r} missing keys: {missing}"
            )
