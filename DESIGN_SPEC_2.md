# Design Spec — DESIGN_WORK_2

## Goal
Redo the Friday 2026-10-09 review using the real Schwab and Fidelity fills, not position changes. Then decide which round-1 rules and fixes are still worth building.

## Design

### Bottom line
- **The real day was bigger than round 1 thought:** 84 fills in 35 names, **$236k bought and $171k sold** (round 1 estimated $284k in total). After same-day round trips cancel out, you **net bought $148k and net sold $96k**.
- **R1 (trim back to max) still holds.** TXG, MSFT, NET and XLV were real net cuts across all your accounts, worth about $60k (63% of net sells). One change is needed: R1 must run on the **live price**. On Thursday's close it would only have caught TXG and MSFT.
- **Two round-1 labels were wrong.** TWLO was a **net add** of 18 shares, not a shuffle. CSCO was sold on **Thursday 10/8**, not Friday. The 10/8 Fidelity position file still showed it.
- **Your sells were well timed.** Dollar-weighted, you sold at 84% of the day's high-low range. Your buys sat mid-range (50%). No rule is needed here.
- **"Trim into strength" is a habit, but it is not an edge on its own.** 36% of your sells in the last 4 weeks came on days up 2% or more, against a 14% base rate. These sells were right no more often than your other sells (59% vs 59% after 20 days). Being **over max** is what makes a trim work (74% right in round 1).
- **"Adding to Hedgeye-Bullish names" is not a useful rule.** 112 of your 118 buys in the last 4 weeks were already in Hedgeye-bullish names, so it tells the app nothing new.
- **One new fix is worth building:** score trades by household net per stock per day. Cross-account moves and same-day round trips would then count as neutral. Today the app scores each account on its own, so ILMN shows up as both a sell and a buy.

### 1. Every trade on 10/9 (real fills, 401k excluded)
Accounts: **IRA** = Schwab Rollover IRA ...892, **F-A** = Fidelity 249118149, **F-M** = Fidelity 261408079. "Range" means where the fill sat in Friday's low-to-high (0% = low, 100% = high). Prices come from the 4:30 PM Yahoo row.

**Sells and net sells**

| Stock | Account | Bought | Avg buy | Sold | Avg sell | Net | Fri close | Day low–high | Sell at % of day |
|---|---|---|---|---|---|---|---|---|---|
| TXG | IRA | 200 | 81.23 | 300 | 84.33 | −100 | 80.65 | 79.16–85.12 | 87% |
| TXG | F-A | 75 | 81.24 | 175 | 83.81 | −100 | | | 78% |
| TXG | F-M | 100 | 81.30 | 150 | 83.77 | −50 | | | 77% |
| XLV | IRA | – | – | 50 | 170.38 | −50 | 170.81 | 167.52–171.03 | 81% |
| XLV | F-M | – | – | 50 | 170.92 | −50 | | | 97% |
| MSFT | F-M | – | – | 25 | 536.10 | −25 | 535.07 | 526.24–537.20 | 90% |
| MSFT | F-A | 4 | 532.23 | 1 | 535.91 | +3 | | | 88% |
| NET | IRA | 5 | 348.36 | 20 | 362.73 | −15 | 360.93 | 343.34–363.21 | 98% |
| NET | F-A | 5 | 347.95 | 25 | 362.65 | −20 | | | 97% |
| NET | F-M | 15 | 348.09 | 10 | 362.19 | +5 | | | 95% |
| ELF | IRA | – | – | 49 | 108.75 | −49 | 109.23 | 107.00–109.57 | 68% |
| ELF | F-M | – | – | 50 | 109.29 | −50 | | | 89% |
| ILMN | IRA | 25 | 276.06 | 50 | 273.50 | −25 | 278.17 | 265.25–278.59 | 62% |
| ILMN | F-M | 30 | 275.76 | 10 | 273.24 | +20 | | | 60% |
| TEAM | IRA | 10 | 203.91 | 15 | 206.17 | −5 | 206.79 | 202.01–207.37 | 78% |
| TEAM | F-A | 5 | 204.15 | 20 | 206.81 | −15 | | | 90% |
| PANW | F-A | 2 | 407.09 | 15 | 417.78 | −13 | 418.78 | 401.89–419.50 | 90% |
| SNOW | IRA / F-A | – | – | 5 / 5 | 367.98 / 367.77 | −10 | 368.89 | 345.30–369.04 | 95% |
| FXH | F-M | – | – | 25 | 130.51 | −25 | 130.15 | 128.54–130.54 | 99% |
| MDB | F-A | – | – | 8 | 387.71 | −8 | 385.93 | 371.53–387.80 | 99% |
| GTLB | F-A | – | – | 35 | 54.90 | −35 | 55.09 | 53.88–55.11 | 83% |
| DT | F-A | – | – | 25 | 63.61 | −25 | 63.50 | 61.62–63.78 | 92% |
| SHOP | F-A | – | – | 3 | 170.25 | −3 | 170.85 | 165.75–171.04 | 85% |

**Buys and net buys** (the last column shows how far the fill was above or below Thursday's close)

| Stock | Account | Bought | Avg buy | Sold | Avg sell | Net | Buy at % of day | Buy vs Thu close |
|---|---|---|---|---|---|---|---|---|
| CRWD | IRA / F-A / F-M | 40 / 10 / 50 | 267.44 / 270.33 / 270.09 | – | – | +100 | 39–62% | +1.7 to +2.8% |
| IBIT | IRA / F-A / F-M | 175 / 50 / 250 | 46.97 / 47.02 / 47.01 | – | – | +475 | 71–78% | +1.6% |
| XLK | IRA / F-M | 50 / 40 | 198.15 / 198.05 | – | – | +90 | 33–38% | +0.2% |
| META | F-A / F-M | 6 / 10 | 720.44 / 720.18 | – | – | +16 | 33–36% | −0.1% |
| XLE | IRA | 175 | 65.60 | – | – | +175 | 74% | +0.6% |
| QQQ | F-M | 15 | 749.67 | – | – | +15 | 29% | +0.3% |
| WST | IRA | 24 | 368.75 | – | – | +24 | no data | no data |
| HOOD | IRA / F-A | 15 / 55 | 109.53 / 109.45 | – | – | +70 | 87–90% | +2.3% |
| QTUM | IRA | 50 | 152.00 | – | – | +50 | 60% | +0.7% |
| TWLO | F-M (+ IRA sold 7) | 25 | 283.06 | 7 | 290.60 | **+18** | 38% | +2.6% |
| BLOK | F-M | 100 | 59.38 | – | – | +100 | no data | no data |
| PBR | IRA / F-A | 100 / 99 | 25.43 / 25.57 | 0 / 20 | – / 25.17 | +179 | 83–97% | +3.0 to +3.6% |
| MPC | IRA | 10 | 455.09 | – | – | +10 | 24% | −1.8% |
| COIN | IRA | 20 | 180.90 | – | – | +20 | 77% | +5.2% |
| AAPL | F-M | 10 | 333.09 | – | – | +10 | 30% | −2.2% |
| SHEL | IRA | 25 | 100.22 | – | – | +25 | 17% | 0.0% |
| CRAK | IRA | 65 | 66.28 | 40 | 67.01 | +25 | 21% | −1.6% |
| IGV | IRA | 75 | 111.33 | 64 | 112.32 | +11 | 42% | +1.6% |
| OKTA | F-A | 9 | 224.46 | 1 | 230.21 | +8 | 38% | +1.9% |
| BNO | IRA | 25 | 63.57 | – | – | +25 | 22% | −0.1% |
| ETHA | IRA | 25 | 56.58 | – | – | +25 | 95% | +1.6% |

- Every net figure matches the 10/8 → 10/9 position change exactly, so the position files were right. Only CSCO is different: there was no 10/9 trade, and the sale is dated 10/8.
- **Same-day round trips** (bought and sold the same stock on Friday): TXG, NET, ILMN, IGV, TEAM, CRAK, PBR, PANW, OKTA, MSFT, TWLO. Selling high and buying low inside the day made about **+$1.5k** net, mostly TXG (+$1,050 on 375 shares). ILMN lost $135, because you bought higher than you sold.

### 2. What changes from round 1

| Round-1 item | Verdict | Reason |
|---|---|---|
| **R1 trim to max on strength** | **KEEP, run on live price** | TXG (−250), MSFT (−22), NET (−30) and XLV (−100) were real household cuts, about $60k. At the fill price, NET was at 110% of its range and XLV at 83%. At Thursday's close they were at 15% and 52%, so R1 only fires on them with the live price. ILMN (net −5) and TWLO (net +18) were rightly not caught. |
| R2 bull trend, above range top | KEEP as a note only | Only DT sold above the range top (145% at fill). PANW, MDB and SHOP sold at 81–91%, so R2 would not catch them anyway. The history adds no new evidence (see §3). |
| R3 "Book-SOME" bug | KEEP (bug fix) | NET was a real net sell, at 97–98% of the day's range. It is the case the dropped alert would have flagged. |
| R4 ETF-list drop | KEEP, low priority | XLV and FXH were clean sells with no buy-back, both near the day's high. There is still not enough history to test it. |
| Look-ahead scoring bug | KEEP (bug fix) and widen it | The 10/8 row was rebuilt on Friday with Friday's close (TXG shows $80.65), so what the screen showed on Friday morning is gone. The scoring also works per account and per broker, which is the shuffle problem (see R5). |
| Area gaps (CRAK, BLOK, HOOD) | KEEP (data fix) | These are cheap links. CRAK was actually 65 bought and 40 sold, still an oil-theme trade. |
| "Chasing?" warning | KEEP, add a day-move trigger | Buys in the top 20% of the day's range were up 20 days later only 36% of the time, against 48% for buys in the bottom 20% (see §3). |
| TWLO "account shuffle" | **CORRECT** | It was a net add of 18 shares on a name already 1.5x max with a Signal Strength REDUCE. It was a real buy, not housekeeping. |
| CSCO on Friday | **CORRECT** | The sale was dated 10/8 (Thursday). Remove it from Friday's list. |

### 3. Fill quality: is there a rule?
Data: every household buy or sell day from 2026-01-30 to 10/9 (about 1,700 buy days and 1,100 sell days), with shuffle days removed. "Right" means the price moved your way. **This was a mostly falling stretch, so compare buckets with each other, not with zero.**

| Buys | Count | Right after 20 days | Median 20d |
|---|---|---|---|
| All buys | 1,728 | 40% | −2.2% |
| Fill in **bottom 20%** of the day's range | 260 | 48% | −0.5% |
| Fill in **top 20%** of the day's range | 241 | 36% | −3.1% |
| Fill 0–2% above prior close | 560 | 35% | −2.2 to −3.6% |
| Fill 3–5% above prior close | 77 | 31% | −4.5% |
| Fill 5% or more above prior close | 43 | 39% | −2.0% |

| Sells | Count | Right after 20 days | Median 20d |
|---|---|---|---|
| All sells | 1,103 | 59% | −1.4% |
| Up 2%+ on the day **and** in the top 20% of the range | 100 | 59% | −2.4% |
| Fill 3–5% above prior close | 96 | 47% | +0.8% |

- **Buying near the day's high is the clearest bad habit.** It was right about 12 points less often than buying near the day's low. On Friday it applied to about $14k (6% of buy dollars): HOOD, PBR and ETHA.
- **"% above prior close" is a noisy signal.** The pattern is not steady across buckets, so do not build a hard X% rule on it.
- **Your sells need no rule.** Friday's sells were 84% up the day's range on average, with none in the bottom 20%.

### 4. Account shuffles
- On Friday, a stock was sold in one account and bought in another on the same day only once: **ILMN** (IRA −25, F-M +20, net −5). NET and MSFT had small offsetting buys, but they were real net sells. TWLO was a real net buy.
- In the last 4 weeks this happened on 5 stock-days out of 194, and 5 days were nearly pure shuffles. It is rare, but each one is currently scored as two opposite trades.
- **Recommendation:** treat it as neutral. Score each stock once per day on the **household net** (all accounts and both brokers combined). The part that cancels out is "moved between accounts" and gets no score. See R5.

### 5. Habits over the prior 4 weeks (9/11–10/8, the same 35 names)
- **Trimming into strength:** 31 of 73 net-sell days (42%) were on a day up 2% or more. The base rate is 14% of days. **It is a real habit.**
- **Sell, then buy back:** you bought back within 5 trading days after 53% of sells (41% from Feb to Sep). The buy-back was cheaper only half the time, at a median of 0.4% *above* the sale price. **On average the cycle breaks even.** It keeps your size near max, but it does not make money.
- **Same names every week:** TXG traded on 16 of the 20 days, MSFT on 12, and NET, CRWD, OKTA, PANW and TEAM on 7–10 days each.
- **Adding to Hedgeye-bullish names:** 112 of 118 buys. Nearly everything you buy is a Hedgeye name, so a rule on it adds no information. **DROP.**

## Rules & numbers

### R1 — Trim back to max on strength — **BUILD** (recommended first)
- **Rule (unchanged from round 1):** you hold more than the max size, and either the **live price** is at or above 80% of the risk range, or the position is at least 2x max. The Final Call becomes SELL SOME, sized back to max.
- **Change:** use the latest intraday price. The hourly Yahoo refresh already re-derives the anchor date, so R1 updates within about an hour. On Thursday's close it catches TXG and MSFT only ($32k). On the live price it catches all four ($60k).
- **Size it on the household position,** across all accounts.
- **Numbers:** 80% of range is a GUESS (round-1 backtest: 78% right). 2x max is a GUESS.
- **Edge cases:**
  - Missing range or price: no fire.
  - Price older than the anchor: no fire.
  - Exactly at max: not over.
  - A sell in one account offset by a buy in another does not count as acting on it (see R5).

### R5 — Score trades on household net per stock per day — **BUILD** (new)
- **Rule:**
  - For each stock and day, add up the shares bought and sold in every account at both brokers.
  - Only the net counts as a buy or a sell.
  - The matched part counts as "round trip / moved between accounts" and is neutral.
  - Judge the net against the **previous day's** Final Call. This also fixes the round-1 look-ahead bug.
- **Source:** use the transaction files when they are loaded for that day. Fall back to position changes when they are not. Transactions carry the true trade date (CSCO = 10/8) and the real price.
- **Edge cases:**
  - Net zero: neutral, no score.
  - Net under 25% of the larger side: also neutral (GUESS).
  - Transaction file arrives late: re-score that day.
  - 401k account 85911: always excluded.

### R3 — "Book-SOME" alert dropped — **BUILD** (bug fix, unchanged)

### Look-ahead scoring bug — **BUILD** (rolled into R5)

### Area links: CRAK → Oil, BLOK and HOOD → Bitcoin — **BUILD** (seed data only)

### "Chasing?" popup line — **BUILD** (note only, never changes the call)
- **Show it on a buy candidate when either is true:**
  - The price is at or above 90% of its risk range (round 1).
  - The live price is in the top 20% of today's low-to-high range.
- **Wording:** "Near today's high. Past buys near the day's high rose 1 in 3 times; near the low, 1 in 2."
- **Numbers:** 90% and 20% are GUESS (the backtest above supports the 20%).
- **Edge cases:**
  - No intraday high or low (WST and BLOK had none): skip that trigger.
  - High equals low: skip.

### R2 — Bull trend above the range top — **NOTE-ONLY** for 4 weeks (unchanged)
Real fills add no support. Sells on up days near the high were right 59% of the time, the same as all sells.

### R4 — ETF-list drop on a held ETF — **NOTE-ONLY / later** (unchanged; Go-Anywhere history starts 10/2)

### "Trim into strength" as its own rule — **DROP**
It is a habit but not an edge (59% vs 59%). R1 already covers the version that works: over max plus a high price.

### "Add to Hedgeye-bullish" rule — **DROP**
It is true of 95% of your buys, so it carries no signal.

### "Buy more than X% above prior close" warning — **DROP**
The buckets are not steady. "Near today's high" (in the Chasing line) is the better test.

### Worth reconsidering
- **The sell-and-buy-back cycle** (TXG on 16 of 20 days) breaks even on average. It adds work, and the fills are hard to read. You could let R1 do the trimming and skip the quick buy-back unless the system says BUY. This is your call, not a rule.

## Files likely touched
- `etl/derive_actionable.py` — R1 (live price, household position, trim sized to max).
- `web/actionable.js` — R1 mirror in `finalCall()`, the trim $ amount, and the "Chasing?" line using the live day high and low.
- `etl/derive_inferred_actions.py` — R5: household net per stock per day, transaction files first, judged against the prior day's Final Call.
- `etl/hedgeye/parsers.py`, `etl/derive_outlook_action.py::_action_rta` — R3.
- `db/seeds_area_driver.sql` — CRAK, BLOK and HOOD links.
- `db/seeds_*.sql` / `db/baseline.sql` — `ref_settings` keys `trim_over_max_pos_pct` (80), `trim_over_max_mult` (2.0), `chase_day_range_pct` (80), `shuffle_net_ratio` (0.25).
- `docs/actionable_logic.md`, `docs/performance_logic.md` — document R1, R5 and the Chasing line.

## Open questions
- **R1 live:** let R1 change the Final Call (recommended), or show the trim amount in the pill only?
- **R5 neutral threshold:** count a day as a shuffle when the net is under 25% of the larger side (recommended), or only when the net is exactly zero?
- **Chasing line:** add the "near today's high" trigger to round 1's "top of risk range" trigger (recommended), or keep round 1's trigger only?
- **For the developer:** check that the drv_quote day high and low refresh hourly. The Chasing line needs them. If only the price refreshes, that trigger has to wait for the next end-of-day file.

## Status
READY_FOR_DEV
