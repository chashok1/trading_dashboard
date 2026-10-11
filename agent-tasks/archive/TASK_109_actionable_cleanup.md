# TASK_109 — Actionable: cleanup, stop alert, CSV refresh

Source: `docs/audit/actionable_screen_review.md` — F4, F6 + orphan removals.
Prereq: TASK_108 done. Queue: 104 → 105 → 106 → 107 → 108 → **109** → 110.

Goal: remove the remaining orphans, surface the stop level as a real alert,
and bring the CSV export up to date with the grid.

Files expected to change: `web/actionable.js`, `api/routers/pages.py`
(only if the /cockpit route references the deleted file), deletions:
`web/macro_band.js`, `web/cockpit.html`.

## Items

1. **Delete `toggleSuppress`** in actionable.js — orphaned since TASK_103
   removed its only caller (the `.btn-suppress` delegation).
2. **Delete `web/macro_band.js` and `web/cockpit.html`.** Orphaned: only
   cockpit.html loads macro_band.js and `/cockpit` 301-redirects to
   `/actionable`; macro_band.js also targets `#macroBand` — the same element
   id the quad regime band uses, a collision waiting to happen. Keep the 301
   route in `pages.py` (confirm it doesn't try to serve the deleted file).
3. **Stop-level alert (F6).** In the AMT$ cell, when
   `last_price < stop_level`, render the "stop …" sub-text bold red with
   `title="Price below stop level"`. Normal styling otherwise.
4. **CSV refresh (F4).** `exportCsv` mirrors the current grid: add Final Call
   (code + confidence), MACRO (already partially there — verify), CALC,
   P(↑20d), Agree, stop_level, RVOL, IVP/IV/HV, MACD, MACDH, RSI. Respect the
   TASK_105 column-visibility settings (hidden columns excluded). Keep the
   context block (POS$, Price, Held, Sector, As Of, Suppressed…). Drop the
   `Trig` column if `trig_action` is no longer surfaced anywhere on this
   screen — otherwise keep.

## Optional stretch (only if the above is done and clean)

- **Tooltip consolidation (U12):** migrate `actDetailTip` and `rrDetailTip`
  onto the `_showDataPop`/`#sourcePop` mechanism (one positioning/dismissal
  path). Do NOT touch `mtTip` (shared with other screens).
- **Legibility floor (U3):** raise sub-9px fonts in actionable cell renderers
  to 10px minimum where row height allows.

## Guardrails

- Verify on Windows: `node --check web/actionable.js`, `tail -10`.
- Deleting cockpit.html/macro_band.js: grep the repo first for any other
  reference (`grep -rn "macro_band\|cockpit" api/ web/ docs/ CLAUDE.md`) and
  fix stale references found (docs handled in TASK_110).
- Log in `DEV_HANDOFF.md`, end `ALL_DONE` (note if stretch items skipped).
  No commit; no tester.

## How to verify

1. `grep -c toggleSuppress web/actionable.js` → 0; grid actions all still work.
2. `/cockpit` in the browser → lands on /actionable; quad regime band renders
   normally (no `#macroBand` clobbering, no 404s in console/network).
3. Find/fabricate a row with `last_price < stop_level` → red bold stop text
   with tooltip; a row above its stop renders the normal gray sub-text.
4. Export CSV: headers match the visible grid columns + context block; hide a
   column via the gear menu → re-export → column absent; values spot-check
   against 2 grid rows.
5. `node --check` passes on Windows; console clean.
