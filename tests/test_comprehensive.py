"""
Comprehensive scenario tests covering every change made in this session.

Organized into 8 SCENARIO AREAS:
  A. Phase 1 — Cockpit feedback + rules write-API
  B. Phase 1 — precondition expr + rule scorer + drv_dash thresholds + scheduler
  C. Phase 2 — outlook-change detection, rule groups, trace, position-aware
  D. Phase 3 — briefing, notifications, backtest, cleanup, tests
  E. Portfolio rewrite (CST + FT transactions, FIFO realized gains)
  F. Rules engine fixes (group walker, fired semantics, applied flag, reasons)
  G. File-type rename (CST / FT)
  H. File integrity (every Python compiles, every JS parses)

Each test prints a one-line outcome through pytest's default reporter; the
JSON report writer (tests/test_comprehensive_runner.py) consumes pytest's
own results to populate docs/test_results.json for the /test-results screen.

These tests are pure-Python — no Postgres needed.
"""
from __future__ import annotations

import json
import re
import csv
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# A. Phase 1 — Cockpit feedback path + Rules write-API
# ─────────────────────────────────────────────────────────────────────────────


class TestA_CockpitFeedback:
    """compute_outcomes._determine_hit must score every action code we emit."""

    SETTINGS = {
        "outcome_hit_threshold_buy":  "0.5",
        "outcome_hit_threshold_sell": "-0.5",
        "outcome_hold_threshold":     "1.0",
    }

    @pytest.mark.parametrize("code", ["SA", "STM", "SS", "REMOVE", "REDUCE"])
    def test_sell_codes_hit_on_negative_move(self, code):
        from etl.compute_outcomes import _determine_hit
        assert _determine_hit(code, -1.0, self.SETTINGS) is True

    @pytest.mark.parametrize("code", ["BM", "ADD", "INCREASE"])
    def test_buy_codes_hit_on_positive_move(self, code):
        from etl.compute_outcomes import _determine_hit
        assert _determine_hit(code, 1.0, self.SETTINGS) is True

    @pytest.mark.parametrize("code", ["HOLD", "SKIP"])
    def test_hold_codes_hit_within_band(self, code):
        from etl.compute_outcomes import _determine_hit
        assert _determine_hit(code, 0.3, self.SETTINGS) is True

    def test_acted_meta_code_scored_as_meaningful_move(self):
        from etl.compute_outcomes import _determine_hit
        assert _determine_hit("ACTED", 2.0, self.SETTINGS) is True
        assert _determine_hit("ACTED", 0.1, self.SETTINGS) is False

    def test_unknown_code_falls_through_to_false(self):
        from etl.compute_outcomes import _determine_hit
        assert _determine_hit("WEIRD", 5.0, self.SETTINGS) is False

    def test_trace_router_resolves_acted_to_consolidated_action(self):
        """trace.py should resolve 'ACTED' to drv_actionable.consolidated_action."""
        src = (PROJECT / "api/routers/trace.py").read_text()
        assert 'raw_code == "ACTED"' in src
        assert "SELECT consolidated_action FROM drv_actionable" in src

    def test_user_action_request_supports_all_codes(self):
        from api.models import UserActionRequest
        for code in ("SA", "STM", "ADD", "REMOVE", "ACTED", "SKIP"):
            req = UserActionRequest(as_of_date="2026-05-15", symbol="AAPL", action_code=code)
            assert req.action_code == code


class TestA_RulesWriteAPI:
    """POST/PUT/DELETE /api/rules/* and dryrun endpoints must exist."""

    def test_atomic_dryrun_endpoint_exists(self):
        src = (PROJECT / "api/routers/rules.py").read_text()
        assert '@router.post("/api/rules/atomic/{rule_id}/dryrun"' in src

    def test_composite_create_returns_409_on_duplicate(self):
        src = (PROJECT / "api/routers/rules.py").read_text()
        # The current implementation raises 409 if any composite_rule_code rows exist
        assert "status_code=409" in src
        assert "already exists" in src

    def test_composite_create_validates_atomic_ids(self):
        src = (PROJECT / "api/routers/rules.py").read_text()
        assert "Unknown or deprecated atomic_rule_id" in src

    def test_atomic_rule_ids_type_is_int_list(self):
        from api.models import CompositeRuleCreateRequest
        # Pydantic should accept int list, reject if not coercible
        req = CompositeRuleCreateRequest(rule_code="X", atomic_rule_ids=[1, 2, 3])
        assert req.atomic_rule_ids == [1, 2, 3]


# ─────────────────────────────────────────────────────────────────────────────
# B. Phase 1 — precondition_expr + rule scorer + thresholds + scheduler
# ─────────────────────────────────────────────────────────────────────────────


class TestB_PreconditionExpr:
    """_eval_precondition supports SQL synonyms + derived aliases + fails-open."""

    def test_sql_synonyms(self):
        from etl.derive import _eval_precondition as evp
        row = {"sector": "Equity", "last_price": 7.5}
        assert evp("sector = 'Equity' AND last_price > 5", row) is True

    def test_derived_alias_is_held(self):
        from etl.derive import _eval_precondition as evp
        assert evp("is_held", {"held_today": True}) is True
        assert evp("is_held", {"held_today": False}) is False

    def test_derived_alias_is_equity(self):
        from etl.derive import _eval_precondition as evp
        assert evp("is_equity", {"asset_class": "Equity"}) is True

    def test_fails_open_on_disallowed_node(self):
        from etl.derive import _eval_precondition as evp
        # function call isn't in the AST allow-list — should return True
        assert evp("len(sector) > 0", {"sector": "ETF"}) is True

    def test_empty_expression_is_true(self):
        from etl.derive import _eval_precondition as evp
        assert evp("", {}) is True
        assert evp(None, {}) is True


class TestB_RuleScorer:
    """eval_atomic_rule supports jump / linear / sigmoid; _bucket_weight gone."""

    JUMP = {"scoring_mode": "jump", "brkeout_from": 5, "brkeout_to": 10,
            "wt_below": -1, "wt_between": 1, "wt_above": 2}

    def test_jump_below(self):
        from etl.derive import eval_atomic_rule
        assert eval_atomic_rule(3, self.JUMP) == -1.0

    def test_jump_between(self):
        from etl.derive import eval_atomic_rule
        assert eval_atomic_rule(7, self.JUMP) == 1.0

    def test_jump_above(self):
        from etl.derive import eval_atomic_rule
        assert eval_atomic_rule(15, self.JUMP) == 2.0

    def test_linear_at_boundaries(self):
        from etl.derive import eval_atomic_rule
        lin = {**self.JUMP, "scoring_mode": "linear"}
        assert eval_atomic_rule(5, lin) == -1.0   # at lo
        assert eval_atomic_rule(10, lin) == 2.0   # at hi

    def test_sigmoid_smooth_transition(self):
        from etl.derive import eval_atomic_rule
        sig = {**self.JUMP, "scoring_mode": "sigmoid",
               "score_params": {"k": 0.5, "x0": 7.5}}
        # Far below should approach wt_below, far above approach wt_above
        v_low = eval_atomic_rule(0, sig)
        v_high = eval_atomic_rule(20, sig)
        assert v_low < 0
        assert v_high > 1.0

    def test_null_value_returns_zero(self):
        from etl.derive import eval_atomic_rule
        assert eval_atomic_rule(None, self.JUMP) == 0.0

    def test_bucket_weight_removed(self):
        import etl.derive as D
        assert not hasattr(D, "_bucket_weight"), \
            "_bucket_weight should be gone — drv_trig now uses eval_atomic_rule"


class TestB_DrvDashThresholds:
    """drv_dash now reads ref_settings + populates zone_signal."""

    def test_derive_dash_reads_settings(self):
        src = (PROJECT / "etl/derive.py").read_text()
        assert "dash_threshold_low_pct" in src
        assert "dash_threshold_high_pct" in src
        # zone_signal must be Y/N/W not None
        assert 'zone = "Y"' in src or "zone = 'Y'" in src

    def test_baseline_seeds_thresholds(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "'dash_threshold_low_pct'" in sql
        assert "'dash_threshold_high_pct'" in sql


class TestB_NightlyScheduler:
    """scheduler.py runs compute_outcomes nightly via in-memory state."""

    def test_state_round_trip(self, tmp_path):
        from etl.scheduler import _read_nightly_state, _write_nightly_state
        from datetime import date
        p = tmp_path / "state.txt"
        assert _read_nightly_state(p) is None
        _write_nightly_state(p, date(2026, 5, 17))
        assert _read_nightly_state(p) == date(2026, 5, 17)

    def test_nightly_hour_setting_present(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "'outcomes_compute_hour'" in sql

    def test_no_nightly_flag_in_cli(self):
        src = (PROJECT / "etl/scheduler.py").read_text()
        assert "--no-nightly" in src


# ─────────────────────────────────────────────────────────────────────────────
# C. Phase 2 — outlook-change + rule groups + trace + position-aware + perf
# ─────────────────────────────────────────────────────────────────────────────


class TestC_OutlookChangeDetection:
    """v_outlook_changes function, /api/outlook/changes endpoint, banner JS."""

    def test_sql_function_defined(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "CREATE OR REPLACE FUNCTION v_outlook_changes" in sql
        assert "dominant_action" in sql

    def test_priority_ordering_remove_first(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        # The CASE expression encodes REMOVE=1, REDUCE=2, ADD=3, INCREASE=4
        assert re.search(r"WHEN 'REMOVE'\s+THEN 1", sql)
        assert re.search(r"WHEN 'REDUCE'\s+THEN 2", sql)

    def test_api_endpoint_defined(self):
        src = (PROJECT / "api/routers/dash.py").read_text()
        assert '@router.get("/api/outlook/changes"' in src

    def test_dashboard_banner_loader(self):
        js = (PROJECT / "web/app.js").read_text()
        assert "loadOutlookChanges" in js
        assert "/api/outlook/changes" in js


class TestC_RuleGroupsInActionable:
    """drv_actionable.triggered_group_ids + rule-group folded into action competition."""

    def test_triggered_group_ids_column_added(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "ADD COLUMN IF NOT EXISTS triggered_group_ids JSONB" in sql

    def test_derive_actionable_evaluates_groups(self):
        src = (PROJECT / "etl/derive_actionable.py").read_text()
        assert "eval_rule_group" in src
        assert "triggered_groups" in src
        assert "RULES:" in src   # synthetic source prefix


class TestC_TraceOutlookAttribution:
    """/api/trace/{sym} returns outlook + actionable blocks; trace.js renders them."""

    def test_api_returns_outlook_and_actionable(self):
        src = (PROJECT / "api/routers/trace.py").read_text()
        assert '"outlook"' in src and '"actionable"' in src
        assert "outlook_changed" in src
        assert "n_sources_changed" in src

    def test_trace_js_renders_outlook(self):
        js = (PROJECT / "web/trace.js").read_text()
        assert "renderOutlook" in js
        assert "Outlook attribution" in js


class TestC_PositionAwareSuppression:
    """derive_actionable suppresses REMOVE-not-held, ADD-established, INCREASE-at-ceiling."""

    def test_all_four_suppression_branches(self):
        src = (PROJECT / "etl/derive_actionable.py").read_text()
        for marker in ("NOT HELD", "ALREADY ESTABLISHED",
                       "AT CEILING", "AT FLOOR"):
            assert marker in src, f"missing suppression branch: {marker}"


class TestC_PerformanceWindowSelector:
    """v_rule_performance_window + window/min_n/from/to params."""

    def test_window_function_defined(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "CREATE OR REPLACE FUNCTION v_rule_performance_window" in sql
        assert "percentile_cont" in sql

    def test_api_accepts_window_params(self):
        src = (PROJECT / "api/routers/rules.py").read_text()
        assert "min_n: int" in src
        # query params from/to are aliased
        assert 'alias="from"' in src and 'alias="to"' in src


# ─────────────────────────────────────────────────────────────────────────────
# D. Phase 3 — briefing + notifications + backtest + cleanup + tests
# ─────────────────────────────────────────────────────────────────────────────


class TestD_DailyBriefing:
    """/api/briefing returns 4 blocks + warnings; dashboard card renders."""

    def test_endpoint_returns_four_blocks(self):
        src = (PROJECT / "api/routers/dash.py").read_text()
        assert '@router.get("/api/briefing"' in src
        for k in ("yesterday_actions", "outlook_flips",
                  "allocation_drift", "load_failures"):
            assert f'"{k}"' in src

    def test_dashboard_card_loader(self):
        js = (PROJECT / "web/app.js").read_text()
        assert "loadBriefing" in js


class TestD_Notifications:
    """notify() module is no-op when settings off; toast + email behind flags."""

    def test_notify_silent_when_disabled(self):
        from etl.notify import notify
        # Both flags default to False — call must not raise
        notify("test", "hello", "info")

    def test_settings_has_notify_flags(self):
        from config.settings import settings
        for attr in ("notify_toast", "notify_email",
                     "smtp_host", "smtp_port", "smtp_user", "notify_email_to"):
            assert hasattr(settings, attr)

    def test_levels_typed(self):
        from etl.notify import notify
        notify("t", "m", "info")
        notify("t", "m", "warn")
        notify("t", "m", "error")


class TestD_BacktestHarness:
    """python -m etl.backtest exposes the expected signature + CLI."""

    def test_backtest_signature(self):
        import inspect
        from etl.backtest import backtest
        sig = inspect.signature(backtest)
        params = list(sig.parameters)
        for p in ("rule_code", "rule_id", "from_date", "to_date",
                  "windows", "hit_threshold_pct"):
            assert p in params

    def test_hit_for_helper(self):
        from etl.backtest import _hit_for
        # bull direction, threshold 0.5
        assert _hit_for("bull", 1.0, 0.5) is True
        assert _hit_for("bull", -1.0, 0.5) is False
        assert _hit_for("bear", -1.0, 0.5) is True
        assert _hit_for("bull", None, 0.5) is None


class TestD_CleanupMetaTables:
    """etl/cleanup.py prunes meta_* tables behind --meta flag."""

    def test_meta_prune_targets(self):
        from etl.cleanup import META_PRUNE, META_RETENTION_DAYS
        target_tables = [t[0] for t in META_PRUNE]
        for t in ("meta_etl_run", "meta_derived_run", "meta_cleanup_history"):
            assert t in target_tables
        assert META_RETENTION_DAYS == 90

    def test_cleanup_cli_has_meta_flags(self):
        src = (PROJECT / "etl/cleanup.py").read_text()
        for flag in ("--meta", "--meta-only", "--retention-days"):
            assert flag in src


class TestD_PytestSuite:
    """Phase 3 #17 added 4 test files."""

    @pytest.mark.parametrize("name", [
        "test_eval_atomic_rule.py",
        "test_precondition_expr.py",
        "test_determine_hit.py",
        "test_outlook_changes_view.py",
    ])
    def test_test_file_present(self, name):
        assert (PROJECT / "tests" / name).exists()

    def test_conftest_has_db_fixtures(self):
        src = (PROJECT / "tests/conftest.py").read_text()
        assert "db_available" in src and "db_session" in src


# ─────────────────────────────────────────────────────────────────────────────
# E. Portfolio rewrite — transactions + FIFO + new endpoints + screen tabs
# ─────────────────────────────────────────────────────────────────────────────


class TestE_PortfolioSchema:
    """hist_ft + drv_realized_gain are in baseline.sql."""

    def test_hist_ft_table(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS hist_ft" in sql
        for col in ("trade_date", "settlement_date", "action_kind",
                    "accrued_interest", "account_number"):
            assert col in sql

    def test_drv_realized_gain_table(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS drv_realized_gain" in sql
        assert "lots_consumed      JSONB" in sql
        assert "PRIMARY KEY (source, account, symbol, sell_date, shares_sold)" in sql


class TestE_FidelityCSVLoader:
    """load_f_transactions parses Fidelity Accounts_History.csv format."""

    def test_action_kind_classification(self):
        from etl.load_raw import _f_action_kind
        cases = [
            ("YOU BOUGHT 10X GENOMICS INC CL A COM (TXG) (Cash)", "BUY"),
            ("YOU SOLD ALPS ETF TR ALERIAN MLP (AMLP) (Cash)", "SELL"),
            ("PURCHASE INTO CORE ACCOUNT FIDELITY GOVERNMENT MONEY MARKET (SPAXX)", "CASH"),
            ("DIVIDEND RECEIVED COMPANY X", "DIV"),
            ("REINVESTMENT INTO DRIP", "BUY"),
            ("LONG-TERM CAP GAIN DISTRIBUTION", "DIV"),
            ("UNKNOWN-NEW-ACTION-TYPE", "OTHER"),
            ("", "OTHER"),
        ]
        for action_text, expected in cases:
            from etl.load_raw import _f_action_kind
            assert _f_action_kind(action_text) == expected, \
                f"{action_text!r} → got {_f_action_kind(action_text)}, expected {expected}"

    def test_loader_present(self):
        from etl.load_raw import load_f_transactions
        assert callable(load_f_transactions)

    def test_actual_csv_parses(self):
        """If the sample Accounts_History.csv is in the repo, classify all rows."""
        csv_path = PROJECT / "Accounts_History.csv"
        if not csv_path.exists():
            pytest.skip("sample Accounts_History.csv not present in repo root")
        with open(csv_path) as f:
            lines = f.readlines()
        hdr = next((i for i, l in enumerate(lines) if l.strip().startswith("Run Date")), None)
        assert hdr is not None, "could not find 'Run Date' header"
        from etl.load_raw import _f_action_kind
        rows = list(csv.DictReader(lines[hdr:]))
        kinds = {}
        for r in rows:
            if not r.get("Run Date") or not r.get("Action"):
                continue
            k = _f_action_kind(r["Action"])
            kinds[k] = kinds.get(k, 0) + 1
        assert kinds.get("BUY", 0) > 0
        assert kinds.get("SELL", 0) > 0


class TestE_FIFOWalker:
    """_process_symbol_events FIFO-matches sells to oldest open buys."""

    def test_simple_fifo_with_two_buy_lots(self):
        from etl.derive_realized import _process_symbol_events
        from datetime import date
        events = [
            {"trade_date": date(2025, 1, 10), "account": "A", "symbol": "X",
             "quantity": 100, "price": 10, "amount": -1000, "fees": 0,
             "kind": "BUY", "raw_action": "buy", "source_file": "f1"},
            {"trade_date": date(2025, 3, 15), "account": "A", "symbol": "X",
             "quantity": 200, "price": 12, "amount": -2400, "fees": 0,
             "kind": "BUY", "raw_action": "buy", "source_file": "f2"},
            {"trade_date": date(2025, 6, 20), "account": "A", "symbol": "X",
             "quantity": -150, "price": 15, "amount": 2250, "fees": 0,
             "kind": "SELL", "raw_action": "sell", "source_file": "f3"},
        ]
        rows = _process_symbol_events(events)
        assert len(rows) == 1
        r = rows[0]
        # FIFO: 100 @ $10 ($1000) + 50 @ $12 ($600) = $1600 cost basis
        assert abs(r["cost_basis"] - 1600) < 0.01
        assert abs(r["sell_proceeds"] - 2250) < 0.01
        assert abs(r["realized_gain"] - 650) < 0.01
        assert len(r["lots_consumed"]) == 2

    def test_unmatched_shares_warning(self):
        from etl.derive_realized import _process_symbol_events
        from datetime import date
        events = [
            {"trade_date": date(2025, 1, 10), "account": "A", "symbol": "Y",
             "quantity": 50, "price": 10, "amount": -500, "fees": 0,
             "kind": "BUY", "raw_action": "buy", "source_file": "f1"},
            {"trade_date": date(2025, 6, 20), "account": "A", "symbol": "Y",
             "quantity": -100, "price": 15, "amount": 1500, "fees": 0,
             "kind": "SELL", "raw_action": "sell", "source_file": "f2"},
        ]
        rows = _process_symbol_events(events)
        assert len(rows) == 1
        has_warning = any("warning" in str(lot).lower()
                          for lot in rows[0]["lots_consumed"])
        assert has_warning, "expected unmatched-shares warning in lots_consumed"

    def test_long_term_classification(self):
        from etl.derive_realized import _process_symbol_events
        from datetime import date
        events = [
            {"trade_date": date(2024, 1, 1), "account": "A", "symbol": "Z",
             "quantity": 100, "price": 10, "amount": -1000, "fees": 0,
             "kind": "BUY", "raw_action": "buy", "source_file": "f1"},
            {"trade_date": date(2025, 6, 1), "account": "A", "symbol": "Z",
             "quantity": -100, "price": 15, "amount": 1500, "fees": 0,
             "kind": "SELL", "raw_action": "sell", "source_file": "f2"},
        ]
        rows = _process_symbol_events(events)
        # Held ~17 months > 365 days → long-term
        assert rows[0]["is_long_term"] is True


class TestE_PortfolioEndpoints:
    """/api/portfolio/{activity,realized,snapshot-status} routes registered."""

    def test_all_three_endpoints(self):
        src = (PROJECT / "api/routers/dash.py").read_text()
        for path in ("/api/portfolio/activity",
                     "/api/portfolio/realized",
                     "/api/portfolio/snapshot-status"):
            assert f'@router.get("{path}"' in src


class TestE_PortfolioScreen:
    """Portfolio HTML has 3 tabs + JS lazy-loads activity/realized."""

    def test_three_tab_panes_present(self):
        html = (PROJECT / "web/portfolio.html").read_text()
        for tab in ("pf-pane-positions", "pf-pane-activity", "pf-pane-realized"):
            assert tab in html
        assert "snapshotStatusBanner" in html

    def test_js_has_tab_loaders(self):
        js = (PROJECT / "web/portfolio.js").read_text()
        assert "loadActivity" in js
        assert "loadRealized" in js
        assert "loadSnapshotStatus" in js


# ─────────────────────────────────────────────────────────────────────────────
# F. Rules engine fixes (#C1-#C4)
# ─────────────────────────────────────────────────────────────────────────────


class TestF_RulesEngineFixes:
    """Group walker optimized, fired = n_member_hit > 0, applied flag added."""

    def test_group_walker_in_memory(self):
        src = (PROJECT / "etl/derive.py").read_text()
        assert "_eval_group_inline" in src
        assert "group_defs" in src

    def test_fired_uses_n_member_hit(self):
        src = (PROJECT / "etl/derive.py").read_text()
        assert "fired = n_member_hit > 0" in src

    def test_triggered_atomics_has_applied_flag(self):
        src = (PROJECT / "etl/derive.py").read_text()
        assert '"applied": value is not None' in src

    def test_trace_per_rule_reasons(self):
        src = (PROJECT / "api/routers/trace.py").read_text()
        for kw in ("no_column", "no_data", "no_thresholds",
                   "below_band", "above_band", "in_band",
                   "value_not_numeric"):
            assert kw in src, f"missing reason category: {kw}"

    def test_health_endpoint_registered(self):
        src = (PROJECT / "api/routers/rules.py").read_text()
        assert '@router.get("/api/rules/health"' in src

    def test_rebuild_cli_present(self):
        path = PROJECT / "etl/rebuild_rules.py"
        assert path.exists()
        src = path.read_text()
        for step in ("_step_refresh_refs", "_step_derive", "_step_health"):
            assert step in src


# ─────────────────────────────────────────────────────────────────────────────
# G. CST + FT file types
# ─────────────────────────────────────────────────────────────────────────────


class TestG_FileTypeRename:
    """CS transactions → CST; F transactions → FT, in code + seeds."""

    def test_old_codes_gone_from_code(self):
        # The lowercase 'cs_transactions' / 'f_transactions' STRING literals
        # should be gone from etl_load.py (the routing branches).
        src = (PROJECT / "etl/etl_load.py").read_text()
        # Check that the file_type=… kwargs use the new codes
        assert "file_type='CST'" in src or 'file_type="CST"' in src
        assert "file_type='FT'" in src or 'file_type="FT"' in src
        assert "file_type='cs_transactions'" not in src
        assert "file_type='f_transactions'" not in src

    def test_table_names_unchanged(self):
        """Table names hist_cst / hist_ft must stay."""
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "CREATE TABLE IF NOT EXISTS hist_cst" in sql
        assert "CREATE TABLE IF NOT EXISTS hist_ft" in sql

    def test_ref_load_files_seed_present(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "C:\\Ashok\\Investing\\Stocks\\CST\\Archive" in sql
        assert "C:\\Ashok\\Investing\\Stocks\\FT\\Archive" in sql
        assert "'SUN'" in sql
        assert "TIME '16:00:00'" in sql

    def test_check_constraint_allows_new_windows(self):
        sql = (PROJECT / "db/baseline.sql").read_text()
        assert "'WINDOW_365_DAYS'" in sql
        assert "'WINDOW_180_DAYS'" in sql
        assert "'WINDOW_90_DAYS'" in sql


# ─────────────────────────────────────────────────────────────────────────────
# H. File integrity — every Python compiles, every JS parses
# ─────────────────────────────────────────────────────────────────────────────


PYTHON_FILES = [
    "api/routers/rules.py", "api/routers/trace.py", "api/routers/dash.py",
    "api/routers/pages.py", "api/routers/ref.py", "api/routers/health.py",
    "api/routers/monitor.py", "api/main.py", "api/models.py", "api/_helpers.py",
    "etl/derive.py", "etl/derive_actionable.py", "etl/derive_realized.py",
    "etl/derive_outlook_action.py", "etl/compute_outcomes.py", "etl/scheduler.py",
    "etl/notify.py", "etl/backtest.py", "etl/cleanup.py", "etl/load_raw.py",
    "etl/etl_load.py", "etl/rebuild_rules.py", "etl/refresh_ref.py",
    "etl/mark_sales.py", "etl/db.py", "etl/_derive_common.py",
    "etl/position_rules.py", "etl/rule_groups.py", "etl/mappings.py",
    "etl/excel_io.py", "etl/casters.py", "etl/_logging.py",
    "etl/ma_codegen.py", "etl/auto_enrich_registry.py",
    "etl/enrich_ref_ma_columns.py", "etl/seed_ref_ma_columns.py",
    "etl/build_drv_cat_layers.py", "etl/derive_v2.py",
    "etl/tickers_initial_load.py", "etl/compute_outcomes.py",
    "db/init_db.py", "db/reset_db.py", "db/dump_schema.py",
    "config/settings.py", "_verify_cst_ft.py",
]


@pytest.mark.parametrize("path", sorted(set(PYTHON_FILES)))
def test_python_file_compiles(path):
    import ast
    full = PROJECT / path
    if not full.exists():
        pytest.skip(f"{path} not present")
    try:
        ast.parse(full.read_text())
    except SyntaxError as e:
        pytest.fail(f"{path}: SyntaxError L{e.lineno}: {e.msg}")


# JS — list files we touched; check via Node would require subprocess
JS_FILES = [
    "web/app.js", "web/portfolio.js", "web/trace.js", "web/trig.js",
    "web/rules.js", "web/composite_edit.js", "web/actionable.js",
    "web/explore.js", "web/cockpit.js", "web/ref.js", "web/dbstats.js",
    "web/_common.js", "web/health_banner.js", "web/file_monitor.js",
]


@pytest.mark.parametrize("path", sorted(set(JS_FILES)))
def test_js_file_parses(path):
    """node --check via subprocess; skip if node not installed."""
    import subprocess
    full = PROJECT / path
    if not full.exists():
        pytest.skip(f"{path} not present")
    try:
        r = subprocess.run(["node", "--check", str(full)],
                           capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            pytest.fail(f"{path}: {r.stderr.strip().splitlines()[0]}")
    except FileNotFoundError:
        pytest.skip("node not installed")


def test_baseline_sql_parses():
    """sqlparse to confirm baseline.sql tokenizes cleanly."""
    try:
        import sqlparse
    except ImportError:
        pytest.skip("sqlparse not installed")
    raw = (PROJECT / "db/baseline.sql").read_text()
    stmts = sqlparse.split(raw)
    assert len(stmts) > 100, f"only {len(stmts)} statements parsed — baseline likely truncated"


def test_baseline_has_no_unbalanced_quotes():
    """Strip line comments, then count single quotes per statement."""
    raw = (PROJECT / "db/baseline.sql").read_text()
    no_comments = re.sub(r"--[^\n]*", "", raw)
    try:
        import sqlparse
    except ImportError:
        pytest.skip("sqlparse not installed")
    stmts = sqlparse.split(no_comments)
    bad = [s for s in stmts if s.strip() and s.count("'") % 2 != 0]
    assert not bad, f"{len(bad)} statements with unbalanced single quotes"
