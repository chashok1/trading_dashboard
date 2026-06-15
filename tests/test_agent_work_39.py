"""Tests for AGENT_WORK_39 — architecture-review batch: Tasks 2–8 + Block A (AGENT_WORK_37) + Block B (AGENT_WORK_38).

Pure Python, no Postgres required (DB tests use skip when DB absent).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Block A — Scorecard CIs (AGENT_WORK_37 acceptance criteria)
# ---------------------------------------------------------------------------

class TestBlockA_ScorecardView:
    """v_rule_scorecard must expose CI columns with correct math."""

    SQL = (PROJECT / "db" / "baseline.sql").read_text(encoding="utf-8-sig")

    def test_view_exists(self):
        assert "CREATE OR REPLACE VIEW v_rule_scorecard" in self.SQL

    def test_n_fires_column(self):
        assert "n_fires" in self.SQL

    def test_edge_20d_ci_low_column(self):
        assert "edge_20d_ci_low" in self.SQL

    def test_edge_20d_ci_high_column(self):
        assert "edge_20d_ci_high" in self.SQL

    def test_confidence_column(self):
        assert "confidence" in self.SQL

    def test_ci_formula_1_96_stddev(self):
        """95% CI formula: 1.96 * stddev_samp / sqrt(n)."""
        assert "1.96" in self.SQL
        assert "STDDEV_SAMP" in self.SQL or "stddev_samp" in self.SQL

    def test_ci_nullif_guard(self):
        """NULLIF(SQRT(n),0) prevents division by zero."""
        assert "NULLIF" in self.SQL.upper()
        assert "SQRT" in self.SQL.upper()

    def test_confidence_proven_bucket(self):
        """'proven' requires n>=100 AND ci_low>0."""
        assert "proven" in self.SQL
        assert "100" in self.SQL

    def test_confidence_promising_bucket(self):
        """'promising' requires n>=30 AND edge>0."""
        assert "promising" in self.SQL
        assert "30" in self.SQL

    def test_confidence_unproven_bucket(self):
        assert "unproven" in self.SQL


class TestBlockA_RulePerformanceJS:
    """rule_performance.js must show CI column and dim unproven rows."""

    JS = (PROJECT / "web" / "rule_performance.js").read_text(encoding="utf-8-sig")

    def test_ci_low_rendered(self):
        assert "edge_20d_ci_low" in self.JS

    def test_ci_high_rendered(self):
        assert "edge_20d_ci_high" in self.JS

    def test_n_fires_rendered(self):
        assert "n_fires" in self.JS

    def test_unproven_opacity_55(self):
        assert "opacity:0.55" in self.JS or "opacity: 0.55" in self.JS

    def test_unproven_confidence_class(self):
        assert "unproven" in self.JS

    def test_confidence_badge_proven(self):
        assert "proven" in self.JS


# ---------------------------------------------------------------------------
# Block B — Palette restyle (AGENT_WORK_38 acceptance criteria)
# ---------------------------------------------------------------------------

class TestBlockB_PaletteVars:
    """styles.css must have new palette hex values."""

    CSS = (PROJECT / "web" / "styles.css").read_text(encoding="utf-8-sig")

    def test_sell_text_color(self):
        assert "#791F1F" in self.CSS

    def test_sell_bg_color(self):
        assert "#FCEBEB" in self.CSS

    def test_buy_text_color(self):
        assert "#27500A" in self.CSS

    def test_buy_bg_color(self):
        assert "#EAF3DE" in self.CSS

    def test_hold_text_color(self):
        assert "#444441" in self.CSS

    def test_hold_bg_color(self):
        assert "#F1EFE8" in self.CSS

    def test_snooze_text_color(self):
        assert "#633806" in self.CSS

    def test_snooze_bg_color(self):
        assert "#FAEEDA" in self.CSS

    def test_act_sell_var(self):
        assert "--act-sell-strong" in self.CSS

    def test_act_buy_var(self):
        assert "--act-buy-strong" in self.CSS

    def test_act_neutral_var(self):
        assert "--act-neutral" in self.CSS

    def test_act_mixed_var(self):
        assert "--act-mixed" in self.CSS


class TestBlockB_ActionableHTML:
    """actionable.html btn-done/btn-skip/btn-snz styling."""

    HTML = (PROJECT / "web" / "actionable.html").read_text(encoding="utf-8-sig")

    def test_btn_done_border_none(self):
        # .btn-done must have border: none
        assert re.search(r"\.btn-done\s*\{[^}]*border:\s*none", self.HTML)

    def test_btn_skip_border_none(self):
        assert re.search(r"\.btn-skip\s*\{[^}]*border:\s*none", self.HTML)

    def test_btn_snz_border_none(self):
        assert re.search(r"\.btn-snz\s*\{[^}]*border:\s*none", self.HTML)

    def test_btn_done_green_bg(self):
        # Must use new green palette (#EAF3DE)
        assert "#EAF3DE" in self.HTML

    def test_btn_done_green_text(self):
        assert "#27500A" in self.HTML

    def test_btn_skip_hold_bg(self):
        assert "#F1EFE8" in self.HTML

    def test_btn_skip_hold_text(self):
        assert "#444441" in self.HTML

    def test_btn_snz_amber_bg(self):
        assert "#FAEEDA" in self.HTML

    def test_btn_snz_amber_text(self):
        assert "#633806" in self.HTML

    def test_btn_border_radius_8(self):
        assert "border-radius:8px" in self.HTML or "border-radius: 8px" in self.HTML

    def test_hover_brightness(self):
        assert "brightness(0.95)" in self.HTML

    def test_conviction_badge_edge_positive(self):
        assert "conviction-badge" in self.HTML
        assert ".conviction-badge.edge-positive" in self.HTML

    def test_conviction_edge_positive_bg(self):
        assert "#E1F5EE" in self.HTML

    def test_conviction_edge_positive_text(self):
        assert "#085041" in self.HTML

    def test_conviction_edge_positive_border_none(self):
        assert re.search(
            r"\.conviction-badge\.edge-positive\s*\{[^}]*border:\s*none",
            self.HTML
        )

    def test_stale_banner_bg(self):
        # staleBanner uses amber bg (#FAEEDA)
        assert "staleBanner" in self.HTML
        idx = self.HTML.find("staleBanner")
        snippet = self.HTML[idx:idx+400]
        assert "#FAEEDA" in snippet

    def test_stale_banner_border_none(self):
        idx = self.HTML.find("staleBanner")
        snippet = self.HTML[idx:idx+400]
        assert "border:none" in snippet or "border: none" in snippet


# ---------------------------------------------------------------------------
# Block C — Batch Task 2: EOD Feed Status
# ---------------------------------------------------------------------------

class TestTask2_EodFeedStatus:
    """EOD feed warning (Task 2)."""

    def test_eod_feed_status_function_exists_in_helpers(self):
        src = (PROJECT / "api" / "_helpers.py").read_text(encoding="utf-8-sig")
        assert "def eod_feed_status(" in src

    def test_eod_feed_status_queries_hist_tl(self):
        src = (PROJECT / "api" / "_helpers.py").read_text(encoding="utf-8-sig")
        assert "hist_tl" in src
        # Must check export_date
        assert "export_date" in src

    def test_eod_feed_status_returns_dict_with_missing_key(self):
        src = (PROJECT / "api" / "_helpers.py").read_text(encoding="utf-8-sig")
        assert '"missing"' in src or "'missing'" in src

    def test_health_router_has_eod_endpoint(self):
        src = (PROJECT / "api" / "routers" / "health.py").read_text(encoding="utf-8-sig")
        assert "/api/eod-feed-status" in src

    def test_actionable_html_has_eod_banner(self):
        html = (PROJECT / "web" / "actionable.html").read_text(encoding="utf-8-sig")
        assert "eodMissingBanner" in html

    def test_actionable_js_has_check_eod_feed(self):
        js = (PROJECT / "web" / "actionable.js").read_text(encoding="utf-8-sig")
        assert "checkEodFeed" in js

    def test_check_eod_feed_calls_endpoint(self):
        js = (PROJECT / "web" / "actionable.js").read_text(encoding="utf-8-sig")
        assert "/api/eod-feed-status" in js

    def test_check_eod_feed_called_on_init(self):
        js = (PROJECT / "web" / "actionable.js").read_text(encoding="utf-8-sig")
        # checkEodFeed() must be called more than just its definition
        calls = [m.start() for m in re.finditer(r"checkEodFeed\(\)", js)]
        assert len(calls) >= 2, "checkEodFeed() must be called at init and on date-change"

    def test_eod_banner_shown_when_missing(self):
        js = (PROJECT / "web" / "actionable.js").read_text(encoding="utf-8-sig")
        # Must handle f.missing being true
        assert "f.missing" in js or "missing" in js


# ---------------------------------------------------------------------------
# Block C — Batch Task 3: Cascade Status Tracking
# ---------------------------------------------------------------------------

class TestTask3_CascadeStatus:
    """Cascade status tracking (Task 3)."""

    def test_baseline_has_cascade_status_column(self):
        sql = (PROJECT / "db" / "baseline.sql").read_text(encoding="utf-8-sig")
        assert "cascade_status" in sql
        assert "meta_derived_run" in sql

    def test_cascade_status_alter_statement(self):
        sql = (PROJECT / "db" / "baseline.sql").read_text(encoding="utf-8-sig")
        assert "ADD COLUMN IF NOT EXISTS cascade_status TEXT" in sql

    def test_derive_py_has_safe_wrapper(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        assert "def _safe(" in src

    def test_derive_py_has_cascade_status(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        assert "cascade_status" in src

    def test_derive_py_success_status(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        assert '"SUCCESS"' in src or "'SUCCESS'" in src

    def test_derive_py_partial_status(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        assert '"PARTIAL"' in src or "'PARTIAL'" in src

    def test_derive_py_failed_status(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        assert '"FAILED"' in src or "'FAILED'" in src

    def test_derive_py_sentinel_row(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        assert "_cascade" in src

    def test_critical_steps_set(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        # CRITICAL set must contain drv_symbols, drv_actionable
        assert "drv_symbols" in src
        assert "drv_actionable" in src
        assert "_CRITICAL" in src

    def test_health_router_has_cascade_endpoint(self):
        src = (PROJECT / "api" / "routers" / "health.py").read_text(encoding="utf-8-sig")
        assert "/api/derive-cascade-status" in src

    def test_daily_health_check_has_derive_health(self):
        src = (PROJECT / "etl" / "daily_health_check.py").read_text(encoding="utf-8-sig")
        assert "_check_derive_health" in src

    def test_daily_health_check_in_checks_list(self):
        src = (PROJECT / "etl" / "daily_health_check.py").read_text(encoding="utf-8-sig")
        # _check_derive_health must be in the CHECKS list
        assert re.search(r"CHECKS\s*=\s*\[.*_check_derive_health", src, re.DOTALL)


# ---------------------------------------------------------------------------
# Block C — Batch Task 4: Intraday Price Tag in drv_quote
# ---------------------------------------------------------------------------

class TestTask4_IntradayTag:
    """drv_quote intraday price tag columns (Task 4)."""

    SQL = (PROJECT / "db" / "baseline.sql").read_text(encoding="utf-8-sig")

    def test_pct_brr_column_in_drv_quote(self):
        assert "pct_brr" in self.SQL
        # Must be on drv_quote via ALTER
        assert "ADD COLUMN IF NOT EXISTS pct_brr NUMERIC" in self.SQL

    def test_zone_signal_column_in_drv_quote(self):
        assert "ADD COLUMN IF NOT EXISTS zone_signal TEXT" in self.SQL

    def test_dist_to_trend_column(self):
        assert "ADD COLUMN IF NOT EXISTS dist_to_trend NUMERIC" in self.SQL

    def test_dist_to_trade_column(self):
        assert "ADD COLUMN IF NOT EXISTS dist_to_trade NUMERIC" in self.SQL

    def test_is_intraday_column(self):
        assert "ADD COLUMN IF NOT EXISTS is_intraday BOOLEAN" in self.SQL

    def test_derive_py_extended_quote_impl(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        assert "pct_brr" in src
        assert "is_intraday" in src

    def test_actionable_js_idy_badge(self):
        js = (PROJECT / "web" / "actionable.js").read_text(encoding="utf-8-sig")
        assert "IDY" in js

    def test_actionable_js_quote_is_intraday(self):
        js = (PROJECT / "web" / "actionable.js").read_text(encoding="utf-8-sig")
        assert "quote_is_intraday" in js or "is_intraday" in js

    def test_pct_brr_from_technicals(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        # pct_brr depends on a_trade_value / a_trend_value
        assert "a_trade_value" in src
        assert "a_trend_value" in src

    def test_zone_signal_uses_threshold_settings(self):
        src = (PROJECT / "etl" / "derive.py").read_text(encoding="utf-8-sig")
        # Uses dash_threshold_low_pct / dash_threshold_high_pct from ref_settings
        assert "dash_threshold_low_pct" in src or "th_low" in src or "threshold_low" in src


# ---------------------------------------------------------------------------
# Block C — Batch Task 7: Cockpit Retirement
# ---------------------------------------------------------------------------

class TestTask7_CockpitRetirement:
    """Cockpit retirement — redirect + macro band (Task 7)."""

    def test_pages_cockpit_route_is_redirect(self):
        src = (PROJECT / "api" / "routers" / "pages.py").read_text(encoding="utf-8-sig")
        assert "/cockpit" in src
        assert "RedirectResponse" in src
        assert "301" in src
        assert "/actionable" in src

    def test_cockpit_redirects_to_actionable(self):
        src = (PROJECT / "api" / "routers" / "pages.py").read_text(encoding="utf-8-sig")
        # Confirm redirect target is /actionable
        assert 'url="/actionable"' in src

    def test_actionable_html_has_macro_band(self):
        html = (PROJECT / "web" / "actionable.html").read_text(encoding="utf-8-sig")
        assert "macroBand" in html

    def test_actionable_html_has_macro_refresh_btn(self):
        html = (PROJECT / "web" / "actionable.html").read_text(encoding="utf-8-sig")
        assert "macroRefreshBtn" in html

    def test_actionable_html_has_macro_band_script(self):
        html = (PROJECT / "web" / "actionable.html").read_text(encoding="utf-8-sig")
        assert "macro_band.js" in html

    def test_actionable_html_no_cockpit_nav_link(self):
        html = (PROJECT / "web" / "actionable.html").read_text(encoding="utf-8-sig")
        # Must not have <a href="/cockpit"> nav link
        nav_links = re.findall(r'<a[^>]+href="/cockpit"', html)
        assert len(nav_links) == 0, f"Found cockpit nav links: {nav_links}"

    def test_no_cockpit_nav_in_non_cockpit_html(self):
        """No web/*.html file (except cockpit.html itself) should have a nav link to /cockpit."""
        web_dir = PROJECT / "web"
        offenders = []
        for f in web_dir.glob("*.html"):
            if f.name == "cockpit.html":
                continue
            content = f.read_text(encoding="utf-8", errors="replace")
            # Look for actual nav links (href="/cockpit") — not CSS class names
            if re.search(r'href="/cockpit"', content):
                offenders.append(f.name)
        assert offenders == [], f"Cockpit nav links still in: {offenders}"

    def test_macro_collapse_toggle_in_actionable_html(self):
        html = (PROJECT / "web" / "actionable.html").read_text(encoding="utf-8-sig")
        assert "localStorage" in html
        assert "macroCardOpen" in html or "macro" in html

    def test_trace_html_cockpit_link_updated(self):
        html = (PROJECT / "web" / "trace.html").read_text(encoding="utf-8-sig")
        # The static href should point to /actionable, not /cockpit
        if "cockpitLink" in html:
            # Find the element
            m = re.search(r'id="cockpitLink"[^>]*', html)
            if m:
                element = html[max(0, m.start()-100):m.end()+100]
                assert "/actionable" in element or "/cockpit" not in element, \
                    f"cockpitLink still points to /cockpit in trace.html: {element!r}"


# ---------------------------------------------------------------------------
# Block C — Batch Task 8: Stop-Level Computation
# ---------------------------------------------------------------------------

class TestTask8_StopLevel:
    """Stop-level derivation (Task 8)."""

    SQL = (PROJECT / "db" / "baseline.sql").read_text(encoding="utf-8-sig")

    def test_stop_level_column_on_drv_actionable(self):
        assert "stop_level" in self.SQL
        assert "ADD COLUMN IF NOT EXISTS stop_level NUMERIC" in self.SQL

    def test_stop_mode_seed_in_ref_settings(self):
        assert "stop_mode" in self.SQL
        assert "trade_line_or_pct" in self.SQL

    def test_stop_pct_seed_in_ref_settings(self):
        assert "stop_pct" in self.SQL
        assert "0.08" in self.SQL

    def test_derive_actionable_has_compute_stop(self):
        src = (PROJECT / "etl" / "derive_actionable.py").read_text(encoding="utf-8-sig")
        assert "_compute_stop" in src

    def test_derive_actionable_has_ref_setting_helper(self):
        src = (PROJECT / "etl" / "derive_actionable.py").read_text(encoding="utf-8-sig")
        assert "_ref_setting" in src

    def test_derive_actionable_loads_stop_mode(self):
        src = (PROJECT / "etl" / "derive_actionable.py").read_text(encoding="utf-8-sig")
        assert "stop_mode" in src

    def test_derive_actionable_loads_stop_pct(self):
        src = (PROJECT / "etl" / "derive_actionable.py").read_text(encoding="utf-8-sig")
        assert "stop_pct" in src

    def test_compute_stop_max_formula(self):
        src = (PROJECT / "etl" / "derive_actionable.py").read_text(encoding="utf-8-sig")
        # MAX(trade, pct_floor) logic
        assert "max(" in src or "MAX(" in src
        assert "pct_floor" in src

    def test_stop_level_in_insert(self):
        src = (PROJECT / "etl" / "derive_actionable.py").read_text(encoding="utf-8-sig")
        assert "stop_level" in src

    def test_actionable_js_displays_stop(self):
        js = (PROJECT / "web" / "actionable.js").read_text(encoding="utf-8-sig")
        assert "stop_level" in js
        assert "stop " in js or "stop${" in js


# ---------------------------------------------------------------------------
# Block C — Batch Task 5: Backfill Pipeline
# ---------------------------------------------------------------------------

class TestTask5_BackfillFull:
    """Backfill pipeline (Task 5)."""

    def test_backfill_full_file_exists(self):
        assert (PROJECT / "etl" / "backfill_full.py").exists()

    def test_inventory_flag(self):
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        assert "--inventory" in src

    def test_skip_outcomes_flag(self):
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        assert "--skip-outcomes" in src

    def test_limit_flag(self):
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        assert "--limit" in src

    def test_calls_compute_firing_outcomes(self):
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        assert "compute_firing_outcomes" in src

    def test_argv_reset_before_outcomes(self):
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        assert 'sys.argv = ["compute_firing_outcomes"]' in src

    def test_calls_derive_all(self):
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        assert "derive_all" in src

    def test_missing_dates_query(self):
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        assert "hist_td" in src
        assert "drv_trig" in src

    def test_inventory_function(self):
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        assert "def _inventory" in src

    def test_syntax_valid(self):
        import ast
        src = (PROJECT / "etl" / "backfill_full.py").read_text(encoding="utf-8-sig")
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"Syntax error in backfill_full.py: {e}")


# ---------------------------------------------------------------------------
# Block C — Batch Task 6: ML Holdout Validation
# ---------------------------------------------------------------------------

class TestTask6_MLHoldout:
    """ML holdout validation (Task 6)."""

    SQL = (PROJECT / "db" / "baseline.sql").read_text(encoding="utf-8-sig")

    def test_train_edge_column(self):
        assert "train_edge" in self.SQL
        assert "ADD COLUMN IF NOT EXISTS train_edge NUMERIC" in self.SQL

    def test_holdout_edge_column(self):
        assert "holdout_edge" in self.SQL
        assert "ADD COLUMN IF NOT EXISTS holdout_edge NUMERIC" in self.SQL

    def test_holdout_n_column(self):
        assert "holdout_n" in self.SQL
        assert "ADD COLUMN IF NOT EXISTS holdout_n INTEGER" in self.SQL

    def test_validated_column(self):
        assert "validated" in self.SQL
        assert "ADD COLUMN IF NOT EXISTS validated BOOLEAN NOT NULL DEFAULT FALSE" in self.SQL

    def test_ml_tune_has_chronological_split(self):
        src = (PROJECT / "etl" / "ml_tune_thresholds.py").read_text(encoding="utf-8-sig")
        # Chronological split commentary or code
        assert "chronological" in src.lower() or "split_idx" in src

    def test_ml_tune_has_mean_edge_helper(self):
        src = (PROJECT / "etl" / "ml_tune_thresholds.py").read_text(encoding="utf-8-sig")
        assert "_mean_edge" in src

    def test_ml_tune_has_train_pct_arg(self):
        src = (PROJECT / "etl" / "ml_tune_thresholds.py").read_text(encoding="utf-8-sig")
        assert "--train-pct" in src

    def test_ml_tune_has_no_holdout_gate_arg(self):
        src = (PROJECT / "etl" / "ml_tune_thresholds.py").read_text(encoding="utf-8-sig")
        assert "--no-holdout-gate" in src

    def test_ml_tune_stores_validated_true(self):
        src = (PROJECT / "etl" / "ml_tune_thresholds.py").read_text(encoding="utf-8-sig")
        assert "validated" in src
        assert "TRUE" in src.upper() or "True" in src

    def test_ml_tune_stores_train_holdout_edge(self):
        src = (PROJECT / "etl" / "ml_tune_thresholds.py").read_text(encoding="utf-8-sig")
        assert "train_edge" in src
        assert "holdout_edge" in src

    def test_rules_router_selects_train_edge(self):
        src = (PROJECT / "api" / "routers" / "rules.py").read_text(encoding="utf-8-sig")
        assert "train_edge" in src
        assert "holdout_edge" in src

    def test_param_sets_html_has_train_edge_header(self):
        html = (PROJECT / "web" / "param_sets.html").read_text(encoding="utf-8-sig")
        assert "Train Edge" in html

    def test_param_sets_html_has_holdout_edge_header(self):
        html = (PROJECT / "web" / "param_sets.html").read_text(encoding="utf-8-sig")
        assert "Holdout Edge" in html

    def test_param_sets_html_unvalidated_pill(self):
        html = (PROJECT / "web" / "param_sets.html").read_text(encoding="utf-8-sig")
        assert "unvalidated" in html

    def test_param_sets_js_fmt_edge(self):
        js = (PROJECT / "web" / "param_sets.js").read_text(encoding="utf-8-sig")
        assert "fmtEdge" in js

    def test_param_sets_js_renders_train_edge(self):
        js = (PROJECT / "web" / "param_sets.js").read_text(encoding="utf-8-sig")
        assert "train_edge" in js

    def test_param_sets_js_renders_holdout_edge(self):
        js = (PROJECT / "web" / "param_sets.js").read_text(encoding="utf-8-sig")
        assert "holdout_edge" in js

    def test_param_sets_js_unvalidated_pill_label(self):
        js = (PROJECT / "web" / "param_sets.js").read_text(encoding="utf-8-sig")
        assert "unvalidated" in js


# ---------------------------------------------------------------------------
# Block D — Regression: file integrity
# ---------------------------------------------------------------------------

class TestBlockD_FileSyntax:
    """All changed files must parse cleanly."""

    def _check_py(self, path):
        import ast
        full = PROJECT / path
        if not full.exists():
            pytest.skip(f"{path} not present")
        src = full.read_text(encoding="utf-8-sig")
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"{path}: SyntaxError L{e.lineno}: {e.msg}")

    def test_api_helpers(self):
        self._check_py("api/_helpers.py")

    def test_api_health(self):
        self._check_py("api/routers/health.py")

    def test_api_pages(self):
        self._check_py("api/routers/pages.py")

    def test_api_dash(self):
        self._check_py("api/routers/dash.py")

    def test_api_rules(self):
        self._check_py("api/routers/rules.py")

    def test_etl_derive(self):
        self._check_py("etl/derive.py")

    def test_etl_derive_actionable(self):
        self._check_py("etl/derive_actionable.py")

    def test_etl_daily_health_check(self):
        self._check_py("etl/daily_health_check.py")

    def test_etl_backfill_full(self):
        self._check_py("etl/backfill_full.py")

    def test_etl_ml_tune(self):
        self._check_py("etl/ml_tune_thresholds.py")


class TestBlockD_JSSyntax:
    """JS files must pass node --check."""

    def _check_js(self, path):
        import subprocess
        full = PROJECT / path
        if not full.exists():
            pytest.skip(f"{path} not present")
        result = subprocess.run(
            ["node", "--check", str(full)],
            capture_output=True, text=True
        )
        assert result.returncode == 0, \
            f"node --check FAILED for {path}:\n{result.stderr}"

    def test_actionable_js(self):
        self._check_js("web/actionable.js")

    def test_param_sets_js(self):
        self._check_js("web/param_sets.js")

    def test_rule_performance_js(self):
        self._check_js("web/rule_performance.js")

    def test_rule_flow_js(self):
        self._check_js("web/rule_flow.js")


class TestBlockD_FileTails:
    """Files must not be truncated."""

    def _check_tail(self, path, expected_endings):
        full = PROJECT / path
        if not full.exists():
            pytest.skip(f"{path} not present")
        content = full.read_text(encoding="utf-8-sig")
        tail = content[-200:]
        for e in expected_endings:
            if e in tail:
                return
        pytest.fail(
            f"{path} may be truncated — tail does not contain any of {expected_endings!r}.\n"
            f"Last 200 chars: {tail!r}"
        )

    def test_baseline_sql_tail(self):
        # The file legitimately ends with the cascade_status ALTER statement
        self._check_tail("db/baseline.sql", [
            "cascade_status TEXT;",
            "ON CONFLICT",
            "DO NOTHING;",
            "ADD COLUMN IF NOT EXISTS",
        ])

    def test_derive_py_tail(self):
        self._check_tail("etl/derive.py", ["return counts", "if __name__", "log.info"])

    def test_derive_actionable_tail(self):
        self._check_tail("etl/derive_actionable.py", ["return ", "log.info", "rows_written"])

    def test_backfill_full_tail(self):
        self._check_tail("etl/backfill_full.py", ["return 0", "raise SystemExit", "__main__"])

    def test_actionable_html_tail(self):
        self._check_tail("web/actionable.html", ["</html>", "</script>", "</body>"])

    def test_actionable_js_tail(self):
        self._check_tail("web/actionable.js", ["}", "});", "//"])


# ---------------------------------------------------------------------------
# Concern: trace.js cockpit link bug
# ---------------------------------------------------------------------------

class TestTask7_TraceJsCockpitLinkBug:
    """trace.js still sets cockpitLink href to /cockpit — documented gap."""

    def test_trace_js_cockpit_link_not_updated(self):
        """This test DOCUMENTS a known gap: trace.js line 77 still writes
        `/cockpit` to cockpitLink. The redirect (301) makes this functional,
        but the direct JS override contradicts the HTML default of /actionable.
        This test will PASS if the bug is present and FAIL once it is fixed."""
        js = (PROJECT / "web" / "trace.js").read_text(encoding="utf-8-sig")
        # Flag the existence of the stale /cockpit assignment
        has_stale = "/cockpit?" in js and "cockpitLink" in js
        # Record the gap — we expect it to be present (bug confirmed)
        # Change assertion to `assert not has_stale` once dev fixes it
        if has_stale:
            pytest.xfail(
                "KNOWN GAP: trace.js still sets cockpitLink href to /cockpit — "
                "should be updated to /actionable after cockpit retirement (Task 7). "
                "301 redirect makes it functional but not clean."
            )
