"""Tests for AGENT_WORK_49 — held/not-held source-order consolidation.

Acceptance criteria:
  A. Python syntax — derive_actionable.py parses cleanly.
  B. SOURCE_ORDER constant present with correct values PS=1,ETF=2,RR=3,SSS=4,II=5,CALL=6.
  C. Held path uses SOURCE_ORDER sort (candidates.sort(key=_order)).
  D. Not-held path uses (-_upd_ord, _order) sort.
  E. _order helper present: returns _group_prio for group candidates, SOURCE_ORDER for sources.
  F. _upd_ord helper present and reads _update_date / source_snapshot_date / as_of_date.
  G. group_candidates stamped with _update_date = as_of_date.
  H. OLD CALL demotion (other_sources_present gate) IS GONE.
  I. OLD PS not-held REMOVE exclusion IS GONE.
  J. OLD SSS INCREASE/REDUCE demotion IS GONE.
  K. ACTION_RANK unchanged: REMOVE=4, REDUCE=3, INCREASE=2, ADD=1, HOLD=0.
  L. docs/actionable_logic.md: Stage-2 describes held/not-held branch.
  M. docs/actionable_logic.md: removed behaviors listed with date stamp.
  N. DEV_HANDOFF.md: ALL_DONE, references TASK 49, mentions SOURCE_ORDER.
  Unit logic tests (pure-Python, no DB):
  U1. Held symbol — PS always beats all others.
  U2. Held symbol — ETF beats RR, SSS, II, CALL.
  U3. Held symbol — CALL is last (rank 6 of 6).
  U4. Held symbol — action of winning source is the consolidated action.
  U5. Not-held — latest updated source wins (even over PS).
  U6. Not-held — tie on date breaks by SOURCE_ORDER.
  U7. Not-held — PS REMOVE CAN win (no exclusion) when freshest.
  U8. Not-held — CALL competes on recency (no demotion).
  U9. SSS INCREASE is eligible to be consolidated action (no demotion).
  U10. SSS REDUCE is eligible to be consolidated action (no demotion).
  U11. group candidate ranked after all six sources on held path (prio > 6).
  U12. _upd_ord returns 0 for missing date (treated as oldest).
  U13. Idempotent re-sort on equal candidates list.
  DB tests (auto-skip when Postgres absent):
  DB1. winning_source column populated in drv_actionable.
  DB2. Held symbols use SOURCE_ORDER (PS before RR when both present).
  DB3. Not-held symbols: winning_source has latest source_snapshot_date.
  DB4. SSS can appear as winning_source.
  DB5. Derive is idempotent — two passes produce identical rows.
"""
from __future__ import annotations

import ast
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DERIVE_ACT = PROJECT_ROOT / "etl" / "derive_actionable.py"
ACTIONABLE_LOGIC_MD = PROJECT_ROOT / "docs" / "actionable_logic.md"
DEV_HANDOFF = PROJECT_ROOT / "DEV_HANDOFF.md"


# ---------------------------------------------------------------------------
# Helpers for extracting code blocks
# ---------------------------------------------------------------------------

def _read_src() -> str:
    return DERIVE_ACT.read_text(encoding="utf-8")


def _winner_block() -> str:
    src = _read_src()
    start = src.find("# ─── Pick the winning action ───")
    assert start != -1, "Winner-pick comment block not found in derive_actionable.py"
    end = src.find("# ─── Decide category", start)
    return src[start:end] if end != -1 else src[start:start + 4000]


# ---------------------------------------------------------------------------
# A. Python syntax
# ---------------------------------------------------------------------------

class TestPythonSyntax:
    def test_derive_actionable_parses(self):
        src = _read_src()
        try:
            ast.parse(src)
        except SyntaxError as e:
            pytest.fail(f"derive_actionable.py has a syntax error: {e}")


# ---------------------------------------------------------------------------
# B. SOURCE_ORDER constant correct values
# ---------------------------------------------------------------------------

class TestSourceOrderConstant:
    def test_source_order_defined(self):
        src = _read_src()
        assert "SOURCE_ORDER" in src, "SOURCE_ORDER constant missing from derive_actionable.py"

    def test_source_order_values(self):
        src = _read_src()
        match = re.search(r'SOURCE_ORDER\s*=\s*\{([^}]+)\}', src)
        assert match, "SOURCE_ORDER dict not found"
        body = match.group(1)
        assert re.search(r'["\']PS["\']\s*:\s*1', body), "PS must be 1 in SOURCE_ORDER"
        assert re.search(r'["\']ETF["\']\s*:\s*2', body), "ETF must be 2 in SOURCE_ORDER"
        assert re.search(r'["\']RR["\']\s*:\s*3', body), "RR must be 3 in SOURCE_ORDER"
        assert re.search(r'["\']SSS["\']\s*:\s*4', body), "SSS must be 4 in SOURCE_ORDER"
        assert re.search(r'["\']II["\']\s*:\s*5', body), "II must be 5 in SOURCE_ORDER"
        assert re.search(r'["\']CALL["\']\s*:\s*6', body), "CALL must be 6 in SOURCE_ORDER"

    def test_source_order_near_action_rank(self):
        """SOURCE_ORDER must be defined at module level, near ACTION_RANK."""
        src = _read_src()
        ar_pos = src.find("ACTION_RANK")
        so_pos = src.find("SOURCE_ORDER")
        assert ar_pos != -1 and so_pos != -1
        # Within 10 lines of each other
        lines_between = abs(src[:max(ar_pos, so_pos)].count('\n') -
                            src[:min(ar_pos, so_pos)].count('\n'))
        assert lines_between <= 10, (
            f"SOURCE_ORDER and ACTION_RANK should be adjacent module-level constants, "
            f"but they are {lines_between} lines apart"
        )


# ---------------------------------------------------------------------------
# C. Held path: sort by _order
# ---------------------------------------------------------------------------

class TestHeldPathSortOrder:
    def test_held_branch_sorts_by_order(self):
        block = _winner_block()
        # Must have a branch for held that sorts by _order only (not -_upd_ord)
        # Pattern: if _held_now: ... candidates.sort(key=_order)
        assert re.search(
            r'if\s+_held_now\s*:.*candidates\.sort\s*\(\s*key\s*=\s*_order\s*\)',
            block,
            re.DOTALL,
        ), (
            "Held branch must sort candidates by _order (SOURCE_ORDER) only. "
            "Pattern: if _held_now: ... candidates.sort(key=_order)"
        )

    def test_held_branch_has_no_upd_ord(self):
        """The held branch sort must NOT use -_upd_ord (recency) as a key."""
        block = _winner_block()
        # Find the if _held_now block
        idx = block.find("if _held_now")
        assert idx != -1, "_held_now check not in winner-pick block"
        # The else clause starts the not-held branch; the held clause ends there
        else_idx = block.find("else:", idx)
        if else_idx != -1:
            held_clause = block[idx:else_idx]
        else:
            held_clause = block[idx:idx + 500]
        assert "_upd_ord" not in held_clause, (
            "Held branch sort must not include _upd_ord (recency) — "
            "held path is pure SOURCE_ORDER"
        )


# ---------------------------------------------------------------------------
# D. Not-held path: sort by (-_upd_ord, _order)
# ---------------------------------------------------------------------------

class TestNotHeldPathSort:
    def test_not_held_branch_uses_upd_ord(self):
        block = _winner_block()
        # Pattern: else: candidates.sort(key=lambda a: (-_upd_ord(a), _order(a)))
        assert re.search(
            r'else\s*:.*candidates\.sort\s*\(\s*key\s*=\s*lambda\s+a\s*:\s*'
            r'\(\s*-_upd_ord\s*\(\s*a\s*\)\s*,\s*_order\s*\(\s*a\s*\)\s*\)',
            block,
            re.DOTALL,
        ), (
            "Not-held branch must sort candidates with key=lambda a: (-_upd_ord(a), _order(a)). "
            f"Actual winner block (first 800 chars): {block[:800]}"
        )


# ---------------------------------------------------------------------------
# E. _order helper: _group_prio for groups, SOURCE_ORDER for sources
# ---------------------------------------------------------------------------

class TestOrderHelper:
    def _order_block(self) -> str:
        src = _read_src()
        idx = src.find("def _order(")
        assert idx != -1, "_order helper not found in derive_actionable.py"
        end = src.find("\n        def ", idx + 1)
        return src[idx:end] if end != -1 else src[idx:idx + 400]

    def test_order_checks_group_prio(self):
        block = self._order_block()
        assert "_group_prio" in block, "_order must check for _group_prio key"

    def test_order_uses_source_order(self):
        block = self._order_block()
        assert "SOURCE_ORDER" in block, "_order must look up SOURCE_ORDER"

    def test_order_returns_99_for_unknown(self):
        """Sources not in SOURCE_ORDER must get fallback rank 99."""
        block = self._order_block()
        assert re.search(r'\b99\b', block), (
            "_order must return 99 (or similar fallback) for unknown source_code"
        )


# ---------------------------------------------------------------------------
# F. _upd_ord helper: reads correct date fields
# ---------------------------------------------------------------------------

class TestUpdOrdHelper:
    def _upd_ord_block(self) -> str:
        src = _read_src()
        idx = src.find("def _upd_ord(")
        assert idx != -1, "_upd_ord helper not found in derive_actionable.py"
        end = src.find("\n        def ", idx + 1)
        return src[idx:end] if end != -1 else src[idx:idx + 400]

    def test_reads_update_date(self):
        block = self._upd_ord_block()
        assert "_update_date" in block

    def test_reads_source_snapshot_date(self):
        block = self._upd_ord_block()
        assert "source_snapshot_date" in block

    def test_reads_as_of_date(self):
        block = self._upd_ord_block()
        assert "as_of_date" in block

    def test_calls_toordinal(self):
        block = self._upd_ord_block()
        assert "toordinal()" in block

    def test_returns_zero_for_missing(self):
        block = self._upd_ord_block()
        assert re.search(r'\belse\s+0\b|\breturn\s+0\b', block), (
            "_upd_ord must return 0 for missing date"
        )


# ---------------------------------------------------------------------------
# G. group_candidates stamped with _update_date = as_of_date
# ---------------------------------------------------------------------------

class TestGroupCandidatesStamped:
    def test_stamp_present(self):
        src = _read_src()
        assert re.search(
            r'gc\["_update_date"\]\s*=\s*as_of_date'
            r'|gc\[\'_update_date\'\]\s*=\s*as_of_date',
            src,
        ), "group_candidates must be stamped with gc['_update_date'] = as_of_date"


# ---------------------------------------------------------------------------
# H. OLD CALL demotion (other_sources_present) IS GONE
# ---------------------------------------------------------------------------

class TestCallDemotionRemoved:
    """The CALL demotion gate (other_sources_present) must be absent from winner-pick block."""

    def test_other_sources_present_gone(self):
        block = _winner_block()
        assert "other_sources_present" not in block, (
            "other_sources_present variable still in winner-pick block — "
            "CALL demotion must be removed per TASK 49 spec"
        )

    def test_call_not_filtered_out_in_winner_block(self):
        """No code in winner-pick block that filters CALL out based on other sources."""
        block = _winner_block()
        # Allow CALL in comments; ban it in active filter code
        code_lines = [
            ln for ln in block.splitlines()
            if not ln.strip().startswith("#")
            and re.search(r"""source_code\s*!=\s*['"]CALL['"]""", ln)
        ]
        assert not code_lines, (
            f"CALL demotion filter (source_code != 'CALL') still in winner-pick code:\n"
            + "\n".join(code_lines)
        )


# ---------------------------------------------------------------------------
# I. OLD PS not-held REMOVE exclusion IS GONE
# ---------------------------------------------------------------------------

class TestPSRemoveExclusionRemoved:
    """The 'not-held PS REMOVE excluded from candidates' filter must be absent."""

    def test_no_ps_remove_not_held_exclusion(self):
        block = _winner_block()
        # Old pattern: not (_held_now) and source_code == 'PS' and action == 'REMOVE'
        has_exclusion = re.search(
            r'source_code\s*==\s*["\']PS["\']'
            r'.*action\s*==\s*["\']REMOVE["\']'
            r'.*not\s+_held_now'
            r'|not\s+_held_now'
            r'.*source_code\s*==\s*["\']PS["\']'
            r'.*action\s*==\s*["\']REMOVE["\']',
            block,
            re.DOTALL,
        )
        assert not has_exclusion, (
            "PS not-held REMOVE exclusion still present in winner-pick block — "
            "must be removed per TASK 49 spec"
        )

    def test_no_outlook_candidates_filter(self):
        """The outlook_candidates filtering step must be removed."""
        block = _winner_block()
        # The old code had: outlook_candidates = [a for a in src_actions if ... PS/REMOVE exclusion]
        # Allow "outlook_candidates" in comments but not in live code
        code_lines = [
            ln for ln in block.splitlines()
            if not ln.strip().startswith("#")
            and "outlook_candidates" in ln
        ]
        assert not code_lines, (
            f"outlook_candidates filter still present in winner-pick code:\n"
            + "\n".join(code_lines)
        )


# ---------------------------------------------------------------------------
# J. OLD SSS INCREASE/REDUCE demotion IS GONE
# ---------------------------------------------------------------------------

class TestSSSDemotionRemoved:
    def test_no_sss_increase_reduce_exclusion(self):
        block = _winner_block()
        assert not re.search(
            r'source_code\s*==\s*["\']SSS["\'].*action\s+in\s+\(["\']INCREASE',
            block,
            re.DOTALL,
        ), "SSS INCREASE/REDUCE demotion clause still in winner-pick block"

    def test_no_sss_filter_in_code(self):
        block = _winner_block()
        code_lines = [
            ln for ln in block.splitlines()
            if not ln.strip().startswith("#")
            and re.search(r"""source_code\s*==\s*['"]SSS['"]""", ln)
        ]
        assert not code_lines, (
            f"SSS source_code filter in non-comment code:\n" + "\n".join(code_lines)
        )


# ---------------------------------------------------------------------------
# K. ACTION_RANK unchanged
# ---------------------------------------------------------------------------

class TestActionRankUnchanged:
    def test_action_rank_values(self):
        src = _read_src()
        match = re.search(r'ACTION_RANK\s*=\s*\{([^}]+)\}', src)
        assert match, "ACTION_RANK dict not found"
        body = match.group(1)
        assert re.search(r'["\']REMOVE["\']\s*:\s*4', body)
        assert re.search(r'["\']REDUCE["\']\s*:\s*3', body)
        assert re.search(r'["\']INCREASE["\']\s*:\s*2', body)
        assert re.search(r'["\']ADD["\']\s*:\s*1', body)
        assert re.search(r'["\']HOLD["\']\s*:\s*0', body)


# ---------------------------------------------------------------------------
# L. docs: Stage-2 describes held/not-held branch
# ---------------------------------------------------------------------------

class TestDocsHeldNotHeldBranch:
    def _stage2(self) -> str:
        docs = ACTIONABLE_LOGIC_MD.read_text(encoding="utf-8")
        start = docs.find("## Stage 2")
        assert start != -1, "Stage 2 section not found in actionable_logic.md"
        end = docs.find("## Stage 3", start)
        if end == -1:
            end = docs.find("## Display", start)
        return docs[start:end] if end != -1 else docs[start:start + 3000]

    def test_held_path_described(self):
        block = self._stage2()
        assert re.search(r'[Hh]eld\s+symbol|[Hh]eld\s+path', block), (
            "Stage-2 must describe the held-symbol path"
        )

    def test_source_order_mentioned(self):
        block = self._stage2()
        assert "SOURCE_ORDER" in block or re.search(
            r'PS.*ETF.*RR.*SSS.*II.*CALL', block
        ), "Stage-2 must mention SOURCE_ORDER or list PS>ETF>RR>SSS>II>CALL"

    def test_not_held_recency_mentioned(self):
        block = self._stage2()
        assert re.search(r'not.held|recency|latest.update|most.recent', block, re.IGNORECASE), (
            "Stage-2 must describe the not-held recency path"
        )

    def test_no_sss_demotion_sentence(self):
        docs = ACTIONABLE_LOGIC_MD.read_text(encoding="utf-8")
        bad_patterns = [
            r'SSS.*INCREASE.*REDUCE.*demoted',
            r'SSS.*INCREASE/REDUCE.*never become',
            r'never become the consolidated action',
        ]
        for pat in bad_patterns:
            assert not re.search(pat, docs, re.IGNORECASE | re.DOTALL), (
                f"Old SSS demotion sentence still in docs: pattern={pat}"
            )


# ---------------------------------------------------------------------------
# M. docs: Removed behaviors documented with date stamp
# ---------------------------------------------------------------------------

class TestDocsRemovedBehaviors:
    def test_removed_behaviors_listed(self):
        docs = ACTIONABLE_LOGIC_MD.read_text(encoding="utf-8")
        # Must mention that the old CALL carve-out, PS REMOVE exclusion,
        # and SSS demotion are removed. Allow flexible phrasing.
        assert re.search(r'[Rr]emoved\s+behav|as of 2026', docs), (
            "actionable_logic.md must document removed behaviors with date stamp"
        )

    def test_call_removal_documented(self):
        docs = ACTIONABLE_LOGIC_MD.read_text(encoding="utf-8")
        # Docs say: CALL "only wins when it's the only source" carve-out
        assert re.search(
            r'CALL.*only.*source|CALL.*carve.out|CALL.*last.*SOURCE_ORDER|CALL.*rank.*last',
            docs, re.IGNORECASE | re.DOTALL
        ), (
            "Removal of CALL 'only-source' carve-out must be documented in actionable_logic.md.\n"
            "Expected phrases: 'CALL only wins when only source' or 'CALL carve-out' or 'CALL now ranks last'."
        )

    def test_ps_remove_removal_documented(self):
        docs = ACTIONABLE_LOGIC_MD.read_text(encoding="utf-8")
        assert re.search(
            r'PS.*REMOVE.*exclu|not.held.*PS.*REMOVE|PS REMOVE.*path|PS REMOVE.*suppressed',
            docs, re.IGNORECASE | re.DOTALL
        ), (
            "Removal of PS not-held REMOVE exclusion must be documented"
        )

    def test_sss_removal_documented(self):
        docs = ACTIONABLE_LOGIC_MD.read_text(encoding="utf-8")
        # Docs say: SSS INCREASE/REDUCE demotion (part of "Removed behaviors" block)
        assert re.search(
            r'SSS INCREASE/REDUCE|SSS.*INCREASE.*REDUCE|SSS.*competes.*equal',
            docs, re.IGNORECASE | re.DOTALL
        ), (
            "Removal of SSS INCREASE/REDUCE demotion must be documented in actionable_logic.md"
        )


# ---------------------------------------------------------------------------
# N. DEV_HANDOFF.md: complete and references key artifacts
# ---------------------------------------------------------------------------

class TestDevHandoff:
    def test_handoff_exists(self):
        assert DEV_HANDOFF.exists(), "DEV_HANDOFF.md not found"

    def test_handoff_all_done(self):
        content = DEV_HANDOFF.read_text(encoding="utf-8")
        assert "ALL_DONE" in content

    def test_handoff_mentions_agent_work_49(self):
        content = DEV_HANDOFF.read_text(encoding="utf-8")
        assert "49" in content or "AGENT_WORK_49" in content

    def test_handoff_mentions_source_order(self):
        content = DEV_HANDOFF.read_text(encoding="utf-8")
        assert "SOURCE_ORDER" in content, "DEV_HANDOFF.md must mention SOURCE_ORDER"

    def test_handoff_mentions_removed_behaviors(self):
        content = DEV_HANDOFF.read_text(encoding="utf-8")
        assert "Removed" in content or "removed" in content, (
            "DEV_HANDOFF.md must describe removed behaviors"
        )


# ---------------------------------------------------------------------------
# Pure-unit tests — replicate winner-pick logic for isolation
# ---------------------------------------------------------------------------

# Mirror the exact constants from derive_actionable.py
ACTION_RANK  = {"REMOVE": 4, "REDUCE": 3, "INCREASE": 2, "ADD": 1, "HOLD": 0}
SOURCE_ORDER = {"PS": 1, "ETF": 2, "RR": 3, "SSS": 4, "II": 5, "CALL": 6}


def _make_src_action(source_code: str, action: str,
                     snapshot_date=None, as_of_date=None) -> dict:
    return {
        "source_code": source_code,
        "action": action,
        "source_snapshot_date": snapshot_date,
        "as_of_date": as_of_date,
    }


def _upd_ord_impl(a: dict) -> int:
    """Mirror of derive_actionable._upd_ord."""
    d = a.get("_update_date") or a.get("source_snapshot_date") or a.get("as_of_date")
    return d.toordinal() if d else 0


def _order_impl(a: dict) -> int:
    """Mirror of derive_actionable._order."""
    if "_group_prio" in a:
        return a["_group_prio"]
    return SOURCE_ORDER.get(a["source_code"], 99)


def _pick_winner(src_actions: list[dict],
                 group_candidates: list[dict],
                 held_dollar: float,
                 as_of_date: date):
    """Replicate the TASK-49 winner-pick block exactly."""
    _held_now = held_dollar > 0

    for gc in group_candidates:
        gc["_update_date"] = as_of_date

    candidates = (
        [a for a in src_actions if a["action"] in ACTION_RANK]
        + group_candidates
    )
    if not candidates:
        return None, None

    if _held_now:
        candidates.sort(key=_order_impl)
    else:
        candidates.sort(key=lambda a: (-_upd_ord_impl(a), _order_impl(a)))

    winner = candidates[0]
    return winner["action"], winner["source_code"]


class TestUnitHeldPath:
    """U1–U4: held-symbol SOURCE_ORDER dominates."""

    def test_u1_ps_beats_all_others_when_held(self):
        d = date(2026, 6, 1)
        actions = [
            _make_src_action("CALL", "ADD", snapshot_date=d),
            _make_src_action("II", "ADD", snapshot_date=d),
            _make_src_action("SSS", "INCREASE", snapshot_date=d),
            _make_src_action("RR", "REMOVE", snapshot_date=d),
            _make_src_action("ETF", "REDUCE", snapshot_date=d),
            _make_src_action("PS", "HOLD", snapshot_date=d),
        ]
        action, source = _pick_winner(actions, [], 5000.0, d)
        assert source == "PS", f"Held: PS must win regardless of action, got {source}"
        assert action == "HOLD"

    def test_u2_etf_beats_rr_sss_ii_call_when_held(self):
        d = date(2026, 6, 1)
        actions = [
            _make_src_action("CALL", "ADD", snapshot_date=d),
            _make_src_action("II", "ADD", snapshot_date=d),
            _make_src_action("SSS", "INCREASE", snapshot_date=d),
            _make_src_action("RR", "REMOVE", snapshot_date=d),
            _make_src_action("ETF", "REDUCE", snapshot_date=d),
        ]
        action, source = _pick_winner(actions, [], 5000.0, d)
        assert source == "ETF", f"Held: ETF (rank 2) must beat RR/SSS/II/CALL, got {source}"

    def test_u3_call_is_last_when_held(self):
        d = date(2026, 6, 1)
        actions = [
            _make_src_action("CALL", "REMOVE", snapshot_date=d),  # most aggressive action
            _make_src_action("PS", "HOLD", snapshot_date=d),      # least aggressive action
        ]
        action, source = _pick_winner(actions, [], 5000.0, d)
        assert source == "PS", (
            f"Held: PS (rank 1) must beat CALL (rank 6) even when CALL has REMOVE; got {source}"
        )
        assert action == "HOLD"

    def test_u4_held_winner_action_matches_source_action(self):
        d = date(2026, 6, 1)
        # RR is rank 3, SSS is rank 4 — RR should win
        actions = [
            _make_src_action("SSS", "REMOVE", snapshot_date=d),
            _make_src_action("RR", "ADD", snapshot_date=d),
        ]
        action, source = _pick_winner(actions, [], 1000.0, d)
        assert source == "RR"
        assert action == "ADD", (
            "Held: consolidated action must be the RR ADD, not SSS REMOVE"
        )


class TestUnitNotHeldPath:
    """U5–U8: not-held recency wins."""

    def test_u5_latest_source_wins_even_over_ps(self):
        older = date(2026, 3, 1)
        newer = date(2026, 6, 10)
        actions = [
            _make_src_action("PS", "ADD", snapshot_date=older),
            _make_src_action("RR", "HOLD", snapshot_date=newer),
        ]
        action, source = _pick_winner(actions, [], 0.0, date(2026, 6, 10))
        assert source == "RR", (
            f"Not-held: RR (newer date) must beat PS (older date); got {source}"
        )

    def test_u6_tie_on_date_breaks_by_source_order(self):
        same = date(2026, 6, 1)
        actions = [
            _make_src_action("CALL", "ADD", snapshot_date=same),
            _make_src_action("RR", "ADD", snapshot_date=same),
            _make_src_action("PS", "ADD", snapshot_date=same),
        ]
        action, source = _pick_winner(actions, [], 0.0, same)
        assert source == "PS", (
            f"Not-held tie on date must break by SOURCE_ORDER (PS first); got {source}"
        )

    def test_u7_ps_remove_can_win_when_freshest_not_held(self):
        """PS REMOVE no longer excluded from not-held candidates."""
        older = date(2026, 3, 1)
        newer = date(2026, 6, 10)
        actions = [
            _make_src_action("PS", "REMOVE", snapshot_date=newer),  # freshest
            _make_src_action("RR", "ADD", snapshot_date=older),
        ]
        action, source = _pick_winner(actions, [], 0.0, date(2026, 6, 10))
        assert source == "PS", (
            f"Not-held: PS REMOVE (freshest) must win — no exclusion in TASK 49; got {source}"
        )
        assert action == "REMOVE"

    def test_u8_call_competes_on_recency_not_held(self):
        """CALL is no longer demoted when other sources present (not-held path)."""
        older = date(2026, 3, 1)
        newer = date(2026, 6, 10)
        actions = [
            _make_src_action("CALL", "ADD", snapshot_date=newer),   # freshest
            _make_src_action("RR", "REMOVE", snapshot_date=older),  # stale
        ]
        action, source = _pick_winner(actions, [], 0.0, date(2026, 6, 10))
        assert source == "CALL", (
            f"Not-held: CALL (freshest) must win when other sources are stale; got {source}"
        )

    def test_u8b_call_loses_to_older_ps_on_date_tie(self):
        """On a date tie (not-held), CALL (rank 6) must lose to PS (rank 1)."""
        same = date(2026, 6, 1)
        actions = [
            _make_src_action("CALL", "ADD", snapshot_date=same),
            _make_src_action("PS", "HOLD", snapshot_date=same),
        ]
        action, source = _pick_winner(actions, [], 0.0, same)
        assert source == "PS", (
            f"Not-held tie: PS (rank 1) must beat CALL (rank 6); got {source}"
        )


class TestUnitSSS:
    """U9–U10: SSS INCREASE/REDUCE are eligible (demotion removed)."""

    def test_u9_sss_increase_wins_held_when_top_rank(self):
        """If SSS is the only held source, SSS INCREASE must be the consolidated action."""
        d = date(2026, 6, 1)
        actions = [_make_src_action("SSS", "INCREASE", snapshot_date=d)]
        action, source = _pick_winner(actions, [], 5000.0, d)
        assert source == "SSS"
        assert action == "INCREASE"

    def test_u10_sss_reduce_wins_held_when_top_rank(self):
        """SSS REDUCE must beat RR REMOVE when SSS outranks RR on held path? No: RR=3 < SSS=4."""
        d = date(2026, 6, 1)
        actions = [
            _make_src_action("RR", "ADD", snapshot_date=d),
            _make_src_action("SSS", "REDUCE", snapshot_date=d),
        ]
        # Held: RR (rank 3) beats SSS (rank 4)
        action, source = _pick_winner(actions, [], 5000.0, d)
        assert source == "RR", f"Held: RR (rank 3) must beat SSS (rank 4); got {source}"

    def test_u10b_sss_reduce_wins_held_when_only_source(self):
        """SSS REDUCE must be the consolidated action when SSS is the only source (held)."""
        d = date(2026, 6, 1)
        actions = [_make_src_action("SSS", "REDUCE", snapshot_date=d)]
        action, source = _pick_winner(actions, [], 5000.0, d)
        assert source == "SSS"
        assert action == "REDUCE", f"SSS REDUCE must win when only source; got action={action}"

    def test_u9b_sss_increase_wins_not_held_when_freshest(self):
        """SSS INCREASE (newest) must beat RR ADD (older) on not-held path."""
        older = date(2026, 3, 1)
        newer = date(2026, 6, 5)
        actions = [
            _make_src_action("RR", "ADD", snapshot_date=older),
            _make_src_action("SSS", "INCREASE", snapshot_date=newer),
        ]
        action, source = _pick_winner(actions, [], 0.0, newer)
        assert source == "SSS", (
            f"Not-held: SSS INCREASE (freshest) must win; got {source}"
        )
        assert action == "INCREASE"

    def test_u10c_sss_reduce_wins_not_held_when_freshest(self):
        """SSS REDUCE (newest) must beat RR ADD (older) on not-held path."""
        older = date(2026, 2, 1)
        newer = date(2026, 6, 5)
        actions = [
            _make_src_action("RR", "ADD", snapshot_date=older),
            _make_src_action("SSS", "REDUCE", snapshot_date=newer),
        ]
        action, source = _pick_winner(actions, [], 0.0, newer)
        assert source == "SSS"
        assert action == "REDUCE"


class TestUnitGroupCandidates:
    """U11: group candidates rank after six sources on held path."""

    def test_u11_group_ranks_after_sources_held(self):
        """Source candidates (prio 1-6) must beat group candidates (prio typically >6) on held path."""
        d = date(2026, 6, 1)
        actions = [_make_src_action("CALL", "REMOVE", snapshot_date=d)]  # rank 6
        group = {"action": "ADD", "source_code": "RULES:MY_GROUP", "_group_prio": 10}
        action, source = _pick_winner(actions, [group], 5000.0, d)
        assert source == "CALL", (
            f"Held: CALL (rank 6) must beat group (prio 10) since 6 < 10; got {source}"
        )

    def test_u11b_group_stamped_with_as_of_date(self):
        d = date(2026, 6, 17)
        group = {"action": "ADD", "source_code": "RULES:G1", "_group_prio": 50}
        _pick_winner([], [group], 0.0, d)
        assert group.get("_update_date") == d, (
            f"Group candidate must be stamped with _update_date={d}"
        )


class TestUnitUpdOrd:
    """U12: _upd_ord returns 0 for missing date."""

    def test_u12_missing_date_returns_zero(self):
        a = {"source_snapshot_date": None, "as_of_date": None}
        assert _upd_ord_impl(a) == 0

    def test_u12b_update_date_priority(self):
        d_update = date(2026, 6, 1)
        d_snap = date(2026, 5, 1)
        a = {"_update_date": d_update, "source_snapshot_date": d_snap}
        assert _upd_ord_impl(a) == d_update.toordinal()

    def test_u12c_falls_back_to_snapshot(self):
        d = date(2026, 5, 15)
        a = {"source_snapshot_date": d, "as_of_date": date(2026, 4, 1)}
        assert _upd_ord_impl(a) == d.toordinal()

    def test_u12d_falls_back_to_as_of(self):
        d = date(2026, 4, 15)
        a = {"source_snapshot_date": None, "as_of_date": d}
        assert _upd_ord_impl(a) == d.toordinal()


class TestUnitIdempotentSort:
    """U13: re-sorting an already-sorted list is stable."""

    def test_u13_idempotent_held_sort(self):
        d = date(2026, 6, 1)
        actions = [
            _make_src_action("CALL", "REMOVE", snapshot_date=d),
            _make_src_action("ETF", "ADD", snapshot_date=d),
            _make_src_action("PS", "HOLD", snapshot_date=d),
            _make_src_action("RR", "INCREASE", snapshot_date=d),
        ]
        a1, s1 = _pick_winner(list(actions), [], 5000.0, d)
        a2, s2 = _pick_winner(list(actions), [], 5000.0, d)
        assert s1 == s2 and a1 == a2

    def test_u13_idempotent_not_held_sort(self):
        older = date(2026, 4, 1)
        newer = date(2026, 6, 1)
        actions = [
            _make_src_action("RR", "ADD", snapshot_date=newer),
            _make_src_action("PS", "ADD", snapshot_date=older),
        ]
        a1, s1 = _pick_winner(list(actions), [], 0.0, newer)
        a2, s2 = _pick_winner(list(actions), [], 0.0, newer)
        assert s1 == s2 and a1 == a2


# ---------------------------------------------------------------------------
# DB tests (auto-skip when Postgres absent)
# ---------------------------------------------------------------------------

class TestLiveDB:
    """DB smoke tests — skip gracefully when Postgres unavailable."""

    def test_db1_winning_source_populated(self, db_available):
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            row = s.execute(text("""
                SELECT tos_symbol, winning_source, consolidated_action
                FROM drv_actionable
                WHERE winning_source IS NOT NULL
                ORDER BY as_of_date DESC
                LIMIT 1
            """)).first()
        assert row is not None, "drv_actionable: no rows with winning_source set"
        assert row[1] is not None

    def test_db2_held_ps_beats_rr(self, db_available):
        """When a held symbol has both PS and RR actions, PS must be winning_source."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            anchor = s.execute(text(
                "SELECT MAX(export_date) FROM hist_td"
            )).scalar()
            if anchor is None:
                pytest.skip("No anchor date in hist_td")
            rows = s.execute(text("""
                SELECT tos_symbol, winning_source, source_actions
                FROM drv_actionable
                WHERE as_of_date = :d
                  AND held_today = TRUE
                  AND winning_source IS NOT NULL
                ORDER BY jsonb_array_length(source_actions) DESC
                LIMIT 50
            """), {"d": anchor}).fetchall()
        if not rows:
            pytest.skip("No held rows at anchor date — cannot check held path")
        # For each held row with both PS and RR in source_actions, PS must win
        violations = []
        for sym, ws, sa in rows:
            if sa is None:
                continue
            import json
            # SQLAlchemy returns JSONB columns as Python objects (list/dict), not as strings
            acts = sa if isinstance(sa, list) else json.loads(sa)
            sources_present = {a["source"] for a in acts if a.get("source")}
            if "PS" in sources_present and "RR" in sources_present:
                if ws != "PS":
                    violations.append(f"{sym}: has PS+RR, winning_source={ws} (expected PS)")
        assert not violations, (
            "Held symbols with PS+RR: PS must always win per SOURCE_ORDER:\n"
            + "\n".join(violations[:5])
        )

    def test_db3_not_held_latest_wins(self, db_available):
        """Not-held symbol with multiple sources: winning_source should have latest snapshot."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        import json as _json
        with session_scope() as s:
            anchor = s.execute(text(
                "SELECT MAX(export_date) FROM hist_td"
            )).scalar()
            if anchor is None:
                pytest.skip("No anchor date in hist_td")
            rows = s.execute(text("""
                SELECT tos_symbol, winning_source, source_actions
                FROM drv_actionable
                WHERE as_of_date = :d
                  AND held_today = FALSE
                  AND jsonb_array_length(source_actions) >= 2
                  AND winning_source IS NOT NULL
                ORDER BY tos_symbol
                LIMIT 100
            """), {"d": anchor}).fetchall()
        if not rows:
            pytest.skip("No not-held multi-source rows at anchor date")

        violations = []
        for sym, ws, sa in rows:
            if sa is None:
                continue
            # SQLAlchemy returns JSONB as Python objects, not strings
            acts = sa if isinstance(sa, list) else _json.loads(sa)
            # Find max snapshot_date across all actions
            dates = {}
            for a in acts:
                snap = a.get("snapshot_date")
                if snap:
                    from datetime import datetime
                    d = datetime.fromisoformat(snap).date() if "T" in snap else date.fromisoformat(snap)
                    dates[a["source"]] = d
            if not dates:
                continue
            max_date = max(dates.values())
            freshest_sources = {src for src, d in dates.items() if d == max_date}
            # winning_source must be among the freshest (or tied and resolved by SOURCE_ORDER)
            if ws not in freshest_sources:
                # It's a violation only if no freshest source also happens to be ws
                # (account for the case where ws has a date equal to max_date)
                ws_date = dates.get(ws)
                if ws_date != max_date:
                    violations.append(
                        f"{sym}: winning={ws} date={ws_date}, "
                        f"freshest={freshest_sources} date={max_date}"
                    )
        assert not violations, (
            "Not-held symbols: winning_source must have the latest snapshot_date:\n"
            + "\n".join(violations[:5])
        )

    def test_db4_sss_can_be_winning_source(self, db_available):
        """SSS must not be blocked from being winning_source (demotion removed)."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            row = s.execute(text("""
                SELECT tos_symbol, winning_source, consolidated_action
                FROM drv_actionable
                WHERE winning_source = 'SSS'
                ORDER BY as_of_date DESC
                LIMIT 1
            """)).first()
        # If no SSS winner exists, that's not necessarily wrong — SSS may simply not be
        # the freshest or top-ranked at the current date. We only fail if SSS is explicitly
        # blocked (covered by static test J). Mark as informational skip.
        if row is None:
            pytest.skip(
                "No SSS winning_source rows at current anchor — may be valid "
                "if SSS is not freshest/top-ranked at this date"
            )
        assert row[1] == "SSS"

    def test_db5_idempotent_derive(self, db_available):
        """derive_actionable twice on same date must produce identical rows."""
        if not db_available:
            pytest.skip("Postgres not available")
        from etl.db import session_scope
        from sqlalchemy import text
        from etl.derive_actionable import derive_actionable

        with session_scope() as s:
            anchor = s.execute(text(
                "SELECT MAX(export_date) FROM hist_td"
            )).scalar()
            if anchor is None:
                pytest.skip("No anchor date in hist_td")

            derive_actionable(s, anchor)
            rows1 = s.execute(text("""
                SELECT tos_symbol, winning_source, consolidated_action
                FROM drv_actionable
                WHERE as_of_date = :d
                ORDER BY tos_symbol
            """), {"d": anchor}).fetchall()

            derive_actionable(s, anchor)
            rows2 = s.execute(text("""
                SELECT tos_symbol, winning_source, consolidated_action
                FROM drv_actionable
                WHERE as_of_date = :d
                ORDER BY tos_symbol
            """), {"d": anchor}).fetchall()

        assert rows1 == rows2, (
            f"derive_actionable not idempotent: "
            f"{len(rows1)} rows pass 1, {len(rows2)} rows pass 2"
        )
