# Design Spec — DESIGN_WORK_9

## Goal
Let the user pick a time period (1, 3, 6 or 12 months) and one or two "recipes" (Quad, Low volatility, Low beta,
Momentum ...). The app then builds a small portfolio of funds, explains every pick in one line, and freezes it for
the period. It tracks the portfolio on paper against SPY and against the user's real book, and shows how far the
real book is from it. Nothing in the portfolio changes until the period ends, unless the user opts in to alert-only
warnings.

> Numbering note: `DESIGN_SPEC_8.md` already exists (Quad market check, committed) but there is no
> `DESIGN_WORK_8.md`. To avoid overwriting it, this spec is number **9** and the brief is archived as
> `DESIGN_WORK_9.md`.

---

## One-page summary (plain English)

**What it is.** A new screen, **Builder**, next to Portfolio in the top menu. Four steps on one page:

1. **Pick how long:** 1, 3, 6 or 12 months.
2. **Pick a recipe:** one recipe, or two blended with a single slider (for example 60% Quad + 40% Low volatility).
3. **Pick the size:** a dollar amount, how many positions (default 10), and how much to hold in cash.
4. **See the proposed portfolio and accept it.** Each line shows the fund, its weight, its dollar amount and
   one sentence saying why it is there. Once you accept, the portfolio is frozen until its end date.

**What gets built.** v1 picks from a fixed list of about 80 liquid funds (ETFs) that the app already downloads
every day: US index funds, the 11 sector funds, style funds (momentum, low-vol, dividend, small caps), foreign
funds, bond funds, gold, commodities and the dollar. Funds are better than single stocks for a "do not touch it"
portfolio: one bad earnings report cannot sink it, and we have cleaner price history for them.

**Four recipes in v1** (all built from data we already have):

| Recipe | In plain words | Picks |
|---|---|---|
| Quad | Holds the areas Hedgeye's Quad playbook says do well over *your* time period | Funds whose sector / asset class is Bullish in the expected Quad mix |
| Low volatility | Holds the calmest stock funds | Lowest price swings over the last 3 months |
| Low beta (defensive) | Holds stock funds that move least with the market | Lowest beta to SPY |
| Momentum | Holds what has been going up and is still in an uptrend | Best 6-month return, must be above its Trend line, no Hedgeye Bearish call |

**How weights work.** Calmer funds get a bigger share ("inverse volatility"), no fund above 20%, no single area
(sector, bonds, gold ...) above 40%. If the Risk Dial says "half size", half the money sits in cash. You can turn
that off.

**"Don't touch it" means don't touch it.** The app buys the shares on paper at the accept-day close and holds
those shares to the end date. No trading in between. Optional warnings (off by default) can *tell* you if
something big happens (portfolio down 10%, the Quad check says "transition", the Risk Dial goes to "No new
risk"), but they never change the portfolio.

**Fit with your real book.** The model is tracked on paper. A "vs your book" panel shows, fund by fund, what
you hold, what the model holds, and the trades that would line them up. It never places trades and never
changes the Actionable screen. If the Actionable screen's Final Call says *Sell* on a fund the recipe wants, the
builder skips it by default and lists it under "Skipped because of a Sell call", so the two screens never
silently disagree.

**Honesty.** At the end of the period you get a report card: return vs SPY, vs your own book, and "did the
recipe do what it promised" (for example: was Low volatility really calmer than SPY?). Before you accept, a
"what would have happened" preview replays the recipe on past data, using only what was known at each past
date. **Today we have only about 9 months of daily prices** (since 2026-01-30), so the preview can honestly test
the 1-month period only. To test 3, 6 and 12 months we should load several years of fund prices from Yahoo
(the app already does this for a few symbols). Quad cannot be replayed before September 2026, because the monthly
Quad mix was not stored before then.

**Smallest useful v1:** 8 tasks of about an afternoon each (see Phasing). v2 adds High beta, All-weather,
Income, Fixed income, Commodities/gold, single stocks, dividends in returns, and e-mail warnings.

---

## Open questions (decide these first; my recommendation is first in each)

1. **Paper model or real target?** *Recommend:* paper model **plus** a read-only "vs your book" panel with the
   trades needed to match. It never feeds the Actionable screen. *Alternative:* push the "trades needed" into
   Actionable as suggestions (more clutter, and it fights the Final Call).
2. **What can it buy in v1?** *Recommend:* funds only (the ~80-fund list). *Alternative:* also single stocks
   from your stock list (about 1,000 names). That means more single-name risk over 12 months and a noisier
   back-test.
3. **Load longer price history for the back-test?** *Recommend:* yes. Add a one-off and nightly Yahoo price
   load for the ~80 funds, going back about 5 years (same method `etl/fetch_quotes.py` already uses). Without it,
   only the 1-month period can be honestly back-tested. *Alternative:* use only our own ~9 months and show "not
   enough history" for 3, 6 and 12 months.
4. **Risk Dial sizing at build time?** *Recommend:* on by default. Money invested = your size x (1 - cash %) x
   Risk Dial size multiplier, and the rest stays in cash. You can untick it. *Alternative:* ignore the dial.
5. **Final Call says Sell on a pick?** *Recommend:* skip it, take the next-ranked fund, and list the skipped fund
   with its reason. *Alternative:* keep it with a red "Conflict" tag.
6. **During the period: hold shares or hold weights?** *Recommend:* hold the **shares** bought on day 1 (true
   "set and forget": weights drift with prices, and nothing is traded until the end). The brief's "fixed target
   weights" would need a rebalance trade every month to stay true, which is tinkering. *Alternative:* fixed
   weights with a monthly paper rebalance.

---

## Design

### Where it lives
- New top-menu item **Builder** right after **Portfolio** (`NAV_LINKS` in `web/_common.js`).
- New page `/builder` (`web/builder.html` + `web/builder.js`). Not a tab inside Portfolio: `web/portfolio.js` is
  already 2,460 lines, and the builder has its own flow.
- Two views on the page, picked by a tab strip: **Build new** and **My model portfolios** (list, then detail).
- Full page width, no max-width. Reuse `.kpi-strip` / `.kpi-card`, the `pf-tab-btn` tab look, and existing CSS
  variables. Nothing new in the colour palette.

### View 1 — Build new

```
+-- Builder ------------------------------------------------------------------------------------------------+
| [Build new]  [My model portfolios (2)]                                     Data as of Fri 2026-10-23  ✓    |
+------------------------------------------+----------------------------------------------------------------+
| 1  How long                              |  PROPOSED PORTFOLIO  -  3 months  -  ends Fri 2027-01-23       |
|   ( ) 1M  (•) 3M  ( ) 6M  ( ) 12M        |  60% Quad + 40% Low volatility   -   $100,000                  |
|                                          |                                                                |
| 2  Recipe                                |  Invested $70,000  -  Cash $30,000 (Risk Dial: Caution x0.70)  |
|   Recipe A [Quad                    v]   |                                                                |
|   Recipe B [Low volatility          v]   |  Fund  Area           Weight   $       Final Call  Why here    |
|   Blend  A 60% ======o---- 40% B         |  XLK   Tech sector     11.8%  8,260   Buy more    Quad: Tech.. |
|   (B is optional: "- none -")            |  ...                                                           |
|                                          |  ---------------------------------------------------------     |
| 3  Size                                  |  Skipped because of a Sell call (1)                           |
|   Amount      [$100,000   ]              |   XLU  Utilities  Final Call: Sell some -> replaced by XLP     |
|   Positions   [10] (5-20)                |                                                                |
|   Cash        [0 %]                      |  WHAT WOULD HAVE HAPPENED (past 3-month periods)               |
|   [x] Size by Risk Dial (now x0.70)      |   Periods tested: 4  -  Beat SPY: 3 of 4  -  Avg +1.2% vs SPY  |
|   [x] Skip funds the Final Call sells    |   Calmer than SPY: 4 of 4                                      |
|   Only from: [All funds          v]      |   [ small bar chart: each period, model vs SPY ]              |
|                                          |   Based on 5 years of fund prices. Past results only.          |
| 4  Warnings (optional, alert only)       |                                                                |
|   [ ] Tell me if the portfolio is down   |  [ Accept and freeze ]   [ Copy list ]                         |
|       10% from start                     |                                                                |
|   [ ] Tell me if the Quad check says     |                                                                |
|       "transition"                       |                                                                |
|   [ ] Tell me if the Risk Dial says      |                                                                |
|       "No new risk"                      |                                                                |
+------------------------------------------+----------------------------------------------------------------+
```

Behaviour:
- Left panel: about 340 px wide; the right panel takes the rest. Any change on the left refreshes the preview
  (debounced 400 ms).
- **Recipe dropdowns** show the recipe name plus a one-line description. A recipe that is not ready shows
  greyed out with "needs more data" in the dropdown (for example Momentum before 126 days of history).
- **Blend slider:** steps of 10%. Recipe B set to "- none -" hides the slider (100% A).
- **"Only from"** filter: All funds / Stock funds only / Bond funds only / one area (Tech, Health care, ...).
  This is how "Equities by sector/style" is offered: as a filter, not as a separate recipe. Low volatility, Low beta
  and Momentum default to "Stock funds only" (otherwise Low volatility would just pick cash-like bond funds).
  Quad defaults to "All funds".
- **Final Call column** uses the existing action badge colours (`--act-buy*` / `--act-sell*` / `--act-neutral`).
- **Why here** is shortened to one line in the grid. Hover shows the full reason as a bulleted list, for example:
  - Recipe: Quad (60% sleeve)
  - Tech is Bullish in Quad 2; the expected mix over your 3 months is Q2 71%, Q1 29%
  - Price above Trend line
  - Weight 11.8%: calmer than average (3-month swings 14% a year)
- **Accept and freeze** is disabled, with the reason shown, when:
  - the data is behind market close (same rule as the `.date-stale` warning);
  - fewer than 3 funds qualify;
  - the amount is 0.

  Clicking it asks for a name (default "Quad+LowVol 3M Oct-26") and confirms: "Frozen until Fri 2027-01-23.
  Nothing will change until then."
- **Copy list** copies `symbol, weight, dollars, shares` as tab-separated text.

### View 2 — My model portfolios (list)

```
| Name                    Recipe            Period         Day  Return   vs SPY   vs your book  Status          |
| Quad+LowVol 3M Oct-26   60% Quad/40% LV   Oct 23-Jan 23  3/63  +0.8%   +0.3%    -0.2%         Running         |
| Momentum 1M Sep-26      Momentum          Sep 25-Oct 23  done  +2.1%   +0.9%    +1.4%         Review due  (!) |
```

- Returns are green when up and red when down (`--pct-up` / `--pct-down`).
- "Review due" shows in amber (`--mr-warn`) when the end date has passed.
- A row with an alert shows a small amber dot; hover lists the alerts as bullets.

### View 3 — Portfolio detail (click a row)

```
+-- Quad+LowVol 3M Oct-26  -  day 3 of 63  -  frozen since Fri 2026-10-23 --------------------------------+
| [Return +0.8%] [vs SPY +0.3%] [vs your book -0.2%] [Worst drop -1.1%] [Swings 9% vs SPY 13%] [Alerts 0]  |
|                                                                                                          |
| [ line chart: model $ (blue --cat1), same $ in SPY (grey), your book's return (teal --cat2) ]            |
|                                                                                                          |
| Holdings   Fund  Shares  Entry   Now     Return  Weight now  Final Call now   Why here                    |
|            XLK   31      266.45  270.10  +1.4%   12.0%       Buy more        Quad: Tech is Bullish ...   |
|                                                                                                          |
| vs YOUR BOOK  (compare to: [Whole book v] scaled to $100,000)                                             |
|   Fund  Model $   You hold $   Gap $     Trade to match                                               |
|   XLK   8,260     12,400       -4,140    Sell 15 sh   (only if you want to match - not advice)          |
|   XLP   7,900     0            +7,900    Buy 98 sh                                                    |
|   NVDA  -         9,800        -         Held, not in model                                           |
|   Matches model: 38%                                                                                    |
|                                                                                                          |
| PROMISE CHECK (fills in as days pass; final at the end)                                                 |
|   Low volatility: calmer than SPY?   9% vs 13%  ✓ so far                                                |
|   Quad: Quad 2 still the call?       Market check: HOLDING  ✓                                           |
|   Hit rate: funds beating SPY         6 of 10                                                           |
|                                                                                                          |
| [ End-of-period review ]  (enabled from the end date)                                                   |
+----------------------------------------------------------------------------------------------------------+
```

**End-of-period review** (opens on or after the end date; it never runs by itself):
- A final report card: return, vs SPY, vs your book, worst drop, swings vs SPY, promise result, hit rate.
- A fresh preview with the same settings on today's data, with a "what changes" list (keep / add / drop and
  shares).
- Three buttons:
  - **Roll over**: freeze the fresh build as a new portfolio linked to the old one.
  - **Change recipe**: go to Build new with the settings pre-filled.
  - **Close**: stop tracking and keep the history.

### Colours and wording
- Green = up, red = down, through the existing `--pct-up` / `--pct-down`. Action badges reuse the
  `--act-*` set. Alerts and "review due" use `--mr-warn` / `--mr-warn-bg`.
- Chart lines: model `--cat1`, SPY `--neutral`, your book `--cat2`.
- Plain labels only: "Swings" (not volatility), "Moves with market" (not beta, but "beta" in the tooltip),
  "Worst drop" (not max drawdown).
- Disclaimer line under the preview and the review: "This applies your chosen recipe mechanically. Past results
  only, not a forecast."

---

## Rules & numbers

### R0 — The fund list (universe)
- New seed table `ref_pb_universe`: one row per fund with `tos_symbol`, `area` (for example "US broad", "Tech
  sector", "Long bonds", "Gold"), `sleeve` (equity / bond / cash_like / gold / commodity / usd / crypto),
  `active`. About 80 funds. Start from what the app already uses: the 11 sector funds (`_SECTOR_ETF`), SPY, QQQ,
  IWM, DIA, the style funds (MTUM, SPLV, VYM, USMV if present), EEM, EFA, EWJ, EWZ, EWG, TLT, IEF, HYG, LQD,
  BUXX, CLOX, CLOZ, GLD, SLV, GSG, UUP, IBIT. Task 1 adds the missing common ones (SHV, BIL, AGG, BND, TIP, VTV,
  VUG, SPHB, MDY, QUAL, USMV, DBC) to the daily TOS export through the existing `ref_my_stocks` /
  `drv_symbol_tier` route.
- No leveraged or inverse funds (curated list, so this is by construction).
- **Eligible on build day D** only if all of these hold:
  - the fund is in `drv_symbols` on D (it was in today's TOS export);
  - it has a price in `drv_quote` on D;
  - its average traded value over the last 20 days is at least **$5M a day** (GUESS; `drv_technicals.volume`
    x price);
  - it has enough history for the recipe (see each recipe).
- A fund missing from today's TOS export cannot be picked that day. It is listed under "Not available today".

### R1 — Shared measures (all from daily closes, using only data up to D)
- **Daily return** = close(t) / close(t-1) - 1, using `drv_quote.last_price` per anchor date. Once the long Yahoo
  history exists (Q3), use `hist_quote_daily` for dates before our own history starts. Our own close wins on
  any day both have.
- **Swings (vol63)** = standard deviation of the last 63 daily returns x sqrt(252). It needs at least 55 of
  the 63 returns.
- **Beta (beta126)** = covariance(fund, SPY) / variance(SPY) over the last 126 daily returns, falling back to 63
  if 126 are not available. It needs at least 55. `drv_fundamentals.beta` is only a fallback, and the tooltip
  says so.
- **6-month return, skip last month (mom)** = close(t-21) / close(t-126) - 1. It needs 126 days.
- **Above Trend line** = `last_price > drv_technicals.a_trend_value`.

### R2 — Recipe scores (v1)
Each recipe ranks the eligible funds in its "Only from" filter and takes the top **n** (n = this recipe's share
of positions, see R4).

| Recipe | Must pass | Score (higher = better) | Default filter | Needs |
|---|---|---|---|---|
| **Quad** | Quad stance > 0 | Quad stance (below); ties broken by mom, then lower vol63 | All funds | `ref_quad_periods`, `ref_quad_outlook`, `drv_quad_check` |
| **Low volatility** | has vol63 | minus vol63 (calmest first) | Stock funds | 63 days |
| **Low beta** | has beta; beta >= 0.2 (GUESS, avoids odd near-zero readings) | minus beta | Stock funds | 63 days (126 preferred) |
| **Momentum** | above Trend line; no Hedgeye **Bearish** in `drv_outlooks` (rr / etf / call) | mom, +5 points if any of rr / etf outlook is Bullish (GUESS) | Stock funds | 126 days |

**Quad stance for a fund** (reuses `etl/derive_macro.py`, no new formula):
- A fund's memberships (sector x2, asset class x1, style x0.5, fixed-income sub-class) are resolved exactly as
  in `derive_macro`. Its stance is that file's `net`.
- The Quad mix is the **horizon-matched window**: the same `window_weights` / `build_effective_distribution`
  functions, with the window length set to the holding period (1M = 30 days, 3M = 91, 6M = 182, 12M = 365)
  instead of the fixed 60 days.
- Months with no monthly row use that quarter's declared Quad (one-hot). If less than 50% of the period is
  covered at all, the preview shows "Quad outlook covers only X of your N months" and the recipe still runs on
  what is covered.
- **Transition risk** from the latest `drv_quad_check.label_shown`:
  - HOLDING: no change;
  - WATCH: mix = 75% window + 25% the `target_quad` ("leaning toward");
  - TRANSITION: 50 / 50 (GUESS).
  - NO_DATA / NO_REF: no change, and the reason line says "market check unavailable".

### R3 — Weights inside a recipe (its "sleeve")
1. **Inverse swings:** raw_i = 1 / vol63_i; w_i = raw_i / sum(raw). An "Equal weight" option exists under
   *More settings*. Risk parity is dropped: it needs a covariance model that nobody could explain in one line.
2. **Cap per fund: 20%** of the whole portfolio. If 20% x n < 100% (too few funds), the cap rises to 100% / n.
3. **Cap per area: 40%** (GUESS) of the whole portfolio, using `ref_pb_universe.area`.
4. Excess above any cap is shared out to the uncapped funds pro-rata. Repeat until nothing breaks a cap
   (max 10 passes).
5. Any fund under **3%** after capping is dropped and its weight shared out (GUESS).

### R4 — Blending two recipes (sleeves, not mixed scores)
- Blending is done as two separate sleeves, not by mixing scores: easier to explain ("60% of the money follows
  Quad, 40% follows Low volatility").
- Positions per sleeve = round(N x share), at least 3. Example: N = 10 and 60/40 gives 6 + 4.
- Each sleeve is weighted by R3 inside itself, then scaled to its share.
- **Same fund in both sleeves:** the weights add up. The "why" line names both recipes, and the freed slot goes
  to that sleeve's next-ranked fund.
- Caps (R3 steps 2-5) are applied again after merging.

### R5 — Cash and Risk Dial
- invested % = (1 - cash %) x (Risk Dial `suggested_size_multiplier` if "Size by Risk Dial" is ticked, else 1).
- The multiplier is read once at build time from `/api/cockpit/risk-dial` for D and stored on the portfolio. It
  is frozen afterwards: the dial is never applied mid-period.
- If the dial has no reading for D, the multiplier is 1 and the preview says "Risk Dial unavailable, full
  size".
- Cash earns 0% in v1, and the label says so. v2 may use BIL/SHV as a cash proxy.

### R6 — Final Call check
- For each pick, read `drv_actionable.consolidated_action` on D.
  - **Sell family** (SA, SS, STM, SO, SW, SWW, REMOVE, REDUCE) = conflict.
  - Buy family = agree.
  - Anything else = neutral.
- **"Skip funds the Final Call sells" ticked (default):** a conflicting fund is replaced by the next-ranked
  fund. It is listed under "Skipped because of a Sell call" with the action.
- **Unticked:** the fund stays, with a red "Conflict" tag in the grid.
- Funds with no `drv_actionable` row show "-" and are treated as neutral.
- During the period, "Final Call now" is shown per holding (live join, display only). A change to Sell is shown
  but changes nothing, unless the "Final Call turns Sell" warning is opted in (R8).

### R7 — Freezing and paper marks
- **Accept on anchor date D:**
  - entry price = `drv_quote.last_price` for D;
  - shares = floor(dollars / entry price) (whole shares; the leftover goes to cash);
  - start = D, end = D + 1/3/6/12 calendar months;
  - the last mark is the last anchor date on or before the end date.
- **Accepting during market hours:** the entry price is that day's close, filled in by the evening derive.
  Until then the portfolio shows "Pending close price".
- **Daily mark** (each derive for anchor date D, for every Running portfolio): value = sum(shares x close) +
  cash.
- **Missing close:**
  - carry the last close forward and count stale days;
  - after **3 stale trading days** (GUESS), raise the "data problem" alert (always on, alert only).
- **Splits:** a daily move bigger than ±40% on a fund flags "possible split, check" and the alert shows. v1 does
  not auto-adjust shares.
- **Dividends:** v1 counts price only, which understates income funds. The detail page says "Price return,
  dividends not included". v2 adds them.
- **SPY line:** the same starting dollars put into SPY at its D close.
- **Your book line:** the whole book's time-weighted return over the same dates, using the TWR method that
  `etl/derive_category_perf.py::_twr_window` already uses. The flows-confidence colour is shown, so an amber
  "suspect" reading is visible.

### R8 — Warnings (opt-in, alert only, never change holdings)

| Warning | Fires when | Default |
|---|---|---|
| Portfolio drop | value is down 10% or more from start (GUESS) | off |
| Quad turn | `drv_quad_check.label_shown` = TRANSITION | off |
| No new risk | Risk Dial label = NOT INVESTABLE | off |
| Final Call turns Sell | any holding's Final Call is now in the Sell family | off |
| Data problem | a holding has 3+ stale days, or a possible split | **always on** |

- Each warning fires once and is shown until dismissed.
- It shows as an amber dot in the list, a bulleted line on the detail page, and one `meta_warning` row
  (screen `builder`) so the dashboard status bar picks it up.
- No e-mail in v1.

### R9 — Promise check (shown live, final at the end)

| Recipe | Promise | Pass when |
|---|---|---|
| Low volatility | calmer than the market | model's daily-return swings over the period < SPY's |
| Low beta | moves less than the market | model's beta to SPY over the period < 0.8 (GUESS) |
| Momentum | trend keeps going | model return > SPY return |
| Quad | the Quad call held, and the areas worked | the market check was not TRANSITION for more than half the days, and model return > SPY |

- **Hit rate** = share of holdings whose return beat SPY's over the period.
- **Blends** list each sleeve's promise separately.

### R10 — "What would have happened" (back-test preview)
- **Start dates:** every 21st trading day going back through the history available. Each start date t is one
  period.
- **Using only data up to t:**
  - the eligible list is the funds that had a close on t (not today's list);
  - every measure (vol, beta, mom, Trend line) comes from closes up to t;
  - the Quad mix uses the `ref_quad_periods` rows as stored (see the limit below);
  - the Final Call skip is **not** replayed (that history is not kept), and the preview says so.
- **Hold:** buy at t's close, hold the shares to t + horizon, compare to SPY over the same days.
- **Shows:** number of periods, how many beat SPY, average excess return, worst period, and the promise pass
  count.
  - Fewer than 6 periods: grey text, "Too few periods to mean much".
  - 0 periods: "Not enough history yet".
- **Overlap:** 3M and longer periods overlap when starts are 21 days apart. The count shown is the number of
  **non-overlapping** periods; the average uses all of them.
- **History we really have (from project docs; must be checked in Task 1):**
  - `drv_quote` daily closes since 2026-01-30, roughly 185 trading days by now;
  - monthly Quad mix only from 2026-09.
- **Without the Yahoo backfill (Q3):**
  - 1M gives about 5 non-overlapping periods after the 63-day warm-up;
  - 3M gives 1;
  - 6M and 12M give 0;
  - Quad gives 0-1 at any horizon.
- **With a 5-year backfill:** about 58 / 19 / 9 / 4 non-overlapping periods for Low vol, Low beta and Momentum.
  Quad stays limited to its own stored months: Hedgeye's past Quad mixes are not in the database, and
  reconstructing them would be look-ahead.
- **Survivorship:** using today's fund list for old dates favours funds that survived. That is minor for large
  index funds, and the preview says it in its tooltip.

### Example output (ILLUSTRATIVE ONLY: database queries were not permitted in this design session)
3M, 60% Quad + 40% Low volatility, $100,000, 10 positions, Risk Dial CAUTION x0.70, so $70,000 is invested.
Task 1 must regenerate this table from live data and paste the real version into the task's handoff.

| Fund | Sleeve | Weight | $ | Why here (one line) |
|---|---|---|---|---|
| XLK | Quad | 9.1% | 6,370 | Tech is Bullish in Quad 2 (71% of your 3 months) |
| XLI | Quad | 8.4% | 5,880 | Industrials Bullish in Quad 2; above Trend line |
| XLF | Quad | 8.0% | 5,600 | Financials Bullish in Quad 2 |
| IWM | Quad | 6.2% | 4,340 | Small caps Bullish in Quad 2; lower weight, bigger swings |
| HYG | Quad | 5.5% | 3,850 | HY credit Bullish in Quad 2 |
| XLE | Quad | 4.8% | 3,360 | Energy Bullish in Quad 2 and Quad 3 |
| XLP | Low vol | 8.6% | 6,020 | Calmest stock fund: swings 11% a year |
| SPLV | Low vol | 7.9% | 5,530 | Swings 12% a year |
| XLV | Low vol | 6.4% | 4,480 | Swings 14% a year |
| DIA | Low vol | 5.1% | 3,570 | Swings 15% a year |
| Cash | - | 30.0% | 30,000 | Risk Dial: Caution, 0.70 size |
| *Skipped* | | | | XLU: Final Call "Sell some", replaced by DIA |

### Edge cases (summary)
- **Fund not in today's TOS export:** cannot be picked today. If it is already held in a frozen portfolio, its
  last price carries forward, and after 3 days the data alert fires.
- **Stale data on build day:** preview allowed with a banner; Accept blocked.
- **Fewer eligible funds than positions asked:** take what exists, put the rest in cash, and say "Only 7 funds
  qualified".
- **Ties:** score, then lower vol63, then symbol A-Z.
- **A fund you hold that the recipe excludes:** shown in "vs your book" as "Held, not in model". The builder
  never suggests selling it; the gap column is blank.
- **Option, cash and money-market rows in the book** (`is_cash()`): count toward the book total and show as one
  "Cash" row.
- **Two portfolios running at once:** allowed. Each is independent; there is no combined view in v1.
- **Settings or recipe rules changed after a freeze:** a frozen portfolio keeps its own copy of the settings and
  scores (stored at accept), so later rule edits never rewrite it.

---

## Data and storage

**Reads (all existing):**
- `drv_symbols`, `drv_quote` (closes), `drv_technicals` (`a_trend_value`, volume), `drv_fundamentals` (beta
  fallback), `drv_outlooks` (Hedgeye rr / etf / call outlooks).
- `ref_quad_periods`, `ref_quad_outlook`, `drv_quad_check`, plus the `derive_macro.py` functions.
- `drv_market_stat` (risk_budget / label, through the existing risk-dial API helper), `drv_actionable`
  (`consolidated_action`).
- `hist_cs` / `hist_f` through the existing portfolio holdings query (tos_symbol-normalised), the
  `derive_category_perf` TWR helper, and `hist_quote_daily` (if Q3 = yes).

**New tables** (`db/baseline.sql`; seeds in `db/seeds_portfolio_builder.sql`):

| Table | Kind | Key | Holds |
|---|---|---|---|
| `ref_pb_universe` | ref, seed | `tos_symbol` | area, sleeve, active, note |
| `ref_pb_recipe` | ref, seed | `recipe_key` | label, one-line description, default filter, min history days, params JSONB (caps, thresholds), promise text, `active`, `version` |
| `drv_pb_score` | drv, idempotent per `as_of_date` | `(as_of_date, recipe_key, tos_symbol)` | eligible, score, rank, vol63, beta, mom, quad_stance, reason JSONB, excluded_reason |
| `user_model_portfolio` | user-created | `portfolio_id` serial | name, created_at, start_date, end_date, horizon, recipe_mix JSONB, amount, cash_pct, size_multiplier, settings JSONB (incl. recipe versions), warnings JSONB, status (PENDING / RUNNING / REVIEW_DUE / CLOSED), rolled_from_id |
| `user_model_position` | user-created, write-once | `(portfolio_id, tos_symbol)` | sleeves JSONB, target_weight, entry_price, shares, why TEXT, why_detail JSONB, final_call_at_build |
| `drv_model_mark` | drv, idempotent per `as_of_date` | `(as_of_date, portfolio_id)` | value, cash, spy_value, book_twr, book_flows_confidence, stale_count, alerts JSONB |
| `drv_model_position_mark` | drv, idempotent per `as_of_date` | `(as_of_date, portfolio_id, tos_symbol)` | close, stale_days, value, return, weight_now, final_call_now |

- All `drv_*` tables use `tos_symbol`. Positions are write-once; only the `status` / `closed_at` / `warnings`
  columns of `user_model_portfolio` are updated.

**Derive step** `etl/derive_model_portfolio.py`, run in `derive_all` after `drv_actionable` and the risk-dial
step:
1. `drv_pb_score` for D.
2. Fill entry prices for PENDING portfolios whose start date = D.
3. Marks for RUNNING portfolios.
4. Warnings, then a `meta_warning` row.
5. Status changes to REVIEW_DUE once D >= end_date.

All steps are idempotent per D. The back-test uses pure functions in the same file, run on request and cached
per (D, mix, horizon, settings hash).

**API** (`api/routers/builder.py`):
- `GET /api/builder/recipes`: recipes plus readiness ("needs N more days").
- `POST /api/builder/preview`: body {horizon, mix, amount, n, cash_pct, use_risk_dial, skip_sells, filter,
  weighting}. Returns positions, skipped, unavailable, the sizing line and the back-test summary.
- `POST /api/builder/portfolios`: accept (re-runs the preview server-side for D and freezes that, never the
  client's copy).
- `GET /api/builder/portfolios`, `GET /api/builder/portfolios/{id}`: marks, holdings, promise, alerts.
- `GET /api/builder/portfolios/{id}/vs-book?scope=whole|<account>`.
- `POST /api/builder/portfolios/{id}/review` (roll / close), `PATCH /api/builder/portfolios/{id}/warnings`.

---

## Recipes: now, later, or dropped

| Recipe | Status | Reason |
|---|---|---|
| Quad-aligned | **v1** | All inputs stored; back-test limited to stored months |
| Low volatility | **v1** | Closes only |
| Low beta / defensive | **v1** | Closes only (own beta calc) |
| Momentum (Hedgeye + trend) | **v1** | Closes + Trend line + outlooks |
| High beta / offense | v2 (tiny) | Same code as Low beta, sorted the other way; can ride along in Task 2 if wanted |
| Balanced all-weather | v2 | Fixed template: stocks / long bonds / gold / commodities / cash-like, inverse-swing weighted. Needs no signal; a good "boring" baseline |
| Income / yield | v2 | `drv_fundamentals.div_yield` coverage for funds is unverified, and returns must include dividends first |
| Fixed income (duration / credit) | v2 | Only ~7 bond funds have history today; needs the Task 1 additions plus 3 months of history, or the Yahoo backfill |
| Commodities / gold | v2, inside All-weather and Quad | Only GLD / SLV / GSG are buyable funds; too few for a standalone 10-fund recipe |
| FX / currencies | **drop** | Only UUP is a buyable fund; the currency crosses are futures with no Trend line. Use UUP inside other recipes |
| Equities by sector / style | **as a filter** | "Only from: Tech" on any recipe, not a recipe of its own |

---

## Phasing (one afternoon each)

| # | Task | Done when |
|---|---|---|
| 1 | Fund list + data check: `ref_pb_universe` seed; add missing funds to the daily export; read-only report of history days, vol / beta coverage and liquidity per fund; real version of the example table | Report in the handoff; seed loads |
| 2 | Scores: shared measures (R1) + 4 recipe scorers (R2) as pure functions + `drv_pb_score` nightly; unit tests on the pure functions | Scores for D match a hand check on 3 funds |
| 3 | Build engine + `POST /api/builder/preview`: sleeves, caps, Risk Dial, Final Call skip, why lines | Preview JSON for 2 sample mixes |
| 4 | `/builder` page, Build-new view (no back-test yet) + nav item | User can see a proposal |
| 5 | Accept / freeze + `user_model_*` tables + daily marks + list and detail views (vs SPY, vs book) | A frozen portfolio marks for 2 derive dates |
| 6 | "vs your book" panel: gaps and trades to match | Shows held / not-in-model rows correctly |
| 7 | Back-test preview (R10) on own history; plus the Yahoo fund-price backfill if Q3 = yes | Shows honest period counts |
| 8 | Warnings (R8), promise check (R9), end-of-period review / roll / close | Review flow works on a back-dated test portfolio |

v2 backlog: High beta, All-weather, Income, Fixed income, a single-stock universe, dividends in returns, cash
earning BIL yield, 3-recipe blends, e-mail warnings through the existing watch digest, combined view of several
model portfolios.

### Worth reconsidering
- **12-month periods in v1.** With ~9 months of our own history and no stored Quad mix before September, a
  12M portfolio cannot be back-tested and its Quad outlook covers only the months already seeded. Offer 12M,
  but label it "untested". Or hide it until the Yahoo backfill exists.
- **Blending more than two recipes** looks flexible but makes the "why" lines and the promise check hard to
  read. Keep v1 at two.

---

## Files likely touched
- `db/baseline.sql`: 7 new tables (above).
- `db/seeds_portfolio_builder.sql`: new; fund list + 4 recipes.
- `etl/derive_model_portfolio.py`: new; scores, marks, warnings, back-test pure functions.
- `etl/derive.py`: one call in `derive_all` after actionable / risk dial.
- `etl/fetch_quotes.py` / `ref_corr_asset` (or a sibling list): long fund-price backfill, only if Q3 = yes.
- `ref_my_stocks` rows: add the missing funds to the daily export (data, not code).
- `api/routers/builder.py`: new; `api/main.py` registers it; `api/routers/pages.py` adds the `/builder` route.
- `web/builder.html`, `web/builder.js`: new page (cache-bust `?v=`).
- `web/styles.css`: a few builder-specific classes reusing existing variables.
- `web/_common.js`: one `NAV_LINKS` entry.
- `docs/portfolio_builder_logic.md`: new detail doc; plus one Lookup row in `CLAUDE.md`.
- `tests/test_portfolio_builder.py`: behaviour tests for the pure functions (weights, caps, sleeves, ties,
  back-test windows).

## Open questions
1. Paper model + read-only "vs your book" (recommended), or push trades into Actionable?
2. Funds only in v1 (recommended), or single stocks too?
3. Load ~5 years of fund prices from Yahoo for an honest back-test (recommended)?
4. Size by Risk Dial at build time, rest in cash, on by default (recommended)?
5. Skip funds the Final Call says to sell (recommended), or keep them with a Conflict tag?
6. Hold the day-1 shares to the end (recommended), or keep fixed weights with a monthly paper rebalance?
- Also for the user: GUESS numbers to confirm or tune are $5M liquidity, 20% fund cap, 40% area cap, 3% minimum
  weight, the +5 Hedgeye boost, beta >= 0.2, the WATCH/TRANSITION Quad blend, the 10% drop warning, 3 stale
  days and the 0.8 beta promise.
- Process note: the read-only database check was blocked in this session, so data ranges come from project
  docs (`drv_quote` since 2026-01-30; monthly Quad from 2026-09). Task 1 verifies them before anything is built.

## Status
READY_FOR_DEV
