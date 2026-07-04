# Market Panel Consolidation — Design (2026-07-04)

Decision: consolidate the three market tapes (`#rrTape1/2/3`, `web/market_bar.js`)
into the Actionable side panel using the **hybrid** approach, with the side
panel **pinned by default**. Approved by user 2026-07-04.

## Why

- The side panel's macro rail (`web/macro_areas.js`, `/api/macro-areas`)
  already renders one-row-per-symbol sections (Volatility, Major Markets,
  Sectors, Rates, Commodities, USD, Country, Crypto, Tech & ETFs) covering
  largely the same instruments as the tapes (`/api/marketbar` + `/api/rr-bar`).
  Two renderers + two payloads + two visual languages for the same data.
- The 3 tapes cost ~90px of the screen's most contested vertical space.
- Hybrid keeps ambient glanceability: one mini-tape row survives.

## Target state

### 1. Mini-tape (replaces all three tapes)

- Single row, same chip renderer (`chipHtml`) and `mtTip` tooltips.
- Curated instruments (new `BAR_MINI` list): `SPX · VIX · DXY · GC · WTI ·
  10Y · HY · BTC` (10Y/HY from the rr-bar Rates/Credit groups; adjust keys to
  what `/api/marketbar`+`/api/rr-bar` actually expose). Right-aligned as-of
  time stamp.
- Mounted on the same pages as today (`/`, `/actionable`, `/portfolio`) —
  the full breadth now lives only on /actionable's panel; that is the
  working screen, other pages keep just the pulse.

### 2. Enriched side rail (absorbs tape content)

Row anatomy (~18px/row, extends the existing `msr-row`):

```
[quad ▲/▼ glyph] [SYM colored by RR outlook] [7×14 candle] [Td↗/Tn↘] [range bar + tick] [%chg chip]
```

- New vs. today's rail row: the mini candle (reuse `mtTip.candleSvg`) and the
  solid %chg chip (tape style) replacing the plain % text.
- Volatility section keeps its 3-zone (green/amber/red) bar with tick — the
  tape's `volRangeBar` and the rail gauge merge into one component. The
  volatility symbol **name is colored by zone, not outlook** (matching the
  tape's `chipHtml` zoneColor): investable → green `#1d9e75`, chop → amber
  `#eab308`, elevated → red `#d4537e`. The trailing zone badge stays;
  non-volatility names remain outlook-colored.
- Section headers gain a breadth summary (↑n ↓n) — Sectors keeps
  leaders/laggards text.
- **Credit** becomes a rail section (currently tape-bar-3 only: HY, IG, HYSPRD
  — HY/HYSPRD stay inverted-color per `INVERTED`).
- Section order = tape priority: Volatility · Major Markets · Sectors ·
  Rates & Duration · Credit · USD & Currency · Commodities · Tech & ETFs ·
  Crypto · Country. Collapse state per section persists (existing
  `_initSidePanels` mechanism).

### 3. Data flow

Server-side merge (one payload, one as-of):

- Extend `/api/macro-areas` members with the fields the tape had that the
  rail lacks: `open/high/low` (candle), `chg_pct` chip value, vol-zone
  thresholds (`vol_low/vol_high`) for the Volatility members, and add the
  Credit area + any tape-only instruments (vol pairs VXN/VXD/RVX/GVZ/OVX,
  futures GC/WTI/BZ) to `ref` membership so the rail's universe ⊇ tape
  universe.
- `/api/marketbar` + `/api/rr-bar` remain for the mini-tape (trimmed
  client-side; endpoints unchanged for compatibility).

### 4. Pinning & layout

- Default **pinned**: absence of the `actSidePinned` localStorage key now
  means pinned (today it means unpinned); explicit user unpin persists.
- Auto-unpin below ~1200px viewport width (resize listener; manual re-pin
  wins for the session).
- Remove the `body:has(#actSidePanel.pinned) #rrTape2/#rrTape3` padding
  rules; keep the rule for the mini-tape (`#rrTape1`).

### 5. Removals / kept hooks

- Remove: `BAR2_CATS`/`BAR3_CATS` render paths, `#rrTape2`/`#rrTape3` mounts,
  their padding CSS, `initEcoBarClick`'s references to tapes 2/3.
- Keep: `mtTip` (shared tooltip API used by actionable.js), `chipHtml`,
  `_refreshTapeGlyphs` (mini-tape still needs the quad-glyph refresh),
  `#econPanel` toggle (unrelated), the symbol tape `#symTape` (unrelated —
  it shows grid rows, not market context).

## Execution

Two tasks, one at a time:

1. **TASK_115 (backend)** — extend `/api/macro-areas` payload + membership
   (candle OHLC, chg chip, vol thresholds, Credit area, tape-only
   instruments). No frontend change; rail renders as today, ignoring new
   fields.
2. **TASK_116 (frontend)** — rail row upgrade + mini-tape + tape 2/3 removal
   + pin defaults + CSS cleanup. Docs (`CLAUDE.md` market-bar rows,
   `Screen_and_DataFlow_Reference.md`) updated in the same task.

Open risk: `/` and `/portfolio` lose tape bars 2/3 with no panel equivalent —
accepted (full context lives on /actionable); revisit if missed in practice.
