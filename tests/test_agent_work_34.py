"""
Tests for AGENT_WORK_34: Replace all -fill badge variants with -tint in web/actionable.js
so every .act-badge element uses consistent soft-colored (soft bg + colored text + border) styling.

All tests are pure static analysis -- no DB, no network, no browser required.
"""

import re
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ACTIONABLE_JS = ROOT / "web" / "actionable.js"
STYLES_CSS = ROOT / "web" / "styles.css"
ACTIONS_JS = ROOT / "web" / "actions.js"
MARKET_BAR_JS = ROOT / "web" / "market_bar.js"
RULE_FLOW_JS = ROOT / "web" / "rule_flow.js"
RULE_PERF_JS = ROOT / "web" / "rule_performance.js"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _uses_colorCls_var(line: str) -> bool:
    """
    Return True if 'line' uses the colorCls variable in either style:
      - template literal: ${colorCls}
      - string concat:    + colorCls +   or   ' + colorCls + '   or   colorCls + '"'
    """
    if "${colorCls}" in line:
        return True
    # Match: colorCls surrounded by + and/or quote chars (string concatenation context)
    return bool(re.search(r"[\"' +]colorCls[\"' +]", line))


# ---------------------------------------------------------------------------
# 1. File existence
# ---------------------------------------------------------------------------

def test_actionable_js_exists():
    """The changed file must exist."""
    assert ACTIONABLE_JS.exists(), f"Missing: {ACTIONABLE_JS}"


def test_styles_css_exists():
    assert STYLES_CSS.exists(), f"Missing: {STYLES_CSS}"


def test_actions_js_exists():
    assert ACTIONS_JS.exists(), f"Missing: {ACTIONS_JS}"


# ---------------------------------------------------------------------------
# 2. No -fill on act-badge elements in actionable.js
# ---------------------------------------------------------------------------

def test_no_act_badge_fill_in_actionable_js():
    """
    No .act-badge element should use a -fill class variant.
    Pattern: 'act-badge' and '-fill' on the same line.
    """
    src = _read(ACTIONABLE_JS)
    violations = []
    for i, line in enumerate(src.splitlines(), 1):
        if "act-badge" in line and "-fill" in line:
            violations.append(f"  line {i}: {line.strip()}")
    assert not violations, (
        "Found act-badge with -fill suffix in actionable.js:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# 3. All 11 badge locations use -tint
# ---------------------------------------------------------------------------

def test_tint_count_in_actionable_js():
    """
    DEV_HANDOFF documents 11 badge usages changed to -tint (plus 1 comment update).
    We expect at least 11 occurrences of '-tint' in actionable.js.
    """
    src = _read(ACTIONABLE_JS)
    tint_lines = [
        (i, line.strip())
        for i, line in enumerate(src.splitlines(), 1)
        if "-tint" in line
    ]
    # 11 badge usages + 1 comment = 12 expected; assert at least 11
    assert len(tint_lines) >= 11, (
        f"Expected >= 11 lines with '-tint', found {len(tint_lines)}: {tint_lines}"
    )


def test_tint_at_badge_locations():
    """
    Each act-badge construction must resolve to a -tint class.

    Two valid patterns in actionable.js:
    (A) Inline: class="act-badge ... ${(expr.colorCls || 'act-neutral') + '-tint'}"
        -- '-tint' appears on the same line as 'act-badge'.
    (B) Variable: colorCls = (expr.colorCls || 'act-neutral') + '-tint'  [line N]
        then:      class="act-badge ... ${colorCls}"   (template) or
                   '"act-badge " + colorCls + ...'     (concat)   [line N+few]
        -- '-tint' is baked into the variable at assignment.

    The DEV_HANDOFF notes that _srcSubLineHtml (~line 723) uses bare colorCls on a
    NON-act-badge span (intentional text-color-only for compact density) -- out of scope.
    """
    src = _read(ACTIONABLE_JS)
    lines = src.splitlines()

    violations = []
    for i, line in enumerate(lines):
        lineno = i + 1
        if "act-badge" not in line:
            continue
        stripped = line.strip()
        # Skip pure comment lines
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue

        # Pattern A: '-tint' appears on the same line -- OK
        if "-tint" in line:
            continue

        # -fill is explicitly disallowed on act-badge
        if "-fill" in line:
            violations.append(f"  line {lineno}: act-badge uses -fill (not -tint): {stripped}")
            continue

        # Pattern B: line uses a colorCls variable (template or concat)
        # Verify by scanning backwards up to 10 lines for the assignment with '-tint'
        if _uses_colorCls_var(line):
            found_tint_assign = False
            for back in range(1, 11):
                if i - back < 0:
                    break
                prev = lines[i - back]
                if re.search(r"(?:const|var|let)\s+colorCls\s*=.*'-tint'", prev):
                    found_tint_assign = True
                    break
                # Stop at a function/block boundary to avoid scanning across functions
                if re.search(r"^\s*(?:function\s|class\s)", prev):
                    break
            if found_tint_assign:
                continue  # Variable carries -tint -- OK
            violations.append(
                f"  line {lineno}: act-badge uses colorCls variable but no preceding "
                f"'-tint' assignment found within 10 lines: {stripped}"
            )
            continue

        # Any other act-badge line with a color token but no -tint
        has_color = any(
            tok in line
            for tok in ["colorCls", "act-sell", "act-buy", "act-neutral", "act-mixed"]
        )
        if has_color:
            violations.append(
                f"  line {lineno}: act-badge has color token but no -tint: {stripped}"
            )

    assert not violations, (
        "Found act-badge elements NOT using -tint:\n" + "\n".join(violations)
    )


def test_specific_badge_lines_use_tint():
    """
    Spot-check the specific lines documented in DEV_HANDOFF.
    Each should have '-tint' in a window of the documented line number +/- 5.
    """
    src = _read(ACTIONABLE_JS)
    lines = src.splitlines()

    check_points = [
        (647,  "colorCls variable assignment for source pills"),
        (1017, "_finalCallHtml colorCls assignment"),
        (1066, "_renderSourcePop saCls assignment"),
        (1252, "rrHtml TrTnBBRskRng badge"),
        (1277, "renderGrid Action cell main badge"),
        (1405, "_renderFocusCard action badge"),
        (1586, "Modal drilldown Action KV badge"),
        (1632, "Per-source table action column badge"),
        (1780, "Comparison panel action badge"),
        (2241, "Action hover popup header badge"),
        (2282, "Action hover popup All Sources list badge"),
    ]

    failures = []
    for target_line, desc in check_points:
        window_start = max(0, target_line - 6)
        window_end = min(len(lines), target_line + 5)
        window = "\n".join(lines[window_start:window_end])
        if "-tint" not in window:
            failures.append(
                f"  line ~{target_line} ({desc}): no '-tint' found in +-5 line window"
            )

    assert not failures, "Missing -tint at expected badge locations:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# 4. CSS has -tint definitions for all token families used in actions.js
# ---------------------------------------------------------------------------

def _get_actionable_colorCls_tokens() -> set:
    """Extract all colorCls values defined in actions.js."""
    src = _read(ACTIONS_JS)
    tokens = set(re.findall(r"colorCls:\s*'(act-[^']+)'", src))
    return tokens


def test_css_has_tint_for_all_action_tokens():
    """
    Every colorCls token from actions.js must have a -tint CSS class defined in styles.css.
    """
    tokens = _get_actionable_colorCls_tokens()
    assert tokens, "No colorCls tokens found in actions.js -- check pattern"

    css = _read(STYLES_CSS)
    missing = []
    for token in sorted(tokens):
        tint_class = f".{token}-tint"
        if tint_class not in css:
            missing.append(f"  {tint_class}")

    assert not missing, (
        "The following -tint CSS classes are missing from styles.css:\n"
        + "\n".join(missing)
    )


# ---------------------------------------------------------------------------
# 5. Other JS files unchanged and have no act-badge usage
# ---------------------------------------------------------------------------

def test_market_bar_js_no_act_badge():
    """
    market_bar.js should not use .act-badge (per dev notes: no act-badge elements there).
    """
    src = _read(MARKET_BAR_JS)
    assert "act-badge" not in src, (
        "market_bar.js unexpectedly contains 'act-badge' -- was it modified?"
    )


def test_rule_flow_js_no_act_badge():
    """rule_flow.js should not use .act-badge."""
    src = _read(RULE_FLOW_JS)
    assert "act-badge" not in src, (
        "rule_flow.js unexpectedly contains 'act-badge' -- was it modified?"
    )


def test_rule_performance_js_no_act_badge():
    """rule_performance.js should not use .act-badge."""
    src = _read(RULE_PERF_JS)
    assert "act-badge" not in src, (
        "rule_performance.js unexpectedly contains 'act-badge' -- was it modified?"
    )


# ---------------------------------------------------------------------------
# 6. No -fill on act-badge (regex-based comprehensive check)
# ---------------------------------------------------------------------------

def test_no_fill_anywhere_in_actionable():
    """
    Comprehensive regex check: no line in actionable.js has both 'act-badge' and '-fill'.
    """
    src = _read(ACTIONABLE_JS)
    pattern = re.compile(r'act-badge[^"\']*-fill')
    matches = [
        (i + 1, line)
        for i, line in enumerate(src.splitlines())
        if pattern.search(line)
    ]
    assert not matches, (
        "act-badge with -fill found:\n"
        + "\n".join(f"  line {ln}: {l.strip()}" for ln, l in matches)
    )


def test_colorCls_variable_bare_assignment_not_used_on_act_badge():
    """
    Every colorCls variable assigned WITHOUT '-tint' must NOT subsequently be used
    on an .act-badge element.

    The known legitimate bare assignment is _srcSubLineHtml (~line 723), which uses
    colorCls on a plain <span class="${colorCls}"> (not an act-badge) for compact
    density sub-lines -- intentionally text-color-only per DEV_HANDOFF.
    """
    src = _read(ACTIONABLE_JS)
    lines = src.splitlines()
    assign_pattern = re.compile(r"(?:const|var|let)\s+colorCls\s*=\s*(.+)$")
    fn_boundary = re.compile(r"^\s*(?:function\s|class\s)")

    violations = []
    for i, line in enumerate(lines):
        m = assign_pattern.search(line)
        if not m:
            continue
        rhs = m.group(1).strip()
        if re.search(r"'-tint'[\s;]*$", rhs):
            continue  # Bakes in -tint -- fine

        # Bare colorCls: scan forward to see if it reaches an act-badge
        for j in range(i + 1, min(i + 20, len(lines))):
            fwd = lines[j]
            # Stop at next colorCls reassignment or function boundary
            if assign_pattern.search(fwd) or fn_boundary.search(fwd):
                break
            if "act-badge" in fwd and _uses_colorCls_var(fwd):
                violations.append(
                    f"  line {i+1}: bare colorCls (no -tint) assigned: {line.strip()}\n"
                    f"    used on act-badge at line {j+1}: {fwd.strip()}"
                )
                break

    assert not violations, (
        "colorCls variable assigned without '-tint' but used on act-badge:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# 7. Inline badge expressions (property access, not variable) also use -tint
# ---------------------------------------------------------------------------

def test_inline_badge_expressions_use_tint():
    """
    For inline badge expressions that access .colorCls as a property inside the
    template literal (e.g. ${(actionDisplay(...).colorCls || 'act-neutral') + '-tint'}),
    confirm '-tint' is present in that same expression.

    Lines using a pre-suffixed variable (${colorCls}) are covered by other tests.
    """
    src = _read(ACTIONABLE_JS)
    # Match template literal expressions: act-badge ... ${ ... .colorCls ... }
    inline_pattern = re.compile(
        r'act-badge[^`\n]*\$\{[^}]*\.colorCls[^}]*\}'
    )
    violations = []
    for i, line in enumerate(src.splitlines(), 1):
        m = inline_pattern.search(line)
        if m:
            matched = m.group(0)
            if "-tint" not in matched and "-fill" not in matched:
                violations.append(f"  line {i}: {line.strip()}")
    assert not violations, (
        "Inline act-badge .colorCls property expression missing -tint suffix:\n"
        + "\n".join(violations)
    )
