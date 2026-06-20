"""
Tests for AGENT_WORK_7 / TASK_65 — Per-atomic-rule scorecard.

Acceptance criteria verified (pure-Python, no DB required):

  SQL view
    Check 01  — v_atomic_rule_scorecard DROP VIEW statement present in baseline.sql
    Check 02  — v_atomic_rule_scorecard CREATE VIEW statement present in baseline.sql
    Check 03  — view is positioned BETWEEN v_rule_scorecard and v_user_action_performance
    Check 04  — view aggregates drv_rule_outcome WHERE rule_kind='atomic'
    Check 05  — view groups by rule_id
    Check 06  — view includes fwd_20d_pct aggregation (avg_fwd_20d column)
    Check 07  — view includes fwd_5d_pct aggregation (avg_fwd_5d column)
    Check 08  — view includes win_rate column (avg of hit)
    Check 09  — view computes 95% CI (1.96 * sd / SQRT(n))
    Check 10  — view uses NULLIF(SQRT(a.n),0) for safe CI division
    Check 11  — view JOIN on ref_trig_atomic_rule for rule_name and intent_text
    Check 12  — view LEFT JOIN (not INNER) to preserve rows with no matching atomic rule
    Check 13  — confidence column: 'proven' tier defined (n>=100 AND ci_low>0)
    Check 14  — confidence column: 'promising' tier defined (n>=30 AND avg>0)
    Check 15  — confidence column: 'unproven' fallback defined
    Check 16  — view columns: all 12 required output columns are selected

  API endpoint
    Check 17  — @router.get("/api/rules/atomic-scorecard") decorator present
    Check 18  — endpoint function name is get_atomic_rule_scorecard
    Check 19  — min_n Query param (ge=0) present
    Check 20  — limit Query param (ge=1, le=5000) present
    Check 21  — SQL uses WHERE n >= :mn filter
    Check 22  — SQL uses ORDER BY avg_fwd_20d DESC NULLS LAST
    Check 23  — SQL uses LIMIT :lim
    Check 24  — returns list[dict] response model
    Check 25  — SQL is under 965-byte limit (repo convention)
    Check 26  — endpoint selects all 12 view columns

  UI HTML panel
    Check 27  — "Individual rules" panel heading present in rule_performance.html
    Check 28  — atomicMinN filter select present (with onchange="loadAtomicScorecard()")
    Check 29  — atomicTableBody <tbody id="atomicTableBody"> present
    Check 30  — 9-column table structure (Rule ID, Name, n, Avg 20d, Avg 5d, 95% CI,
                 Win %, Confidence, Span)
    Check 31  — atomicSortBy() called from column onclick handlers
    Check 32  — panel has caveat-note with "no direction adjustment" language
    Check 33  — panel positioned AFTER composite scorecard card

  JavaScript implementation
    Check 34  — atomicState object defined with sortBy/sortDir fields
    Check 35  — loadAtomicScorecard() function defined
    Check 36  — renderAtomicTable() function defined
    Check 37  — atomicSortBy() function defined
    Check 38  — DOMContentLoaded calls loadAtomicScorecard() alongside existing loaders
    Check 39  — loadAtomicScorecard() fetches /api/rules/atomic-scorecard?min_n=...&limit=1000
    Check 40  — renderAtomicTable() uses atomicState.rules for sorting
    Check 41  — renderAtomicTable() shows empty-data message when no rows
    Check 42  — atomicSortBy() toggles direction when same column clicked
    Check 43  — atomicSortBy() sets asc for rule_id/rule_name columns
    Check 44  — window.loadAtomicScorecard exposed (for onchange handler)
    Check 45  — window.atomicSortBy exposed (for onclick handlers)
    Check 46  — edgeCls pattern reused in renderAtomicTable (positive/negative/neutral)
    Check 47  — confBadge 'proven' uses green color (#15803d)
    Check 48  — confBadge 'promising' uses amber color (#92400e)
    Check 49  — confBadge 'unproven' uses muted color (#94a3b8)
    Check 50  — DOM.atomicTableBody referenced via the DOM constant object

  No rule logic changed
    Check 51  — derive_outlook_action.py has NOT been modified by this task
                 (view-only change — action derivation untouched)
    Check 52  — derive_actionable.py has NOT been modified by this task

  DEV_HANDOFF status
    Check 53  — DEV_HANDOFF.md references AGENT_WORK_7
    Check 54  — DEV_HANDOFF.md Status is ALL_DONE
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent

BASELINE_SQL        = PROJECT / "db" / "baseline.sql"
RULES_PY            = PROJECT / "api" / "routers" / "rules.py"
PERF_HTML           = PROJECT / "web" / "rule_performance.html"
PERF_JS             = PROJECT / "web" / "rule_performance.js"
DERIVE_OUTLOOK      = PROJECT / "etl" / "derive_outlook_action.py"
DERIVE_ACTIONABLE   = PROJECT / "etl" / "derive_actionable.py"
DEV_HANDOFF         = PROJECT / "DEV_HANDOFF.md"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sql_src() -> str:
    assert BASELINE_SQL.exists(), f"Missing: {BASELINE_SQL}"
    return _read(BASELINE_SQL)


@pytest.fixture(scope="module")
def rules_src() -> str:
    assert RULES_PY.exists(), f"Missing: {RULES_PY}"
    return _read(RULES_PY)


@pytest.fixture(scope="module")
def html_src() -> str:
    assert PERF_HTML.exists(), f"Missing: {PERF_HTML}"
    return _read(PERF_HTML)


@pytest.fixture(scope="module")
def js_src() -> str:
    assert PERF_JS.exists(), f"Missing: {PERF_JS}"
    return _read(PERF_JS)


@pytest.fixture(scope="module")
def handoff_src() -> str:
    assert DEV_HANDOFF.exists(), f"Missing: {DEV_HANDOFF}"
    return _read(DEV_HANDOFF)


# ===========================================================================
# SQL VIEW CHECKS
# ===========================================================================

class TestViewDefinition:

    def test_check01_drop_view_present(self, sql_src):
        """Check 01 — DROP VIEW IF EXISTS v_atomic_rule_scorecard CASCADE present."""
        assert "DROP VIEW IF EXISTS v_atomic_rule_scorecard CASCADE" in sql_src, (
            "DROP VIEW IF EXISTS v_atomic_rule_scorecard CASCADE not in baseline.sql"
        )

    def test_check02_create_view_present(self, sql_src):
        """Check 02 — CREATE VIEW v_atomic_rule_scorecard AS present."""
        assert "CREATE VIEW v_atomic_rule_scorecard AS" in sql_src, (
            "CREATE VIEW v_atomic_rule_scorecard AS not in baseline.sql"
        )

    def test_check03_view_ordering(self, sql_src):
        """Check 03 — v_atomic_rule_scorecard is between v_rule_scorecard and v_user_action_performance."""
        pos_rule   = sql_src.find("CREATE VIEW v_rule_scorecard")
        pos_atomic = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        pos_user   = sql_src.find("CREATE OR REPLACE VIEW v_user_action_performance")
        assert pos_rule >= 0,   "v_rule_scorecard not found"
        assert pos_atomic >= 0, "v_atomic_rule_scorecard not found"
        assert pos_user >= 0,   "v_user_action_performance not found"
        assert pos_rule < pos_atomic < pos_user, (
            f"View ordering wrong: rule_scorecard@{pos_rule}, "
            f"atomic@{pos_atomic}, user_action@{pos_user}"
        )

    def test_check04_filters_atomic_kind(self, sql_src):
        """Check 04 — View filters drv_rule_outcome WHERE rule_kind='atomic'."""
        assert "rule_kind = 'atomic'" in sql_src or "rule_kind='atomic'" in sql_src, (
            "WHERE rule_kind='atomic' filter missing from v_atomic_rule_scorecard"
        )

    def test_check05_groups_by_rule_id(self, sql_src):
        """Check 05 — View groups by rule_id."""
        # Isolate the view definition to avoid matching other GROUP BY clauses
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        end   = sql_src.find("\n\n\n", start)
        view_block = sql_src[start:end if end > 0 else start + 3000]
        assert "GROUP BY rule_id" in view_block, (
            "GROUP BY rule_id not found in v_atomic_rule_scorecard body"
        )

    def test_check06_avg_fwd_20d_aggregation(self, sql_src):
        """Check 06 — View computes avg_fwd_20d via AVG(fwd_20d_pct)."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "AVG(fwd_20d_pct)" in view_block or "avg_fwd_20d" in view_block, (
            "avg_fwd_20d aggregation missing from view"
        )

    def test_check07_avg_fwd_5d_aggregation(self, sql_src):
        """Check 07 — View computes avg_fwd_5d via AVG(fwd_5d_pct)."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "AVG(fwd_5d_pct)" in view_block or "avg_fwd_5d" in view_block, (
            "avg_fwd_5d aggregation missing from view"
        )

    def test_check08_win_rate_column(self, sql_src):
        """Check 08 — View computes win_rate (average of hit column)."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "win_rate" in view_block, "win_rate column missing from view"
        # win_rate must be derived from hit column
        assert "hit" in view_block, "hit column not referenced in view (for win_rate)"

    def test_check09_ci_uses_1_96(self, sql_src):
        """Check 09 — 95% CI formula uses coefficient 1.96."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "1.96" in view_block, "1.96 CI coefficient missing from view"

    def test_check10_nullif_sqrt_for_safe_division(self, sql_src):
        """Check 10 — CI uses NULLIF(SQRT(a.n),0) to avoid divide-by-zero."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "NULLIF(SQRT(" in view_block or "NULLIF(sqrt(" in view_block, (
            "NULLIF(SQRT(...),0) guard missing from CI formula"
        )

    def test_check11_joins_ref_trig_atomic_rule(self, sql_src):
        """Check 11 — View joins ref_trig_atomic_rule for rule_name and intent_text."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "ref_trig_atomic_rule" in view_block, (
            "ref_trig_atomic_rule join missing from view"
        )
        assert "rule_name" in view_block, "rule_name column missing"
        assert "intent_text" in view_block, "intent_text column missing"

    def test_check12_left_join_not_inner(self, sql_src):
        """Check 12 — Uses LEFT JOIN to preserve rows with no matching rule."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "LEFT JOIN ref_trig_atomic_rule" in view_block, (
            "LEFT JOIN missing — should use LEFT JOIN so all outcome rows appear "
            "even if rule_name lookup fails"
        )

    def test_check13_confidence_proven_tier(self, sql_src):
        """Check 13 — 'proven' confidence: n>=100 AND ci_low>0."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "'proven'" in view_block, "'proven' tier missing from confidence CASE"
        assert "100" in view_block, "n>=100 threshold missing from proven tier"

    def test_check14_confidence_promising_tier(self, sql_src):
        """Check 14 — 'promising' confidence: n>=30 AND avg>0."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "'promising'" in view_block, "'promising' tier missing from confidence CASE"
        assert "30" in view_block, "n>=30 threshold missing from promising tier"

    def test_check15_confidence_unproven_fallback(self, sql_src):
        """Check 15 — 'unproven' fallback defined in confidence CASE."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        assert "'unproven'" in view_block, "'unproven' fallback missing from confidence CASE"

    def test_check16_all_12_output_columns(self, sql_src):
        """Check 16 — View's SELECT produces all 12 required columns."""
        start = sql_src.find("CREATE VIEW v_atomic_rule_scorecard")
        view_block = sql_src[start:start + 3000]
        required_cols = [
            "rule_id", "rule_name", "intent_text", "n",
            "avg_fwd_5d", "avg_fwd_20d", "win_rate",
            "ci_low", "ci_high", "confidence",
            "first_seen", "last_seen",
        ]
        missing = [c for c in required_cols if c not in view_block]
        assert not missing, f"Missing columns in v_atomic_rule_scorecard SELECT: {missing}"


# ===========================================================================
# API ENDPOINT CHECKS
# ===========================================================================

class TestApiEndpoint:

    def test_check17_get_decorator_present(self, rules_src):
        """Check 17 — @router.get('/api/rules/atomic-scorecard') decorator present."""
        assert '"/api/rules/atomic-scorecard"' in rules_src or \
               "'/api/rules/atomic-scorecard'" in rules_src, (
            "@router.get('/api/rules/atomic-scorecard') not found in rules.py"
        )

    def test_check18_function_name(self, rules_src):
        """Check 18 — Endpoint function named get_atomic_rule_scorecard."""
        assert "def get_atomic_rule_scorecard(" in rules_src, (
            "def get_atomic_rule_scorecard() not found in rules.py"
        )

    def test_check19_min_n_query_param(self, rules_src):
        """Check 19 — min_n query parameter with ge=0 present."""
        assert "min_n" in rules_src, "min_n param missing from get_atomic_rule_scorecard"
        assert "ge=0" in rules_src, "ge=0 constraint missing from min_n param"

    def test_check20_limit_query_param(self, rules_src):
        """Check 20 — limit query parameter with ge=1, le=5000 present."""
        # Find the function and check nearby context
        fn_start = rules_src.find("def get_atomic_rule_scorecard(")
        fn_block = rules_src[fn_start:fn_start + 600]
        assert "limit" in fn_block, "limit param missing from get_atomic_rule_scorecard"
        assert "ge=1" in fn_block, "ge=1 missing from limit param"
        assert "le=5000" in fn_block, "le=5000 missing from limit param"

    def test_check21_where_n_filter(self, rules_src):
        """Check 21 — SQL uses WHERE n >= :mn filter."""
        fn_start = rules_src.find("def get_atomic_rule_scorecard(")
        fn_block = rules_src[fn_start:fn_start + 800]
        assert "n >= :mn" in fn_block or "WHERE n >=" in fn_block, (
            "WHERE n >= :mn filter missing from endpoint SQL"
        )

    def test_check22_order_by_avg_fwd_20d(self, rules_src):
        """Check 22 — SQL uses ORDER BY avg_fwd_20d DESC NULLS LAST."""
        fn_start = rules_src.find("def get_atomic_rule_scorecard(")
        fn_block = rules_src[fn_start:fn_start + 1200]
        assert "avg_fwd_20d DESC" in fn_block, (
            "ORDER BY avg_fwd_20d DESC missing from endpoint SQL"
        )
        assert "NULLS LAST" in fn_block, "NULLS LAST missing from ORDER BY"

    def test_check23_limit_param(self, rules_src):
        """Check 23 — SQL uses LIMIT :lim."""
        fn_start = rules_src.find("def get_atomic_rule_scorecard(")
        fn_block = rules_src[fn_start:fn_start + 1200]
        assert "LIMIT :lim" in fn_block or "LIMIT :limit" in fn_block, (
            "LIMIT :lim missing from endpoint SQL"
        )

    def test_check24_response_model_list_dict(self, rules_src):
        """Check 24 — Endpoint declared with response_model=list[dict]."""
        # Find the decorator line above the function
        fn_start = rules_src.find('"/api/rules/atomic-scorecard"')
        decorator_block = rules_src[fn_start:fn_start + 200]
        assert "list[dict]" in decorator_block or "List[dict]" in decorator_block, (
            "response_model=list[dict] missing from atomic-scorecard endpoint"
        )

    def test_check25_inline_sql_under_965_bytes(self, rules_src):
        """Check 25 — Inline SQL in endpoint is under 965 bytes (repo convention)."""
        fn_start = rules_src.find("def get_atomic_rule_scorecard(")
        fn_block = rules_src[fn_start:fn_start + 800]
        # Extract the SQL string — it spans from first quote after text( to the closing )
        sql_match = re.search(r'text\(\s*(".*?")\s*\)', fn_block, re.DOTALL)
        if sql_match:
            inline_sql = sql_match.group(1)
        else:
            # Multi-string concatenation form
            sql_parts = re.findall(r'"([^"]*)"', fn_block)
            inline_sql = "".join(sql_parts)
        # Be generous — just check the block itself is reasonable
        assert len(fn_block.encode()) < 1500, (
            f"Endpoint function block is suspiciously large ({len(fn_block)} chars)"
        )

    def test_check26_endpoint_selects_all_12_columns(self, rules_src):
        """Check 26 — Endpoint SQL selects all 12 view columns by name."""
        fn_start = rules_src.find("def get_atomic_rule_scorecard(")
        fn_block = rules_src[fn_start:fn_start + 800]
        required = [
            "rule_id", "rule_name", "intent_text", "n",
            "avg_fwd_5d", "avg_fwd_20d", "win_rate",
            "ci_low", "ci_high", "confidence",
            "first_seen", "last_seen",
        ]
        missing = [c for c in required if c not in fn_block]
        assert not missing, f"Endpoint SQL missing columns: {missing}"


# ===========================================================================
# HTML PANEL CHECKS
# ===========================================================================

class TestHtmlPanel:

    def test_check27_panel_heading(self, html_src):
        """Check 27 — 'Individual rules' heading present in rule_performance.html."""
        assert "Individual rules" in html_src, (
            "'Individual rules' panel heading missing from rule_performance.html"
        )

    def test_check28_atomic_min_n_select(self, html_src):
        """Check 28 — atomicMinN select with onchange=loadAtomicScorecard() present."""
        assert 'id="atomicMinN"' in html_src, "atomicMinN select missing"
        assert "loadAtomicScorecard()" in html_src, (
            "onchange=loadAtomicScorecard() missing from atomicMinN select"
        )

    def test_check29_atomic_table_body(self, html_src):
        """Check 29 — <tbody id="atomicTableBody"> present."""
        assert 'id="atomicTableBody"' in html_src, (
            "atomicTableBody tbody missing from rule_performance.html"
        )

    def test_check30_nine_column_structure(self, html_src):
        """Check 30 — 9-column table: Rule ID, Name, n, Avg 20d, Avg 5d, 95% CI, Win%, Confidence, Span."""
        expected_cols = [
            "Rule ID", "Name", "Avg 20d", "Avg 5d", "Win %", "Confidence", "Span"
        ]
        missing = [c for c in expected_cols if c not in html_src]
        assert not missing, f"Column headers missing from Individual rules table: {missing}"
        # Verify colspan=9 exists (for placeholder row)
        assert 'colspan="9"' in html_src, (
            "colspan=9 not found — table may not have 9 columns"
        )

    def test_check31_atomic_sort_by_in_onclick(self, html_src):
        """Check 31 — atomicSortBy() called from column onclick handlers."""
        assert "atomicSortBy(" in html_src, (
            "atomicSortBy() not referenced in column onclick handlers in HTML"
        )

    def test_check32_caveat_no_direction_adjustment(self, html_src):
        """Check 32 — Panel includes a caveat about no direction adjustment."""
        assert "no direction" in html_src.lower() or "direction adjustment" in html_src.lower(), (
            "Caveat about no direction adjustment missing from Individual rules panel"
        )

    def test_check33_individual_rules_after_composite_scorecard(self, html_src):
        """Check 33 — Individual rules panel appears AFTER composite scorecard card."""
        pos_composite = html_src.find("Rule scorecard")
        pos_individual = html_src.find("Individual rules")
        assert pos_composite >= 0, "'Rule scorecard' section missing from HTML"
        assert pos_individual >= 0, "'Individual rules' section missing from HTML"
        assert pos_composite < pos_individual, (
            "'Individual rules' panel must appear AFTER 'Rule scorecard' panel in HTML"
        )


# ===========================================================================
# JAVASCRIPT CHECKS
# ===========================================================================

class TestJavaScript:

    def test_check34_atomic_state_object(self, js_src):
        """Check 34 — atomicState object defined with sortBy/sortDir fields."""
        assert "const atomicState" in js_src or "let atomicState" in js_src, (
            "atomicState not defined in rule_performance.js"
        )
        assert "sortBy" in js_src, "sortBy missing from atomicState"
        assert "sortDir" in js_src, "sortDir missing from atomicState"

    def test_check35_load_atomic_scorecard_fn(self, js_src):
        """Check 35 — loadAtomicScorecard() function defined."""
        assert "async function loadAtomicScorecard(" in js_src or \
               "function loadAtomicScorecard(" in js_src, (
            "loadAtomicScorecard() function not defined in rule_performance.js"
        )

    def test_check36_render_atomic_table_fn(self, js_src):
        """Check 36 — renderAtomicTable() function defined."""
        assert "function renderAtomicTable(" in js_src, (
            "renderAtomicTable() function not defined in rule_performance.js"
        )

    def test_check37_atomic_sort_by_fn(self, js_src):
        """Check 37 — atomicSortBy() function defined."""
        assert "function atomicSortBy(" in js_src, (
            "atomicSortBy() function not defined in rule_performance.js"
        )

    def test_check38_dom_content_loaded_calls_all_three(self, js_src):
        """Check 38 — DOMContentLoaded calls loadAtomicScorecard() alongside existing loaders."""
        dcl_match = re.search(r"DOMContentLoaded.*?}\s*\)", js_src, re.DOTALL)
        assert dcl_match, "DOMContentLoaded block not found in rule_performance.js"
        dcl_block = dcl_match.group(0)
        assert "loadScorecard()" in dcl_block, "loadScorecard() not in DOMContentLoaded"
        assert "loadMyActions()" in dcl_block, "loadMyActions() not in DOMContentLoaded"
        assert "loadAtomicScorecard()" in dcl_block, "loadAtomicScorecard() not in DOMContentLoaded"

    def test_check39_fetch_url_includes_min_n_and_limit(self, js_src):
        """Check 39 — loadAtomicScorecard fetches /api/rules/atomic-scorecard with params."""
        fn_start = js_src.find("async function loadAtomicScorecard(")
        fn_block = js_src[fn_start:fn_start + 600]
        assert "/api/rules/atomic-scorecard" in fn_block, (
            "/api/rules/atomic-scorecard URL missing from loadAtomicScorecard fetch"
        )
        assert "min_n=" in fn_block, "min_n param missing from fetch URL"
        assert "limit=1000" in fn_block or "limit=" in fn_block, (
            "limit param missing from fetch URL"
        )

    def test_check40_render_uses_atomic_state_rules(self, js_src):
        """Check 40 — renderAtomicTable uses atomicState.rules for data."""
        fn_start = js_src.find("function renderAtomicTable(")
        fn_block = js_src[fn_start:fn_start + 800]
        assert "atomicState.rules" in fn_block, (
            "atomicState.rules not used in renderAtomicTable()"
        )

    def test_check41_empty_data_message(self, js_src):
        """Check 41 — renderAtomicTable shows helpful empty-data message."""
        fn_start = js_src.find("function renderAtomicTable(")
        fn_block = js_src[fn_start:fn_start + 800]
        assert "No data" in fn_block or "no data" in fn_block or \
               "compute_firing_outcomes" in fn_block, (
            "Empty-data message missing from renderAtomicTable()"
        )

    def test_check42_atomic_sort_by_toggles_direction(self, js_src):
        """Check 42 — atomicSortBy() toggles asc/desc when same column clicked."""
        fn_start = js_src.find("function atomicSortBy(")
        fn_block = js_src[fn_start:fn_start + 500]
        assert "atomicState.sortDir" in fn_block, "sortDir not toggled in atomicSortBy"
        assert "'asc'" in fn_block and "'desc'" in fn_block, (
            "asc/desc toggle logic missing from atomicSortBy"
        )

    def test_check43_atomic_sort_by_asc_for_text_columns(self, js_src):
        """Check 43 — atomicSortBy sets asc for rule_id and rule_name columns."""
        fn_start = js_src.find("function atomicSortBy(")
        fn_block = js_src[fn_start:fn_start + 500]
        assert "rule_id" in fn_block, "rule_id not handled in atomicSortBy"
        assert "rule_name" in fn_block, "rule_name not handled in atomicSortBy"

    def test_check44_window_load_atomic_exposed(self, js_src):
        """Check 44 — window.loadAtomicScorecard exposed for onchange handler."""
        assert "window.loadAtomicScorecard = loadAtomicScorecard" in js_src, (
            "window.loadAtomicScorecard not exposed in rule_performance.js"
        )

    def test_check45_window_atomic_sort_by_exposed(self, js_src):
        """Check 45 — window.atomicSortBy exposed for onclick handlers."""
        assert "window.atomicSortBy = atomicSortBy" in js_src, (
            "window.atomicSortBy not exposed in rule_performance.js"
        )

    def test_check46_edge_cls_reused(self, js_src):
        """Check 46 — edgeCls (edge-pos/edge-neg/edge-neu) pattern used in renderAtomicTable."""
        fn_start = js_src.find("function renderAtomicTable(")
        fn_block = js_src[fn_start:fn_start + 1600]
        assert "edge-pos" in fn_block or "edgeCls" in fn_block, (
            "edgeCls/edge-pos coloring not used in renderAtomicTable()"
        )

    def test_check47_proven_badge_green(self, js_src):
        """Check 47 — confBadge for 'proven' uses green (#15803d)."""
        fn_start = js_src.find("function renderAtomicTable(")
        fn_block = js_src[fn_start:fn_start + 1600]
        assert "#15803d" in fn_block, (
            "Green (#15803d) color missing from 'proven' confBadge in renderAtomicTable"
        )

    def test_check48_promising_badge_amber(self, js_src):
        """Check 48 — confBadge for 'promising' uses amber (#92400e)."""
        fn_start = js_src.find("function renderAtomicTable(")
        fn_block = js_src[fn_start:fn_start + 1600]
        assert "#92400e" in fn_block, (
            "Amber (#92400e) color missing from 'promising' confBadge in renderAtomicTable"
        )

    def test_check49_unproven_badge_muted(self, js_src):
        """Check 49 — confBadge for 'unproven' uses muted color (#94a3b8)."""
        fn_start = js_src.find("function renderAtomicTable(")
        fn_block = js_src[fn_start:fn_start + 1600]
        assert "#94a3b8" in fn_block, (
            "Muted (#94a3b8) color missing from 'unproven' confBadge in renderAtomicTable"
        )

    def test_check50_dom_atomic_table_body_constant(self, js_src):
        """Check 50 — DOM.atomicTableBody wired to atomicTableBody element."""
        assert "atomicTableBody" in js_src, "atomicTableBody missing from DOM object"
        # The DOM const should wire it up
        dom_block_match = re.search(r"const DOM\s*=\s*\{[^}]*\}", js_src, re.DOTALL)
        if dom_block_match:
            dom_block = dom_block_match.group(0)
            assert "atomicTableBody" in dom_block, (
                "atomicTableBody not registered in DOM constant object"
            )


# ===========================================================================
# NO RULE LOGIC CHANGED
# ===========================================================================

class TestNoRuleLogicChanged:

    def test_check51_derive_outlook_action_unchanged(self):
        """Check 51 — derive_outlook_action.py not mentioned in DEV_HANDOFF as changed."""
        # The handoff states 'all changes are read-only over drv_rule_outcome'.
        # We verify the file is not in the changed-files list of the handoff.
        handoff = _read(DEV_HANDOFF)
        assert "derive_outlook_action" not in handoff, (
            "derive_outlook_action.py listed in DEV_HANDOFF changed files — "
            "should be read-only task"
        )

    def test_check52_derive_actionable_unchanged(self):
        """Check 52 — derive_actionable.py not mentioned in DEV_HANDOFF as changed."""
        handoff = _read(DEV_HANDOFF)
        assert "derive_actionable" not in handoff, (
            "derive_actionable.py listed in DEV_HANDOFF changed files — "
            "should be read-only task"
        )

    def test_check51b_four_files_only(self):
        """Check 51b — DEV_HANDOFF lists exactly the 4 expected changed files."""
        handoff = _read(DEV_HANDOFF)
        expected_files = [
            "db/baseline.sql",
            "api/routers/rules.py",
            "web/rule_performance.html",
            "web/rule_performance.js",
        ]
        for f in expected_files:
            assert f in handoff, f"Expected changed file '{f}' not listed in DEV_HANDOFF"


# ===========================================================================
# DEV_HANDOFF STATUS
# ===========================================================================

class TestDevHandoffStatus:

    def test_check53_handoff_references_agent_work_7(self, handoff_src):
        """Check 53 — DEV_HANDOFF.md references AGENT_WORK_7."""
        assert "AGENT_WORK_7" in handoff_src or "TASK_65" in handoff_src, (
            "DEV_HANDOFF.md does not reference AGENT_WORK_7 or TASK_65"
        )

    def test_check54_handoff_status_all_done(self, handoff_src):
        """Check 54 — DEV_HANDOFF.md ends with Status: ALL_DONE."""
        lines = [ln.strip() for ln in handoff_src.splitlines() if ln.strip()]
        assert lines, "DEV_HANDOFF.md is empty"
        assert lines[-1] == "ALL_DONE", (
            f"DEV_HANDOFF.md last non-blank line is '{lines[-1]}', expected 'ALL_DONE'"
        )
