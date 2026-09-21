# Market State · Factor Monitor · SSS Breadth — design proposal

**Date:** 2026-09-21 · **Status:** built (TASK_143/144/145/146/147, 2026-09-21)
· **Author:** Cowork (code + docs review only; no DB access)

**Build note (2026-09-21):** implemented as specced with a few real-data
adjustments — see `docs/migrations.md` (2026-09-21, "Market Read") and
`DEV_HANDOFF.md` for the developer's own verification results, and
`docs/audit/market_read_validation_2026-09.md` for TASK_147's scorecard
report. The mockup's Q3/hand-derived numbers are illustrative, per Addendum
F/E — the build reads the live monthly-weighted quad and live snapshot
data, which legitimately differ date to date.

Three asks from the user, one finding each. All three reuse data that is
already loaded daily; two of them reuse computation that already exists.

---

## 1. "How is the market — not just SPX"

### Finding: the one-glance read was designed, computed, and never rendered

`docs/macro_areas_design.md` §"The gap" specified exactly this: a compact,
area-organised strip with an explicit stance per area, a Trade-vs-Trend
dual-duration call, hot/cold extremes, and a one-line top-down posture.

- **API — built and live.** `GET /api/macro-areas` returns, per area:
  `stance`, `conviction`, `trade`, `trend`, `rr_pos`, `extremes_hot`,
  `extremes_cold`, plus a `top_down` posture sentence
  (`api/routers/macro_areas.py::_build_top_down`).
- **Renderer — dead code.** `web/macro_areas.js::renderLegacyCard` draws that
  table, but only if `#macroReadCard` exists, and `injectLegacyCard()` is
  defined and never called. The dashboard (`/`) has neither anchor. Nothing
  on any screen shows the synthesis.
- **What the dashboard shows instead:** eight separate rail bands (Volatility ·
  Rates & Duration · Credit · Major Markets · Sectors · USD & Currency ·
  Country ETFs · Remaining), each a list of per-symbol rows with a day %
  and a range bar. Oil, gold, copper sit inside "Major Markets"/"Remaining"
  with no area-level verdict. That is the "it's there but not obvious."

Two genuine data gaps on top of the rendering gap:

1. **Only a 1-day % exists per member** (`pct_chg`). No 1-week / 1-month
   move, so "how is the dollar doing" can't be answered beyond today.
   `drv_quote`/`hist_y` history is loaded; 5d/20d returns are a window
   function away.
2. **Commodities are one bucket.** The user named oil separately from
   metals/ags. `ref_macro_area` has `commodities_credit` and `top9`; there is
   no `energy` / `metals` split.

### Proposal — Band ⓪ "Market State" on `/`

One strip, directly under the mini-tape, above the Risk Dial. One row per
area, nine areas, in this order (risk-on → risk-off reading top to bottom):

| Area | Members (RR / technicals — all already loaded) |
|---|---|
| US equities | SPX · $COMP · RUT / SPY · QQQ · IWM |
| Volatility | VIX (vol zones) · MOVE if present |
| USD & FX | $DXY / UUP; EUR·JPY·GBP·AUD crosses |
| Rates & curve | DGS2 · TNX:CGI · TYX:CGI / TLT · IEF |
| Credit | HYG · LQD |
| **Oil & energy** | /CL · /BZ · /NG / XLE |
| **Metals** | /GC · /SI · /HG / GLD · SLV |
| Broad commodities & ags | GSG / DBA if present |
| Crypto | /BTC / IBIT |

Per row: **stance pill** · **1d / 1w / 1m %** (new) · **range bar** (`rr_pos`)
· **Trade / Trend chips** · **hot / cold extremes** (which member is at TRR
or LRR). Above the table: the `top_down` posture sentence, already computed.
Click a row → expands that area's existing rail band in place (no new detail
view; the rails stay as the drill-down, they just stop being the headline).

**Work involved**

| Piece | Effort | New computation? |
|---|---|---|
| Mount + restyle `renderLegacyCard` as Band ⓪ on `/` (and keep on `/actionable`) | ½ day | No — dead code revived |
| Add `pct_5d` / `pct_20d` per member + per area to `/api/macro-areas` | ½ day | Yes, trivial (`LAG` over `drv_quote`) |
| Split `commodities` → `energy` / `metals` / `ags` in `ref_macro_area` + seeds | ¼ day | No — config |
| Collapse rails by default, expand from the strip | ¼ day | No |

No schema change beyond `ref_macro_area` rows. Nothing on the decision path.

---

## 2. "How is a certain factor doing"

### Finding: factor data exists, but framed as *your allocation*, not *the market*

`drv_category_perf` (`etl/derive_category_perf.py`, band ④ on `/`) already
computes, per sector / asset class / style tag: your time-weighted return over
1w·3w·1m·2m·3m, a proxy-ETF benchmark ("Mkt"), the quad stance, and an
ADD/HOLD/TRIM verdict. That is an **allocation** scorecard. The market-level
factor read is one column, and for several styles it is blank in disguise:

```
_STYLE_ETF = { "High Beta": "SPY",   # SPHB unavailable -- fallback
               "Value":     "SPY",   # VTV/SPYV unavailable -- fallback
               "Mid Caps":  "SPY", } # MDY/IJH unavailable -- fallback
```

So "how is High Beta doing" currently answers "same as SPY." Style tags
themselves are rule-based (`etl/derive_macro.py::_classify_style`: beta ≥ 1.5
→ High Beta, RSI > 65 → Momentum, PE < 15 → Value …) — usable, but a symbol's
tag changes as its RSI/PE moves, so "Momentum stocks" is a moving set.

### Proposal — a Factor Monitor with two independent lenses

**Lens A — the proxy (what the ETF says).** One row per factor: proxy ETF ·
1w / 1m / 3m return · **relative to SPY** · `rr_pos` · Trade / Trend. Requires
the missing proxies to actually be in the daily export so they have
`drv_quote`/`drv_technicals` history:

| Factor | Add to TOS watchlist universe |
|---|---|
| High Beta / Low Beta | SPHB / SPLV (SPLV present) |
| Momentum | MTUM (present) |
| Value / Growth | VTV / VUG |
| Size | MDY, IJR |
| Quality | QUAL |
| Dividend | VYM (present) |

Mechanism already exists: `ref_my_stocks` + `drv_symbol_tier`
`dashboard_dependency` → tier-1 daily export → `drv_quote` history. Add the
rows; the pipeline does the rest. Until ~63 days of history accumulate, the
3m column is blank, not faked.

**Lens B — constituent breadth (what the stocks say).** For every sector and
style tag, over the user's own universe (`ref_my_stocks` active ∪ held):

| Metric | Source |
|---|---|
| n members | `ref_sector` / `_classify_style` |
| % with `rr_bull_bear = 'B'` | `drv_tn_td_bb_rr` — the one bull flag that measured correctly (A1) |
| % above Trend line, % above Trade line | `drv_technicals` |
| median `rr_pos` | `drv_rr` |
| net RR outlook flips this week | `drv_rr_trend_change` |

Stored in a new idempotent `drv_factor_breadth(as_of_date, axis, category,
n, pct_bull, pct_above_trend, pct_above_trade, median_rr_pos, flips_net)`.
Breadth is the honest complement to a proxy: XLK can be up on three names
while 70% of tech stocks are below trend.

**Surfacing.** A "Factor Monitor" card on `/` beside band ④ (not merged into
it — allocation and market read are different questions), tabs Sector /
Style / Asset class. Each row: proxy return trio · rel-to-SPY · breadth mini
bar (pct_bull) · sparkline of pct_bull over 13 weeks. Click → member list,
reusing the Universe screen's grouping (`web/universe.js`), filtered to that
category, sortable by `rr_pos`.

**Work:** proxies ¼ day (config) · `drv_factor_breadth` ~1 day · card + drill
~1 day.

---

## 3. "SSS list count as a sector-health signal"

### Finding: everything needed is already in `hist_sss`

```
hist_sss(snapshot_date, symbol, tos_symbol, days_on, signal_date,
         prior_close, last_close, pct_delta, sector, analyst, …)
```

`sector` and `days_on` are loaded per weekly snapshot, and `hist_sss_change`
carries the same-day Gmail adds/removes. Nothing counts them over time today
(grep: no `COUNT(*)` over `hist_sss` anywhere in `etl/`, `api/`, `db/`).

The user's inference is sound: Hedgeye's Signal Strength list is longs-only,
the short book is not delivered, so **the list shrinking is the only visible
trace of the short side.** 80 → 35 names is a breadth collapse on the long
side and, by construction, an expanding short side.

### Proposal — `drv_sss_breadth`, weekly per snapshot

| Column | Meaning |
|---|---|
| `n_total` | names on the list |
| `n_sector` (one row per sector) | names in that sector |
| `share_sector` | `n_sector / n_total` — immune to the whole list shrinking |
| `n_vs_med13`, `n_vs_med26` | count vs 13-week and 26-week median, as a ratio |
| `z_26` | z-score of `n_sector` over 26 weeks |
| `adds`, `removes`, `net` | from `hist_sss_change` in the week |
| `median_days_on` | freshness — a list of old names is a tired list |
| `pct_positive` | share of members with `pct_delta > 0` since signal |

**Two counts, two meanings — keep them separate:**

- **Absolute count vs its own history** ("80 → 35") = *long-book breadth*.
  This is the risk-on/off gauge. Candidate 16th gauge on the Risk Dial
  (`ref_risk_gauge`, small weight, fires when `n_total < 0.6 × med26`).
- **Sector share and z-score** = *relative sector health* ("restaurants are
  bad"). This is the factor read. Goes on the Factor Monitor's Sector tab as
  an extra column + 26-week sparkline, beside the constituent-breadth numbers
  from §2 — so the analyst-list view and the price-based view sit next to
  each other and can disagree visibly.

**Three caveats the display must carry, not hide:**

1. The count also moves when Hedgeye changes process or analyst coverage,
   not only when the market does. `share_sector` and `z_26` are the more
   robust reads; the raw count is context.
2. "Inferred short pressure" = `med26 − n_total` is a proxy for an unseen
   book. Label it inferred. Never let it set an action on its own.
3. **Validate before it influences anything.** Add
   `v_sss_breadth_scorecard`: does a sector's `z_26` (or its 4-week change)
   predict that sector ETF's forward 20d return? Same forward-return
   convention as `v_factor_scorecard`. If it doesn't, it stays a display.

**One thing to check first (developer, has mailbox access):** Hedgeye's SSS
email may state the long/short totals in the body ("35 longs / 80 shorts").
If it does, parse them into `hist_sss_summary(snapshot_date, n_long,
n_short)` via `etl/hedgeye/parsers.py` — a *real* short count beats an
inferred one. Check `note_repo` / `meta_hedgeye_msg` for the phrase before
building the inference.

**Work:** `drv_sss_breadth` ½ day · scorecard view ¼ day · display ½ day ·
email-total parse ½ day if the numbers are there.

---

## 4. Suggested order and what NOT to do

| Order | Item | Why first |
|---|---|---|
| 1 | §1 Market State strip | Mostly dead code revival; highest visibility per hour |
| 2 | §3 `drv_sss_breadth` + check the email for real totals | Pure SQL over loaded data; answers a question the user is already asking by hand |
| 3 | §2 Lens A proxies (config) | Starts the history clock now — every week of delay is a week of missing 3m data |
| 4 | §2 Lens B `drv_factor_breadth` + Factor Monitor card | Needs a design pass on the card |
| 5 | §3 scorecard + Risk Dial gauge | Only after the data has a few weeks to validate against |

**Not proposed:** merging any of this into `consolidated_action`. All three are
*context* surfaces. The decision-layer work (TASK_139–142) is separate and
should not be entangled with display work.

**Worth reconsidering:** the dashboard already has 11 bands plus 8 rail bands.
Adding Band ⓪ and a Factor Monitor without collapsing the rails by default
would make the screen longer, not clearer. §1's "rails collapsed, strip
expands them" is load-bearing, not optional.

---

# Addendum — decisions from the 2026-09-21 review (supersedes §1–§4 where they differ)

Mockup of the agreed picture: `docs/mockups/market_read_one_picture_mockup.html`
(real values from the Sep 21 RR file, Sep 20 ETF Pro, Sep 18 PS, Sep 14 SSS,
Sep 21 CALL, Sep 18 Fidelity positions). Every number in it was computed from
those files by hand; the build reproduces them from `hist_*`.

## A. The picture — four bands on `/`

| Band | Content | Source tables |
|---|---|---|
| ① Headline | regime read from the lists · Quad model label + **conflict count** · turn date · your book in one line | derived below · `ref_quad_periods` · `drv_category_perf` |
| ② Breadth | RR macro net · ETF longs−shorts · PS count · SSS **rows + books** — hero, Δ vs 3 wk, 13-wk sparkline · RR flip-days | `drv_source_breadth` |
| ③ Theme grid | theme × (RR · ETF · PS · SSS · **CALL muted**) → Lists say · Agree · 1w · 4w · **Quad says** · **You $ · You % · Fit** | `drv_theme_stance` + `drv_category_perf` |
| ④ Sectors | per sector: **rows** and **book** side by side, tier bar, top-3, avg strength, median days-on, RR/ETF chips, your $ | `drv_sss_breadth` |

## B. New tables (all idempotent per date)

**`ref_symbol_theme`** — hand-curated, ~90 rows: `(symbol, theme, weight, inverted)`.
`inverted` for FX crosses quoted against USD (EUR/USD bearish ⇒ USD bullish) and
for yields (UST bullish ⇒ "Rates ↑"). Themes: Rates↑ · Duration · Credit · USD ·
Volatility · Cash/short FI · Large caps · Small caps · Breadth · Momentum ·
Defensives · Cyclicals · Healthcare · Tech/software · Semis · Energy · Precious
metals · Industrial metals · Ags · Crypto · Developed intl · Emerging. Each theme
also carries its `ref_quad_outlook (category, sub_category)` key so the Quad
column is a join, not a second map.

**`drv_source_breadth`** `(as_of_date, source_code, n_bull, n_bear, n_neutral,
net, flips_vs_prior, n_total)` — RR daily; ETF/PS/SSS/CALL per snapshot.
`flips_vs_prior ≥ 9` on RR is the turn marker.

**`drv_theme_stance`** `(as_of_date, theme, rr, etf, ps, sss, call, stance,
agree_n, trend_1w, trend_4w, quad_says, quad_conflict)`:
- each source cell ∈ {B, S, N, M(ixed), —}; a source votes B/S only if ≥ 2/3 of
  its members with a stance agree, else M;
- `stance` = majority of RR/ETF/PS/SSS votes (CALL excluded — see D);
- `agree_n` = number of those four that voted the stance direction;
- `quad_says` from `ref_quad_outlook` for the current quad
  (`/api/quad/band-factors` logic, not reimplemented);
- `quad_conflict` = `stance` and `quad_says` both non-neutral and opposite.

**`drv_sss_breadth`** `(as_of_date, sector, n_rows, n_ranked, n_bench, n_km,
book_size, book_size_asof, top3 JSONB, avg_strength, median_days_on,
n_rows_med13, n_rows_med26)`:
- `n_rows` = your original count — everything on the list;
- `book_size` = max rank denominator among ranked rows; when a sector has no
  ranked row that week, **carry the last known value forward** and stamp
  `book_size_asof` so the age is visible (Global Tech, Sep 14);
- sector strings normalized through a small map before grouping (dev: confirm
  DB copy is already clean with `SELECT DISTINCT sector, analyst`).

## C. Positions columns

`You $` / `You %` per theme = sum of `drv_category_perf.market_value` over the
theme's mapped categories (sector / asset_class / style), both brokers.
`Fit` = ✓ (exposure and stance agree) · ⚠ exposed (bear stance, you hold) ·
⚠ conflict (quad vs lists) · ○ none (bull stance, no position) · ~ (split).
Headline strip: total · % cash & short FI · risk $ split by bull / bear / split
themes · bull themes with no position.

## D. CALL — included with a caveat

CALL (The Call, daily, stock-level long/short) appears in the theme grid
**muted, dashed, half-weight, never counted in `agree_n`**, mapped to themes via
`ref_sector`. Reason, in the user's words: SSS drives its outlook, so it is not
independent evidence. It is the only source with explicit single-stock shorts.

**Validation rule (D1):** in `v_source_edge_scorecard` and any theme-level
scorecard, **score CALL longs and CALL shorts as two separate series**, never
pooled. July's pooled measurement gave CALL +0.52% (n=7,945); its sell-family
alone measured +5.26% (n=82). If the short leg holds up on more data it earns a
seat in the vote for bear stances only; the long leg stays muted regardless.
Same split for every other source that carries both sides (RR, ETF).

## E. Caveats carried into the build

1. The current-quad label is *assumed* Q3 in the mockup. The build reads it.
   The mockup's own data shows 4 lists-vs-quad conflicts under Q3 (duration,
   defensives, momentum, USD) — the headline therefore says "inflation-up,
   growth-down not confirmed" rather than claiming agreement.
2. Only Fidelity positions were in the reviewed folder; the build uses
   `drv_category_perf`, which already covers both brokers.
3. Nothing in this design touches `consolidated_action`. Every stance is
   display + scorecard. A theme stance may influence an action only after its
   own forward-return scorecard is positive on ≥ 30 samples, and only through
   the switch-gated path TASK_140/141 establish.
4. Colour: the app's `--bull #15803d` / `--bear #b91c1c` pair fails the
   colour-blindness check (deutan ΔE 4.2). The mockup uses teal `#0d9488` /
   orange-red `#c2410c`, which passes; every cell also carries a glyph (▲ ▼ –)
   so direction never rests on colour alone. Recommend adopting the pair
   app-wide, separately from this work.

## F. Correction from the live screen (2026-09-21)

The dashboard's regime line reads **Sep Q1 17% · Oct Q2 52% · Nov Q1 32% · Qtr Q4**
— the effective quad is a **Q1/Q2 blend, not Q3** as the mockup assumed.
`quad_says` must be read from the same monthly-weighted stance
`/api/quad/band-factors` already produces (the Quad Rotation tiles' ▲/▼),
never a single hard-coded quad. Under the Q2-dominant blend the lists-vs-quad
conflicts are **six**, not four — small caps, cyclicals, credit, USD, momentum,
healthcare — and the read flips: the lists are positioned **more defensively
than the model** on everything growth-sensitive. That sentence is the
headline the build computes; the mockup's Q3 wording is superseded.

## G. Placement on `/` and the Quad Rotation tiles

- **Middle column (`.cat-col`), collapsible**, in the slot the Quad Rotation
  tiles occupy today, reusing that panel's own 🧭 filter-bar toggle
  (`web/quad_rotation_panel.js`). Breadth strip (one thin row) above the
  theme grid. The nine macro rail panels stay as drill-down, **always
  visible** (reverted 2026-09-21 — shipped collapsed by default, but that
  hid panels the user relied on seeing at all times; a theme row click still
  scrolls to and highlights the matching band, it just no longer needs to
  reveal it first). Sector cards replace the Sectors rail on the right. The
  headline sentence merges into the Regime line band.
- **Quad Rotation tiles are retired, their computation is kept.**
  `/api/actionable/quad-rotation` already produces two grid columns per
  category — the quad stance (▲/▼) and price breadth (`n_above/n_tracked`,
  symbols above both Trade and Trend lines). Each tile becomes a theme-grid
  row: stance → `quad_says`; breadth → a sixth evidence column **Price**
  beside RR / ETF / PS / SSS / CALL, shown as `pct (n_above/n_tracked)` so
  Gold's 100% (2/2) no longer renders like Equities' 24% (142/590). Keep
  the per-row deep-link to Actionable (`?filter_sector=` etc.). Move
  "Country ETF" out of the Sector axis.

## H. Risk Dial — a new gauge category: positioning

All 31 gauges in `ref_risk_gauge` are price / vol / macro-data reads. None
reads the research house's own list positioning. Add `category='positioning'`
(and one `'self'`), computed in `etl/derive_risk_dial.py` from
`drv_source_breadth`, `drv_sss_breadth`, `drv_theme_stance`, `drv_category_perf`:

| gauge_key | label | fires when | weight | Sep 21 |
|---|---|---|---|---|
| `lists_derisking` | Hedgeye lists de-risking | ≥3 of 4 lists (RR macro net, ETF net, PS count, SSS rows) down >25% vs 4 wk ago | 3 | fires (4/4) |
| `etf_net_short` | ETF Pro net short | ETF longs − shorts ≤ 0 | 2 | fires (17/20) |
| `sss_book_collapse` | SSS long list collapsing | rows down ≥40% from 4-wk high | 2 | fires (86→46) |
| `rr_flip_day` | RR regime-shift day | ≥9 outlook flips in one session within the last 3 sessions | 1 | fires (Sep 17, 18) |
| `lists_quad_conflict` | Lists disagree with Quad playbook | ≥4 themes with `quad_conflict` | 2 | fires (6) |
| `exposed_bear_themes` (`self`) | Positioned against the lists | risk $ in bear-stance themes >15% of risk $ | 1 | quiet (8%) |

Rules:
1. Same shape as every existing gauge: one condition, `fired` + detail line
   naming the numbers, appears under TRIGGERED / QUIET like the rest.
2. **Budget dilution check before activation**: budget = 100 × (1 − fired
   weight / evaluable weight); the 11 new weight points shrink every existing
   gauge's share. Developer backfills the dial for the last 30 anchor dates
   with and without the new gauges and reports both series; the user
   decides weights from that, not from the defaults above.
3. Thresholds (25% / 40% / 9 flips / 4 conflicts / 15%) are the values
   observed in this session's data — starting points, tunable in
   `ref_risk_gauge.notes`/`ref_settings`, and each gauge gets a scorecard
   row (did it fire before SPX 20d drawdowns?) before its weight is trusted.
4. **Not a gauge — a cap**: when TASK_142's freshness contract flags the
   edge data behind the dial as stale, the dial keeps its budget but the
   label is suffixed ("CAUTION · edge data as of <date>"). Staleness is
   uncertainty about the reading, not a market risk, so it must not move
   the number.
