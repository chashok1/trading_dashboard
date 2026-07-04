"""
Tests for DEV_HANDOFF / TASK_78 (Macro read card) + TASK_79 (USD correlations card).

Acceptance criteria verified (static/offline — no DB, no network):

  [Schema]
  S1  ref_macro_area table definition present in baseline.sql
  S2  ref_corr_asset table definition present in baseline.sql
  S3  hist_quote_daily table definition present in baseline.sql
  S4  drv_usd_correlation table definition present in baseline.sql
  S5  seeds_macro_area.sql exists and seeds exactly 8 area_keys
  S6  seeds_corr.sql exists and seeds exactly 6 asset_keys (incl. usd as is_usd_base)

  [API routers — file presence & syntax]
  A1  api/routers/macro_areas.py exists and parses without SyntaxError
  A2  api/routers/correlations.py exists and parses without SyntaxError
  A3  api/main.py — 'macro_areas' in router loop tuple
  A4  api/main.py — 'correlations' in router loop tuple
  A5  api/main.py — include_router(macro_areas.router) called
  A6  api/main.py — include_router(correlations.router) called

  [Router endpoint paths]
  A7  macro_areas.py defines GET /api/macro-areas
  A8  correlations.py defines GET /api/correlations and returns WINDOWS=[15,30,90,120,180]

  [SQL length <= 965 bytes — convention 7]
  Q1  All SQL strings in macro_areas.py <= 965 bytes
  Q2  All SQL strings in correlations.py <= 965 bytes
  Q3  All SQL strings in fetch_quotes.py <= 965 bytes
  Q4  All SQL strings in derive_usd_correlation.py <= 965 bytes

  [ETL files — presence & syntax]
  E1  etl/fetch_quotes.py exists and parses without SyntaxError
  E2  etl/derive_usd_correlation.py exists and parses without SyntaxError
  E3  derive.py wires derive_usd_correlation in derive_all()
  E4  derive_usd_correlation is wrapped non-critically (try/except in derive.py)
  E5  derive_usd_correlation uses DELETE+INSERT (idempotent) pattern

  [Web files — presence & syntax]
  W1  web/macro_areas.js exists and passes `node --check`
  W2  web/macro_usd_corr.js exists and passes `node --check`
  W3  actionable.html contains <script src="/static/macro_areas.js" defer>
  W4  actionable.html contains <script src="/static/macro_usd_corr.js" defer>
  W5  both new script tags appear before warning_badge.js in actionable.html

  [Inter-card wiring]
  W6  macro_areas.js dispatches 'macroReadReady' CustomEvent
  W7  macro_areas.js injects #macroReadWrapper
  W8  macro_areas.js renders #macroCorrRow / #macroCorrSummary placeholder
  W9  macro_usd_corr.js listens for 'macroReadReady' event
  W10 macro_usd_corr.js injects #usdCorrWrapper after #macroReadWrapper
  W11 macro_usd_corr.js fills #macroCorrSummary with chip content

  [CSS classes]
  C1  styles.css contains .mra-wrapper (macro read card)
  C2  styles.css contains .ucr-wrapper (USD corr card)

  [DEV_HANDOFF sentinel]
  H1  DEV_HANDOFF.md Status is ALL_DONE
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _parse_py(rel: str) -> None:
    """Raise SyntaxError if file does not parse."""
    src = _read(rel)
    ast.parse(src)


def _sql_strings(src: str) -> list[str]:
    """
    Extract all SQL strings passed to text() calls.
    Handles triple-quoted and single-line double-quoted strings.
    """
    result = []
    # Triple-quoted inside text(""" ... """)
    for m in re.finditer(r'text\s*\(\s*"""(.*?)"""\s*[,)]', src, re.DOTALL):
        result.append(m.group(1))
    # Single-line double-quoted inside text(" ... ")
    for m in re.finditer(r'text\s*\(\s*"(.*?)"\s*[,)]', src, re.DOTALL):
        result.append(m.group(1))
    return result


def _node_check(rel: str) -> tuple[bool, str]:
    path = str(ROOT / rel)
    r = subprocess.run(
        ["node", "--check", path],
        capture_output=True, text=True
    )
    return r.returncode == 0, r.stderr.strip()


# ---------------------------------------------------------------------------
# S: Schema / seeds
# ---------------------------------------------------------------------------

def test_S1_ref_macro_area_in_baseline():
    sql = _read("db/baseline.sql")
    assert "CREATE TABLE IF NOT EXISTS ref_macro_area" in sql, \
        "ref_macro_area table not found in baseline.sql"


def test_S2_ref_corr_asset_in_baseline():
    sql = _read("db/baseline.sql")
    assert "CREATE TABLE IF NOT EXISTS ref_corr_asset" in sql, \
        "ref_corr_asset table not found in baseline.sql"


def test_S3_hist_quote_daily_in_baseline():
    sql = _read("db/baseline.sql")
    assert "CREATE TABLE IF NOT EXISTS hist_quote_daily" in sql, \
        "hist_quote_daily table not found in baseline.sql"


def test_S4_drv_usd_correlation_in_baseline():
    sql = _read("db/baseline.sql")
    assert "CREATE TABLE IF NOT EXISTS drv_usd_correlation" in sql, \
        "drv_usd_correlation table not found in baseline.sql"


def test_S5_seeds_macro_area_has_8_areas():
    """REWRITTEN (TASK_113, 2026-07-04): the macro-area categorization was
    reorganized — each area_key now renders as its own side-panel section
    (see the seed file's own header comment). Renamed: usd->usd_currency,
    rates->rates_duration, us_equities/global replaced by country_etfs +
    remaining, plus a new commodities_credit area alongside the pre-existing
    credit area (still 8 areas total, different names). Legitimate seed-data
    evolution, not drift to revert — updated the expected set rather than
    re-pinning the stale names.
    """
    seed = _read("db/seeds_macro_area.sql")
    # Extract first positional argument to INSERT VALUES (the area_key)
    area_keys = set(re.findall(r"'([a-z_]+)',\s*'[^']*',\s*'", seed))
    assert len(area_keys) == 8, \
        f"Expected 8 distinct area_keys, got {len(area_keys)}: {sorted(area_keys)}"
    expected = {"usd_currency", "country_etfs", "volatility", "rates_duration",
                "credit", "commodities_credit", "crypto", "remaining"}
    assert area_keys == expected, \
        f"area_keys mismatch: got {sorted(area_keys)} expected {sorted(expected)}"


def test_S6_seeds_corr_has_6_assets():
    seed = _read("db/seeds_corr.sql")
    # Match the asset_key column value — first value in each INSERT row
    asset_keys = set(re.findall(r"'(usd|spx|brent|crb|gold|bitcoin)'", seed))
    assert len(asset_keys) == 6, \
        f"Expected 6 asset_keys, got {len(asset_keys)}: {sorted(asset_keys)}"
    assert "usd" in seed and "TRUE" in seed, \
        "USD base row with is_usd_base=TRUE not found in seeds_corr.sql"


# ---------------------------------------------------------------------------
# A: API routers
# ---------------------------------------------------------------------------

def test_A1_macro_areas_py_exists_and_parses():
    assert (ROOT / "api/routers/macro_areas.py").exists(), \
        "api/routers/macro_areas.py missing"
    _parse_py("api/routers/macro_areas.py")


def test_A2_correlations_py_exists_and_parses():
    assert (ROOT / "api/routers/correlations.py").exists(), \
        "api/routers/correlations.py missing"
    _parse_py("api/routers/correlations.py")


def test_A3_main_includes_macro_areas_in_loop():
    src = _read("api/main.py")
    assert '"macro_areas"' in src, \
        "'macro_areas' not found in api/main.py router loop"


def test_A4_main_includes_correlations_in_loop():
    src = _read("api/main.py")
    assert '"correlations"' in src, \
        "'correlations' not found in api/main.py router loop"


def test_A5_main_include_router_macro_areas():
    src = _read("api/main.py")
    assert "include_router(macro_areas.router)" in src, \
        "app.include_router(macro_areas.router) not found in api/main.py"


def test_A6_main_include_router_correlations():
    src = _read("api/main.py")
    assert "include_router(correlations.router)" in src, \
        "app.include_router(correlations.router) not found in api/main.py"


def test_A7_macro_areas_endpoint_path():
    src = _read("api/routers/macro_areas.py")
    assert '@router.get("/api/macro-areas")' in src, \
        "GET /api/macro-areas route not found in macro_areas.py"


def test_A8_correlations_endpoint_and_windows():
    src = _read("api/routers/correlations.py")
    assert '@router.get("/api/correlations")' in src, \
        "GET /api/correlations route not found in correlations.py"
    assert "WINDOWS = [15, 30, 90, 120, 180]" in src, \
        "WINDOWS list not found in correlations.py"


# ---------------------------------------------------------------------------
# Q: SQL length convention (<= 965 bytes)
# ---------------------------------------------------------------------------

def _check_sql_lengths(rel: str) -> list[tuple[int, str]]:
    src = _read(rel)
    over = []
    for s in _sql_strings(src):
        if len(s) > 965:
            over.append((len(s), s[:80].replace("\n", " ")))
    return over


def test_Q1_sql_lengths_macro_areas():
    over = _check_sql_lengths("api/routers/macro_areas.py")
    assert not over, f"SQL strings > 965 bytes in macro_areas.py: {over}"


def test_Q2_sql_lengths_correlations():
    over = _check_sql_lengths("api/routers/correlations.py")
    assert not over, f"SQL strings > 965 bytes in correlations.py: {over}"


def test_Q3_sql_lengths_fetch_quotes():
    over = _check_sql_lengths("etl/fetch_quotes.py")
    assert not over, f"SQL strings > 965 bytes in fetch_quotes.py: {over}"


def test_Q4_sql_lengths_derive_usd_correlation():
    over = _check_sql_lengths("etl/derive_usd_correlation.py")
    assert not over, f"SQL strings > 965 bytes in derive_usd_correlation.py: {over}"


# ---------------------------------------------------------------------------
# E: ETL files
# ---------------------------------------------------------------------------

def test_E1_fetch_quotes_exists_and_parses():
    assert (ROOT / "etl/fetch_quotes.py").exists(), "etl/fetch_quotes.py missing"
    _parse_py("etl/fetch_quotes.py")


def test_E2_derive_usd_correlation_exists_and_parses():
    assert (ROOT / "etl/derive_usd_correlation.py").exists(), \
        "etl/derive_usd_correlation.py missing"
    _parse_py("etl/derive_usd_correlation.py")


def test_E3_derive_all_wires_usd_correlation():
    src = _read("etl/derive.py")
    assert "derive_usd_correlation" in src, \
        "derive_usd_correlation not wired into derive.py"
    assert "from etl.derive_usd_correlation import derive_usd_correlation" in src, \
        "import of derive_usd_correlation not found in derive.py"


def test_E4_derive_all_wraps_usd_corr_noncritically():
    src = _read("etl/derive.py")
    # Must be inside a try/except block (non-critical)
    # Find the block around derive_usd_correlation
    idx = src.find("derive_usd_correlation")
    assert idx != -1, "derive_usd_correlation not found in derive.py"
    context = src[max(0, idx - 300): idx + 200]
    assert "try:" in context, \
        "derive_usd_correlation is not wrapped in a try block (must be non-critical)"
    assert "except" in context, \
        "derive_usd_correlation is not wrapped in a try/except block"


def test_E5_derive_usd_correlation_is_idempotent():
    src = _read("etl/derive_usd_correlation.py")
    assert "DELETE FROM drv_usd_correlation WHERE as_of_date" in src, \
        "Idempotent DELETE+INSERT pattern not found in derive_usd_correlation.py"


def test_E6_fetch_quotes_has_on_conflict_do_nothing():
    src = _read("etl/fetch_quotes.py")
    assert "ON CONFLICT" in src and "DO NOTHING" in src, \
        "ON CONFLICT DO NOTHING (convention 1) not found in fetch_quotes.py"


def test_E7_fetch_quotes_throttle():
    src = _read("etl/fetch_quotes.py")
    assert "THROTTLE_SECONDS" in src, \
        "THROTTLE_SECONDS not defined in fetch_quotes.py"
    assert "time.sleep(THROTTLE_SECONDS)" in src, \
        "throttle sleep not found in fetch_quotes.py"


# ---------------------------------------------------------------------------
# W: Web files
# ---------------------------------------------------------------------------

def test_W1_macro_areas_js_exists_and_node_check():
    assert (ROOT / "web/macro_areas.js").exists(), "web/macro_areas.js missing"
    ok, err = _node_check("web/macro_areas.js")
    assert ok, f"node --check web/macro_areas.js failed:\n{err}"


def test_W2_macro_usd_corr_js_exists_and_node_check():
    assert (ROOT / "web/macro_usd_corr.js").exists(), "web/macro_usd_corr.js missing"
    ok, err = _node_check("web/macro_usd_corr.js")
    assert ok, f"node --check web/macro_usd_corr.js failed:\n{err}"


def test_W3_actionable_html_has_macro_areas_script():
    html = _read("web/actionable.html")
    assert '<script src="/static/macro_areas.js" defer>' in html, \
        '<script src="/static/macro_areas.js" defer> not found in actionable.html'


def test_W4_actionable_html_has_macro_usd_corr_script():
    html = _read("web/actionable.html")
    assert '<script src="/static/macro_usd_corr.js" defer>' in html, \
        '<script src="/static/macro_usd_corr.js" defer> not found in actionable.html'


def test_W5_new_scripts_before_warning_badge():
    html = _read("web/actionable.html")
    idx_areas = html.find('src="/static/macro_areas.js"')
    idx_corr  = html.find('src="/static/macro_usd_corr.js"')
    idx_badge = html.find('src="/static/warning_badge.js"')
    assert idx_areas != -1, "macro_areas.js script tag missing"
    assert idx_corr  != -1, "macro_usd_corr.js script tag missing"
    assert idx_badge != -1, "warning_badge.js script tag missing"
    assert idx_areas < idx_badge, \
        "macro_areas.js must appear before warning_badge.js"
    assert idx_corr  < idx_badge, \
        "macro_usd_corr.js must appear before warning_badge.js"


def test_W6_macro_areas_dispatches_ready_event():
    src = _read("web/macro_areas.js")
    assert "macroReadReady" in src, \
        "macroReadReady CustomEvent not dispatched in macro_areas.js"
    assert "dispatchEvent" in src and "CustomEvent" in src, \
        "CustomEvent dispatch not found in macro_areas.js"


def test_W7_macro_areas_injects_wrapper():
    src = _read("web/macro_areas.js")
    assert "macroReadWrapper" in src, \
        "#macroReadWrapper not set in macro_areas.js"


def test_W8_macro_areas_corr_placeholder_row():
    src = _read("web/macro_areas.js")
    assert "macroCorrRow" in src, \
        "#macroCorrRow placeholder not found in macro_areas.js"
    assert "macroCorrSummary" in src, \
        "#macroCorrSummary placeholder not found in macro_areas.js"


def test_W9_macro_usd_corr_listens_for_ready_event():
    src = _read("web/macro_usd_corr.js")
    assert "macroReadReady" in src, \
        "macro_usd_corr.js does not listen for macroReadReady event"
    assert "addEventListener" in src, \
        "addEventListener not found in macro_usd_corr.js"


def test_W10_macro_usd_corr_injects_wrapper():
    src = _read("web/macro_usd_corr.js")
    assert "usdCorrWrapper" in src, \
        "#usdCorrWrapper not injected in macro_usd_corr.js"


def test_W11_macro_usd_corr_fills_summary():
    src = _read("web/macro_usd_corr.js")
    assert "macroCorrSummary" in src, \
        "macro_usd_corr.js does not reference #macroCorrSummary to fill chips"


# ---------------------------------------------------------------------------
# C: CSS
# ---------------------------------------------------------------------------

def test_C1_css_has_mra_wrapper():
    css = _read("web/styles.css")
    assert ".mra-wrapper" in css, \
        ".mra-wrapper CSS rule not found in styles.css"


def test_C2_css_has_ucr_wrapper():
    css = _read("web/styles.css")
    assert ".ucr-wrapper" in css, \
        ".ucr-wrapper CSS rule not found in styles.css"


# ---------------------------------------------------------------------------
# H: Handoff sentinel
# ---------------------------------------------------------------------------

def test_H1_handoff_all_done():
    content = _read("DEV_HANDOFF.md")
    lines = [l.strip() for l in content.splitlines() if l.strip()]
    last = lines[-1] if lines else ""
    assert last == "ALL_DONE", \
        f"DEV_HANDOFF.md does not end with ALL_DONE (last line: {last!r})"
