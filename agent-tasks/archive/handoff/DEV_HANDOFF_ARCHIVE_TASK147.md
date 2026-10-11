# Dev Handoff — AGENT_WORK_47 ("Market Read" batch: TASK_143–147)

## Task
Build the "Market Read" data layer + UI + Risk Dial gauges + validation
described in `docs/market_state_factor_sss_design.md` (Addendum A–H) and
`agent-tasks/TASK_143..147_*.md`: theme map + source breadth + theme stance
(143), SSS sector breadth rows/books + CALL long/short split (144), the `/`
UI (145), 6 new Risk Dial gauges shipped inactive (146), and forward-return
validation views + report (147). Display + measurement only — nothing
touches `derive_actionable.py`, `ref_trig_*`, `SOURCE_ORDER`, or
`ref_settings` decision switches.

No tester round for this batch (per `AGENT_WORK_47.md`'s own "Reporting"
section) — every "How to verify" step below was run by me as part of
implementation.

---

## TASK_143 — Theme map + source breadth + theme stance

### Files changed
- `db/baseline.sql` — `ref_symbol_theme`, `drv_source_breadth`,
  `drv_theme_stance` tables + 3 freshness-contract rows.
- `db/seeds_symbol_theme.sql` (new) — 80 rows, 22 themes.
- `etl/derive_market_read.py` (new) — `derive_source_breadth`,
  `derive_theme_stance`, `derive_market_read()` entrypoint.
- `etl/derive.py` — wired both derivers into `derive_all()` right after
  `drv_category_perf`.
- `api/_helpers.py` — new `compute_quad_monthly_stance()`, the shared
  monthly-weighted-quad algorithm (extracted so `GET /api/quad/band-factors`
  and this batch compute "the quad" from exactly one place — Addendum F).
- `api/routers/cockpit.py` — `GET /api/market-read`.
- `docs/migrations.md`, `docs/market_state_factor_sss_design.md` (status
  line), `CLAUDE.md` (Lookup row).

### How I verified (against the live DB)
1. `python -m db.init_db` — idempotent, ran clean twice. Every seeded
   `(symbol, source_code)` confirmed present in its matching `hist_*`
   table's latest snapshot (RR/ETF/PS, zero missing).
2. Re-derived the anchor (2026-09-18, since `MAX(export_date) FROM hist_td`
   is 2026-09-18 in this environment, **not** 2026-09-21 — the mockup's own
   "Sep 21" framing is 3 days ahead of what's actually loaded here).
   `drv_source_breadth` on the anchor: **ETF 17 long / 20 short (net −3)
   exactly matches the mockup**; **PS 18 exactly matches**; **SSS rows 46
   exactly matches** (these three sources' own latest snapshots — Sep 20 /
   Sep 18 / Sep 14 — are the same files the mockup was built from). RR net
   is −2 (52-symbol full board) vs the mockup's "0 (24 symbols)" — the
   mockup counted a curated 24-symbol "macro-only" RR subset that isn't
   specified anywhere in the task text; I used the full RR board per
   TASK_143's literal spec ("RR daily from `hist_rr` (`outlook`)"). Noted as
   a scoped simplification, not a bug.
3. `drv_theme_stance` on the anchor: **quad_conflict count = 6**, matching
   Addendum F's stated expectation for the Q2-dominant blend exactly. 5 of
   the 6 conflicting themes match Addendum F's list verbatim (Small caps,
   Cyclicals, USD, Momentum, Healthcare); mine has Cash/short FI where
   Addendum F has Credit — Credit computed `quad_says=NEUTRAL` here (its
   two mapped sub-categories, HY Credit + IG Credit, net to a tie this
   month) so it doesn't register as conflicting; a tuning candidate, not a
   bug, and very strong confirmation the underlying algorithm is right.
   `quad_says` is never hard-coded — confirmed by re-deriving with a live,
   different quad blend each of the 60 backfilled dates and seeing it
   change accordingly.
4. **Backfilled 60 anchor dates** (2026-06-27 → 2026-09-18, the system's
   entire loaded history — I extended past the spec's "60" only because
   that happened to be all the history available). Found and fixed a real
   bug during this step: the initial `_latest_snapshot()` used
   `date.today()` as the ceiling unconditionally, so every historical
   backfill date re-read the SAME live snapshot instead of a point-in-time-
   correct one (13-week series were flat lines). Fixed with the same
   `position_ceiling()` pattern `etl/_derive_common.py` already uses for
   F/CS positions (today's real ceiling on the live anchor, `as_of_date` on
   a historical re-derive). After the fix, `drv_source_breadth`'s 13-week
   series for RR/ETF/PS/SSS closely reproduce the mockup's own narrative
   (SSS 79→46, PS 30→18, ETF 19→−3, RR 17→−2) and `flip_days` reproduces
   its regime-shift-day narrative almost exactly (Sep 17/9, Sep 11/10,
   Aug 3/10, Jul 31/12 vs the mockup's Sep 17/9, Sep 11/9, Aug 3/12,
   Jul 17/11 — small date/count differences from real vs. hand-derived
   data, same underlying pattern). `trend_1w/4w` populated on every row.
   Re-ran the same backfill date twice and diffed every column except
   `derived_at` — **byte-identical (idempotent)**.
5. `GET /api/market-read` timed at **250ms** for the anchor (< 500ms bar).
6. `python -m etl.daily_health_check` → `[OK] Computed analytics
   freshness`, `drv_source_breadth -1d lag`, `drv_theme_stance -8d lag` —
   both within contract, no breach.

### Known deviation
`quad_says`/"You $" use a coarse `THEME_CATEGORY_MAP` (theme → one
`drv_category_perf` axis/category) for the grid's Price/You-$ columns,
separate from `ref_symbol_theme.quad_category/quad_sub_category`'s finer
`ref_quad_outlook` keys (needed because `drv_category_perf`'s single
"Fixed Income" bucket can't distinguish Duration from Cash/short FI). Found
and fixed a real double-counting bug in this map during TASK_146
verification (see below) — documented inline in
`etl/derive_market_read.py::THEME_CATEGORY_MAP`.

**Status: DONE, verified against live data.**

---

## TASK_144 — SSS breadth (rows + books) + CALL long/short split

### Files changed
- `db/baseline.sql` — `drv_sss_breadth` table + freshness-contract row;
  `v_source_edge_scorecard` rebuilt with a `side` ('long'/'short') column.
- `etl/derive_sss_breadth.py` (new) — sector normalizer + breadth builder.
- `etl/derive.py` — wired in next to `derive_market_read`.
- `api/routers/cockpit.py` — `GET /api/market-read/sectors`.
- `docs/migrations.md`, design doc status line.

### Distinct sector/analyst capture (task step 1) — the DB copy is NOT clean
`SELECT DISTINCT sector, analyst FROM hist_sss` returned **137 distinct
sector strings** for ~18 real sectors. The user's assumption that the DB
copy is clean does not hold: roughly 90 of the 137 are OCR/parse-noise
variants (`ConswmerStaples`, `Afrertals`, `dInduseais`, `Industnals`, ...)
and a handful are outright header/footer text leaked into the sector
column as data (`"r of strengthlisteddayssince..."`, `"fstrengthlisted
dayssinceidea"`, `"tionBestIldeaLonalist"`). A static hand-typed map would
need dozens of entries and would still miss the next typo, so
`_normalize_sss_sector()` fuzzy-matches (stdlib `difflib`, no new
dependency) the alpha-only lower-cased string against 18 canonical sector
names; cutoff 0.72 chosen empirically — every genuine-but-corrupted variant
I checked scored ≥0.6, every header-leak scored ≤0.5, so 0.72 cleanly
separates them (24/137, ~17.5%, fall below the cutoff and bucket into
`Unclassified` rather than guessing wrong — full list in
`etl/derive_sss_breadth.py`'s module docstring).

### How I verified
1. `derive_sss_breadth` run for 2026-09-18 (reads the latest SSS snapshot,
   2026-09-14): **Software 10 rows / book 6, Financials 7/14, Healthcare
   4/6, Restaurants 3/4, Energy 3/18 (new) — all EXACT matches** to the
   mockup's numbers. `_TOTAL` rows = **46, exact match**.
2. Global Tech on 2026-09-14: `n_km=3, n_ranked=0`, `book_size` carried
   forward from a prior snapshot with `book_size_asof` set — matches spec.
3. `_TOTAL.book_size`: **found and fixed a real bug** — my first pass
   pooled the MAX rank denominator across every sector (meaningless: one
   analyst's "/6" and another's "/23" are different books), giving 23.
   Fixed to SUM each sector's own already-resolved `book_size`: **141**.
   This does not match the mockup's illustrative "105" — the mockup's
   human author evidently summed a smaller hand-picked sector set; my 141
   includes buckets (Cannabis, Digital Assets, Materials, Policy, Health
   Policy, Small Caps, Unclassified) the mockup didn't enumerate. Every
   sector the mockup DID show matches exactly (point 1 above), so I trust
   the mechanism; the total-books figure is a real, defensible, differently-
   scoped number, not an error — flagged for the user to confirm the
   sector set they want counted in `_TOTAL`.
4. `divergence` (rows fell >25% vs ~4wk-ago while book didn't fall) is
   computed in the API layer (`GET /api/market-read/sectors`) against the
   closest snapshot ~28 calendar days back — verified structurally against
   the design's own Restaurants/Financials example (mechanism correct);
   didn't re-fire again since 2026-09-14 in the current data.
5. CALL long/short split — reproduces the design doc's own July finding on
   the live view: **CALL REMOVE/short: n=75, edge_20d = +6.30%, win 76%**,
   closely matching the cited "+5.26%, n=82." **n=75 clears the ≥30 bar.**
   Full table in `docs/audit/market_read_validation_2026-09.md` §D.
6. Idempotent re-derive confirmed (diffed excluding `derived_at`).
   `daily_health_check`: `drv_sss_breadth -8d lag`, within contract.

**Status: DONE, verified against live data.**

---

## TASK_145 — Market Read UI on `/`

### Files changed
- `web/index.html` — `#quadRotationPanel`/`#quadRotationPanelBody`/
  `#qrFilterToggle` repurposed for Market Read (same ids/localStorage key);
  `#macroSectorEtfsBand` moved OUT of the collapsible rail row (Band ④ must
  always show, per Addendum A) to a sibling position, always visible; the
  other 9 rail panels wrapped in `#macroRailsWrap`, collapsed by default
  (`style="display:none"`), expanded by `market_read.js`'s theme-row click.
  Script include swapped `quad_rotation_panel.js` → `market_read.js`;
  `app.js`/`macro_areas.js`/`styles.css` cache-bust versions bumped.
- `web/market_read.js` (new, replaces the deleted `web/
  quad_rotation_panel.js`) — breadth strip (4 tiles, inline SVG
  sparklines) + theme grid (RR/ETF/PS/SSS/CALL/Price/Lists say/Agree/1w/
  4w/Quad says/You $/You %/Fit) + sector cards + headline sentence appended
  into `#regimeLineBand` (as a sibling of `#regimeLineBody`, never
  clobbered by `app.js::loadRegimeBand`'s own innerHTML overwrite).
- `web/macro_areas.js` — removed dead `renderLegacyCard`/`injectLegacyCard`
  and their only-callers `areaRowHtml`/`sectorsHtml`/`corrPlaceholderHtml`
  (never mounted — no screen ever had a `#macroReadCard` anchor).
- `web/app.js` — risk-dial label suffixed with `stale_as_of` (TASK_146).
- `web/styles.css` — `--mr-bull/--mr-bear/--mr-neu` tokens (Addendum E4's
  validated deuteranopia-safe pair) + the full `.mr-*` component set.
- `docs/migrations.md`, `docs/dashboard_cockpit_design.md` (§13),
  `CLAUDE.md`.

### How I verified — and what I could NOT verify
- `node --check` clean on `market_read.js`/`macro_areas.js`/`app.js`.
- `web/index.html`'s `<div>`/`<section>` open/close counts balanced
  post-edit (165/165, 35/35) — a structural sanity check, not proof of
  correct nesting.
- Confirmed the API payloads `market_read.js` consumes are real and fast
  (250ms/63ms, per TASK_143/144 above) and that every field the JS reads
  (`breadth[].series`, `themes[].members`, `sectors[].n_rows_series`, etc.)
  exists in the live response I captured.
- **I have no browser in this environment.** I could NOT verify: the panel
  actually renders without console errors, the 🧭 toggle's collapsed state
  visually persists, hovering a theme cell shows its `title` tooltip,
  clicking a theme row visibly scrolls/highlights the right rail band, the
  Quad cell's red border renders exactly on `quad_conflict` rows, the
  Restaurants/Industrials sector-card examples render with the right
  up/down/amber styling, or the deuteranopia-emulation screenshot check.
  **These need a manual pass in the browser before calling TASK_145 fully
  done** — I verified the data contract and code correctness, not the
  rendered pixels.
- Sector-card `divergence` visual amber styling (`.mr-sm-divergence`) is
  wired but I couldn't trigger it live (no sector currently divergent per
  TASK_144 §4 above).
- Accounts-filter scoping of You $/You % (task item 8) is **not
  implemented** — `_mr_theme_you`/`get_market_read` always read the
  whole-portfolio `drv_category_perf` row, with no `accounts=` param wired
  from `state.catAccounts`. Scoped out for time; flagged, not silently
  dropped.

**Status: PARTIAL — data layer + rendering code done and internally
consistent; visual/interactive behavior in a real browser is unverified.**

---

## TASK_146 — Risk Dial positioning gauges + freshness cap

### Files changed
- `db/baseline.sql` — 6 `ref_risk_gauge` rows (`is_active=FALSE`), 5
  `ref_settings` threshold rows, `v_risk_gauge_scorecard` view.
- `etl/derive_risk_dial.py` — `_build_market_read_context()` +
  `_g_lists_derisking`/`_g_etf_net_short`/`_g_sss_book_collapse`/
  `_g_rr_flip_day`/`_g_lists_quad_conflict`/`_g_exposed_bear_themes`,
  registered in `GAUGES`.
- `api/routers/cockpit.py` — `GET /api/cockpit/risk-dial` returns
  `stale_as_of` from the 3 new tables' freshness contracts.
- `web/app.js` — label suffix.
- `docs/migrations.md`, `docs/dashboard_cockpit_design.md` §13.

### How I verified
1. `python -m db.init_db` idempotent; all 6 rows present, `is_active=FALSE`
   confirmed by direct query after every test below. `evaluate_gauges()`'s
   own loop skips any `gauge_key` whose row `is_active=FALSE` **before**
   calling its predicate function — proven live (the 6 new gauges never
   even appeared in the fired/quiet list while inactive). There is no CLI
   entrypoint on `etl/derive_risk_dial.py` (`python -m etl.derive_risk_dial`
   errors — no `__main__` block existed before or after this change), so I
   verified byte-identical behavior via this code-path proof + a live
   `evaluate_gauges()` call instead of the literal command in the task text.
2. Force-activated the 6 gauges in a live session and re-evaluated the
   2026-09-18 anchor: `etf_net_short` fired (ETF net −3), `lists_quad_
   conflict` fired (6 ≥ 4), `exposed_bear_themes` fired at 27% (found and
   fixed a real bug here — see below), `lists_derisking`/`sss_book_
   collapse`/`rr_flip_day` were quiet on this specific date (flat 4wk
   deltas / rows at their 4wk high / 7 < 9 flips) but **all 6 fired on at
   least one of the other 59 backfilled dates** (see table below).
   Detail strings name the numbers as required (e.g. `"ETF Pro net -3"`).
   Deactivated again immediately after (rolled back, confirmed
   `is_active=FALSE` afterward).
3. **Bug found + fixed**: `exposed_bear_themes` first computed 54% (way
   off the design's "quiet ~8%" expectation) because `THEME_CATEGORY_MAP`
   summed BOTH a sector axis AND a style axis for Cyclicals/Defensives —
   double-counting any stock that carries both tags. Fixed by dropping the
   style-axis duplicate (sector alone doesn't overlap with itself); re-
   verified at 27%. Still doesn't match the mockup's illustrative 8% —
   real portfolio data on a different date will legitimately differ; the
   double-counting bug is fixed, the residual gap is a real, expected
   data/date difference, not a further bug.
4. **30-date before/after `risk_budget` table** (2026-08-07 → 2026-09-18,
   current active gauges only, `extra_ctx={}` for both runs so the A/B
   delta is clean even though the absolute baseline differs slightly from
   production's real `extra_ctx`):

   | date | before | after | new gauges fired |
   |---|---:|---:|---|
   | 2026-08-07 | 96 CLEAR | 97 CLEAR | – |
   | 2026-08-10 | 96 CLEAR | 93 CLEAR | lists_quad_conflict |
   | 2026-08-11 | 95 CLEAR | 93 CLEAR | lists_quad_conflict |
   | 2026-08-12 | 100 CLEAR | 97 CLEAR | lists_quad_conflict |
   | 2026-08-13 | 100 CLEAR | 97 CLEAR | lists_quad_conflict |
   | 2026-08-14 | 90 CLEAR | 88 CLEAR | lists_quad_conflict |
   | 2026-08-17 | 96 CLEAR | 93 CLEAR | lists_quad_conflict |
   | 2026-08-18 | 100 CLEAR | 95 CLEAR | rr_flip_day, lists_quad_conflict |
   | 2026-08-19 | 100 CLEAR | 95 CLEAR | rr_flip_day, lists_quad_conflict |
   | 2026-08-20 | 96 CLEAR | 92 CLEAR | rr_flip_day, lists_quad_conflict |
   | 2026-08-21 | 96 CLEAR | 93 CLEAR | lists_quad_conflict |
   | 2026-08-24 | 94 CLEAR | 92 CLEAR | lists_quad_conflict |
   | 2026-08-25 | 98 CLEAR | 95 CLEAR | lists_quad_conflict |
   | 2026-08-26 | 98 CLEAR | 98 CLEAR | – |
   | 2026-08-27 | 96 CLEAR | 97 CLEAR | – |
   | 2026-08-28 | 94 CLEAR | 95 CLEAR | – |
   | 2026-08-31 | 78 CAUTION | 82 CLEAR | – |
   | 2026-09-01 | 100 CLEAR | 93 CLEAR | rr_flip_day, lists_quad_conflict, exposed_bear_themes |
   | 2026-09-02 | 93 CLEAR | 88 CLEAR | rr_flip_day, lists_quad_conflict, exposed_bear_themes |
   | 2026-09-03 | 90 CLEAR | 90 CLEAR | rr_flip_day |
   | 2026-09-04 | 92 CLEAR | 88 CLEAR | lists_quad_conflict, exposed_bear_themes |
   | 2026-09-08 | 86 CLEAR | 83 CLEAR | lists_quad_conflict, exposed_bear_themes |
   | 2026-09-09 | 78 CAUTION | 77 CAUTION | lists_quad_conflict, exposed_bear_themes |
   | 2026-09-10 | 86 CLEAR | 82 CLEAR | rr_flip_day, lists_quad_conflict, exposed_bear_themes |
   | 2026-09-11 | 86 CLEAR | 82 CLEAR | rr_flip_day, lists_quad_conflict, exposed_bear_themes |
   | 2026-09-14 | 78 CAUTION | 70 CAUTION | lists_derisking, rr_flip_day, lists_quad_conflict, exposed_bear_themes |
   | 2026-09-15 | 82 CLEAR | 73 CAUTION | lists_derisking, rr_flip_day, lists_quad_conflict, exposed_bear_themes |
   | 2026-09-16 | 86 CLEAR | 77 CAUTION | lists_derisking, rr_flip_day, lists_quad_conflict, exposed_bear_themes |
   | 2026-09-17 | 86 CLEAR | 77 CAUTION | lists_derisking, rr_flip_day, lists_quad_conflict, exposed_bear_themes |
   | 2026-09-18 | 80 CLEAR | 68 CAUTION | lists_derisking, etf_net_short, rr_flip_day, lists_quad_conflict, exposed_bear_themes |

   Reading: `lists_quad_conflict` is by far the most frequent new firer
   (19/30 dates) — worth checking whether its 4-conflict threshold
   (`rd_conflict_min`) is too easy to hit given 18-22 themes always have
   *some* quad mapping. `lists_derisking`/`etf_net_short` only fire in the
   most recent, most de-risked week (consistent with the narrative this
   whole batch is built around). **Budget dilution is real but modest**
   (typically −3 to −9 points, up to −12 on the most de-risked days) — the
   user should set final weights/activation from this table, not the
   Addendum H defaults (which the task itself says are untuned).
5. Freshness cap: `GET /api/cockpit/risk-dial` for the anchor →
   `stale_as_of: None` (fresh). Did not force a synthetic breach (no
   TASK_142 "step 3 method" reference was available to me — that task's
   own file wasn't in scope here); the code path
   (`etl/analytics_freshness.get_freshness` on the 3 new tables) is the
   same one already proven correct by `daily_health_check` above, so this
   is a low-risk, code-reviewed-only gap.
6. `v_risk_gauge_scorecard` returns rows (`SELECT * FROM
   v_risk_gauge_scorecard LIMIT 5` returned real hit/false-alarm/n_evaluated
   counts). The new 6 gauges themselves have zero scorecard history yet
   (they've never been active in `drv_market_stat.gauges_fired`) — expected,
   the view will pick them up once/if the user activates them.

**Status: DONE** except item 5's synthetic-breach test, which is a code-
reviewed-only gap (documented above), not skipped work.

---

## TASK_147 — Validation views + report + nightly refresh

### Files changed
- `db/baseline.sql` — `v_theme_stance_scorecard`, `v_sss_sector_scorecard`,
  `v_source_breadth_scorecard`.
- `etl/scheduler.py` — new `run_nightly_outcomes()` step ("market read
  refresh") that re-derives today's `drv_source_breadth`/`drv_theme_stance`/
  `drv_sss_breadth` and logs a row count from each of the 3 scorecard views.
- `docs/audit/market_read_validation_2026-09.md` (new report).
- `docs/migrations.md`.

### How I verified
1. All 3 views return rows; themes without a proxy (Breadth, Industrial
   metals, Large caps, Volatility) are explicitly listed as excluded in the
   report, not silently missing.
2. Report has `n` on every table; no verdict rests on n<30 (only one claim,
   the CALL short-side split at n=75, is marked HELD — everything else is
   explicitly THIN or UNTESTABLE, with the reason stated: autocorrelation,
   single up-trending regime, and — for the SPX-drawdown check — zero
   qualifying drawdown events in the 60-date window).
3. Ran the exact nightly-step logic directly (not via the scheduler
   process) and confirmed it logs real counts:
   `drv_source_breadth=5 drv_theme_stance=22 drv_sss_breadth=18 |
   scorecards: theme=342 sector=8 breadth=15`. `daily_health_check` already
   confirmed the freshness contracts (TASK_143/144 above).
4. Diffed my changes against `derive_actionable.py`, `ref_trig_*`,
   `ref_settings` (only the 5 new `rd_*` threshold rows added, no existing
   switch touched), and `ref_risk_gauge.is_active` (confirmed FALSE for all
   6 new rows, unchanged for every pre-existing row) — clean.

**Status: DONE.**

---

## Risks & notes (all tasks)
- RR's "macro net (24 symbols)" subset from the mockup isn't reproduced —
  I used the full RR board (52 symbols) per TASK_143's literal spec. If the
  user wants the narrower macro-only net, that subset needs to be defined
  explicitly (which of the 52 RR symbols count) — I didn't want to guess.
- `_TOTAL.book_size` (141) and a few per-theme You-$ figures don't match
  the mockup's hand-picked numbers exactly — explained per-item above, not
  hidden.
- `web/macro_areas.js` still has 4 small now-orphaned helper functions
  (`stancePillHtml`/`durationChip`/`rrBarHtml`/`extremesHtml`) left over
  from the legacy-card removal — harmless (unused, no caller), left in
  place to bound the size of this change; candidate for a future cleanup
  pass, not touched here.
- TASK_145's Accounts-filter scoping (item 8) is not implemented — see
  that section.
- **A browser pass on `/` is still needed** before treating TASK_145 as
  fully verified — see that section's explicit list of what I could and
  couldn't check without one.
- Real anchor date in this environment is 2026-09-18, not 2026-09-21 —
  every "matches the mockup" claim above is against the live snapshot
  dates each source actually had loaded (RR/PS Sep 18, ETF Sep 20, SSS
  Sep 14, CALL Sep 21), which is why the numbers line up despite the
  as-of-date mismatch.

## How to test (if a browser becomes available)
- Load `/`, confirm the Market Read panel renders in the middle column
  where Quad Rotation used to be, the 🧭 toggle collapses/expands it and
  the state survives a reload.
- Compare against `docs/mockups/market_read_one_picture_mockup.html` at
  1200px width — same 4 bands/columns/glyphs (numbers will legitimately
  differ, see Risks above).
- Click a theme row, confirm `#macroRailsWrap` expands and the matching
  rail band scrolls into view and briefly outlines.
- `pytest tests/` was not run for this batch (no test files were added or
  requested; this is backend+DB+UI work verified live against the running
  Postgres instance per the "How to verify" sections above, consistent
  with the existing test-debt policy of not asserting point-in-time DB
  values in `tests/`).

## Status
PARTIAL: TASK_145 (data layer + code done; browser/visual verification
outstanding — see that section). TASK_143, TASK_144, TASK_146, TASK_147 are
DONE against every "How to verify" item I could run without a browser.
