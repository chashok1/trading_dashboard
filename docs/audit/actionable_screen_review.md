# Actionable Screen Review — 2026-07-03

Full feature/function/design review of `/actionable`. Sources read:
`web/actionable.html`, `web/actionable.js` (4,371 lines), `web/hedgeye_panel.js`,
`web/macro_band.js`, `web/warning_badge.js`, `api/routers/dash.py`
(actionable endpoints), `api/routers/hedgeye.py` (route map), `docs/actionable_logic.md`.
All findings verified against file:line — nothing here is speculative.

Legend: **P1** = bug / broken behavior, fix first · **P2** = high-value improvement ·
**P3** = polish / cleanup.

---

## 1. What the screen does well (keep as-is)

- **Decision hierarchy is coherent**: Sources (strategic gate) → Technical (tactical)
  → Final Call, computed server-side (D6) with a documented client fallback. Good design.
- **Explainability is exceptional**: every cell has a "why" — source popovers, RR decision
  path (QF/QK/QO), MacroNet formula breakdown, atomic-rule trace, current-vs-prev record
  comparison. Few trading tools do this.
- **Forensic audit trail**: `POST /{symbol}/action` snapshots the full drv_actionable row
  plus raw source records into `user_action_log`. Excellent for the feedback loop.
- **Freshness honesty**: stale banner + re-derive button, EOD-missing banner, IDY intraday
  tag, anchor-stale date highlight, auto-refresh when new TL/Y data lands.
- **Filter architecture**: `baseRows` vs `rows` split so chip counts stay accurate under
  every other filter. Clean.

---

## 2. Bugs (P1)

| # | Bug | Evidence | Fix |
|---|-----|----------|-----|
| B1 | **Inline / bulk / focus Snooze does not stick.** `inlineAction(sym,'SNOOZED')` posts `user_action=SNOOZED` with **no `snooze_until`** (actionable.js:2961–2984). Server hides SNOOZED rows only when `snooze_until >= date` (dash.py:1114–1116); client `matchesBaseFilters` only hides DONE/SKIPPED/OVERRIDDEN (actionable.js:1187–1188). Row reappears on next reload. | actionable.js:2965–2971, 3896, 3935; dash.py:1112–1116 | Inline snooze should default `snooze_until` (e.g. +1 day or next business day), or treat date-less SNOOZED as "hide for this as_of_date" server-side. |
| B2 | **Atomic-popover × button is dead.** Close handler targets non-existent `#detailPop`: `$('closePop').addEventListener('click', () => $('detailPop')?.classList.remove('open'))`. Should call `closeAtomicPopover()`. | actionable.js:4022 | One-line fix. |
| B3 | **Date-snoozed rows can't be un-snoozed.** `DELETE /{symbol}/action` removes only `user_action='SKIPPED'` rows (dash.py:1492–1495). A modal snooze-until row has no UI path back. | dash.py:1481–1496 | Extend DELETE to clear SKIPPED + SNOOZED (or add a param). |
| B4 | **CSV `Metric` column is always empty.** Exports `r._metric` (actionable.js:3072) but `_metric` is never assigned anywhere; the `'_metric'` sort special-case (line 2796) is equally dead — no column carries `data-key="_metric"`. | actionable.js:3072, 2796 | Remove, or recompute from `_rowMetric()` (currently dead too). |
| B5 | **30-second auto-refresh destroys working state.** `checkForNewData` → `loadActionable()` resets sort to default (line 1107) and `applyClientFilter()` clears bulk selection (line 1244) — mid-triage, without warning. | actionable.js:1409–1420, 1107, 1244 | Preserve sort/selection across auto-reload, or show a "New data — refresh" toast instead of silently reloading. |
| B6 | **Focus mode shows a different action than the Act button logs.** Card badge = `consolidated_action` (`actionLabel`, line 3017); the Done path logs the Final Call code (`fcActCode`). User confirms "BUY SOME" while the log records `BM`, or worse, sees the Sources action when Final Call disagrees. | actionable.js:3006–3032 vs 2869, 2918 | Render the Final Call badge in the focus card (grid's ACTION column is already FC-driven). |

---

## 3. Dead code & orphaned features (P3 cleanup, low risk)

All confirmed defined-but-never-called in `web/actionable.js` (single occurrence = definition only):

- `_srcSubLineHtml`, `_renderOtherSources`, `_convictionHtml` (conviction **badge** never rendered though the conviction **filter** works), `_sourceWeightDelta`, `_rowMetric`, `_fcStrengthToAction`, `_outlookChip`, `_assetClass`.
- `.btn-suppress` click delegation (line 3911–3914) — no such button is rendered anywhere.
- **Top-N collapse (Pass 2)**: `state.showAll`, `TOP_N = 15`, `.show-all-bar` CSS all exist; `renderGrid` ignores them (`const visibleRows = state.rows`, line 2826). Either finish the feature (valuable — see U2) or delete.
- **Filter persistence is half-removed**: `saveFiltersToStorage` writes `act_filters_v3` on every filter change; `loadFiltersFromStorage` is an explicit no-op (lines 1546–1567). Dead writes — pick one direction.
- `setupRRActionCol` wiring: a nested `document.addEventListener('DOMContentLoaded', …)` inside the already-fired DOMContentLoaded handler never runs (line 4044) — delete.
- `web/macro_band.js` + `web/cockpit.html` are orphaned: only cockpit.html loads macro_band.js and `/cockpit` 301-redirects to `/actionable`. Note `macro_band.js` also targets `#macroBand` — the **same element ID** the quad regime band uses on actionable.html. If anyone ever re-adds the script, the FRED tiles will clobber the quad band. Rename one ID or delete the orphans.

---

## 4. Doc drift (P2 — violates the "docs stay current" convention)

`docs/actionable_logic.md` §Display describes a grid that no longer exists:

- Claims columns **Metric, Snapshot, Other Sources** and grid order "Metric, Symbol, Action, AMT$, Source, Reason, Snapshot, Other Sources, sizing" — actual grid is: checkbox · H · POS$ · AMT$ · %CHG · Symbol · ACTION (Final Call) · MACRO · CALC · Sources · Technical · Vlm · IV · MACD · MACDH · RSI · Rules(edge) · P(↑20d) · Agree · Act.
- Claims "the first grid column is a per-row Snooze button" — first column is the bulk checkbox; snooze lives in the Act column.
- The per-source "Way 1 / Way 2" Metric sort no longer exists.
- `CLAUDE.md` Lookup row says `macro_band.js` is "loaded by web/actionable.html" — it is not (cockpit.html only).

The doc's Stage-1/Stage-2 derive sections and RR-analysis data flow still look accurate; only the Display section needs a rewrite.

---

## 5. Usability & screen design (P2 unless noted)

### 5.1 Information density / layout
- **U1 — Column overload.** 20 columns, `Rules (edge)` hard-coded to 720px width forces
  horizontal scroll and dwarfs the decision columns. Recommend: cap Rules with
  `max-width` + ellipsis + "+n more" expander, and add a **user column show/hide menu**
  (persist in localStorage). Evaluation-only columns (CALC, P(↑20d), Agree) are prime
  candidates to default-hidden — they're model diagnostics, not decisions.
- **U2 — No top-N focus by default.** The default sort is priority DESC, so the top 10–15
  rows are the day's real work; finishing the dormant Top-N collapse ("show 15 · Show all
  N") would make the default view match the actual workflow.
- **U3 — Legibility.** Extensive 8–9px text (source reasons, sub-lines, hedgeye cards,
  macro dots at 7px). On a 1080p screen this is squint territory. Bump floors to 10px and
  let cells grow a pixel; the grid already scrolls.
- **U4 — 'H' column** occupies a header slot at all times but is only meaningful when
  Show Hidden is on. Render it conditionally.

### 5.2 Vocabulary & discoverability
- **U5 — Three action vocabularies on one row**: chips say SELL ALL/BUY SOME, ACTION badge
  says SA/BS/BM codes, Sources cells show glyph icons, MACRO shows SA/STM/BS/BM again,
  CALC likewise. A user needs the mapping in their head. Add a **legend popover** ("?"
  icon in the toolbar) documenting action codes, chip meanings, conviction levels, edge
  badges, IDY tag, IV glyph, RVOL dot. Cheap, high leverage.
- **U6 — Unlabeled segmented control** `Any | Multi | Proven` gives no hint it's a
  conviction filter (title attr only). Prefix a tiny "Conv:" label or fold into the legend.
- **U7 — Icon-only toggles** (eye, briefcase, checkbox-square, TV, econ, side-panel)
  rely on hover tips with 0.4s delay; state polarity ("Active Only → Show Hidden") reads
  ambiguously. Consider active-state pill styling with a 1-word label on the two most
  important toggles (Hidden, Positions).

### 5.3 Interaction
- **U8 — Keyboard support.** Escape closes focus mode but **not** the drilldown modal;
  focus mode has no keys (Enter=Done, S=Skip, Z=Snooze, ←/→=prev/next would make it an
  actual rapid-triage tool); grid has no keyboard row navigation. Focus mode also lacks a
  **Back/previous** button — Next only.
- **U9 — Symbol search re-filters and re-renders the whole grid per keystroke**
  (input event → applyClientFilter → full renderGrid + tape). Add ~150ms debounce.
- **U10 — Copy Symbols gives no success feedback** (errors only to console). One
  `showStatus('Copied N symbols')`.
- **U11 — Empty state** is one string for every cause. Distinguish "no rows match these
  filters" (offer Clear Filters button inline) from "everything acted — done for today"
  (positive reinforcement; you have the data via baseRows vs allRows).
- **U12 — Six coexisting tooltip systems**: native `title`, `#sourcePop`, `actDetailTip`,
  `rrDetailTip`, `#symTilePop`, `mtTip`. Behavior (delay, dismissal, positioning) differs
  per column. Consolidate on the `_showDataPop` pattern; long-term this is also the main
  source of stuck-tooltip edge cases.
- **U13 — MACRO column sorts alphabetically** (`data-type="str"` on `macro_value`:
  BM < BS < HOLD < SA < STM), which is meaningless. Sort on `macronet` numeric.

### 5.4 Hedgeye panel
- **U14 — Fragile fixed-pixel layout.** Cards use hand-tuned bases (`flex:0 0 340px`,
  `flex:0 0 506px` with a comment admitting the 506px is reverse-engineered from an
  image's natural width, `calc(15ch + 20px)` etc.) and fixed 125px/105px row heights with
  internal scroll. Any new card or narrower window breaks alignment. Convert the two rows
  to CSS grid with `minmax()` tracks; let row height fit content up to a max.
- **U15 — Toggle icon desync.** `#hePanelToggle` ships with `icon-on` hard-coded in HTML;
  `render()` reads the persisted collapsed state for the body but never syncs the button's
  icon class on initial load — icon can point the wrong way until first click
  (hedgeye_panel.js:395, 515–524; actionable.html:716).
- The panel is strong content-wise (received-time stamps, rich tips, ext-links ↗). Main
  ask is layout robustness.

### 5.5 Side panel / bands
- Side panel is `position:fixed` overlaying at 260px with body padding compensation —
  works, but on narrower windows it eats a third of the grid. Consider auto-unpin below a
  width threshold.
- Quad band + macro distribution + breadth + action split in one 10px strip is dense but
  genuinely useful; the `data-quadbandpop` popovers carry the depth. Fine as-is.

---

## 6. Functionality improvements

- **F1 (P2) — Bulk action endpoint.** `bulkAction` loops `await inlineAction(sym)` —
  N sequential POSTs, each re-running the full forensic snapshot (per-source hist_* reads).
  20 symbols ≈ 20× round-trips. Add `POST /api/actionable/bulk-action {symbols:[…]}`.
- **F2 (P2) — `GET /api/actionable` payload & compute.** The endpoint runs the full
  MacroNet Python computation (`_compute_macro`) per row per request and ships
  `macro_detail` + `macro_howto` + `monthly_scores_json` for **every** row — and it's
  re-fetched on every 30s data poll. The popover pattern already used for source-data
  (lazy `GET /api/actionable/source-data` on hover) fits perfectly: keep
  `macro_value/conf/turn` + the three nets in the row payload, lazy-load the detail.
- **F3 (P2) — Snooze semantics unification** (pairs with B1/B3): one definition —
  SKIPPED = gone for this snapshot date; SNOOZED = gone until `snooze_until` (default
  next business day when not supplied); both un-doable from the grid when Show Hidden is on.
- **F4 (P3) — CSV export refresh.** Columns still export `Trig`, dead `Metric`, and omit
  everything added since: Final Call, confidence, MACRO, CALC, P(↑20d), Agree, stop_level,
  RVOL, IV, MACD/MACDH, RSI. Mirror the visible grid (respect column visibility once U1
  lands).
- **F5 (P3) — Conviction 'proven' threshold** (`edge_20d > 0.5`) is hard-coded
  client-side (actionable.js:1821). Move to `ref_settings` alongside the macro thresholds.
- **F6 (P3) — Stop level surfacing.** Stop shows as 9px sub-text under AMT$. Given it's
  the risk-management number, consider: highlight the row (or the stop text red) when
  `last_price < stop_level` — the comparison is already client-side computable.
- **F7 (P3) — `_computePriority` scale mixing.** Server `priority_rank` = seq×1e6+amt is
  re-multiplied ×1e6 client-side and mixed with client fallback seq×1e12+amt. For rows
  with amt ≥ $1M the tiers can cross between server- and client-ranked rows in one list.
  Normalize to one formula (drop the client fallback once all dates are post-TASK_53).

---

## 7. Suggested execution order

| Batch | Items | Effort |
|---|---|---|
| 1. Bug sweep | B1, B2, B3, B4, B6 (+ dead-code deletes §3) | Small, mostly one-liners; one dev task |
| 2. State preservation | B5 (auto-refresh keeps sort/selection or toast) + U9 debounce | Small |
| 3. Doc sync | §4 rewrite of actionable_logic.md Display + CLAUDE.md lookup row fix | Small |
| 4. Density & legend | U1 column manager, U2 top-N finish, U5 legend popover, U13 macro sort | Medium |
| 5. API efficiency | F1 bulk endpoint, F2 lazy macro detail | Medium |
| 6. Focus mode v2 | U8 keyboard + prev, B6 FC badge | Small-medium |
| 7. Hedgeye layout | U14 grid conversion, U15 icon sync | Medium |

Each batch is independently shippable; 1–3 are safe before market Monday.
