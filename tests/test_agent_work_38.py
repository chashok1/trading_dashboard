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

class TestRootCSSVariables:
    """Verify --act-* CSS custom property hex values in styles.css :root."""

    def _find_var(self, var_name):
        """Return the hex value assigned to a :root CSS variable."""
        pattern = rf"{re.escape(var_name)}\s*:\s*(#[0-9A-Fa-f]{{3,8}})"
        m = re.search(pattern, STYLES_CSS)
        assert m, f"CSS variable {var_name} not found in styles.css"
        return m.group(1).upper()

    # --- SELL family ---
    def test_act_sell_strong_text_hex(self):
        assert self._find_var("--act-sell-strong") == "#791F1F"

    def test_act_sell_strong_bg_hex(self):
        assert self._find_var("--act-sell-strong-bg") == "#FCEBEB"

    def test_act_sell_text_hex(self):
        assert self._find_var("--act-sell") == "#791F1F", \
            "--act-sell should be consolidated sell-family text color"

    def test_act_sell_bg_hex(self):
        assert self._find_var("--act-sell-bg") == "#FCEBEB"

    def test_act_sell_weak_text_hex(self):
        assert self._find_var("--act-sell-weak") == "#791F1F"

    def test_act_sell_weak_bg_hex(self):
        assert self._find_var("--act-sell-weak-bg") == "#FCEBEB"

    # --- BUY family ---
    def test_act_buy_strong_text_hex(self):
        assert self._find_var("--act-buy-strong") == "#27500A"

    def test_act_buy_strong_bg_hex(self):
        assert self._find_var("--act-buy-strong-bg") == "#EAF3DE"

    def test_act_buy_text_hex(self):
        assert self._find_var("--act-buy") == "#27500A"

    def test_act_buy_bg_hex(self):
        assert self._find_var("--act-buy-bg") == "#EAF3DE"

    def test_act_buy_weak_text_hex(self):
        assert self._find_var("--act-buy-weak") == "#27500A"

    def test_act_buy_weak_bg_hex(self):
        assert self._find_var("--act-buy-weak-bg") == "#EAF3DE"

    # --- Neutral/hold ---
    def test_act_neutral_text_hex(self):
        assert self._find_var("--act-neutral") == "#444441"

    def test_act_neutral_bg_hex(self):
        assert self._find_var("--act-neutral-bg") == "#F1EFE8"

    # --- Mixed/snooze/warning ---
    def test_act_mixed_text_hex(self):
        assert self._find_var("--act-mixed") == "#633806"

    def test_act_mixed_bg_hex(self):
        assert self._find_var("--act-mixed-bg") == "#FAEEDA"


# ---------------------------------------------------------------------------
# 2. styles.css — -tint utility classes: border: none, border-radius: 8px
# ---------------------------------------------------------------------------

class TestTintClassBorders:
    """All action -tint utility classes must have border: none."""

    TINT_CLASSES = [
        "act-sell-strong-tint",
        "act-sell-tint",
        "act-sell-weak-tint",
        "act-buy-strong-tint",
        "act-buy-tint",
        "act-buy-weak-tint",
        "act-neutral-tint",
        "act-mixed-tint",
    ]

    def _get_rule_block(self, class_name):
        """Extract the CSS rule body for a given simple class selector."""
        pattern = rf"\.{re.escape(class_name)}\s*\{{([^}}]*)\}}"
        m = re.search(pattern, STYLES_CSS)
        assert m, f".{class_name} rule block not found in styles.css"
        return m.group(1)

    def _check_tint_class(self, class_name):
        block = self._get_rule_block(class_name)
        assert "border: none" in block, \
            f".{class_name} should have 'border: none' but block is: {block.strip()}"
        assert "border-radius: 8px" in block, \
            f".{class_name} should have 'border-radius: 8px' but block is: {block.strip()}"

    def test_act_sell_strong_tint_border_none(self):
        self._check_tint_class("act-sell-strong-tint")

    def test_act_sell_tint_border_none(self):
        self._check_tint_class("act-sell-tint")

    def test_act_sell_weak_tint_border_none(self):
        self._check_tint_class("act-sell-weak-tint")

    def test_act_buy_strong_tint_border_none(self):
        self._check_tint_class("act-buy-strong-tint")

    def test_act_buy_tint_border_none(self):
        self._check_tint_class("act-buy-tint")

    def test_act_buy_weak_tint_border_none(self):
        self._check_tint_class("act-buy-weak-tint")

    def test_act_neutral_tint_border_none(self):
        self._check_tint_class("act-neutral-tint")

    def test_act_mixed_tint_border_none(self):
        self._check_tint_class("act-mixed-tint")


class TestActBadgeTintCompoundSelectors:
    """compound .act-badge.*-tint selectors in styles.css must also have border: none."""

    COMPOUND_TINT_CLASSES = [
        "act-sell-strong-tint",
        "act-sell-tint",
        "act-sell-weak-tint",
        "act-buy-strong-tint",
        "act-buy-tint",
        "act-buy-weak-tint",
        "act-neutral-tint",
    ]

    def _get_compound_block(self, tint_class):
        pattern = rf"\.act-badge\.{re.escape(tint_class)}\s*\{{([^}}]*)\}}"
        m = re.search(pattern, STYLES_CSS)
        assert m, f".act-badge.{tint_class} compound rule not found in styles.css"
        return m.group(1)

    def _check_compound(self, tint_class):
        block = self._get_compound_block(tint_class)
        assert "border: none" in block, \
            f".act-badge.{tint_class} should have 'border: none'"
        assert "border-radius: 8px" in block, \
            f".act-badge.{tint_class} should have 'border-radius: 8px'"

    def test_act_badge_act_sell_strong_tint(self):
        self._check_compound("act-sell-strong-tint")

    def test_act_badge_act_sell_tint(self):
        self._check_compound("act-sell-tint")

    def test_act_badge_act_sell_weak_tint(self):
        self._check_compound("act-sell-weak-tint")

    def test_act_badge_act_buy_strong_tint(self):
        self._check_compound("act-buy-strong-tint")

    def test_act_badge_act_buy_tint(self):
        self._check_compound("act-buy-tint")

    def test_act_badge_act_buy_weak_tint(self):
        self._check_compound("act-buy-weak-tint")

    def test_act_badge_act_neutral_tint(self):
        self._check_compound("act-neutral-tint")


# ---------------------------------------------------------------------------
# 3. actionable.html — inline button styles
# ---------------------------------------------------------------------------

class TestInlineButtonStyles:
    """btn-done/skip/snz in actionable.html <style> block."""

    def _get_btn_rule(self, class_name):
        pattern = rf"\.{re.escape(class_name)}\s*\{{([^}}]*)\}}"
        matches = list(re.finditer(pattern, ACTIONABLE_HTML))
        assert matches, f".{class_name} rule not found in actionable.html"
        # Return the last match (most specific / latest override)
        return matches[-1].group(1)

    def test_btn_done_bg(self):
        block = self._get_btn_rule("btn-done")
        assert "#EAF3DE" in block.upper() or "eaf3de" in block.lower(), \
            f"btn-done background should be #EAF3DE, got: {block.strip()}"

    def test_btn_done_color(self):
        block = self._get_btn_rule("btn-done")
        assert "#27500A" in block.upper() or "27500a" in block.lower(), \
            f"btn-done color should be #27500A, got: {block.strip()}"

    def test_btn_done_border_none(self):
        block = self._get_btn_rule("btn-done")
        assert "border: none" in block, \
            f"btn-done should have 'border: none', got: {block.strip()}"

    def test_btn_done_border_radius(self):
        block = self._get_btn_rule("btn-done")
        assert "border-radius: 8px" in block, \
            f"btn-done should have 'border-radius: 8px', got: {block.strip()}"

    def test_btn_skip_bg(self):
        block = self._get_btn_rule("btn-skip")
        assert "#F1EFE8" in block.upper() or "f1efe8" in block.lower(), \
            f"btn-skip background should be #F1EFE8, got: {block.strip()}"

    def test_btn_skip_color(self):
        block = self._get_btn_rule("btn-skip")
        assert "#444441" in block.upper() or "444441" in block.lower(), \
            f"btn-skip color should be #444441, got: {block.strip()}"

    def test_btn_skip_border_none(self):
        block = self._get_btn_rule("btn-skip")
        assert "border: none" in block, \
            f"btn-skip should have 'border: none', got: {block.strip()}"

    def test_btn_skip_border_radius(self):
        block = self._get_btn_rule("btn-skip")
        assert "border-radius: 8px" in block, \
            f"btn-skip should have 'border-radius: 8px', got: {block.strip()}"

    def test_btn_snz_bg(self):
        block = self._get_btn_rule("btn-snz")
        assert "#FAEEDA" in block.upper() or "faeeda" in block.lower(), \
            f"btn-snz background should be #FAEEDA, got: {block.strip()}"

    def test_btn_snz_color(self):
        block = self._get_btn_rule("btn-snz")
        assert "#633806" in block.upper() or "633806" in block.lower(), \
            f"btn-snz color should be #633806, got: {block.strip()}"

    def test_btn_snz_border_none(self):
        block = self._get_btn_rule("btn-snz")
        assert "border: none" in block, \
            f"btn-snz should have 'border: none', got: {block.strip()}"

    def test_btn_snz_border_radius(self):
        block = self._get_btn_rule("btn-snz")
        assert "border-radius: 8px" in block, \
            f"btn-snz should have 'border-radius: 8px', got: {block.strip()}"


class TestInlineButtonHover:
    """Hover rules for btn-done/skip/snz use filter: brightness(0.95)."""

    def test_btn_done_hover_brightness(self):
        assert "btn-done:hover" in ACTIONABLE_HTML
        # Find the hover rule and check brightness
        m = re.search(r"\.btn-done:hover\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, "btn-done:hover rule not found"
        assert "brightness(0.95)" in m.group(1), \
            f"btn-done:hover should use brightness(0.95), got: {m.group(1).strip()}"

    def test_btn_skip_hover_brightness(self):
        assert "btn-skip:hover" in ACTIONABLE_HTML
        m = re.search(r"\.btn-skip:hover\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, "btn-skip:hover rule not found"
        assert "brightness(0.95)" in m.group(1), \
            f"btn-skip:hover should use brightness(0.95), got: {m.group(1).strip()}"

    def test_btn_snz_hover_brightness(self):
        assert "btn-snz:hover" in ACTIONABLE_HTML
        m = re.search(r"\.btn-snz:hover\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, "btn-snz:hover rule not found"
        assert "brightness(0.95)" in m.group(1), \
            f"btn-snz:hover should use brightness(0.95), got: {m.group(1).strip()}"


# ---------------------------------------------------------------------------
# 4. actionable.html — focus card button styles (fc-btn-*)
# ---------------------------------------------------------------------------

class TestFocusCardButtonStyles:
    """fc-btn-done/skip/snz in actionable.html match the same palette."""

    def _get_fc_btn_rule(self, class_name):
        pattern = rf"\.{re.escape(class_name)}\s*\{{([^}}]*)\}}"
        matches = list(re.finditer(pattern, ACTIONABLE_HTML))
        assert matches, f".{class_name} rule not found in actionable.html"
        return matches[-1].group(1)

    def test_fc_btn_done_bg(self):
        block = self._get_fc_btn_rule("fc-btn-done")
        assert "#EAF3DE" in block.upper() or "eaf3de" in block.lower(), \
            f"fc-btn-done bg should be #EAF3DE, got: {block.strip()}"

    def test_fc_btn_done_color(self):
        block = self._get_fc_btn_rule("fc-btn-done")
        assert "#27500A" in block.upper() or "27500a" in block.lower(), \
            f"fc-btn-done color should be #27500A, got: {block.strip()}"

    def test_fc_btn_done_border_none(self):
        block = self._get_fc_btn_rule("fc-btn-done")
        assert "border: none" in block, \
            f"fc-btn-done should have 'border: none', got: {block.strip()}"

    def test_fc_btn_skip_bg(self):
        block = self._get_fc_btn_rule("fc-btn-skip")
        assert "#F1EFE8" in block.upper() or "f1efe8" in block.lower(), \
            f"fc-btn-skip bg should be #F1EFE8, got: {block.strip()}"

    def test_fc_btn_skip_color(self):
        block = self._get_fc_btn_rule("fc-btn-skip")
        assert "#444441" in block.upper() or "444441" in block.lower(), \
            f"fc-btn-skip color should be #444441, got: {block.strip()}"

    def test_fc_btn_skip_border_none(self):
        block = self._get_fc_btn_rule("fc-btn-skip")
        assert "border: none" in block, \
            f"fc-btn-skip should have 'border: none', got: {block.strip()}"

    def test_fc_btn_snz_bg(self):
        block = self._get_fc_btn_rule("fc-btn-snz")
        assert "#FAEEDA" in block.upper() or "faeeda" in block.lower(), \
            f"fc-btn-snz bg should be #FAEEDA, got: {block.strip()}"

    def test_fc_btn_snz_color(self):
        block = self._get_fc_btn_rule("fc-btn-snz")
        assert "#633806" in block.upper() or "633806" in block.lower(), \
            f"fc-btn-snz color should be #633806, got: {block.strip()}"

    def test_fc_btn_snz_border_none(self):
        block = self._get_fc_btn_rule("fc-btn-snz")
        assert "border: none" in block, \
            f"fc-btn-snz should have 'border: none', got: {block.strip()}"

    def test_fc_btn_hover_brightness(self):
        m = re.search(
            r"\.fc-btn-done:hover.*?\.fc-btn-skip:hover.*?\.fc-btn-snz:hover\s*\{([^}]*)\}",
            ACTIONABLE_HTML, re.DOTALL
        )
        if not m:
            # Try separate rules
            combined = ACTIONABLE_HTML
            assert "fc-btn-done:hover" in combined and \
                   "fc-btn-skip:hover" in combined and \
                   "fc-btn-snz:hover" in combined, \
                "fc-btn hover rules missing"
            assert "brightness(0.95)" in combined, \
                "fc-btn hover should use brightness(0.95)"
        else:
            assert "brightness(0.95)" in m.group(1)


# ---------------------------------------------------------------------------
# 5. actionable.html — conviction-badge styles
# ---------------------------------------------------------------------------

class TestConvictionBadgeStyles:
    """conviction-badge base + edge-positive + edge-none variants."""

    def test_conviction_badge_base_bg_transparent(self):
        m = re.search(
            r"\.conviction-badge\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m, ".conviction-badge base rule not found"
        block = m.group(1)
        assert "background: transparent" in block, \
            f".conviction-badge base should have 'background: transparent', got: {block.strip()}"

    def test_conviction_badge_base_border(self):
        m = re.search(
            r"\.conviction-badge\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m
        block = m.group(1)
        assert "0.5px solid #D3D1C7" in block, \
            f".conviction-badge base should have '0.5px solid #D3D1C7', got: {block.strip()}"

    def test_conviction_badge_base_color(self):
        m = re.search(
            r"\.conviction-badge\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m
        block = m.group(1)
        assert "#888780" in block.upper() or "888780" in block.lower(), \
            f".conviction-badge base should have color #888780, got: {block.strip()}"

    def test_conviction_badge_edge_positive_bg(self):
        m = re.search(
            r"\.conviction-badge\.edge-positive\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m, ".conviction-badge.edge-positive rule not found"
        block = m.group(1)
        assert "#E1F5EE" in block.upper() or "e1f5ee" in block.lower(), \
            f".conviction-badge.edge-positive bg should be #E1F5EE, got: {block.strip()}"

    def test_conviction_badge_edge_positive_color(self):
        m = re.search(
            r"\.conviction-badge\.edge-positive\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m
        block = m.group(1)
        assert "#085041" in block.upper() or "085041" in block.lower(), \
            f".conviction-badge.edge-positive color should be #085041, got: {block.strip()}"

    def test_conviction_badge_edge_positive_border_none(self):
        m = re.search(
            r"\.conviction-badge\.edge-positive\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m
        block = m.group(1)
        assert "border: none" in block, \
            f".conviction-badge.edge-positive should have 'border: none', got: {block.strip()}"

    def test_conviction_badge_edge_none_bg_transparent(self):
        m = re.search(
            r"\.conviction-badge\.edge-none\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m, ".conviction-badge.edge-none rule not found"
        block = m.group(1)
        assert "background: transparent" in block, \
            f".conviction-badge.edge-none should have 'background: transparent', got: {block.strip()}"

    def test_conviction_badge_edge_none_border(self):
        m = re.search(
            r"\.conviction-badge\.edge-none\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m
        block = m.group(1)
        assert "0.5px solid #D3D1C7" in block, \
            f".conviction-badge.edge-none should have '0.5px solid #D3D1C7', got: {block.strip()}"

    def test_conviction_badge_edge_none_color(self):
        m = re.search(
            r"\.conviction-badge\.edge-none\s*\{([^}]*)\}", ACTIONABLE_HTML
        )
        assert m
        block = m.group(1)
        assert "#888780" in block.upper() or "888780" in block.lower(), \
            f".conviction-badge.edge-none color should be #888780, got: {block.strip()}"


# ---------------------------------------------------------------------------
# 6. actionable.html — #staleBanner inline style
# ---------------------------------------------------------------------------

class TestStaleBanner:
    """#staleBanner div should use #FAEEDA bg and border:none."""

    def test_stale_banner_bg_color(self):
        m = re.search(r'id="staleBanner"[^>]*style="([^"]*)"', ACTIONABLE_HTML)
        assert m, "#staleBanner element not found with inline style"
        style = m.group(1)
        assert "faeeda" in style.lower(), \
            f"#staleBanner bg should be #FAEEDA, got style: {style}"

    def test_stale_banner_no_border(self):
        m = re.search(r'id="staleBanner"[^>]*style="([^"]*)"', ACTIONABLE_HTML)
        assert m
        style = m.group(1)
        assert "border:none" in style.replace(" ", "").lower() or \
               "border: none" in style.lower(), \
            f"#staleBanner should have border:none, got style: {style}"

    def test_stale_banner_no_border_color(self):
        """No 1px solid border color should remain on staleBanner."""
        m = re.search(r'id="staleBanner"[^>]*style="([^"]*)"', ACTIONABLE_HTML)
        assert m
        style = m.group(1)
        assert "1px solid" not in style, \
            f"#staleBanner should not have '1px solid', got style: {style}"

    def test_stale_banner_text_color(self):
        m = re.search(r'id="staleBanner"[^>]*style="([^"]*)"', ACTIONABLE_HTML)
        assert m
        style = m.group(1)
        assert "633806" in style.lower(), \
            f"#staleBanner text color should be #633806, got style: {style}"


# ---------------------------------------------------------------------------
# 7. actionable.html — status-bar variants
# ---------------------------------------------------------------------------

class TestStatusBar:
    """status-bar.success/error/info use the new palette."""

    def test_status_bar_success_bg(self):
        m = re.search(r"\.status-bar\.success\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, ".status-bar.success rule not found"
        block = m.group(1)
        assert "#EAF3DE" in block.upper() or "eaf3de" in block.lower(), \
            f".status-bar.success bg should be #EAF3DE, got: {block.strip()}"

    def test_status_bar_success_color(self):
        m = re.search(r"\.status-bar\.success\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m
        block = m.group(1)
        assert "#27500A" in block.upper() or "27500a" in block.lower(), \
            f".status-bar.success color should be #27500A, got: {block.strip()}"

    def test_status_bar_error_bg(self):
        m = re.search(r"\.status-bar\.error\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, ".status-bar.error rule not found"
        block = m.group(1)
        assert "#FCEBEB" in block.upper() or "fcebeb" in block.lower(), \
            f".status-bar.error bg should be #FCEBEB, got: {block.strip()}"

    def test_status_bar_error_color(self):
        m = re.search(r"\.status-bar\.error\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m
        block = m.group(1)
        assert "#791F1F" in block.upper() or "791f1f" in block.lower(), \
            f".status-bar.error color should be #791F1F, got: {block.strip()}"

    def test_status_bar_info_bg(self):
        m = re.search(r"\.status-bar\.info\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, ".status-bar.info rule not found"
        block = m.group(1)
        assert "#F1EFE8" in block.upper() or "f1efe8" in block.lower(), \
            f".status-bar.info bg should be #F1EFE8, got: {block.strip()}"

    def test_status_bar_info_color(self):
        m = re.search(r"\.status-bar\.info\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m
        block = m.group(1)
        assert "#444441" in block.upper() or "444441" in block.lower(), \
            f".status-bar.info color should be #444441, got: {block.strip()}"


# ---------------------------------------------------------------------------
# 8. actionable.html — pill-my/suppressed/acted colors
# ---------------------------------------------------------------------------

class TestPillColors:
    """pill-my = amber, pill-suppressed = sell-red, pill-acted = buy-green."""

    def test_pill_my_bg(self):
        m = re.search(r"\.pill-my\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, ".pill-my rule not found"
        block = m.group(1)
        assert "#FAEEDA" in block.upper() or "faeeda" in block.lower(), \
            f".pill-my bg should be #FAEEDA, got: {block.strip()}"

    def test_pill_my_color(self):
        m = re.search(r"\.pill-my\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m
        block = m.group(1)
        assert "#633806" in block.upper() or "633806" in block.lower(), \
            f".pill-my color should be #633806, got: {block.strip()}"

    def test_pill_suppressed_bg(self):
        m = re.search(r"\.pill-suppressed\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, ".pill-suppressed rule not found"
        block = m.group(1)
        assert "#FCEBEB" in block.upper() or "fcebeb" in block.lower(), \
            f".pill-suppressed bg should be #FCEBEB, got: {block.strip()}"

    def test_pill_suppressed_color(self):
        m = re.search(r"\.pill-suppressed\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m
        block = m.group(1)
        assert "#791F1F" in block.upper() or "791f1f" in block.lower(), \
            f".pill-suppressed color should be #791F1F, got: {block.strip()}"

    def test_pill_acted_bg(self):
        m = re.search(r"\.pill-acted\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m, ".pill-acted rule not found"
        block = m.group(1)
        assert "#EAF3DE" in block.upper() or "eaf3de" in block.lower(), \
            f".pill-acted bg should be #EAF3DE, got: {block.strip()}"

    def test_pill_acted_color(self):
        m = re.search(r"\.pill-acted\s*\{([^}]*)\}", ACTIONABLE_HTML)
        assert m
        block = m.group(1)
        assert "#27500A" in block.upper() or "27500a" in block.lower(), \
            f".pill-acted color should be #27500A, got: {block.strip()}"


# ---------------------------------------------------------------------------
# 9. No layout/markup changes — structural elements not touched
# ---------------------------------------------------------------------------

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
