# Migration History

Append-only log of schema and behaviour changes. Most-recent first.

---

## 2026-09-22

- **Theme grid 1w/4w trend arrows bugfix: every theme showed "flat".**
  User: "why all 1W/4w showing -> arrows". `drv_theme_stance` stores one
  row per THEME per date (~22 rows/day); the prior-date lookup in
  `etl/derive_market_read.py::_derive_theme_stance_impl` used `OFFSET`
  without `DISTINCT`, so `OFFSET 4`/`OFFSET 19` (meant to land 5/20
  trading days back) skipped table ROWS instead of DAYS -- with ~22 rows
  per day, both offsets landed inside the very next earlier day's block,
  so "1w" and "4w" were both actually comparing today to just 1 trading
  day back (last Friday to Monday), which almost never changes stance.
  Fixed by adding `DISTINCT` to the date lookup. Re-derived the current
  anchor date (2026-09-21) to apply the fix; verified live -- Semis now
  shows up/up, Small caps down/down, Ags/USD/Industrial metals up on 4w,
  instead of 22/22 themes reading flat on both columns. Older historical
  `drv_theme_stance` rows still carry the old (wrong) trend values unless
  separately backfilled -- not done, user only asked to fix today's read.

- **Side-rail panel header bar charts removed.** User: "remove these
  barcharts that we added to the panels (volatility/major markets/etc)" --
  reverted the whole feature from this same day (see the entry directly
  below): removed `_weekly_bull_bear`/`_member_net_signal`
  (`api/routers/macro_areas.py`) and the `bull_bear_weekly` field from
  `/api/macro-areas`; removed `_breadthBarHtml` and the now-unused
  `_AREA_BREADTH_ID` map (`web/macro_areas.js`); removed the dead
  `.msr-breadth`/`.msr-breadth-bars` CSS rules and the now-permanently-
  empty `<span class="msr-breadth" id="macroBreadth...">` placeholders
  from all 10 panel headers in `web/index.html` (shared `.mr-bar-hit`
  hover-target CSS kept -- still used by the unrelated top breadth-strip
  tiles). Panels are back to a plain text header with no breadth
  indicator.

- **Side-rail panel headers (Volatility/Major Markets/Credit/etc.): "↑n
  ↓n" text → per-symbol %chg bar chart → 13-week bullish-minus-bearish bar
  chart.** Two-step user request. First: "add barchart for each panel ...
  replace '↑6 ↓1' ... right justified, take half of the panel width" —
  added `_breadthBarHtml` (`web/macro_areas.js`) rendering one bar per
  member's today's %chg (inverted-aware), right-justified via new
  `.msr-breadth` 50%-width flex container + `.msr-breadth-bars` SVG.
  Then, on being asked what the bars showed, user corrected: "calculate
  bullish - bearish. one bar per week. 13 weeks... (not down or up)" —
  wanted the same "bullish minus bearish" concept as the top breadth strip
  (RR/ETF/etc.), not a raw price-move chart. Confirmed definition: reuse
  each panel's own existing Long/Short stance signal (RR outlook
  Bullish/Bearish for most members; price-vs-Trade-line for "dual" role
  stock/ETF members with technicals — same rule `area_sig_sum`/
  `area_stance_raw` already summed for today), just counted per week
  instead of for one date. New `api/routers/macro_areas.py::
  _weekly_bull_bear` (+ extracted `_member_net_signal` helper, shared with
  the existing single-date roll-up logic) computes 13 weekly buckets
  (`DATE_TRUNC('week', as_of_date)`, same pattern as the top breadth
  strip's own 13-week fix) from `drv_rr`/`drv_technicals` history, one net
  value per week per area; `bull_bear_weekly` added to each area in the
  `/api/macro-areas` response. `web/macro_areas.js::_breadthBarHtml`
  rewritten to plot that 13-point series instead of per-member %chg.
  Verified live end-to-end via `get_macro_areas()`. Known non-bug: the
  Volatility panel (VIX/VXN/VXD/RVX/GVZ/OVX/MOVE — all "gauge" role) shows
  a flat 0 bar every week, because gauge members never fed the Long/Short
  stance sum either (excluded before that logic even runs) — there's no
  bullish/bearish concept for them under this definition.

- **RR breadth tile: reverted flip-based net back to the plain standing
  bull/bear snapshot.** User: "There should be more bullish (20) and 22
  bearish" — after the flip-count and then flip-direction-net experiments
  (2026-09-21, both built specifically to dodge RR's ~52-instrument
  cancellation problem), the user confirmed they actually want the
  straightforward standing count of all currently-tracked RR symbols'
  current outlook: 20 Bullish / 22 Bearish / 10 Neutral as of the 9/18
  snapshot, verified directly against `hist_rr`. That number was never
  missing — `etl/derive_market_read.py::_rr_bull_bear_counts` has computed
  it into `drv_source_breadth.n_bull/n_bear/net` unchanged the whole time;
  only `api/routers/cockpit.py`'s breadth-strip endpoint was overriding it
  with the flip-direction calc. Fix: removed the `if source_code == "RR"`
  branch entirely and merged RR into the same `else` path ETF already
  uses (`net_based = source_code in ("ETF", "RR")`), so RR now reads
  `n_bull`/`n_bear`/`net` straight from the stored row like ETF does. Also
  removed the now-unused `rr_flip_direction_counts` import from
  `cockpit.py` (the function itself is left in `derive_market_read.py` in
  case flip logic is wanted again later for a different purpose). No
  `web/market_read.js` change needed — RR was already wired into
  `_MR_NET_BASED`/`_MR_NET_WORDS: ['bull','bear']`/`_MR_BAR_CHART: 'sign'`
  from the 2026-09-21 work, which is the same shape this standing count
  needs. Flagged tradeoff to the user: this is exactly the calculation
  that had the cancellation problem (USD bullish + EUR/USD bearish, same
  dollar move, opposite raw labels) — but showing both raw counts (not a
  collapsed net) keeps it visible rather than hidden, so it's an accepted
  tradeoff. Verified live: `drv_source_breadth` for RR shows
  `n_bull=20, n_bear=22, n_total=52, net=-2`, matching exactly.

- **RR breadth tile bugfix: was silently showing "0 bull − 0 bear" when RR
  hadn't refreshed since the last derive.** User: "why 0 and 0?" caught
  it. `api/routers/cockpit.py`'s new RR directional-net code (added
  2026-09-21) called `rr_flip_direction_counts(s, row["as_of_date"])` --
  wrong column. `as_of_date` is the derive/anchor date; `snapshot_date` is
  the actual `hist_rr` data date `_rr_flips` itself has always used. When
  RR hasn't gotten a new file since the last derive (as_of_date=9/21 but
  snapshot_date still 9/18, e.g. over a weekend), `hist_rr` has zero rows
  dated 9/21, so the flip lookup silently matched nothing instead of
  falling back to the last real reading. Fixed by adding `snapshot_date`
  to the series query and using it instead of `as_of_date` for all three
  `rr_flip_direction_counts` calls (latest, 3wk-ago, and the 13-week
  series loop). Verified live: now correctly shows "0 bull − 3 bear" for
  today (carrying forward Friday 9/18's real reading), not "0 and 0."

## 2026-09-21

- **RR breadth tile: flip count -> directional longs/shorts net.** User:
  "RR -> change it longs - shorts." Kept the earlier flip-count fix (still
  avoids the original net-standing-position cancellation problem, e.g. USD
  bullish + EUR/USD bearish on the same dollar move) but broke it into a
  directional net, same shape as ETF/CALL: new `etl/derive_market_read.py::
  rr_flip_direction_counts` counts how many symbols flipped TO bullish vs
  TO bearish (not just the combined total), computed live per point in the
  13-week series, no new stored column. Verified live: a real, varied
  pattern (mid-August was clean bullish flips 4-0/3-0/2-0, September
  shifted to bearish 0-2/0-4/0-3). `web/market_read.js`: RR moved from
  `_MR_COUNT_UNIT` into `_MR_NET_BASED`/`_MR_NET_WORDS` and `_MR_BAR_CHART`
  switched from `'delta'` to `'sign'` (a directional net can cross zero; a
  plain count couldn't). Wording: user follow-up "BULLISH - BEARISH" —
  RR uses `['bull', 'bear']`, not ETF/CALL's `['longs', 'shorts']`, since
  RR's ~60 mixed instruments (indices, rates, FX, commodities) don't all
  carry a long/short trading concept the way an equity list does. SSS/PS
  are now the only tiles left on the plain-count path. Also removed the
  "BREADTH — five independent lists, 13-week history, dot = latest"
  subtitle line to save vertical space, per user request.

- **RR breadth tile: line sparkline -> green/red bar chart.** User: "do
  the same for RR -> add bar chart." Added to `_MR_BAR_CHART` with
  `colorMode: 'delta'` (week-over-week direction), not `'sign'` — RR's
  flip count is a plain count like SSS/PS, verified live to never go
  negative (ranged 2-12 across the last 13 weeks), so a sign check would
  always read green. All 5 breadth tiles are now bar charts; none are
  left on the line sparkline.

- **CALL breadth tile: line sparkline -> green/red bar chart.** User:
  "add bar chart instead of line" (following independent verification of
  CALL's turnover numbers). Added to `_MR_BAR_CHART` with `colorMode:
  'sign'`, same treatment as ETF — CALL's turnover net genuinely crosses
  zero (verified live: ranged from -11 to +37 across the last 13 weeks),
  so green/red by actual sign is meaningful. RR keeps the line sparkline
  (a plain flip count, not part of this ask).

- **Breadth tiles: right-justified current/max readout.** User: "Show
  current/Max right justified and take first two lines combined for
  height." Tile layout restructured: header+delta now stack in a left
  column (`.mr-tile-top` flex row), with a right-justified "current/max"
  figure (e.g. "35/86") vertically centered against that same two-line
  block — reuses `hero`/`max_13wk`, already computed, no new data.
  Sparkline/bar chart unchanged, still full-width below the row. New CSS:
  `.mr-tile-top/.mr-tile-left/.mr-tile-curmax`. Coloring iterated twice:
  first matched the "vs max 13wk" delta segment (green only at/above the
  exact high, which is rare so it read as almost-always-red); user: "Use
  if the count is with in 20% of max, color it green else red" — final
  rule is `hero >= max_13wk * 0.8` (`.mr-tile-curmax.up/.dn`).

- **Breadth strip bars: hover tooltip shows the date + number.** User:
  "bar hover/pop over should show the number." Native SVG `<title>` per
  `<rect>` (`web/market_read.js::barSparkline`) — a real browser tooltip
  on hover, no JS tooltip system needed. `api/routers/cockpit.py::
  get_market_read` now also returns `series_dates` (ISO date per series
  point) alongside `series` so the tooltip can show "MM/DD: value", not
  just a bare number.

- **Market Read breadth strip: fixed the "13-week history" claim to
  actually be 13 weeks.** User: "i thought you are displaying 13 weeks of
  data" — real bug, not just SSS: `drv_source_breadth` gets a new row on
  every trading-day derive, so `ORDER BY as_of_date DESC LIMIT 13`
  (all 5 sources) only ever covered ~19 calendar days (2.7 weeks), not 13.
  It also silently mislabeled "vs 3wk ago" (`series[-4]` was really ~4
  trading days back, not 3 weeks). Fixed in `api/routers/cockpit.py::
  get_market_read` with `DISTINCT ON (DATE_TRUNC('week', as_of_date))` --
  one row per calendar week, the latest day in each of the last 13 weeks
  ("one bar per week," per user). Verified live: now spans 11.6 weeks
  (`drv_source_breadth` itself only goes back to 2026-06-23, ~13 weeks
  before today, so that's the real ceiling) with genuine week-to-week
  variation restored (SSS: 80→77→68→86→67→66→73→75→86→79→61→35→35, not
  the flat/repeated-value view the old daily-window query showed).
  `series[-4]` now correctly means 3 real weeks ago. No frontend change
  needed — `web/market_read.js` just renders whatever `series` it's given.

- **SSS/ETF/PS breadth tiles: line sparkline -> green/red bar chart.**
  User: "can you change line graph to green (+ve) and red (-ve) bar
  graph." Bar heights still scaled min/max like the old line chart (so
  week-to-week variation stays legible in a small sparkline), but color
  now carries the +ve/-ve read: ETF (`web/market_read.js::barSparkline`,
  `colorMode='sign'`) colors by the value's actual sign, since its net can
  genuinely cross zero. SSS/PS (`colorMode='delta'`) are always-positive
  counts — raw sign would always read "positive" and never show red — so
  they're colored by week-over-week direction instead (green if higher
  than the previous point, red if lower; the first point has no prior to
  compare, shown neutral gray), per user confirmation. New CSS:
  `.mr-bar-up/.mr-bar-dn/.mr-bar-flat` reuse the existing `--mr-bull/
  --mr-bear/--mr-neu` tokens. RR/CALL keep the original line sparkline,
  untouched.

- **RR and CALL breadth tiles: replaced the "net" hero with a plain change
  count — flip count (RR) / turnover (CALL).** User: "for RR and CALL, is
  there any other way to represent the changes in those tiles? they are
  not helpful. SSS/ETF/PS tiles are good. We can lock them." Investigated
  a `ref_rrt` category-breakdown alternative first (categorize RR's ~62
  symbols by asset class, show a per-category net) — dropped it after two
  findings: (1) only ~20% of RR's symbols (Credit/Crypto/Rates/FX) actually
  move together as a group; the other 80% (Sector ETFs, Single Stocks,
  Commodity, Equity Index) are idiosyncratic, so categorizing them buys
  nothing, and (2) even within "coordinated" categories, a naive net sum
  is actively wrong, not just noisy — verified live that USD is inverse to
  EUR/USD (39% opposite-label days vs 3% same-label) and GBP/USD & CAD/USD
  lean the same way, so a dollar-strength day would show up as bullish
  USD + bearish EUR/USD canceling to ~zero net instead of reinforcing.
  Recommendation instead: show **how much is changing**, not **what the
  net position is** — neither number has a cancel-out risk, since both
  just count "did something change," not direction.
  - **RR**: hero is now flip count (`drv_source_breadth.flips_vs_prior`,
    already computed for the existing "regime-shift marker" flip-days
    note — no new derive logic). "RR macro board · 7 flipped today."
  - **CALL**: first tried a plain turnover total ("CALL · 12 new in last 5
    days"), then user: "CALL needs to go back to longs vs shorts" — kept
    the turnover fix (still recomputed over the trailing 5 days, not the
    30-day standing window that barely moves) but restored the ETF-style
    net-based shape: `etl/derive_market_read.py::call_turnover_counts`
    dedups per symbol to its most recent row in the 5-day window (same
    pattern as `_call_window_counts`) and returns the bull/bear/neutral
    breakdown, computed live per point in the 13-week series. Hero =
    n_bull − n_bear of that window. "CALL (-8) · 30 longs − 38 shorts"
    (verified live), vs. the old 30-day standing net that barely moved.
  - SSS/ETF/PS tiles untouched, per "lock them." `web/market_read.js`:
    `_MR_NET_BASED` now contains ETF and CALL (RR is the only one on the
    plain-count/no-zero-line path, since flip count is never negative);
    `_MR_COUNT_UNIT` has RR's unit text only.

- **Root-caused and fixed the stray drv_quote anchor bug from earlier
  today.** User: "why there is a stray quote in drv_quote in the first
  place?" -- traced precisely: every legitimate derive trigger
  (`etl_load.py`'s file watcher, `etl/hedgeye_fetch.py`'s email poller,
  `etl/backfill_derives.py`) correctly keys off `get_anchor_date()` or
  `hist_td`'s own real export dates, none of which can ever produce a
  weekend date -- but every major `drv_*`/`rpt_*` table had a complete
  920-symbol cascade sitting at `as_of_date=2026-09-20` (a Sunday, zero
  `hist_td` rows). Root cause: an ad-hoc `derive_all(session, <date>)`
  call outside the normal triggers (most likely the background Market
  Read build agent's own "full derive_all cascade re-run at the end",
  per its hand-back report, evaluating `date.today()` while its clock
  read that Sunday). It then self-perpetuated: `etl_load.py`'s forward-
  re-derive step re-derives any `drv_dash.as_of_date` later than the
  current anchor after every file load, with no check that the date is
  a real trading day, so it kept "refreshing" this fake row indefinitely
  -- which is exactly what shadowed the correct anchor row in every
  `SELECT MAX(as_of_date) FROM drv_quote` query and caused yesterday's
  wrong-date-time symptom.
  - **Prevention**: `etl/derive.py::derive_all` now refuses outright
    (warns and returns `{}`) when `as_of_date.weekday() >= 5` -- no
    anchor is ever a Saturday/Sunday, so this closes the door on the
    entire class of bug regardless of which caller gets the date wrong.
    User: "shouldn't we add a check if it is SAT or SUN, it shouldn't
    derive for that date."
  - **Query hardening**: `api/routers/marketbar.py` and the two identical
    call sites in `api/routers/dash.py` that did
    `SELECT MAX(as_of_date) FROM drv_quote` now cap it at
    `<= (SELECT MAX(export_date) FROM hist_td)`, so even a future stray
    row (from some other bug) could never again outrank the real anchor.
    (Note: this exact unguarded pattern also exists at ~25 other call
    sites across other `drv_*` tables, not touched here -- the weekend
    guard above is what actually closes off recurrence at the source;
    these two were hardened because they were the specific bug reported.)
  - **Cleanup**: deleted all `as_of_date=2026-09-20` rows -- 80,522 rows
    across 32 base tables (`drv_actionable`, `drv_dash`, `drv_quote`,
    `drv_trig`, `drv_source_standing`, `meta_derived_run`, etc.; `rpt_dash`/
    `rpt_actionable`/`drv_ma`/`v_available_dates` are views, auto-cleared).
    Verified after cleanup: `drv_quote` now correctly resolves to today's
    real anchor with fresh TOSD data (`source='TD'`, `export_date=
    2026-09-21`).

- **CALL breadth/theme-vote counts fixed: proper 30-day sparse-window
  aggregation, deduped per symbol, instead of a single-date snapshot.**
  User: "How far are you going back and checking in the table? there are
  rule on how much to check. check existing logic" -- `etl/derive_market_
  read.py::_latest_snapshot` (used for all 5 breadth sources) has no
  lookback cap at all, but CALL is specifically documented elsewhere
  (`etl/derive_outlook_action.py::_action_call_standing`, "sparse 30-day
  source") as a STANDING source: a symbol's call persists for
  `ref_outlook_source.lookback_days` (30) after its last row, not just on
  whichever date happens to be most recent. The old single-date count
  only ever saw symbols that happened to update on the single latest
  date -- verified against live data: **17 symbols** (8 bull/8 bear/1
  neutral) vs the correct **257** (104/91/62) once the full 30-day window
  is included. New `_call_window_counts`/`_call_stance_window_map`
  dedup per symbol to their most recent row in the window (`DISTINCT ON
  (symbol) ... ORDER BY snapshot_date DESC`, same pattern
  `_call_window_states` already uses in the actionable pipeline) before
  counting -- user: "make sure not to count same stock multiple times,
  you need to take the latest record." Verified live: META alone has 14
  rows inside the current 30-day window; naively summing all raw rows in
  the window would have inflated the total to 623 instead of the correct
  257 deduped symbols. Applies to both `drv_source_breadth` (breadth
  tiles) and `drv_theme_stance`'s CALL column (still computed/stored,
  though no longer displayed in the theme grid — see the CALL-column-
  dropped entry below). RR/ETF/PS/SSS untouched -- none of them are
  configured as sparse sources.

- **Market Read breadth tiles: hero number folded into the header text,
  standalone big-number line dropped.** User: "number don't mean anything
  here -- you can display them in the header text itself." Format:
  `SSS · 33 rows on list` (count-based: SSS/PS) / `ETF Pro (-3) · 17
  longs − 20 shorts` (net-based: RR/ETF/CALL, net in parens then the
  bull/bear or long/short breakdown -- RR uses "bull"/"bear" wording,
  ETF/CALL use "longs"/"shorts", matching each source's own established
  terminology). `.mr-tile-hero`/`.mr-tile-sub` removed (dead CSS);
  `.mr-tile-lbl` bumped from a 9px muted caption to 10px/weight 600/
  `--text-1` since it's now the tile's primary content line, not just a
  label. `web/market_read.js::_mrBreadthHeaderText`.

- **Market Read breadth tile deltas: the max-13wk comparison now gets its
  own arrow/sign too.** Format: `▼ -11 vs 3wk ago (46) · ▼ -44 vs max 13wk
  79` — each comparison (vs 3wk ago, vs max 13wk) is its own independently
  colored segment (`web/market_read.js::_mrDeltaSeg`), since a tile can be
  up vs one reference and down vs the other. `.mr-tile-delta.up/.dn`
  changed to `.mr-tile-delta .up/.dn` (now target the inner `<span>`s, not
  the whole line) in `web/styles.css`.

- **Yahoo-fetch last-fetch-time label: switched to the actual fetch
  timestamp, not the winning price source's.** Went through a few
  iterations on position/format (12h next to the icon, 24h below it,
  Actionable/Portfolio only -> every page) before user caught the real
  issue: the label read `/api/marketbar`'s `quote_time`, which is
  `drv_quote`'s WINNING SOURCE's timestamp after derive_quote's TL/TD/Y/
  CACHE merge -- not "when did we last check Yahoo". That's also exactly
  what surfaced a separate real bug: a stray `drv_quote` row for
  `as_of_date=2026-09-20` (never a real anchor -- likely leftover from the
  Market Read backfill) was shadowing the correct, freshly-updated anchor
  row (`2026-09-18`) in every `MAX(as_of_date) FROM drv_quote)` query,
  displaying Friday's stale price/time even though the actual anchor row
  already had today's fresh CACHE data. **Not yet fixed** (`api/routers/
  marketbar.py`, `api/routers/dash.py` both have this fragile pattern) --
  flagged for follow-up, either delete the stray row and/or key these
  queries off `get_anchor_date()` instead of a bare `MAX(as_of_date)`.
  The label itself now sidesteps all of that: switched to the existing
  `GET /api/yahoo-fetch/status` endpoint (`MAX(fetched_at)`/
  `MAX(detail_fetched_at)` from `cache_yahoo_quote`, no derive/anchor
  logic at all), showing whichever of intraday/full-detail fetch is more
  recent. The auto-refresh-when-stale staleness check
  (`_checkAutoRefresh`) had the identical flaw and was switched the same
  way. `market_bar.js`'s now-unused `_fmt12h`/`_latestQuoteTimeStr`/
  `_latestQuoteDateStr` helpers removed. Final label state: 24h, "MM/DD
  HH:MM", below the icon, on every page (`market_bar.js` was already
  `<script>`-included on 20 pages for the toolbar icon, just never
  cache-busted -- fixed on all 20).

- **Market Read breadth strip: CALL added, reordered SSS/ETF/PS/CALL/RR,
  max-13wk shown alongside the 3wk-ago delta.** CALL was already computed
  in `drv_source_breadth` (`etl/derive_market_read.py` treats it like ETF —
  net = n_bull − n_bear) but never surfaced in the breadth tiles, only in
  the theme grid (where it was just dropped for lack of data — a different,
  still-valid finding; CALL stays excluded from theme-vote stance).
  `api/routers/cockpit.py::get_market_read` now iterates
  `("SSS","ETF","PS","CALL","RR")` instead of `("RR","ETF","PS","SSS")`;
  frontend `BREADTH_LABEL`/`_MR_NET_BASED` in `web/market_read.js` updated
  to match (CALL gets the same L/S sub-label and zero-line sparkline ETF
  has). Each tile's delta line now also shows the max value seen over the
  same already-fetched 13-week window, no extra query
  (`breadth[].max_13wk`).

- **Market Read grid + macro rail panels moved to the top of the middle
  column.** Both (`#quadRotationPanel` then `#macroRailsWrap`) moved from
  below the graphs panel/above Hedgeye (their original slot) to above the
  accounts filter bar — user: "move them to the top above the filter bar."
  Their relative order to each other is unchanged (grid first, then the
  rail panels). Removed an orphaned 2026-08-24 historical comment that had
  documented the rail panels' old position and no longer applied. Also:
  theme grid split into 2 columns (Macro + Commodities & real assets on the
  left, Equity factors + International on the right,
  `web/market_read.js::_themeGridColHtml`); all `.mr-*` font sizes/padding
  trimmed twice over (user: "reduce the sizes so i can see more", then
  "reduce the font by 1 point and size accordingly"); "Lists say" and
  "Agree" column headers shortened to "Lists"/"Ag".

- **Market Read theme grid: CALL column dropped.** User: "it doesn't have
  any data" — confirmed, not a rendering bug: `ref_symbol_theme`'s ~80
  hand-curated symbols were drawn from the four original headline lists
  (RR/ETF/PS/SSS), and CALL's much broader daily list barely overlaps that
  set, so its per-theme vote was empty on nearly every row. Removed the
  `<th>`/`<td>` from `web/market_read.js` (colspan 15→14) and the
  now-unused `.mr-muted-cell` CSS rule. Backend (`etl/derive_market_read.py`,
  `drv_theme_stance.call`) untouched — display-only change.

- **Market Read's 9 macro rail panels reverted to always-visible.** TASK_145
  (below) shipped Volatility/Rates/Credit/Major Markets/USD/Country ETFs
  collapsed by default behind `#macroRailsWrap`, revealed only by clicking a
  Market Read theme row. User noticed the panels had disappeared ("What
  happened to all my panels in the middle column?") — reverted to always
  visible, same as pre-TASK_145. `web/market_read.js::_mrExpandRail` keeps
  the scroll-to-and-highlight behavior on a theme-row click, it just no
  longer needs a show/hide step first. Follow-up: TASK_145 had also pulled
  the Sectors panel out of the rail row into its own standalone
  always-visible band (the reason no longer applied once the row itself
  stopped being collapsible) — moved back into its original column-2 slot,
  right after Major Markets, per "move the sectors back into its place as
  before." Same ids throughout (`#macroSectorEtfsBand`/`#macroRailSectorEtfs`),
  so no script changes needed either time. Second follow-up: the whole
  `#macroRailsWrap` block moved from *before* the Market Read grid
  (`#quadRotationPanel`) to *after* it — summary first, detail below (a
  raw data panel shouldn't precede its own synthesis), which also matches
  the direction `_mrExpandRail`'s scroll-to-and-highlight already goes
  (down into the panels, not up). Pure DOM reorder, no id/script changes.
  Docs: `docs/market_state_factor_sss_design.md` Addendum G.

- **Yahoo-fetch: auto-refresh when stale + last-fetch-time label.** On
  Actionable/Portfolio, the main-toolbar quote-refresh icon now
  auto-triggers once (no retry) if the newest quote is >30 min stale and the
  tab is visible — spins while in flight, shows a persistent `!` on
  failure/skip until a real fresh quote lands. Guaranteed no more than one
  auto-triggered call per 30 min **server-side** (`ref_settings.
  yahoo_auto_trigger_last_at`, `etl/yahoo_fetch.py::auto_trigger_on_cooldown`
  / `mark_auto_trigger_now`), not just client-side, so it holds across every
  browser tab and survives API `--reload-dir api` restarts. Manual clicks
  are unaffected by the cooldown. A small last-fetch-time label (12-hour
  format) now shows under the icon on those two pages. `web/market_bar.js`,
  `api/routers/dash.py` (`/api/yahoo-fetch/quotes-now?auto=1`).

- **Market Read (TASK_143/144/145/146/147)** — display + measurement layer
  reading the four Hedgeye lists (RR/ETF/PS/SSS) + CALL over time, mapped to
  22 hand-curated themes. Design: `docs/market_state_factor_sss_design.md`
  (Addendum A-H). Nothing here touches `derive_actionable.py`, `ref_trig_*`,
  `SOURCE_ORDER`, or `ref_settings` decision switches.
  - New tables (`db/baseline.sql`): `ref_symbol_theme` (seeded ~80 rows,
    `db/seeds_symbol_theme.sql`), `drv_source_breadth`, `drv_theme_stance`,
    `drv_sss_breadth`. All idempotent per `as_of_date`, freshness-contract
    rows added. `etl/derive_market_read.py` (source breadth + theme votes,
    reuses `api/_helpers.py::compute_quad_monthly_stance` — same monthly-
    weighted quad algorithm `GET /api/quad/band-factors` uses, factored out
    so "the quad" is never hard-coded); `etl/derive_sss_breadth.py` (SSS
    sector rows+books, `_normalize_sss_sector` fuzzy-matches the raw
    `hist_sss.sector` text — confirmed NOT clean, ~18% of rows are OCR/
    header-leak noise, see the module docstring). Both wired into
    `derive_all()` after `drv_category_perf`, non-critical.
  - New endpoints (`api/routers/cockpit.py`): `GET /api/market-read`,
    `GET /api/market-read/sectors`.
  - New UI: `web/market_read.js` (replaces the retired `web/
    quad_rotation_panel.js` in the same `#quadRotationPanel` slot, middle
    column of `/`) — breadth strip + theme grid + sector cards (into
    `#macroRailSectorEtfs`, pulled out of the collapsible `#macroRailsWrap`
    since Sector cards are an always-visible Market Read band, not a
    drill-down rail) + headline sentence appended into `#regimeLineBand`.
    `web/macro_areas.js`'s dead `renderLegacyCard`/`injectLegacyCard` (never
    mounted) removed. New CSS tokens `--mr-bull/--mr-bear/--mr-neu`
    (deuteranopia-safe pair, Addendum E4) in `web/styles.css`.
  - Risk Dial: 6 new `category='positioning'`/`'self'` gauges in
    `ref_risk_gauge`, shipped `is_active=FALSE` (predicates in
    `etl/derive_risk_dial.py`; thresholds in `ref_settings` `rd_*`).
    Freshness CAP (not a gauge): `GET /api/cockpit/risk-dial` returns
    `stale_as_of` when the positioning tables breach their freshness
    contract; `web/app.js` suffixes the risk-dial label, the number itself
    never moves for staleness. `v_risk_gauge_scorecard` (report-only).
  - Validation: `v_theme_stance_scorecard`, `v_sss_sector_scorecard`,
    `v_source_breadth_scorecard` + CALL long/short `side` split on
    `v_source_edge_scorecard` (reproduces the July CALL-short-leg finding,
    +6.30% n=75 vs the pooled series' +0.48%). Report:
    `docs/audit/market_read_validation_2026-09.md`. Refresh wired into
    `etl/scheduler.py::run_nightly_outcomes`.
- **SSS/SSSCHG merged into one candidate per symbol, resolved by recency.**
  User: these are not two independently-weighted sources — SSSCHG is the
  daily added/removed-only categorization of the SSS feed, SSS is the same
  feed's full-list reprocess (done weekly). The old fixed `SOURCE_ORDER`
  (SSSCHG=3 always beats SSS=7) meant a held row's winner sort — which
  ignores date entirely, unlike the not-held path — could show a stale
  SSSCHG event over a fresher SSS read. `etl/derive_actionable.py` now
  drops the older of the two (by `source_snapshot_date`/`as_of_date`)
  right after `by_sym` is built, before either reaches `src_actions`/
  `candidates` — so winner selection, the popover's driven-by list, and
  `source_actions` all see a single merged candidate. Every other source's
  `SOURCE_ORDER` position is unaffected. Docs: `docs/actionable_logic.md`.

- **Freshness contracts for computed analytics (TASK_142).** New
  `ref_freshness_contract` (`db/baseline.sql`, seeded by
  `db/seeds_freshness_contract.sql`) lets a computed table declare its own
  staleness contract: `date_column`, `max_lag_days`, `maturity_lag_days`
  (the *expected* structural lag, e.g. drv_rule_outcome can never be closer
  than ~20 trading days to the anchor), and `refreshed_by` (the job that
  keeps it current). `etl/analytics_freshness.py::check_all` evaluates every
  active contract against the anchor; a breach = `(anchor - MAX(date_column))
  > maturity_lag_days + max_lag_days`, and a zero-row table is always a
  breach. Wired into a new seventh `daily_health_check.py` check
  (`_check_stale_analytics`), which writes breaches to `meta_warning`
  (`code='stale_analytics'`) so they ride the existing `/api/warnings`
  toolbar badge. `api/_helpers.py::set_freshness_headers` stamps
  `X-Analytics-As-Of` / `X-Analytics-Stale` response headers (not the JSON
  body, to keep existing list-shaped responses byte-identical) on
  `/api/rules/scorecard` and `/api/rules/factor-scorecard`; Actionable
  reads the scorecard headers to grey the "Rules (edge)" pills and show an
  amber "EDGE DATA `<date>`" header chip (`web/actionable.js`); the
  Performance screen shows an "as of `<date>`" stamp + amber border on the
  scorecard/factor cards (`web/rule_performance.js`); File Monitor gets a
  read-only "Stale analytics" status beside the existing "Stale Derives"
  button (`GET /api/monitor/stale-analytics`). Purely additive — no derive
  logic, rule, or threshold on the decision path changed. Seeded tables:
  `drv_rule_outcome`, `drv_factor_snapshot`, `drv_inferred_action`,
  `ref_vlm_intraday_curve` (all `refreshed_by='scheduler.run_nightly_outcomes'`),
  `drv_market_stat`, `drv_pvv` (`refreshed_by='derive_all'`). Prevention
  process change: `docs/agent_handoff_workflow.md` now requires any task
  adding a computed table feeding a decision screen to answer "what
  schedules it" / "what alerts if it stops" and ship the contract row in
  the same task. Also fixed two unrelated pre-existing bugs found while
  verifying this task's own health check: `_check_hist_gap` left a bad
  `ref_outlook_source.source_table` row (`hist_pk`, no longer a real table)
  poisoning the shared session's transaction for every check that ran after
  it, and `_check_scheduler_idle` read a `meta_file_processed.loaded_at`
  column that no longer exists (renamed to `processed_at`, already fixed in
  `api/routers/health.py`'s copy of this check but not this CLI's).

- **Enforce unproven SELL rules (TASK_141).** New
  `ref_settings.unproven_sell_mode` (`'annotate'` default / `'suppress'`) +
  `drv_actionable.unproven_sell_suppressed`. Reuses the existing
  `low_confidence` condition (TASK_118) — no second classifier. Under
  `'suppress'`, `etl/derive_actionable.py` excludes a `low_confidence` row's
  REMOVE/REDUCE `group_candidates` from the winner contest before the sort
  (falls to the next candidate or HOLD, never a synthesized action);
  `_compute_final_call` (+ JS mirror `finalCall()` in `web/actionable.js`)
  downgrades a sell call that would render `fc_confidence='high'` to
  `'mixed'` when `low_confidence` and the mode is `'suppress'`. Verified
  byte-identical in default `'annotate'` mode (zero
  `consolidated_action`/`final_code`/`fc_confidence`/`suppressed_reason`
  changes on a full anchor re-derive). **Finding:** on the current
  `ref_trig_rule_group` configuration, zero active action-type groups carry
  a REMOVE/REDUCE `action_label`, so `low_confidence` has never once
  co-occurred with a sell-family `consolidated_action` in this table's
  history — `'suppress'` mode produced **zero** suppressions on the test
  derive. Both Part A (candidate filter) and Part B (confidence downgrade)
  verified correct via direct isolated function calls instead. Mode left
  `'annotate'` after verification. Released by TASK_139 (SELL-side HELD
  across two windows). Docs: `docs/actionable_logic.md`
  "Unproven-sell enforcement", `docs/actionable_playbook.md` §5.

- **Source ranking by measured edge (TASK_140).** New `ref_source_precedence`
  (`db/baseline.sql`, seeded by `db/seeds_source_precedence.sql` with today's
  `SOURCE_ORDER` values as `static_rank` — the rollback anchor) +
  `ref_settings.source_order_mode` (`'static'` default / `'measured'`).
  `etl/derive_source_edge.py::recompute_source_precedence` (nightly, via
  `scheduler.run_nightly_outcomes`) ranks the six outlook sources
  (RR/SSS/CALL/II/PS/ETF) by n-weighted buy-family `edge_20d`
  (`v_source_edge_scorecard`), `measured_rank` NULL when n<30.
  `etl/derive_actionable.py::_order()` resolves via
  `COALESCE(measured_rank, static_rank)` under `'measured'`;
  `RTA`/`TOP5`/`SSSCHG`/`RTAINFO`/`MACROSHOW` unaffected by either mode. The
  not-held sort also becomes `(rank, -latest_update)` under `'measured'`
  (was `(-latest_update, rank)`, which structurally favoured CALL).
  `drv_actionable.winning_source_rank`/`winning_source_edge` persist what
  won and its measured edge. Verified byte-identical in default `'static'`
  mode (zero `consolidated_action`/`winning_source`/`winning_priority`
  changes on a full anchor re-derive); `'measured'` mode changed 29/1,078
  winning sources and 16 `consolidated_action`s on the same test derive.
  Mode left `'static'` after verification. Released by TASK_139 (A4 HELD
  across two windows). Docs: `docs/actionable_logic.md`,
  `docs/actionable_playbook.md` §5.

- **Second-regime signal revalidation (TASK_139).** Re-ran the July
  signal-validation report (`docs/audit/signal_validation_2026-07.md`) over
  the full Feb→Sep dataset (`python -m etl.backfill_full`, drv_rule_outcome
  now 12,406,349 rows through 2026-08-20), split into the original window
  (2026-02-02→06-11, regression check) and the new independent half
  (2026-06-12→latest). New report: `docs/audit/signal_validation_2026-09.md`.
  Measurement only — no view/derive/rule/threshold changes. Gate outcome:
  **A4 (source ranking) HELD → released TASK_140; SELL-side (unproven sell
  rules) HELD → released TASK_141.** Two non-gating assumptions FLIPPED
  without a regime change: `rr_bull_bear` (B/!B) no longer separates
  outcomes correctly, and the `SS`/high vs `SS`/mixed confidence direction
  reversed — both retired as trustworthy signals in
  `docs/actionable_playbook.md` §3.3/§5. The new period (SPX +3.0%, VIX avg
  16.5) is a calmer continuation of the same up-trend, not a drawdown/chop —
  A5 (edges generalize across regimes) remains formally unproven.

---

## 2026-09-20

- **Outcome ETL (`drv_rule_outcome`) scheduled nightly (TASK_138).**
  `etl/compute_firing_outcomes.py` was never wired into anything automatic —
  every edge number on screen (scorecard, LOW CONF flag, weak-buy-source
  recompute, the default dollar-weighted edge sort) had been scoring off a
  window last refreshed by hand on 2026-07-12.
  `etl/scheduler.py::run_nightly_outcomes()` now runs a missing-dates
  `derive_all` backfill (no-op if nothing missing) followed by
  `compute_firing_outcomes.run_incremental(since=anchor - 45 days)` every
  night, before the weak-buy-sources recompute and the factor-outcomes
  refresh (both consume this table). New `run_incremental()` +
  `--since DATE` CLI option added to `compute_firing_outcomes.py` — without
  it, the script rescans the *full* history in `drv_trig`/
  `drv_cat_atomic_input` on every call, even without `--truncate`; `--since`
  caps that to the tail of history (still idempotent via the existing
  `(rule_id, as_of_date, tos_symbol)` PK upsert). No `--truncate` in the
  nightly path — a full rebuild stays manual (`backfill_derives` +
  `compute_firing_outcomes --truncate`). No schema change, no derive-logic
  change on the decision path. Docs: `docs/rule_tuning_and_outcomes.md`,
  `docs/actionable_playbook.md` §0/§6.

---

## 2026-09-02

- **Universe screen — "By Source" view + "All My Stocks" button.** Third
  top-level hierarchy (Source → Asset Class → Sector → Symbol) rooted at
  the outlook source(s) that flagged a symbol (`drv_actionable.source_actions`,
  new `sources` field on `/api/universe`'s symbol rows) — a symbol can
  carry more than one, so it can land under several source tiles, same as
  Style tags. "All My Stocks" is an orthogonal toggle (not a 4th view):
  every held symbol across every account as flat tiles, no Account/Source/
  Asset Class/Sector grouping — a symbol held in several accounts combines
  into one tile (`current_position_dollar` is already the cross-account
  total on a `drv_actionable` row). `web/universe.js`/`web/universe.html`.
- **Actionable screen — 3W column removed.** The "3-Way Agreement" ▼3/▲3
  grid column is gone (dead `_agree3`/`_agree3Score` plumbing removed with
  it); `_threeWayAgreement()` itself stays, still feeding the "3-Way" row
  in the Final-Call side panel checklist.
- **Actionable screen — %Chg column Hi/Lo readout.** Tiny-font day
  High/Low under the price, each with its % distance from `last_price` in
  parens (e.g. "H $100 (+4%)"). Column widened 62px→98px, candle-to-price
  gap widened 4px→9px.
- **Watch/notify (🔔 column).** New `ref_watch` table — same-day price/
  level alert, separate from the standing `ref_conviction_hold` thesis.
  Trigger on a % move, or a genuine crossing (vs. a baseline reading taken
  at watch-creation, see `etl/derive_watch.py::_crossed`) of LRR/TRR/Trade
  line/Trend line/a $ target, or no condition at all (a plain
  "remind me regardless" reminder, triggered immediately). Live
  `LEFT JOIN LATERAL` in `get_actionable` (not baked into `drv_actionable`
  — this is ephemeral, not a historical annotation); `GET/POST/PATCH/DELETE
  /api/actionable/watch`. `etl/scheduler.py`'s `maybe_check_watches`
  (every ~minute, idempotent) flips `triggered_at`/`triggered_reason`;
  `maybe_send_watch_digest` (once/day, `ref_settings.watch_digest_hour`,
  default 15 = 3pm) emails ONE combined message of everything still
  triggered-and-unreviewed via `etl/notify.py::send_email` — skipped
  entirely if nothing qualifies, which is also how reviewing a watch
  in-app before the digest runs suppresses its email. Grid badge +
  quick-add popover + toolbar "Watching" panel in `web/actionable.js`/
  `web/actionable.html`.

---

## 2026-08-01

- **Dashboard cockpit (TASK_133, full build).** Replaces the `/` ticker-grid
  landing screen with a six-band daily risk cockpit. Design:
  `docs/dashboard_cockpit_design.md` (supersedes and deletes
  `docs/dashboard_attention_panel_design.md`).
  - **New tables** (`db/baseline.sql`): `ref_risk_gauge`, `ref_level_watch`,
    `ref_gauge_transmission`, `ref_market_pattern` (Phase 2 tuning surfaces);
    `drv_market_stat` (Phase 3: Yang–Zhang realized vol/VRP/breadth/
    participation + the 14/15-gauge Risk Dial, `etl/derive_risk_dial.py`);
    `drv_market_event` (Phase 6: range breaks/trend flips/z-scores/8 seeded
    patterns/calendar, `etl/derive_market_event.py`); `drv_category_perf`
    (Phase 5: time-weighted sector/asset_class/style returns vs proxy
    benchmark vs quad stance, `etl/derive_category_perf.py`);
    `hist_internals` (Phase 4.1: ToS `$ADVN`/`$DECN`/`$UVOL`/`$DVOL`/`$TRIN`,
    feed not yet flowing pending a user-side watchlist/LoadFiles.xlsx change).
  - **New feeds**: KOSPI complex (`^KS11`/`005930.KS`/`000660.KS`/`EWY` via
    Yahoo → `hist_macro`), Cboe VVIX/RVOL free CSVs (`etl/fetch_cboe.py`),
    `HYOAS` real credit-spread metric (was showing the `HYG` ETF price under
    a misleading `HY` label — relabeled), `T2S10` (2s10s curve) switched on.
  - **Bug fixes**: MOVE marketbar zone badge (`MOVE`→`MOVE:GIF` vol-threshold
    key mismatch); `/api/macro-areas` now sends server-canonical `hot_pct`/
    `cold_pct` (was silently falling back to a stale JS default).
  - **New API**: `api/routers/cockpit.py` — `GET /api/cockpit/risk-dial`,
    `/events`, `/factor-scorecard?axis=`, `/shortlist` (reuses the existing
    `/api/actionable` high-conviction filter, no new ranking logic).
  - **`derive_all()` cascade order**: `drv_market_stat` → (existing steps) →
    `drv_macro_score` → `drv_category_perf` → `drv_market_event`. The last
    two run later than their Phase headers originally said, because
    `drv_category_perf.quad_stance` needs `drv_macro_score`'s live
    per-membership stance and `drv_market_event`'s exposure block needs
    `drv_category_perf.market_value` — both are non-critical steps (a
    failure doesn't fail the cascade).
  - **Round 2 fix (position-swap / flow-gap detection, Part A):**
    `etl/derive_category_perf.py::_build_series` now detects a symbol's
    qty changing between two reported snapshots with **zero matching row
    in hist_cst/hist_ft (any action, not just Buy/Sell)** and forces that
    day's `r_t=0` + `flows_confidence='suspect'`, with the offending
    symbols recorded in `detail.windows.<w>.gap_days` — closing a gap the
    original 25%-magnitude-only guard missed whenever the untracked swap
    was small relative to the category's total value. Root cause: a Schwab
    transaction feed (`hist_cst`) for one account stopped loading
    2026-06-02 while its positions (`hist_cs`) kept updating, and a
    Fidelity account's positions (`hist_f`) have never had a single
    matching `hist_ft` row, ever — both real, ongoing feed gaps. See
    `DEV_HANDOFF.md` (archived as `DEV_HANDOFF.md` at the time, TASK_133
    round 2) for the full investigation.
  - **Frontend (Phase 7)**: `web/index.html` + `web/app.js` rebuilt — the
    `.dash-grid`/`#tickerSections`/section-chip ticker grid and the 3
    standalone side-stack cards (quads/econ/earnings) retired; six new
    bands render via `/api/cockpit/*` + the existing `/api/quad-window`,
    `/api/quad/band-factors`, `/api/anchor-status`. `styles.css`:
    `.dash-grid`/`.sections-grid`/`.ticker-col`/`.section-block`/
    `.ticker-grid` removed (verified dashboard-only); `.mini-grid`/
    `.side-scroll`/`.quad-mini`/`.side-stack` kept (reused by
    `web/actionable.html`).
  - **New tests**: `tests/test_yang_zhang.py`, `tests/test_risk_dial.py`,
    `tests/test_twr.py`, `tests/test_market_patterns.py` (pure-Python, no
    DB); `tests/acceptance/test_cockpit.py` (marked `@pytest.mark.acceptance`).

---

## 2026-07-15

- **MACRO: sliding look-ahead window over the monthly quad calendar
  (TASK_126).** Replaces the month now/next ramp + quarterly one-hot blend
  in `etl/derive_macro.py` with a sliding window `[D, D+H)` (`H` =
  `quad_lookahead_days`, default 60 calendar days) projected onto
  `ref_quad_periods` monthly rows; overlap-day weights (optional decay via
  `quad_lookahead_decay_hl`) blend the months' distributions into one
  effective distribution feeding the unchanged Stage 1–2 membership calc.
  Quarterly leg simplifies to current-quarter-only (no next-quarter blend)
  and its combine weight drops 0.20 → **0.05** (`quad_horizon_weight_qtr`).
  `quad_month_ramp_begin_days` / `quad_month_lead_days` /
  `quad_qtr_ramp_begin_days` / `quad_qtr_lead_days` / `quad_horizon_weight_mo`
  retired (reads deleted; rows left in `ref_settings` harmless). Sign-agreement
  override redefined on **near** (nearest window month's stance) vs **far**
  (weight-renormalized stance of the rest of the window) instead of
  month/quarter. Thresholds recalibrated: `macro_thr_bm` 0.62→1.25,
  `macro_thr_bs` 0.276→1.05, `macro_thr_stm` -0.736→-0.15, `macro_thr_sa`
  -0.88→-0.6 (live split: BM 2.4% / BS 17.3% / HOLD 65.0% / STM 8.3% / SA
  6.9%, n=1152 on 2026-07-14). `drv_macro_score` gained `detail JSONB`
  (`{h, coverage_pct, fallback, months[], eff{}, near_vs_far{}, tracking}`);
  `month_now_net`/`month_next_net`/`month_weight`/`qtr_next_net`/`qtr_weight`
  deprecated (columns kept, NULL going forward); `monthly_score` now stores
  `M_window`. This UPDATE also folds in a pre-existing drift fix: the
  2026-07-06 threshold/weight recalibration (0.65/0.35→0.80/0.20,
  thresholds 1.5/0.5/-0.5/-1.5→0.62/0.276/-0.736/-0.88) had only ever been
  applied by hand to the live DB, never migrated into `db/baseline.sql` — a
  fresh `db/init_db` before this change would silently get the stale 2026
  values. New API: `GET /api/quad-window` (aggregate, symbol-independent
  window mix for the regime band). `GET /api/actionable/macro-detail`
  layers `drv_macro_score.detail` onto the still-live Stage 1–2 membership
  resolution instead of recomputing the ramp/blend. `web/actionable.js`:
  `loadMacroBand()` regime band shows the window mix + dominant forward
  quad (was Month) with Quarter shown small/de-emphasized;
  `_macroTooltip()`/`_buildMacroPopHtml()` show the per-month window table +
  tracking tag instead of Month/Quarter ramp blocks; `macro_turn` (ramp
  alert) retired, `macro_conf` now the nearest window month's weight. Apply:
  `python -m db.init_db` then re-derive (restart the app first if it was
  already running — `etl/` changes need a fresh process, see CLAUDE.md).
  Full design: `docs/quad_design.md` (Stage 3).

---

## 2026-07-04

- **Market panel consolidation, frontend (TASK_116).** Hybrid consolidation of the three
  market tapes into one mini-tape + the Actionable side rail (design:
  `docs/market_panel_consolidation_design.md`; backend superset payload was TASK_115).
  `web/market_bar.js`: `#rrTape2`/`#rrTape3` mounts deleted; `#rrTape1` now renders a
  curated `BAR_MINI` list (SPX/VIX/DXY/GC/WTI from `/api/marketbar`; 10Y/HY/BTC from
  `/api/rr-bar` Rates/Credit/Crypto groups) plus a right-aligned as-of time. `/api/marketbar`
  + `/api/rr-bar` calls unchanged server-side; mini-tape trims client-side. `web/macro_areas.js`:
  rail member rows gained a candle (`window.mtTip.candleSvg`, now exposed alongside
  `volRangeBar`) and a solid tape-style %chg chip (honors `member.inverted`); Volatility
  rows color the symbol name by zone (not outlook) and keep the 3-zone `volRangeBar` +
  trailing zone badge; new **Credit** rail section (HYG/LQD); section headers gained
  breadth (↑n/↓n) counts. `web/actionable.js`: side panel now pinned by default (missing
  `actSidePinned` key ⇒ pinned; explicit `'0'` stays unpinned) and auto-unpins below
  1200px viewport width (manual toggle wins for the session). No schema change; no
  server restart needed (frontend-only — static assets hot-reload).

---

## 2026-06-10

- **Cockpit retired (Task 7).** `/cockpit` now returns `301 Redirect → /actionable`. All nav menus updated (removed Cockpit link). `web/macro_band.js` Market-context band moved to `web/actionable.html` as a collapsible card above the toolbar (collapse state persists in `localStorage['macroCardOpen']`). `docs/macro_feed_logic.md` and `CLAUDE.md` lookup table updated.
- **EOD feed status warning (Task 2).** `GET /api/eod-feed-status` checks `hist_tl` for rows on the anchor date. Returns `{missing, date, message}`. `web/actionable.js` calls it on load/date-change/refresh and shows a red blocking banner (`#eodMissingBanner`) with dimmed rows (opacity 0.7) when missing. `/api/healthz/warnings` also surfaces the status.
- **Derive cascade status tracking (Task 3).** `meta_derived_run` gained `cascade_status TEXT` column. `derive_all()` tracks failed steps and writes a `target_table='_cascade'` summary row with `SUCCESS/PARTIAL/FAILED`. `/api/derive-cascade-status` endpoint returns latest cascade status for a date. `/api/healthz/warnings` surfaces PARTIAL/FAILED. `daily_health_check.py` includes derive health in its checks.
- **Intraday price tag in drv_quote (Task 4).** `drv_quote` gained columns `pct_brr`, `zone_signal` (Y/W/N), `dist_to_trend`, `dist_to_trade`, `is_intraday`. Actionable screen shows a blue "IDY" badge when `quote_is_intraday=true`. Apply: `python -m db.init_db` then re-derive.
- **Backfill pipeline unified (Task 5).** `etl/backfill_full.py` combines `backfill_derives.py` + `compute_firing_outcomes.py` into one command: inventory, derive missing dates, compute outcomes. Usage: `python -m etl.backfill_full [--inventory] [--limit N] [--skip-outcomes] [--from DATE] [--to DATE]`.
- **ML holdout validation (Task 6).** `ml_tune_thresholds.py` now does a chronological 70/30 train/holdout split, evaluates edge on both halves, and refuses to save (warns) if holdout edge <= 0 or < half of train edge (overfit guard, bypassable with `--no-holdout-gate`). Param set rows now store `train_edge`, `holdout_edge`, `holdout_n`, `validated=TRUE`. Legacy rows default to `validated=FALSE` (shown as "unvalidated" tag in the UI). Param Sets screen shows Train Edge and Holdout Edge columns side-by-side. Apply: `python -m db.init_db`.
- **Stop-level in drv_actionable (Task 8).** `drv_actionable` gained `stop_level NUMERIC`. Computed as `MAX(trade_line, price*(1-stop_pct))` using `ref_settings.stop_mode`/`stop_pct`. Shown below AMT$ in Actionable rows. `ref_settings` seeded with `stop_mode='trade_line_or_pct'` and `stop_pct='0.08'`. Apply: `python -m db.init_db` then re-derive.

---

## 2026-06-07

- **Macro feed (FRED) — data layer only (UI deferred).** New `ref_macro_series` (tunable catalog, seeded by `db/seeds_macro.sql`, ~20 series) + append-only `hist_macro` (PK `(series_id, obs_date)`, `ON CONFLICT DO NOTHING`) + `v_macro_latest` view (latest+prior+chg). `etl/fetch_macro.py` pulls from FRED via stdlib `urllib` (no new dependency) — the only **pull** ingest, NOT in `etl/scheduler.py`; run daily after close. `FRED_API_KEY` in `.env` → `settings.fred_api_key`. `GET /api/macro` (`api/routers/macro.py`, registered in `main.py`) returns grouped tiles for the planned cockpit band. Covers econ data AND EOD index levels (`SP500`/`NASDAQCOM`/`DJIA`/`RU2000PR`/`VIXCLS`) — no second API needed for an EOD workflow. Complementary to workbook-sourced `ref_econ_indicator`/`ref_calendar_event`. Apply: add key to `.env` → `python -m db.init_db` → `python -m etl.fetch_macro --full`. Full design: `docs/macro_feed_logic.md`.
- **Macro fetch throttle + manual refresh.** `etl/fetch_macro.py` is now throttled: skips (no FRED call) if a real run started within a window, logged to new `meta_macro_fetch`. Window tunable via `ref_settings.macro_fetch_min_interval_min` (seeded 360=6h; precedence: `--min-interval`/arg → ref_settings → code default); `--force` overrides. `GET /api/macro` returns a `last_fetch` block; `POST /api/macro/refresh` runs a throttled fetch for the (future) manual Refresh button — reads never call FRED so the screen is 0 requests. Apply: `python -m db.init_db`.
- **Cockpit "Market context" band LIVE.** `web/macro_band.js` (loaded by `web/cockpit.html`, route `/cockpit`) renders a Market-context card above the actions table: grouped macro tiles (Indexes/Rates/Inflation/Jobs/Risk/Dollar&commodities) from `GET /api/macro`, a "Refresh data" button → `POST /api/macro/refresh` (throttled; shows "Up to date" when skipped), plus `as of`/`updated` stamps. Self-contained file — doesn't touch existing cockpit.js logic. Static assets — just hard-refresh; no DB/restart needed.

---

## 2026-06-06

- **Phase 2 base rules LIVE (firing-equivalent).** 8 leaf composites nest `BASE-Bull-Context`/`BASE-Bull-Trend`. Engine fixes that made it score-neutral: nested-composite gating fires only when the child fired (`_derive_stks_impl`), `_derive_trig_impl` now scores nested members (two-pass), `seeds_base_rules.sql` gate members `weight_override=10`, `refactor_base_rules.py` only absorbs members identical in threshold/operator/role. `_derive_trig_impl` also no longer double-evaluates pre-scored atomics (fixed 697 over-fire).
- **Phase 3 profiles LIVE.** `ref_trig_param_set`/`_value` overlay (`etl/param_sets.py`). Profiles: id=1 **Baseline 2026-06-05** (active, frozen current numbers, rollback anchor), id=2 Sigmoid v1 (inactive scaffold), id=3 ml-sweep-20d (inactive, overfit). One active at a time; switch two-step then re-derive. Rollback = activate id=1.
- **Phase 4 outcomes + scorecard.** `etl/backfill_derives.py` (additive historical derive backfill) + `etl/compute_firing_outcomes.py` populate `drv_rule_outcome` from rule firings + forward returns (no `user_action_log`). `v_rule_scorecard` ranks composites by direction-adjusted `edge_20d`. `drv_rule_outcome` PK fixed to `(rule_id, as_of_date, tos_symbol)`; column `symbol`→`tos_symbol`. ML (`ml_tune_thresholds.py`) writes inactive `ml:` profiles. **Caveat: only ~4 months/one regime loaded — diagnostic only; don't activate tuned profiles yet.** Full guide: `docs/rule_tuning_and_outcomes.md`.
- **`rebuild_rules` durability.** Now re-applies `current_volume_rule` neg thresholds (25/50) that a workbook reload would otherwise strip. Keep DB-only rule tweaks in sync there + `baseline.sql`.
- **Rules made usable in the UI.** Performance screen (`/rule-performance`) now shows the direction-adjusted scorecard (`/api/rules/scorecard`) + a "Your actions" panel (`/api/rules/my-actions`). Actionable (`/actionable`) gained a "Rules (edge)" column (fired rules winning-first w/ edge) + edge badges in the row popup; Rule Flow composites show the same badge. `v_rule_performance_window` re-anchored to `MAX(as_of_date)` (was wall-clock `CURRENT_DATE` → blank screen). Full UI map: `docs/rule_tuning_and_outcomes.md` §7.

---

## 2026-06-05

- **Anchor-date derive model**: Derive date `D` is now `MAX(export_date) FROM hist_td` (TOSD), resolved by `etl/derive.py::get_anchor_date`. Only TOSD advances `D`; `etl/etl_load.py` derives the anchor (not the filename date) after every load. `snapshot_date` is informational; derivation keys off `export_date`. Daily-EOD sources (TOSL/TOSD/TOSW/Y, `ANCHOR_LOCKED_SOURCES`) read `export_date = D` exactly with max `sequence` per symbol — no per-symbol carry-forward. `drv_symbols` universe = daily-EOD sources (td/tl/tw/y) at `export_date = D` (exact, no carry-forward) UNION periodic feeds (etf/ii/call/rr) at `snapshot_date <= D` — so a stock missing from today's TOSD/TOSL is excluded, but non-TOSD symbols (e.g. ETFs in etf/ii feeds) still appear. Periodic feeds + positions keep `<= D` carry-forward. **Run Missing Derives** now enumerates TOSD market-close dates (`DISTINCT export_date FROM hist_td`) via `api/routers/monitor.py::_find_missing_derive_dates`. `drv_quote` may use a fresher intraday price on the anchor date (tagged `as_of_date=D`). Missing daily-EOD files surface via `warn_missing_eod_sources` → `meta_warning` (dashboard/actionable toolbars). **No schema change** to the derive logic; apply across history with File Monitor → Force Re-derive. Full design: `docs/derive_date_logic.md`.
- **Default screen date = anchor**: `v_available_dates` and `/api/actionable/dates` are capped at `MAX(export_date) FROM hist_td`, so every screen's default (`dates[0]`) and `_resolve_date(None)` resolve to the anchor (stray future-dated derives no longer show). View change → **`python -m db.init_db`** to apply.
- **"Data behind market close" warning + date highlight**: `GET /api/anchor-status` (request-time) compares the anchor to `api/_helpers.py::expected_market_close_date()` (most recent completed US trading session — weekday not in `ref_holiday` — past `ref_settings.market_close_cutoff` default `16:30` in `market_timezone` default `America/New_York`; Windows needs `tzdata`). `web/warning_badge.js` polls it and, when stale, raises an amber toolbar warning + adds `.date-stale` to `#datePicker`. Displayed date stays the actual anchor.

---

## 2026-06-03

- **Composite mapping surrogate PK**: `ref_trig_composite_mapping` PK was `(composite_rule_code, atomic_rule_id)`, which made `atomic_rule_id` implicitly NOT NULL and blocked `data` / nested-`composite` members. Replaced with surrogate `mapping_id BIGSERIAL` PK + NULL-permissive `UNIQUE (composite_rule_code, atomic_rule_id)` (index `uq_ctm_code_atomic`). The loader upsert now passes `conflict_cols=` to `etl/db.py::insert_skip_duplicates` (new param) to target that unique. Apply via `python -m db.init_db`. **Required for Phase 2 nesting / clone / data members.**
- **Gate/WATCH composite firing**: `ref_trig_composite_mapping.member_role` (`gate`|`watch`) + `evidence_cutoff`. Fire = all gates pass AND watch evidence ≥ cutoff (NULL = watch never blocks). Pure-watch falls back to all-hit. Default `gate` = zero change. `etl/derive.py` + `api/routers/trace.py` apply it; `web/composite_edit.*` + `web/rule_flow.*` show roles. Backfill: `db/migrate_member_watch_roles.sql` (weight_override=1 → watch). Full design: `docs/rule_engine_redesign.md`.
- **Per-member thresholds loaded**: `etl/load_raw.py` now stores the Trig threshold cell into `data_brkeout_from` (was discarded → members degraded to "value≠0"). Workbook reload refreshes weight/threshold/role via ON CONFLICT DO UPDATE.
- **BASE-* sub-composites (Phase 2)**: `db/seeds_base_rules.sql` (5 reusable bases); exempt from loader pruning. Refactor leaves via `etl/refactor_base_rules.py` (dry-run default).
- **Param sets (Phase 3)**: `ref_trig_param_set` + `ref_trig_param_value` overlay tunable thresholds/weights/k/x0 at scoring time via `etl/param_sets.py` (consumed by `load_trig_rules`). `db/migrate_sigmoid_learnable.sql` converts monotonic rules jump→sigmoid (+ rollback).
- **ML tuning (Phase 4)**: `etl/ml_tune_thresholds.py` fits thresholds from `drv_cat_atomic_input` + `drv_rule_outcome`, writes an inactive param set to backtest then activate.

---

## 2026-05-31

- **drv_ma → VIEW**: Now a JOIN VIEW over `drv_symbols`, `drv_technicals`, `drv_fundamentals`, `drv_outlooks`, `drv_portfolio`. Never INSERT into it. `python -m db.init_db` applies the migration on existing DBs.
- **derive_all cascade**: `derive_ma` removed; 5 component derives run in its place (after drv_quote/drv_rr, before drv_cat_atomic_input).
- **trig_action on drv_actionable**: Third action column (SA/STM/SS/BM). Computed from fired rule groups via `ref_param_lookup` buysell scores.
- **git lock gotcha**: `.git/index.lock` / `.git/HEAD.lock` may stick after agent commits on Windows-mounted repos. Delete from Explorer before next git op.

---

## 2026-05-29

- **tos_symbol**: All `drv_*` use `tos_symbol` exclusively. `symbol` kept in `hist_*` only.
- **RR loader**: `load_rr()` in `load_raw.py`, registered in `CUSTOM_HANDLERS['rr']`.
- **hist_ps**: Uses `ticker` column; mapped to `tos_symbol` via `_populate_ps_tos_symbol()` through `ref_rrt`.
- **Schema migration pattern**: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `baseline.sql`.
