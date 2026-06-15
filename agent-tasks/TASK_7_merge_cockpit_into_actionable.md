# TASK 7 — Retire Cockpit: merge its unique pieces into Actionable

## Goal
Cockpit and Actionable are two answers to "what do I do today?". User decision
(2026-06-10): Actionable becomes the single daily decision surface; Cockpit is
retired. Direction approved — no plan-gate needed; proceed.

## Scope
- Move the Market-context band into Actionable: `web/macro_band.js` is
  self-contained — add its container markup (`#macroBand`, `#macroRefreshBtn`,
  `#macroAsOf`, `#macroLastFetch`) + scoped tile styles + script tag to
  `web/actionable.html`, rendered as a collapsible card ABOVE the toolbar
  (collapsed state remembered in localStorage).
- Audit `web/cockpit.html` for anything else not already on Actionable (e.g.
  briefing/summary line, anything reading endpoints Actionable doesn't) — port
  it or note in DEV_HANDOFF.md why it's dropped.
- Routing: `/cockpit` → 301/redirect to `/actionable` (api/routers/pages.py).
  Remove the Cockpit nav item from ALL web/*.html navbars.
- Delete `web/cockpit.html` (keep `web/macro_band.js`, now loaded by
  actionable.html).
- Docs: update CLAUDE.md Lookup rows referencing cockpit (macro band row →
  actionable.html), docs/macro_feed_logic.md, docs/migrations.md entry.
- Out of scope: redesigning the grid layout (separate design effort);
  TradingView tape (stays).

## Acceptance criteria
- /actionable shows the macro band (tiles + Refresh with throttle) above the
  toolbar; collapsible; band behavior identical to old Cockpit.
- /cockpit redirects to /actionable; no nav link remains; no console errors.
- No orphaned references to cockpit.html in code (grep clean except docs
  history/migrations).

## How to verify (combined test round)
- Hard-refresh /actionable: band renders, Refresh respects throttle, collapse
  state persists across reloads. /cockpit redirects. Grep for "cockpit" in
  web/ + api/ → only intentional redirect remains. Console clean; pytest.

## Constraints
- Follow CLAUDE.md rules 10/13 (docs as index rows; this is a behavior change —
  record in docs/migrations.md).
