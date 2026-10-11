# TASK_100 — Hedgeye action panel on the Actionable screen

**Type:** implementation (API + web UI). **Author:** Cowork. **Owner:** Developer.
**Source of requirement:** `docs/hedgeye_feeds_design.md` Decision #11 ("Top 5 …
stored **and shown on actionable screen**") + §7 "Open / intraday (the money-makers)".
**Depends on:** TASK_93 (data already in `hist_*`).

## Why

The Hedgeye action data is in the DB but invisible in the UI. Ashok's stated goal is
to *take action easily, without confusion*. This surfaces the intraday money-makers on
the screen he already uses for decisions (`/actionable`).

## Data sources (all already populated)

- `hist_call_top5` — The Call's Top-5 actionable ideas (`snapshot_date, rank, symbol,
  tos_symbol, side, rationale_snippet`).
- `hist_rta` — Real-Time Alerts (`alert_ts, action, side, symbol, tos_symbol, price,
  dur_trade/trend/tail, is_correction, superseded, coaching_notes`). Show only
  `superseded = FALSE`.
- `drv_rr_trend_change` — day-over-day Risk Range outlook flips
  (`as_of_date, tos_symbol, from_trend, to_trend`).
- `hist_hedgeye_stance` — daily Macro Show Bullish/Bearish list (`snapshot_date, stance,
  symbol, tos_symbol`) — used for the corroboration/disagreement flag (§7 EOD).

## API

Add `GET /api/actionable/hedgeye?date=D` (in `api/routers/dash.py` or a new
`hedgeye.py` router included by `main.py`). `date` defaults to the anchor date via the
existing `_resolve_date` helper. Return JSON:

```json
{
  "date": "2026-06-26",
  "top5":   [{"rank":1,"symbol":"AAPL","side":"long","rationale":"…"}],
  "alerts": [{"ts":"…","action":"Buy","side":"long","symbol":"…","price":…,
              "durations":["TRADE","TREND"],"is_correction":false,"notes":"…"}],
  "trend_flips": [{"symbol":"AAPL","from":"Bullish","to":"Bearish"}],
  "stance": {"bullish":["…"],"bearish":["…"]}
}
```

Reuse `tos_symbol` everywhere (Rule 15). Keep each SQL statement ≤ 965 bytes (Rule 7).

## UI

Add a Hedgeye panel to `/actionable` — model it on the existing market/macro band
(`web/macro_band.js`, loaded by `web/actionable.html`). New `web/hedgeye_panel.js`
(loaded by `actionable.html`) that fetches `/api/actionable/hedgeye?date=<current
screen date>` and renders a compact, scannable block with up to four mini-sections:

1. **Top-5 Actionable Ideas** — rank, symbol, side (color long/short), rationale on hover.
2. **Real-Time Alerts (today)** — action + side + symbol + price + duration chips
   (TRADE/TREND/TAIL); corrections flagged.
3. **Risk-Range trend flips** — `SYMBOL: Bullish → Bearish` rows, colored by direction.
4. **Stance disagreement flag** — if a symbol you hold / a fired rule conflicts with the
   Bullish/Bearish stance, highlight it (§7 EOD "you long a name Keith just flipped
   Bearish"). If cross-referencing the book is too heavy for v1, show the raw
   Bullish/Bearish counts and defer the per-symbol conflict to a follow-up.

Wire it to the screen's current date selector so it moves with the rest of the screen.
Empty sections render a quiet "none today", not an error.

## How to verify

- `GET /api/actionable/hedgeye?date=2026-06-26` returns the four blocks with real rows
  (Top-5 = 5 ideas, alerts non-superseded only, flips list, stance lists).
- `/actionable` shows the panel; changing the screen date refreshes it; long/short and
  flip directions are color-coded; corrections are visibly marked.
- Superseded RTAs are excluded; a corrected alert shows the current one, not the reversed.
- No console errors; existing actionable content unaffected.
- `pytest tests/` → no new failures.

## Done criteria

`/api/actionable/hedgeye` returns Top-5 + alerts + trend-flips + stance; the panel
renders them on `/actionable`, date-linked and color-coded. Log to `DEV_HANDOFF.md`,
end `ALL_DONE`. No commits — Ashok commits from Windows.

## Out of scope (later tasks)

Pre-open digest screen (§7), per-symbol Hedgeye dossier, rule-candidate builder,
Quad/MACRO overlay tie-in. This task is the intraday actionable surface only.
