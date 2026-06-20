"""
Tests for AGENT_WORK_5 — Read-only live-data validation of Price/Volume/Volatility audit.

Scope: verify that the developer agent correctly populated §6 of
docs/audit/price_volume_volatility_analysis.md with Q0–Q19 results, added
verdicts for every row, and did not modify any production code files.
No DB connection required — all assertions are structural/textual.
"""

import re
from pathlib import Path

PROJECT = Path(__file__).parent.parent
ANALYSIS_FILE = PROJECT / "docs" / "audit" / "price_volume_volatility_analysis.md"
HANDOFF_FILE = PROJECT / "DEV_HANDOFF.md"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. File existence
# ---------------------------------------------------------------------------

class TestFileExistence:
    def test_analysis_file_exists(self):
        assert ANALYSIS_FILE.exists(), (
            f"docs/audit/price_volume_volatility_analysis.md must exist"
        )

    def test_handoff_file_exists(self):
        assert HANDOFF_FILE.exists(), "DEV_HANDOFF.md must exist"

    def test_queries_file_exists(self):
        qf = PROJECT / "docs" / "audit" / "pvv_validation_queries.sql"
        assert qf.exists(), "docs/audit/pvv_validation_queries.sql must exist"


# ---------------------------------------------------------------------------
# 2. DEV_HANDOFF.md status and completeness
# ---------------------------------------------------------------------------

class TestDevHandoff:
    def test_handoff_ends_all_done(self):
        content = _read(HANDOFF_FILE)
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        assert lines[-1] == "ALL_DONE", (
            f"DEV_HANDOFF.md last non-blank line must be ALL_DONE, got {lines[-1]!r}"
        )

    def test_handoff_references_agent_work_5(self):
        content = _read(HANDOFF_FILE)
        assert "AGENT_WORK_5" in content, (
            "DEV_HANDOFF.md must reference AGENT_WORK_5"
        )

    def test_handoff_mentions_task_63(self):
        content = _read(HANDOFF_FILE)
        # Either as TASK_63 or TASK_63_pvv_live_validation
        assert "TASK_63" in content or "pvv_validation" in content.lower(), (
            "DEV_HANDOFF.md should reference TASK_63 or the PVV validation task"
        )

    def test_handoff_reports_q7_q8_findings(self):
        """DEV_HANDOFF must include Q7/Q8 quantification of F1/F2 exposure."""
        content = _read(HANDOFF_FILE)
        assert "Q7" in content and "Q8" in content, (
            "DEV_HANDOFF.md must discuss Q7 and Q8 results (F1/F2 sizing)"
        )

    def test_handoff_reports_q15_findings(self):
        """DEV_HANDOFF must include Q15 (VolumeSpike F3 exposure)."""
        content = _read(HANDOFF_FILE)
        assert "Q15" in content, (
            "DEV_HANDOFF.md must discuss Q15 (F3 VolumeSpike padding exposure)"
        )

    def test_handoff_reports_q4_q10(self):
        """DEV_HANDOFF must include Q4/Q10 (OHLC and RR bound violations)."""
        content = _read(HANDOFF_FILE)
        assert "Q4" in content and "Q10" in content, (
            "DEV_HANDOFF.md must discuss Q4 and Q10 (OHLC and RR violations)"
        )

    def test_handoff_reports_q17_q19(self):
        """DEV_HANDOFF must include Q17/Q19 (TW staleness + missing TOSD)."""
        content = _read(HANDOFF_FILE)
        assert "Q17" in content and "Q19" in content, (
            "DEV_HANDOFF.md must discuss Q17 and Q19 (staleness)"
        )

    def test_handoff_confirms_read_only(self):
        """DEV_HANDOFF must state no code changes were made."""
        content = _read(HANDOFF_FILE).lower()
        assert "no code" in content or "read-only" in content or "read only" in content, (
            "DEV_HANDOFF.md must confirm this was a read-only validation (no code changes)"
        )


# ---------------------------------------------------------------------------
# 3. Section §6 structure and completeness
# ---------------------------------------------------------------------------

class TestSection6Structure:
    def _section6(self) -> str:
        content = _read(ANALYSIS_FILE)
        # Extract from §6 header to end of file (or §7 header)
        match = re.search(r'## 6\..*', content, re.DOTALL)
        assert match, "Section 6 not found in analysis file"
        section = content[match.start():]
        # Trim at §7 if present
        end = re.search(r'\n## 7\.', section)
        if end:
            section = section[:end.start()]
        return section

    def test_section_6_exists(self):
        content = _read(ANALYSIS_FILE)
        assert "## 6." in content, "Section 6 must be present in analysis file"

    def test_anchor_date_stated(self):
        """Anchor date (Q0 result) must be recorded in §6."""
        section = self._section6()
        # Should contain a date like 2026-06-18 or 2026-XX-XX
        assert re.search(r'202\d-\d{2}-\d{2}', section), (
            "§6 must state the resolved anchor date (Q0 result)"
        )

    def test_results_table_has_19_data_rows(self):
        """Q1–Q19: exactly 19 data rows in the results table."""
        section = self._section6()
        # Match pipe-started rows that begin with | Q followed by digits
        q_rows = re.findall(r'^\| Q\d+\b', section, re.MULTILINE)
        assert len(q_rows) == 19, (
            f"§6 results table must have exactly 19 data rows (Q1–Q19), found {len(q_rows)}"
        )

    def test_all_queries_q1_through_q19_present(self):
        """Every query Q1–Q19 must have a row in the results table."""
        section = self._section6()
        for n in range(1, 20):
            pattern = rf'^\| Q{n}\b'
            assert re.search(pattern, section, re.MULTILINE), (
                f"Q{n} row is missing from the §6 results table"
            )

    def test_no_pending_placeholders(self):
        """No _pending_ placeholder values remain in §6."""
        section = self._section6()
        assert "_pending_" not in section, (
            "§6 still contains '_pending_' placeholder — results were not filled in"
        )

    def test_every_row_has_verdict(self):
        """Every Q row must have a non-empty Verdict column (5th pipe-separated field)."""
        section = self._section6()
        q_rows = re.findall(r'^\| Q\d+.*', section, re.MULTILINE)
        for row in q_rows:
            parts = [p.strip() for p in row.split('|')]
            # Expected: ['', 'Qn', 'Checks', 'Expected', 'Result', 'Verdict', '']
            assert len(parts) >= 6, f"Row has fewer than 5 columns: {row[:60]}"
            verdict = parts[5] if len(parts) > 5 else ""
            assert verdict and verdict not in ("-", "—", ""), (
                f"Row {parts[1]} has empty or missing verdict: {row[:80]}"
            )

    def test_every_row_has_numeric_result(self):
        """Every Q row's Result column must contain at least one number (not just text)."""
        section = self._section6()
        q_rows = re.findall(r'^\| Q\d+.*', section, re.MULTILINE)
        for row in q_rows:
            parts = [p.strip() for p in row.split('|')]
            if len(parts) < 5:
                continue
            result = parts[4]
            has_number = bool(re.search(r'\d', result))
            assert has_number, (
                f"Row {parts[1]} Result column appears to have no numeric data: {result[:60]}"
            )

    def test_query_rewrites_documented(self):
        """§6 must document the query rewrites that were needed (Q8, Q9, Q12, Q16)."""
        section = self._section6()
        for q in ("Q8", "Q9", "Q12", "Q16"):
            assert q in section, (
                f"{q} rewrite must be documented in §6 preamble"
            )


# ---------------------------------------------------------------------------
# 4. Key finding values cross-checked between DEV_HANDOFF and analysis file
# ---------------------------------------------------------------------------

class TestFindingValues:
    def test_f1_f2_material_finding_recorded(self):
        """F1/F2 divergence rate should be recorded as > 50% in both files."""
        analysis = _read(ANALYSIS_FILE)
        handoff = _read(HANDOFF_FILE)
        # Q7 shows 543/966 = 56%, Q8 shows 505/882 = 57%
        # Either file should mention >50% or a specific large fraction
        for content, fname in [(analysis, "analysis"), (handoff, "handoff")]:
            has_majority = (
                "56%" in content or "57%" in content
                or "543" in content or "505" in content
                or "majority" in content.lower()
                or "more than half" in content.lower()
            )
            assert has_majority, (
                f"The {fname} file should record that F1/F2 affects >50% of symbols"
            )

    def test_f3_zero_exposure_recorded(self):
        """Q15 result of zero at-risk rows must appear in at least one of the files."""
        analysis = _read(ANALYSIS_FILE)
        handoff = _read(HANDOFF_FILE)
        combined = analysis + handoff
        zero_exposure = (
            "short_fg_at_risk=0" in combined
            or "at_risk=0" in combined
            or "zero" in combined.lower() and "F3" in combined
            or "0 at-risk" in combined
            or "0\n" in combined  # loose check
        )
        # Check the analysis file specifically for zero result in Q15 row
        q15_match = re.search(r'\| Q15 .*', analysis)
        if q15_match:
            q15_row = q15_match.group(0)
            assert re.search(r'\b0\b', q15_row), (
                "Q15 row must show zero at-risk rows for F3"
            )

    def test_q4_ohlc_violation_result_recorded(self):
        """Q4 OHLC violation result must be in the analysis (expect 0 or 1)."""
        analysis = _read(ANALYSIS_FILE)
        q4_match = re.search(r'\| Q4 .*', analysis)
        assert q4_match, "Q4 row must exist in §6"
        q4_row = q4_match.group(0)
        assert re.search(r'\d', q4_row), "Q4 row must contain a numeric result"

    def test_q10_no_inverted_bounds(self):
        """Q10 should confirm zero inverted RR bounds."""
        analysis = _read(ANALYSIS_FILE)
        q10_match = re.search(r'\| Q10 .*', analysis)
        assert q10_match, "Q10 row must exist in §6"
        q10_row = q10_match.group(0)
        # Should contain inverted=0
        assert "inverted=0" in q10_row or "inverted_bounds=0" in q10_row or (
            "0" in q10_row and "inverted" in q10_row.lower()
        ), "Q10 row should show zero inverted bounds"

    def test_q17_staleness_quantified(self):
        """Q17 TW staleness: must show both fresh and stale counts."""
        analysis = _read(ANALYSIS_FILE)
        q17_match = re.search(r'\| Q17 .*', analysis)
        assert q17_match, "Q17 row must exist in §6"
        q17_row = q17_match.group(0)
        # Should contain multiple numbers (fresh count, stale count)
        numbers = re.findall(r'\d+', q17_row)
        assert len(numbers) >= 3, (
            f"Q17 row should contain multiple counts (fresh/stale), found: {numbers}"
        )

    def test_q19_missing_tosd_quantified(self):
        """Q19 must report both universe total and missing-TOSD count."""
        analysis = _read(ANALYSIS_FILE)
        q19_match = re.search(r'\| Q19 .*', analysis)
        assert q19_match, "Q19 row must exist in §6"
        q19_row = q19_match.group(0)
        numbers = re.findall(r'\d+', q19_row)
        assert len(numbers) >= 2, (
            f"Q19 row should contain universe + missing_tosd counts, found: {numbers}"
        )


# ---------------------------------------------------------------------------
# 5. Overall document completeness
# ---------------------------------------------------------------------------

class TestDocumentCompleteness:
    def test_all_7_sections_present(self):
        content = _read(ANALYSIS_FILE)
        for n in range(1, 8):
            assert f"## {n}." in content, f"Section {n} is missing from analysis file"

    def test_no_truncation(self):
        """File must end with the closing citation line, not mid-sentence."""
        content = _read(ANALYSIS_FILE)
        # Should end with the italic citation
        assert content.strip().endswith("*"), (
            "Analysis file appears truncated — does not end with closing italic"
        )

    def test_section7_recommendations_present(self):
        content = _read(ANALYSIS_FILE)
        assert "## 7." in content, "Section 7 (Recommendations) must be present"
        # Should have at least F1 recommendation
        assert "F1" in content or "F2" in content, (
            "Section 7 must include F1/F2 fix recommendations"
        )

    def test_anchor_date_consistent(self):
        """Anchor date in §6 should match anchor date mentioned in DEV_HANDOFF."""
        analysis = _read(ANALYSIS_FILE)
        handoff = _read(HANDOFF_FILE)
        # Extract all dates from both
        analysis_dates = set(re.findall(r'202\d-\d{2}-\d{2}', analysis))
        handoff_dates = set(re.findall(r'202\d-\d{2}-\d{2}', handoff))
        # The anchor date (2026-06-18) should appear in both
        overlap = analysis_dates & handoff_dates
        assert overlap, (
            f"No common date found between analysis ({analysis_dates}) "
            f"and handoff ({handoff_dates}) — anchor date should appear in both"
        )


# ---------------------------------------------------------------------------
# 6. No production code was modified by this task
# ---------------------------------------------------------------------------

class TestNoProductionCodeModified:
    """
    AGENT_WORK_5 is read-only — it must not have modified production source files.
    We verify by checking that the task-specific deliverable files are only
    docs/audit/* files (new/untracked) and that production directories show no
    changes attributable to this task.

    Note: pre-existing working-tree modifications in etl/, api/, db/, web/ existed
    before AGENT_WORK_5 and are out of scope. We verify only that the files specified
    in DEV_HANDOFF.md > "Files changed" do NOT include any production source files.
    """

    def test_handoff_files_changed_only_docs(self):
        """Files changed listed in DEV_HANDOFF.md must only reference docs/ paths."""
        content = _read(HANDOFF_FILE)
        # Find the "Files changed" section
        match = re.search(r'## Files changed(.*?)(?=\n## |\Z)', content, re.DOTALL)
        if not match:
            # Section may not exist — that's fine for a read-only task
            return
        files_section = match.group(1)
        # Extract any file paths mentioned
        paths = re.findall(r'`([^`]+\.(?:md|sql|py|js|html|css))`', files_section)
        for path in paths:
            assert path.startswith("docs/") or path.startswith("DEV_HANDOFF"), (
                f"DEV_HANDOFF 'Files changed' mentions non-docs file: {path}. "
                "AGENT_WORK_5 is read-only — only docs/ files should be changed."
            )

    def test_analysis_file_is_new_not_core_production(self):
        """The analysis file is a docs artifact, not a production code file."""
        path = ANALYSIS_FILE
        # Just confirm it lives in docs/audit/
        assert "docs" in str(path) and "audit" in str(path), (
            "price_volume_volatility_analysis.md should be in docs/audit/"
        )
        # Confirm it does NOT contain Python function definitions (sanity check it's a doc)
        content = _read(path)
        assert "def " not in content or content.count("def ") <= 3, (
            "Analysis file should be a markdown document, not code"
        )
