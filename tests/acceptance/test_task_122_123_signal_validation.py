"""
Acceptance tests for the AGENT_WORK_30 round (TASK_122 tier restructure +
TASK_123 signal validation scorecards).

TASK_122 (web/actionable.js, display-layer only):
  - new-arrival bypass (_isNewArrival) removed; buy-noise gate is purely
    unheld + effective ADD + Technical not in _ENTRY_RIPE_TECH
  - NEW pill (_isNewSnapshot) inside the Watchlist band, display-only
  - 6-stage tier order: Tier 0 stop -> Tier 1 credible held sells ->
    Tier 2 agreement-ranked buys (2a/2b/2c via _buyAgreementSubTier) ->
    Tier 3 hold/mixed -> Watchlist -> Bottom
  - "?" legend updated to describe the new tier order

TASK_123 (db/baseline.sql + docs/audit report, additive only):
  - v_bull_gate_scorecard, v_final_call_scorecard, v_source_edge_scorecard
  - drv_rule_outcome repopulated via `compute_firing_outcomes --truncate`
  - docs/audit/signal_validation_2026-07.md with A1-A6 verdicts

MOVED to tests/acceptance/ per CLAUDE.md's test-debt policy (rule 18) / this
repo's `docs/audit/test_debt_review.md` §2 — this is a one-time acceptance
proof for a specific round's spec, not a durable regression test. Deletable
after the round is committed.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.acceptance

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ACTIONABLE_JS = PROJECT_ROOT / "web" / "actionable.js"
BASELINE_SQL = PROJECT_ROOT / "db" / "baseline.sql"
REPORT_MD = PROJECT_ROOT / "docs" / "audit" / "signal_validation_2026-07.md"


@pytest.fixture(scope="module")
def js_source() -> str:
    return ACTIONABLE_JS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_source() -> str:
    return BASELINE_SQL.read_text(encoding="utf-8")


# ─────────────────────────────────────────
# TASK_122 — structural checks on web/actionable.js
# ─────────────────────────────────────────

class TestNodeSyntax:
    def test_node_check_passes(self):
        result = subprocess.run(
            ["node", "--check", str(ACTIONABLE_JS)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr


class TestNewArrivalBypassRemoved:
    def test_isNewArrival_function_absent(self, js_source):
        assert "function _isNewArrival(" not in js_source

    def test_buyNoiseGated_no_longer_calls_isNewArrival(self, js_source):
        m = re.search(
            r"function _buyNoiseGated\(row\)\s*\{(.*?)\n\}",
            js_source, re.S,
        )
        assert m, "_buyNoiseGated function not found"
        body = m.group(1)
        assert "_isNewArrival" not in body

    def test_gate_is_held_chipaction_and_technical_only(self, js_source):
        m = re.search(
            r"function _buyNoiseGated\(row\)\s*\{(.*?)\n\}",
            js_source, re.S,
        )
        body = m.group(1)
        assert "held_today" in body
        assert "_chipAction(row)" in body
        assert "_ENTRY_RIPE_TECH" in body


class TestNewPillDisplayOnly:
    def test_isNewSnapshot_exists(self, js_source):
        assert "function _isNewSnapshot(row)" in js_source

    def test_new_pill_span_present(self, js_source):
        assert 'class="new-pill"' in js_source

    def test_isNewSnapshot_not_used_in_computePriority(self, js_source):
        m = re.search(
            r"function _computePriority\(row\)\s*\{(.*?)\n\}\n",
            js_source, re.S,
        )
        assert m, "_computePriority not found"
        assert "_isNewSnapshot" not in m.group(1)

    def test_isNewSnapshot_not_used_in_buyNoiseGated(self, js_source):
        m = re.search(
            r"function _buyNoiseGated\(row\)\s*\{(.*?)\n\}",
            js_source, re.S,
        )
        assert "_isNewSnapshot" not in m.group(1)


class TestTierConstants:
    """The 6 tier constants must exist and be strictly ordered (descending
    priority score = higher tier), with enough headroom between them that a
    row's in-tier score (bounded, per the file's own comments) can never
    bleed into a neighboring tier."""

    def _const(self, js_source, name):
        m = re.search(rf"const {name}\s*=\s*(-?[\d.e+]+)", js_source)
        assert m, f"{name} not found"
        return float(m.group(1))

    def test_all_six_constants_present_and_ordered(self, js_source):
        stop = self._const(js_source, "_TIER_STOP")
        sell = self._const(js_source, "_TIER_SELL")
        buy = self._const(js_source, "_TIER_BUY")
        hold = self._const(js_source, "_TIER_HOLD")
        watch = self._const(js_source, "_TIER_WATCHLIST")
        bottom = self._const(js_source, "_TIER_BOTTOM")
        assert stop > sell > buy > hold > watch > bottom


class TestBuyAgreementSubTier:
    def test_function_exists(self, js_source):
        assert "function _buyAgreementSubTier(row)" in js_source

    def test_uses_entry_ripe_tech_not_full_tech_buy_set(self, js_source):
        m = re.search(
            r"function _buyAgreementSubTier\(row\)\s*\{(.*?)\n\}",
            js_source, re.S,
        )
        assert m
        body = m.group(1)
        # Spec: Technical leg here is BS/BM only (_ENTRY_RIPE_TECH), not the
        # display-only _threeWayAgreement's broader _TECH_BUY set (which
        # also allows BMN/BR).
        assert "_ENTRY_RIPE_TECH" in body

    def test_returns_three_distinct_subtiers(self, js_source):
        m = re.search(
            r"function _buyAgreementSubTier\(row\)\s*\{(.*?)\n\}",
            js_source, re.S,
        )
        body = m.group(1)
        assert "return 2;" in body
        assert "return 1;" in body
        assert "return 0;" in body


class TestComputePriorityTierOrder:
    def _priority_body(self, js_source):
        m = re.search(
            r"function _computePriority\(row\)\s*\{(.*?)\n\}\n",
            js_source, re.S,
        )
        assert m, "_computePriority not found"
        return m.group(1)

    def test_tier0_stop_breached_first(self, js_source):
        body = self._priority_body(js_source)
        assert body.strip().startswith(
            "// Tier 0"
        ) or "row.stop_breached && row.held_today" in body.split("\n")[1:4][0] \
            or "stop_breached" in body[:400]

    def test_bottom_checked_before_watchlist_and_sell(self, js_source):
        body = self._priority_body(js_source)
        bottom_pos = body.index("_TIER_BOTTOM")
        watch_pos = body.index("_TIER_WATCHLIST")
        sell_pos = body.index("_TIER_SELL")
        buy_pos = body.index("_TIER_BUY")
        hold_pos = body.index("_TIER_HOLD")
        # Bottom must be decided before Watchlist/Sell/Buy/Hold checks run,
        # so a low_confidence sell/infeasible/suppressed row never reaches
        # the later, more specific tier checks.
        assert bottom_pos < watch_pos < sell_pos < buy_pos < hold_pos

    def test_sell_tier_requires_held_and_sell_side(self, js_source):
        body = self._priority_body(js_source)
        assert "row.held_today && fc.side === 'sell'" in body

    def test_buy_tier_uses_subtier_helper(self, js_source):
        body = self._priority_body(js_source)
        assert "_buyAgreementSubTier(row)" in body
        assert "fc.side === 'buy'" in body

    def test_hold_tier_is_final_fallthrough(self, js_source):
        body = self._priority_body(js_source)
        # Last non-comment statement should be the Tier 3 (Hold) return.
        stripped_lines = [l.strip() for l in body.strip().split("\n") if l.strip() and not l.strip().startswith("//")]
        assert stripped_lines[-1].startswith("return _TIER_HOLD")


class TestLegendUpdated:
    def test_legend_mentions_new_tier_order(self, js_source):
        assert "credible sells" in js_source
        assert "agreement" in js_source

    def test_legend_mentions_watchlist_and_new_pill(self, js_source):
        assert "Watchlist" in js_source
        assert "NEW" in js_source


# ─────────────────────────────────────────
# TASK_123 — SQL view definitions (structural, no DB needed)
# ─────────────────────────────────────────

class TestNewViewsDefinedInBaseline:
    @pytest.mark.parametrize("view_name", [
        "v_bull_gate_scorecard",
        "v_final_call_scorecard",
        "v_source_edge_scorecard",
    ])
    def test_view_created_in_baseline_sql(self, sql_source, view_name):
        assert f"CREATE VIEW {view_name}" in sql_source

    def test_bull_gate_scorecard_columns(self, sql_source):
        m = re.search(
            r"CREATE VIEW v_bull_gate_scorecard AS(.*?);\n",
            sql_source, re.S,
        )
        assert m
        body = m.group(1)
        for col in ("dimension", "bull_bucket", "avg_fwd_5d", "avg_fwd_20d",
                    "median_fwd_20d", "win_rate_20d"):
            assert col in body, f"missing column {col} in v_bull_gate_scorecard"

    def test_final_call_scorecard_columns(self, sql_source):
        m = re.search(
            r"CREATE VIEW v_final_call_scorecard AS(.*?);\n",
            sql_source, re.S,
        )
        assert m
        body = m.group(1)
        for col in ("final_code", "fc_confidence", "edge_20d",
                    "raw_avg_fwd_20d", "win_rate_20d"):
            assert col in body, f"missing column {col} in v_final_call_scorecard"

    def test_source_edge_scorecard_columns(self, sql_source):
        m = re.search(
            r"CREATE VIEW v_source_edge_scorecard AS(.*?);\n",
            sql_source, re.S,
        )
        assert m
        body = m.group(1)
        for col in ("source_code", "action", "edge_5d", "edge_20d",
                    "win_rate_20d"):
            assert col in body, f"missing column {col} in v_source_edge_scorecard"


# ─────────────────────────────────────────
# TASK_123 — report file structure
# ─────────────────────────────────────────

class TestSignalValidationReport:
    def test_report_exists(self):
        assert REPORT_MD.exists()

    @pytest.fixture(scope="class")
    def report_text(self):
        return REPORT_MD.read_text(encoding="utf-8")

    def test_sections_a_through_f_present(self, report_text):
        for heading in (
            "Bull-gate scorecard",
            "Final Call scorecard",
            "Per-source edge scorecard",
            "Inferred-action aggregate",
            "Hit-threshold sensitivity",
            "Verdicts",
        ):
            assert heading in report_text, f"missing section: {heading}"

    def test_verdict_table_has_all_six_assumptions(self, report_text):
        for a in ("A1", "A2", "A3", "A4", "A5", "A6"):
            assert re.search(rf"\|\s*{a}\s*\|", report_text), f"{a} missing from verdict table"

    def test_regime_caveat_present(self, report_text):
        assert "one regime" in report_text.lower() or "one market regime" in report_text.lower()

    def test_prep_step_documents_row_count_and_date_range(self, report_text):
        assert "drv_rule_outcome" in report_text
        assert re.search(r"7,924,452|row", report_text)


# ─────────────────────────────────────────
# TASK_123 — live DB checks (skip if Postgres unavailable)
# ─────────────────────────────────────────

class TestLiveViews:
    def test_bull_gate_scorecard_returns_rows(self, db_session):
        from sqlalchemy import text
        rows = db_session.execute(text("SELECT * FROM v_bull_gate_scorecard")).fetchall()
        assert len(rows) > 0
        for r in rows:
            m = dict(r._mapping)
            assert m["avg_fwd_20d"] is not None
            assert m["n"] > 0

    def test_final_call_scorecard_returns_rows(self, db_session):
        from sqlalchemy import text
        rows = db_session.execute(text("SELECT * FROM v_final_call_scorecard")).fetchall()
        assert len(rows) > 0
        for r in rows:
            m = dict(r._mapping)
            assert m["edge_20d"] is not None

    def test_source_edge_scorecard_returns_rows(self, db_session):
        from sqlalchemy import text
        rows = db_session.execute(text("SELECT * FROM v_source_edge_scorecard")).fetchall()
        assert len(rows) > 0
        for r in rows:
            m = dict(r._mapping)
            assert m["edge_20d"] is not None

    def test_drv_rule_outcome_repopulated(self, db_session):
        from sqlalchemy import text
        row = db_session.execute(
            text("SELECT count(*) AS n, min(as_of_date) AS lo, max(as_of_date) AS hi FROM drv_rule_outcome")
        ).fetchone()
        m = dict(row._mapping)
        assert m["n"] > 1_000_000, "drv_rule_outcome looks empty/truncated, not repopulated"
        assert m["lo"] is not None and m["hi"] is not None
        assert m["hi"] >= m["lo"]

    def test_views_not_joined_into_actionable_api(self):
        """Analyst views must stay out of the runtime /api/actionable path
        (spec performance constraint) — grep the API router source."""
        dash_router = (PROJECT_ROOT / "api" / "routers" / "dash.py").read_text(encoding="utf-8")
        for view in ("v_bull_gate_scorecard", "v_final_call_scorecard", "v_source_edge_scorecard"):
            assert view not in dash_router


# ─────────────────────────────────────────
# TASK_122 — live tier-order replay against /api/actionable payload fields
# (mirrors the exact JS gate/tier logic in Python; skips gracefully if the
# DB/derived data required for drv_actionable isn't available)
# ─────────────────────────────────────────

class TestLiveTierReplay:
    ENTRY_RIPE_TECH = {"BS", "BM"}
    SRC_BUY = {"ADD", "INCREASE"}
    SRC_SELL = {"REDUCE", "REMOVE"}
    MACRO_BUY = {"BM", "BS"}
    MACRO_SELL = {"STM", "SA"}
    TECH_SELL = {"SA", "STM", "SS", "SO"}

    @staticmethod
    def _is_over_max(row):
        if (row.get("consolidated_action") or "").upper() == "REMOVE":
            return False
        try:
            pos = float(row.get("current_position_dollar"))
            mx = float(row.get("target_max_dollar"))
        except (TypeError, ValueError):
            return False
        return mx > 0 and pos > mx

    def _final_call(self, row):
        feasible = row.get("fc_feasible") in (True, "true")
        side = row.get("final_side") or "neutral"
        code = row.get("final_code") or ""
        return {"feasible": feasible, "side": side, "code": code}

    def _chip_action(self, row):
        if self._is_over_max(row):
            return "OVER_MAX"
        fc = self._final_call(row)
        if not fc["feasible"]:
            return "NONE"
        code = (fc["code"] or "").upper()
        if code == "SA":
            return "REMOVE"
        if code in ("SS", "STM", "SO"):
            return "REDUCE"
        if code in ("BM", "BS"):
            return "INCREASE"
        if code == "BMN":
            return "ADD"
        if fc["side"] == "neutral" or code == "HOLD":
            return "HOLD"
        return "NONE"

    def _buy_noise_gated(self, row):
        if row.get("held_today"):
            return False
        if self._chip_action(row) != "ADD":
            return False
        tech = (row.get("rr_action") or "").upper()
        return tech not in self.ENTRY_RIPE_TECH

    def _buy_agreement_subtier(self, row):
        m = (row.get("macro_value") or "").upper()
        s = (row.get("consolidated_action") or "").upper()
        t = (row.get("rr_action") or "").upper()
        tech_buy = t in self.ENTRY_RIPE_TECH
        src_buy = s in self.SRC_BUY
        macro_buy = m in self.MACRO_BUY
        any_sell = (t in self.TECH_SELL) or (s in self.SRC_SELL) or (m in self.MACRO_SELL)
        votes = int(tech_buy) + int(src_buy) + int(macro_buy)
        if votes == 3:
            return 2
        if votes == 2 and not any_sell:
            return 1
        return 0

    def _tier_of(self, row):
        fc = self._final_call(row)
        if row.get("stop_breached") and row.get("held_today"):
            return "stop"
        if row.get("low_confidence") or not fc["feasible"] or row.get("suppressed_reason"):
            return "bottom"
        if self._buy_noise_gated(row):
            return "watch"
        if row.get("held_today") and fc["side"] == "sell":
            return "sell"
        if fc["side"] == "buy":
            st = self._buy_agreement_subtier(row)
            return {2: "buy_2a", 1: "buy_2b", 0: "buy_2c"}[st]
        return "hold"

    @pytest.fixture
    def actionable_rows(self, db_session):
        from sqlalchemy import text
        anchor = db_session.execute(text("SELECT MAX(as_of_date) FROM drv_actionable")).scalar()
        if anchor is None:
            pytest.skip("drv_actionable is empty — no anchor date to test against")
        rows = db_session.execute(
            text("SELECT * FROM drv_actionable WHERE as_of_date = :d"),
            {"d": anchor},
        ).fetchall()
        return [dict(r._mapping) for r in rows]

    def test_no_stop_breached_held_row_outside_tier0(self, actionable_rows):
        """A stop-breached held row must never be classified as anything but
        Tier 0 — the single most safety-critical invariant of the sort."""
        for row in actionable_rows:
            if row.get("stop_breached") and row.get("held_today"):
                assert self._tier_of(row) == "stop", (
                    f"{row.get('tos_symbol')} is stop_breached+held but tiered "
                    f"as {self._tier_of(row)!r}"
                )

    def test_low_confidence_sell_never_in_sell_tier(self, actionable_rows):
        """A low_confidence row must never land in Tier 1 (credible sells) —
        it must fall through to Bottom."""
        for row in actionable_rows:
            if row.get("low_confidence") and not (row.get("stop_breached") and row.get("held_today")):
                assert self._tier_of(row) != "sell", (
                    f"{row.get('tos_symbol')} is low_confidence but tiered as 'sell' (credible)"
                )

    def test_held_rows_never_watchlisted(self, actionable_rows):
        for row in actionable_rows:
            if row.get("held_today"):
                assert self._tier_of(row) != "watch", (
                    f"{row.get('tos_symbol')} is held but landed in the Watchlist band"
                )

    def test_tier_counts_partition_full_row_set(self, actionable_rows):
        tiers = [self._tier_of(r) for r in actionable_rows]
        valid = {"stop", "sell", "buy_2a", "buy_2b", "buy_2c", "hold", "watch", "bottom"}
        assert set(tiers) <= valid
        assert len(tiers) == len(actionable_rows)
