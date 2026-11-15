# Design Spec — DESIGN_WORK_18

## Goal
Redesign the Builder screen into one easy flow (account, limits, optional stocks, see what is left, be told near / over) for the single user of the dashboard, one account at a time.

### In plain English (one page)

**The screen becomes two columns and one button.**

1. **Pick an account** in the bar at the top.
2. **Left: "My limits".** One table. You type a % for each asset class. They must add to 100. Cash is one of them. That is the only required part.
3. **Still left: "More limits".** Open it if you want. Beta, sector and style. Every box starts blank. Blank means no limit.
4. **Right: "Stocks to buy".** Optional. Tick names, press **Plan to buy** (each one) or **Buy one of these** (a group). Type a dollar amount.
5. **Save plan.** One button. Saved means live.

**What you see while you work.**

- The limits table is also the "where I stand" table. Next to each box you see **Now**, **After buys**, **Room** and a state.
- It updates as you type. No save needed to see it.
- Asset classes say **Room / On plan / Over**. Optional limits say **OK / Near / Over**.
- The names list shows how many dollars of each stock still fit.
- A planned buy that breaks a limit gets a plain sentence under it: which limit, how much over, how much fits.

**What changes from today.**

- A planned buy counts as soon as it has an amount. It does not wait for a Buy call.
- Planned buys also use up cash. If they need more cash than the account can spend, the Cash row says how much it is short.
- Every % is a share of the whole account. One meaning everywhere.
- Nothing is filled in for you except a first suggestion for the asset classes. No stock is ticked for you. No amount is typed for you.
- Unsaved work is always marked. Leaving with unsaved work always asks first.

**How you are told, away from the Builder.**

- The **warning badge** in the top bar of every screen lists each account that is over or near a limit.
- On **Actionable**, the "My plan" chip turns amber and each row carries a pill: Over limit, Near limit, Cash short.

**What goes.** Paper model portfolios (tab, list, detail, warnings card, banner), saved sets, Save draft / Activate, the five comparison grids, the picks grid with "% of class" and group letters, the separate To do block, Match my holdings, Show what's missing. About half the controls.

**Checked against your real accounts** (read-only, positions of Nov 13). The mock-ups use IRA's real value, cash and holdings mix. Stock names and amounts in them are made up.

## Design

### 1. Layout

Full page width, no max width. One top bar, then two columns. No tabs. Reuses today's classes (`bld-acct`, `bld-card`, `bld-step`, `bld-t`, `bld-pill`, `bld-btn`, `td-p`, `td-bar`, `bld-ftag`) and colours. No new colours.

| Part | Width | Holds |
|---|---|---|
| Top bar | 100% | Account, facts, plan state, Start from, Save plan |
| Left column | `minmax(540px, .9fr)` | Step 1 My limits. Sells, when a class is over. |
| Right column | `minmax(520px, 1.1fr)` | Step 2 Stocks to buy: planned buys on top, the names list under it. |

The left column stays in view while the long names list scrolls (it sticks to the top of the window). That keeps "what is left" visible while picking. Below 1000px wide the two columns stack.

### 2. Mock-ups

Figures are IRA on Nov 13: value $419.7K, cash $82.2K. Stock names and amounts are made up.

**(a) New account. Only asset class % set.**

```
+------------------------------------------------------------------------------------------------------------------------------+
| Account [ IRA        v]   Value $419.7K · Cash $82.2K · Positions Nov 13      ( No plan yet )    [Start from v]  [ Save plan ] |
+----------------------------------------------------------------+-------------------------------------------------------------+
| (1) MY LIMITS · % of the whole account                         | (2) STOCKS TO BUY (optional)                                |
|                                                                |                                                             |
| 1 over · the rest are fine                                     | PLANNED BUYS                                                |
|                                                                | None. Tick names below, then press Plan to buy.             |
| ASSET CLASS (required)  Limit     Now   After buys      Room   | ----------------------------------------------------------- |
| Equities                [ 48]%   38.9%    38.9%      $38.2K  Room    | Lists [x]Held [x]PS [x]ETF [x]II [x]CALL [x]SSS [x]RR [x]My stocks |
| Fixed Income            [ 30]%   36.9%    36.9%     -$29.0K  OVER    | [+ my stock    ][Add]                                 |
| Gold                    [  5]%    0.0%     0.0%      $21.0K  Room    | [class v][sector v][style v] Quad favored [Q1][Q2][Q3][Q4]   |
| Commodities             [  0]%    0.0%     0.0%          -   On plan | [symbol   ]  [Clear filters]   212 names                    |
| Crypto                  [  0]%    0.0%     0.0%          -   On plan |                                                       |
| Currency                [  2]%    1.4%     1.4%       $2.5K  Room    |     Symbol Lists  Class     Sector      Beta  Fits     |
| Cash                    [ 15]%   19.6%    19.6%      $19.2K  To spend| [ ] AAPL   PS,ETF Equities  Info Tech   1.18  $19.2K   |
| Total                    100%  OK                              | [ ] MSFT   PS     Equities  Info Tech   0.97  $19.2K          |
| No class                    -     3.2%   $13.4K, no limit covers it  | [ ] XLU    ETF    Equities  Utilities   0.55  $19.2K   |
|                                                                | [ ] GLD    RR     Gold      -           0.10  $19.2K          |
| > More limits (optional): beta, sector, style. None set.       | [ ] TLT    Held   Fixed Inc -           0.20  Over            |
|                                                                | ...                                                         |
| SELL TO GET BACK ON PLAN                                       |                                                             |
| Fixed Income is $29.0K over its 30%.  Ticked $0 of $29.0K      | 0 ticked   [Plan to buy]  [Buy one of these]  [Clear ticks] |
|   [ ] TLT   $61.2K   Hold                                      |                                                             |
|   [ ] IEF   $40.1K   Sell Some                                 |                                                             |
+----------------------------------------------------------------+-------------------------------------------------------------+
| The Builder never trades and never changes the Actionable Final Call.                                                        |
+------------------------------------------------------------------------------------------------------------------------------+
```

- The asset class boxes arrive filled with a suggestion: what the account holds now, rounded, Cash as the rest. The pill says "No plan yet". Save plan is ready to press.
- "Fits" for AAPL is $19.2K: Equities has $38.2K of room, but the account can only spend $19.2K of cash. The smaller number wins.
- TLT says "Over" because Fixed Income is already over.

**(b) Limits plus picks, one group. Not saved yet.**

```
+------------------------------------------------------------------------------------------------------------------------------+
| Account [ IRA        v]   Value $419.7K · Cash $82.2K · Positions Nov 13                                                     |
|   ( Unsaved changes )  [Undo changes]                                           [Start from v]  [ Save plan ]   Delete plan  |
+----------------------------------------------------------------+-------------------------------------------------------------+
| (1) MY LIMITS · % of the whole account                         | (2) STOCKS TO BUY (optional)                                |
|                                                                |                                                             |
| 1 over · 1 near · the rest are fine                            | PLANNED BUYS  2 · $15,000                                   |
| Not saved yet. Actionable and the warning badge still use      | AAPL or MSFT   Buy call today: MSFT     [$10,000]  x        |
| the plan saved Nov 14.                                         |   ! Info Tech is near its limit. $1.3K more fits.           |
|                                                                | XLU            No Buy call yet          [ $5,000]  x        |
| ASSET CLASS (required)  Limit     Now   After buys      Room   | ----------------------------------------------------------- |
| Equities                [ 48]%   38.9%    42.5%      $23.2K  Room    | Lists [x]Held [x]PS [x]ETF ...            [+ my stock][Add] |
| Fixed Income            [ 30]%   36.9%    36.9%     -$29.0K  OVER    | [class v][sector v][style v] Quad favored ...  [symbol ]    |
| Gold                    [  5]%    0.0%     0.0%      $21.0K  Room    |                                                       |
| Commodities             [  0]%    0.0%     0.0%          -   On plan |     Symbol Lists  Class     Sector      Beta  Fits     |
| Crypto                  [  0]%    0.0%     0.0%          -   On plan | pl. AAPL   PS,ETF Equities  Info Tech   1.18  planned  |
| Currency                [  2]%    1.4%     1.4%       $2.5K  Room    | pl. MSFT   PS     Equities  Info Tech   0.97  planned  |
| Cash                    [ 15]%   19.6%    16.0%       $4.2K  To spend| pl. XLU    ETF    Equities  Utilities   0.55  planned  |
| Total                    100%  OK                              | [ ] NVDA   CALL   Equities  Info Tech   1.71  $1.3K           |
| No class                    -     3.2%   $13.4K, no limit covers it  | [ ] KO     Held   Equities  Cons Staples 0.58 $4.2K    |
|                                                                | [ ] GLD    RR     Gold      -           0.10  $4.2K           |
| v MORE LIMITS (optional) · blank = no limit                    | ...                                                         |
| High beta (beta over 1.2) [ 10]%  1.2%     1.2%      $36.9K  OK      |                                                       |
| Low beta (0.8 or less)    [   ]%  36.1%   37.3%          -   no limit| 0 ticked   [Plan to buy]  [Buy one of these]  [Clear ticks] |
| SECTOR                                                         |                                                             |
| Consumer Staples          [ 20]%  17.2%   17.2%      $11.8K  OK      |                                                       |
| Info Tech                 [  4]%   1.3%    3.7%       $1.3K  NEAR    |                                                       |
| Health Care               [   ]%  14.2%   14.2%          -   no limit|                                                       |
| ... 4 more sectors with no limit                               |                                                             |
| STYLE   Defensive [  ]%  Offensive [  ]%  Value [  ]%  Growth [  ]%  Mid [  ]%                                               |
|                                                                |                                                             |
| SELL TO GET BACK ON PLAN                                       |                                                             |
| Fixed Income is $29.0K over its 30%.  Ticked $0 of $29.0K      |                                                             |
|   [ ] TLT   $61.2K   Hold                                      |                                                             |
+----------------------------------------------------------------+-------------------------------------------------------------+
```

- The group "AAPL or MSFT" is one planned buy with one amount.
- "After buys" moved: Equities 38.9% to 42.5%, Info Tech 1.3% to 3.7%, Cash 19.6% to 16.0%.
- Info Tech uses 92% of its limit, so it says NEAR.
- NVDA "Fits $1.3K": Info Tech is the tightest line for it.

**(c) Over a limit.** The group amount is raised to $14,000.

```
| 2 over · the rest are fine                                     | PLANNED BUYS  2 · $19,000                                   |
|                                                                | AAPL or MSFT   Buy call today: MSFT     [$14,000]  x        |
| ASSET CLASS (required)  Limit     Now   After buys      Room   |   ! Info Tech goes $2.7K over its 4% limit. $11.3K fits.    |
| Equities                [ 48]%   38.9%    43.4%      $19.2K  Room    | XLU            No Buy call yet          [ $5,000]  x  |
| Fixed Income            [ 30]%   36.9%    36.9%     -$29.0K  OVER    |                                                       |
| ...                                                            |     Symbol Lists  Class     Sector      Beta  Fits          |
| Cash                    [ 15]%   19.6%    15.0%          $0  On plan | [ ] NVDA   CALL   Equities  Info Tech   1.71  Over     |
| ...                                                            | [ ] KO     Held   Equities  Cons Staples 0.58 No cash       |
| Info Tech                 [  4]%   1.3%    4.6%      -$2.7K  OVER    |                                                       |
```

- The Info Tech row turns amber with OVER and the amount.
- The same fact is under the planned buy that caused it, with what would fit.
- The headline counts it.
- If XLU were raised to $9,000, cash would run out. The Cash row would read `-$3.8K  SHORT` in red and XLU would get: "Not enough cash for this one. $5,100 fits."

### 3. What the user clicks, in order

| # | Click | What happens |
|---|---|---|
| 1 | Account list | Page loads that account. Saved plan if there is one, else the suggestion. |
| 2 | Asset class boxes | Total line updates on each keystroke. Green "100% OK" or red "92%, must be 100". |
| 3 | "More limits" (optional) | Opens beta, sector, style. All blank. Type only the ones wanted. |
| 4 | Tick names (optional) | Counter under the list: "2 ticked". |
| 5 | **Plan to buy** or **Buy one of these** | The names move to Planned buys. Cursor lands in the amount box. |
| 6 | Amount box | After buys, Room, states and Fits all update. |
| 7 | **Save plan** | Limits, planned buys and sell ticks save together. Pill becomes "Saved Nov 14". |

"Start from" is a one-time fill, used at step 2 if wanted: `What this account holds` · each mix preset · `Copy <account>'s plan`. It fills boxes and saves nothing.

### 4. Unsaved changes

The page holds two copies of the plan: the **saved** one and the **working** one. Everything on screen shows the working one.

| Situation | What shows |
|---|---|
| No plan, nothing typed | Grey pill "No plan yet". Save plan enabled. No prompt on leaving. |
| Working = saved | Grey pill "Saved Nov 14". Save plan disabled. |
| Working differs from saved | Amber pill "Unsaved changes" (`bld-pill warn`). Save plan enabled. "Undo changes" link. Note above the table: "Not saved yet. Actionable and the warning badge still use the plan saved Nov 14." |
| Save refused | Red line under the bar with the reason. Nothing is saved. Working copy is kept. |
| Leave with unsaved changes (other account, closing the tab, another screen) | "You have unsaved changes to IRA's plan." [Save] [Discard] [Stay] |
| Past date picked in "As of" | Blue-grey note: "Showing Nov 6 holdings against today's plan. Go back to the latest date to change the plan." Boxes and Save plan disabled. |

If you type a number and then type the old number back, the pill returns to "Saved". The state comes from comparing the two copies, not from a "something was touched" flag.

**Built so the old save bugs cannot come back**

| Old bug | Rule in this design |
|---|---|
| Reload replaced saved limits | Only two things may write the working copy: the user, and a load of the saved plan on account change. Holdings never write limits. |
| Picks leaked between accounts | The working copy carries its account name. Changing account throws the whole copy away (after the prompt) and builds a new one. Save sends the copy's own account name and is refused if it differs from the account list. |
| Date / Refresh clobbered edits | Date and Refresh reload holdings and prices only (Now, After buys, Fits). They never reload the plan. |
| Amounts filled in for you | An amount is only ever typed by the user. A new planned buy has an empty amount. Cash limits never change a typed amount; they only say what fits. |
| Buys and limits saved at different times | One save, one request, one database step. Nothing else writes the plan. Amount boxes and sell ticks do not save by themselves. |

### 5. Where near / over warnings appear

| Place | What it shows | Uses |
|---|---|---|
| State pill on the limit row | Room / On plan / Over, or OK / Near / Over | Working copy |
| Headline above the table | "2 over · 1 near · the rest are fine" | Working copy |
| Sentence under a planned buy | Which limit, how much over, what fits | Working copy |
| "Fits" column in the names list | Dollars that still fit, or Over / No cash | Working copy |
| Warning badge, every screen | One entry per account that is over or near | Saved plan, holdings only |
| Actionable "My plan" chip and row pills | Over limit, Near limit, Cash short, planned buy, sell | Saved plan, holdings plus planned buys |

State pills (existing `td-p` colours): green `ok` for OK / Room / To spend, grey for On plan and "no limit", amber `warn` for Near and Over (Over is bold with the amount), red `bad` only for Cash short. A limit is a warning, so amber. Cash is the one thing that really stops a buy, so red.

Under each limit row a thin bar (existing `td-bar`): grey = now, blue = after buys, amber when over. Build the table first; the bar can follow.

### 6. KEEP / MOVE / REMOVE

| Control or section today | Decision | Note |
|---|---|---|
| "Build new / Portfolios" tabs | REMOVE | One view. |
| Portfolios list, portfolio detail, review window, chart | REMOVE | Paper models. Also drop the Chart.js script tag from this page. |
| "Running model" banner and pill, account Type pill | REMOVE | Paper models. |
| Warnings card (4 tick-boxes) | REMOVE | Paper models. |
| Compare, back-test | REMOVE | Already no button. Nothing on the page may call them. |
| Account list | MOVE | From the left card to the top bar. Real accounts only. |
| "Whole book (preview only)" choice | REMOVE | A plan belongs to one account. |
| Amount box | REMOVE | The plan always uses the full account value. |
| Value / Cash / Positions date | KEEP | In the top bar. Old file: date in amber plus "old file". |
| Plan pill | KEEP | New words: No plan yet / Saved Nov 14 / Unsaved changes. |
| Save draft, Activate | REMOVE | Replaced by one Save plan. |
| Turn off | MOVE | Small "Delete plan" link at the right of the bar, with a confirm. Shown only when a plan is saved. |
| Preset | MOVE | Entries in "Start from". No "Custom" mode. |
| Saved sets (list, Open, Save as, Delete) | REMOVE | One plan per account is the saved thing. |
| Lists to choose from | MOVE | One row of tick-boxes above the names list. |
| My stocks add box | MOVE | Same row. |
| Names filters: asset class, sector, style (was Factor), Quad favored, symbol | KEEP | |
| Names filter: List | REMOVE | The list tick-boxes do this. |
| Names filter: Industry | REMOVE | No limit uses it. See Open questions. |
| Select all shown | REMOVE | Would create dozens of planned buys. |
| Clear picks | MOVE | Becomes "Clear ticks". Planned buys are removed one by one with x. |
| Match my holdings | REMOVE | Copied holdings into the paper model. Holdings already count. |
| Show what's missing | REMOVE | Click a limit row to filter the names to it; the Fits column shows room. |
| Clear filters, name count, copy-symbols button | KEEP | |
| Names table | KEEP | Drop the Quad and Style columns, add **Fits**. A planned name shows "pl." in place of its tick-box. |
| Picks count and copy-picks button | REMOVE | |
| Five comparison grids (asset class, risk, Quad, sectors, style) | REMOVE | Replaced by the My limits table. |
| Quad rows, Portfolio beta row | REMOVE | Never saved, never checked. See Open questions. |
| "To plan" column | REMOVE | Now the Room column. |
| Live bars strip above the grids | REMOVE | The thin bar under each limit row does it. |
| Picks grid ("% of class", "Buy $", "One of" letter) | REMOVE | Replaced by Planned buys. |
| To do block: Sell | MOVE | Under the limits table as "Sell to get back on plan". Shown only when a class is over. |
| To do block: Buy table | MOVE | Becomes Planned buys. No "count this" tick-box, no "Allowed" column. |
| To do block: What is left | REMOVE | Now the Room column. |
| To do block: summary line and notes | MOVE | Headline above the table; notes under it. |
| To do block: Refresh button | REMOVE | The top Refresh does it. |
| Problems note at the top | KEEP | |
| Footer line | KEEP | Shortened to "The Builder never trades and never changes the Actionable Final Call." |
| "As of" date and Refresh in the app bar | KEEP | They reload holdings only. |
| `web/builder_plan.js` | KEEP, becomes the page's script | See section 8. |

### 7. Wording

All tooltips are bulleted lists, one fact per bullet.

**On the Builder**

| Where | Text |
|---|---|
| Card title | My limits · % of the whole account |
| Optional section | More limits (optional) · blank = no limit |
| Empty optional box | placeholder `no limit` |
| Total fine / wrong | `100% OK` / `92%, must be 100` |
| Blank asset class box | Red box. "Type a number. 0 is fine." |
| Over, under a planned buy | "Info Tech goes $2.7K over its 4% limit. $11.3K fits." |
| Near, under a planned buy | "Info Tech is near its limit. $1.3K more fits." |
| Cash, under a planned buy | "Not enough cash for this one. $5,100 fits." |
| Cash row when short | `-$3.8K  SHORT` and "Planned buys need $3.8K more cash than this account can spend. Tick a sell or lower an amount." |
| Planned buy with no amount | "Type an amount to count it." |
| Call beside a planned buy | `Buy call today: MSFT` (green) · `No Buy call yet` (grey) · `Sell call today` (red) |
| Bought since it was planned | "You now hold $9,800 of MSFT. Done?" [Done] |
| Save refused | "Asset classes add to 92%. They must add to 100." / "Sector limits add to 55%, more than Equities (48%)." |
| After save | "Plan saved for IRA. Actionable and the warning badge use it now." |
| Delete plan | "Delete IRA's plan? Its limits and planned buys are removed and IRA is no longer checked." [Delete] [Keep] |

Tooltip on a limit row (High beta shown):
- Limit: 10% of the account = $42.0K
- Held now: $5.0K (1.2%)
- Planned buys: $0
- Room left: $36.9K
- Counts: stocks whose measured beta is over 1.2
- Not the "High Beta" style tag
- Left out: stocks with no beta, and anything that is not a stock

Tooltip on a "Fits" cell (NVDA shown):
- $1.3K of NVDA fits
- Tightest: Info Tech, $1.3K left of its 4% limit
- Equities: $23.2K left
- High beta: $36.9K left
- Cash to spend: $4.2K

Tooltip on Save plan:
- Saves the limits, planned buys and sell ticks for IRA
- Saved means live: Actionable and the warning badge use it at once
- Nothing is traded

**Warning badge (every screen).** One entry per account with something over or near. Amber, never red. Holdings only: planned buys are not counted here.

Title: `IRA plan: 1 over, 1 near its limit`

Bullets under it, over first, at most four, then a last line:
- Fixed Income: $29.0K over its 30% limit
- Consumer Staples: 17.2% of a 19% limit, $7.6K left
- Open the Builder to fix or change the plan

If more than four lines are in trouble the fourth reads "and 3 more".

**Actionable, "My plan (N)" chip.** Grey when every plan is fine. Amber when any account is over. Tooltip:
- IRA: Fixed Income $29.0K over its 30% limit
- IRA: Consumer Staples near its 19% limit, $7.6K left
- F-M: all limits fine
- Click to show only the stocks in your plans
- Information only. The Final Call does not change.

**Actionable, row pills** (existing pill style and colours)

| Pill | Colour | When | Tooltip bullets |
|---|---|---|---|
| `Plan: IRA buy $10K` | blue | The stock is a planned buy | IRA plan: planned buy · Amount: $10,000 · Fits inside every limit · Information only. The Final Call does not change. |
| `Plan: IRA one of AAPL or MSFT` | blue | The stock is in a group | IRA plan: buy any one of AAPL, MSFT · Amount: $10,000 · Buy call today: MSFT · Information only. The Final Call does not change. |
| `Over limit in IRA` | amber, bold | A planned buy, or a Buy call, on a stock whose limit is over or would go over | IRA: Info Tech limit is 4% = $16.8K · Held now: $5.5K · Planned buy: $14,000 · Goes $2.7K over · $11.3K fits · Information only. The Final Call does not change. |
| `Near limit in IRA` | amber | Same, and the limit is 90% used but not over | IRA: Info Tech limit is 4% = $16.8K · Held plus planned: $15.5K (92%) · $1.3K left · Information only. The Final Call does not change. |
| `Cash short in IRA` | red | A planned buy, or a Buy call, and the account has no cash left to spend | IRA can spend $0 · It keeps its Cash % (15%) and $1,000 · Tick a sell on the Builder or lower a planned buy · Information only. The Final Call does not change. |
| `Plan: sell in IRA` | red | Existing. The stock's class is over its limit | IRA: Fixed Income is $29.0K over its 30% limit · You hold $61.2K of TLT · Information only. The Final Call does not change. |

Each "·" above is a separate bullet on its own line in the tooltip. Sort order of the Plan column, worst first: Over limit, Cash short, Near limit, Sell, Buy one of, Planned buy.

### 8. Reuse of `web/builder_plan.js`

It is not loaded by any page today, yet it already holds most of this design on the right basis (% of the account). Make it the page's script and stop loading `web/builder.js` on this page. That also keeps every old bug out, because the code that caused them is no longer loaded.

| Piece in `builder_plan.js` | Use |
|---|---|
| `renderCls` (class boxes, Cash box, total line, Room / Sell pills) | The asset class half of My limits. Add After buys and the state pill. |
| `renderOpt` (beta, sector, style boxes, blank = Open, "Held" as % of account) | The More limits half. Change "Open" to "no limit". |
| `fromHeld`, `renderStart`, `onStart` | The first suggestion and "Start from". Add the presets. |
| `renderLists`, `renderMine`, `refreshMine` | The lists row and My stocks. |
| `renderNames`, `syncMake`, `onMake` | The names list and the two buttons. `onMake` must add to the working copy, not post to the server. |
| `renderPicks` | Planned buys. Amount edits go to the working copy, not the server. |
| `renderTodo` sells part | "Sell to get back on plan". |
| `dirty`, `savePlan` | Replace with the saved-versus-working comparison and one save. |
| Plan / To do tab wiring, `onActivate`, the two account lists | Drop. |

From `web/builder.js` only the names filters are carried over (class, sector, style, Quad favored, symbol, click-to-filter, copy symbols).

## Rules & numbers

**One basis.** Every limit is a % of the account's total value (holdings plus cash) in the latest positions file. Limit in dollars = limit % x account value.

**Asset classes (required)**
- Seven: Equities, Fixed Income, Gold, Commodities, Crypto, Currency, Cash.
- They must add to 100, within 0.1. A blank box is an error, not a zero.
- States: **Room** (more than the tolerance under), **On plan** (within the tolerance), **Over** (more than the tolerance above).
- Cash is the mirror: **To spend** when above its %, **On plan**, **Short** when planned buys take it below.

**Optional limits (low beta, high beta, sector, style)**
- Blank = no limit. 0 = none allowed.
- Ceilings only. Being under is never flagged.
- States: **OK**, **Near** (90% or more of the limit is used and it is not over), **Over** (above the limit by more than the tolerance).
- Sector, style and beta count stocks (Equities) only, in Now and in the check.
- Low beta = measured beta 0.8 or less. High beta = measured beta over 1.2. Not the style tag.
- Styles: Defensive, Offensive, Value, Growth, Mid. A stock can be in several, so they do not add to 100.
- Sector rows shown: sectors the account holds, sectors of planned buys, sectors that have a limit.
- Save is refused when sector limits add to more than the Equities limit, or low + high beta add to more than 100.

**"After buys"** = held now, minus ticked sells, plus every planned buy that has an amount. States, the headline and the sentences all use After buys.

**Planned buys**
- Count as soon as they have an amount. No Buy call needed. No tick-box.
- The full typed amount counts against the % limits, even when cash is short.
- Counted in the order they were made.
- A group has one amount. It counts against the member with a Buy call today. If none or several have one, it counts against the member with the least room.
- A name can be in one planned buy per account.
- The Actionable call is shown beside the buy as information only.

**What happens to cash**
- Cash to spend = cash + ticked sells, minus the larger of $1,000 and the plan's Cash % of the account.
- Every planned buy with an amount takes from it, in order.
- When buys need more than there is: the Cash row turns red (Short, with the amount) and each buy that does not fully fit says what fits, rounded down to $100. The typed amount is never changed.
- Cash from ticked sells is expected, not real yet. The Cash row says so: "includes $61.2K expected from sells".

**"Fits" in the names list** = the smallest of: room in the stock's class, room in each optional limit it counts in, and cash to spend. Zero or less on a limit shows "Over". Zero cash shows "No cash". A name with no asset class shows "-".

**Sell ticks**
- Listed only for classes that are Over. A tick adds that holding's value to expected cash.
- A tick is ignored, and dropped at the next save, when the holding is gone or its class is no longer over. This is not an unsaved change.

**Saving**
- One plan per account. One save writes limits, planned buys and sell ticks together.
- Saved = live. No draft on screen. (Storage can keep writing both of today's copies so nothing else has to change.)
- The live numbers on screen come from a check that reads the typed plan and writes nothing.

**Warning badge**
- Built when the badge asks, from saved plans and the latest holdings. Nothing new is stored. No email.
- An account appears when any line is Over or Near from holdings alone, or Cash is below its plan %.
- Refreshes right after Save plan, otherwise on its normal 5 minutes.

**Numbers and where they come from**

| Number | Value | Source |
|---|---|---|
| Classes add to 100 within | 0.1 | `etl/plan_check.py` `TOL`. Unchanged. |
| Tolerance for On plan / Over | $500 | `plan_check.py` `MIN_NEED`. Today optional lines use $1; this makes them the same. |
| Tolerance on small accounts | the smaller of $500 and 0.5% of the account | **GUESS.** $500 is a third of account Ra ($1.4K). |
| Cash floor | $1,000 | `plan_check.py` `DEFAULT_CASH_KEEP`. Unchanged. |
| Near | 90% of the limit used | **GUESS.** New. Keep it beside the others in `plan_check.py`. |
| Beta cut-offs | 0.8 and 1.2 | `plan_check.py`. Unchanged. |
| "Fits" rounding | down to $100 | `plan_check.py`. Unchanged. |
| Old positions file | over 3 trading days | `PB_PARAMS`. Unchanged. |
| Badge bullets per account | 4 plus one closing line | The badge shows at most 5 lines per entry today. |

**Edge cases**

| Case | What happens |
|---|---|
| Account is all cash (A, HSA today) | Suggestion is Cash 100. Every other row shows 0% and Room once a % is typed. |
| Account with no value (401K today) | Listed. Page says "No positions file for this account yet." Boxes disabled. |
| Holding with no asset class (IRA: 3.2%, $13.4K) | Counts in the account value, in no line. Shown as the "No class" row. The suggestion puts that share in Cash, so the total is still 100. |
| Stock with no sector or no beta | Counts in Equities only. Note under the table with the dollars. |
| Limit typed exactly at what is held | Near (fully used, not over). |
| Limit of 0% on something held | Over by all of it. For a class, the sell list says "sell all". |
| Two planned buys compete for the last room | First made keeps it. The second gets the Over sentence. |
| Planned buy in a class with a 0% limit | Over for the full amount. |
| Old positions file | Checks still run. Date in amber with "old file". Badge bullets end "(positions from Nov 6)". |
| Positions file now holds a planned stock | Row says "You now hold $X. Done?" [Done]. Nothing is removed by itself, so it counts twice until Done is pressed. The sentence says so. |
| Save pressed twice, or the server is slow | Button disabled while saving. On failure the working copy stays and the pill stays "Unsaved changes". |
| Two browser tabs on the same account | Last save wins. On save, if the saved plan changed since this tab loaded it, ask: "This plan was changed elsewhere. Save over it?" |
| No plan saved for any account | Badge shows nothing. Actionable chip reads "My plan (0)". |

## Files likely touched

### Task list (build order; each is useful alone and fits one session)

| # | Task | What the user gets | Size | Reuses `builder_plan.js` |
|---|---|---|---|---|
| T1 | **States and the read-only check.** In `plan_check`: Room / On plan / Over for classes, OK / Near / Over for ceilings, buys counted without a Buy call, the cash rule, the Near number. A check endpoint that takes a typed plan and writes nothing. | The right answer for "near / over" exists in one place. Today's To do block shows it at once. | Small | No |
| T2 | **Warning badge.** Add the per-account entry to the warnings feed. | Told on every screen when holdings break or approach a limit. | Small | No |
| T3 | **Actionable wording.** Amber chip with bulleted tooltip; Over limit / Near limit / Cash short pills that use planned amounts. | Told on the row where the buy decision is made. | Small | No |
| T4 | **Strip the page.** Remove tabs, Portfolios views, Warnings card, banner, saved sets, Match my holdings, Show what's missing, Select all shown, picks count, Amount, Whole book. Move the account to a top bar. | About half the controls gone. Nothing lost: no data exists. | Small | No |
| T5 | **My limits table plus one Save plan.** Left column: class boxes, Total, More limits, with Now / After buys / Room / state from the T1 check. Saved-versus-working state, Undo changes, leave prompt, Delete plan, Start from. Replaces the five grids and "What is left". | The natural order and one honest save. | Medium | **Yes**: `renderCls`, `renderOpt`, `fromHeld`, `renderStart`, `onStart` |
| T6 | **Planned buys.** Plan to buy / Buy one of these, amount boxes in the working copy, the sentences, Done?. Replaces the picks grid and the To do buy table. | Groups in plain words. Live "what is left" while picking. | Medium | **Yes**: `onMake`, `syncMake`, `renderPicks`, `renderNames` |
| T7 | **Sells under the limits.** The sell list for over classes, ticks in the working copy, stale ticks dropped. Removes the To do block. | Sells sit next to the limit that asks for them. | Small | **Yes**: sells part of `renderTodo` |
| T8 | **Names list tidy.** Lists row, fewer filters, Fits column with tooltip, "pl." tag, click a limit row to filter. | See what fits before ticking. | Small | **Yes**: `renderLists`, `renderMine`, `renderNames` |
| T9 | **Docs.** Rewrite the "Plans per account" section; update the one Lookup row. | Docs match the screen. | Small | No |

T1 to T3 do not touch the Builder page and can ship first. Between T5 and T7 the old picks grid and To do block stay on the page under the new table, so nothing is missing in between. Deleting the paper-model engine code is a later step and is not in this list.

### Files

- `web/builder.html` — top bar, two columns, the two cards; remove tabs, list and detail views, Warnings card, saved-sets row, banner, To do card, Chart.js tag; load `builder_plan.js`; bump script versions.
- `web/builder_plan.js` — becomes the page script: working and saved copies, one save, My limits table, planned buys, sells, names list with Fits.
- `web/builder.js` — no longer loaded by the page; names-filter code is carried into `builder_plan.js`. File stays until the engine clean-up.
- `etl/plan_check.py` — line states, Near number, small-account tolerance, buys counted on amount, cash-short result, "fits" per name.
- `etl/plan_store.py` — one save for limits + buys + sell ticks; read-only check on a typed plan; per-account standing for the badge and the chip; Actionable rows using planned amounts.
- `api/routers/builder.py` — check endpoint; save endpoint takes the whole plan; delete plan.
- `api/routers/health.py` — one block in the warnings feed for plan limits.
- `web/warning_badge.js` — a way to refresh at once after a save.
- `web/actionable.js`, `web/actionable.html` — chip state and tooltip; new and reworded pills; sort order.
- `tests/test_plan_check.py` — states, counting without a Buy call, cash short, fits.
- `docs/portfolio_builder_logic.md`, `CLAUDE.md` — section rewrite; one Lookup row.
- `db/baseline.sql` — no change expected.

## Open questions

- **Is "Near" at 90% of a limit right?** Recommended: yes, start at 90%. It is one number in one place and easy to change after a few weeks of use.
- **OK to drop the Industry filter, the Quad rows and the Portfolio beta row from this screen?** Recommended: yes. None of them is a limit, and none is saved or checked. The "Quad favored" filter stays for choosing names.

Noticed while reading the code (for the developer, not decisions):

- `plan_store.plan_page` returns style names in lower case (`defensive`, `growth`). The screen should show them capitalised.
- `web/warning_badge.js` silently cuts an entry to its first 5 lines. The badge wording above is sized for that.
- `web/builder.html` loads `warning_badge.js` with no version tag, so a changed badge script can be served stale.
- `plan_check.todo` counts the cash-cut amount, not the typed amount, against the % limits. This design counts the typed amount.
- `plan_store.plan_check_page` ignores planned amounts and only flags a line when no room is left at all. T3 replaces that.

## Status
READY_FOR_DEV
