# Design Spec — DESIGN_WORK_4

## Goal
Design the sell side. It should protect profits, cut losses, keep positions within limits and watch concentration. Only rules the data supports become rules; the rest become notes. This builds on the decided items in `DESIGN_SPEC_3.md`.

## Design

### Bottom line
- **Staying within limits is the only sell job with a clear edge.** Positions more than 1.25× over their max fell over the next 20 days 73% of the time (average −3.1%), against 56% for all held stocks. This held in all three periods tested.
  - **DECIDED:** "over max" is the lead sell signal. T2's "2× max" leg is replaced by a **1.25× max** leg. 2× had no edge (57%, +1.0%, 9 stocks).
- **Some existing sell sources work, some do not:**
  - **Work:** Hedgeye's **PS** and **II** list removals, and **Technical-driven** sells. Across all stocks they were 2.5–2.9 points better than doing nothing over 20 days.
  - **No edge:** Signal Strength (**SSS**), Risk-Range list (**RR**) and **ETF** list sells. Stocks rose after them at the market rate or faster.
  - **DECIDED:** those three show as **LOW CONF** (annotate only, never suppressed), the label the app already uses for unproven sells. No new pill.
- **Profit protection: no rule.** Held positions rarely carry big gains (70 of 3,611 held days had a gain of 15% or more), because you trim and buy back so often. Sells after a give-back from the high **rebounded**. Gains of 20%+ fell 73% of the time, but that is only 22 days in a few stocks. NOTE-ONLY.
- **Cutting losses: no rule.**
  - Losses of 10%+ were rare (25 days) and rebounded (+5.0% over 20 days).
  - Your own loss-cut sells (11) rebounded +14.8%.
  - Stop hits, trend breaks and "down 2 SD" days did not predict further falls.
  - An outlook turning from Bullish looked good on held stocks, but across all stocks it had no edge (52% vs 51%).
  - **The stop stays a warning, not a sell.**
- **Concentration: no edge, so a note only.** Sectors that were 25–50% of your stock book did **better** over the next 20 days than the rest of your book. Show the sector share in the tooltip, and make no rule.
- **Your own sells:**
  - **Full exits** (74% fell over 20 days), **over-max trims** (81%) and **spike trims** (70%) all beat the 67% base for this falling stretch.
  - **Loss-cuts** (40%) did worst.
- **Friday 10/9:** still **10 of 13 net sells matched** (~$86k of $95k).
  - On stocks you did **not** sell, the design would have flagged three:
    - AAPL: TRIM→MAX in F-M, 1.9× over max. You bought more.
    - XLE: TRIM→MAX in F-M and SELL ALL (PS). You bought more in IRA.
    - BLOK: SELL ALL (PS). You bought.
- **"Don't sell the low" guard (approved): a caution only, never a block. Evidence: weak.**
  - On drop days your sells did a little worse than your other sells: +0.8% over 5 days against +0.2%, but the stock rose afterwards 49% of the time either way.
  - It shows about 1.5 times a day, on held stocks down 1.5 SD or more that also carry a sell call, a STOP or a REMOVE.
  - It suggests a "sell the bounce" limit price (live price + 0.5 SD), which was reached within 5 days 65% of the time.
  - It is skipped when a Hedgeye CALL / RTA / Top-5 sell is behind the drop.
- **The sell badges add nothing new to the volume:** TRIM about 6 a day and TRIM→MAX about 2. The LIVE column stays at about 16 visible badges a day.
- **Caveat:** all held-stock numbers come from a mostly falling market (Mar–Oct; the last 8 weeks fell hard). Where a result also holds across all ~550 stocks or across periods, I say so. Otherwise treat it as weak.

### 1. Audit of today's sell machinery
**Where sells come from today:**
- **Per-source actions:** REMOVE / REDUCE from PS, II, ETF, RR, CALL, SSS, SSSCHG, RTA, TOP5 and Go-Anywhere.
- **Technical sell reads:** SELL SOME / SELL ALL / STM codes when the source says hold or buy.
- **Composite rules:** 30 SELL rules in `v_rule_scorecard`.
- **The stop:** `stop_breached`.

**Measured** from the close on the day of the call ("fell" = lower after 20 days; base = all stocks, or all held stocks):

| Sell evidence | All stocks (n, fell 20d, avg 20d) | Held stocks (n, fell 20d, avg 20d) | Verdict |
|---|---|---|---|
| Base (all stocks / all held) | 103,668 · 49% · +1.2% | 3,460 · 56% · 0.0% | — |
| **PS removal / reduce** | 489 · **61% · −1.4%** | 195 · **61% · −1.8%** | **KEEP** (moderate) |
| **II removal / reduce** | 505 · **56% · −1.7%** | few held | **KEEP** (weak–moderate) |
| **Technical-driven sell** (source not selling) | 552 · **58% · −1.3%** | 337 · 54% · +0.9% | **KEEP** (weak: works across all stocks, not on held ones) |
| CALL removal | small | 16 · 67% · −1.6% (5d: 94% fell) | KEEP (too few to judge) |
| RTA (real-time alert) sell | 189 · 52% · +0.1% | 179 · 56% · −0.1% | KEEP (weak; it is an explicit analyst call) |
| SSS change (SSSCHG) | 123 · 59% · +0.1% | 120 · 58% · +0.7% | KEEP (weak) |
| **SSS (Signal Strength) sell** | 1,613 · 47% · +1.1% | 424 · 47% · +1.5% | **DEMOTE → LOW CONF** (no edge) |
| **RR list sell** | 1,331 · 42% · +1.9% | 19 · 44% · +4.0% | **DEMOTE → LOW CONF** (worse than base) |
| **ETF list sell** | 683 · 40% · +1.7% | few | **DEMOTE → LOW CONF** (matches round 3's R4 note) |
| Stop breached | — | 391 · 55% · +0.2% | **Warning only** (unchanged pill) |
| Held stock down ≥ 2 SD on the day | — | 90 · 44% · +0.9% | **DROP** as a sell idea (rebounds) |

**Composite SELL rules** (`v_rule_scorecard`): all 30 are "unproven". Over the same period the average stock rose about +1.2% in 20 days, so a rule's `edge_20d` is better judged against −1.2 than against 0.
- **Best:** the "at or above top of range" trims, 698 / 791 (edge −0.7). Stocks rose less than average, so there is a small real edge. These are covered by T1.
- **Worst:** the "trend / trade break" and "streak going bad" rules: 893, 896, 898, 899 (SELL ALL), 784, 785 (SELL SOME), with edge −1.3 to −1.7. Stocks rose **more** than average after them, so they sold the lows.
  - **Recommendation:** these are already LOW CONF under `v_unproven_sell_rules`. Leave them there. Do not promote any composite.
- **Note:** `v_unproven_sell_rules` flags any SELL composite with `edge_20d < 0`. In a rising period that is all of them, because the test is not measured against the market. A fairer test (rule return compared with the base for the same dates) is NOTE-ONLY, for later.

**How often they fire on your held stocks** (123 position dates):
- Sell-side Final Call: 7.0 a day (SELL ALL 2.2, SELL SOME 4.2, STM 0.6)
- Stop breached: 3.2 a day
- Over max: 3.2 a day
- Most held-stock sell calls came from SSS (362 of 856), so demoting SSS removes most of the noise.

### 2. Your own sells, by reason (8/10–10/9, household net, 379 sell stock-days, $2.9M)
Reasons are assigned in this order: full exit, over max, spike trim, profit-take (gain ≥ 15%), loss-cut (loss ≥ 5%), sector ≥ 25%, other. Gain comes from the prior position file. **Base for this stretch:** held stocks fell over 20 days 67% of the time (average −2.1%).

| Kind | Count | $ | Fell 5d | Fell 20d (avg) | Bought back within 5d (cheaper) | Worth it? |
|---|---|---|---|---|---|---|
| Full exit | 140 | $1,064k | 61% | **74% (−3.1%)** | 21% (30%) | **Yes** |
| Over max | 45 | $768k | 53% | **81% (−3.1%)**, n20=21 | 87% (62%) | **Yes** |
| Spike trim | 51 | $282k | 62% | **70% (−3.8%)** | 73% (68%) | Yes, as a swing |
| Other trim | 85 | $477k | 54% | 65% (−1.1%) | 76% (62%) | Neutral |
| Sector ≥ 25% (rough: includes bond funds in the share) | 44 | $239k | 41% | 93% (−7.8%), n20=14 | 73% (50%) | Unclear: 5d rose, sample small |
| Loss-cut (loss ≥ 5%) | 11 | $55k | 55% | **40% (+14.8%)** | 36% (50%) | **No** (sold the low) |
| Profit-take (gain ≥ 15%) | 3 | $9k | — | — | — | Too few |

- **Big gains are rare in your book.** Of the 379 sells, only 4 were at a gain of 15% or more; 188 were at 0–15% and 185 at a loss. Your cost basis keeps resetting through the round trips.

### 3. Profit protection — tested, no rule (NOTE-ONLY)
Held stocks with a gain of 10% or more: 185 days, base 54% fell over 20 days (+1.3%).

| Candidate | Days | Fell 5d | Fell 20d (avg) | Result |
|---|---|---|---|---|
| Give-back ≥ 2 SD from the 60-day high | 31 | 37% | 52% (−2.1%) | No edge at 5 days |
| Give-back ≥ 3 SD | 18 | 17% | 36% (+0.7%) | **Rebounds**: would sell the low |
| At/above top of range | 63 | 46% | 54% (+0.6%) | No edge (T1 already trims these on up days) |
| Falls back through the trade line | 0 | — | — | No cases with trade-line data |
| Gain ≥ 20% (any) | 22 | 68% | 73% (−5.2%) | Promising, but a handful of stocks |

**Recommendation: NOTE-ONLY.** Add one tooltip bullet, "Gain +X% since cost", when the gain is 20% or more, and collect evidence for 3 months. T1 (spike trim) and T2 (over max) already protect profits in the way your history supports.

### 4. Cutting losses — tested, no rule (stop stays a warning)
| Candidate (held stocks) | Days | Fell 5d | Fell 20d (avg) | Note |
|---|---|---|---|---|
| Loss ≥ 10% (base) | 25 | 48% | 42% (+5.0%) | Losers rebounded |
| Stop breached | 391 | 57% | 55% (+0.2%) | Same as the base |
| Down ≥ 2 SD; with stop | 90; 29 | 55%; 48% | 44% (+0.9%); 48% (+0.6%) | Rebounds |
| Below LRR | 176 | 58% | 57% (+0.2%) | No edge |
| Trend line break today | 11 | 55% | 100% (−8.5%) | Too few; the scorecard's trend-break rules lose |
| Down ≥ 1 SD on heavy volume | 93 | 63% | 51% (−0.8%) | Short-lived |
| Outlook turned from Bullish (held) | 166 | 65% | 64% (−1.7%) | Looks good on held stocks… |
| …same, all stocks | 2,642 | 50% | 52% (0.0%) | …but no edge overall. It only worked in the 8/10+ fall (76% vs 68%) |
| Outlook turned to **Bearish** (all stocks) | 101 | 46% | 58% (−2.0%) | Small |

**Recommendation:**
- **No loss-cut rule.** The stop stays the existing STOP pill (a warning).
- **Add the "Don't sell the low" caution** (section 7b) on drop days when a sell path is active.
- **NOTE-ONLY:** one tooltip bullet, "Outlook turned from Bullish today". Score it in the Daily review for 3 months.

### 5. Limits — T2 finalised
How far over max, held stocks:

| Over max | Days/day | Stocks | Fell 5d | Fell 20d (avg) |
|---|---|---|---|---|
| 1.0–1.25×, with a price trigger (up ≥ 1 SD or ≥ 80% of range) | 0.32 | 20 | 61% (−1.4%) | 48% (+2.2%) |
| 1.0–1.25×, no trigger | 1.24 | 43 | 54% | 58% (+1.7%) |
| **More than 1.25×, any day** | **1.63** | 37 | 55% | **73% (−3.1%)** |
| …with a price trigger | 0.28 | 16 | 66% (−1.4%) | 83% (−4.4%) |
| 2× or more | 0.22 | 9 | 59% | 57% (+1.0%) |

More than 1.25× by period, against the base:
- Mar–May: 71% vs 55%
- Jun–8/9: 55% vs 46%
- 8/10 on: 96% vs 67%

It beat the base every time. **Evidence: moderate** (37 stocks, the same names on many days).

**Final T2 rule (DECIDED):** the account holds more than its max, and either:
- it is **more than 1.25× max** (any day), or
- it is over max and the live price is up at least 1 SD, or at or above 80% of the risk range.

Sell straight back to max (DECIDED).
- The 1.0–1.25× band with a price trigger is a short swing (5-day edge, none at 20 days). It still trims to max, as decided.
- Replacing 2× with 1.25× raises T2 from about 0.8 to about **1.9 badges a day**.
- Per account: each account is checked on its own (DECIDED). The 1.25× is measured on that account's rounded max.

### 6. Concentration — NOTE-ONLY
**What exists today:**
- `drv_actionable.sector` has history.
- `drv_actionable.asset_class` holds the sizing category (Call / Sig / RR …), not a real asset class.
- Area exposure (`drv_driver_exposure`) only starts on 10/1, so it cannot be tested yet.
- **Sector is the only dimension with history,** so it comes first.

**Test:** each day, each sector's share of the **stock book** (bond and cash funds such as BUXX, CLOX and CLOZ left out), then that sector's next-20-day return against the rest of the book.

| Sector share | Cases | Sector fwd 20d | Rest of book | Sector lagged the rest |
|---|---|---|---|---|
| Under 15% | 767 | −0.5% | −0.2% | 58% |
| 15–25% | 176 | −1.1% | −0.8% | 55% |
| 25–35% | 38 | +0.1% | −0.6% | 42% |
| 35–50% | 29 | +3.3% | +1.3% | 38% |

Concentrated sectors did **better**, not worse. No rule.

**Design (NOTE-ONLY):**
- One tooltip bullet on held rows: "Sector: Information Technology, 43% of your stock book" when the share is 35% or more (GUESS).
- No badge, no chip, no pill.
- On 10/8, IT was 43% and Health Care 30% of a $397k stock book.
- **Later:** area concentration (`drv_driver_exposure`), once 3 months of history exist.

### 7b. "Don't sell the low" guard (approved; caution only)
**Your sells on down days, verified** (household sell days since 3/2: 902 days, $7.8M; account 85911 ignored; measured from your sell price):

| Sells made on a day the stock closed… | Sell days | $ | Rose 5d (avg) | Rose 20d (avg) | Full exits | Filled in the day's lowest third |
|---|---|---|---|---|---|---|
| Down ≥ 1.5 SD | 97 | $1.22M | 49% (+0.8%) | 51% (−0.4%) | 73% | 32% |
| Down ≥ 2 SD | 54 | $0.79M | 40% (+0.4%) | 53% (+1.6%) | 76% | 28% |
| Other sells | 805 | $6.61M | 50% (+0.2%) | 46% (+1.1%) | 40% | 30% |
| Down ≥ 1.5 SD, bond/gold/cash funds removed (BNDD, AAAU, TLT, GLD and SD < 0.8%) | 82 | $0.83M | 49% (+0.8%) | 54% (−0.1%) | 73% | 30% |
| Down ≥ 2 SD, funds removed | 45 | $0.48M | 42% (+0.4%) | 61% (**+2.7%**) | 76% | 31% |
| Down ≥ 1.5 SD, **full exits** | 71 | $0.87M | 53% (**+1.6%**) | 52% (−0.4%) | — | 35% |
| Down ≥ 1.5 SD, **trims** | 26 | $0.36M | 38% (−1.4%) | 50% (−0.5%) | — | 23% |

**Where I differ from the coordinator's numbers:**
- I find 97 drop-day sells (not 90) out of 902 sell days (not 873).
- The 5-day result is **weaker**: 49% rose, +0.8% (not 54%, +1.9%). At ≥ 2 SD it is 40% rose, +0.4% (not 54%, +1.8%). Only the 20-day average at ≥ 2 SD (+2.7% without the funds) matches the coordinator's picture.
- Removing the low-volatility funds does not change the pattern; it was never strong.
- The clearest part is **full exits on a drop day: +1.6% over 5 days.** Drop-day trims kept falling (−1.4%).
- Held stocks down ≥ 2 SD on the day rebounded +0.9% over 5 days (+1.7% with the stop also hit), which matches section 4.

**Strength: weak.** That is enough for a reminder, not for a rule. It fits the SELL SOME caution style.

**1. Caution text** (LIVE tooltip, bulleted; shown when a held stock's live price is ≥ 1.5 SD below the prior close and a sell path is active):
- "Down 2.1 normal moves today."
- "Your past full exits on days like this: the stock was higher 5 days later on average (+1.6%), about half the time."
- "If you still want out: sell the bounce at $X (good for 5 days)."

The badge gets the same small `!` (warn colour) tag that SELL SOME uses. No new badge or chip.

**2. Sell-the-bounce price** (frozen when the caution first shows that day):
- **Rule:** a limit price = the live price when the caution first shows + **0.5 SD**, good for 5 trading days.

| Bounce target (stocks only) | Reached within 5 days | Result vs selling now |
|---|---|---|
| **+0.5 SD above the price you would sell at** (recommended) | **65%** | +0.5 SD better |
| +1.0 SD | 55% | +1 SD better, reached less often |
| Back to the prior close | 43% | +3.3%, reached too rarely |

- **Full exit:** the whole position at the bounce price. If it is not reached by day 5, the tooltip says "bounce did not come; decide again" (no automatic sell).
- **Trim:** one unit at the bounce price. Because drop-day trims kept falling (−1.4% over 5 days), the tooltip also says "trims on drop days did not recover; waiting is optional".

**3. Which sell paths can fire on a drop day:**
- The round-3 LIVE sell rules (TRIM, TRIM→MAX) fire on **rises**, so they never trigger on a drop day. The one exception is the TRIM→MAX "more than 1.25× max, any day" leg, which can show on a drop day and so carries the caution.
- These existing paths **can** fire on a drop day and carry the caution:
  - STOP pill (`stop_breached`)
  - Final Call SELL ALL / SELL SOME / STM
  - source REMOVE / REDUCE
- **Frequency:** held stocks touch −1.5 SD about 3.3 times a day; **with one of those sell paths active, about 1.5 times a day.** That is the caution count.

**4. Exceptions: no caution, sell as normal:**

| Situation on the drop day | Sell days | Rose 5d (avg) | 20d avg | Decision |
|---|---|---|---|---|
| Hedgeye CALL / RTA / Top-5 sell call behind it | 8 | 29% (−2.4%) | −5.6% | **No caution** (weak, small n, but clear direction) |
| Trend line broken today | 2 | 0% (−3.4%) | −11.0% | **No caution** (GUESS, n = 2) |
| Earnings gap (earnings date today or yesterday) | not tested | — | — | **No caution** (GUESS: news, not noise) |
| PS / II removal | 2 | 50% | −4.9% | Caution stays (too few to exempt) |
| Outlook turned from Bullish that day | 13 | **77% (+3.6%)** | +5.0% | **Caution stays.** Not an exception: these rebounded most |
| Stop breached | 10 | 50% (−0.4%) | +1.7% | Caution stays |
| None of these | 54 | 48% (+1.4%) | +0.2% | Caution |

**5. Daily review habit check, "Sold into a drop":** each sell made on a day the stock was ≥ 1.5 SD down, with its 5-day result and whether a bounce price was available and reached.

### 7. Fit into the LIVE column (from round 3)
Sell badges, in sort order (sells sort first):

| Rank | Badge | Colour | When |
|---|---|---|---|
| 0 | `TRIM→MAX` | act-sell-strong-tint | T2 (above) |
| 1 | `TRIM` | act-sell-tint | T1, spike ≥ 1.5 SD or top of range while up ≥ 1 SD |

**Tooltip bullets added for sells** (bulleted, per account):
- how far over max ("IRA: $30.9k = 1.8× the $17k max")
- gain since cost, when 20% or more (NOTE-ONLY)
- "Outlook turned from Bullish today" (NOTE-ONLY)
- sector share, when 35% or more (NOTE-ONLY)
- "Caution: STOP hit" when `stop_breached`
- "Don't sell the low" bullets and the sell-the-bounce price (section 7b) on drop days, with the warn `!` tag on the badge

**ACTION column:**
- The Final Call keeps showing SELL ALL / SELL SOME as today.
- SSS, RR and ETF list sells show the existing **LOW CONF** label, by extending the `low_confidence` condition.
- The LIVE column never changes the Final Call.

**Volume:** about 6.3 TRIM and about 1.9 TRIM→MAX a day, out of the ~16 visible LIVE badges.

### 8. Friday 10/9 replay (sells)
**Net sells (13 + ILMN wash):**

| Verdict | Stocks | ~$ |
|---|---|---|
| LIVE TRIM | XLV, ELF, NET, DT, FXH, SNOW | $47k |
| LIVE TRIM→MAX | MSFT (F-M 2.0×), TXG (IRA 1.9×, F-A 1.1× with trigger) | $33k |
| Final Call SELL SOME, kept (Technical-driven; source said INCREASE) | GTLB, TEAM | $6k |
| Near miss | PANW | $5k |
| Silent | MDB, SHOP | $4k |

- **10 of 13 matched (~$86k of $95k), unchanged.**
- Demoting SSS / RR / ETF changes no Friday match.

**Stocks you did not sell, and what the design would have said:**
- **AAPL:** TRIM→MAX in F-M ($25.5k = 1.9× the $13k max). You bought 10 more.
- **XLE:** TRIM→MAX in F-M (1.23× and at 103% of range) plus SELL ALL (PS removal, kept). You bought 175 in IRA.
- **BLOK:** SELL ALL (PS removal, kept). You bought 100.
- **ILMN:** IRA 1.2× over max with no price trigger, so the over-max pill only. SSS REDUCE is LOW CONF.
- **TWLO:** SSS REDUCE, LOW CONF.
- **HOOD:** STOP pill and "outlook turned" bullet only. No sell badge.
- **Concentration:** IT at 43% of the stock book. A tooltip bullet on IT rows only.

## Rules & numbers

### L1 — T2 over max, with the 1.25× leg — **BUILD** (DECIDED; replaces the 2× leg; `DESIGN_SPEC_3.md` T2 updated to match)
- Fires when the account is over max and either it is more than **1.25×** max, or it is up at least 1.0 SD, or at or above 80% of the range. Sells back to max.
- **Evidence:** moderate (above).
- **Edge cases:**
  - Exactly at max: not over.
  - Cash-like funds (BUXX, CLOX): skip, per the SD < 0.5% rule.
  - SELL ALL already showing: no T2 line.
  - A stale account value (more than 5 days old): no T2.
- **Numbers:** 1.25× is set from the data, but the cut point itself is a GUESS (1.25 vs 1.5 both work). 1 SD and 80% are GUESS.

### L2 — Demote SSS / RR / ETF list sells to LOW CONF — **BUILD** (DECIDED: annotate, not suppress; `unproven_sell_mode` stays `annotate`)
- Extend `low_confidence` to be TRUE when the only sell evidence is a REMOVE / REDUCE from SSS, RR or ETF, or an unproven composite.
- No change to `consolidated_action` (annotate mode).
- **Evidence:** strong that they have no edge (n = 683–1,613 across all stocks).
- **Edge case:** if a kept source (PS, II, CALL, RTA, SSSCHG, Technical) also says sell, there is no demotion.

### L3 — Keep PS / II / Technical / CALL / RTA / SSSCHG sells as they are — **KEEP**

### L4 — Stop stays a warning — **KEEP** (no change). No loss-cut rule — **DROP**.

### L5 — "Sell after a big down day" — **DROP** (rebounds).

### G1 — "Don't sell the low" caution + sell-the-bounce price — **BUILD** (approved; caution only)
- **When:** held, live price ≤ prior close − 1.5 SD, and a sell path is active (STOP, SELL ALL / SELL SOME / STM, REMOVE / REDUCE, or TRIM→MAX on the 1.25× leg).
- **Exceptions (no caution):** a Hedgeye CALL / RTA / Top-5 sell, a trend break today (GUESS) or an earnings gap (GUESS).
- **Bounce price:** live price at first caution + 0.5 SD, good for 5 trading days (65% reached).
- **Evidence: weak.** About 1.5 a day.
- **Edge cases:**
  - Low-volatility funds (SD < 0.5%): skip, as in T1.
  - A gap down: use the first live price.
  - Caution showing and you sell anyway: the Daily review logs it under "Sold into a drop".

### N1 — Gain ≥ 20% tooltip bullet — **NOTE-ONLY** (score for 3 months)
### N2 — "Outlook turned from Bullish" tooltip bullet — **NOTE-ONLY**
### N3 — Sector ≥ 35% of the stock book tooltip bullet — **NOTE-ONLY** (35% is a GUESS)
### N4 — A market-relative unproven-sell test (rule return vs same-day base) — **NOTE-ONLY**, later
### N5 — Area concentration — **NOTE-ONLY**, once 3 months of `drv_driver_exposure` exist
### Give-back from the high as a sell — **DROP** (rebounds)

### Worth reconsidering
- **Selling losers.** Your loss-cuts rebounded +14.8% (11 cases), and held losers rebounded +5%. The data says the stop is better as a prompt to review than as a reason to sell.
- **Buying into names already over max** (AAPL, XLE on Friday). That is where your own history is clearest: over 1.25× fell 73% of the time.

## Files likely touched
- `etl/derive_live_advice.py` (from round 3) — T2's 1.25× leg; new tooltip fields (gain, outlook turned, sector share).
- `etl/derive_actionable.py` — extend `low_confidence` for SSS / RR / ETF-only sells.
- `web/actionable.js` — the LIVE tooltip's sell bullets; the LOW CONF label already exists, so check it renders for the new cases (bump `?v=`).
- `db/seeds_*.sql` — `ref_settings` keys: `overmax_any_day_ratio` 1.25, `lowconf_sell_sources` 'SSS,RR,ETF', `note_gain_pct` 20, `note_sector_share_pct` 35, `dont_sell_low_sd` 1.5, `sell_bounce_sd` 0.5, `sell_bounce_days` 5.
- `docs/actionable_logic.md` (sell confidence section), `docs/live_advice_logic.md` (sell badges and notes).

## Open questions
- None. All user decisions are made.

**Notes for the developer** (checks, not decisions):
  - Sector names are inconsistent ("Health care" vs "Health Care", "Country ETF"). Normalise them before the sector bullet is built.
  - Trade-line values were missing on held rows with a gain of 10% or more, so the trade-line give-back test could not run. Check `trade_line_value` coverage.

### Build order
1. L2: LOW CONF for SSS / RR / ETF sells. Small; independent of round 3.
2. L1: T2's 1.25× leg, built with round 3's live check.
3. Sell tooltip bullets (N1–N3) and the G1 caution + bounce price, with round 3's LIVE column. The "Sold into a drop" check goes in with the Daily review.
4. N4 and N5 later.

## Consolidated build plan (specs 2, 3 and 4)
Phases ship in order. Each phase ends with something you can check on screen.

| Phase | What ships | Tables / files | What you can check afterwards | Depends on |
|---|---|---|---|---|
| **0. Quick fixes** (any time, independent) | R3: "Book-SOME" alerts read as Sell-SOME (spec 2). Area links: CRAK → Oil; BLOK and HOOD → Bitcoin (spec 2). L2: SSS / RR / ETF-only sells show LOW CONF (spec 4) | `etl/hedgeye/parsers.py`, `etl/derive_outlook_action.py`, `db/seeds_area_driver.sql`, `etl/derive_actionable.py` (`low_confidence`), `ref_settings.lowconf_sell_sources` | NET's 10/8 alert shows REDUCE. CRAK sits under the Oil tile. TWLO / ILMN SSS REDUCE show LOW CONF | — |
| **1. Per-account sizes** (spec 3 P1) | Min / max / unit = % × account value × multiplier, rounded to $1,000. Per-account over-max pill | `ref_accounts.size_mult`, `ref_asset_allocation.units_pct` (`db/baseline.sql`, seeds), `etl/derive_actionable.py`, `api/routers/dash.py`, `web/actionable.js` | The popup shows IRA / F-A / F-M sizes (Call: $4k / $17k / $2k in IRA). TXG shows "IRA over max ($30.9k / $17k)" | — |
| **2. Frozen night plan** (spec 3 D2) | Plan rows per stock per account: trim line, over-max line, dip tier and line, starter account, buy-back line. Frozen at 9:30 ET | `hist_advice_plan`, new `etl/derive_live_advice.py` (plan part) | A plan exists before the open and does not change after 9:30. The TXG trim line reads $84.24 for a day like 10/9 | Phase 1 |
| **3. Live checks** (spec 3 T1, T2 with the 1.25× leg, dip-buy Strong 1.5 / Light 2.0, buy-back, Chasing; spec 4 G1 guard and notes) | Each price pull sets a signal per plan row and saves it | `hist_advice_live`, `etl/derive_live_advice.py` (check part), hooks in `etl/yahoo_fetch.py` and `etl/etl_load.py`, `GET /api/actionable/live`, `ref_settings` keys from both specs | Rows are written every ~30 minutes while the screen is open (and at 10:00 / 15:00). About 16 visible signals a day | Phase 2 |
| **4. LIVE column** (spec 3 §6 + spec 4 §7 / 7b) | Badge, bulleted tooltip (sizes, room to range, caution, "Don't sell the low", bounce price, gain / outlook / sector notes), "Live (N)" chip, sort; Light hidden unless the chip is on | `web/actionable.js`, `web/actionable.html` (bump `?v=`) | LIVE column next to PVV. TRIM→MAX sorts first. The tooltip is bulleted per account. No new pills elsewhere | Phase 3 |
| **5. Scoring + Daily review** (spec 2 R5, spec 3 §7, spec 4 "Sold into a drop") | Household-net scoring against the plan and live checks, replacing the wrong-day scoring. Daily review tab | `etl/derive_inferred_actions.py`, `GET /api/review/daily`, `web/rule_performance.*`, docs | The 10/9 review reproduces the replay (10 of 13 sells, 8 of 20 buys) and lists "Sold into a drop" cases | Phases 2–4 (and same-day transaction files) |
| **Later / optional** | D1 (save every pull), N4 (market-relative sell scorecard), N5 (area concentration after 3 months), R4 (ETF-list drop), review file export | `hist_quote_intraday`, `v_rule_scorecard`, `drv_driver_exposure` | — | Phase 5 |

Dropped across the three rounds: R1 (replaced by T2), R2, the "trim into strength" rule, the "add to Hedgeye-bullish" rule, "% above prior close", email, the strip, the SYMBOL badge, the 5-day-high buy, loss-cut and give-back sells, and sell-after-a-big-drop.

## Status
READY_FOR_DEV
