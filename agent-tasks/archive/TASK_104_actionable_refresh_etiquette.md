# TASK_104 — Actionable: auto-refresh state preservation + search debounce

Source: `docs/audit/actionable_screen_review.md` — B5, U9. First of the
sequenced improvement tasks (queue: 104 → 105 → 106 → 107 → 108 → 109 → 110).

Goal: the 30-second auto-refresh must stop destroying the user's working
state, and symbol search must stop re-rendering per keystroke.

Files expected to change: `web/actionable.js` only.

## Item 1 — Auto-refresh preserves sort + selection (B5)

`checkForNewData()` calls `loadActionable()` when the data-status signal
changes. `loadActionable()` unconditionally resets `state.sort` to
`{key:'_priority', dir:-1}`, and `applyClientFilter()` clears
`state.selected` — so a background poll wipes the user's column sort and
bulk-selected checkboxes mid-triage.

Fix:
- Add an options param: `loadActionable({preserveState:true})`, passed **only**
  from the auto-poll path (`checkForNewData`).
- When `preserveState`: skip the `state.sort` reset, and after the new rows
  land re-intersect `state.selected` with the new symbol set (drop symbols no
  longer present) instead of clearing it. `renderBulkBar()` after.
- Manual Refresh button and date-picker change keep current reset behavior.

## Item 2 — Debounce symbol search (U9)

The `symbolSearch` `input` handler runs `applyClientFilter()` (full grid +
tape re-render) on every keystroke. Wrap in a ~150 ms trailing debounce.

## Guardrails

- After editing, verify **on Windows**: `node --check web/actionable.js` and
  `tail -10 web/actionable.js` (sandbox mirror false-alarms — CLAUDE.md gotcha).
- No other behavior changes; no API changes.
- Log in `DEV_HANDOFF.md`, end with `ALL_DONE`. Do not commit; do not invoke
  the tester.

## How to verify

1. Sort by POS$ (click header), tick 2 row checkboxes. Trigger a data-status
   change (load a TOSL/Y file, or temporarily shorten the poll and touch
   `meta_file_processed` via the normal loader). After the auto-reload: sort
   indicator still on POS$, both checkboxes still ticked (unless the symbol
   vanished from the new dataset), bulk bar still shows "2 selected".
2. Manual Refresh click → sort resets to default priority order (unchanged
   behavior).
3. Type "AAPL" quickly in symbol search → grid re-renders once (confirm via
   a temporary console.log or the Performance tab), filter result correct.
4. `node --check web/actionable.js` passes on Windows; console clean on load.
