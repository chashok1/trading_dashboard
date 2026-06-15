# TASK 46 — Restyle econ bar 1 + bar 2 tiles (symbol button + range bar + candle)

## Goal

Replace the current per-symbol chips in **econ bar 1** (`#marketTape`,
`GET /api/marketbar`) and **econ bar 2** (`#rrTape`, `GET /api/rr-bar`) with a new
card-style tile. Both bars stay **single-row horizontal scrolling tapes**
(unchanged layout/scroll behaviour) — only each tile's look changes, and each
tile becomes fixed-width (~180px).

New tile anatomy (one per symbol), left → right:

```
┌──────────────────────────┬────┐
│ [AAPL]          +1.85%    │ ▐  │   ← symbol = white-on-outlook-color button;
│ ░░░░░░░░░░|░░░░░░░░░░░     │ █  │     % change colored by direction
│                          │ ▌  │   ← range bar (LRR→TRR) w/ current-price tick
└──────────────────────────┴────┘   ← candle (O/H/L/C) on the right, full-height strip
```

Data sources (per user): **OHLC from `drv_quote`**, **range + outlook from `drv_rr`**
(a new `outlook` column is added to `drv_rr` in this task).

---

## Part A — DB: add `outlook` to `drv_rr`

### A1. `db/baseline.sql`

In the `CREATE TABLE IF NOT EXISTS drv_rr (...)` block (~line 2305) add an
`outlook` column:

```sql
    mrr             NUMERIC,        -- Midpoint (lrr + trr) / 2
    outlook         TEXT,           -- outlook from hist_rr (Bullish/Bearish/Neutral); NULL when BB fallback
    source          TEXT,           -- 'RR' or 'BB'
```

Then add a plain migration statement (NOT inside a `DO $$ … $$` block — `init_db`
swallows DO blocks per CLAUDE.md) near the other `drv_rr` alters:

```sql
ALTER TABLE drv_rr ADD COLUMN IF NOT EXISTS outlook TEXT;
```

### A2. `etl/derive.py` — `_derive_rr_impl` (~line 1585)

The `rr` LATERAL subquery already reads `hist_rr`. Add `outlook` to it and to the
INSERT:

- INSERT column list → add `outlook`:
  ```sql
  INSERT INTO drv_rr (as_of_date, tos_symbol, lrr, trr, mrr, outlook, source, source_run_id)
  ```
- Add a select expression (after `mrr`, before `source`):
  ```sql
  rr.outlook                          AS outlook,
  ```
- LATERAL subquery (~line 1628):
  ```sql
  LEFT JOIN LATERAL (
      SELECT buy_trade, sell_trade, outlook
      FROM hist_rr
      WHERE tos_symbol = s.tos_symbol AND snapshot_date <= :d
      ORDER BY snapshot_date DESC LIMIT 1
  ) rr ON TRUE
  ```

`outlook` is NULL for BB-fallback symbols (no hist_rr row) — that is expected and
fine. No `reverse` scaling applies to `outlook`.

### A3. Apply + re-derive

`python -m db.init_db` then re-run the derive for the anchor date so `drv_rr.outlook`
is populated (e.g. `python -m etl.derive` path used elsewhere, or a single
`derive_rr` for D). Confirm populated (see verify §1).

---

## Part B — API: feed tiles from `drv_rr` + `drv_quote`

File: `api/routers/marketbar.py`.

### B1. Bar 1 — `GET /api/marketbar`

Currently range/outlook come from `hist_rr` (`rr_lookup`) and only `pct_change`
comes from `drv_quote`. Change so that:

- **Range + outlook** come from **`drv_rr`** (anchor `as_of_date`): `lrr`→`rr_buy`,
  `trr`→`rr_sell`, `outlook`→`rr_outlook`. Key by `tos_symbol`.
- **OHLC** comes from **`drv_quote`** (latest `as_of_date`): add to each item
  `open`, `high`, `low`, `close` (`open_price`, `high_price`, `low_price`,
  `last_price`). Reuse the existing `_METRIC_TO_RR_SYMBOL` / synthetic `rr_sym`
  mapping to look up `tos_symbol` in the `drv_quote` and `drv_rr` lookups.

Build two lookups keyed by `tos_symbol`:

```python
rr_lookup = {  # from drv_rr at anchor
    r['tos_symbol']: {'buy': r['lrr'], 'sell': r['trr'], 'outlook': r['outlook']}
    for r in s.execute(text(
        "SELECT tos_symbol, lrr, trr, outlook FROM drv_rr "
        "WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_rr)"
    )).mappings().all()
}
ohlc_lookup = {  # from drv_quote at latest
    r['tos_symbol']: {'o': r['open_price'], 'h': r['high_price'],
                      'l': r['low_price'], 'c': r['last_price'],
                      'pct': r['pct_change']}
    for r in s.execute(text(
        "SELECT tos_symbol, open_price, high_price, low_price, last_price, pct_change "
        "FROM drv_quote WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_quote)"
    )).mappings().all()
}
```

Then, when enriching each item (and each synthetic item), attach:
`rr_buy/rr_sell/rr_outlook` from `rr_lookup` and `open/high/low/close` (+ keep
`chg_pct` from `ohlc_lookup[...]['pct']` for synthetics) from `ohlc_lookup`. Cast
`Decimal`→`float` (or `None`). Omit OHLC keys when no `drv_quote` row exists.

### B2. Bar 2 — `GET /api/rr-bar` (and `/api/rr-bar-all`)

Rewrite `_RR_SQL` to source the **range + outlook from `drv_rr`** and **price/OHLC
from `drv_quote`** instead of `hist_rr`:

```sql
SELECT r.tos_symbol,
       r.lrr  AS buy_trade,
       r.trr  AS sell_trade,
       r.outlook,
       q.open_price, q.high_price, q.low_price,
       q.last_price AS q_price,
       q.pct_change AS pct
FROM drv_rr r
LEFT JOIN drv_quote q
       ON q.tos_symbol = r.tos_symbol
      AND q.as_of_date = (SELECT MAX(as_of_date) FROM drv_quote)
WHERE r.as_of_date = (SELECT MAX(as_of_date) FROM drv_rr)
ORDER BY r.tos_symbol
```

- `name`: `drv_rr` has no `name`. Use the label from `_RR_META`/`_RR_META_ALL`
  (already the display source) for the tooltip; if a separate `name` is still
  wanted, LEFT JOIN `hist_rr` only for `name`, otherwise fall back to `sym`.
- In `_build_rr_response`, set `bar_price = q_price` (drop the `rr_price` ratio
  sanity-check, or keep it using `(r.lrr+r.trr)/2` as the reference). Add
  `open/high/low/close` (= `q_price`) to each `item` dict.

---

## Part C — Frontend: new tile render

File: `web/market_bar.js`.

### C1. Candle builder (shared)

Add a helper that returns an SVG candle from open/high/low/close, **flat (square)
edges**, with **wicks** (upper = high→body-top, lower = body-bottom→low) and a
solid body for open→close. Color = the tile's direction color (see C4), NOT
outlook. Return `''` when any of o/h/l/c is null or `high<=low`.

```js
function candleSvg(o, h, l, c, color) {
  if ([o, h, l, c].some(v => v == null) || h <= l) return '';
  const VB = 48, top = 2, bot = 46, span = bot - top;           // 2px buffer top/bot
  const y = p => top + (h - p) / (h - l) * span;
  const bodyTop = y(Math.max(o, c)), bodyBot = y(Math.min(o, c));
  const bh = Math.max(1.5, bodyBot - bodyTop);                  // min 1.5px body
  return `<svg width="16" height="46" viewBox="0 0 16 ${VB}" class="mt-candle" aria-hidden="true">`
       + `<line x1="8" y1="${top.toFixed(1)}" x2="8" y2="${bodyTop.toFixed(1)}" stroke="${color}" stroke-width="1.5"/>`
       + `<line x1="8" y1="${bodyBot.toFixed(1)}" x2="8" y2="${bot}" stroke="${color}" stroke-width="1.5"/>`
       + `<rect x="2" y="${bodyTop.toFixed(1)}" width="12" height="${bh.toFixed(1)}" fill="${color}"/>`
       + `</svg>`;
}
```

### C2. Range bar with current-price tick

Extend the range bar to draw a **vertical current-price tick** (dark 2px marker)
at the current position, in addition to (or instead of) the existing fill. Current
price for bar 1 = `item.value`; bar 2 = `item.bar_price`. Position
`pct = clamp((cur - buy)/(sell - buy), 0, 1)`.

```js
function rangeBarTick(buy, sell, cur, color) {
  if (buy == null || sell == null || sell <= buy || cur == null) return '';
  const pct = Math.max(0, Math.min(1, (cur - buy) / (sell - buy)));
  const w = Math.round(pct * 100);
  return `<span class="mt-rb">`
       + `<span class="mt-rb-fill" style="width:${w}%;background:${color};"></span>`
       + `<span class="mt-rb-tick" style="left:${w}%;"></span>`
       + `</span>`;
}
```

### C3. Symbol button color (outlook)

```js
function outlookBg(outlook) {
  const ol = (outlook || '').toLowerCase();
  return ol === 'bullish' ? '#15803d'
       : ol === 'bearish' ? '#b91c1c'
       : ol === 'neutral' ? '#d97706'
       : '#64748b';   // no outlook → neutral gray
}
```

### C4. Direction color (keeps INVERTED for bar 1)

Reuse the existing `dirClass(chg_pct, metric_key)` → `mt-up | mt-down | mt-flat`
for the **% text color**, and derive the **candle hue** from the same direction so
VIX-type inverted metrics show a red candle when "bad". Map:
`mt-up → var(--act-buy-strong)/#15803d`, `mt-down → #b91c1c`, `mt-flat → #64748b`.

### C5. Tile markup

Replace `renderOnePair` / `mt-cell` (bar 1) and `buildRrHtml` chip (bar 2) output
with this tile (one per symbol — for bar 1 render the index and the vol as two
separate tiles rather than a combined pair):

```js
function tileHtml({label, outlook, pctHtml, dirCls, buy, sell, cur, o,h,l,c}) {
  const dir = dirCls === 'mt-up' ? '#15803d' : dirCls === 'mt-down' ? '#b91c1c' : '#64748b';
  return `<div class="mt-tile">`
    + `<div class="mt-tile-body">`
    +   `<div class="mt-tile-top">`
    +     `<span class="mt-sym" style="background:${outlookBg(outlook)};">${escHtml(label)}</span>`
    +     pctHtml
    +   `</div>`
    +   rangeBarTick(buy, sell, cur, dir)
    + `</div>`
    + `<div class="mt-tile-candle">${candleSvg(o,h,l,c,dir)}</div>`
    + `</div>`;
}
```

Keep tooltips (`title=`) with the same info as today (label, value, %, range,
outlook, source/as_of, stale). Keep the `Econ ▾` expander button at the end of
bar 1 unchanged. Keep the 60s refresh.

### C6. CSS — `web/styles.css`

Keep `.market-tape` / `.rr-tape` as horizontal scroll flex rows (unchanged
overflow/scrollbar-hiding). Make tiles fixed-width, non-shrinking:

```css
.mt-tile { flex: 0 0 auto; width: 180px; display: flex; align-items: stretch;
           background: var(--surface-1); border: 1px solid var(--border-1);
           border-radius: 7px; overflow: hidden; }
.mt-tile-body { flex: 1; min-width: 0; padding: 6px 8px; }
.mt-tile-top { display: flex; justify-content: space-between; align-items: center; }
.mt-sym { font-size: 12px; font-weight: 500; color: #fff; padding: 2px 8px; border-radius: 5px; }
.mt-rb { position: relative; display: block; height: 6px; margin-top: 7px;
         background: var(--track, #e5e7eb); border-radius: 3px; }
.mt-rb-fill { position: absolute; left: 0; top: 0; height: 100%; border-radius: 3px; opacity: .28; }
.mt-rb-tick { position: absolute; top: -2px; width: 2px; height: 10px;
              background: var(--text-1, #111); transform: translateX(-1px); }
.mt-tile-candle { width: 28px; display: flex; align-items: center; justify-content: center; }
```

Use existing theme variables where they exist (match the surrounding file's
`--surface-*`, `--border-*`, `--text-*`, `--act-buy-strong`, `--bear`). Verify the
tile reads in both light and dark themes.

---

## Files expected to change

- `db/baseline.sql` — `drv_rr.outlook` column + ALTER.
- `etl/derive.py` — `_derive_rr_impl` populates `outlook`.
- `api/routers/marketbar.py` — bar 1 + bar 2 read `drv_rr` (range/outlook) and
  `drv_quote` (OHLC); emit `open/high/low/close`.
- `web/market_bar.js` — candle builder, range-tick, symbol button, tile render.
- `web/styles.css` — `.mt-tile*` classes; keep tape scroll.
- `tests/test_agent_work_46.py` — new unit tests (see below).
- `tests/test_market_bar_ui.py` — update if it asserts old chip markup.

Do NOT rearrange the top-level layout. Do NOT commit (user commits from Windows).

---

## How to verify

1. **drv_rr.outlook populated** (DB, anchor `D = MAX(export_date) FROM hist_td`):
   ```sql
   SELECT count(*) FILTER (WHERE outlook IS NOT NULL) AS with_ol,
          count(*) AS total
   FROM drv_rr WHERE as_of_date = (SELECT MAX(as_of_date) FROM drv_rr);
   ```
   `with_ol` > 0 and equals the count of RR-sourced rows (`source='RR'`). Paste a
   few rows: `SELECT tos_symbol, lrr, trr, outlook, source FROM drv_rr
   WHERE as_of_date=(SELECT MAX(as_of_date) FROM drv_rr) AND source='RR' LIMIT 5;`

2. **API returns OHLC + drv_rr range** (app running):
   - `curl -s localhost:8000/api/marketbar | python -m json.tool` → at least one
     item has non-null `open`, `high`, `low`, `close`, `rr_buy`, `rr_sell`,
     `rr_outlook`.
   - `curl -s localhost:8000/api/rr-bar | python -m json.tool` → items carry
     `open/high/low/close`, `buy`, `sell`, `outlook`, `bar_price`.

3. **JS sane**: `node --check web/market_bar.js`.

4. **Visual** on `/actionable` (bars mount there): hard-refresh, console clean.
   Confirm both bars are still single-row horizontal scrollers; each tile shows a
   colored symbol button, a colored %, a range bar with a current-price tick, and
   a candle on the right with wicks + flat body. Spot-check a `Bullish` symbol
   (green button), a `Bearish` (red), and `VIX` (% should be red when VIX rises —
   INVERTED preserved). Candle color matches the % direction.

5. **Idempotency**: run the derive for D twice; `drv_rr` row count + `outlook`
   values identical (paste a diff or matching counts).

6. **Regression**: `pytest tests/ -q --tb=no` — report new failures vs the
   pre-existing baseline (currently ~89). `tests/test_agent_work_46.py` covers:
   - `candleSvg` math is not unit-tested (JS); instead unit-test the Python:
     `/api/marketbar` and `/api/rr-bar` response include the new keys for a seeded
     symbol with a `drv_quote` + `drv_rr` row (use the existing test DB fixtures
     in `tests/test_market_bar_ui.py` as a pattern).
   - `_derive_rr_impl` writes `outlook` from `hist_rr` (seed a hist_rr row with
     outlook='Bullish' → drv_rr row has outlook='Bullish'); BB-fallback symbol →
     `outlook IS NULL`.

## Notes / decisions

- Candle hue follows the tile's **direction** (chg_pct, with INVERTED applied),
  not the outlook — so the symbol button (outlook) and candle (today's move) can
  legitimately differ in color.
- Bar 1 renders index and its vol (e.g. SPX / VIX) as **two separate tiles**, not
  a combined pair, since each now needs its own range bar + candle.
- Tiles missing `drv_quote` OHLC simply omit the candle; tiles missing a range
  omit the range bar — neither should break the row.
- No schema changes beyond `drv_rr.outlook`. Do not touch `derive_source_standing`
  or `drv_outlooks` (they still read outlook from `hist_rr`/`drv_source_standing`).
