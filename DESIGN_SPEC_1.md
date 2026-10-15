# Design Spec — DESIGN_WORK_1

## Goal
Check every trade from Friday 2026-10-09 against what the system was saying. Explain the trades it missed, and propose rules that would have caught the ones worth catching.

## Design

### Bottom line
- **40 trades on 10/9** (24 buys, about $174k; 16 sells, about $110k), across 3 IRAs. The 401k fund changes are left out because they are payroll contributions.
- **Matched 12 (about $101k). Opposed 7 (about $39k). Silent 21 (about $144k).**
- That is normal for you. From Aug 3 to Oct 8 the split was 37% matched, 19% opposed and 44% silent (588 trades). Friday had a few more silent trades, but nothing unusual.
- Most of the misses fall into four groups:
  1. **Trimming positions that were over their max size** (TXG, XLV, MSFT, NET, ILMN). This was 66% of Friday's sell dollars. The system only shows an "OVER MAX" pill and never says sell. **This is worth a rule.**
  2. **Selling into a strong up day when the price was at or above the top of the range** (DT, PANW, MDB, SHOP). The system has no Technical rule for "above the top of the range" when the stock is in a bull trend, so the Technical read was blank. **Worth a trial.**
  3. **Buying the oil and crypto themes after Hedgeye's Macro Show** (XLE, BNO, CRAK, MPC, PBR, SHEL, BLOK, HOOD, ETHA). History says this has not paid off. **Not worth a buy rule. A warning is better.**
  4. **A bug.** On 10/8 Hedgeye sent a "Book-SOME" (take some profit) alert on NET. The system stored it with no signal type and dropped it. **Fix the bug. No new rule is needed.**
- You also bought and sold the same names in different accounts on the same day (ILMN, TWLO, NET, MSFT). That is account housekeeping, not a signal. **No rule.**

### How the trades were found
- The Schwab and Fidelity transaction files only go up to 10/1, so the 10/9 trades come from comparing positions between the 10/8 and 10/9 position files. Both files are dated correctly: the 10/8 file loaded after Thursday's close, and the 10/9 file loaded Friday night.
- Share counts are exact. **Dollar amounts are estimates** (shares × Friday's close), because the fill prices are not loaded yet.
- Each row below combines same-side trades in one symbol across accounts. The account column shows the shares in each account. Accounts: **IRA** = Schwab Rollover IRA ...892, **F-A** = Fidelity 249118149, **F-M** = Fidelity 261408079.

### What "System said" means
- It is the Final Call on the Actionable screen for the 10/8 anchor date. That is what the screen showed during Friday's session.
- That row was last rebuilt at 6:06 PM on Friday, so it already includes Friday's Hedgeye emails and Friday's closing prices. The live screen earlier in the day may have differed a little. For example, the META real-time alert only arrived at 3:16 PM ET.
- **Verdicts:**
  - **Matched**: the Final Call was on the same side as your trade.
  - **Opposed**: the Final Call was on the other side.
  - **Silent**: the Final Call was HOLD. "Leaned buy" or "leaned sell" means a Hedgeye source agreed with you, but the price checks held the call back to HOLD.
- **"% of range"** means where Friday's close sat between the bottom of the risk range (LRR) and the top (TRR). 0% is the bottom, 100% is the top, and above 100% means above the top.

### Buys

| Symbol | Account (shares) | Side | $ amount | System said | Rule/source | Verdict | Likely reason |
|---|---|---|---|---|---|---|---|
| CRWD | IRA 40, F-A 10, F-M 50 | Buy | ~$27,500 | BUY MORE (high) | Hedgeye Top-5 long (10/9), Call bullish (10/9), Technical buy | Matched | Hedgeye's favourite cybersecurity name |
| IBIT | IRA 175, F-A 50, F-M 250 | Buy | ~$22,100 | BUY MIN (high) | Macro Show bullish Bitcoin (10/9), Go-Anywhere/PS/ETF lists, price at range bottom, Bitcoin area Tailwind | Matched | Crypto theme, good entry spot |
| XLK | IRA 50, F-M 40 | Buy | ~$17,900 | HOLD (leaned buy) | PS/ETF/Go-Anywhere say add. No Technical buy because MACD was falling. 43% of range | Silent | Hedgeye ETF lists, mid-range |
| META | F-A 6, F-M 10 | Buy | ~$11,500 | BUY MORE (high) | Hedgeye real-time Buy alert (10/9, 3:16 PM ET), price near range bottom (21%) | Matched | Real-time alert |
| XLE | IRA 175 | Buy | ~$11,400 | SELL ALL | PS and ETF Pro both dropped XLE (10/2). Price above the range top (135%). Already $32.6k vs $24k max | Opposed | Oil theme: Oil area Tailwind, Macro Show bullish on Brent (GUESS) |
| QQQ | F-M 15 | Buy | ~$11,300 | HOLD (leaned buy) | ETF Pro added QQQ (10/9). No Technical buy. 41% of range | Silent | New ETF Pro add |
| WST | IRA 24 | Buy | ~$8,800 | HOLD (leaned buy) | Top-5 long vs. Signal Strength removed it (10/8). No price data | Silent | Building a 1-share stub up to normal size. Hedgeye real-time Buy on 10/2 (GUESS) |
| HOOD | IRA 15, F-A 55 | Buy | ~$7,600 | HOLD (leaned buy) | Call says add, but the stop was hit (price broke below the Trade line) | Silent | Crypto theme, buying the dip (GUESS) |
| QTUM | IRA 50 | Buy | ~$7,600 | BUY MIN (high) | Macro Show bullish (10/7), PS/ETF add, price at range bottom | Matched | Theme plus good entry |
| TWLO | F-M 25 | Buy | ~$7,200 | HOLD (leaned sell) | Signal Strength REDUCE. Already $23.4k vs $16k max | Silent | Shares moved from IRA to F-M (sold 7 in IRA) (GUESS) |
| BLOK | F-M 100 | Buy | ~$6,000 | SELL ALL | PS and ETF Pro dropped BLOK. 95% of range | Opposed | Crypto theme (GUESS). BLOK is not linked to the Bitcoin area |
| ILMN | F-M 20 | Buy | ~$5,600 | HOLD (leaned sell) | Signal Strength REDUCE. Already $27.8k vs $16k max | Silent | Account shuffle: sold 25 in IRA the same day |
| MPC | IRA 10 | Buy | ~$4,600 | SELL SOME (high) | Signal Strength REDUCE. Technical sell near range top (88%) | Opposed | Oil theme. Buying back after selling 30 shares on 10/1 at $401–417; Friday close $455 |
| PBR | IRA 100, F-A 79 | Buy | ~$4,500 | HOLD (leaned sell) | Signal Strength REDUCE. II add. 82% of range | Silent | Oil theme. Buying back after selling on 10/1 at $21.00; Friday close $25.30 |
| COIN | IRA 20 | Buy | ~$3,600 | BUY MIN (high) | Call add, price at range bottom, Bitcoin area Tailwind | Matched | Crypto theme, good entry |
| AAPL | F-M 10 | Buy | ~$3,400 | BUY SOME (high) | Risk-range list add. But Hedgeye Call turned bearish on 10/9, and you already held $25.5k vs $12k max | Matched | Technical buy near range bottom |
| SHEL | IRA 25 | Buy | ~$2,500 | HOLD | No Hedgeye source. Technical says sell some (210% of range) | Silent | Oil theme (GUESS) |
| NET | F-M 5 | Buy | ~$1,800 | BUY MORE (high) | Top-5 long (10/8) | Matched | Account shuffle: net seller of 30 shares across accounts |
| OKTA | F-A 8 | Buy | ~$1,900 | HOLD (leaned buy) | Top-5/Signal Strength increase. Above range top (107%) | Silent | Building a 1-share stub up to normal size (GUESS) |
| CRAK | IRA 25 | Buy | ~$1,700 | SELL SOME (high) | PS REDUCE. Technical sell at range top (88%) | Opposed | Macro Show named Oil Refiners (CRAK) bullish on 10/9 |
| MSFT | F-A 3 | Buy | ~$1,600 | HOLD (leaned buy) | Risk-range list add. At range top | Silent | Account shuffle: sold 25 in F-M the same day |
| BNO | IRA 25 | Buy | ~$1,600 | SELL SOME | Technical sell at range top (95%). Go-Anywhere still holds it | Opposed | Macro Show bullish on Brent (10/8 and 10/9), Oil Tailwind |
| ETHA | IRA 25 | Buy | ~$1,400 | HOLD (leaned buy) | Hedgeye real-time Buy (10/7) and Top-5 ETH long (10/8), but the stop was hit and price was below range bottom | Silent | Buying the dip on Hedgeye's call |
| IGV | IRA 11 | Buy | ~$1,200 | SELL SOME | Technical sell at range top (102%). PS increase | Opposed | Small top-up. Position $2.8k, below the $8k min. Macro Show bullish on software |

### Sells

| Symbol | Account (shares) | Side | $ amount | System said | Rule/source | Verdict | Likely reason |
|---|---|---|---|---|---|---|---|
| TXG | IRA 100, F-A 100, F-M 50 | Sell | ~$20,200 | HOLD (leaned buy) | Top-5 long (10/7) | Silent | **Way over max: $61.8k vs $16k.** Trim on a +4.4% day |
| XLV | IRA 50, F-M 50 | Sell | ~$17,100 | HOLD | PS INCREASE outranked the Go-Anywhere removal (10/7). Technical sell some | Silent | Go-Anywhere dropped XLV. Over max ($29.4k vs $24k) |
| MSFT | F-M 25 | Sell | ~$13,400 | HOLD | Risk-range list add. Hedgeye Call went to neutral (10/9). At range top (100%) | Silent | **Over max: $26.7k vs $12k**, plus the Call downgrade |
| NET | IRA 15, F-A 20 | Sell | ~$12,600 | BUY MORE (high) | Top-5 long (10/8). **The real-time "Book-SOME" alert on 10/8 was dropped (bug)** | Opposed | Hedgeye said take some profit. +5.6% day, above range top (103%), over max ($20.5k vs $16k) |
| ELF | IRA 49, F-M 50 | Sell | ~$10,800 | SELL SOME | Technical sell above range top (158%) | Matched | Sell into strength |
| ILMN | IRA 25 | Sell | ~$7,000 | HOLD (leaned sell) | Signal Strength REDUCE | Silent | Over max. Shares moved to F-M |
| PANW | F-A 13 | Sell | ~$5,400 | HOLD (leaned buy) | Signal Strength increase. No Technical read (84% of range) | Silent | Sell into a +5.1% day |
| TEAM | IRA 5, F-A 15 | Sell | ~$4,100 | SELL SOME | Technical sell above range top (106%) | Matched | Sell into strength |
| SNOW | IRA 5, F-A 5 | Sell | ~$3,700 | SELL SOME | Technical sell far above range top (273%) | Matched | Sell into a +7.4% day |
| FXH | F-M 25 | Sell | ~$3,300 | HOLD (leaned sell) | ETF Pro dropped FXH (10/8), but PS HOLD won. It became SELL ALL on 10/9 | Silent | ETF list removal |
| MDB | F-A 8 | Sell | ~$3,100 | HOLD (leaned buy) | Top-5 increase. No Technical read (79% of range) | Silent | Trim on a +3.9% day |
| CSCO | F-A 25 | Sell | ~$2,900 | SELL ALL | Hedgeye Call went to neutral (10/7) | Matched | Call removal |
| TWLO | IRA 7 | Sell | ~$2,000 | HOLD (leaned sell) | Signal Strength REDUCE | Silent | Account shuffle. Over max |
| GTLB | F-A 35 | Sell | ~$1,900 | SELL SOME | Technical sell above range top (106%) | Matched | Sell into strength. Hedgeye real-time Sell-SOME on 10/1 too |
| DT | F-A 25 | Sell | ~$1,600 | HOLD (leaned buy) | Signal Strength increase. **No Technical read even at 142% of range** | Silent | Sell into a +3.9% day |
| SHOP | F-A 3 | Sell | ~$500 | HOLD (leaned buy) | Signal Strength increase. No Technical read (93% of range) | Silent | Tiny trim on a +3.8% day |

### Summary counts

| | Matched | Opposed | Silent | Total |
|---|---|---|---|---|
| Buys | 7 (~$77k) | 6 (~$26k) | 11 (~$70k) | 24 (~$174k) |
| Sells | 5 (~$23k) | 1 (~$13k) | 10 (~$73k) | 16 (~$110k) |
| **All** | **12 (~$101k)** | **7 (~$39k)** | **21 (~$144k)** | **40 (~$284k)** |

- Of the 21 silent trades, **10 leaned your way**. A Hedgeye source agreed with you, but the price checks held the call to HOLD.
- **Area verdicts lined up with the themes.** Oil was Tailwind from 10/6 and Bitcoin was Tailwind from 10/2. No cross-asset trade signal fired.
- **Two follow-up items** were spotted on the way. See Open questions.

### Is 10/9 typical? (Aug 3 – Oct 8, 588 trades)
- **Match rate:** 37% matched, 19% opposed, 44% silent. Friday was 30% / 18% / 53%, so it was a normal day.
- **Over-max trims:** these were 30% of your sell trades and **48% of your sell dollars**. Over the next 20 days, the price fell after 74% of them (38 with results). They are your most reliable kind of sell.
- **Round trips:** you often sell and buy back the same names within 1–3 weeks (TXG, MSFT, XLE, PBR, MPC, BNO, XLV, NET, IGV). On 10/9 you bought back BNO, MPC and PBR above where you sold them on 10/1.
- **Macro Show buys:** buys made while Hedgeye's Macro Show was bullish on the name were up 20 days later only 30% of the time (67 buys).
- **A word of caution:** buys that matched the system were not better than silent buys (right 31% vs 41% after 20 days, on a small sample in a falling market). Judge rules by what happened next, not by how often you agreed with them.

## Rules & numbers

### R1 — Trim back to max on strength (NEW rule, recommended)
- **Rule:** you hold more than the max size for the name, and either the price is at or above 80% of its risk range, or the position is 2x max or more. The Final Call becomes **SELL SOME**, sized to bring the position back to max.
- **Why it is allowed:** on 9/3 you decided that "over max" alone should not drive the call. This rule keeps that decision, because it also needs the price to be high in its range or the position to be far oversized. A position slightly over max and low in its range stays as the pill only.
- **Data needed:** all of it already exists. Position $, max $, LRR, TRR and the latest price.
- **History (Feb–Sep, held names):**
  - Over max and at or above 80% of range: 81 cases, price lower 20 days later 78% of the time, average −2.2%.
  - Over max and at or above the range top: 42 cases (21 symbols), 90% lower, average −4.6%.
  - All held names in the same period: 58% lower, average −0.7%.
  - Held at 1.5x max or more: 346 cases, 63% lower, median −2.3%.
  - Your own over-max sells: right 74% of the time (38).
- **Thresholds:** 80% of range is **GUESS** (backed by the numbers above). 2x max is **GUESS** (only loosely backed by the 1.5x numbers). "Trim to max, not to min" is **GUESS**. Some of the sample is cash-like funds (BUXX, CLOX) that hardly move, so the real gain is smaller than it looks.
- **Edge cases:**
  - Missing LRR/TRR or price: no fire. The pill stays.
  - Equal to max: this is not "over".
  - Stale price (older than the anchor): no fire.
- **On 10/9 it would have caught:** TXG (3.9x max), MSFT (2.2x max, at 100% of range), NET (103% of range) and XLV (85% of range). About $63k of your $110k in sells. ILMN and TWLO (1.5–1.7x max, mid-range) would stay as the pill.

### R2 — "Above the top of the range" in a bull trend (TABLE CHANGE, trial first)
- **The gap today:** the bull-trend table (Table 2 in `docs/actionable_logic.md`) has no case for price at or above TRR. Those names get no Technical read at all. That is why DT (142%), PANW, MDB, SHOP and MSFT were blank.
- **Rule:** bull trend, price at or above TRR, and the day's move is up 3% or more. Technical says **SELL SOME**. This copies the not-bull table, which already says SELL SOME at or above TRR.
- **History:**
  - Bull trend at or above TRR with no read: 1,100 cases, average −1.5% over 20 days, 51% lower.
  - Adding the "up 3% or more" day: 1,132 cases, median −1.3%, 54.5% lower.
  - **But** the existing scorecard rule `698-SS-Bull-HighAbvTRR` scores −0.69 edge (unproven). Stocks often keep rising.
- **Evidence is mixed.** Turn it on as a note only for 4 weeks, score it with `v_rule_scorecard`, and only then let it change the Final Call. The 3% threshold is **GUESS**.
- **Edge cases:**
  - Earnings within 5 days: skip.
  - Down day: no fire.
  - TRR missing: no fire.

### R3 — Read Hedgeye "Book-SOME" alerts as Sell-SOME (BUG FIX, not a rule)
- **The bug:** "Book-SOME" (take some profit) alerts are saved with no signal type. The system then throws them away, and the older Buy alert on the same name is hidden too.
- **Fix:** treat "Book-SOME" as Sell-SOME. For a held name that means REDUCE. The real-time alert outranks every other source, so NET on 10/8 would have shown REDUCE instead of BUY MORE.
- **Scale:** 3 long-side alerts in history have no signal type. Check those 3 after the fix.

### R4 — Hedgeye ETF list drop on a held ETF (THRESHOLD/ORDER CHANGE, low priority)
- **Rule:** ETF Pro or Go-Anywhere drops a held ETF, and the price is above the middle of its range. Show **REDUCE** instead of letting PS's HOLD/INCREASE win.
- **On 10/9 it would have caught:** XLV and FXH (about $20k).
- **No backtest is possible yet.** Go-Anywhere data starts 10/2. Every number here is **GUESS**. Revisit in about 2 months.

### Not worth a rule
- **Theme buys after the Macro Show (oil, crypto).**
  - The Macro Show said bullish on a name 487 times. Twenty days later the average was −1.0% and only 40% were up.
  - When the price was already at or above 90% of its range: −2.3% average, 33% up (69 cases).
  - Bearish mentions did better than bullish ones.
  - See "Worth reconsidering" below.
- **Relaxing the Technical check so mid-range "list adds" become buys (XLK, QQQ).** Names below mid-range with no Technical read had no edge: +0.3% average, 48.5% up (9,060 cases). Keep the check.
- **Account shuffles (ILMN, TWLO, NET, MSFT).** These are housekeeping, not signals.
- **Buying the dip after a stop is hit on a Hedgeye Buy (ETHA, HOOD).** The dollars are small and the sample is too thin. The stop rule exists for a reason.

### Worth reconsidering
- **A "theme buy" rule would be wasteful.** It would push more buys like XLE, BNO, CRAK and BLOK on 10/9, and history says those lose more often than they win.
- **Better option:** a one-line **"Chasing?" warning** in the Action popup. Show it when the Macro Show is bullish on the name (or the area is Tailwind) and the price is at or above 90% of its range, for example: "Macro Show bullish, but price is near the top of its range. Past cases like this rose only 1 in 3 times." It costs one popup line and does not change the call.
- **For the themes, the system already points to the better entries.** IBIT, COIN and QTUM sat near the bottom of their ranges and were Matched.

## Files likely touched
- `etl/hedgeye/parsers.py` — R3: treat "Book-SOME" as Sell-SOME. Also check `etl/derive_outlook_action.py::_action_rta`.
- `etl/derive_actionable.py::_compute_final_call` — R1: trim-to-max sell, sized to max. R4: ETF-list drop order.
- `web/actionable.js` — mirror R1 in `finalCall()`, add the trim $ to the Action popup, and add the "Chasing?" line.
- `etl/derive.py::_derive_trend_trade_rules_impl` plus the bull-trend table seed in `db/seeds_*.sql` — R2: new "at/above TRR" case, note-only flag at first.
- `db/baseline.sql` / `db/seeds_*.sql` — new `ref_settings` keys: `trim_over_max_pos_pct` (80), `bull_trr_trim_min_up_pct` (3), `bull_trr_trim_mode` (`annotate` / `live`).
- `etl/derive_inferred_actions.py` — compare each trade to the day before, not the same day (see Open questions).
- `db/seeds_area_driver.sql` — link CRAK to the Oil area, and BLOK and HOOD to the Bitcoin area.
- `docs/actionable_logic.md`, `docs/rules_logic.md` — document R1–R4.

## Open questions
- **Approve R1 (trim back to max) as a live Final Call?** It needs over-max plus either a high price in the range or a 2x-max position, so the 9/3 "over max alone" decision still holds. Option B is to show the trim $ in the pill only, without changing the call.
- **R2 (bull trend, above TRR):** start as a note only (recommended), or live straight away?
- **Bug, for the developer: "Book-SOME" alerts are dropped.** NET on 10/8 was lost this way. Fix with R3.
- **Bug, for the developer: the "followed/contradicted" scoring checks the wrong day.** `etl/derive_inferred_actions.py::_batch_rec_actions` compares each trade with that same day's row. That row is rebuilt after the trade, using the new positions. It should use the day before. It also scores against the Hedgeye source action, not the Final Call. Example: your XLK buy is marked "contradicted" because of a 10/9 REDUCE that only appeared after you bought.
- **Area links:** CRAK, BLOK and HOOD are not linked to the Oil or Bitcoin areas, so the Tailwind tiles don't cover them. Add them?
- **Load the 10/9 Schwab and Fidelity transaction files** if you want exact fill prices. Shares and verdicts will not change.

## Status
READY_FOR_DEV
