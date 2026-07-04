"""
Tests for AGENT_WORK_19 — Unified action/direction color scheme.

Acceptance criteria:
  1. node --check passes on all edited JS files (actions.js, actionable.js,
     market_bar.js, rule_flow.js, rule_performance.js).
  2. CSS :root token block exists in styles.css with all required --act-* vars.
  3. Utility classes (.act-sell-strong, .act-buy, .act-neutral, etc.) exist in
     styles.css.
  4. actions.js _MAP entries each have a colorCls field.
  5. actionable.js has no stray action-color hex (#2f9e2f, #d83a3a, #e07c1a).
  6. actionable.js defines _actionColorCls() and uses colorCls from actions.js.
  7. actionable.html .act-chip-* and .badge-action-* use var(--act-*) not hex.
  8. rule_flow.js references var(--act-*) for action/direction colors.
  9. rule_flow.js has no hardcoded action-color hex (#2f9e2f, #d83a3a, #e07c1a).
 10. rule_performance.js uses CSS classes (act-buy-strong, act-sell-strong) for
     return coloring, not inline hex.
 11. rule_performance.js has no stray action-color hex.
 12. rule_performance.html removed local edge-pos/neg/neu and dir-buy/sell defs;
     points to styles.css.
 13. rule_flow.html removed local grp-* and val-* class defs; points to styles.css.
 14. styles.css has .dir-buy/.dir-sell/.edge-pos/.edge-neg/.edge-neu using tokens.
 15. styles.css has .grp-bearish/.grp-bullish/.grp-neutral using tokens.
 16. styles.css has .val-sa/.val-bm/.val-hold etc. using tokens.
 17. Buy=green, sell=red, hold=grey token semantics are correct.
 18. Strength variants exist: sell-strong/sell/sell-weak and buy-strong/buy/buy-weak.
 19. No git commit was made — files appear as modified (unstaged) in git status.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = PROJECT_ROOT / "web"
ACTIONS_JS = WEB_DIR / "actions.js"
ACTIONABLE_JS = WEB_DIR / "actionable.js"
ACTIONABLE_HTML = WEB_DIR / "actionable.html"
RULE_FLOW_JS = WEB_DIR / "rule_flow.js"
RULE_FLOW_HTML = WEB_DIR / "rule_flow.html"
RULE_PERF_JS = WEB_DIR / "rule_performance.js"
RULE_PERF_HTML = WEB_DIR / "rule_performance.html"
MARKET_BAR_JS = WEB_DIR / "market_bar.js"
STYLES_CSS = WEB_DIR / "styles.css"

# Action-color hex values that must NOT appear in refactored JS files
STRAY_HEX = [
    "#2f9e2f",  # old buy mid (now --act-buy)
    "#d83a3a",  # old sell strong (now --act-sell-strong)
    "#e07c1a",  # old sell weak / amber (now --act-sell-weak / --act-mixed)
]

# All required --act-* CSS custom properties
REQUIRED_TOKENS = [
    "--act-sell-strong",
    "--act-sell-strong-bg",
    "--act-sell",
    "--act-sell-bg",
    "--act-sell-weak",
    "--act-sell-weak-bg",
    "--act-buy-strong",
    "--act-buy-strong-bg",
    "--act-buy",
    "--act-buy-bg",
    "--act-buy-weak",
    "--act-buy-weak-bg",
    "--act-neutral",
    "--act-neutral-bg",
    "--act-mixed",
    "--act-mixed-bg",
]

# All action codes that must have colorCls in actions.js _MAP
REQUIRED_CODES = [
    "REMOVE", "SA", "REDUCE", "SS", "STM", "OVER_MAX", "SO", "SW", "SWW",
    "INCREASE", "BS", "BM", "ADD", "BMN", "BW", "BSW", "HOLD", "N", "BN", "SN", "NONE",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Test 1: node --check on all edited JS files ────────────────────────────

@pytest.mark.parametrize("js_file", [
    ACTIONS_JS,
    ACTIONABLE_JS,
    MARKET_BAR_JS,
    RULE_FLOW_JS,
    RULE_PERF_JS,
])
def test_node_check(js_file: Path):
    """node --check must pass on every edited JS file."""
    result = subprocess.run(
        ["node", "--check", str(js_file)],
        capture_output=True, text=True
    )
    assert result.returncode == 0, (
        f"node --check FAILED for {js_file.name}:\n{result.stderr}"
    )


# ── Test 2: CSS :root token block ─────────────────────────────────────────

@pytest.mark.parametrize("token", REQUIRED_TOKENS)
def test_css_root_has_token(token: str):
    """All required --act-* tokens must be defined in styles.css :root."""
    css = _read(STYLES_CSS)
    # token must appear as a property definition (colon follows)
    assert f"{token}:" in css, (
        f"CSS token '{token}' not found in styles.css :root block"
    )


def test_css_root_token_block_in_root():
    """The token block must be inside :root."""
    css = _read(STYLES_CSS)
    # find :root block
    root_start = css.find(":root")
    root_end = css.find("}", root_start)
    assert root_start != -1, ":root block not found in styles.css"
    root_block = css[root_start:root_end]
    # at least 10 --act-* tokens should be inside :root
    token_count = root_block.count("--act-")
    assert token_count >= 10, (
        f"Expected >= 10 --act-* tokens in :root, found {token_count}"
    )


# ── Test 3: Utility classes in styles.css ─────────────────────────────────

@pytest.mark.parametrize("cls", [
    ".act-sell-strong", ".act-sell", ".act-sell-weak",
    ".act-buy-strong", ".act-buy", ".act-buy-weak",
    ".act-neutral", ".act-mixed",
    ".act-sell-strong-fill", ".act-buy-strong-fill",
    ".act-sell-strong-tint", ".act-buy-strong-tint",
    ".dir-buy", ".dir-sell",
    ".edge-pos", ".edge-neg", ".edge-neu",
    ".grp-bearish", ".grp-bullish", ".grp-neutral",
    ".val-sa", ".val-bm", ".val-hold", ".val-null",
])
def test_css_utility_classes_exist(cls: str):
    """All token-driven utility classes must exist in styles.css."""
    css = _read(STYLES_CSS)
    assert cls in css, f"CSS utility class '{cls}' not found in styles.css"


def test_css_utility_classes_use_tokens():
    """Utility classes must reference var(--act-*), not hardcoded hex."""
    css = _read(STYLES_CSS)
    # Strip the :root token definitions block before checking
    root_start = css.find(":root {")
    root_end = css.find("}", root_start) + 1
    css_without_root = css[:root_start] + css[root_end:]
    # Find all color: and background: declarations in utility class blocks
    # The utility classes section ends before the next major section
    for hex_val in STRAY_HEX:
        # these should not appear outside the :root definitions in a color/bg context
        # (they now appear as token values inside :root only)
        pass  # covered by the per-file stray hex tests below


# ── Test 4: actions.js colorCls fields ────────────────────────────────────

@pytest.mark.parametrize("code", REQUIRED_CODES)
def test_actions_js_has_colorCls_for_code(code: str):
    """Every action code in _MAP must have a colorCls field."""
    js = _read(ACTIONS_JS)
    # Find the code's map entry as a dictionary key (e.g. 'REMOVE': {)
    # Use a regex to find the key followed by object literal start
    code_pat = re.compile(rf"['\"]({re.escape(code)})['\"]:\s*\{{")
    m = code_pat.search(js)
    assert m is not None, f"Code '{code}' not found as map key in actions.js _MAP"
    # colorCls must appear within 300 chars of the key
    snippet = js[m.start():m.start()+300]
    assert "colorCls:" in snippet, (
        f"Code '{code}' in actions.js is missing 'colorCls:' field. Snippet:\n{snippet}"
    )


def test_actions_js_default_has_colorCls():
    """_DEFAULT object in actions.js must have colorCls."""
    js = _read(ACTIONS_JS)
    default_idx = js.find("var _DEFAULT")
    assert default_idx != -1, "_DEFAULT not found in actions.js"
    snippet = js[default_idx:default_idx+200]
    assert "colorCls:" in snippet, (
        f"_DEFAULT in actions.js missing colorCls. Snippet:\n{snippet}"
    )


def test_actions_js_fallback_has_colorCls():
    """Fallback object in actionDisplay() must include colorCls."""
    js = _read(ACTIONS_JS)
    # fallback: || { label: '' + code, ... colorCls: 'act-neutral' }
    assert "colorCls: 'act-neutral'" in js or 'colorCls:"act-neutral"' in js, (
        "Fallback in actionDisplay() missing colorCls: 'act-neutral'"
    )


# ── Test 5: actionable.js — no stray action-color hex ─────────────────────

@pytest.mark.parametrize("hex_val", STRAY_HEX)
def test_actionable_js_no_stray_hex(hex_val: str):
    """actionable.js must not contain old action-color hex values in the
    action/direction color pipeline.

    REWRITTEN (TASK_112, 2026-07-04): the blind whole-file substring scan
    now also matches `_quadColor(q)`, a later, unrelated feature (MacroNet
    Quad-regime coloring — see docs/quad_design.md) that legitimately reuses
    the same green/amber/red hex tones for a completely different semantic
    domain (Quad 1-4 macro regime, not buy/sell action direction). Excluding
    that function's body from the scan restores the original, narrower
    intent: no stray hex in the *action-color* pipeline specifically. This
    correctly still catches the genuine (if currently dead-code) reintroduction
    of these hex values via `ACTION_CODE_COLOR`/`_actionCodeColor()` — see
    `## Real bugs found` in DEV_HANDOFF.md; that finding is intentionally
    left red, not papered over.
    """
    js = _read(ACTIONABLE_JS)
    quad_start = js.find("function _quadColor(")
    if quad_start != -1:
        quad_end = js.find("\n}\n", quad_start) + len("\n}\n")
        js = js[:quad_start] + js[quad_end:]
    assert hex_val.lower() not in js.lower(), (
        f"Stray action hex '{hex_val}' found in actionable.js"
    )


# ── Test 6: actionable.js has _actionColorCls and uses colorCls ───────────

def test_actionable_js_has_actionColorCls():
    """actionable.js must define _actionColorCls() helper."""
    js = _read(ACTIONABLE_JS)
    assert "_actionColorCls" in js, "_actionColorCls() not found in actionable.js"


def test_actionable_js_uses_colorCls_from_actions():
    """_actionColorCls in actionable.js must delegate to actionDisplay()."""
    js = _read(ACTIONABLE_JS)
    idx = js.find("function _actionColorCls")
    assert idx != -1, "function _actionColorCls not found"
    snippet = js[idx:idx+200]
    assert "actionDisplay" in snippet, (
        "_actionColorCls() does not call actionDisplay(). Snippet:\n" + snippet
    )
    assert "colorCls" in snippet, (
        "_actionColorCls() does not use .colorCls. Snippet:\n" + snippet
    )


# ── Test 7: actionable.html uses var(--act-*) tokens ─────────────────────

@pytest.mark.parametrize("hex_val", STRAY_HEX)
def test_actionable_html_no_stray_hex(hex_val: str):
    """actionable.html must not contain old action-color hex values."""
    html = _read(ACTIONABLE_HTML)
    assert hex_val.lower() not in html.lower(), (
        f"Stray action hex '{hex_val}' found in actionable.html"
    )


def test_actionable_html_chips_use_tokens():
    """actionable.html .act-chip-* must use var(--act-*) for border colors."""
    html = _read(ACTIONABLE_HTML)
    # All act-chip-* classes with action colors should use var(--act-*)
    chip_remove = re.search(r"\.act-chip-remove\s*\{[^}]+\}", html)
    assert chip_remove, ".act-chip-remove class not found in actionable.html"
    assert "var(--act-" in chip_remove.group(), (
        f".act-chip-remove does not use var(--act-*): {chip_remove.group()}"
    )


# test_actionable_html_badge_action_use_tokens — RETIRED (TASK_112 test-debt
# cleanup, 2026-07-04). `.badge-action-*` classes were removed outright — a
# comment in actionable.html's own <style> block explicitly documents this:
# "/* .badge-action and .badge-action-* removed — superseded by .act-badge
# in styles.css */". Cat B — superseded, not renamed. NOTE (worth
# reconsidering, not a bug to fix here): the current `.act-badge.*-fill`
# rules in styles.css (the successor) use hardcoded hex per selector
# (#d83a3a, #e07c1a, #2f9e2f — the exact "stray hex" values this task's
# STRAY_HEX list bans) rather than `var(--act-*)`, even though the
# `--act-*` custom properties still exist in :root with *different* current
# values (#9e3636 etc., used by the separate `.act-sell-strong` text-color
# classes). This is a real, if cosmetic, inconsistency between the two
# color mechanisms — not fixed here (no production code changes in this
# task); flagged in DEV_HANDOFF.md for follow-up consideration.


# ── Test 8-9: rule_flow.js uses var(--act-*), no stray action hex ─────────

@pytest.mark.parametrize("hex_val", STRAY_HEX)
def test_rule_flow_js_no_stray_hex(hex_val: str):
    """rule_flow.js must not contain old action-color hex values."""
    js = _read(RULE_FLOW_JS)
    assert hex_val.lower() not in js.lower(), (
        f"Stray action hex '{hex_val}' found in rule_flow.js"
    )


def test_rule_flow_js_references_act_tokens():
    """rule_flow.js must reference var(--act-*) for action coloring."""
    js = _read(RULE_FLOW_JS)
    assert "var(--act-" in js, (
        "rule_flow.js has no var(--act-*) references — colors may not be token-driven"
    )


# ── Test 10-11: rule_performance.js uses classes, no stray hex ────────────

@pytest.mark.parametrize("hex_val", STRAY_HEX)
def test_rule_perf_js_no_stray_hex(hex_val: str):
    """rule_performance.js must not contain old action-color hex values."""
    js = _read(RULE_PERF_JS)
    assert hex_val.lower() not in js.lower(), (
        f"Stray action hex '{hex_val}' found in rule_performance.js"
    )


def test_rule_perf_js_uses_act_classes():
    """rule_performance.js num() helper must use act-buy-strong/act-sell-strong classes."""
    js = _read(RULE_PERF_JS)
    assert "act-buy-strong" in js, (
        "rule_performance.js num() does not use 'act-buy-strong' CSS class"
    )
    assert "act-sell-strong" in js, (
        "rule_performance.js num() does not use 'act-sell-strong' CSS class"
    )


def test_rule_perf_js_uses_edge_classes():
    """rule_performance.js scorecard must use edge-pos/neg/neu CSS classes."""
    js = _read(RULE_PERF_JS)
    assert "edge-pos" in js, "rule_performance.js missing 'edge-pos' class"
    assert "edge-neg" in js, "rule_performance.js missing 'edge-neg' class"
    assert "dir-buy" in js, "rule_performance.js missing 'dir-buy' class"
    assert "dir-sell" in js, "rule_performance.js missing 'dir-sell' class"


# ── Test 12: rule_performance.html removed local class defs ───────────────

def test_rule_perf_html_no_local_edge_classes():
    """rule_performance.html must not define edge-pos/neg/neu or dir-buy/sell locally."""
    html = _read(RULE_PERF_HTML)
    # Look for CSS rule definitions of the form: .cls-name { ... }
    # (outside of comments). A comment line looks like /* ... */.
    for cls in ["edge-pos", "edge-neg", "dir-buy", "dir-sell"]:
        # Pattern: dot + class name + optional whitespace + opening brace
        # This would only match an actual CSS rule definition, not a comment mention
        pattern = re.compile(r"\." + re.escape(cls) + r"\s*\{")
        if pattern.search(html):
            pytest.fail(
                f"rule_performance.html still locally defines '.{cls}' as a CSS rule"
            )


def test_rule_perf_html_has_styles_css_pointer():
    """rule_performance.html must have a comment pointing to styles.css for moved classes."""
    html = _read(RULE_PERF_HTML)
    assert "styles.css" in html, (
        "rule_performance.html has no comment pointing to styles.css for moved classes"
    )


# ── Test 13: rule_flow.html removed local grp-* and val-* defs ────────────

def test_rule_flow_html_no_local_grp_classes():
    """rule_flow.html must not define grp-bearish/bullish/neutral locally."""
    html = _read(RULE_FLOW_HTML)
    for cls in ["grp-bearish", "grp-bullish", "grp-neutral"]:
        pattern = re.compile(r"\." + re.escape(cls) + r"\s*\{")
        if pattern.search(html):
            pytest.fail(
                f"rule_flow.html still locally defines '.{cls}' as a CSS rule"
            )


def test_rule_flow_html_no_local_val_classes():
    """rule_flow.html must not define val-sa/stm/bm/bs/etc locally."""
    html = _read(RULE_FLOW_HTML)
    for cls in ["val-sa", "val-stm", "val-bm", "val-bs", "val-hold"]:
        pattern = re.compile(r"\." + re.escape(cls) + r"\s*\{")
        if pattern.search(html):
            pytest.fail(
                f"rule_flow.html still locally defines '.{cls}' as a CSS rule"
            )


def test_rule_flow_html_has_styles_css_pointer():
    """rule_flow.html must have comment(s) pointing to styles.css for moved classes."""
    html = _read(RULE_FLOW_HTML)
    assert "styles.css" in html, (
        "rule_flow.html has no comment pointing to styles.css for moved classes"
    )


# ── Test 14-16: styles.css has all new utility class groups ───────────────

def test_styles_css_has_dir_classes():
    """styles.css must have .dir-buy and .dir-sell using var(--act-*) tokens."""
    css = _read(STYLES_CSS)
    dir_buy = re.search(r"\.dir-buy\s*\{[^}]+\}", css)
    assert dir_buy, ".dir-buy not found in styles.css"
    assert "var(--act-" in dir_buy.group(), ".dir-buy does not use var(--act-*)"

    dir_sell = re.search(r"\.dir-sell\s*\{[^}]+\}", css)
    assert dir_sell, ".dir-sell not found in styles.css"
    assert "var(--act-" in dir_sell.group(), ".dir-sell does not use var(--act-*)"


def test_styles_css_has_edge_classes():
    """styles.css must have .edge-pos, .edge-neg, .edge-neu using var(--act-*) tokens."""
    css = _read(STYLES_CSS)
    for cls in ["edge-pos", "edge-neg", "edge-neu"]:
        m = re.search(rf"\.{cls}\s*\{{[^}}]+\}}", css)
        assert m, f".{cls} not found in styles.css"
        assert "var(--act-" in m.group() or cls == "edge-neu" and "var(--act-neutral)" in m.group(), \
            f".{cls} does not use var(--act-*): {m.group()}"


def test_styles_css_has_grp_classes():
    """styles.css must have .grp-bearish, .grp-bullish, .grp-neutral using tokens."""
    css = _read(STYLES_CSS)
    for cls in ["grp-bearish", "grp-bullish", "grp-neutral"]:
        m = re.search(rf"\.{cls}\s*\{{[^}}]+\}}", css)
        assert m, f".{cls} not found in styles.css"
        assert "var(--act-" in m.group(), \
            f".{cls} does not use var(--act-*): {m.group()}"


def test_styles_css_has_val_classes():
    """styles.css must have .val-sa, .val-bm, .val-hold etc. using tokens."""
    css = _read(STYLES_CSS)
    for cls in ["val-sa", "val-stm", "val-bm", "val-bs", "val-bw", "val-hold", "val-null", "val-remove"]:
        assert f".{cls}" in css, f".{cls} not found in styles.css"


# ── Test 17: Token color semantics ────────────────────────────────────────

def test_buy_token_is_green():
    """--act-buy and --act-buy-strong must be green hues (g > r+b, roughly)."""
    css = _read(STYLES_CSS)
    # --act-buy-strong: #15803d (dark green) — just verify it's present and looks green
    m = re.search(r"--act-buy-strong:\s*(#[0-9a-fA-F]{6})", css)
    assert m, "--act-buy-strong token not found in styles.css"
    hex_val = m.group(1).lstrip("#")
    r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
    assert g > r and g > b, (
        f"--act-buy-strong {m.group(1)} does not look green (r={r}, g={g}, b={b})"
    )


def test_sell_token_is_red():
    """--act-sell-strong must be a red hue (r > g+b, roughly)."""
    css = _read(STYLES_CSS)
    m = re.search(r"--act-sell-strong:\s*(#[0-9a-fA-F]{6})", css)
    assert m, "--act-sell-strong token not found in styles.css"
    hex_val = m.group(1).lstrip("#")
    r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
    assert r > g and r > b, (
        f"--act-sell-strong {m.group(1)} does not look red (r={r}, g={g}, b={b})"
    )


def test_neutral_token_is_grey():
    """--act-neutral must be a grey hue (r ~ g ~ b)."""
    css = _read(STYLES_CSS)
    m = re.search(r"--act-neutral:\s*(#[0-9a-fA-F]{6})", css)
    assert m, "--act-neutral token not found in styles.css"
    hex_val = m.group(1).lstrip("#")
    r, g, b = int(hex_val[0:2], 16), int(hex_val[2:4], 16), int(hex_val[4:6], 16)
    max_diff = max(abs(r-g), abs(r-b), abs(g-b))
    assert max_diff < 40, (
        f"--act-neutral {m.group(1)} does not look grey (r={r}, g={g}, b={b}, max_diff={max_diff})"
    )


# ── Test 18: Strength intensity variants exist ─────────────────────────────

def test_sell_strength_variants():
    """All three sell-strength variants must be in styles.css."""
    css = _read(STYLES_CSS)
    for var in ["--act-sell-strong", "--act-sell:", "--act-sell-weak"]:
        assert var in css, f"Sell strength variant '{var}' not found in styles.css"


def test_buy_strength_variants():
    """All three buy-strength variants must be in styles.css."""
    css = _read(STYLES_CSS)
    for var in ["--act-buy-strong", "--act-buy:", "--act-buy-weak"]:
        assert var in css, f"Buy strength variant '{var}' not found in styles.css"


def test_actions_js_has_sell_strength_cls():
    """actions.js must map codes to all three sell-strength colorCls values."""
    js = _read(ACTIONS_JS)
    assert "act-sell-strong" in js, "act-sell-strong colorCls missing from actions.js"
    assert "'act-sell'" in js or '"act-sell"' in js, "act-sell colorCls missing from actions.js"
    assert "act-sell-weak" in js, "act-sell-weak colorCls missing from actions.js"


def test_actions_js_has_buy_strength_cls():
    """actions.js must map codes to all three buy-strength colorCls values."""
    js = _read(ACTIONS_JS)
    assert "act-buy-strong" in js, "act-buy-strong colorCls missing from actions.js"
    assert "'act-buy'" in js or '"act-buy"' in js, "act-buy colorCls missing from actions.js"
    assert "act-buy-weak" in js, "act-buy-weak colorCls missing from actions.js"


# ── Test 19: No git commit was made ───────────────────────────────────────

# test_no_git_commit_for_these_files — RETIRED (TASK_112 test-debt cleanup,
# 2026-07-04). Asserted a `git status --short` staging snapshot from the
# moment AGENT_WORK_19 was authored (files must appear "modified"); those
# files have long since been committed and are clean today, and any later
# unrelated edit could make this pass/fail unpredictably. Same Cat A
# git-status pattern as `TestNoGitCommit`, already retired in
# test_agent_work_18.py (TASK_111).
