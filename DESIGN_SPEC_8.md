# Design Spec — DESIGN_WORK_8

## Goal
Show, from prices and data the app already tracks, whether the market agrees with the current Quad or is starting to move to another one (2 -> 3, 2 -> 4, and so on). The user should be able to read Hedgeye's Early Look of 2026-10-19 ("still late-stage Quad 2, not Quad 4; credit and cyclicals are the risk") straight off the Dashboard.

## Design

### The idea in one paragraph
A Quad is just two arrows: is **growth** speeding up or slowing down, and is **inflation** speeding up or slowing down. So the market check has two meters.
- **Growth meter** (-100 to +100): credit, cyclicals vs defensives, QQQ, Bitcoin, 10Y yield, copper vs gold, small caps, jobless claims.
- **Inflation meter** (-100 to +100): a commodity basket (stands in for the CRB), oil, energy stocks, the dollar (upside down), 10Y breakevens.

Compare the two meters with the arrows the declared Quad expects and you get one word: **Holding**, **Watch**, or **Transition**, plus the Quad it is leaning toward. The same two meters cover all 12 possible moves, so there is no separate rule set for each transition.

The three groups in the Hedgeye note are how the factors are **shown** (so the screen reads like the note). The two meters are how they are **counted**.

| Group shown on screen | Factors | Meter they count toward |
|---|---|---|
| 1. Risk & liquidity | QQQ, Bitcoin, 10Y yield, US Dollar | Growth (QQQ, Bitcoin, 10Y) / Inflation (Dollar, upside down) |
| 2. Inflation & commodities | Commodity basket, WTI oil, Energy stocks, 10Y breakeven | Inflation |
| 3. Growth, credit & cyclicals | HY credit spread, Cyclicals vs defensives, Copper vs gold, Small caps vs S&P, Jobless claims | Growth |

### Where it shows (recommendation: a strip chip, a drill-down, and one Risk Dial gauge; no Macro Rail column)

**1. One chip in the Macro Week strip, directly after the Quad M / Q / G chips.** This is where the Quad already lives. It costs one short chip, which matters because the rail is only about 200-380 px wide.

```
 Quad  M2 ✓  Q2 ✓  G3 ✓   [ Market: Q2 → 3  watch  54 ▸ ]   US DOLLAR 98.6 ...
                            └ growth ◆ -8   inflation ▲ +40   (2nd line only if it wraps)
```
- The chip text is `Market: Q2 holding`, `Market: Q2 → 3 watch 54`, or `Market: Q2 → 3 likely 72`.
- A small ✓ or ✗ goes after each existing M / Q / G chip. ✓ means the market's read fits that chip.
- Chip colour:
  - Holding: plain chip (existing `mw-chip`, no colour class).
  - Watch: amber (`mw-amber` / `mw-warn`).
  - Transition: the stronger amber/orange used for ⚠.
  - Red and green are **not** used on the chip, because a move like 2 -> 1 is not bearish. Red and green stay on the factor rows, where they mean up and down.
- Not enough data: grey `mw-dim` chip, `Market: not enough data`.

**2. Drill-down popover** opens when the chip is clicked. It is a wide popover, the same pattern as the existing "Book" checklist (`mwBookBtn`), and it reuses `mw-tbl`.

```
 Market check vs Quad 2 (dashboard 60-day Quad)                   as of 2026-10-16
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ Growth     ◆ -8  (unclear)   ███████░░░░░░░  needs ≥ +20 to back Quad 2        │
 │ Inflation  ▲ +40 (rising)    ██████████░░░░  backs Quad 2                      │
 │ Transition risk 54 / 100  ->  leaning Quad 3 (growth fading, inflation hot)    │
 │ Last 20 days: ▁▂▂▃▃▄▄▅▅  (risk sparkline)                                       │
 └──────────────────────────────────────────────────────────────────────────────┘
 Factor                      Says         3W      3M      Trend    Counts for
 1. Risk & liquidity
   QQQ                       ◆ mixed     -1.8%   +6.2%   above    Growth
   Bitcoin                   ▲ up        +4.1%   +9.0%   Bullish  Growth
   10Y yield                 ▲ up        +12bp   +31bp   Bullish  Growth
   US Dollar (upside down)   ▼ down*     +1.1%   +2.0%   Bullish  Inflation
 2. Inflation & commodities
   Commodity basket (CRB-like)▲ up       +2.3%   +12.4%  GSG above Inflation
   WTI oil                   ▲ up        ...
   Energy stocks (XLE)       ▲ up        ...
   10Y breakeven             ◆ flat      ...
 3. Growth, credit & cyclicals
   HY credit spread          ▼ widening  +18bp   +35bp   HYG below Growth
   Cyclicals vs defensives   ▼ lagging   ...
   Copper vs gold            ◆ mixed     ...
   Small caps vs S&P         ▼ lagging   ...
   Jobless claims            ◆ flat      ...
 What would confirm each move from Quad 2:
   • → Quad 3: growth meter at or below -20 while inflation stays up (credit, cyclicals, copper/gold, QQQ, yields rolling over)
   • → Quad 4: both meters at or below -20 (above, plus commodities, oil, energy falling; dollar rising; Bitcoin/QQQ breaking down)
   • → Quad 1: inflation meter at or below -20 while growth stays up
```
\* "Says" is the effect on the meter. For the dollar, a rising dollar is shown as **▼ (inflation down)**. The hover over that row says "Dollar rising, which points to inflation cooling". HY spread uses the same upside-down rule: widening is red, as on the rail.

Row colours follow the standing rule: ▲ green, ▼ red, ◆ amber/grey, `–` grey for missing or stale.

**3. Hover tooltip on the chip** (a bulleted list, plain English):
- Market read: Quad 2, leaning to Quad 3 (watch)
- Growth: unclear (-8). Credit spread widening, cyclicals and small caps lagging. QQQ mixed.
- Inflation: rising (+40). Commodities +12% over 3 months, oil and energy stocks up.
- Not seeing Quad 4: Bitcoin, 10Y yield and commodities are not breaking down.
- Fits your Quad chips: Monthly 2 ✓, Quarterly 2 ✓, Global 3 ✓
- Click for the factor list

The "Not seeing Quad 4" line is written from whichever factors still point against the diagonal move. That makes it the same sentence Hedgeye wrote.

**4. Risk Dial: one gauge, "Growth signals breaking the Quad"** (`quad_growth_break`, category `macro`). It fires only when the dashboard Quad is 1 or 2 (growth expected up) and the growth meter has been at or below -20 for the confirm days. That is the risk-off half of a transition. It ships **inactive** (see Rules). The other directions (2 -> 1, 3 -> 2 and so on) are not risk for sizing, so they never move the dial.

**5. Macro Rail: no new column.** Only about 14 rail rows are factors, so a column would be blank on most of the 50+ rows and squeeze a crowded rail. The rail already shows these symbols' Day / 1WK / 3W / 3M returns. The drill-down adds the meaning.

### Worth reconsidering
- **A separate panel.** The middle-left column is already crowded (Hedgeye panel, Macro Rail, Signal Strength, Themes). The whole read fits in one chip plus a popover, so a full panel would repeat the strip.
- **A gauge for each factor in the Risk Dial.** Thirteen new gauges would double-count things the Dial already watches (credit stress, IG/BBB spread widening, claims rising, oil shock, dollar strong) and would swamp the budget. One roll-up gauge is enough.

## Rules & numbers

### Factor list (seed rows for `ref_quad_factor`)
Every factor is read from its own up to three checks: **3W move**, **3M move**, and **Trend**. "3W" means today vs the close on or before 21 calendar days ago, and "3M" means 3 calendar months back. These are the same bases the rail's 3W / 3M columns use. Data comes from `hist_td` closes (latest sequence per day) and `hist_macro` (FRED).

| # | Factor | Data | 3W band | 3M band | Trend check | Meter | Direction | Weight |
|---|---|---|---|---|---|---|---|---|
| G1 | QQQ | `QQQ` close | ±1% | ±2% | price vs Trend line (`drv_technicals.a_trend_value`) | Growth | normal | 1 |
| G2 | Bitcoin | `/BTC` close | ±3% | ±6% | Hedgeye RR outlook (`drv_rr`) | Growth | normal | 1 |
| G3 | 10Y yield | FRED `DGS10` change | ±10bp | ±20bp | `TNX:CGI` RR outlook | Growth | normal | 1 |
| G4 | HY credit spread | FRED `BAMLH0A0HYM2` change | ±10bp | ±20bp | `HYG` vs Trend line | Growth | upside down (spread widening = growth down; HYG above trend = growth up) | 1 |
| G5 | Cyclicals vs defensives | avg(XLI, XLY, XLF, XLB) minus avg(XLU, XLP, XLV) | ±1 pt | ±2 pt | none (2 checks, both must agree) | Growth | normal | 1 |
| G6 | Copper vs gold | `/HG` minus `/GC` return | ±1 pt | ±2 pt | none | Growth | normal | 1 |
| G7 | Small caps vs S&P | `IWM` minus `SPX` return | ±1 pt | ±2 pt | none | Growth | normal | 0.5 |
| G8 | Jobless claims | FRED `ICSA` 4-week avg vs 13-week avg | — | — | single check: 4-wk avg ≥5% above 13-wk = down, ≥5% below = up | Growth | upside down | 0.5 |
| I1 | Commodity basket (CRB stand-in) | equal-weight average return of /CL /BZ /NG /HG /GC /SI /ZC /ZW /ZS /KC /SB /LE (whichever have the history) | ±1% | ±2% | `GSG` vs Trend line | Inflation | normal | 1 |
| I2 | WTI oil | `/CL` close | ±2% | ±4% | `/CL` RR outlook | Inflation | normal | 1 |
| I3 | Energy stocks | `XLE` close | ±1% | ±2% | `XLE` vs Trend line | Inflation | normal | 1 |
| I4 | US Dollar | `$DXY` close | ±0.5% | ±1% | `$DXY` RR outlook | Inflation | upside down (dollar up = inflation down) | 1 |
| I5 | 10Y breakeven | FRED `T10YIE` change | ±5bp | ±10bp | none | Inflation | normal | 1 |

Every band and weight above is a **GUESS**. They are picked so that a normal two-week wiggle reads as "flat". All of them are columns in `ref_quad_factor`, so they can be tuned without code changes.

Data we do **not** have, and the stand-in used:
- **CRB Index:** not tracked. Use I1, an equal-weight futures basket, which is closer to the CRB's even weighting than GSG alone (GSG is mostly energy). GSG is the trend check.
- **ISM / PMI:** no FRED series is loaded. Use G6 (copper vs gold) and G5 (cyclicals vs defensives), the usual market stand-ins.
- **Software (IGV):** tracked only since 2026-08-18, so it has no 3M history yet. Not a factor in v1. Add it to G1 as a second symbol once it has 3 months.
- **JNK:** not needed. FRED HY spread `BAMLH0A0HYM2` is loaded daily back to 2023, plus `HYG`.
- **Hedgeye CPI nowcast:** this is Hedgeye's forecast, not market data. It appears in the tooltip for context but does **not** vote.

### Factor state (each row)
1. Turn each available check into up (+1), down (-1) or flat (0) using its band. "Upside down" factors flip the sign after this step.
2. **Up** when at least 2 checks say up. **Down** when at least 2 say down. Otherwise **Mixed** (0).
   - With only 2 checks available, both must agree.
   - With fewer than 2 checks, the factor is **missing** and does not vote.
3. **Breakdown override:** if a factor has a Hedgeye risk range and the close is below the range low (LRR) on 2 straight days, it is Down whatever the other checks say. The tooltip then says "broke below its risk range". For the upside-down dollar, the override is a close above the range top (TRR), which counts as inflation down. **GUESS:** 2 days.

### Meters (roll-up)
- Meter = (sum of weight × state) / (sum of weights that voted) × 100. The result runs from -100 to +100, rounded to whole numbers.
- **Coverage:** if the factors that voted carry less than 60% of the meter's total weight, the meter is "not enough data" (**GUESS**: 60%).
- Each meter reads one of three ways (**GUESS**: the band is ±20):
  - **with** the Quad: the meter points the expected way by at least 20.
  - **unclear**: the meter is between -20 and +20.
  - **against** the Quad: the meter points the wrong way by at least 20.

### Which Quad we compare against
- **Reference Quad = the dashboard's own 60-day Quad.** This is the "Win" number on the Regime band. It is the same `_dominant_quad` helper in `etl/derive_risk_dial.py`, so the screen never shows two different "current quads".
- Expected arrows: Quad 1 = growth up, inflation down. Quad 2 = up, up. Quad 3 = down, up. Quad 4 = down, down.

### Transition risk, label and target (covers all 12 moves)
- Each meter's "break" = (100 − expected sign × meter) / 2.
  - This gives 0 when the meter fully backs the Quad, 50 when it is flat, and 100 when it fully opposes.
- **Transition risk = the larger of the two breaks** (0-100).
- The three labels follow from the meter readings:
  - **Holding** (risk under 40): both meters are "with".
  - **Watch** (risk 40-59): no meter is "against", and at least one is "unclear".
  - **Transition likely** (risk 60 or more): at least one meter is "against".
- **Leaning toward:** flip every meter that is "against" or "unclear", then read off the Quad.
  - Watch shows that Quad with "?".
  - If both meters flip, it is a diagonal move (2 <-> 4 or 1 <-> 3). The tooltip says "needs both growth and inflation to turn".
- The moves can be read from the two meters:
  - One meter flips: 1<->2 (inflation), 2<->3 (growth), 3<->4 (inflation), 4<->1 (growth).
  - Both meters flip: 1<->3 and 2<->4.
- **Market's own read:** if both meters are clear, it is one Quad. If one meter is unclear, it is two Quads (for example "2 or 3").
- **✓ / ✗ on the M / Q / G chips:** ✓ when that chip's Quad is inside the market's read, ✗ when it is not.
- **No flicker:** a new label only shows once it has held for 2 derive dates in a row (**GUESS**; `ref_settings.quad_check_confirm_days` = 2, 0 turns it off). Until then the chip keeps the old label and adds a small "changing" dot.

### Edge cases
- **Missing data:**
  - A missing symbol or missing check means the factor does not vote.
  - Low coverage on one meter: the label is "not enough data", grey.
  - If no reference Quad exists, the chip shows the market read alone ("Market reads Quad 2 or 3"), with no risk number and no ✓/✗.
- **Stale data** (stale factors are shown with `–` and "stale since <date>"):
  - A price close older than 3 market days before the derive date is stale.
  - A daily FRED series older than 7 days is stale.
  - Claims older than 14 days are stale.
  - One `meta_warning` per derive when any factor is stale (code `QUAD_CHECK_STALE`, screen `dashboard`), the same pattern as `AREA_DRIVER_STALE`.
- **Ties:** a meter exactly at ±20 counts as with/against, not unclear. When the two breaks are equal, risk is that value and the target flips both meters only if both are "against".
- **Yield scale:** changes always use FRED `DGS10`, so they avoid the x10 problem on `TNX:CGI`. `TNX:CGI` is used only for its outlook word.
- **Weekends and holidays:** the "on or before" lookups handle gaps. Do not count trading days.

### Risk Dial gauge
- `quad_growth_break` fires when the reference Quad is 1 or 2, the growth meter is "against" (≤ -20), and this has held for the confirm days.
- Weight 2 (**GUESS**).
- Seeded with `is_active = false` until the check below has been done (same as other unproven gauges).
- It overlaps with `quad2_overheat`. That gauge is about inflation running too hot inside Quad 2, not about growth breaking, so keep both.

### Check against real data (read-only replay run 2026-10-19, weekly from 2026-05-08)
- **Today (2026-10-16):**
  - Growth -8: credit widening, cyclicals and small caps lagging, QQQ mixed, Bitcoin and 10Y up.
  - Inflation +40: basket +12% over 3 months, oil and energy up, dollar rising pulls the other way.
  - Result: **"Quad 2 → 3 watch, 54"**, market reads "2 or 3", all three chips ✓.
  - This is Hedgeye's note: still Quad 2, not Quad 4 (inflation still up), with credit and cyclicals as the risk.
- **Earlier this year,** compared with the declared **quarterly** Quads:
  - Declared Quad 3 (April-June): the market read Quad 2 in May, then Quad 1 in June when oil and commodities fell.
  - Declared Quad 4 (July-September): the market read mostly Quad 2 / unclear from mid-July. Hedgeye then declared Quad 2 for October-December. The market read was about 10 weeks early in that one case.
  - Measured against quarterly Quads, the label would have been "Transition likely" in 19 of 24 weeks. That is why the gauge ships inactive. The real reference is the 60-day monthly blend, and monthly Quad rows only exist from 2026-09, so that version cannot be replayed yet.

### How to validate properly (and the limits)
- **History is short.** There are only about 8 months of daily closes (`hist_td` from 2026-02-02, 166 days) and 3 declared quarterly changes in that window. That is enough to show the read is sensible, not enough to prove an edge.
- **Test 1, money:** on each date, does the basket of categories the market-read Quad favours (`ref_quad_outlook`) beat the basket the reference Quad favours over the next 20 trading days? Use the same forward-return machinery as `v_factor_scorecard`.
- **Test 2, early warning:** how many weeks before a declared Quad change did the label first reach Watch or Transition, and how often did Watch fire with no change following (false alarms)?
- **Re-test when:** there are 6+ months of monthly Quad rows (about 2027-03), and 12+ months of `hist_td` (about 2027-02). FRED factors (spreads, yields, breakevens, claims) go back years, so the growth/inflation meters from FRED alone can be replayed further back as a sanity check now.

## Files likely touched
- `db/baseline.sql` — new `ref_quad_factor`, `drv_quad_factor`, `drv_quad_check` (below).
- `db/seeds_quad_factor.sql` — the 13 factor rows, the `ref_settings` rows (`quad_check_unclear_band`=20, `quad_check_min_coverage`=0.6, `quad_check_confirm_days`=2) and the `ref_risk_gauge` row `quad_growth_break` (inactive).
  - `ref_quad_factor` columns: factor_key PK, label, family 1-3, meter `growth|inflation`, direction ±1, kind `price|relative|fred_change|claims`, symbols, minus_symbols, band_3w, band_3m, trend_source `technicals|rr_outlook|none`, trend_symbol, weight, enabled, sort_order.
  - `drv_quad_factor` (one row per as_of_date + factor_key): family, meter, state -1/0/1/NULL, ret_3w, ret_3m, trend_state, breakdown flag, stale_since, weight. Idempotent DELETE + INSERT on as_of_date.
  - `drv_quad_check` (one row per as_of_date): ref_quad, growth_score, inflation_score, growth_cov, inflation_cov, growth_read, inflation_read, risk, label `HOLDING|WATCH|TRANSITION|NO_DATA`, label_shown (after the confirm days), target_quad, market_quads int[], agrees_m/q/g, detail JSONB (bullet lines for the tooltip). Idempotent.
- `etl/derive_quad_check.py` — new derive. Wired into `derive_all` after drv_rr / drv_technicals and before the Risk Dial derive. Reuses `_dominant_quad` (move it to a shared helper or import it).
- `etl/derive_risk_dial.py` — new `_g_quad_growth_break` reading `drv_quad_check`; add it to `GAUGES`.
- `api/routers/cockpit.py` — add a `quad_check` summary block to `GET /api/cockpit/macro-week`, plus new `GET /api/cockpit/quad-check?date=` returning the summary, factor rows and a 20-day risk history.
- `web/macro_week.js` — the chip, the ✓/✗ marks after the M/Q/G chips, the tooltip, and the popover (same pattern as the Book button). Bump its `?v=` in `web/index.html`.
- `web/styles.css` — a few classes for the meter bars and sparkline if the `mw-*` set lacks them.
- `docs/quad_design.md` (new "Market check" section) and a one-line Lookup row in `CLAUDE.md`.

## Open questions
- **Reference Quad:** compare against the dashboard's 60-day Quad (recommended, matches the Regime band and Risk Dial), or against the quarterly Quad (the "climate")? Note that the monthly mix for October is already 44% Quad 2 / 36% Quad 3.
- **Risk Dial gauge:** ship it inactive until the money test is run (recommended), or turn it on now at weight 2?
- **Possible bug, outside this brief:** `drv_rr.outlook` mixes "BULLISH" and "Bullish" (2 rows today). `_g_quad2_overheat` compares with `== "BULLISH"`, so the mixed-case rows can be missed. The new derive should compare case-insensitively.

## Status
READY_FOR_DEV
