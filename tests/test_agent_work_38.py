"""
Tests for AGENT_WORK_38 — Colors-only restyle of the Actionable screen.

Checks that web/styles.css and web/actionable.html contain the correct hex
values, border settings, and border-radius as specified in the June 2026
palette. No layout, markup, or JS changes are expected.
"""
import re
import pathlib

ROOT = pathlib.Path(__file__).parent.parent
STYLES_CSS = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
ACTIONABLE_HTML = (ROOT / "web" / "actionable.html").read_text(encoding="utf-8")
ACTIONABLE_JS = (ROOT / "web" / "actionable.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. CSS custom properties — :root variable hex values
# ---------------------------------------------------------------------------

# TestRootCSSVariables — RETIRED (TASK_111 test-debt cleanup, 2026-07-04).
# Pinned exact June-2026 --act-* hex values (e.g. --act-sell-strong ==
# #791F1F). The palette has since changed (current values differ, e.g.
# #9E3636) and any legitimate future palette edit breaks this by design.
# Cat A implementation-snapshot pin per docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# 2. styles.css — -tint utility classes: border: none, border-radius: 8px
# ---------------------------------------------------------------------------

# TestTintClassBorders — RETIRED (TASK_111 test-debt cleanup, 2026-07-04).
# Pinned exact "border: none" / "border-radius: 8px" CSS rule bodies for the
# June-2026 restyle; current styles.css uses 1px solid borders instead. Cat A
# implementation-snapshot pin per docs/audit/test_debt_review.md.


# TestActBadgeTintCompoundSelectors — RETIRED (TASK_111 test-debt cleanup,
# 2026-07-04). Same compound-selector CSS-snapshot pin as
# TestTintClassBorders above. Cat A per docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# 3. actionable.html — inline button styles
# ---------------------------------------------------------------------------

# TestInlineButtonStyles — RETIRED (TASK_111 test-debt cleanup, 2026-07-04).
# Pinned exact inline hex/border CSS for btn-done/skip/snz from the
# June-2026 restyle. Cat A implementation-snapshot pin per
# docs/audit/test_debt_review.md.


# TestInlineButtonHover — RETIRED (TASK_111 test-debt cleanup, 2026-07-04).
# Pinned exact hover "brightness(0.95)" filter value. Cat A
# implementation-snapshot pin per docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# 4. actionable.html — focus card button styles (fc-btn-*)
# ---------------------------------------------------------------------------

# TestFocusCardButtonStyles — RETIRED (TASK_111 test-debt cleanup,
# 2026-07-04). Pinned exact fc-btn-* hex/border CSS from the June-2026
# restyle. Cat A implementation-snapshot pin per
# docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# 5. actionable.html — conviction-badge styles
# ---------------------------------------------------------------------------

# TestConvictionBadgeStyles — RETIRED (TASK_111 test-debt cleanup,
# 2026-07-04). Pinned exact conviction-badge hex/border CSS from the
# June-2026 restyle. Cat A implementation-snapshot pin per
# docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# 6. actionable.html — #staleBanner inline style
# ---------------------------------------------------------------------------

# TestStaleBanner — RETIRED (TASK_111 test-debt cleanup, 2026-07-04). Pinned
# exact #staleBanner inline style hex from the June-2026 restyle. Cat A
# implementation-snapshot pin per docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# 7. actionable.html — status-bar variants
# ---------------------------------------------------------------------------

# TestStatusBar — RETIRED (TASK_111 test-debt cleanup, 2026-07-04). Pinned
# exact status-bar.success/error/info hex CSS from the June-2026 restyle.
# Cat A implementation-snapshot pin per docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# 8. actionable.html — pill-my/suppressed/acted colors
# ---------------------------------------------------------------------------

# TestPillColors — RETIRED (TASK_111 test-debt cleanup, 2026-07-04). Pinned
# exact pill-my/suppressed/acted hex CSS from the June-2026 restyle. Cat A
# implementation-snapshot pin per docs/audit/test_debt_review.md.


# ---------------------------------------------------------------------------
# 9. No layout/markup changes — structural elements not touched
# ---------------------------------------------------------------------------
# NOTE (TASK_111, 2026-07-04): TestNoLayoutChanges kept per task spec — it
# does not currently pass in full (test_all_column_headers_present fails on
# 'Pos $') and is not a pure palette/hex snapshot, so it is deferred to
# TASK_112 rather than retired here (see docs/audit/test_debt_review.md
# Cat C — drifted behavioral test, judgment call).

class TestNoLayoutChanges:
    """Confirm that markup/column/structural elements were not modified."""

    REQUIRED_COLUMNS = [
        "Pos $",
        "%chg / Price",
        "Pri",
        "Symbol",
        "Final Call",
        "AMT$",
        "Sources",
        "Technical",
        "Rules (edge)",
        "Act",
    ]

    def test_all_column_headers_present(self):
        for col in self.REQUIRED_COLUMNS:
            assert col in ACTIONABLE_HTML, \
                f"Expected column header '{col}' missing from actionable.html"

    def test_act_grid_table_present(self):
        assert 'class="act-grid"' in ACTIONABLE_HTML or \
               "class='act-grid'" in ACTIONABLE_HTML, \
            "act-grid table missing from actionable.html"

    def test_focus_backdrop_present(self):
        assert 'class="focus-backdrop"' in ACTIONABLE_HTML, \
            "focus-backdrop element missing"

    def test_modal_backdrop_present(self):
        assert 'class="modal-backdrop"' in ACTIONABLE_HTML, \
            "modal-backdrop element missing"

    def test_bulk_bar_present(self):
        assert 'class="bulk-bar"' in ACTIONABLE_HTML, \
            "bulk-bar element missing"

    def test_no_inline_hex_in_js(self):
        """actionable.js should NOT emit inline hex badge colors (per spec)."""
        # Look for inline style with hex colors for sell/buy bg specifically
        # The key is that the new palette colors should come from CSS classes, not inline hex
        # This checks that no new hard-coded inline hex for action badges was added.
        sell_inline = re.search(r'style=["\'].*#FCEBEB.*["\']', ACTIONABLE_JS)
        buy_inline = re.search(r'style=["\'].*#EAF3DE.*["\']', ACTIONABLE_JS)
        assert not sell_inline, \
            "actionable.js should not emit inline #FCEBEB hex — use CSS classes"
        assert not buy_inline, \
            "actionable.js should not emit inline #EAF3DE hex — use CSS classes"


# ---------------------------------------------------------------------------
# 10. File integrity — last lines are not truncated
# ---------------------------------------------------------------------------
# NOTE (TASK_111, 2026-07-04): TestFileTails kept per task spec — it does not
# currently pass in full (test_actionable_html_has_tradingview_widget fails,
# the TV widget string is absent from actionable.html) and is not a pure
# palette/hex snapshot, so it is deferred to TASK_112 rather than retired
# here (see docs/audit/test_debt_review.md Cat C — drifted behavioral test,
# judgment call).

class TestFileTails:
    """Verify file tails are not truncated (CLAUDE.md file-truncation warning)."""

    def test_styles_css_ends_properly(self):
        # Should end with a closing brace for the last rule block
        tail = STYLES_CSS.strip()
        assert tail.endswith("}"), \
            f"styles.css tail does not end with '}}': ...{tail[-50:]!r}"

    def test_actionable_html_ends_with_body_close(self):
        tail = ACTIONABLE_HTML.strip()
        assert tail.endswith("</html>"), \
            f"actionable.html does not end with </html>: ...{tail[-80:]!r}"

    def test_styles_css_has_act_src_label(self):
        """Last rule block .act-src-label should be present (not truncated mid-file)."""
        assert ".act-src-label" in STYLES_CSS, \
            "styles.css appears truncated — .act-src-label block missing"

    def test_actionable_html_has_tradingview_widget(self):
        """TV tape at bottom of file should be present."""
        assert "tradingview-widget-container" in ACTIONABLE_HTML, \
            "actionable.html appears truncated — TradingView widget missing"
