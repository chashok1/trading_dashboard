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
# REWRITTEN (TASK_112, 2026-07-04): TestNoLayoutChanges::test_all_column_
# headers_present drifted because the header *captions* were re-cased/
# reworded since June 2026 ('Pos $' -> 'POS$', '%chg / Price' -> '%CHG', the
# 'Final Call' column is now captioned 'ACTION'). The feature (the grid has a
# fixed, identifiable set of columns) is unchanged — only the display text
# did. Rewritten to assert the durable `data-col="..."` schema identifiers on
# the <th> elements instead of the cosmetic caption strings, so future
# re-captioning doesn't re-break this test the same way.

class TestNoLayoutChanges:
    """Confirm that markup/column/structural elements were not modified."""

    # data-col identifiers on the act-grid <th> elements — the stable schema
    # identity of each column, independent of its (cosmetic) display caption.
    REQUIRED_DATA_COLS = [
        "pos",
        "amt",
        "chg",
        "sym",
        "action",
        "sources",
        "technical",
        "rules",
        "act",
    ]

    def test_all_column_headers_present(self):
        for col in self.REQUIRED_DATA_COLS:
            assert f'data-col="{col}"' in ACTIONABLE_HTML, \
                f"Expected column data-col='{col}' missing from actionable.html"

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
# REWRITTEN (TASK_112, 2026-07-04): test_actionable_html_has_tradingview_
# widget drifted because the TV tape markup moved from static HTML to a
# dynamic injection by `_initTvToggle()` in actionable.js (confirmed via grep
# — actionable.html tail now has a `#tv-tape-wrapper` placeholder + comment
# pointing at the JS; the `tradingview-widget-container` class literal now
# lives in actionable.js, built at runtime). The feature still exists, just
# relocated — rewritten to check each file for its own current tail marker
# rather than re-pinning a snapshot.

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

    def test_actionable_html_has_tv_tape_placeholder(self):
        """TV tape placeholder (filled in at runtime by actionable.js) should be present."""
        assert 'id="tv-tape-wrapper"' in ACTIONABLE_HTML, \
            "actionable.html appears truncated — #tv-tape-wrapper placeholder missing"

    def test_actionable_js_has_tradingview_widget_builder(self):
        """The TV widget-building code that fills the placeholder should be present
        (not truncated) in actionable.js, where it now lives at runtime."""
        assert "tradingview-widget-container" in ACTIONABLE_JS, \
            "actionable.js appears truncated — TradingView widget builder missing"
        assert "_initTvToggle" in ACTIONABLE_JS, \
            "actionable.js appears truncated — _initTvToggle() missing"
