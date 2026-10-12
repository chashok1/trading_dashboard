# TASK_149 — Area Driver Rules (area verdicts + linked-stock warnings)

**Author:** Cowork, 2026-10-11. **Owner:** Developer agent.
**Design of record:** `docs/mockups/area_driver_rules_design.html` (sections 1–9).
Numbers in it are illustrative. **The outcome is fixed; the implementation is
yours** — you have the live DB and code. Where the design and live code/data
disagree, trust live and note it in `DEV_HANDOFF.md`.

## Goal (user's words, condensed)
For each market **area** (not individual stocks) — Gold, Silver, Copper/commodities,
Oil, Bitcoin, Large caps, Small caps, Tech, Bonds, Credit, Intl/EM (+ Precious
metals as a roll-up) — read the area's **drivers** (e.g. Dollar + rates for gold) and
give one verdict: ▼ Headwind · ▲ Tailwind · ◆ Turning · ⚠ Stretched · ○ Unclear ·
(silent when nothing fires). Then flag the user's **holdings and buy candidates** in
that area through the **existing Actionable Action-icon warning list**.

## What the user sees (fixed)
1. **Dashboard `/`:** compact area tiles (verdict glyph + colour; `$ held` only on
   Headwind/Stretched tiles), quiet areas collapsed into "+N quiet", a
   "$X headwind" total. Click a tile → its driver legs (✓/✗), read text, linked stocks.
   **Placement is your call.** TASK_148 found the Regime band is only ~206px wide in
   the right rail. Put the tiles where they read at a glance without growing the page
   much: as a compact grid in that rail, or in the main column. Note the choice.
2. **Existing macro rails:** a verdict pill. One area per rail → header pill
   (Energy=Oil, Crypto=Bitcoin, Rates & Duration=Bonds, Credit=Credit,
   Country ETFs=Intl/EM). Rails holding several areas → pill on the **driving row**:
   Precious Metals (Gold row, Silver row + header roll-up "2 ▼"), Major Markets
   (SPX=Large caps, $COMP=Tech, RUT=Small caps), Industrial & Ag (/HG row only).
   **Do not split or rearrange rails.**
3. **Actionable:** one generic line per flagged area in `_signalReasons`
   (Headwind/Stretched → Caution on buys; on sells it swaps to Confirm, like the
   existing sector-Bear warning; Tailwind → Confirm on buys), plus a toolbar filter
   chip "In headwind area (N)".

## Rules
Use the catalog in design §3 (12 areas: driver, gate, headwind / tailwind /
turning-or-stretched conditions). Known facts from TASK_148 and Cowork's checks:
- Outlook values are **mixed case** (BULLISH/Bullish/BEARISH/NEUTRAL; ii also
  Long/Short). Compare case-insensitively everywhere.
- `macronet > 0` = tailwind (only if you add the optional quad confirm leg; no rule needs it).
- Real yield = `DGS10 − T10YIE` (both in `hist_macro`). HY spread = `BAMLH0A0HYM2`.
- Dollar-correlation gate: `drv_usd_correlation.w30`, asset keys gold / brent /
  crb / bitcoin / spx. **Silver has none** → add one `ref_corr_asset` seed row
  (yfinance `SI=F`); until it has data, Silver borrows gold's gate.
- Bitcoin's dollar correlation sign varies → gate on |corr| ≥ 0.3.
- Vol zones (investable/chop/elevated) are computed **only inside**
  `api/routers/macro_areas.py` today. Extract one shared helper so the derive, the
  rails and the tiles can never disagree.
- Stretched uses the existing 0.85 cut-off (`macro_area_hot_pct`). TASK_148 saw
  rr_pos clamp at 100% above TRR; above TRR counts as stretched.
- The 10Y "5% level" comes from `ref_level_watch` (TNX ×10 scale, as TASK_148 handled).

## Architecture (fixed direction, details yours)
**Extend, don't add a fifth silo** (design §5–6):
- Generalise the cross-asset engine: `ref_cross_asset_rule` gains area_key, verdict,
  read_text, severity, mode ('advisory' | 'actionable'); target_symbol nullable.
  Legs gain the check types the catalog needs (flip, delta over N days, derived
  series, corr gate, gauge fired, vol zone, level). New small refs as needed
  (`ref_driver_area` with parent for roll-ups; derived-series definitions).
- **The existing `BONDS_USD_TRR_GOLD_LRR` must behave exactly as today**
  (mode='actionable', still folded into Actionable). Tag it area 'gold'.
- **All new rules are mode='advisory'** and must **never** reach
  `consolidated_action` / `trig_action`. Make sure `derive_actionable.py`'s
  cross-asset fold ignores advisory rules. This is the only allowed change there.
- Exposure (which stocks): area members (`ref_macro_area`) → asset class/sector/style
  via `ref_gauge_transmission` keyed by area → `ref_symbol_theme` → manual override
  (`ref_gauge_transmission` axis 'symbol'). `inverted` flips the verdict (PFIX etc.).
- New computed tables (or equivalent): area verdict per date, and linked-stock flags
  per date. **Each ships with its `ref_freshness_contract` row and runs inside
  `derive_all`** (TASK_142 rule). `tos_symbol` everywhere (convention 15).
- Stale or missing inputs → area Unclear + one `meta_warning` (toolbar badge).
  Market verdicts themselves do **not** go to the toolbar badge.
- Read text describes co-movement only ("Dollar ▲ and 10Y ▲ while Gold ▼"), never causes.

## Decisions (Cowork's recommendations, adopted)
- All 12 areas in this task. Ag and Cannabis are excluded (no clear driver).
- Warnings go to holdings **and** buy candidates. Everything else stays silent.
- "$ headwind" counts Headwind areas only. Inverted holdings are not counted.
- 2-day confirmation before a verdict flips: build the `ref_settings` switch, default **off**.
- A "new" dot for 3 days after a verdict changes.
- **Out of scope:** scorecard / validation views, email digest, moving the old
  hard-coded JS warnings into rules (future task).

## Constraints
Schema in `db/baseline.sql` (+ `migrate_*.py` for DO blocks) · seeds in `db/seeds_*.sql`
· SQL ≤ 965 bytes · reuse existing endpoints/helpers where they already return what's
needed · CVD-safe `--mr-*` colours, and every state also has a glyph · no commits or pushes.

## Testing — NONE this round (user's instruction)
No tester round, no new tests, no `pytest` run. Sanity only: `node --check` on
changed JS, `ast.parse` on changed Python, `/` and `/actionable` load with no console
errors, one `curl` of each new endpoint. Record the outputs in the handoff.

## Files (your call; likely)
`db/baseline.sql`, `db/seeds_*.sql`, `etl/derive_cross_asset_rules.py`, `etl/derive.py`,
`etl/derive_actionable.py` (advisory filter only), `api/routers/cockpit.py`,
`api/routers/macro_areas.py` (zone helper), `api/routers/dash.py` (driver flags on rows),
`web/index.html`, `web/macro_areas.js`, `web/actionable.js`, `web/actionable.html`,
`web/styles.css`, a new `docs/area_driver_rules_logic.md`, one `CLAUDE.md` Lookup row,
`docs/migrations.md`, `DEV_HANDOFF.md`.
