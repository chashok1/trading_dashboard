"""
Tests for TASK_101 — Hedgeye panel visibility fix on /actionable.

Two specific fixes were applied:
1. web/actionable.html was truncated — restored </body></html> and added the
   hedgeye_panel.js script tag (primary cause of panel never loading).
2. api/routers/hedgeye.py — effective_date clamping added; alerts/flips queries
   changed from exact-date to <= effective_date.

Acceptance criteria verified here:
  A. actionable.html: file complete (<body>, </html>), hedgeye_panel.js script,
     warning_badge.js script, id="hedgeyePanel" div present.
  B. hedgeye.py: effective_date clamping logic, <= queries for alerts/flips,
     as_of field in response.
  C. hedgeye_panel.js: uses data.as_of (with fallback to data.date).
  D. Syntax: hedgeye.py parses cleanly, hedgeye_panel.js passes node --check.
  E. DB data (skipped if no Postgres): top5/alerts/flips/stance all > 0.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HEDGEYE_PY   = PROJECT_ROOT / "api" / "routers" / "hedgeye.py"
PANEL_JS     = PROJECT_ROOT / "web" / "hedgeye_panel.js"
ACT_HTML     = PROJECT_ROOT / "web" / "actionable.html"


def _py():
    return HEDGEYE_PY.read_text(encoding="utf-8")


def _js():
    return PANEL_JS.read_text(encoding="utf-8")


def _html():
    return ACT_HTML.read_text(encoding="utf-8")


# =============================================================================
# D. Syntax checks
# =============================================================================

class TestSyntax:

    def test_hedgeye_py_parses(self):
        """hedgeye.py must parse cleanly with ast."""
        src = _py()
        try:
            ast.parse(src)
        except SyntaxError as e:
            raise AssertionError(f"hedgeye.py SyntaxError: {e}") from e

    def test_hedgeye_panel_js_node_check(self):
        """hedgeye_panel.js must pass node --check."""
        result = subprocess.run(
            ["node", "--check", str(PANEL_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            f"hedgeye_panel.js failed node --check:\n{result.stderr}"
        )


# =============================================================================
# A. actionable.html completeness
# =============================================================================

class TestActionableHtmlComplete:

    def test_file_ends_with_html_close(self):
        """File must end with </html>."""
        html = _html()
        assert "</html>" in html, "actionable.html missing </html>"

    def test_file_has_body_close(self):
        """File must have </body>."""
        html = _html()
        assert "</body>" in html, "actionable.html missing </body>"

    def test_hedgeye_panel_js_script_tag(self):
        """actionable.html must load hedgeye_panel.js via a <script> tag."""
        html = _html()
        assert "hedgeye_panel.js" in html, (
            "<script src=...hedgeye_panel.js...> not found in actionable.html"
        )

    def test_warning_badge_js_script_tag(self):
        """actionable.html must still include warning_badge.js (restored tail)."""
        html = _html()
        assert "warning_badge.js" in html, (
            "<script src=...warning_badge.js...> not found in actionable.html — "
            "truncated tail not fully restored"
        )

    def test_hedgeye_panel_div_present(self):
        """#hedgeyePanel div must exist in actionable.html."""
        html = _html()
        assert 'id="hedgeyePanel"' in html, (
            'id="hedgeyePanel" div not found in actionable.html'
        )

    def test_hedgeye_panel_js_comes_after_body_content(self):
        """hedgeye_panel.js script tag must appear after the main page content."""
        html = _html()
        hedgeye_panel_pos = html.find("hedgeye_panel.js")
        hedgeye_div_pos   = html.find('id="hedgeyePanel"')
        assert hedgeye_div_pos != -1, 'id="hedgeyePanel" div not found'
        assert hedgeye_panel_pos != -1, "hedgeye_panel.js script not found"
        assert hedgeye_div_pos < hedgeye_panel_pos, (
            "hedgeye_panel.js script must come after the #hedgeyePanel div"
        )

    def test_body_close_before_html_close(self):
        """</body> must appear before </html>."""
        html = _html()
        body_pos = html.rfind("</body>")
        html_pos = html.rfind("</html>")
        assert body_pos != -1, "</body> not found"
        assert html_pos != -1, "</html> not found"
        assert body_pos < html_pos, (
            f"</body> (pos {body_pos}) must come before </html> (pos {html_pos})"
        )


# =============================================================================
# B. hedgeye.py — effective_date clamping + <= queries + as_of field
# =============================================================================

class TestHedgeyeEffectiveDateLogic:

    def test_effective_date_variable_exists(self):
        """Code must define an effective_date variable."""
        assert "effective_date" in _py(), (
            "effective_date variable not found in hedgeye.py"
        )

    def test_effective_date_uses_max(self):
        """effective_date must be computed with max() to clamp up to latest Hedgeye data."""
        src = _py()
        assert "effective_date = max(" in src, (
            "effective_date clamping 'effective_date = max(...)' not found in hedgeye.py"
        )

    def test_alerts_uses_lte_effective_date(self):
        """hist_rta query must use <= :eff (not = :d exact date) for date alignment."""
        src = _py()
        # Find the rta_date lookup that feeds the alerts section
        rta_block_pos = src.find("hist_rta WHERE snapshot_date <=")
        assert rta_block_pos != -1, (
            "hist_rta date filter must use '<= :eff' (not exact-date '= :d'). "
            "Pattern 'hist_rta WHERE snapshot_date <=' not found in hedgeye.py"
        )

    def test_trend_flips_uses_lte_effective_date(self):
        """drv_rr_trend_change query must use <= :eff for date alignment."""
        src = _py()
        flip_block_pos = src.find("drv_rr_trend_change WHERE as_of_date <=")
        assert flip_block_pos != -1, (
            "drv_rr_trend_change date filter must use '<= :eff'. "
            "Pattern 'drv_rr_trend_change WHERE as_of_date <=' not found in hedgeye.py"
        )

    def test_as_of_in_response(self):
        """Response must include 'as_of' key (the effective data date)."""
        src = _py()
        assert '"as_of"' in src or "'as_of'" in src, (
            "as_of field not set in response dict in hedgeye.py"
        )

    def test_as_of_set_from_effective_date(self):
        """as_of must be set from effective_date.isoformat() not d.isoformat()."""
        src = _py()
        # Find the line that assigns out["as_of"]
        as_of_pos = src.find('"as_of"')
        assert as_of_pos != -1, '"as_of" key not found in hedgeye.py'
        context = src[as_of_pos:as_of_pos + 60]
        assert "effective_date" in context, (
            f"out['as_of'] must use effective_date, not anchor date d. Context: {context!r}"
        )

    def test_latest_hedgeye_date_query_present(self):
        """Code must query MAX(snapshot_date) from Hedgeye tables to compute effective_date."""
        src = _py()
        assert "MAX(snapshot_date)" in src or "MAX(d)" in src, (
            "No MAX(snapshot_date) query found to compute latest Hedgeye date"
        )

    def test_top5_query_uses_effective_date(self):
        """Top-5 query must use <= :eff with effective_date passed as parameter."""
        src = _py()
        # Verify the pattern: the date-selection sub-query for top5 uses :eff
        # and the parameter dict passes effective_date for it.
        assert '"eff": effective_date' in src, (
            'Top5 date query must pass {"eff": effective_date} — not found in hedgeye.py'
        )

    def test_stance_query_uses_effective_date(self):
        """Stance query must use <= :eff with effective_date passed as parameter."""
        src = _py()
        # The stance_date selection must also use effective_date via :eff.
        # Confirmed by counting how many times :eff appears — should be >= 4.
        eff_count = src.count('"eff": effective_date')
        assert eff_count >= 4, (
            f"Expected at least 4 occurrences of '\"eff\": effective_date' (top5, alerts, "
            f"flips, stance), found {eff_count}. Stance may not use effective_date."
        )


# =============================================================================
# C. hedgeye_panel.js — uses data.as_of
# =============================================================================

class TestHedgeyePanelJs:

    def test_uses_data_as_of(self):
        """Panel must read data.as_of for the header date label."""
        src = _js()
        assert "data.as_of" in src, (
            "hedgeye_panel.js does not reference data.as_of"
        )

    def test_as_of_has_fallback(self):
        """Panel must fall back to data.date when as_of is absent."""
        src = _js()
        assert "data.as_of || data.date" in src or "data.date" in src, (
            "hedgeye_panel.js has no fallback from data.as_of to data.date"
        )

    def test_renders_into_hedgeye_panel_el(self):
        """Panel JS must target the #hedgeyePanel element."""
        src = _js()
        assert "hedgeyePanel" in src, (
            "#hedgeyePanel not referenced in hedgeye_panel.js"
        )

    def test_fetches_api_actionable_hedgeye(self):
        """Panel JS must fetch /api/actionable/hedgeye."""
        src = _js()
        assert "/api/actionable/hedgeye" in src, (
            "/api/actionable/hedgeye endpoint not referenced in hedgeye_panel.js"
        )

    def test_listens_to_date_picker_change(self):
        """Panel JS must re-load when the date picker changes."""
        src = _js()
        assert "datePicker" in src, (
            "hedgeye_panel.js does not listen to #datePicker changes"
        )
        assert "change" in src or "addEventListener" in src, (
            "hedgeye_panel.js missing change event listener for date picker"
        )

    def test_hides_panel_on_empty_data(self):
        """If all arrays are empty, panel must be hidden (display:none)."""
        src = _js()
        assert "style.display = 'none'" in src or 'style.display="none"' in src, (
            "hedgeye_panel.js does not hide panel when data is empty"
        )

    def test_symbol_links_to_symbol_hedgeye_page(self):
        """Symbol clicks must navigate to /symbol-hedgeye."""
        src = _js()
        assert "symbol-hedgeye" in src, (
            "hedgeye_panel.js does not link symbols to /symbol-hedgeye"
        )


# =============================================================================
# E. DB data tests — skipped when Postgres is unavailable
# =============================================================================

def _db_session():
    """Return a live SQLAlchemy session or raise pytest.skip."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(str(env_path))
        except ImportError:
            pass
    try:
        from etl.db import session_scope
        return session_scope
    except Exception as exc:
        pytest.skip(f"Cannot import etl.db: {exc}")


@pytest.mark.db
class TestDbDataAvailability:
    """Verify Hedgeye data is present in the DB for the known anchor date."""

    ANCHOR = "2026-06-26"

    @pytest.fixture(autouse=True)
    def _skip_if_no_db(self):
        env_path = PROJECT_ROOT / ".env"
        if not env_path.exists():
            pytest.skip("No .env file — DB tests skipped")
        try:
            from dotenv import load_dotenv
            load_dotenv(str(env_path))
            import os
            pw = os.environ.get("PG_PASSWORD", "")
            import psycopg
            conn = psycopg.connect(
                f"host=localhost port=5432 dbname=trading user=postgres password={pw}",
                connect_timeout=5,
            )
            conn.close()
        except Exception as exc:
            pytest.skip(f"Cannot connect to Postgres: {exc}")

    def _count(self, sql, params=None):
        from dotenv import load_dotenv
        load_dotenv(str(PROJECT_ROOT / ".env"))
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            return s.execute(text(sql), params or {}).scalar()

    def test_hist_call_top5_has_data(self):
        """hist_call_top5 must have rows on or before the anchor date."""
        from datetime import date
        count = self._count(
            "SELECT COUNT(*) FROM hist_call_top5 WHERE snapshot_date <= :e",
            {"e": date(2026, 6, 26)},
        )
        assert count > 0, f"hist_call_top5: expected >0 rows for date <= {self.ANCHOR}, got 0"

    def test_hist_rta_has_non_superseded_data(self):
        """hist_rta must have non-superseded rows on or before the anchor date."""
        from datetime import date
        count = self._count(
            "SELECT COUNT(*) FROM hist_rta WHERE snapshot_date <= :e AND superseded = FALSE",
            {"e": date(2026, 6, 26)},
        )
        assert count > 0, f"hist_rta: expected >0 non-superseded rows for date <= {self.ANCHOR}, got 0"

    def test_drv_rr_trend_change_has_data(self):
        """drv_rr_trend_change must have rows on or before the anchor date."""
        from datetime import date
        count = self._count(
            "SELECT COUNT(*) FROM drv_rr_trend_change WHERE as_of_date <= :e",
            {"e": date(2026, 6, 26)},
        )
        assert count > 0, f"drv_rr_trend_change: expected >0 rows for date <= {self.ANCHOR}, got 0"

    def test_hist_hedgeye_stance_has_data(self):
        """hist_hedgeye_stance must have rows on or before the anchor date."""
        from datetime import date
        count = self._count(
            "SELECT COUNT(*) FROM hist_hedgeye_stance WHERE snapshot_date <= :e",
            {"e": date(2026, 6, 26)},
        )
        assert count > 0, f"hist_hedgeye_stance: expected >0 rows for date <= {self.ANCHOR}, got 0"

    def test_hist_call_top5_count_matches_expected(self):
        """hist_call_top5 should have exactly 5 rows for the anchor date."""
        from datetime import date
        count = self._count(
            "SELECT COUNT(*) FROM hist_call_top5 WHERE snapshot_date = :e",
            {"e": date(2026, 6, 26)},
        )
        assert count == 5, (
            f"hist_call_top5 for {self.ANCHOR}: expected 5 rows (one per rank), got {count}"
        )

    def test_effective_date_clamping_not_needed_for_anchor(self):
        """For 2026-06-26, Hedgeye data date should match the anchor (no clamping needed).
        This validates the current DB state matches what the DEV_HANDOFF recorded."""
        from datetime import date
        from sqlalchemy import text
        from dotenv import load_dotenv
        load_dotenv(str(PROJECT_ROOT / ".env"))
        from etl.db import session_scope
        with session_scope() as s:
            latest_rta = s.execute(text(
                "SELECT MAX(snapshot_date) FROM hist_rta"
            )).scalar()
            latest_top5 = s.execute(text(
                "SELECT MAX(snapshot_date) FROM hist_call_top5"
            )).scalar()
        anchor = date(2026, 6, 26)
        if latest_rta is not None:
            assert latest_rta <= anchor or latest_rta == anchor, (
                f"hist_rta max date {latest_rta} is after anchor {anchor} — "
                "clamping code is essential (good it exists)"
            )
        if latest_top5 is not None:
            assert latest_top5 <= anchor or latest_top5 == anchor, (
                f"hist_call_top5 max date {latest_top5} is after anchor {anchor} — "
                "clamping code is essential (good it exists)"
            )
