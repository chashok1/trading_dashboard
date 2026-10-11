# TASK_136 — Cockpit grid layout

## Goal

`/` is a single-column stack: six full-width cards, one per row. On a wide monitor every
card stretches to ~1900px while holding content that needs 400–600px, so the screen is
mostly empty and the user scrolls past six short cards instead of seeing the day at once.

Convert to a **12-column CSS grid** so the cockpit fills the viewport and the morning
read happens without scrolling.

**Layout only.** No calculation, threshold, endpoint or derive change. Content changes
are limited to the two additions in Part C, both of which use fields the API already
returns.

**No tests.** Do not write, extend, or run anything under `tests/`. Do not hand off to
the tester agent. (Standing user instruction — overrides repo convention #18.)

---

# PART A — The grid

## A.1 Current state

```css
.cockpit-bands { display: flex; flex-direction: column; gap: 10px; padding: 0 12px 12px; }
```

Six `.cockpit-band` sections stack vertically at full width.

## A.2 Target

```
┌────────────────────────────────────────────────────────────────────────┐
│ ③ REGIME — quad path · favors · avoids · breadth        full width thin│
├──────────────────────┬──────────────────────┬──────────────────────────┤
│ ① RISK DIAL          │ ② WHAT CHANGED       │ ⑤ SHORTLIST              │
│   4 cols             │   4 cols             │   4 cols                 │
├──────────────────────┴──────────────────────┴──────────────────────────┤
│ ④ FACTOR SCORECARD — full width, the table that actually needs it      │
├────────────────────────────────────────────────────────────────────────┤
│ ⑥ HOUSEKEEPING — thin; econ + earnings side by side                    │
└────────────────────────────────────────────────────────────────────────┘
```

**Why this arrangement:**

- **Regime goes on top as a thin strip** because it is inherently one horizontal line
  and it is the slow backdrop — it frames the day rather than being part of it.
- **Dial, What changed, Shortlist share one row** because that row *is* the morning
  decision: how much risk (dial) → why (what changed) → what to trade (shortlist). Left
  to right is the reading order of the decision itself.
- **Factor scorecard gets full width** because it is the only element with a genuine
  width requirement — 11 categories × ~10 numeric columns. Everything else was being
  given width it could not use.
- **Housekeeping last and thin** — it only matters when it is red.

## A.3 CSS

Replace the `.cockpit-bands` rule in `web/styles.css` (line ~1843):

```css
.cockpit-bands {
  display: grid;
  gap: 8px;
  padding: 0 8px 8px;
  align-content: start;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  grid-template-areas:
    "regime regime regime regime regime regime regime regime regime regime regime regime"
    "dial   dial   dial   dial   events events events events short  short  short  short"
    "score  score  score  score  score  score  score  score  score  score  score  score"
    "house  house  house  house  house  house  house  house  house  house  house  house";
}
#regimeBand          { grid-area: regime; }
#riskDialBand        { grid-area: dial;   }
#eventsBand          { grid-area: events; }
#shortlistBand       { grid-area: short;  }
#factorScorecardBand { grid-area: score;  }
#housekeepingBand    { grid-area: house;  }

.cockpit-band { min-width: 0; }   /* required — without it wide tables blow the grid out */
```

`minmax(0, 1fr)` and `min-width: 0` are both load-bearing. A grid track defaults to
`min-content`, so the scorecard table would force its column wider than its share and
push the layout sideways. Do not drop either.

## A.4 Breakpoints

```css
/* ≤1500px — two columns; shortlist moves under the dial */
@media (max-width: 1500px) {
  .cockpit-bands {
    grid-template-areas:
      "regime regime regime regime regime regime regime regime regime regime regime regime"
      "dial   dial   dial   dial   dial   dial   events events events events events events"
      "short  short  short  short  short  short  score  score  score  score  score  score"
      "house  house  house  house  house  house  house  house  house  house  house  house";
  }
}
/* ≤1100px — single column, current behaviour */
@media (max-width: 1100px) {
  .cockpit-bands { grid-template-columns: 1fr; grid-template-areas: none; }
  .cockpit-band  { grid-area: auto !important; }
}
```

The single-column fallback must keep DOM order = reading order, so leave the section
order in `index.html` as it is (dial, events, regime, score, short, house) and let
`grid-area` do the placement at wide sizes. **Do not reorder the HTML.**

## A.5 Vertical space

Two things currently waste height:

- `.cockpit-band { padding: 10px 14px }` → `8px 12px`.
- `.cockpit-band h2 { margin: 0 0 8px }` → `0 0 6px`.

Also check for a **double scrollbar**: `main` is `flex: 1; overflow-y: auto` (line ~796)
and `body.dash-page .cockpit-bands` is `flex: 1; min-height: 0; overflow-y: auto`
(line 832). With the grid, `.cockpit-bands` should no longer scroll independently —
remove the `flex`/`overflow-y` from that `body.dash-page` rule and let `main` own the
single scroll. Verify only one scrollbar appears.

**Target:** on a 1920×1080 screen, regime + the three-card row + the scorecard are all
visible without scrolling. Housekeeping below the fold is fine.

---

# PART B — Make the cards fill their new columns

Each card now has a defined width instead of an accidental one.

| Band | Change |
|---|---|
| **① Risk Dial** | The number/label/size-line row currently spreads across the full page. In a 4-col card, stack: number + label on line 1, `today's size = AMT$ × 0.79` on line 2 at 15px bold. Meter full card width. Gauge rows already fit. |
| **② What changed** | No change needed — event rows were always narrow. When quiet, the card is mostly empty; that is correct and now costs one third of a row instead of a full one. |
| **③ Regime** | Now a true strip. Lay out as a single flex row with `flex-wrap: wrap`: quad path · Favors · Avoids · breadth, separated by a `1px` `--border` divider. This is what it was always meant to be. |
| **④ Factor scorecard** | See Part C.1 — use the width. |
| **⑤ Shortlist** | See Part C.2. |
| **⑥ Housekeeping** | `.hk-tables` is already a 2-col grid; keep it, drop its breakpoint to `max-width: 1100px` to match A.4. |

---

# PART C — Two content additions the extra width pays for

Both use fields already in the API response. No new endpoint, no new query.

## C.1 Scorecard: show the vs-Mkt delta on all five windows

TASK_133 shipped a single benchmark comparison because the card was cramped in a
narrow stack. At full width there is room for the delta on every window, which is the
column that drives the `ROTATE` verdict — showing it for one window only made that
verdict look arbitrary.

Target columns:

```
Category | Quad | You % | vs tgt | 1w Δ | 3w Δ | 1m Δ | 2m Δ | 3m Δ | Verdict
```

where each `Δ` = `twr_<window> − bench_<window>`, coloured by sign (`--bull` / `--bear`),
`font-variant-numeric: tabular-nums`. Keep the raw `twr_*` values available in the row
`title` attribute so the absolute return is still reachable on hover.

Wrap the table in `<div style="overflow-x:auto">` so it degrades rather than breaking
the grid at narrow widths.

## C.2 Shortlist: pre-multiply the size

The shortlist sits beside the Risk Dial now. Do the multiplication for the user rather
than making them do it while reading two cards:

```
ACHC    BUY SOME    $7,900        ← AMT$ 10,000 × 0.79
                    stop 22.40
```

Show the adjusted figure as the primary number, with `AMT$ 10,000 × 0.79` beneath it in
11px `--text-3`. `suggested_size_multiplier` is already in the risk-dial response —
have `loadShortlist()` read it from the same `state` the dial populates, or fetch both
in the existing `Promise.all` and pass it in. If the multiplier is unavailable, show
the raw AMT$ with no sub-line rather than guessing.

This is presentation of two numbers the system already produces. **Do not change AMT$
itself, and do not write the adjusted figure to any table.**

---

# Done when

- `/` renders as the Part A.2 layout at ≥1500px, two columns at ≤1500px, one column at
  ≤1100px.
- No horizontal scrollbar at any width; exactly one vertical scrollbar.
- On 1920×1080, regime + the three-card row + the scorecard are visible without
  scrolling.
- Scorecard shows five delta columns; shortlist shows the pre-multiplied size.
- `node --check web/app.js` passes (file-integrity check for silent truncation, not a
  test).

## Files expected to change

`web/styles.css`, `web/app.js`. `web/index.html` only if a wrapper element is needed —
**section order must not change**.

**Not touched:** `api/`, `etl/`, `db/`, `web/actionable.*`, anything under `tests/`.

## Standing rules

- **No questions.** Where silent, match existing app conventions; note it in `DEV_HANDOFF.md`.
- **No tests.** Do not write, extend or run test files. Do not invoke the tester agent.
- **No commits, no pushes.** The user commits from Windows.
- **Layout only** — no calculation, threshold, or stored value may change.
- Append a `# Dev Handoff — TASK_136` section; end `ALL_DONE`.
