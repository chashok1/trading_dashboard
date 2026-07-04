"""
Tests for AGENT_WORK_24 — Source-actions sub-line beneath main action badge
in the Actionable screen's Action column.

RETIRED WHOLESALE (TASK_112 test-debt cleanup, 2026-07-04).

This file pinned a specific, since-superseded implementation of the
"per-source breakdown" feature:
  - `_srcSubLineHtml()` (a compact sub-line under the main Action-column
    badge) no longer exists in web/actionable.js (0 matches via grep).
  - Its CSS classes `.act-src-sub` / `.act-src-token` / `.act-src-label`
    are dead rules in web/styles.css — nothing emits them anymore.
  - The underlying behavior (standardized, colored, winner-first per-source
    breakdown) was relocated to the *Sources* column as always-visible
    reason lines, implemented by `_srcReasonsHtml()` and CSS classes
    `.src-reasons` / `.src-reason-line` / `.src-tag` / `.src-ic` / `.src-rsn`
    in web/actionable.html. That current behavior is already covered by the
    rewritten `TestSrcReasonsHtml` class in test_agent_work_27.py (TASK_112)
    — there is no remaining gap to re-test here.
  - `TestNoCommit` additionally pinned a specific git HEAD commit hash
    (`b764d89`) — a Cat A implementation-snapshot/git-status pin, same
    pattern as the `TestNoGitCommit` class retired in test_agent_work_18.py
    (TASK_111).
  - `TestFrontendOnly` asserted that the (now nonexistent) `_srcSubLineHtml`
    / `act-src-sub` tokens don't leak into Python files — vacuously true
    forever now that neither token exists anywhere, so it asserts nothing
    meaningful.
  - `TestFileIntegrity`'s generic file-length/closing-brace sanity checks are
    already covered by test_agent_work_38.py::TestFileTails and
    test_agent_work_39.py::TestBlockD_FileTails/FileSyntax.

Per docs/audit/test_debt_review.md Cat B (feature superseded, not merely
renamed) — retired comments-in-place rather than rewritten, since a rewrite
here would just duplicate the TestSrcReasonsHtml coverage already added to
test_agent_work_27.py.
"""
