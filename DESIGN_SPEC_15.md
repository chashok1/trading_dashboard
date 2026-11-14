# Design Spec — DESIGN_WORK_15

## Goal
Make the Builder answer one question in one glance, once a week: "what do I buy this week, and is everything inside my limits?" Do it with about half the work of Spec 14, and with limits that really hold.

### In plain English (one page)
- **Your real position today (from the database, 2026-11-13):** all accounts together are worth **$1,055,081**. **$262,177 is cash, which is 24.8%.** Equities are 40.4%, Fixed Income 32.4%. You hold 45 names in three main accounts (F-M, IRA, F-A) and three tiny ones (HSA, A, Ra).
- **So the real job is not "rebalance". It is "put about a quarter of the money to work, steadily, without thinking about it every day."** The design is built around that.
- **You set a plan once. It has three parts:**
  1. **The mix**: how much in Equities, Fixed Income, Gold, Cash and so on, for all accounts together.
  2. **My list**: the names you are happy to own. One click fills it from what you already own. You add or remove names a few times a year.
  3. **The limits**: how much to spend in a week, how much cash to keep, and how big one name may get.
- **Every week the screen gives you one short list.** At most 6 lines. Example with today's real numbers and a 60/30/10 mix: "Buy 34 XLV in F-M, about $6.4K" and five more lines, $24.1K in total, in two accounts. Place them, tick Done, close the screen.
- **Money limits are hard. The list can never break them.** It never spends more than an account's cash, never dips below the cash you want to keep, never goes over the weekly amount, and never makes one name too big. There is no "go ahead anyway" button. If you want to spend more, you change the number in the plan. That is one calm decision, not a daily temptation.
- **Opinions and drift only warn.** A class that has drifted out of its range, a name that is already too big, a Sell signal, or the Risk Dial saying "no new risk" all show as a note. They never stop the list.
- **Nothing trades by itself.** You place the orders at the broker. The screen cannot stop you there. "Hard" means the screen will never suggest it and will not let you type it.
- **It ships in three steps.** Step 1 alone (the mix check) already tells you where the cash should go by class. Step 2 adds the buy list. Step 3 adds a Monday email.
- **What is cut from Spec 14:** the two-level "segment then name" target list, the "beyond the budget" and "beyond the cash" sections, sell lines with tax estimates, the 401k and account-type rules, the daily cap, and the four repairs to the old screen. Reasons are in "What changed" below.

## Open questions
1. **No override on money limits.** To spend more than the weekly amount, or below the cash you keep, you change the number in "My plan" first. Recommend **yes**. The other choice is a "go over this once" button on the list, which brings back the daily decision you want to escape.
2. **Weekly amount to start with.** Recommend **$25,000 a week** (GUESS). With a 60/30/10 mix there is about $157K to place, so that takes about 7 weeks. $50,000 a week would take about 4.
3. **Sectors: a cap only, no sector targets.** Recommend **cap only** (no sector above 40% of Equities). Today your largest is Consumer Staples at 27%. Sector targets, as in Spec 14, mean about 15 more numbers to set and keep right. They can be added later without rework.
4. **Sells.** Recommend **a note only** for now ("Fixed Income is 3 points above its range, about $32K"), with no sell lines and no tax estimates. With 25% in cash you will not need sells for months.
5. **The old screen ("Build new" and "Portfolios").** Recommend **leave it as it is, rename the tabs "Explore" and "Paper models", and spend no repair work on it now.** The database shows it has never been used to the end: 0 saved models, 0 saved sets, 0 kept holdings. Spec 14's four repairs can be a later round if you miss them.

## What changed vs Spec 14

| Topic | Spec 14 | Spec 15 | Why |
|---|---|---|---|
| Limits | All soft: "warn but never block" | **Money limits hard, drift and opinions warn** | You said "make sure I don't exceed". A warning you can click past every day is not a limit |
| The list | Top block, then "beyond the budget" lines, then "beyond the cash" lines in red | **One list, at most 6 lines, all inside every limit.** One sentence says how much is still to go | The extra sections are a menu of ways to overspend, and more to read |
| How money is spread | Each line sized to the name's full gap, in class order | **This week's money is shared across the 6 biggest gaps** | Tested on your real data: Spec 14's way would put most of a week into one or two names |
| When to act | Only when a class is outside its range | **Whenever there is spare cash above the cash target and something is under target** | With 25% cash, the range test adds nothing. Ranges become a drift warning only |
| Inside a class | Segments (share of class), then names (share of segment); shares must add to 100 | **One flat list of names with a share. Filled from your holdings in one click. Shares are scaled for you** | About 45 names are ready in one click, and nothing has to add to 100 |
| Sectors | A target per segment | A cap only (Open question 3) | Fewer numbers to keep right |
| Sells | Trim lines, tax estimate, smallest gain first, kept holdings | A note only (Open question 4) | Not needed for months; removes the tax and keep-list work |
| Account types | 401k "guide only", placement by type as an option | **Dropped for now** | Every account's type in the database is still "OTHER". The rule would never fire |
| Small accounts | Not covered | A "Use for buys" tick per account | HSA, A and Ra hold $11K of cash between them |
| Old data | List still shown, with a red card | **No list** until new position files are loaded | A list built on old cash is how overspending happens |
| Daily cap | Yes, equal to the weekly cap | Dropped | One visit a week makes it the same number twice |
| Repairs to the old screen (0a-0d) | Do first | Not in this round (Open question 5) | They repair paper tracking, which is not on the way to your goal |
| Tabs | This week, Set the build, Explore, Models | This week, My plan, Explore, Paper models | Same idea; the last two are untouched |
| Size of work | 4 repairs + 8 tasks, 3 new tables | **5 tasks, 3 small tables**; Task 1 is useful on its own | Shorter route to the first time saved |
| Mock-up numbers | Made up | Real, from your accounts | Read-only queries were allowed this round |

**What Spec 14 got right and is kept:** one target for all accounts together, not one per account; the "This week" card as the first thing you see; the Done tick so cash is not counted twice; the weekly email using the existing mail code; Final Call as information only; nothing trades by itself.

## Design

### 1. Review of today's Builder
- **Strong:** honest sums. It reads the same position files and uses the same class map as the Portfolio pie. The class, beta, sector and style comparison is a good research view.
- **Weak for your goal:** it starts from zero on every visit. It rebuilds a whole account as if it were all cash. It knows nothing about real cash or a weekly amount. It works one account at a time. It never says "do this".
- **Over-built for your goal:** recipes, Quad tilt, back-tests, compare variants, frozen paper models and nightly marks. None of it tells you what to buy this week. None of it has been used to the end (0 models, 0 saved sets, 0 kept holdings in the database).
- **Missing:** a saved plan, an all-accounts view, a weekly answer, and limits that hold.

### 2. Tabs
`[ This week ]  [ My plan ]  ...........  [ Explore ]  [ Paper models ]`
- **This week** is the default. If no plan is saved, it shows only: "Set your plan first" and a button to My plan.
- **Explore** is today's "Build new", unchanged. **Paper models** is today's "Portfolios", unchanged. Both sit at the right, out of the weekly path.
- All tabs use the full page width.

### 3. "This week" tab
Real numbers from 2026-11-13. The 60/30/10 mix is only an example, not advice.
```
+----------------------------------------------------------------------------------------------------------------------+
| THIS WEEK                                                                   Positions 11-13 · Prices 11-13 · Wk of 11-09 |
| [AMBER]  6 buys, about $24.1K, in 2 accounts.  All inside your limits.                                               |
|          After this week: $132.6K still to place, about 6 more weeks at $25K a week.                                 |
+----------------------------------------------------------------------------------------------------------------------+
| BUY LIST                                                                         Week: $24.1K of $25K · left $0.9K   |
| #  Shares  Name  Account  About    Why                                                          Call   Done          |
| 1  [ 34]   XLV   F-M      $6.4K    Equities are 19.6 points under target. XLV has the biggest gap.  --    [ ]        |
| 2  [ 49]   XLP   IRA      $4.5K    Equities under target. XLP is $14.5K under its share.         --    [ ]        |
| 3  [ 38]   KO    IRA      $3.8K    Equities under target. KO is $12.0K under its share.          --    [ ]        |
| 4  [  3]   COST  F-M      $3.3K    Equities under target. COST is $10.7K under its share.        --    [ ]        |
| 5  [  2]   LLY   F-M      $2.9K    Equities under target. LLY is $10.5K under its share.         --    [ ]        |
| 6  [ 17]   ABNB  F-M      $3.2K    Equities under target. ABNB is $10.4K under its share.        --    [ ]        |
+------------------------------------------------------------+---------------------------------------------------------+
| THE MIX, ALL ACCOUNTS ($1,055,081)     now -> after  target | LIMITS                                                  |
| Equities      [=========|   ]   40.4% -> 42.7%   60  (55-65)| ✓ No account spends more than its cash                  |
| Fixed Income  [=======|=]       32.4% -> 32.4%   30  (25-35)| ✓ Every account keeps at least $1,000                   |
| Cash          [=====|          ] 24.8% -> 22.6%  10 (7.5-12.5)| ✓ Week: $24.1K of $25K                                |
| Currency      [|]                1.1% ->  1.1%   no target  | ✓ Biggest stock after buys: KO 2.7% (limit 5%)          |
| No class      [|]                1.3% ->  1.3%   LVHI [set] | ✓ Biggest fund after buys: CLOX 9.0% (limit 20%)        |
| Total                           100%  -> 100%               | ✓ Biggest sector: Consumer Staples 27.4% (limit 40%)    |
|                                                             | NOTES                                                   |
|                                                             | ! Equities are 14.6 points below their range (55-65)    |
|                                                             | ! Cash is 12.3 points above its range (7.5-12.5)        |
|                                                             | ! LVHI ($13.3K) has no asset class. Set it.             |
+------------------------------------------------------------+---------------------------------------------------------+
| ACCOUNTS         Value      Cash      Keep     Can spend   This week   Use for buys                                  |
| F-M            $451,064   $83,804   $1,000    $82,804     $15.8K       [x]                                           |
| IRA            $419,745   $82,157   $1,000    $81,157      $8.3K       [x]                                           |
| F-A            $171,635   $84,856   $1,000    $83,856        $0        [x]                                           |
| HSA              $7,219    $7,219   $1,000     $6,219        $0        [x]                                           |
| A                $4,063    $4,063   $1,000     $3,063        $0        [x]                                           |
| Ra               $1,355       $77   $1,000         $0        $0        [x]                                           |
+----------------------------------------------------------------------------------------------------------------------+
```
- **Card.** One sentence of what to do, one sentence of how far there is to go.
  - Green (`--act-buy-bg` / `--act-buy`): "Nothing to do this week."
  - Amber (`--mr-warn-bg` / `--mr-warn`): "N buys, about $X, in M accounts. All inside your limits."
  - Red (`--act-sell-strong-bg` / `--act-sell-strong`): one reason and one fix, and **no list**. Example: "IRA's position file is 5 trading days old. Load a new one, then look again."
- **Buy list.** At most 6 lines. Every line is inside every hard limit when it is shown.
  - **Shares box.** You may lower it or type 0. If you raise it past a limit, it snaps back to the most allowed and says why in plain words: "Most here is 41 shares: IRA's cash."
  - **Call** shows today's Final Call badge as information. It never changes the list.
  - **Done** records the line. The line turns grey and its dollars count against the week and that account's cash.
- **The mix.** Bars reuse `.bld-viz .vtrack2`: fill = after, thin grey bar = now, black ticks = range ends, a longer tick = target. A bar outside its range gets an amber outline. No green or red on the bars, because drift is not good or bad.
- **Limits** shows a tick per hard limit with the real number. These always pass, because the list is built inside them. Their job is to let you see it at a glance.
- **Notes** are the warnings. Amber `!` only. They never stop anything.
- **"No class" row.** A small "set" picker saves the class on the spot. It uses the existing `POST /api/builder/asset-class`.
- **Accounts table.** "Can spend" = cash minus the cash to keep, minus Done buys not yet in a position file. Unticking "Use for buys" keeps the account in the mix but never buys in it.
- **Tooltips are bulleted lists.** Example on line 1:
  - Equities now 40.4% of all accounts, target 60%
  - XLV share of Equities: 10.0% in your list
  - XLV now $42.5K, target $63.1K, gap $20.6K
  - This week's share of the $25K: $6.5K, which is 34 whole shares at $188.85
  - F-M can spend $82.8K; chosen because it already holds XLV and has the most cash
  - After the buy XLV is 4.6% of all accounts (fund limit 20%)

### 4. "My plan" tab
```
+----------------------- THE MIX (all accounts) -----------------------+------------------- LIMITS ---------------------+
| Start from: [What I hold now] [Balanced 60/30/10] [Growth] [Defensive] | HARD - the list never breaks these           |
|             [All-weather]                                             |  Most to spend in a week        [$25,000]     |
| Class          Target   Range      Now                                |  Cash to keep in each account   [ $1,000]     |
| Equities        [60]    55 - 65    40.4%                              |  One stock, at most             [  5 ] % all  |
| Fixed Income    [30]    25 - 35    32.4%                              |  One fund, at most              [ 20 ] % all  |
| Gold            [ 0]    -           0.0%                              |  One sector, at most            [ 40 ] % Eq.  |
| Commodities     [ 0]    -           0.0%                              |  Smallest buy                   [ $1,000]     |
| Crypto          [ 0]    -           0.0%                              |  Most lines in a week           [  6 ]        |
| Currency        [ 0]    -           1.1%                              | WARN ONLY                                     |
| Cash            [10]    7.5 - 12.5  24.8%                             |  A class outside its range                    |
| Total           100 ✓                                                 |  A name you hold that is over its limit       |
|                                                                       |  Final Call says Sell on a name in my list    |
|                                                                       |  Risk Dial says "No new risk"                 |
+--------------------------------- MY LIST ---------------------------------------------------------------------------+
| [Fill from what I own]  [+ Add a name]                         38 names in Equities · 5 in Fixed Income · 1 Currency |
| EQUITIES (60% = $633K)                                                                                               |
| Name   Sector             Share   = of all   Target $   Now $     Gap $     Call   Limit                            |
| XLV    Health Care        [10.0]   6.0%      $63.1K     $42.5K   $20.6K     --     fund 20% ✓                 [x]   |
| XLP    Consumer Staples   [ 7.0]   4.2%      $44.6K     $30.0K   $14.5K     --     fund 20% ✓                 [x]   |
| KO     Consumer Staples   [ 5.8]   3.5%      $36.8K     $24.8K   $12.0K     --     stock 5% ✓                 [x]   |
| ...                                                                                                                  |
| Sectors: Staples 27% · Health Care 26% · Tech 23% · Discretionary 9% · Financials 7% · ...   (limit 40% each ✓)     |
| FIXED INCOME (30% = $317K)   CLOX 27.7 · BUXX 27.2 · IEF 17.1 · FXNAX 14.5 · TLT 13.4                                |
+----------------------------------------------------------------------------------------------------------------------+
| [Save my plan]    Saved 11-13.                                                                                       |
+----------------------------------------------------------------------------------------------------------------------+
```
- **Start from** copies a preset or your current mix into the boxes. Presets come from the existing `ref_pb_mix_preset`. Nothing saves until you press Save.
- **Fill from what I own** adds every holding to the list with a share equal to its share of its class today. So the first lists top up what you already own, in today's proportions. You then remove names you do not want more of and add new ones.
- **Share** is the name's share of its class. You do not need to make shares add to 100: the screen scales them and shows the result in "= of all". A blank share means "an equal slice of what is left".
- **Removing a name** from the list never sells it. It only means "do not buy more". Its dollars still count in its class.
- **Add a name** is a symbol box. The class and sector come from the Portfolio pie's map. A name with no class must be given one before it can be added.
- **Limit column.** If a name's target would be above its limit, the target is cut to the limit and the cell says "cut to 5%". This is shown, not refused.
- **Ranges** are filled in for you (rule below). They are used for notes only.

### 5. Hard and soft limits (the decision the brief asked for)
**Rule of thumb: anything that spends money is hard. Anything about drift or opinion only warns.**

| Limit | Hard or warn | What the screen does | Why |
|---|---|---|---|
| An account's own cash | **Hard** | Never lists or accepts a buy the account cannot pay for. No cash moves between accounts | It is a fact, not a preference. This is the literal "don't exceed the money" |
| Cash to keep in each account | **Hard** | Buys stop at the floor | A buffer for fees, price moves and orders the app cannot see |
| Household cash target | **Hard** | Only cash above the Cash target is ever spent | Otherwise the list would break the mix you set |
| Weekly amount | **Hard** | The list and Done ticks together never pass it | This is the pace you chose. A soft one would be re-decided every day |
| One stock / one fund / one sector | **Hard for new buys** | A buy is shrunk to stop at the limit | The screen should never make a name too big |
| Smallest buy, most lines | **Hard** | Smaller lines are not listed; no more than 6 lines | Keeps the list short |
| Old position file (over 3 trading days) | **Hard** | Red card, no list | Old cash numbers are how overspending happens |
| Plan that makes no sense | **Hard** | Save is refused with the reason | See "Save is refused when" |
| A name you already hold above its limit | Warn | A note with the amount over | The screen cannot undo what you hold |
| A class outside its range | Warn | A note; if above, the dollars to trim | Markets move; this is information |
| Final Call says Sell on a list name | Warn | Badge on the line and a note | Calls are short-term; you set the list on purpose |
| Risk Dial says "No new risk" | Warn | A note on the card | Same reason |
| Holdings with no class | Warn | A note with a "set" picker | Does not affect cash safety |

To go past a hard limit you edit the number in My plan and save. There is no override on the list (Open question 1).

### 6. The weekly routine
- Once a week: open the Builder, or read the Monday email. Green: close it. Amber: place the lines, tick Done. Red: do the one thing it says. About five minutes.
- **What you can stop doing for this money:** watching the Actionable screen daily, scanning the Hedgeye lists for buys, and checking the Portfolio pie. Explore is for changing "My list" a few times a year.

### 7. Weekly email (step 3)
- Reuses `etl/notify.py::send_email` and the `maybe_send_watch_digest` pattern in `etl/scheduler.py`. No new outside service. No mail settings means nothing is sent.
- Monday at 8, after the newest position files. Sent every week, even when green, so silence never hides a broken job.
- Subject: "Build: nothing to do", "Build: 6 buys, $24.1K", or "Build: needs a look".
- Body: the card, the buy lines, then the notes as bullets.

### Worth reconsidering
- **Repairing the paper-model screen first (Spec 14's 0a-0d).** It delays the first time saved by four tasks and repairs something that has never been used. Park it.
- **Per-name signals deciding when to buy (Spec 14's phase 2).** This pulls you back to daily signals. A fixed weekly amount already spreads the timing. Leave it out unless the simple list proves too blunt.

## Rules & numbers

### Where the numbers come from
- **Holdings, cash, value per account:** the newest position files (`builder_data.account_positions`). Cash is decided by the database function `is_cash()`.
- **Class and sector of a name:** the Portfolio pie's map (`classify_holdings`). Your own choice from `POST /api/builder/asset-class` wins.
- **Prices:** the app's latest quote on the app's data date; if missing, the broker's price in the position file.
- **Fund or stock:** a fund if it is on `ref_pb_universe` or the position file's type says fund or ETF. Unknown counts as a stock (the stricter limit). The developer must check the real type values in the position files.
- **The week:** Monday to Sunday of the app's data date, never the computer clock.

### Starting numbers (all can be changed in My plan)
| Number | Start | Source |
|---|---|---|
| Weekly amount | $25,000 | **GUESS** (about 2.4% of all accounts) |
| Cash to keep per account | $1,000 | **GUESS** |
| One stock | 5% of all accounts | **GUESS**. Largest today: KO 2.4% |
| One fund | 20% of all accounts | today's `fund_cap`. Largest today: CLOX 9.0% |
| One sector | 40% of Equities | today's sector cap. Largest today: Consumer Staples 27.0% |
| Smallest buy | $1,000 | **GUESS** (0.1% of all accounts) |
| Most lines a week | 6 | **GUESS** |
| Range | target plus or minus the smaller of 5 points or a quarter of the target | **GUESS** (a common rule). 60 gives 55-65; 10 gives 7.5-12.5 |
| Old position file | more than 3 trading days | existing rule |
| Old price | no price in 3 trading days | existing rule |
| Possible split | a move of 40% or more in one day | existing rule |

### How the list is made (same data in, same list out)
1. **Stop with a red card and no list if:** no plan is saved; an account ticked "Use for buys" has a position file more than 3 trading days old; or total value is 0.
2. **Now:** dollars per class and per name across all accounts. Cash and "No class" are their own rows.
3. **Spare cash** = all-accounts cash minus (Cash target % x total value). If it is under the smallest buy: green card, no list.
4. **Class gap** = (class target % x total value) minus what the class holds. Only classes under target count.
5. **Name target** = class target dollars x the name's scaled share, cut to the stock or fund limit. **Name gap** = name target minus held dollars, if above 0. Gaps in a class are scaled down so they add up to no more than the class gap.
6. **This week's money** = the smallest of: weekly amount minus this week's Done buys; spare cash; total "can spend" across ticked accounts.
7. **Pick the lines.** Skip names with an old price or a possible split, and say so in a note. Rank the rest by name gap, biggest first; ties by symbol A to Z. Take the top 6.
8. **Share the money** across those lines in proportion to their gaps. No line gets more than its gap.
9. **Choose the account** for each line, in list order: among ticked accounts that can pay the whole line, prefer one that already holds the name, then the one with the most "can spend", then name A to Z. If none can pay the whole line, use the account with the most "can spend" and shrink the line to fit.
10. **Shrink for the limits.** Cut the line so the name stays inside its stock or fund limit and its sector stays inside the sector limit, counting earlier lines.
11. **Whole shares, rounded down.** Drop a line that ends under the smallest buy. Dropped money is not handed to other lines this week; it stays as cash for next week.
12. **After mix** = now plus the buys, per class. Cash falls by the same dollars, so both columns add to 100%.
13. **Still to go** = spare cash minus this week's buys. Weeks = that divided by the weekly amount, rounded up.

**Checked on real data (2026-11-13, 60/30/10, list filled from holdings):** spare cash $156,669; six lines, $24,099, in F-M and IRA; Equities 40.4% to 42.7%; Cash 24.8% to 22.6%; no limit touched. The same test with equal shares for every name bought the six smallest holdings first (CELH, SOFI and so on). That is why "Fill from what I own" copies today's proportions.

### Can spend, and Done ticks
- **Can spend** (per account) = cash minus the cash to keep, minus Done buys recorded after that account's newest position file. Never below 0.
- A Done tick counts against the week it was ticked in, for the whole week.
- When a newer position file arrives for the account, its Done buys stop reducing "can spend", because the file now shows the lower cash.
- Unticking Done removes the record.
- Orders placed without a tick are invisible until the next position file. The card says: "Tick Done for what you placed."

### Typing in the Shares box
- Lower or 0 is always allowed.
- Higher is allowed up to the smallest of: what the account can spend, what is left of the week, and the room under the name and sector limits. Above that, the box snaps to the most allowed and names the limit.

### Save is refused when
- Class targets do not add to 100 (plus or minus 0.1).
- Any number is negative, or a range's low end is above its high end.
- The weekly amount or the smallest buy is 0 or blank.
- A list name has no class.

### Notes (warn only), with wording
- "Equities are 14.6 points below their range (55-65)."
- "Fixed Income is 3 points above its range, about $32K. Consider trimming." (No sell lines.)
- "NVDA is 6.1% of all accounts, 1.1 points over your 5% stock limit. No more will be bought."
- "Final Call says Sell on KO. It is in your list, so it is still bought. Remove it from the list if you agree with the call."
- "Risk Dial says no new risk."
- "LVHI ($13.3K) has no asset class. Set it."
- "SOFI skipped: no price for 3 trading days."

### Edge cases
- **An account with no position file:** left out and named in a note.
- **A class with a target but no list names:** note "Gold has a target but no names. Add one." Its gap is not bought.
- **A class with holdings but a target of 0:** shown with "no target". A note appears only above 2 points (**GUESS**).
- **Every gap is smaller than the smallest buy:** green card, "Nothing worth a trade this week."
- **Mutual funds with no app quote:** broker price, whole shares only.
- **A plan saved today, then position files reloaded:** the list is always worked out fresh. Nothing is stored except the plan, the list of names and the Done ticks.
- **The app never knows about money you add or withdraw** until the next position file. The cash to keep is the buffer.

### Found while reviewing (not design changes)
- Every account's type in `ref_accounts.account_type` is unset, so it reads "OTHER". Any future rule based on account type needs these set first.
- LVHI has no asset class in the pie's map.
- The fund list spells an area "Short Duration Tresuries" (`db/seeds_portfolio_builder.sql`).
- On "Build new", the Warnings tick-boxes and the missing Accept button are as Spec 14 describes. Left alone in this round.

## Files likely touched
- `etl/build_guide.py` (NEW, pure functions, no database) — `ranges_for`, `validate_plan`, `scale_shares`, `name_targets`, `can_spend`, `buy_list`, `max_shares` (for the Shares box), `limit_checks`, `notes`, `card_status`.
- `etl/builder_data.py` — add `household_context(session, d)`: every account's holdings, cash, file date, prices, class and sector. Reuses `account_positions` and `classify_holdings`. Nothing existing changes.
- `etl/builder_store.py` — save and read the plan, the list of names and the Done ticks.
- `api/routers/builder.py` — new endpoints below. Existing ones untouched.
- `web/builder.html` — two new tabs first, old tabs renamed; `.bg-*` styles; bump `?v=`.
- `web/builder_guide.js` (NEW) — the two new tabs. `web/builder.js` — tab switching only.
- `etl/scheduler.py` — `maybe_send_build_digest`, modelled on `maybe_send_watch_digest`.
- `db/baseline.sql` — three tables below. `db/seeds_build_guide.sql` — `ref_settings` rows `build_digest_weekday` (1) and `build_digest_hour` (8).
- `docs/portfolio_builder_logic.md` — new section "Plan and weekly buy list"; one CLAUDE.md lookup row.
- `tests/test_build_guide.py` — pure-function tests.

### New tables
`user_build_plan` (one row)

| column | type | note |
|---|---|---|
| plan_id | SERIAL PK | always 1 |
| mix | JSONB | {class: target %}, Cash included |
| ranges | JSONB | {class: [low, high]}; missing = worked out by the rule |
| week_budget_usd, cash_floor_usd, min_trade_usd | NUMERIC | 25000 / 1000 / 1000 |
| stock_cap_pct, fund_cap_pct, sector_cap_pct | NUMERIC | 5 / 20 / 40 |
| max_lines | INT | 6 |
| accounts | JSONB | {account short name: {"buy": true}}; missing = true |
| updated_at | TIMESTAMPTZ | |

`user_build_name` (My list)

| column | type | note |
|---|---|---|
| name_id | SERIAL PK | |
| tos_symbol | TEXT UNIQUE | |
| share | NUMERIC | share of its class; NULL = equal slice of what is left |
| active | BOOLEAN | |
| added_at | TIMESTAMPTZ | |

`user_build_done`

| column | type | note |
|---|---|---|
| done_id | SERIAL PK | |
| account_short, tos_symbol | TEXT | |
| shares, est_price, est_usd | NUMERIC | |
| list_date | DATE | the app's data date when ticked |
| done_at | TIMESTAMPTZ | |

No derived table. The list is worked out when asked; the email calls the same function.

### New endpoints
- `GET /api/builder/plan` — plan, ranges, list of names with targets and gaps, current mix.
- `PUT /api/builder/plan` — save; 400 with a plain reason when refused.
- `POST /api/builder/plan/names` (one name, or `{"from_holdings": true}`), `PATCH` and `DELETE /api/builder/plan/names/{id}`.
- `GET /api/builder/guide?date=` — card, lines, mix now and after, limit checks, notes, accounts table.
- `POST /api/builder/guide/check` — body: the edited shares; returns the snapped shares and fresh totals. Reads only.
- `POST /api/builder/done`, `DELETE /api/builder/done/{id}`.

### Build plan (each task ships and is useful on its own)

| # | Task | You get | Checks (behaviour only) | DB |
|---|---|---|---|---|
| 1 | **Mix check.** Plan table, plan endpoints (mix, ranges, limits), "My plan" top half, "This week" card + mix + accounts table | A saved target and a weekly view of where the cash should go by class, for all accounts | Targets not adding to 100 are refused; ranges follow the rule; mix adds to 100%; an old position file gives a red card | Yes |
| 2 | **Buy list engine** (pure): `scale_shares`, `name_targets`, `can_spend`, `buy_list`, `max_shares`, `limit_checks`, `notes` | Nothing visible yet | On made-up books: per account, buys never exceed cash minus the floor; total never exceeds the weekly amount or spare cash; no name or sector passes its limit through a buy; no line under the smallest buy; at most `max_lines`; whole shares; now and after each add to 100%; same input gives the same list; a name already over its limit gets a note and no buy | No |
| 3 | **My list + buy list on the page.** Names table and endpoints, "Fill from what I own", `GET guide` with lines, Shares box with snap-back | The weekly buy list | Fill from holdings copies today's proportions; a typed share above a limit comes back snapped with the limit named; removing a name never produces a sell | Yes |
| 4 | **Done ticks.** Done table and endpoints | Cash and the week are not counted twice | A tick lowers "can spend" and the week's room; a newer position file stops it lowering "can spend"; untick restores | Yes |
| 5 | **Monday email + docs** | The list in your inbox | Sent at most once a week; tests replace `send_email` with a fake, so no real email is ever sent | Faked |

Tasks 1 to 4 are the whole product. Task 2 needs no database.

### Risks and how each is handled
| Risk | Handling |
|---|---|
| Old position files | Red card, no list |
| Old price or possible split | The name is skipped that week, with a note |
| Orders the app cannot see | Done ticks; the cash to keep as a buffer; a reminder on the card |
| Whole-share rounding | Always down; the rest stays cash |
| The broker lets you buy more than the list | The app cannot prevent it. The next position file shows it and the list adjusts |
| A wrong class on a name | Shown per name in My list; one picker to correct it |
| The example mix read as advice | The mock-up says it is an example; nothing is saved until you choose |

## Status
READY_FOR_DEV — Tasks 1 to 5, after the user answers Open questions 1 to 5 (each has a recommendation that the tasks assume). Replaces Spec 14's build plan; Spec 14's repairs 0a-0d are parked.
