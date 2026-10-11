# TASK_105 — Actionable: grid density & discoverability

Source: `docs/audit/actionable_screen_review.md` — U1, U2, U4, U5, U6, U10,
U11, U13. Prereq: TASK_104 done. Queue: 104 → **105** → 106 → 107 → 108 → 109 → 110.

Goal: cut column overload, surface the top-priority workflow, and make the
screen's vocabulary discoverable.

Files expected to change: `web/actionable.js`, `web/actionable.html`.

## Items

1. **Column show/hide manager (U1).** Gear `btn-icon` in the toolbar's right
   cluster → checklist popover of toggleable columns. Give each `th` a stable
   `data-col` id and stamp the same id on its `td`s in `renderGrid`; hide via
   per-column CSS class. Persist as `act_cols_v1` in localStorage.
   Default-hidden: CALC, P(↑20d), Agree (model diagnostics). Non-toggleable:
   bulk checkbox, H, Symbol, ACTION, AMT$, Act.
2. **Rules column width (U1b).** Replace fixed `width:720px` with
   `max-width:340px`; render at most 4 pills + `+n` suffix (full list stays in
   the drilldown; keep cell-click → /rule-flow).
3. **Top-N collapse (U2) — finish the dormant feature.** When no action-chip
   filter is active and sort is default `_priority`: render first `TOP_N` (15)
   rows + the existing `.show-all-bar` ("Show all N rows") which sets
   `state.showAll = true`. `applyClientFilter` already resets it.
4. **H column (U4).** Render H `th`/`td` only when `show_hidden` is on.
5. **Legend popover (U5).** "?" `btn-icon` → static popover (reuse
   `_showDataPop` or a small modal) documenting: action codes
   (SA/STM/SS/SO/BMN/BS/BM/HOLD + plain English), chip labels, confidence
   badges (High/Gate/Mixed), conviction filter meanings, edge badge format,
   IDY tag, RVOL dot, IV glyph, MACRO ▲▼ dots + sparkline.
6. **Conviction label (U6).** Prefix the segmented control with a tiny
   `Conv` label.
7. **Copy Symbols feedback (U10).** `showStatus('Copied N symbols','success')`.
8. **Empty state (U11).** `state.allRows` non-empty but `state.rows` empty →
   "No rows match these filters" + inline Clear Filters button. `baseRows`
   empty because everything is acted/snoozed → "All caught up for <date>".
9. **MACRO sort (U13).** MACRO `th` → `data-key="macronet" data-type="num"`
   (currently sorts `macro_value` alphabetically, which is meaningless).

## Guardrails

- Verify on Windows after edits: `node --check web/actionable.js`, `tail -10`.
- CSV export intentionally NOT touched here (TASK_109 will mirror the grid
  incl. column visibility).
- Log in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit; no tester.

## How to verify

1. Gear menu: hide CALC → column disappears (th + tds), reload page → still
   hidden; re-enable → back. Defaults on first load: CALC/P(↑20d)/Agree hidden.
2. Default view shows 15 rows + "Show all N" bar; clicking shows all; applying
   any chip filter shows the full filtered set (no bar).
3. H column absent normally; toggle Show Hidden → H column appears with Y
   markers and hover reasons.
4. "?" opens legend; every symbol/badge in it matches what the grid renders.
5. MACRO header click sorts by macronet (verify a few hover values are in
   numeric order).
6. Copy Symbols shows the success status; clipboard content correct.
7. Filter to zero rows → filter message + working Clear Filters button; act
   every row on a test date → "All caught up".
8. `node --check` passes on Windows; console clean; sorting, popovers,
   drilldown, tape all unaffected.
