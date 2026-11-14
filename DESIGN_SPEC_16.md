# Design Spec — DESIGN_WORK_16

## Goal
Let the user set a plan in percentages for each account, switch it on, then pick buys, sells and "buy any one of these" groups with dollar amounts while the screen shows what is left in that account, and warn on the Actionable screen when a buy would break that account's active plan.

### In plain English (one page)
- **Each account stands alone.** F-M, IRA, F-A, HSA, A and Ra each have their own plan. Every percentage is a share of that one account. Nothing is added across accounts anywhere.
- **Step 1: the plan.** Choose an account. Type percentages for asset classes, sectors, styles and "My stocks". This is the table you already use on the Builder. Change it any day. Save as many drafts as you like.
- **Step 2: Activate.** One plan per account is ACTIVE. Activating changes only the checks and warnings for that account. Nothing trades. An account with no active plan is not checked.
- **Step 3: pick.** Two separate lists to pick from: **Hedgeye names** (what Hedgeye is bullish on) and **My stocks** (names you add yourself). A stock is in only one list. Tick a name and type dollars or shares.
- **Step 4: sells.** The same tab lists Actionable's Sell names held in that account. Tick the ones you will sell. The cash is added to that account only, marked "expected, not yet in your broker file". Room opens up in the class, sector and style of what you sell.
- **Groups: "buy any one of these".** You do not know when Actionable will say Buy. So you make a group, for example "Tech leaders: MSFT, NVDA, AAPL, $9K" in IRA. The $9K is set aside at once, so it cannot be spent twice. When any member gets a Buy call, Actionable shows a note on that row. Buying one member fills the group.
- **"What is left" is always on screen**, for the chosen account only: plan, now, picks, reserved for groups, and left, in dollars. Each name shows the most you can still add and which line stops it. Leaving money in cash is fine.
- **Money limits block. Percentages only warn.** You cannot pick or reserve more than the account's cash, go below the cash you keep, or take cash below the plan's Cash %. Going over a class, sector, style or My stocks percentage is allowed, with an amber note that says how much over and the most that fits.
- **Actionable warnings always name the account**: "Over plan in IRA". They never change the Final Call.
- **Real numbers for IRA today (2026-11-13):** value $419,745, cash $82,157 (19.6%), Equities 38.9%, Fixed Income 36.9%. With an example plan of Equities 52%, Fixed Income 34%, Cash 12%: Equities has $54.9K of room, Fixed Income is $12.3K over, and $31.8K of cash can be spent.
- **Picks last until the next broker file.** When a new position file lands for an account, its picks and sell ticks drop away. Groups stay until they are filled, closed or expire.

## What changed vs the first Spec 16
| Topic | First Spec 16 | Now | Why |
|---|---|---|---|
| Scope of a plan | One plan for all accounts together | **One plan per account.** Every % is a share of that account | Your decision |
| All-accounts figures | Household mix, household cash target, accounts table | **Removed everywhere.** No blended numbers | Your decision |
| Cash limit | All-accounts cash never below the plan's Cash % | **This account's cash never below its plan's Cash %** | Follows from per account |
| "Use for buys" tick per account | Yes | **Dropped.** An account with no active plan is simply not checked | Simpler |
| Account for a pick | Chosen per pick line, with a default rule | **The Pick tab starts by choosing an account.** Every pick is in that account | Your decision |
| "Risky" | A tag you could put on any name | **Renamed "My stocks".** A separate list. A stock is in the Hedgeye list or in My stocks, never both | Your decision |
| Hedgeye adds one of your stocks | Not covered | **It leaves My stocks by itself** and counts as a Hedgeye name | Your decision |
| Groups | Not covered | **New: "buy any one of these"**, with the dollars reserved at once | Your decision |
| After Activate | Not covered | **The account's standing and a pre-filled, unticked picker** (Open question 1) | Default until you choose |
| Actionable pill | "Over plan", one check per row | **"Over plan in IRA"**: one check per account that has an active plan | Your decision |
| Actionable summary | One all-accounts line | **One short line per account** | No blended numbers |
| "fits $X" under AMT$ | Yes | **Dropped.** The per-account numbers are in the tooltip | One row can now have several accounts |
| Open question on plan scope | Open | **Settled** | Your decision |
| Open questions on block or warn, and when sell cash counts | Open | **Settled:** money blocks, percentages warn, sell cash counts when ticked | Your decision |

## Open questions
1. **What you see right after Activate.** Recommend: the Pick tab for that account opens with **(a)** where the account stands against its plan, for example "Equities 38.9% vs plan 52%, $54.9K room", and **(b)** the picker filled with Actionable's current Buys and Sells for that account, **unticked, with no amounts**. Nothing is created for you. The other choice is to stay on the Plan tab and show only "Activated".
2. **Replace the "Build new" tab with Plan and Pick.** Recommend **yes**. They reuse its two halves: the target tables and the names list. What goes away: the "% of class" box per pick and the "To match" column. "Paper models" stays as it is.
3. **Hedgeye later drops a stock it took from My stocks.** Recommend: **it does not go back by itself.** A note says "MSFT is no longer a Hedgeye name" with a one-click "Put back in My stocks". The other choice is to move it back automatically, which could push My stocks over its % without you doing anything.
4. **A group is filled by one buy, even a smaller one.** Recommend **yes**: if you reserve $9K and buy $6K, the group is filled and the other $3K is free again. You can reopen the group or raise its amount. The other choice keeps the $3K reserved until you close the group.
5. **Which amount Actionable checks in each account.** Recommend the **per-account size the Actionable popup already shows** (IRA's unit is $2,000; its minimum is $4,000), not the all-accounts AMT$. For a name you do not hold, every account with an active plan is checked and the tooltip says where it fits.

## What changed vs Spec 15

| Topic | Spec 15 | Spec 16 | Why |
|---|---|---|---|
| Who chooses the trades | The Builder made a list of at most 6 buys | **You pick names and amounts.** The Builder checks and counts | Your words: "choose a list of stocks I want to buy and set amounts" |
| Scope | One target for all accounts together | **One plan per account; accounts never blended** | Your decision |
| Weekly dollar amount | Hard, $25K a week | **Dropped** | You said no fixed weekly amount |
| 6-line cap, smallest buy | Hard | **Dropped** | You decide when to stop |
| "My list" of names with a share each | Needed for the list engine | **Dropped.** You pick from Hedgeye names and My stocks | No shares to keep right |
| The plan | One saved plan: class mix, ranges, limits | **Many drafts, one ACTIVE per account.** Class, sector, style, beta, Quad and My stocks percentages | Your words: "assign % every day, then activate" |
| Sectors | A 40% cap only | **A percentage per sector**, as on today's screen | You asked for sectors and styles |
| Ranges around each target | Target plus or minus 5 points | **Dropped.** Each % is a ceiling for buys. Under it is room, not a warning | One number per line; "left" is a plain dollar figure |
| One stock 5%, one fund 20% | Hard | **Dropped.** Actionable's own OVER MAX pill already covers a name that is too big | Fewer numbers |
| Class, sector, style drift | Notes on the side | **Warn on the pick itself**, with the amount over and the most that fits | Confirmed: percentages warn |
| Money limits | Hard | **Still hard**, per account: cash, cash kept, cash below the plan's Cash % | Confirmed: money blocks |
| Your own names | Not covered | **"My stocks" list with its own %** | New need |
| Waiting for a signal | Not covered | **Groups that reserve dollars** | New need |
| Sells | A note only | **Tick Actionable's Sell names; expected cash and room are counted** | New need |
| Done ticks | A tick per line | **None.** Picks and sell ticks clear when the account's next broker file lands | Same protection, no extra clicks |
| Actionable screen | Final Call shown inside the Builder only | **Plan pill and group note on Actionable buy rows** | New need |
| Monday email | Task 5 | **Dropped** | There is no machine-made list to send |
| Tabs | This week, My plan, Explore, Paper models | **Plan, Pick, Paper models** | See Open question 2 |

**Kept from Spec 15:** hard money limits with no override; no checks on an old position file; plain-English reasons; OK / Shrunk / Blocked; mix bars showing now and after; nothing trades by itself.

## Design

### 1. Tabs and the account chooser
`Account [ IRA · plan active v ]      [ Plan ]  [ Pick ]  ...........  [ Paper models ]`
- The account box is the one already on the Builder. Each entry shows its state: `plan active`, `draft only`, or `no plan`. There is no "all accounts" entry on Plan or Pick.
- **Plan** is where the percentages live. **Pick** is where you choose trades. Both show the chosen account only and use the full page width.
- A strip under the tabs:
  - Green pill (`--act-buy-bg` / `--act-buy`): `IRA · ACTIVE: Steady IRA · since 11-13`
  - Grey pill: `IRA has no active plan. It is not checked.`
  - Amber pill (`--mr-warn-bg` / `--mr-warn`), Plan tab only: `You are editing a draft. IRA's active plan has not changed.`
- **Pick** with no active plan for the account shows only: "Activate a plan for IRA first", a button to the Plan tab, and "Copy another account's plan".

### 2. Plan tab
IRA's real "now" numbers from 2026-11-13. The percentages are an example, not advice.
```
+------------------------------------------------------------------------------------------------------------------------------+
| Account [IRA v]   Value $419,745 · Cash $82,157 (19.6%) · Positions 11-13                                                    |
| IRA · ACTIVE: Steady IRA · since 11-13     [amber] You are editing a draft. IRA's active plan has not changed.               |
| Plan [Steady IRA  v] [Open] [Save draft] [Save as...] [Delete]   [ ACTIVATE FOR IRA ] [Turn off]                             |
| Start from [What IRA holds now v]   Copy from [another account's plan v]                                                     |
+---------------------------------------+---------------------------------------+----------------------------------------------+
| ASSET CLASS      Plan %  = $    Now   | SECTORS (stocks)  Plan %  = $    Now  | STYLE (stocks)     Plan %  = $     Now       |
| Equities         [52]  $218.3K  38.9% | Cons. Staples     [18]   $75.6K 17.2% | Defensive          [50]  $209.9K  38.9%      |
| Fixed Income     [34]  $142.7K  36.9% | Health Care       [15]   $63.0K 14.2% | Growth             [14]   $58.8K  10.0%      |
| Gold             [ 0]     -      0.0% | Info Technology   [ 7]   $29.4K  1.3% | Offensive          [ 9]   $37.8K   5.2%      |
| Commodities      [ 0]     -      0.0% | Financials        [ 5]   $21.0K  4.1% | Mid                [  ]     -      6.6%      |
| Crypto           [ 0]     -      0.0% | Cons. Discretion. [ 4]   $16.8K  1.2% | Value              [  ]     -      0.9%      |
| Currency         [ 2]    $8.4K   1.4% | Utilities         [ 2]    $8.4K  1.0% +----------------------------------------------+
| Cash (the rest)   12    $50.4K  19.6% | Industrials       [ 1]    $4.2K  0.0% | RISK               Plan %  = $     Now       |
| No class           -      -      3.2% | Adds to 52 of Equities 52 ok          | High beta (>1.2)   [ 5]   $21.0K   1.2%      |
| Total            100 ok               +---------------------------------------+ Low beta (<=0.8)   [  ]     -     36.1%      |
+---------------------------------------+ QUAD FAVOURED     Plan %  = $    Now  | Average beta       guide only                |
| MY STOCKS        Plan %  = $    Now   | Q1 .. Q4          [  ]     -     ...  +----------------------------------------------+
| My stocks        [ 3]   $12.6K   0.0% |                                       | LIMITS THAT BLOCK (this account)             |
| 2 names: MSFT, NVDA    [Edit list]    |                                       | Cash to keep                     [ $1,000 ]  |
+---------------------------------------+---------------------------------------+ Cash never below the plan's Cash %    12%    |
                                                                                | Never spend more than the account has        |
                                                                                | EVERYTHING ELSE ONLY WARNS                   |
                                                                                | Class, sector, style, risk, Quad, My stocks  |
                                                                                +----------------------------------------------+
```
- **Reused from today's screen:** the five small tables, the bar above each one (grey = now, black tick = plan), typing a class % so that Cash becomes the rest, the preset list, and Save as / Open / Delete of named sets (already stored per account).
- **New:** the "= $" column, the My stocks block, the limits card, Activate, Turn off, and "Copy from".
- **Every % is a share of this account's value.** The "= $" column shows the dollars.
- **A blank box means no limit on that line.** It still shows "Now".
- **Start from** fills the boxes from what the account holds now, or from a preset. **Copy from** fills them from another account's active plan or draft. Percentages copy as they are; the dollars are worked out for this account. Nothing is saved until you press Save.
- **Save draft** never changes the checks.
- **ACTIVATE FOR IRA** shows a short confirm box listing what will change, as a bulleted list, for example:
  - Equities 48% to 52%
  - My stocks 2% to 3%
  - Consumer Discretionary 3% to 4%
  Then the plan becomes IRA's active plan. The old one is kept in history. The screen then moves to the Pick tab (Open question 1).
- **Turn off** ends IRA's active plan. IRA's checks and Actionable notes switch off. Other accounts are not touched.
- **What "active" changes:** only the numbers behind this account's Pick tab and this account's Actionable notes. No trade, no Final Call, no amount, no other account.
- **Edit list** opens My stocks (section 5).

### 3. Pick tab
IRA, real prices and holdings from 2026-11-13. The plan, the picks and the group are examples.

**Right after Activate (nothing ticked yet):**
```
+------------------------------------------------------------------------------------------------------------------------------+
| IRA · ACTIVE: Steady IRA · since 11-13                    Value $419,745 · Positions 11-13 · Prices 11-13                    |
| WHERE IRA STANDS AGAINST ITS PLAN                                                                                            |
| - Equities 38.9% vs plan 52%. $54.9K of room                                                                                 |
| - Fixed Income 36.9% vs plan 34%. $12.3K over                                                                                |
| - Cash 19.6% vs plan 12%. $31.8K can be spent                                                                                |
| - Most room by sector: Info Technology $24.0K · Consumer Discretionary $11.9K · Utilities $4.0K                              |
| Actionable has 6 Buy calls and 1 Sell call on names IRA holds. They are listed below, unticked. Nothing is picked for you.   |
+------------------------------------------------------------------------------------------------------------------------------+
```
**After some picking (one sell ticked, one group made, four buys picked):**
```
+------------------------------------------------------------------------------------------------------------------------------+
| [AMBER] IRA: 4 buys, $27.7K. 1 group waiting, $9.0K reserved. 1 sell, $7.9K expected. 3 notes. You can still spend $3.0K.    |
+----------------------------------------------------------------------+-------------------------------------------------------+
| SELLS  (Actionable says Sell on names IRA holds)                     | WHAT IS LEFT IN IRA        Plan    Now  Picks Reserved  Left |
| [ ] Name Call       Held     Sell      Expected  Opens room in       | CASH                                                  |
| [x] TLT  Sell Some  $21.8K  [100] sh    $7,941   Fixed Income        | Cash you can spend               $39.7K $27.7K  $9.0K   $3.0K |
|                                         [+ Sell another holding]     |   $31.8K above your 12% + $7.9K expected from sells   |
+----------------------------------------------------------------------+ Cash after everything  12.7% of IRA (plan 12%)        |
| GROUPS  (buy any one of these)                        [+ New group]  | ASSET CLASS                                           |
| Name          Members            Reserved  Until   State             | Equities     [=====:==|.|  ]  $218.3K $163.4K $27.7K  $9.0K  $18.1K |
| Tech leaders  MSFT · NVDA · AAPL   $9,000  12-31   Waiting. No Buy   | Fixed Income [=========|!]    $142.7K $147.1K    -      -   over $4.4K |
|               call yet.  [Buy one now] [Edit] [Close]                | Currency     [==|  ]            $8.4K   $5.9K    -      -     $2.5K |
+----------------------------------------------------------------------+ SECTORS                                               |
| YOUR PICKS IN IRA  (in the order you picked them)                    | Cons. Staples                  $75.6K  $72.2K  $9.0K    -   over $5.6K |
| # Name  Asked            Allowed          Result     Why             | Health Care                    $63.0K  $59.6K    -      -     $3.3K |
| 1 KDP   [$3,000][ 82 sh]  $2,984  82 sh   OK         Fits every line.                       [x] | Info Technology                $29.4K   $5.3K    -    $9.0K  $15.0K |
| 2 RCL   [$6,000][ 18 sh]  $5,756  18 sh   OK         Fits every line.                       [x] | Financials                     $21.0K  $17.0K    -      -     $4.0K |
| 3 BTI   [$6,000][ 97 sh]  $5,970  97 sh   OVER PLAN  Consumer Staples is $5.6K over.            | Cons. Discretionary            $16.8K   $4.8K $18.8K    -   over $6.9K |
|                                                      $0.4K fits.                      [Fit] [x] | Utilities                       $8.4K   $4.4K    -      -     $4.0K |
| 4 AZO  [$18,000][  5 sh] $13,039   4 sh   SHRUNK     Cash: 4 shares fit. More would take IRA's  | STYLE AND RISK                                        |
|                                                      cash below your 12%. Also over plan:       | Defensive                     $209.9K $163.4K $27.7K  $9.0K   $9.7K |
|                                                      Offensive by $11.9K.             [Fit] [x] | Growth                         $58.8K  $42.0K    -    $9.0K   $7.8K |
+----------------------------------------------------------------------+ Offensive                      $37.8K  $21.9K $18.8K  $9.0K over $11.9K |
| NAMES TO PICK FROM                                                   | High beta                      $21.0K   $4.8K  $5.8K  $9.0K   $1.4K |
| [ Hedgeye names 181 ]  [ My stocks 2 ]      show: [Buy calls today]  | MY STOCKS                                             |
|   [Held in IRA] [All]    filters: class, sector, style, Quad, symbol | My stocks                      $12.6K     $0     -    $9.0K   $3.6K |
|   [Show names with room]                                             +-------------------------------------------------------+
| [ ] Name  Call      Held in IRA  Sector         Most you can add     | ROOM OPENED BY YOUR SELLS                             |
| [ ] RDNT  Buy More    $13.4K     Health Care    $3.0K  cash          | - Fixed Income: $7.9K less. Still $4.4K over          |
| [ ] LFST  Buy More    $11.3K     Health Care    $3.0K  cash          | - IRA cash: $7.9K more (expected)                     |
| [ ] PM    Buy Some    $14.9K     Cons. Staples    $0   Cons. Staples | You can buy where there is room, or leave it as cash. |
| [ ] UL    Buy More      -        Cons. Staples    $0   Cons. Staples +-------------------------------------------------------+
| [ ] GPN   Buy More      -        Financials     $3.0K  cash          |
+----------------------------------------------------------------------+
```

**The top card.** One sentence, about this account only. Green: "All picks fit IRA's plan." Amber: counts of notes. Red: one reason and one fix when checks cannot run, for example "IRA's position file is 5 trading days old. Load a new one."

**Where the account stands.** A bulleted list, shown at the top until the first pick, then folded into one line. It lists each class against its plan and the three sectors with the most room.

**Sells block.**
- Lists every position this account holds where Actionable's Final Call is a Sell. Unticked at first.
- Tick = "I will sell this". Unticked sells never count.
- The Sell box is in shares. Sell All is filled with the whole position. Sell Some is filled with Actionable's amount when it has one, otherwise blank for you to type.
- "Expected" = shares x the latest price. It is added to this account's cash only.
- "+ Sell another holding" lets you add any name the account holds.

**Your picks.**
- **Asked** is what you type, in dollars or shares. Typing one fills the other. Shares are whole and rounded down.
- **Allowed** is what the money limits let through. It is the number that counts in the tally.
- **Result** pill:
  - `OK` green (`--act-buy-bg` / `--act-buy`): allowed = asked, inside every plan line.
  - `OVER PLAN` amber (`--mr-warn-bg` / `--mr-warn`): allowed = asked, but a percentage line is over. Says which line, how much over, and the most that fits.
  - `SHRUNK` amber: a money limit cut the amount. Says which one. If a percentage line is also over, it is added after "Also over plan".
  - `BLOCKED` red (`--act-sell-strong-bg` / `--act-sell-strong`): a money limit leaves nothing. Says which one.
- **[Fit]** sets the amount to the most that fits the plan. **[x]** removes the pick.
- A new pick starts with a blank amount.

**Names to pick from.**
- Two list buttons that never mix: **Hedgeye names** and **My stocks**.
- "show" narrows the list: **Buy calls today** (first), **Held in IRA**, **All**.
- Reuses today's names list and its filters. New columns: Call, Held in this account, and "Most you can add".
- **Most you can add** shows the smallest room across every line the name belongs to, and names that line. A red `$0` means a money limit. An amber `$0` means a percentage line is full.
- **Show names with room** keeps only names that still fit the plan, biggest room first. It replaces "Show what's missing".
- A name the account holds that is on neither list can be sold. To buy more of it, add it to My stocks first.

**What is left in this account.**
- One row per plan line that has a number, plus the cash rows.
- Columns: Plan, Now (after ticked sells), Picks, Reserved (groups), Left.
- Bars reuse `.bld-viz .vtrack2`: thin grey bar = now, solid part = picks, dotted part = reserved for a group, black tick = plan. A bar past its tick turns amber. No green or red on the bars, because drift is not good or bad.
- "Left" in black when there is room. `over $X` in amber when over. The cash row can never go below $0.
- **Room opened by your sells** is a bulleted list. It shows only when a sell is ticked.

**Tooltip on "Most you can add" (bulleted list), example RDNT:**
- Health Care: plan $63.0K, now $59.6K, left $3.3K
- Equities: left $18.1K
- Defensive style: left $9.7K
- A Hedgeye name, so it does not count in My stocks
- IRA cash you can spend: $3.0K
- Most that fits the plan: $3.3K. Most the money allows: $3.0K

**Order.** First come, first served. Picks and groups are checked in the order you made them. To give one priority, remove or lower another.

### 4. Groups ("buy any one of these")
**Create or edit (a small box opened by "+ New group" or "Edit"):**
```
+------------------------------ NEW GROUP IN IRA --------------------------------+
| Name        [Tech leaders                ]                                    |
| Amount      [$9,000]      IRA can spend $39.7K now                            |
| Good until  [2026-12-31]  (leave blank for no end date)                       |
| Members     [type a symbol...  ] [Add]                                        |
|   MSFT   My stocks     Info Technology   Call today: Hold     [remove]        |
|   NVDA   My stocks     Info Technology   Call today: Hold     [remove]        |
|   AAPL   Hedgeye name  Info Technology   Call today: Hold     [remove]        |
| WHILE IT WAITS, THE $9,000 IS COUNTED IN                                      |
| - IRA cash: $9.0K reserved. $30.7K left to spend                              |
| - Equities: $45.9K left after this                                            |
| - Info Technology: $15.0K left after this                                     |
| - My stocks: $3.6K left after this (MSFT and NVDA are My stocks)              |
| - High beta: $7.2K left after this (MSFT and NVDA)                            |
| [ Save group ]   [ Cancel ]                                                   |
+-------------------------------------------------------------------------------+
```
- A group belongs to one account. Members can be Hedgeye names or My stocks, mixed. At least one member.
- **The amount is reserved at once.** It counts against the account's cash and plan from the moment you save, shown in the tally under "Reserved" and in the bars as a dotted part.
- **While it waits, it is counted the cautious way:**
  - in the asset class and the sector with the **least room** among its members;
  - in **every** style, beta and Quad line that **any** member belongs to;
  - in My stocks if **any** member is a My stock.
- **When a member gets a Buy call**, the group line turns green: "MSFT has a Buy call today. [Buy MSFT]". If two members get a Buy the same day, both are named and each has its own button.
- **[Buy one now]** lets you buy a member without waiting for a call.
- **Buying a member** makes a pick for that stock with the group's amount, which you can change. From then on the group's dollars are counted in the lines of the stock you chose, not the cautious way.
- **One buy fills the group.** If you spend less than the reserve, the rest is free again (Open question 4). **[Reopen]** makes a filled group wait again with an amount you type. **[Edit]** changes the name, amount, date or members while it waits.
- **Good until.** After that date the group ends and its dollars are free. A note says so.
- **[Close]** ends the group and frees its dollars.
- **Group states and pills:** `Waiting` grey · `Buy call` green · `Buying MSFT` blue (`--accent`) · `Filled` grey · `Ended` grey · `Short of cash` red.

### 5. My stocks
```
+---------------------- MY STOCKS ----------------------+
| [type a symbol...] [Add]                              |
| MSFT   Info Technology    held in F-A      [remove]   |
| NVDA   Info Technology    not held         [remove]   |
| MOVED TO HEDGEYE NAMES                                |
| - AAPL joined a Hedgeye list on 11-10                 |
+-------------------------------------------------------+
```
- One list of names, used by every account. Each account's plan has its own My stocks %.
- **A stock is in one list only.** You cannot add a stock that is a Hedgeye name today; the box says "AAPL is already a Hedgeye name."
- **If Hedgeye adds one of your stocks,** it leaves My stocks by itself and counts as a Hedgeye name from that day. It is listed under "Moved to Hedgeye names". Its dollars stop counting in My stocks.
- **If Hedgeye later drops it,** it does not come back by itself (Open question 3). The note offers "Put back in My stocks".
- A name with no asset class must be given one before it can be added (the existing picker).

### 6. Actionable notes
```
 Symbol   ACTION
 BTI      [ BUY MORE ]
          [Over plan in IRA]

 MSFT     [ BUY->MIN ]
          [Group: Tech leaders]

 Today's actions panel, one short line per account that has an active plan:
 IRA: $31.8K left to spend   ·   F-M: $24.6K left to spend   ·   F-A: no active plan        [Open Builder]
```
- **Where.** Two new pills in the ACTION cell's existing pill line, after OVER MAX and the sizing pill.
- **Plan pill.** Buy calls only (Buy More, Buy Some, Buy To Min).
  - `Over plan in IRA` amber: the buy would take a percentage line over IRA's plan. Two accounts: `Over plan in IRA, F-M`. Three or more: `Over plan in 3 accounts`.
  - `Low cash in IRA` red: IRA cannot pay for it inside its money limits.
  - No pill for an account where the buy fits, and none for an account with no active plan.
- **Which accounts are checked.** Accounts with an active plan that hold the name. If no such account holds it, every account with an active plan.
- **How a row is checked.** Each row alone, in each account alone, as if it were that account's next buy, on top of what the account holds, its ticked sells, its picks and its group reserves.
- **Group pill** `Group: Tech leaders` blue (`--accent` on `#eef2ff`). Shown on a Buy row when the stock is a member of a waiting group. It does not show on Hold or Sell rows.
- **Small grey markers** after the pills: `Picked $6.0K in IRA`; `Will sell in IRA`.
- **Filter chips:** `Over plan (N)` and `Group ready (N)`.
- **Relation to existing badges.** OVER MAX is about one name's size. The plan pill is about the account's mix. "In headwind area" is about the market. All can show together.
- **They never change** the Final Call, AMT$, the confidence badge, the sort order or any other chip count.
- **Plan pill tooltip (bulleted list), example BTI:**
  - IRA: buy asked $4,000 (IRA's minimum size)
  - IRA: Consumer Staples plan $75.6K, now $72.2K, left $3.4K. This buy is $0.6K over
  - IRA: Equities left $54.9K. Fits
  - IRA: cash you can spend $31.8K. Fits
  - IRA: most that fits the plan is $3.4K (55 shares)
  - F-M: fits. Most that fits is $5.0K
  - Warning only. The Final Call does not change
- **Group pill tooltip (bulleted list), example MSFT:**
  - Group: Tech leaders, $9,000 reserved in IRA
  - Buy this or another member: MSFT (Buy today), NVDA (Hold), AAPL (Hold)
  - Buying one fills the group
  - Good until 12-31
  - $9,000 of MSFT fits IRA's plan
- **A group member's row is checked with the group's amount**, in place of the reserve, so the money is not counted twice.
- **Optional link.** The bulk bar gets "Add to Builder picks", which asks for the account first.

### 7. Hard and warn (the decision)
| Limit (always for one account) | Block or warn | What the screen does | Why |
|---|---|---|---|
| The account's own cash, plus expected cash from its ticked sells | **Block** | A pick's allowed amount, or a group's reserve, is cut to what the account can pay | A fact, not a preference |
| Cash to keep ($1,000) | **Block** | Buys and reserves stop at the floor | A buffer for price moves and orders the app cannot see |
| Cash below the plan's Cash % | **Block** | Buys and reserves stop when the account's cash would fall below it | Otherwise picks break the mix you set |
| Selling more shares than the account holds | **Block** | The box stops at the shares held | A fact |
| Old position file (more than 3 trading days) | **Block** | Red card; no buys or new groups in that account | Old cash numbers are how overspending happens |
| Asset class over its % | Warn | `OVER PLAN`, amount over, most that fits | Confirmed by you |
| Sector, style, high or low beta, Quad over its % | Warn | Same | Same. These lines overlap, and tags can be wrong |
| My stocks over its % | Warn | Same | Confirmed by you |
| A group over a % line when made | Warn | The box shows the line and the amount over; you can still save | Same rule as a pick |
| Cash above its % | Warn | A note on the cash row only | Leaving money in cash is allowed |
| Name with no class | Cannot be picked or grouped | Set the class first | It cannot be counted |

There is no "go ahead anyway" on a money limit. To go past one, change the number in the plan and activate. Cash never moves between accounts.

### Worth reconsidering
- **Keeping "Build new" as a third tab.** It would show almost the same tables as Plan and almost the same list as Pick. Recommend replacing it (Open question 2).
- **A "Placed" tick per pick.** Clearing picks when the next broker file lands gives the same safety with no clicks. A tick can be added later without rework.
- **Six separate plans is more upkeep than one.** "Copy from another account" keeps it light. HSA, A and Ra together hold $12.6K; leaving them with no plan is a reasonable choice.

## Rules & numbers

### Where the numbers come from
- **Holdings, cash, value of an account:** its newest position file (`builder_data.account_positions`). Cash is decided by the database function `is_cash()`.
- **Class, sector, style tags, beta, Quad view of a name:** `builder_data.name_info`, the same source today's Builder uses.
- **Prices:** the app's latest quote on the app's data date; if missing, the broker's price in the position file.
- **Buy and Sell calls:** `drv_actionable.final_code`.
- **Per-account buy size for the Actionable check:** `drv_account_size` (today it covers IRA, F-M and F-A).
- **Hedgeye names:** `builder_data.source_pool`, every name Hedgeye is bullish on today (181 names).
- **Today's date** is the app's data date, never the computer clock.

### Starting numbers (all can be changed in each plan)
| Number | Start | Source |
|---|---|---|
| Cash to keep | $1,000 | **GUESS**, carried from Spec 15 |
| My stocks | 3% of the account | **GUESS** (IRA: $12.6K) |
| Every other % | blank until you fill it, or "What the account holds now" | your choice |
| Old position file | more than 3 trading days | existing rule |
| High beta / low beta | above 1.2 / 0.8 or under | existing rule |
| "Good until" on a group | blank (no end) | your choice |

### One basis for every percentage
- Every % in a plan is a share of **that account's value** (cash included).
- Plan dollars for a line = its % x the account's value. Example: IRA Equities 52% x $419,745 = $218.3K.
- The account's value is not changed by picks or sells: a buy moves cash into a name, a sell moves it back.
- Style, beta and Quad lines count **stocks only**.
- Sector percentages must add up to no more than the Equities %.

### Which lines a name counts in
- Its asset class (one).
- Its sector, if it is a stock with a sector (one).
- Every style group whose tag it carries (can be several).
- High beta or low beta, from its measured beta. No beta means neither.
- Each Quad where its sector or class is favoured.
- My stocks, if it is on that list today.
- A line with a blank % is shown but never limits anything.

### Hedgeye names and My stocks
- A name is a **Hedgeye name** on a day when it is in Hedgeye's bullish pool that day.
- A name is a **My stock** when you added it and it is not a Hedgeye name that day.
- When a My stock becomes a Hedgeye name, the app stamps the date on its row and stops counting it in My stocks. It stays stamped even if Hedgeye drops it later.
- A stamped row comes back only when you press "Put back in My stocks".

### The sums for one account (same data in, same answer out)
1. **Now** per line = dollars the account holds in the names of that line.
2. **Sells.** For each ticked sell: expected cash = shares x price. It is added to the account's cash and taken off every line the name counts in.
3. **Cash you can spend** = the smaller of:
   - cash + expected sell cash - cash to keep;
   - cash + expected sell cash - (Cash % x account value).
   Never below 0. IRA today: the second is smaller, $82,157 - $50,369 = $31,788.
4. **Picks and waiting groups are walked in the order they were made.** For each:
   - money room = what is left of "cash you can spend";
   - allowed = the smaller of asked and money room; picks are in whole shares rounded down;
   - allowed below asked = `SHRUNK` (a group: `Short of cash`); allowed of 0 = `BLOCKED`;
   - the allowed dollars are taken off the cash and added to the lines below.
5. **Lines of a pick** = the lines of that stock.
6. **Lines of a waiting group** = the class and the sector with the least room among its members, every style, beta and Quad line any member is in, and My stocks if any member is a My stock.
7. **Lines of a group being bought** = the lines of the stock picked. The pick replaces the reserve.
8. **Left** per line = plan dollars - now (after sells) - picks - reserved. Below 0 = "over by" that amount.
9. **Over plan.** A pick or group is over plan when, after it is counted, any of its lines is over. The amount shown is the largest overage among them. A line that was already over also counts.
10. **Most that fits** = the smallest "left" among its lines before it is counted, never below 0. For a pick, in whole shares.
11. **Most you can add** to a name not yet picked = the smaller of "most that fits" and the money room.
12. **Actionable check** = steps 4 to 10 for that one row alone in one account, on top of that account's sells, picks and reserves. The amount asked is the account's minimum size minus what it holds when it holds less than the minimum, otherwise one unit.

**Checked on IRA's real data (2026-11-13, example plan):** cash you can spend $31,788, or $39,729 after ticking 100 shares of TLT. KDP 82 shares $2,984 and RCL 18 shares $5,756 fit. BTI 97 shares $5,970 puts Consumer Staples $5.6K over; $0.4K fits. The group reserves $9,000. AZO at $3,259.70 a share is cut from 5 shares to 4 ($13,039) by the Cash %. $2,980 is left to spend.

### When things go away
- **Picks and sell ticks** remember the date of the account's position file. When a newer file lands for that account, they are cleared. A note says so: "IRA's file for 11-14 arrived. 4 buys and 1 sell were cleared."
- Cleared lines stay for one day in a folded "Cleared" list with a **Pick again** button each.
- **Groups do not clear on a new file.** A waiting group keeps its reserve until it is filled, closed or past its date.
- **A group is filled** when a new file lands after you picked a member through the group.
- **A buy made at the broker without a pick:** when a new file shows the account holds more shares of a member than when the group was made, the group line asks: "IRA now holds 17 more MSFT. [Mark filled] [Keep waiting]". Until you answer, the reserve still counts.
- "Clear all picks" empties the account's picks at any time. It does not touch groups.

### Plan states (per account)
- **Draft:** any saved set for the account. Unlimited. Does nothing.
- **Active:** a copy taken when you press Activate. Later edits and saves of the draft do not touch it. Press Activate again to apply them.
- **Off:** the account has no active plan. It is not checked, and it gets no Actionable notes. Its groups stay but are not checked against percentages.
- One active plan per account. Activating a new one ends the old one and keeps it in history.

### Activate is refused when
- The asset classes add to more than 100.
- The sectors add to more than the Equities %.
- Any number is negative.
- The account has no position file.

### Wording (warn and block)
- "Consumer Staples is $5.6K over in IRA. $0.4K fits."
- "Fixed Income is already $12.3K over in IRA. Nothing more fits."
- "My stocks is $2.4K over IRA's 3%. $3.6K fits."
- "Shrunk: IRA can spend $3.0K."
- "Shrunk: more would take IRA's cash below your 12%."
- "Blocked: IRA has nothing left to spend. Lower a pick, close a group, or change the plan."
- "Fits. Uses $4.2K of cash from the sell you ticked. Sell first."
- "IRA's cash would be 12.7%, above your 12%. That is allowed."
- "Tech leaders: counted the cautious way while it waits. Offensive is $3.1K over if you buy NVDA."
- "Tech leaders ended on 12-31. $9,000 is free again."

### Edge cases
- **No active plan for the account:** Pick asks you to activate one or copy another account's. Actionable shows no notes for that account.
- **Old position file:** the account is red and takes no buys or new groups. Other accounts are not affected.
- **Prices older than 3 trading days, or a possible split (a move of 40% or more in a day):** the name cannot be picked; the row says why.
- **A sell is unticked after buys were picked:** everything is re-checked in order. Picks that no longer fit become `SHRUNK` or `BLOCKED`. Groups that no longer fit become `Short of cash`. Your asked amounts are kept.
- **The plan is changed and activated while picks or groups exist:** they are re-checked against the new plan at once.
- **Group amount above what the account can spend, when made:** the amount box stops at the most the account can spend and says so. At $0 the group cannot be saved.
- **Account cash falls after a group was made** (a new file shows less cash): the group shows `Short of cash: IRA can cover $4.0K of $9.0K`. Only the covered part is reserved. You lower the amount, close the group, or change the plan.
- **Group over a % line when made:** saved, with an amber note naming the line and the amount over.
- **A member is removed from the group:** the cautious count is worked out again from the members left. Removing the last member closes the group and frees its dollars.
- **A member is sold or has a Sell call:** it stays in the group, greyed, with "Sell call today". It never shows a group note on Actionable while it is not a Buy.
- **A member leaves both lists** (Hedgeye drops it and it is not a My stock): it stays in the group, greyed, with "on no list now". It cannot be bought through the group until it is on a list again.
- **A My stock in a group becomes a Hedgeye name:** it stays in the group. The group stops counting in My stocks if no other member is a My stock.
- **The same stock in two waiting groups in one account:** refused with "MSFT is already in Tech leaders".
- **The same stock in groups in two accounts:** allowed. Actionable shows one group pill per account.
- **Two members get a Buy call the same day:** both rows show the group pill. Picking one makes the other row read "Group: Tech leaders, being filled with MSFT".
- **A group member is also picked on its own:** allowed. The pick and the reserve both count.
- **Sell and buy of the same name in one account:** allowed. The lines show the net.
- **A name with no style tags or no beta:** counted in its class and sector only.
- **Sell Some with no amount from Actionable:** the box is blank and the line cannot be ticked until you type shares.
- **Data behind market close:** an amber note on the card; checks still run on the latest loaded data.
- **Orders placed at the broker without picking them here:** invisible until the next position file. The cash to keep is the buffer.

### Found while reviewing (not design changes)
- **Two cash numbers for the same account.** The Live advice night plan has F-A cash $125.8K and F-M $62.5K. The Builder's position read has $84.9K and $83.8K, same file date. The plan checks use the Builder's read. The developer must settle which is right before the Pick tab is built, because cash is the hard limit.
- **Style tags and measured beta disagree.** W is tagged "Low Beta" with a measured beta of 2.71. TRU is tagged "High Beta" with 0.08. One more reason percentages only warn.
- **8 of 11 Sell calls today have an amount of $0.** They are "Sell Some" on positions already under their target. The Sells block leaves these blank.
- **36 of the 181 Hedgeye names have no asset class.** They cannot be picked until a class is set.
- **VIX shows as a Buy call** and has no class. It is an index, not something you can buy.
- **LVHI ($13.3K in IRA) has no asset class**, so 3.2% of IRA sits in no plan line.
- **F-A is 47% Information Technology and 46% high beta.** Any plan for it will show large "over" lines from day one. That is information, not an error.
- **`drv_account_size` covers IRA, F-M and F-A only.** For HSA, A and Ra the Actionable check needs a fallback (one unit of the name's all-accounts size) or no check.
- **`ref_accounts` has two rows named HSA.** They are grouped by name today, so the sums are right.
- **No saved sets exist yet** (0 rows), so changing what a saved set holds breaks nothing.

## Files likely touched
- `etl/plan_check.py` (NEW, pure functions, no database) — `plan_lines`, `lines_of_name`, `lines_of_group`, `now_by_line`, `apply_sells`, `cash_to_spend`, `walk_items` (picks and groups in order), `most_that_fits`, `check_one`, `standing`, `validate_plan`, `plan_diff`.
- `etl/builder_data.py` — add `account_context(session, d, account)`: holdings, cash, file date and `name_info` for one account. Add `calls_for_account(session, d, account)` and `is_hedgeye_name`. Nothing existing changes.
- `etl/builder_store.py` — activate, turn off, read active plan per account; picks and sell ticks; clear on a newer position file; groups and members; My stocks and the "moved" stamp.
- `api/routers/builder.py` — new endpoints below. Existing set endpoints are reused for drafts.
- `api/routers/dash.py` — nothing baked into `drv_actionable`. The Actionable page calls the new plan-check endpoint itself, the same way Watch is joined live.
- `web/builder.html` — tabs Plan, Pick, Paper models; account strip; group box; My stocks box; `.pc-*` styles; bump `?v=`.
- `web/builder.js` — Plan tab from the existing compare tables; Pick tab from the existing names list; remove the per-pick "% of class" table and the "Whole book" entry on these tabs. Bump `?v=`.
- `web/actionable.js`, `web/actionable.html` — plan pill, group pill, grey markers, two chips, the per-account line, optional bulk button. Bump `?v=`.
- `db/baseline.sql` — five tables below.
- `docs/portfolio_builder_logic.md` — new section "Plans per account, picks, groups and plan checks"; `docs/actionable_logic.md` — short section on the two pills; one CLAUDE.md lookup row.
- `tests/test_plan_check.py` — pure-function tests.

### New tables
`user_plan_activation` (history; per account, the row with no end date is the active plan)

| column | type | note |
|---|---|---|
| activation_id | SERIAL PK | |
| account_short | TEXT | one row at most per account with `ended_at` NULL |
| set_id | INT | the draft it was copied from; may be gone later |
| name | TEXT | |
| state | JSONB | the full plan copy: class, sector, style, risk, Quad and My stocks %, cash to keep |
| activated_at, ended_at | TIMESTAMPTZ | |

`user_plan_pick` (buys and sell ticks)

| column | type | note |
|---|---|---|
| pick_id | SERIAL PK | |
| account_short, tos_symbol | TEXT | |
| side | TEXT | BUY or SELL |
| asked_usd, asked_shares, est_price | NUMERIC | |
| group_id | INT NULL | set when the pick fills a group |
| made_at | TIMESTAMPTZ | the order, shared with groups |
| file_date | DATE | the account's position-file date when picked |
| status | TEXT | OPEN or CLEARED |
| picked_on | DATE | the app's data date |
| cleared_at | TIMESTAMPTZ | |

`user_plan_group`

| column | type | note |
|---|---|---|
| group_id | SERIAL PK | |
| account_short, name | TEXT | name unique per account among waiting groups |
| amount_usd | NUMERIC | the reserve |
| good_until | DATE NULL | |
| status | TEXT | WAITING, FILLED, ENDED (date passed) or CLOSED |
| made_at | TIMESTAMPTZ | the order, shared with picks |
| filled_symbol | TEXT NULL | |
| filled_usd | NUMERIC NULL | |
| filled_on | DATE NULL | |

`user_plan_group_member`

| column | type | note |
|---|---|---|
| group_id | INT | |
| tos_symbol | TEXT | PK (group_id, tos_symbol) |
| shares_at_add | NUMERIC | shares the account held when added; used to spot a buy made without a pick |
| added_at | TIMESTAMPTZ | |

`user_my_stock`

| column | type | note |
|---|---|---|
| tos_symbol | TEXT PK | |
| note | TEXT | |
| added_at | TIMESTAMPTZ | |
| moved_on | DATE NULL | the day Hedgeye took it; NULL = it is a My stock |

Drafts stay in the existing `user_builder_set` (it already has an account column). No derived table: checks are worked out when asked.

### New endpoints
- `GET /api/builder/plan/now?account=&date=` — the account's value, cash, and "now" dollars for every line.
- `GET /api/builder/plan/active?account=` — the active plan, or none. Without `account`: the state of every account, for the account box.
- `POST /api/builder/plan/activate` — body: account and plan; returns the change list on `?dry_run=1`, activates otherwise; 400 with a plain reason when refused.
- `POST /api/builder/plan/off?account=`.
- `GET /api/builder/pick?account=&date=&list=&show=` — standing, sells block, groups, picks with allowed and result, names with "most you can add", the tally, room opened by sells, the card.
- `POST /api/builder/pick`, `PATCH /api/builder/pick/{id}`, `DELETE /api/builder/pick/{id}`, `DELETE /api/builder/pick?account=` (clear all).
- `POST /api/builder/group/check` — body: account, amount, members; returns the cautious count and any notes. Reads only.
- `POST /api/builder/group`, `PATCH /api/builder/group/{id}` (edit, reopen, close, mark filled), `DELETE /api/builder/group/{id}`.
- `GET /api/builder/my-stocks`, `PUT /api/builder/my-stocks/{symbol}` (add, or put back), `DELETE /api/builder/my-stocks/{symbol}`.
- `GET /api/builder/plan-check?date=` — for Actionable: per buy call, one entry per checked account (pill, lines, most that fits), the group notes, and the per-account lines. Reads only.

### Build plan (each task ships and is useful on its own)

| # | Task | You get | Checks (behaviour only) | DB |
|---|---|---|---|---|
| 1 | **Check engine** (pure): lines, now, sells, cash to spend, walking picks and groups in order, cautious group lines, most that fits, single-row check, standing, validate, change list | Nothing visible yet | On made-up accounts: allowed buys plus reserves never exceed cash plus ticked sell cash minus the floor; cash never falls below the Cash %; unticked sells change nothing; a percentage line never cuts an allowed amount; a waiting group counts in the sector with the least room and in My stocks if any member is one; a group being bought counts in the bought stock's lines only; two accounts never affect each other; same input gives the same answer | No |
| 2 | **Plan tab per account.** "Now", the five tables with "= $", My stocks %, limits card, Save draft, Activate, Turn off, Copy from, strip, account box states | A saved, active plan per account and a view of plan against now | Sectors above Equities are refused at Activate; saving a draft does not change the active plan; one active plan per account; activating IRA changes nothing for F-M | Yes |
| 3 | **Pick tab, buys.** Standing list, two name lists, My stocks box with the move-to-Hedgeye rule, picks, results, tally | Pick names and amounts in an account and see what is left | Right after Activate nothing is ticked and no amount is filled; a stock is never in both lists; a My stock that joins a Hedgeye list stops counting in My stocks; an over-plan pick keeps its amount and says the amount over; a pick above the cash is shrunk and names the limit | Yes |
| 4 | **Sells on the Pick tab.** Sells block, expected cash, room opened | Cash and room from the sells you plan | A ticked sell adds expected cash to its own account only; unticking re-checks the picks; shares cannot exceed shares held | Yes |
| 5 | **Groups.** Create and edit box, reserve in the tally, buy a member, fill, reopen, close, end date, "bought without a pick" question | Money set aside for "any one of these" | The reserve is counted from the moment it is saved; a reserve above the cash is refused or cut; one buy fills the group and frees the rest; a filled group reserves nothing; a group past its date reserves nothing | Yes |
| 6 | **Clear on new broker file** + "Pick again" + docs | Picks never double-count | A newer position file clears that account's picks and sell ticks, no other account's, and no waiting group | Yes |
| 7 | **Actionable plan pill.** Plan-check endpoint, pill naming the account, tooltip, markers, `Over plan` chip, per-account line | The warning where you read the calls | No pill for an account with no active plan; the Final Call, AMT$ and sort order are the same with and without plans; sell rows never get a plan pill | Reads only |
| 8 | **Actionable group pill** (needs Task 5) and `Group ready` chip | You learn a group member has a Buy call | The pill shows only on Buy rows of members of waiting groups; two members with a Buy both show it | Reads only |
| 9 | **"Add to Builder picks"** on Actionable's bulk bar (optional) | One click from a call to a pick | It asks for the account; buys land as picks with no amount; sells land ticked | Yes |

Tasks 1 to 4 are the core. Task 1 needs no database.

### Risks and how each is handled
| Risk | Handling |
|---|---|
| Old position files | That account takes no buys or new groups until a new file is loaded |
| Expected sell cash that never arrives | Marked "expected" everywhere; a buy that needs it says "Sell first"; cleared at the next file |
| Orders the app cannot see | Cash to keep; picks cleared and re-read at the next file; groups ask before they assume |
| Reserves forgotten for months | The "Good until" date; the tally always shows "Reserved" |
| A wrong class, sector or style tag | Percentages only warn; class can be set on the spot |
| The two cash numbers disagree | Settle before Task 3 (see "Found while reviewing") |
| The example plan read as advice | The mock-ups say it is an example; nothing is active until you press Activate |

## Status
READY_FOR_DEV — Tasks 1 to 9, after the user answers Open questions 1 to 5 (each has a recommendation that the tasks assume). Revised in place for per-account plans, My stocks and groups. Replaces Spec 15's build plan.
