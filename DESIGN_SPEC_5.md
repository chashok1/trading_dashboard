# Design Spec — DESIGN_WORK_5

## Goal
Give one short, ranked, per-account "Today's actions" list on the Actionable screen. It should say exactly what to do today, and mark everything else as optional or info only.

## Design

### Bottom line
- **Only two signals are required. Both are sells:**
  1. **SELL ALL** from a source we keep (PS, II, CALL, RTA, SSSCHG, Top-5) on a stock you hold.
  2. **TRIM TO MAX** when an account is **more than 1.25× its max**.
  - Together they average **about 4 stocks a day** (about 1.4 new, the rest carried over from earlier days). The most in one day was 7.
- **Everything else that has some edge is CONSIDER (optional):** buy-back, spike trim, SELL SOME from a kept source, Strong dip-buy, and the 1.0–1.25× over-max trim.
  - Each is worth only about **$10 to $200 per action** in expectation.
  - Show the top **8 stocks**, ranked by estimated dollar value. The rest go under "+N more".
- **IGNORE / INFO (never listed):**
  - LOW CONF sells and Technical-only SELL SOME
  - stop hits
  - Light dip-buys
  - Final Call buys with no price trigger (about 33 a day, no edge)
  - WAIT, chase tags and notes
  - anything under **$1,500**
- **Materiality floor: $1,500 per account order** (GUESS). It removes 11% of your real trades but only 1.6% of your dollars.
- **Placement:** one collapsible **"Today's actions" panel** above the toolbar, and one **"Act (N)" chip**. The chip **replaces** spec 3's "Live (N)" chip. The LIVE column stays as the per-row detail and now sorts by tier first. No new column and no new pill.
- **Replay, 9/11–10/9 (19 trading days with prices):**
  - **MUST DO:** 4.1 stocks a day. Of 36 required episodes, you acted the same day on 17 and 1–7 days later on 16. You never acted on 3 (WEAT, AAPL, SHEL).
  - Acting on the signal day instead of later would have been worth about **$2.5k**. The late SELL ALLs (JPM, WFC, LFST, AR) are most of that.
  - **CONSIDER:** 11.6 stocks a day on offer, so the cap of 8 bites on 16 of 19 days.
  - **Coverage:** the shown list covered **29% of your traded dollars** ($781k of $2.66M) and **56% of your net sells**. It covered only **10% of your buys**, because most of your buys were on HOLD calls (81 trades, $550k), with no live signal behind them.
- **Honest limits:**
  - Nearly every forward number comes from a falling market (8/10 on), which flatters sells and hurts buys.
  - The MUST DO tier rests on moderate evidence: limits held in every period, and SELL ALL mainly avoids big drops.
  - Nothing on the buy side earns MUST.

### 1. What acting is worth, per signal (3/2–10/9)
How to read the table:
- **Fill** is the signal's line price, or the open for overnight calls.
- **Edge** is the result versus the same-day baseline:
  - for sells, the average of all held stocks
  - for buys, the average of all Bullish non-cash, non-macro stocks
  - both measured from that day's close
- **Edge +** means acting beat doing nothing.
- **$ per action** = typical size × average 20-day edge. 5-day figures are shown where 20 days is thin.

| Signal | Per day | Typical size | 5d edge (hit) | 20d edge (hit) | $ per action (20d) | Falling-market effect | Class |
|---|---|---|---|---|---|---|---|
| **SELL ALL, kept source** | 1.4 | $5.9k (whole position) | +0.6% (58%) | **+1.3% (61%)** | ~$77; **worst 10% avoided: $2.4k each** | Mixed by period (SSSCHG −1.4% before 8/10, +5.4% after). Big-drop rate 24% vs 14% base in both | **Risk control** |
| **TRIM TO MAX > 1.25×** | 1.4 | $7.0k (excess) | +0.3% (54%) | **+2.7% (75%)** | ~$190 | Positive in both periods (+1.2% before 8/10, +5.1% after), so the size is inflated, not the sign | **Risk control (limits)** |
| TRIM TO MAX 1.0–1.25× with price trigger | 0.6 | $2.0k | +0.3% (59%) | −0.3% (49%) | ~$0 | 5-day swing only | Opportunity |
| Spike trim T1 (one unit) | 4.4 | $2.0k | +0.4% (54%) | +1.0% (61%) | ~$20 | Edge almost all from 8/10 on (+2.6% vs +0.4%) | Opportunity |
| SELL SOME, kept source | 0.9 | $2–4k | +0.5% (50%) | +1.6% (68%) | ~$40 | Mixed: 5-day sign flips by period | Opportunity |
| Technical-only SELL SOME / STM | 2.9 | $2.0k | −0.2% (52%) | 0.0% (60%) | $0 | No edge in either period | **Noise** |
| LOW CONF sell (SSS / RR / ETF) | 1.5 | $2.0k | −1.9% (44%) | **−3.4% (46%)** | **−$67** (selling lost money) | Negative in both periods | **Noise** |
| Stop breached | 3.2 | $8.0k (whole position) | +0.1% (55%) | +0.6% (60%) | ~$46 | Only positive after 8/10. Big-drop rate equals the base (14% vs 13%) | Noise (warning stays) |
| **Buy-back after your sale** | 5.3 | $7.6k | **+1.2% (55%)** | +2.1% (58%) | ~$160 | 5-day edge the same in both periods (+1.3% / +1.1%) | Opportunity (best one) |
| Strong dip, held (add one unit) | 0.5 | $2.0k | +1.0% (39%) | +2.7% (53%) | ~$55 | Small sample (59). Negative after 8/10 | Opportunity |
| Strong dip, starter at min | 2.7 | $4.0k | +0.6% (55%) | −0.7% (50%) | ~$24 (5d) | **−1.9% at 20 days after 8/10** | Opportunity (weak) |
| Light dip, sized category | 1.8 | $2–4k | +0.7–2.1% | +0.9–1.1% | ~$20–45 | Negative 5-day result after 8/10 | Noise for a list (optional in the grid) |
| Light dip, no category | 8.8 | **$0** (no category) | +0.5% (52%) | +0.2% (52%) | $0 (cannot be sized) | Negative after 8/10 | **Noise** |
| Final Call buy, no price trigger | ~33 | — | +0.4% (49%) | +0.1% | ~$0 | **−1.2% at 20 days after 8/10** | **Noise for a list** |

- "Per day" counts stock-days over 3/2–10/9. Sizes come from P1 per-account rounding.
- **Risk control, in plain words:** SELL ALL is about avoiding the big drop. After a kept-source SELL ALL, 24% of stocks fell 10% or more within 20 days, against 14% of all held stocks on the same days. Over max is about staying within limits: 75% underperformed.
- Expected dollars per action are small everywhere. The case for the MUST DO tier is protection, not expected gain.

### 2. Tiers
| Tier | Signals | Why (one line) |
|---|---|---|
| **MUST DO TODAY** | SELL ALL (kept source) on a held stock · TRIM TO MAX when the account is more than 1.25× max | The two sells where acting clearly beat holding, in both periods. They keep you within your own limits. |
| **CONSIDER** | BUY BACK · SELL SOME (kept source) · TRIM (spike) · TRIM TO MAX 1.0–1.25× with trigger · DIP BUY Strong (held add or starter) | Small positive edge, worth $10–$200 each. Your call. |
| **IGNORE / INFO** | LOW CONF sells · Technical-only SELL SOME / STM · stop hit · Light dip · Final Call buy with no trigger · WAIT · chase · notes (gain, outlook, sector) · anything below $1,500 | No edge, a negative edge, or too small to matter. These still show in the grid. |

- There are **no buys in MUST DO**. That follows your principle: a missed buy costs only an opportunity.

### 3. Daily budget and ranking
- **MUST DO: 5 stocks** (GUESS). The replay averaged 4.1 and went over 5 on 5 of 19 days.
  - Sort by dollars at risk: the whole position for SELL ALL, the excess over max for TRIM TO MAX.
  - On a busy day, items 6 and up go under a "+N more required" line, opened by default and **never dropped**. Required sells are never hidden.
- **CONSIDER: 8 stocks** (GUESS).
  - Rank by estimated value = size × that signal's typical 5-day edge:

    | Signal | Typical 5-day edge |
    |---|---|
    | Buy-back | 1.2% |
    | Dip-buy | 0.8% |
    | SELL SOME | 0.5% |
    | Trim | 0.4% |
    | Trim to max 1.0–1.25× | 0.3% |

  - On ties, the sell comes first.
  - The rest go under "+N more", which turns on the grid's Act filter.
- **Carried items:** a MUST DO still open from an earlier day shows "since Tue (day 3)". About 2.7 of the 4.1 daily MUST DO stocks were carry-overs.

### 4. Materiality
- **Rule:** an account order under **$1,500** is not listed (GUESS). It still shows in the LIVE tooltip as "too small to list".
  - It mostly removes stubs, such as a one-share F-M remainder trimmed to $100.
  - The P1 rounding already makes every non-zero size at least $1,000, so the floor only bites on capped sizes (a held stub, or a small excess over max).
- **Your real trades below $1,500 (3/2–10/9, per account, net per stock per day):**

  | Account | Trades | Below $1,500 | Share of dollars |
  |---|---|---|---|
  | IRA | 1,959 | 212 (11%) | 1.8% |
  | F-A | 475 | 91 (19%) | 3.9% |
  | F-M | 456 | 28 (6%) | 0.5% |
  | Household (net per stock per day) | 2,525 | 12% | 1.6% |

- **One flat number, not a percent:** a percent of the account gives about the same answer (0.35% of value × multiplier is $1.25–1.6k), but it is harder to read.
- **Signal lines:** the floor removed 387 of 5,600 simulated signal lines.

### 5. One action per stock — precedence
| # | Situation | Result |
|---|---|---|
| 1 | Kept-source SELL ALL | Wins over everything. SELL ALL in every account that holds it. Blocks all buys in all accounts. |
| 2 | Any account more than 1.25× max | TRIM TO MAX in that account. **Blocks buys of that stock in every account that day.** This changes spec 3's fallback starter: AAPL's IRA starter on 10/9 would no longer show. |
| 3 | A sell in one account and a buy in another, same stock, same day | Show the sell only. The buy is noted in the tooltip, so you do not wash shares. |
| 4 | T1 and T2 in the same account | The bigger sell (spec 3). |
| 5 | TRIM and DIP BUY in the same account | Whichever fired at the later check (spec 3). |
| 6 | Sell on a ≥1.5 SD drop day ("Don't sell the low", spec 4 G1) | Same tier. The order becomes a limit at the bounce price, good for 5 days. |
| 7 | Live sell (T1 / T2) while the Final Call is a buy | The live sell shows. Limits and price beat the night call. The tooltip says "Final Call: BUY MORE". |
| 8 | Live dip-buy or buy-back while the Final Call is SELL SOME | Stays in CONSIDER with the `!` caution (spec 3). |
| 9 | Buy-back while a kept source says REMOVE | Not listed (GUESS). You sold for that reason. Example: MSOS on 10/9. |
| 10 | Final Call buy or sell with no live trigger, or LOW CONF | Not listed. Stays in the grid. |
| 11 | You marked the stock 🔭 Hold (existing LT conviction note) | MUST DO drops to CONSIDER with "you marked Hold". 🚫 Avoid blocks buys. This is the snooze; nothing new is built for it. |

**Which account:**
- **Sells:** each account acts on its own excess: the per-account max for T2, every holding account for SELL ALL. Within a stock row, the biggest dollars come first.
- **Buys:**
  - Held: one unit in each holding account below max.
  - Starter: the account with the largest dollar gap to its min (spec 3 rule, unchanged).

### 6. Wording
Each line reads like an order:
- **verb, shares, symbol, account, price, size**
- then a four-word reason
- then **Evidence: good / fair / weak**, set from section 1

| Signal | Line | Evidence |
|---|---|---|
| SELL ALL (kept) | `SELL ALL 502 XLE in F-M (~$32.6k) — PS dropped it` | good |
| SELL ALL on a drop day | `SELL ALL 502 XLE in F-M at $66.20 limit (bounce, 5 days) — PS dropped it` | good |
| TRIM TO MAX > 1.25× | `SELL 177 TXG in IRA at ~$78.60 (back to max, $13.9k) — 1.8× over max` | good |
| TRIM TO MAX 1.0–1.25× | `SELL 10 ILMN in IRA at $274+ (back to max, $2.8k) — over max, price up` | weak |
| TRIM (spike) | `TRIM 24 XLV in IRA and F-M at $169.84+ ($8k) — up 1.6 normal moves` | weak |
| SELL SOME (kept) | `SELL 60 CRAK in IRA (1 unit, $4k) — PS cut its weight` | fair |
| BUY BACK | `BUY BACK 9 META in F-A at $720.89 or less ($6.7k) — $X below your sale` | fair |
| DIP BUY, held | `ADD 6 AAPL in IRA at $X or less (1 unit, $2k) — dip on buy call` | weak |
| DIP BUY, starter | `START 10 CPAY in IRA at $395.76 or less ($4k, min) — dip on buy call` | weak |

- **Price words:**
  - "at $X+" means a sell limit at or above the line.
  - "at $X or less" means a buy limit.
  - "at ~$X" means sell now; the price shown is the live price.
- **Tooltip** (bulleted, same `_showDataPop`): the spec 3 / spec 4 LIVE tooltip bullets, plus two more:
  - "Why required: 1.8× your $17k IRA max; stocks over 1.25× fell vs your book 75% of the time"
  - "Est. value ≈ $40 (size × typical edge)"
- **Quiet states:**
  - No MUST DO: `No required actions today.` Then: `Why: nothing is over 1.25× max and no kept source says SELL ALL on a stock you hold. 6 optional ideas below.`
  - Nothing at all: `No required actions today. Nothing to consider either — no trims (nothing up 1.5 normal moves), no dip-buys, no buy-backs. Checked 10:58 ET.`
  - Stale price (older than 45 minutes): `Prices are 1 h 10 m old — the list may be out of date.`
  - No position file in 5 days: `Can't size IRA: no position file since 10/2.` That account's lines are left out.

### 7. Where it appears (one design)
```
[Hedgeye panel]
┌ Today's actions · Fri 10/9 · prices 10:58 ET ───────────────────────────────── Hide ┐
│ MUST DO (4)                                                                         │
│ 1 SELL ALL 502 XLE in F-M (~$32.6k) — PS dropped it              good               │
│ 2 SELL 177 TXG in IRA at ~$78.60 (back to max, $13.9k) — 1.8× over max   good       │
│     optional: F-A 24 sh to max · F-M trim 24 sh at $84.23+                          │
│ 3 SELL 25 MSFT in F-M (back to max, $13.1k) — 2.0× over max   good                │
│ 4 SELL 38 AAPL in F-M (back to max, $12.5k) — 1.9× over max   good   since 10/2     │
│ CONSIDER (8 of 20)                                                                  │
│ 5 BUY BACK 9 META in F-A at $720.89 or less ($6.7k) — below your sale   fair        │
│ 6 TRIM 24 XLV in IRA and F-M at $169.84+ ($8k) — up 1.6 normal moves    weak        │
│ … + 12 more · Show all live signals                                                 │
│ Not listed today: 13 Technical SELL SOME · 1 LOW CONF · 3 stop hits · 33 buy calls  │
│ with no price trigger (all still in the grid)                                       │
└─────────────────────────────────────────────────────────────────────────────────────┘
[toolbar … In headwind area (N)  Act (12) …]
[grid … PVV | LIVE | …]
```
- **Place:**
  - between `#hedgeyePanel` and `.act-toolbar`, full width, no max-width
  - open by default when MUST DO > 0
  - collapsed to one line otherwise: `Today's actions: none required · 6 to consider · 10:58 ▸`
- **Colours:** existing tokens only:
  - MUST DO rows: a 4px left border in `--act-sell-strong`
  - CONSIDER sells: `--act-sell`; CONSIDER buys: `--act-buy`
  - the "Not listed" line: muted grey
  - "since …" tag: `--warn` from day 3 on
- **Click a line:** scroll to the grid row and open its LIVE tooltip.
- **Act (N) chip:**
  - **replaces** spec 3's "Live (N)" chip, same spot and style, next to "In headwind area (N)"
  - N = MUST DO + all CONSIDER stocks
  - filters the grid to those rows
- **"Show all live signals"** (in the panel):
  - reveals INFO-tier live badges (Light dip, WAIT …) in the LIVE column
  - **replaces** spec 3's "Light hidden unless the Live chip is on"
- **LIVE column:**
  - unchanged badges
  - sort is tier first (MUST 0, CONSIDER 1, INFO 2, none 9), then spec 3's `_live_rank`
  - INFO badges draw muted
- **Unchanged:**
  - ACTION column (Final Call, OVER MAX pill, LOW CONF)
  - Trade / Trade2 buttons (see Open questions)

### 8. Replay
**Daily counts (stocks), 9/11–10/9.** 9/25 and 9/28 have no price file.

| Date | MUST DO | CONSIDER on offer (shown) | Your trades ≥ $1.5k | In MUST | In shown CONSIDER | Covered $ / yours |
|---|---|---|---|---|---|---|
| 9/11 | 5 | 22 (8) | 10 | 2 | 1 | $17k / $58k |
| 9/14 | 0 | 22 (8) | 26 | 0 | 2 | $9k / $189k |
| 9/15 | 4 | 12 (8) | 24 | 3 | 3 | $61k / $200k |
| 9/16 | 4 | 6 (6) | 4 | 0 | 0 | $0 / $34k |
| 9/17 | 4 | 12 (8) | 2 | 0 | 1 | $9k / $16k |
| 9/18 | 6 | 11 (8) | 6 | 3 | 1 | $46k / $53k |
| 9/21 | 7 | 7 (7) | 16 | 1 | 3 | $46k / $112k |
| 9/22 | 2 | 4 (4) | 25 | 0 | 1 | $6k / $222k |
| 9/23 | 2 | 13 (8) | 11 | 1 | 3 | $60k / $151k |
| 9/24 | 6 | 10 (8) | 9 | 2 | 1 | $118k / $159k |
| 9/29 | 3 | 9 (8) | 17 | 0 | 1 | $5k / $134k |
| 9/30 | 3 | 11 (8) | 9 | 1 | 0 | $13k / $46k |
| 10/1 | 3 | 11 (8) | 32 | 2 | 3 | $88k / $398k |
| 10/2 | 3 | 10 (8) | 24 | 2 | 4 | $54k / $179k |
| 10/5 | 6 | 11 (8) | 7 | 0 | 2 | $12k / $35k |
| 10/6 | 6 | 9 (8) | 22 | 3 | 5 | $102k / $234k |
| 10/7 | 4 | 9 (8) | 19 | 1 | 0 | $17k / $156k |
| 10/8 | 5 | 15 (8) | 4 | 1 | 0 | $13k / $33k |
| 10/9 | 4 | 16 (8) | 31 | 2 | 5 | $104k / $256k |
| **Total** | **77 (4.1/day)** | **220 (11.6/day)** | **298** | **24** | **36** | **$781k / $2.66M (29%)** |

**Required actions you did not take on the day** (36 episodes):
- 17 same day.
- **16 late, by 1–7 days.** Selling at the signal price instead of your later price would have been worth about **$2.5k**.
  - JPM SELL ALL on 9/15 ($25k across 3 accounts): −3.1% in 5 days; you sold 9/22.
  - WFC SELL ALL on 9/18 ($15k): −10.3% in 5 days; you sold 9/22.
  - AR, LFST and XLE were 1–2 days late.
- **3 never acted on within 5 days:**
  - WEAT SELL ALL on 9/21 ($10k, −5.6% in 5 days)
  - AAPL TRIM TO MAX on 10/2 ($12k, +1.0%: holding was fine so far)
  - SHEL SELL ALL on 10/5 (no forward data yet)
- **Not every required item paid.** The TXG TRIM TO MAX on 9/24 (you did act) was followed by +29.5%. MSFT over max went up and down.

**CONSIDER items you skipped (shown, with 5-day data):**
- 41 trims: acting would have added about **$3.6k** (stock fell 3.2% vs the book)
- 64 buy-backs: skipping saved about $5.1k
- 14 dip-buys: skipping saved about $1.8k
- 7 SELL SOME: skipping saved about $0.5k
- In a falling stretch, skipping buys was right and skipping trims was wrong. Do not read more into 14 days.

**Your trades that would have been IGNORE / not listed** (213 of 298):
- **31 matched only INFO signals ($305k):**
  - Light dip-buys: 16 ($161k)
  - LOW CONF or Technical sells: 13 ($126k)
  - Stops: 2–3
- **182 had no live signal at all ($1.44M), by last night's Final Call:**

  | Trade | Final Call | Trades | $ |
  |---|---|---|---|
  | Buys | HOLD | 81 | $550k |
  | Sells | HOLD | 26 | $246k |
  | Buys | buy-side, no dip | 21 | ~$190k |
  | Buys | SELL SOME | 13 | $130k |
  | Sells | STM | 7 | $80k |
  | The rest | | | |

**Friday 10/9 — the exact list:**
- **MUST DO (4):**
  1. `SELL ALL 502 XLE in F-M (~$32.6k) — PS dropped it`. **You bought $11.5k in IRA (against).**
  2. `SELL 177 TXG in IRA at ~$78.60 (back to max, $13.9k) — 1.8× over max`
     - optional: F-A 24 shares to max; F-M trim 24 shares at $84.23+
     - **You: net sold $22k (match)**
  3. `SELL 25 MSFT in F-M (back to max, $13.1k) — 2.0× over max`. **You: net sold $11.8k (match)**
  4. `SELL 38 AAPL in F-M (back to max, $12.5k) — 1.9× over max`. Final Call says BUY SOME; limits win. **You bought $3.3k (against).**
- **CONSIDER (8 of 20):**
  5. `BUY BACK 9 META in F-A at $720.89 or less ($6.7k)`. You bought (match).
  6. `TRIM 24 XLV in IRA and 24 in F-M at $169.84+ ($8k)`. You sold $17.1k (match).
  7. `START 10 CPAY in IRA at $395.76 or less ($4k)`. Not bought.
  8. `START 31 SXT in IRA at $129.63 or less ($4k)`. Not bought.
  9. `BUY BACK 10 CRWD in F-A at $263.01 or less ($2.5k)`. You bought $26.9k (match by direction).
  10. `TRIM 6 NET in IRA, F-M and F-A at $360.21+ ($6k)`. You sold (match).
  11. `TRIM 6 SNOW in IRA and F-A at $348.24+ ($4k)`. You sold (match).
  12. `SELL 60 CRAK in IRA (1 unit, $4k)` (trim plus PS SELL SOME). You net bought.
- **+12 more:** ELF, GTLB, TWLO, DT, FXH, IGV, ILMN (IRA to max), PANW. You sold most of them.
- **Removed by the rules:**
  - MSOS buy-back (PS says REMOVE)
  - ILMN F-M buy-back (the sell wins)
  - AAPL IRA starter (over-max block)
  - 6 stub lines under $1,500
- **Not listed:** 13 Technical SELL SOME, 3 stops, 1 LOW CONF, about 33 buy calls with no trigger.
- **Your trades not in the list:**
  - Buys on Final Call buys with no dip: COIN, QTUM, IBIT
  - Buys on HOLD calls: XLK, QQQ, WST, HOOD, PBR, SHEL, ETHA
  - Buys on SELL SOME: MPC, BNO
  - A buy against SELL ALL: BLOK
  - Sells: TEAM (Technical), MDB, SHOP
- **Coverage:** $104k of your $256k.

## Rules & numbers
### A1 — Tier, merge and rank in the live check — **BUILD**
- Each check sets `tier` (MUST / CONSIDER / INFO) on every plan row. It applies the precedence table, the $1,500 floor and the budgets.
- It stores `tier`, `list_rank`, `in_list` and `est_value` in `hist_advice_live`, so Phase 5 can score "required, not done".
- **MUST DO:** kept-source SELL ALL (`final_code` SA and `winning_source` in PS/II/CALL/RTA/SSSCHG/TOP5 with REMOVE/REDUCE), and T2 on its more-than-1.25× leg.
- **Edge cases:**
  - Stale price (older than 45 minutes): keep the last tier and show the stale line.
  - A stale position file (older than 5 days): drop that account's lines and show the "Can't size" line.
  - Ties: bigger dollars first, then sell before buy, then IRA, F-A, F-M.
  - The same stock in both MUST and CONSIDER: one row, under MUST, with the optional account lines inside.

### A2 — Budgets — **BUILD**
- MUST 5 (overflow shown, never dropped).
- CONSIDER 8 (overflow behind "+N more").
- Both GUESS. Revisit after 4 weeks of saved checks.

### A3 — Materiality floor $1,500 per account order — **BUILD** (GUESS)

### A4 — Ranking edges (5-day, from section 1) — **BUILD** as `ref_settings` keys
- buy-back 1.2, dip-buy 0.8, SELL SOME 0.5, trim 0.4, trim to max (1.0–1.25×) 0.3
- They are estimates from a mostly falling market. Refresh them from the Daily review later.

### A5 — Precedence rows 2, 3 and 9 (new) — **BUILD**
- Over 1.25× blocks buys everywhere (amends spec 3 DB "fallback starter").
- Sells win across accounts.
- A kept-source REMOVE blocks a buy-back (GUESS).

### A6 — Conviction Hold / Avoid as the snooze — **BUILD**
- Reuses `drv_actionable.conviction_direction`.

### A7 — "Today's actions" panel, Act (N) chip, tier-first LIVE sort, "Show all live signals" — **BUILD**
- Replaces the "Live (N)" chip and the Light-hidden rule of spec 3.

### A8 — "Required, not done" and "skipped CONSIDER" sections in the Daily review — **BUILD** (with Phase 5)

### N1 — Stop hits stay INFO (warning pill only) — **NOTE-ONLY**
- Re-score after 3 months. They looked better after 8/10, +1.5% at 20 days.

### N2 — Light dips with no sizing category — **NOTE-ONLY**
- 1,198 of 1,490 Light dips have no category, so their spec 3 starter is $0.
- They can never pass the floor. The LIVE tooltip should say "not in a sizing category".

### D1 — Push notifications or email for MUST DO — **DROP** (no email, by your rule)

### D2 — A separate MUST column or SYMBOL pill — **DROP** (it would duplicate the panel and the LIVE column)

### Worth reconsidering
- **Spike trims fill the CONSIDER list (about 9 account lines a day) for about $20 each.** If the list still feels busy, list a spike trim only when it is at least 2 units or the account is above the midpoint between min and max. Your own trims already run at about 2 units.
- **Trade mode starts ON and overlaps with this list.** Two "what to do" views is one too many. See Open questions.

## Files likely touched
- `etl/derive_live_advice.py` — tier, merge, floor, budget, rank, `est_value`, carried-day count
- `db/baseline.sql` — `hist_advice_live` columns `tier`, `list_rank`, `in_list`, `est_value`, `carried_days`
- `db/seeds_*.sql` — `ref_settings` keys:
  - `today_floor_dollar` 1500
  - `today_must_budget` 5
  - `today_consider_budget` 8
  - `must_overmax_ratio` 1.25
  - `must_sellall_sources` 'PS,II,CALL,RTA,SSSCHG,TOP5'
  - `rank_edge_buyback` 1.2, `rank_edge_dip` 0.8, `rank_edge_sellsome` 0.5, `rank_edge_trim` 0.4, `rank_edge_trim_to_max` 0.3
- `api/routers/dash.py` — add a `today` block (must, consider, more_count, not_listed counts, why line, price time) to `GET /api/actionable/live`. One call per refresh.
- `web/actionable.html`:
  - `#todayPanel` between `#hedgeyePanel` and `.act-toolbar`
  - the "Act (N)" chip in `#triggerSourcePills` in place of "Live (N)"
  - bump `?v=`
- `web/actionable.js`:
  - `_renderTodayPanel`
  - `act_only` and `live_all` filters
  - tier-first `_live_rank`
  - line click → scroll and open the LIVE tooltip
- `web/rule_performance.*` — Daily review sections from A8
- `docs/live_advice_logic.md` — tiers, precedence, wording; one Lookup row in `CLAUDE.md`

### Build order (slots into the consolidated plan in `DESIGN_SPEC_4.md`)
| Phase | Change from this spec |
|---|---|
| 0, 1 (in progress), 2 | No change |
| **3. Live checks** | **Extended:** A1–A6 (tier, merge, floor, budget, rank, new precedence rows, Hold snooze) and the new columns |
| **4. LIVE column** | **Extended, and partly replaced:** A7. The panel and the "Act (N)" chip replace "Live (N)". "Show all live signals" replaces the Light-hidden rule |
| **5. Scoring + Daily review** | **Extended:** A8 |
| Later | Refresh the A4 edges and the A2 budgets from 3 months of saved checks; N1, N2 |

## Open questions
- **Trade mode:** keep Trade / Trade2 as they are, and start Trade mode OFF once the panel ships? (Recommended.) Or keep Trade mode starting ON next to the panel? After 4 weeks, decide whether to retire Trade / Trade2.
- **Over 1.25× blocks buys in every account** (precedence row 2). Recommended: yes. It removes spec 3's fallback starter (AAPL in IRA on 10/9), which is exactly the case spec 4 flagged.
- **🔭 Hold as the snooze** for a MUST DO you disagree with, such as AAPL in F-M: demote it to CONSIDER. Recommended: yes. Otherwise the same item shows every day.

**Notes for the developer** (checks, not decisions):
- `hist_y` / `hist_td` have no rows for 9/25 and 9/28, although trades exist on both days.
- MSOS was a buy-back candidate on 10/9 with `consolidated_action` REMOVE from PS, while `final_code` was HOLD. Check why a PS REMOVE ends as HOLD.
- About 2 in 3 MUST DO items are carry-overs. Count `carried_days` from the saved checks, not from the night plan.

## Status
READY_FOR_DEV
