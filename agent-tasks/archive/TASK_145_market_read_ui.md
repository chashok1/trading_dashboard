# TASK_145 — Market Read on `/`: breadth strip + theme grid + sector cards

## Context

Design Addendum A (bands), C (positions columns), D (CALL muted), G
(placement, tiles retired). **Mockup is the acceptance reference:**
`docs/mockups/market_read_one_picture_mockup.html` — same bands, same
columns, same glyphs; only the Q3 wording in its headline is superseded
(Addendum F). Reads `/api/market-read` (TASK_143) and
`/api/market-read/sectors` (TASK_144).

The synthesis renderer that was designed for this
(`web/macro_areas.js::renderLegacyCard` / `injectLegacyCard`) is dead code —
never mounted. Reuse what's useful, delete the rest.

## Goal

### Placement (Addendum G)
- **Middle column (`.cat-col`)**, in the slot the Quad Rotation tiles occupy
  today (`#quadRotationPanel`), collapsible via that panel's existing 🧭
  filter-bar toggle (`web/quad_rotation_panel.js` → rename/repurpose to
  `web/market_read.js`, keep the `qrPanel_collapsed` localStorage key so the
  user's state carries over).
- **Quad Rotation tiles retired** — their two computations survive as grid
  columns (`quad_says`, `price`). Per-row deep-link to Actionable kept
  (`?filter_sector=` / `?filter_asset_class=` / `?filter_style=`).
- The nine macro rail panels stay, **collapsed by default**; clicking a theme
  row expands the rail band(s) its members live in. "Country ETF" leaves the
  Sector axis.
- Sector cards replace the Sectors rail panel on the right rail
  (`#macroSectorEtfsBand` content; keep the id so nothing else breaks).
- The headline sentence + conflict count render inside the existing Regime
  line band (`#regimeLineBand`), not a new band.

### Band ② — Breadth strip
Four tiles: RR macro net · ETF longs−shorts · PS count · **SSS rows + books**;
hero number, Δ vs 3 weeks ago, 13-wk sparkline (inline SVG, 2px line, dot on
latest, zero line where the series crosses zero). Flip-days line below.

### Band ③ — Theme grid
Columns exactly as the mockup: Theme · RR · ETF Pro · PS · SSS · **CALL
(muted, dashed, non-voting)** · **Price** (`pct (n_above/n_tracked)`) ·
Lists say · Agree · 1w · 4w · **Quad says** · You $ · You % · Fit. Group
rows Macro / Equity factors / Commodities & real assets / International.
Red-bordered Quad cell + amber row edge on `quad_conflict`. Hover on any
source cell lists the member symbols and their stances (`members` JSONB).

### Band ④ — Sector cards
Per sector: rows (vs med13, vs 4-wk) and book (vs prior) side by side, tier
bar (ranked / Bench / KMSignal), 13-wk rows sparkline coloured teal/red vs
median and **amber on `divergence`**, top-3, avg strength, median days-on,
RR/ETF chips, your $. One insight line above the cards when `_TOTAL` rows
and books diverge (mockup text).

### Colour
Use the mockup's validated pair — bull `#0d9488`, bear `#c2410c`, neutral
`#6b7280` — as new tokens `--mr-bull/--mr-bear/--mr-neu` in `styles.css`
(the app's `--bull/--bear` fail the deutan check; Addendum E4). Every cell
carries a glyph (▲ ▼ – ▲/▼ —); never colour alone.

### Docs
`docs/migrations.md`; `docs/dashboard_cockpit_design.md` gets a short
"Market Read (2026-09)" section pointing at the design doc; CLAUDE.md gets
one Lookup row.

## Files expected to change

- `web/index.html`, `web/market_read.js` (renamed from
  `quad_rotation_panel.js`), `web/macro_areas.js` (delete dead legacy card
  code, add collapse/expand hooks), `web/styles.css`
- `api/routers/pages.py` only if a script include changes
- `docs/migrations.md`, `docs/dashboard_cockpit_design.md`, `CLAUDE.md`
- `DEV_HANDOFF.md`

## How to verify

1. `/` loads with no console errors; Market Read panel in the middle column,
   Quad Rotation tiles gone, 🧭 toggle collapses/expands it and the state
   persists across reload.
2. Side by side with the mockup at 1200px width: same four bands, same
   columns, same glyphs. Numbers match `/api/market-read` for the anchor.
3. Hover a theme's RR cell → member symbols + stances shown.
4. Click a theme row → the matching rail band expands; rails are collapsed
   on first load.
5. Quad cell red-bordered exactly on rows where `quad_conflict` is true;
   count in the regime band equals `SUM(quad_conflict)`.
6. Sector cards: Restaurants shows rows ↓ / book ↑ with the amber line;
   Industrials shows rows 0 and the carried book with its as-of date.
7. Screenshot the panel with the browser's deuteranopia emulation — every
   B/S cell still distinguishable by glyph.
8. Accounts filter (`state.catAccounts`) scopes You $ / You % like it scopes
   the pies.
