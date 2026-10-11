# TASK_108 — Hedgeye panel: robust layout + toggle icon sync

Source: `docs/audit/actionable_screen_review.md` — U14, U15.
Prereq: TASK_107 done. Queue: 104 → 105 → 106 → 107 → **108** → 109 → 110.

Goal: replace the hand-tuned pixel flexbox with a resilient CSS-grid layout;
fix the collapse-toggle icon desync.

Files expected to change: `web/hedgeye_panel.js` (all layout lives in its
`render()` string templates), possibly `web/actionable.html` (toggle button).

## Items

1. **CSS-grid layout (U14).** The three card rows currently use hand-tuned
   flex bases — `flex:0 0 340px` (MSR card), `flex:0 0 506px` (Macro
   Commentary, with an in-code comment admitting 506px is reverse-engineered
   from the MSR image's rendered width), `calc(15ch + 20px)` / `calc(35ch +
   20px)` chip cards, fixed `height:125px` / `105px` rows with internal
   scroll. Any new card or a narrower window breaks alignment.
   - Convert each row to CSS grid with `minmax()` tracks (fixed-ish tracks
     for MSR/Top-5/RTA/ETF/II/SSS/INFL, `1fr` for Early Look / Macro Show /
     Top 3 / Call).
   - Cards size to content up to a `max-height` (keep ~125px cap) with
     internal scroll — no fixed row heights.
   - Rows must hold alignment with the side panel pinned and at ~1280px
     window width.
   - Card order, content, tooltips (`data-hetip`), ext-links (↗), and the
     collapse behavior must be unchanged.
2. **Toggle icon sync (U15).** `#hePanelToggle` ships with `icon-on`
   hard-coded in actionable.html; `render()` reads `hePanel_collapsed` for
   the body but never syncs the button classes — the chevron points the wrong
   way after a reload in collapsed state. In `render()`, set
   `icon-on`/`icon-off` on the button to match the persisted state.

## Guardrails

- JS-only string-template refactor — keep the IIFE structure and the
  `_showDataPop` tooltip coupling intact.
- Verify on Windows: `node --check web/hedgeye_panel.js`, `tail -10`.
- Log in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit; no tester.

## How to verify

1. Full-width window: all three rows render, cards aligned, no horizontal
   overflow; every card's content/tooltips/links identical to before.
2. Pin the side panel, then narrow the window to ~1280px: cards shrink
   proportionally, nothing overlaps or wraps out of its row; INFL image and
   MSR image still visible and click-to-zoom works.
3. Collapse the panel via the toolbar toggle, reload the page → panel stays
   collapsed AND the chevron icon points the correct direction; expand →
   both flip.
4. A date with sparse data (few sections) still lays out cleanly (empty
   cards show "none").
5. `node --check web/hedgeye_panel.js` passes on Windows; console clean.
