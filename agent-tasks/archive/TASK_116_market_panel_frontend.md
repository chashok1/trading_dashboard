# TASK_116 — Market panel consolidation, part 2: frontend merge

Source: `docs/market_panel_consolidation_design.md` (read it first).
Prereq: TASK_115 done and reviewed (payload superset available).

Goal: one mini-tape + enriched side rail; tape bars 2/3 deleted; side panel
pinned by default.

Confirmed by user 2026-07-04: **hybrid** (keep mini-tape), **pinned by
default** accepted, `/` and `/portfolio` reduced to the mini-tape pulse
accepted. Use the exact instrument identifiers TASK_115's preflight recorded
in `DEV_HANDOFF.md` — do not re-derive them.

Files expected to change: `web/market_bar.js`, `web/macro_areas.js`,
`web/actionable.js` (pin defaults), `web/actionable.html` (CSS rules),
`web/styles.css` (rail row/chip styles), `CLAUDE.md` +
`docs/Screen_and_DataFlow_Reference.md` (one-line row updates),
`docs/actionable_logic.md` if it references the tapes.

## Items

1. **Mini-tape** (`market_bar.js`): replace the three-bar mount with a single
   `#rrTape1` row rendering a new `BAR_MINI` curated list — `SPX · VIX · DXY
   · GC · WTI · 10Y · HY · BTC` (use the exact metric keys/group members
   recorded by TASK_115's preflight in `DEV_HANDOFF.md`; if BTC was flagged
   unavailable there, use the substitute it proposed). Keep `chipHtml`, `mtTip`,
   `_refreshTapeGlyphs`, the 60s refresh, and the `TAPE_PAGES` set
   (`/`, `/actionable`, `/portfolio`). Add a right-aligned as-of time. Delete
   `BAR1_GROUPS`/`BAR2_CATS`/`BAR3_CATS` render paths, `#rrTape2`/`#rrTape3`
   mounts and their loading placeholders. `/api/marketbar` + `/api/rr-bar`
   calls stay (mini-tape trims client-side).
2. **Rail row upgrade** (`macro_areas.js`): extend the member row to the
   design's anatomy — `[quad glyph][SYM outlook-colored][candle][Td/Tn]
   [range bar+tick][%chg chip]` — using the TASK_115 fields. Candle via
   `window.mtTip.candleSvg(open, high, low, last)`; %chg chip solid
   green/red/gray (tape convention, honoring the member `inverted` flag);
   keep the existing stance arrow if present. Volatility members render the
   3-zone bar (port `volRangeBar` from market_bar.js — move it to a shared
   location or duplicate minimally with a comment). **Volatility symbol NAME
   is colored by zone, not outlook** (match the tape's `chipHtml` zoneColor):
   investable → green `#1d9e75`, chop → amber `#eab308`, elevated → red
   `#d4537e`. Today the rail colors the vol name by `_nameColor(outlook)`
   (usually gray) and only the trailing gauge badge shows the zone — change
   the name too so an investable VIX reads green like it does on the tape.
   Keep the zone badge. Non-volatility names stay outlook-colored. Row height
   target ~18px; font floor 10px.
3. **New sections**: render the Credit area; section headers gain ↑n/↓n
   breadth counts (from member pct_change signs); section order per the
   design doc. Existing per-section collapse persistence must keep working.
4. **Pin defaults** (`actionable.js`): missing `actSidePinned` key ⇒ pinned;
   explicit '0' stays unpinned. Auto-unpin below 1200px viewport width on
   load and resize (manual toggle wins for the session). Panel width stays
   260px.
5. **CSS cleanup** (`actionable.html`): delete the
   `body:has(#actSidePanel.pinned) #rrTape2, #rrTape3` padding rules (keep
   `#rrTape1`'s). Remove any `.rr-tape`-specific rules that are now unused
   (`styles.css`) — grep before deleting.
6. **Docs** (same task, it's small): update the CLAUDE.md market-bar lookup
   row and `docs/Screen_and_DataFlow_Reference.md` to the new architecture;
   fix any tape references in `docs/actionable_logic.md`. Note the change in
   `docs/migrations.md` per its convention.
7. **Tests**: update/retire any tests asserting three tapes or `#rrTape2/3`
   (grep `tests/` for `rrTape`, `BAR2_CATS`, `market-tape`); add a durable
   check that actionable.html/js mount exactly one tape row and that
   macro_areas renders the candle/chip for a member with OHLC.

## Guardrails

- `node --check` on every touched web/*.js **on Windows** + `tail -10`
  (mirror false-alarm gotcha).
- `mtTip` API must remain intact — actionable.js consumes it.
- The symbol tape (`#symTape`) and Econ panel are OUT of scope — untouched.
- Log in `DEV_HANDOFF.md`, end `ALL_DONE`. No commit; no tester.

## How to verify

1. /actionable: exactly one tape row; panel pinned on a fresh profile
   (cleared localStorage); grid gains the vertical space; no 404s/console
   errors.
2. Rail rows show candle + Td/Tn + range bar + %chg chip; Volatility rows
   show the 3-zone bar; Credit section present with HY colors inverted;
   breadth counts in section headers.
3. Narrow window below 1200px → panel auto-unpins; manual re-pin sticks for
   the session; explicit unpin persists across reloads.
4. `/` and `/portfolio`: mini-tape renders, no leftover empty tape divs.
5. Hover tooltips work on mini-tape chips AND rail rows; chip/row click
   behavior unchanged where it existed.
6. Grep: zero references to `rrTape2`/`rrTape3`/`BAR2_CATS`/`BAR3_CATS`
   outside retirement comments; updated tests pass.
