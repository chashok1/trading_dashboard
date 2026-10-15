# Design Spec — DESIGN_WORK_3

## Goal
Make the advice stay right during the day. Each night, write a fixed plan for each account. During the day, check it against the live price on every price pull and save each check. Then score every trade against the advice that was live at the time.

## Design

### Bottom line (with your decisions)
- **The plan is written at night as prices.** For every stock it gives:
  - a **trim line** and trim size
  - a **dip-buy line**
  - after a recent sale of yours, a **buy-back line**

  During the day the app only compares the live price with those lines.
- **Sizes are per account (DECIDED).** Size = category percent × that account's value (cash included) × the account's multiplier, rounded to the nearest $1,000.
  - Multipliers: IRA 1.0, F-A 2.0, F-M 1.0, all others 0.
  - Example, a Call-category stock (min / max / unit):
    - IRA $4k / $17k / $2k
    - F-A $4k / $14k / $2k
    - F-M $4k / $18k / $2k
- **The live rules:**
  1. **Trim (DECIDED, 1.5 SD).** Fires when the price is up at least 1.5 times the stock's normal daily move (its 20-day standard deviation, "SD"), or at the top of its risk range while up at least 1 SD. Size: one unit.
  2. **Over max (DECIDED).** If an account is over its max and the price is up at least 1 SD, sell straight back to max.
  3. **Dip-buy, two tiers (DECIDED).** Any Bullish-outlook stock, held or not, that falls from yesterday's close:
     - **Split thresholds (DECIDED):** measured from yesterday's close, same SD20.
     - **Strong:** last night's Final Call was buy-side. Fires at **−1.5 SD**.
     - **Light:** no buy-side call. Fires at **−2.0 SD**, shown greyed, and **hidden unless the "Live (N)" chip is on**.
     - Why the split: buys are opportunities, not risk controls, so a little more volume is fine on the Strong side. At 2.0 SD, Friday's CPAY (which you say you should have bought) and SXT (a dip from the top of its range) would have been lost.
     - No "room to the top of the range" filter and no sector preference (DECIDED). The tooltip shows room and range width so you can judge for yourself.
     - Held stock: one unit in each account that holds it.
     - Not held: a starter at the min, in **one account at a time**.
  4. **Buy-back after your own sale (DECIDED).** You sold in this account in the last 5 days, and the price is at least 0.5 SD below your sell price. It is a cheaper re-entry, not a prediction.
- **Blocks (DECIDED):** only SELL ALL or a hit stop block a buy. A plain SELL SOME shows a caution tag.
- **Everything live is shown in a new LIVE column on the Actionable grid,** built like the PVV column:
  - a coloured badge
  - a bulleted hover tooltip per account
  - a "Live (N)" filter chip
  - sorting that puts signals first

  It replaces the planned strip and the SYMBOL-cell badge. The Action popup gets no extra section; the detail lives in the tooltip.
- **Friday 10/9 replay:**
  - **Net sells: 10 of 13 match** (~$86k of $95k).
  - **Net buys: 8 of 20 match** (~$79k of $147k).
  - Friday was a strong up day:
    - **Strong at −1.5 SD fired 3 times:** AAPL, CPAY, SXT. You bought AAPL.
    - **Light at −2.0 SD fired 0 times.**
- **Badges per day** (live touch; trim 1.5 SD, Strong dip 1.5 SD, Light dip 2.0 SD):

| Badge | Per day |
|---|---|
| Trim | 6.3 |
| Back to max | ~1.9 (with the 1.25× leg, DECIDED in spec 4) |
| Dip-buy Strong (−1.5 SD) | 3.3–3.6 |
| Buy-back | ~4 |
| **Visible action badges** | **about 16 a day** |
| Dip-buy Light (−2.0 SD, hidden unless the chip is on) | 7–12 |
| WAIT (muted, not counted) | ~19 |
| Chase tag (not counted) | ~8 |

  - That is close to the target of about 15. With the chip on, the total is about 23–28.
- **Caution:** the dip-buy edge is relative, not absolute. In the last 8 weeks (a falling market), dip-buys were up only 45% after 5 days, against a 42% base for all Bullish stocks.

### 1. What intraday data exists today
| Store | What it holds | History? |
|---|---|---|
| `cache_yahoo_quote` | Today's open / high / low / last / prev close / volume, one row per stock | No; overwritten on each pull |
| Yahoo pulls | Every ~30 minutes while Actionable is open (browser-triggered, 30-minute cooldown); scheduler fallback at **10:00 and 15:00 ET** | — |
| `hist_y` | One end-of-day row per day | Daily only |
| `hist_tl` (your TOSL exports) | Intraday snapshots with volume, kept forever, 1–4 a day | Yes, irregular |
| `drv_quote` | Latest price for the anchor date | No |
| Transaction files (`hist_cst`, `hist_ft`) | Trade date and price | **No trade time** |

- Every rule needs only the latest pull: live price, day high, day low.
- Fill times are unknown, so scoring uses **price lines**, not clock times.

### 2. How you actually trim (8 weeks, 8/10–10/9, IRA + F-A + F-M, household per stock per day)
- **402 sell days:** 140 full exits (on down days, low in the range) and 262 partial trims.
- **Partial trims:**
  - median fill +0.6 SD above the prior close (18% at +1.5 SD or more)
  - median 69% of the risk range
  - 77% were followed by a buy-back within 5 days

| Day high reached (held stocks) | Held stock-days | You sold on |
|---|---|---|
| Any day | 1,828 | 22% |
| +1 SD | 491 | 31% |
| **+1.5 SD** | **254** | **36%** |
| +2 SD | 126 | 42% |
| At/above top of range | 271 | 33% |

**Which trims work** (510 partial trims since March):

| Trim fill | Count | Lower 20 days later | Median 20d | Rebuy cheaper within 5 days |
|---|---|---|---|---|
| Down on the day | 143 | 50% | +0.2% | 51% |
| 0 to 1 SD up | 191 | 60% | −1.0% | 63% |
| 1 to 2 SD up | 122 | 49% | +0.1% | 64% |
| 2 SD or more up | 54 | 54% | −2.8% | 71% |
| Below 50% of range | 162 | 44% | +1.2% | 51% |
| At/above top of range | 77 | 61% | −2.8% | 69% |

- At the 1.5 SD trim line, the price fell at least 1 SD below the line within 5 days **88%** of the time.

### 3. Buying on dips — what the data says (re-checked)
- **Universe:** Bullish outlook the night before (`drv_rr.outlook`), with cash (`is_cash()`), macro instruments (`ref_rrt.y_ticker` index / futures / FX) and stop-breached stocks removed.
  - From 3/5 to 10/2 that is 28,032 stock-days, about 211 a day.
  - Base rate: 49% up after 5 days, average +0.1%.
- **Two ways to measure:**
  - **Close:** the stock *closed* down ≥ k SD; measured from the close.
  - **Touch:** the day's *low* reached the line; bought at the line. A live alert behaves like this.

| Test (5 days later) | Close: per day / up / avg | **Touch (live): per day / up / avg** |
|---|---|---|
| All Bullish, −1.5 SD | 13.0 / 57% / +1.1% | **25.9 / 56% / +1.0%** |
| Not held, −1.5 SD | 11.9 / 57% / +1.0% | 23.8 / 56% / +0.9% |
| Held, −1.5 SD | 1.1 / 55% / +2.0% | 2.1 / 52% / +1.5% |
| **Strong (buy-side call), −1.5 SD** | 1.6 / 59% / +1.0% | **3.6 / 55% / +0.9%** (from 4/2) |
| Strong and not held, −1.5 SD | 1.4 / 61% / +1.1% | 2.7 / 58% / +0.9% |
| Light (no buy-side call), −1.5 SD | 11.3 / 57% / +1.1% | 25.6 / 56% / +1.0% |
| **Light, −2.0 SD** | 5.6 / 57% / +1.0% | **12.2 / 57% / +1.1%** (8/10 on: 7.3 a day) |
| Light, −2.5 SD | — | 6.1 / 59% / +1.0% |
| All Bullish, −2.0 SD | 6.3 / 58% / +1.0% | 12.3 / 56% / +1.1% |

**Where I differ from the coordinator's numbers:**
- **Volume:**
  - Your "~10 a day at 1.5 SD" matches my *close* test (13 a day).
  - A live alert fires on the *touch*, which happens twice as often: **about 26 a day** for all Bullish stocks at −1.5 SD.
  - Plan on the touch numbers.
- **Strong tier:** I get a weaker edge than you: 55–59% and +0.9–1.0%, against your 61% and +1.7%. It is still above the base. Strong-and-not-held is the best cell (58–61%), which agrees with you.
- **Held:** held stocks were weaker on the "up" count (52–55%), but had a higher average (+1.5–2.0%) on small samples. The held / not-held split is not a reason to exclude either.
- **Dates:** the Bullish outlook rows start on 3/5 and buy-side `final_code` rows on 4/2, so the Strong numbers cover 4/2–10/2.
- **The edge depends on the period** (touch at −1.5 SD, all Bullish):

| Period | Base | Dip-buy |
|---|---|---|
| Mar–Apr (small sample) | 45% | 26% (46 cases) |
| May–Jun | 53% | 59%, +1.3% |
| Jul–8/9 | 51% | 60%, +1.2% |
| 8/10–10/2 | 42%, −0.4% | 45%, 0.0% |

  In a falling market it beats the base, but it still does not make money. Treat it as "better entry", not "will go up".

**Thresholds (DECIDED):**
- **Strong at −1.5 SD:** 3.6 a day, 55% up, +0.9% (from 4/2); 3.3 a day from 8/10.
- **Light at −2.0 SD:** 12.2 a day, 57% up, +1.1% (7.3 a day from 8/10). Hidden unless the chip is on.
- At 2.0 SD the Strong tier would be only 1.6 a day (57%, +1.2%). The extra Strong signals at 1.5 SD carry about the same edge.

**Room to the top of the range — shown, not filtered (DECIDED):**
- You skipped SXT on 10/9 because its range was tight: 3.2% wide, with 1.9% of room to the top. But AAPL, which you did buy, was about the same (3.6% / 2.2%), and so was CPAY (4.3% / 2.6%). The median stock's range is 5.7% wide.
- The coordinator's backtest found no useful split by room to the top. Only 9 of 772 dip-buys had less than one normal day's move of room (33% up, too few to trust), and none were Strong.
- So there is no room filter. The LIVE tooltip shows room (in % and in normal moves) and range width, so you can make the call.

**Sector-neutral on purpose (DECIDED):** the rules treat every sector the same. You mentioned a tech bias. There is no sector preference rule; any preference stays your own judgement.

### 4. Buying back after your own sale (369 buy-backs, 0–5 days after a trim, since March)
- **Same day:** cheaper than the sale 60% of the time; no forward edge (45% up after 5 days). 146 same-day round trips netted +$5.3k.
- **Days 1–5, at least 0.5 SD below the sale and at or above yesterday's close:** 80–83% up after 5 days, on a small sample (15–39).
- So label it **"cheaper re-entry: locks in the spread"**, not a forecast.

### 5. Plan plus live check
**At night,** after the end-of-day derive, write the plan for the next trading day. It may be rewritten until 9:30 ET, then it is frozen. It holds, per stock and per trading account:
- Last night's Final Call / `final_code`, outlook, stop status, cash and macro flags.
- Frozen account value, multiplier, and min / max / unit (raw and rounded).
- Held $ and shares, prior close, SD20, LRR, TRR.
- Trim line, over-max trim line, trim size.
- **Dip tier** (Strong / Light / none), dip line, dip size.
- **Starter account** (for not-held stocks).
- Last sell price and buy-back line.

**Why eligibility is set at night, not from Trade Mode:**
- Trade Mode (`web/actionable.js::_isTradeModeQualifyingBuy`) is a stricter live filter. It needs:
  - BUY MORE or BUY TO MIN only
  - a Technical entry-ripe read
  - no stop hit
  - a tradability score
  - no macro instrument
  - PVV not AVOID
  - BUY TO MIN only above the Trade line
- A stock that just dropped 2 SD often fails these, so it would fall out of Trade Mode exactly when the dip-buy should fire.
- Eligibility is therefore frozen the night before, starting from all Bullish stocks.

**On every price pull** (browser pull about every 30 minutes, the 10:00 / 15:00 fallback, TOSL loads):
- compare each plan row with the live price, day high and day low
- set its signal
- save the check (D3)

### 6. Screen — the LIVE column on Actionable (DECIDED)
Built the same way as the PVV column. It is a new toggleable column `live` in `TOGGLEABLE_COLS`, placed right after PVV. It is **visible by default**: the gear menu saves hidden columns in `act_cols_v1`, so a new column shows unless you hide it.

**Badge** (one per row, using the existing `.act-badge` tint classes):

| Signal | Badge text | Colour |
|---|---|---|
| Trim | `TRIM` | act-sell-tint (red family) |
| Over max | `TRIM→MAX` | act-sell-strong-tint |
| Dip-buy Strong | `DIP BUY` | act-buy-strong-tint (green) |
| Dip-buy Light | `dip buy` | act-neutral-tint text on a green-outline (greyed) |
| Buy-back | `BUY BACK` | act-buy-tint |
| Waiting for buy-back | `WAIT` | act-neutral-tint (grey) |
| No signal | `—` (muted dash, still hoverable) | — |

- **Small tags after the badge:**
  - `chase` when the stock sits in the top 20% of today's range on a buy badge.
  - `!` (warn colour) when last night's Final Call is SELL SOME.
- **Stale price** (older than 45 minutes): the badge is drawn with a `--warn` outline, and the tooltip says "price 1 h 10 m old".

**Hover tooltip** (`data-livepop`, same `_showDataPop` mechanism as `data-pvvpop`), always a bulleted list. One block per account the signal applies to:
- **TXG — TRIM**
  - Price $84.30, prior close $77.28, normal daily move 6.0% (SD)
  - Trim line $84.24 (prior close + 1.5 SD)
  - **IRA:** over max ($30.9k vs $17k) → sell 165 shares to max
  - **F-A:** sell 1 unit ($2k) ≈ 24 shares
  - **F-M:** sell 1 unit ($2k) ≈ 24 shares
  - Checked 10:58 ET
- For a not-held dip-buy: "Starter in **F-M** at min $4k (next: IRA, then F-A)".
- For every dip-buy and buy-back, two range bullets:
  - "Room to top of range: 1.9% (0.6 normal moves)"
  - "Range width: 3.2% (LRR $X – TRR $Y)"
- For WAIT: one bullet "PVV today: DRIFT (price and volume down, volatility down) · 11:45". This is shown in the tooltip only, because the PVV column already shows PVV and should not be repeated in the cell.
- Last line when it applies: "Caution: last night's call was SELL SOME".

**Toolbar:**
- One new chip **"Live (N)"** (`data-flag-pill="live_only"`). It filters to rows with any live signal and also reveals the hidden Light dip-buys. N counts the visible action signals (WAIT and Light excluded).
- Same style as the existing "In headwind area (N)" chip.

**Sort:** a `_live_rank` like `_pvv_rank`:

| Rank | Signal |
|---|---|
| 0 | TRIM→MAX |
| 1 | TRIM |
| 2 | DIP BUY Strong |
| 3 | BUY BACK |
| 4 | dip buy Light |
| 5 | WAIT |
| 9 | no signal |

Within a rank, larger suggested $ comes first.

**Refresh:** the column re-reads `/api/actionable/live` whenever prices refresh, about every 30 minutes while the screen is open.

**Action popup:** **no new section.** Everything is in the tooltip. A popup section would repeat the same lines, and the Action popup is about the Final Call.

**Duplicates checked:**
- **OVER MAX pill in the ACTION cell:** it stays (it is a state, always on). The LIVE column only shows `TRIM→MAX` when the price trigger fires, and the tooltip does not repeat the pill.
- **PVV:** not repeated in the cell (see above).
- **"Chasing?":** shown only as the `chase` tag here, not also in the Action popup (this replaces round 2's popup line).
- **New chips:** only one ("Live (N)"). No new pill in the SYMBOL cell, and no strip.

**"Nothing separate from Actionable" — corrected:**
- All live signals are on Actionable: the column, the tooltip and the chip.
- The only thing elsewhere is the **Daily review**. It is an after-the-fact report on the Performance screen, not a live alert.
- No email.

**When the screen is closed:** only the 10:00 / 15:00 ET fallback pulls and TOSL loads run, and each still writes its checks. When you reopen, the badges show their last check with the stale outline until the fresh pull lands.

### 7. Daily review — what it gives you
- A Friday-style report for any day, on a "Daily review" tab of the Performance screen.
- **For each stock** (household net), it says whether you followed the plan, followed a LIVE signal, had a near miss, went against it, acted silently, or just washed shares.
- It also lists:
  - the LIVE signals you skipped, and where the price went by the close
  - the spread you made on round trips
  - habit checks, such as buying near the day's high or trimming on a down day
  - a data-health line
- It replaces the old followed/contradicted scoring, which compared trades with the wrong day.
- It is a feedback tool, not trading advice, so it is built last.

### 8. Friday 10/9 replay
Sizes are per account and rounded; account values come from the 10/8 position files. Trades are judged at the fill price, because fill times are unknown. ILMN and IGV are washes.

**Net sells (13):**

| Verdict | Stocks | ~$ net |
|---|---|---|
| LIVE TRIM at the fill | XLV, ELF, NET, DT, FXH, SNOW | $47k |
| LIVE TRIM→MAX | MSFT (F-M); TXG IRA and F-A (F-M a near miss at $83.77 vs $84.24) | $33k |
| Followed plan (SELL SOME) | GTLB, TEAM | $6k |
| Near miss | PANW | $5k |
| Silent | MDB, SHOP | $4k |

**10 of 13 match (~$86k of $95k).** The app would have suggested about $63k of selling; you sold about 2 units where it said 1.

**Net buys (20):**

| Verdict | Stocks |
|---|---|
| Followed plan | COIN, CRWD, IBIT, META, QTUM (~$72k) |
| LIVE DIP BUY (Strong) | **AAPL** (BUY SOME, Bullish; low −2.4 SD, your fill −1.8 SD). F-M, the account that holds it, was over max, so the app would have offered a one-unit add nowhere and a starter in IRA (the account furthest below min). You bought in F-M. Counted as a match by direction, with an "account differs" note |
| LIVE BUY BACK | CRAK (IRA, caution SELL SOME); OKTA (F-A; your buy probably came before the sale) |
| Against | BLOK, XLE (SELL ALL); BNO, MPC (SELL SOME, no signal); HOOD (stop hit on 10/8) |
| Silent | ETHA, PBR, QQQ, SHEL, TWLO, WST, XLK |

**8 of 20 match (~$79k of $147k).** CPAY and SXT were signals you did not take, so they do not change the count.

**Dip-buy signals that fired on Friday:**
- **Strong (−1.5 SD): 3.**
  - AAPL (−2.4 SD, held). You bought it.
  - CPAY (−1.9 SD, BUY TO MIN, not held). Not bought; you say you should have.
  - SXT (−1.51 SD, BUY TO MIN, not held). Not bought: a tight range (3.2% wide), dipping from the top of it.
- **Light (−2.0 SD): 0.**
- None of the silent buys was a dip. They were HOLD-call theme or list adds and small stubs.

**TXG:** closed up 4.4%, so only BUY BACK can fire. With the simpler same-day test (above the day's low), your $81.25 buy-back **passes**, because the low came before the peak. This is the accepted limit of not saving every pull.

**Signals on Friday:**
- Trim: 13 stocks.
- Trim→max: 3 accounts.
- Dip-buy: 3 Strong, 0 Light.
- Buy-back: about 6, plus about 19 WAIT.
- About 25 badges. Friday was busier than average on trims and quieter on dips.

**Average day:**

| Badge | Per day |
|---|---|
| Trim | 6.3 (busiest 18) |
| Trim→max | ~1.9 (1.25× leg) |
| DIP BUY Strong at −1.5 | 3.3–3.6 |
| dip buy Light at −2.0 (hidden unless the chip is on) | 7–12 |
| BUY BACK | ~4 |
| WAIT | ~19 (muted) |
| chase tag | ~8 |

- **Visible: about 16 action badges a day** with Light hidden (DECIDED). About 23–28 with the chip on.

**Another rule for the silent trades?** No. Silent buys are theme / ETF-list adds and small stubs on HOLD calls (round 1 showed theme buys lose more often than they win). Silent sells are small trims below the trim line by design.

## Rules & numbers

### P1 — Per-account sizes from percentages — **BUILD** (DECIDED)
- **Sizes:**
  - min / max / unit = `min_pct` / `max_pct` / `units_pct` × account value × multiplier
  - `units_pct` = `units` ÷ $400,000 (half the min percent)
- **Account value:**
  - latest position file total per account (Schwab `hist_cs.market_value`, Fidelity `hist_f.current_value`)
  - cash, money market and pending activity included
  - frozen once a night
- **Multiplier:** `ref_accounts.size_mult` (default 0, range 0–5, edited on `/ref`).
  - IRA 1, F-A 2, F-M 1.
  - 401K, HSA, A and Ra are 0.
- **Rounding:**
  - nearest $1,000 (exactly $500 rounds up)
  - anything above $0 never goes below $1,000
  - done at night plan time from the frozen value; raw and rounded amounts are both saved
- **Household min / max:** the sum of the rounded account amounts (context only).
- **Neutral / Other categories:** stay at $0 (DECIDED).

| Account (10/9 value × multiplier) | Call: min / max / unit | Equities: min / max / unit |
|---|---|---|
| IRA ($419.9k × 1) | $4k / $17k / $2k | $8k / $25k / $4k |
| F-A ($178.2k × 2) | $4k / $14k / $2k | $7k / $21k / $4k |
| F-M ($445.6k × 1) | $4k / $18k / $2k | $9k / $27k / $4k |

**Over max, per account:** 7 stocks on 10/8 and 8 on 10/9 (the old household count was 11 and 13); 5 and 6 without BUXX and CLOX.
- **Edge cases:**
  - No position file within 5 trading days: no plan rows for that account.
  - Accounts with no holding still get sizes.

### T1 — Spike trim — **BUILD** (DECIDED)
- **Line:** the lower of:
  - prior close × (1 + **1.5** × SD20)
  - the higher of TRR and prior close × (1 + 1.0 × SD20) (GUESS)
- **Applies to:** every account that holds the stock.
- **Size:** one unit, using the existing REDUCE rule as is: held − one unit, which can reach $0 because `maintain_min` is off (DECIDED).
- **SD20:** the standard deviation of the last 20 daily close-to-close % moves, ending at the prior close.
- **Edge cases:**
  - Fewer than 15 moves: no fire.
  - SD under 0.5%: skip (GUESS).
  - SD20 more than 3× its 60-day median (ETHA 43%): use the median (GUESS).
  - Cash: skip.
  - Price older than 45 minutes: stale, nothing new fires.
  - No TRR: SD leg only.
  - Earnings day: still fires, with a tag.

### T2 — Over max: back to max — **BUILD** (DECIDED; replaces R1)
- **Applies to:** each account over its max, when any one is true:
  - up at least **1.0** SD
  - at or above **80%** of the range
  - **more than 1.25× max**, on any day (DECIDED; replaces the earlier 2× leg; evidence in `DESIGN_SPEC_4.md` §5)
- **Size:** back to max.
- **Edge cases:**
  - If T1 and T2 both fire, use the bigger sell.
  - SELL ALL: no T2 line.
- **Numbers:** 80% and 1 SD are GUESS. The 1.25× cut is set from the data, but the exact cut point is a GUESS.

### DB — Dip-buy, two tiers — **BUILD** (DECIDED)
- **Eligible (frozen in the night plan):**
  - outlook Bullish (`drv_rr.outlook`)
  - not cash (`is_cash()`)
  - not a macro instrument (`ref_rrt.y_ticker` index / futures / FX, same test as `is_macro_instrument`)
  - no hit stop (`stop_breached`)
  - held or not held
  - **plus** any stock sold in a trading account in the last 5 trading days
- **Tiers:**
  - **Strong (DECIDED):** last night's `final_code` is BM / BMN / BS. Fires at live price ≤ prior close × (1 − **1.5** × SD20).
  - **Light (DECIDED):** every other eligible stock. Fires at ≤ prior close × (1 − **2.0** × SD20). Shown greyed, and **hidden unless the "Live (N)" chip is on**.
  - **No room-to-range filter and no sector rule (DECIDED).** The tooltip shows room to TRR (% and in SD) and range width.
- **Blocks:** live Final Call SELL ALL, or the stop is hit during the day. SELL SOME shows a caution tag.
- **Which accounts and how much:**
  - **Held** (in at least one trading account): one unit (existing INCREASE rule) in **each account that holds it and is below max**, capped at max. Accounts that do not hold it get nothing.
    - If every holding account is at or over max, it falls back to the not-held starter rule for one non-holding account (AAPL on 10/9).
  - **Not held anywhere:** a **starter at the account's min** (existing ADD rule, rounded), in **one account at a time**:
    - **Pick the account with the largest dollar gap to its min.** A gap is used, not a held/min ratio, because for a stock held nowhere every ratio is 0 and would tie.
    - **Ties** (common, since rounded mins are often equal, e.g. $4k in all three for Call): pick the account with the **most cash** in the latest position file. Then IRA, F-A, F-M in that order.
    - Accounts with multiplier 0 are never picked. Accounts whose cash is below the starter are skipped.
    - Once that account holds the stock at its min, or you buy it anywhere, the next check offers the next account with a gap. A stock that is now held moves to the held rule.
- **Limit:** once per stock, per account, per day.
- **Edge cases:**
  - Same SD edge cases as T1.
  - Gap down below the line: fires at the first pull.
  - TRIM and DIP BUY on the same day: show the later one and note the other in the tooltip.

### B — Buy-back after your own sale — **BUILD** (DECIDED)
- **All must be true:**
  1. You sold in this account in the last 5 trading days.
  2. Live price ≤ average sell price − **0.5** × SD20 (in $).
  3. **Stopped falling:**
     - Days 1–5: at or above yesterday's close.
     - Same day: at least **0.25** SD above today's low.
  4. Not SELL ALL and no hit stop. SELL SOME shows a caution tag.
- **WAIT** when rule 2 is met but rule 3 is not. The tooltip shows the PVV DRIFT / BEAR_LEAN line with its time.
- **Applies to:** the account that sold. Size: back up to the smaller of the amount held before the sale and the account max.
- **Wording:** "Cheaper re-entry: X below your sale."
- **Expiry:** 5 trading days, or a close back above the sell price.
- **Known limit:** the same-day test cannot tell whether the low came before the peak (TXG).

### C — Chasing tag — **BUILD**
- Shown on DIP BUY, BUY BACK or a buy-side row when the price is in the top 20% of today's range, or at or above 90% of the risk range.
- It is a small tag in the LIVE cell only.

### PVV — **separate** (DECIDED)
- Shown only as a tooltip line on WAIT, with its time. It is never repeated in the cell.

### D2 — Frozen night plan `hist_advice_plan` — **BUILD**
- **Key:** (plan_date, tos_symbol, account_short).
- **Columns:**
  - made_at, anchor_date
  - final_action / final_code / final_side, outlook, stop_breached, is_cash, is_macro
  - account_value, value_date, size_mult, account cash
  - category, min / max / unit (raw and rounded)
  - held $ and shares
  - prior close, SD20, LRR, TRR
  - trim_line, overmax_trim_line, trim_size
  - dip_tier, dip_line, dip_size, starter_account, starter_order
  - last_sell_price, buyback_line, buyback_size
  - rule_version
- **Writing:** append-only. It may be rewritten until 9:30 ET, then frozen.

### D3 — Saved live checks `hist_advice_live` — **BUILD**
- **Key:** (checked_at, tos_symbol, account_short).
- **Columns:**
  - plan_date
  - price, price_time, day high / low
  - signal (TRIM / TRIM_TO_MAX / DIP_BUY_STRONG / DIP_BUY_LIGHT / BUY_BACK / WAIT / NONE), live_rank, reason
  - suggested shares and $
  - caution, chase, PVV line
- **Writing:** one row per plan row per pull. Kept forever. This is the scoring record.
- **Size:** the plan now covers about 210 Bullish stocks plus held stocks, so roughly 250 stocks × 1–3 accounts × up to ~14 pulls ≈ 5–10k rows a day. That is fine. If needed, write only rows whose signal is not NONE, plus one NONE row per stock per day.

### D1 — Save every price pull — **OPTIONAL / later**
- Not needed by any rule. The same-day test uses the day's high and low, and D3 already saves the price seen at each check.

### R5 — Household-net scoring — **BUILD** (last, with the Daily review)
- Household net per stock per day; under 25% of the larger side is a wash (GUESS).
- A fill beyond a line, with that LIVE signal on at some check that day, is "followed live". The suggested size is shown next to yours.

### Other items
- R1: replaced by T2.
- R2: **DROP**.
- R3 (Book-SOME bug): **BUILD**.
- R4: **NOTE-ONLY**.
- Area links (CRAK, BLOK, HOOD): **BUILD**.
- Email: **DROP**.
- Live now strip and SYMBOL-cell badge: **DROP** (replaced by the LIVE column).
- Action popup Live section: **DROP** (folded into the tooltip).
- 5-day-high buy idea: **DROP**.
- Review file export: **NOTE-ONLY**.

### Worth reconsidering
- **Badge volume:** about 16 visible a day (Light hidden, DECIDED). If that still feels busy, the next cut is a 3-day buy-back window instead of 5 (about −1.4 a day). Light signals are still saved, so the Daily review can show whether they would have paid.
- **You trim about 2 units where the plan says 1.** If the review keeps flagging this, consider making the unit equal to the full min.

## Files likely touched
- `db/baseline.sql`:
  - `ref_accounts.size_mult`
  - `ref_asset_allocation.units_pct`
  - new tables `hist_advice_plan`, `hist_advice_live` (and `hist_quote_intraday` only if D1 is built)
- `db/seeds_*.sql`:
  - multipliers
  - `units_pct`
  - `ref_settings` keys: `live_trim_sd` 1.5, `live_trim_trr_min_sd` 1.0, `live_overmax_sd` 1.0, `trim_over_max_pos_pct` 80, `overmax_any_day_ratio` 1.25, `dip_buy_strong_sd` 1.5, `dip_buy_light_sd` 2.0, `live_show_light` false (Light shown only with the chip on), `buyback_below_sell_sd` 0.5, `buyback_window_days` 5, `buyback_bounce_sd` 0.25, `live_min_sd_pct` 0.5, `live_price_stale_min` 45, `chase_day_range_pct` 80, `plan_freeze_et` 09:30, `account_value_max_age_days` 5, `size_round_dollar` 1000, `size_min_nonzero_dollar` 1000
- New `etl/derive_live_advice.py` — account values, the night plan (D2) with tiers and starter account, and the live check (D3).
- `etl/yahoo_fetch.py` — run the live check after each intraday pull.
- `etl/etl_load.py` — run the live check after an intraday TOSL load.
- `etl/derive_actionable.py` — per-account min / max / unit; per-account over-max pill and AMT$.
- `etl/derive_inferred_actions.py` — R5 against D2 and D3.
- `api/routers/dash.py`:
  - `GET /api/actionable/live` (latest signal per stock, per-account detail, live rank)
  - per-account sizes in the payload
- `api/routers/rules.py` — `GET /api/review/daily?date=`.
- `web/actionable.js`:
  - `live` in `TOGGLEABLE_COLS` (after `pvv`)
  - `_liveCellHtml`, `_liveRank`, the `data-livepop` tooltip in the `_showDataPop` mouseover list (includes room-to-TRR and range-width lines)
  - `live_only` chip filter
  - refresh on price pull
- `web/actionable.html`:
  - LIVE header cell
  - "Live (N)" chip next to "In headwind area (N)"
  - bump `?v=`
- `web/rule_performance.html` / `web/rule_performance.js` — Daily review tab (bump `?v=`).
- `docs/live_advice_logic.md` (new), `docs/actionable_logic.md`, `docs/performance_logic.md`; one Lookup row in `CLAUDE.md`.

## Open questions
- None. All user decisions are made.

**Notes for the developer** (checks, not decisions):
  - ETHA's 20-day SD comes out at 43% (bad price row?).
  - IBIT's category changed from RR to Commodities between 10/8 and 10/9.
  - Buy-side `final_code` history starts on 4/2; Bullish outlook rows on 3/5.
  - Transaction files have no trade time.

### Build order
1. **P1:** account values, `units_pct`, multipliers, rounding, per-account sizes.
2. **D2 + D3** with the live checks: T1, T2, dip-buy (both tiers, starter account), buy-back, Chasing.
3. **LIVE column**, tooltip, "Live (N)" chip and sort on Actionable.
4. **R5 scoring + Daily review** (last; it is a feedback tool).
5. **Any time:** R3 and area links.
6. **Optional:** D1.

## Status
READY_FOR_DEV
