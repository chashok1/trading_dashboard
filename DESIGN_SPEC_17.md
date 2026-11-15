# Design Spec — DESIGN_WORK_17

## Goal
Review the Builder screen against one simple wish (pick an account, set asset class limits, optionally set sector / style / beta limits, optionally pick stocks, get told when a limit is hit) and propose the simplest natural flow, removing more than adding. Used by the single user of the dashboard, one account at a time.

### In plain English (one page)

**What you asked for.** Pick an account. Set asset class % (must total 100). Optionally set sector, style or beta limits. Optionally pick stocks, or "buy any one of these". Be told whenever a buy would break any limit.

**What the screen does today.** All the parts exist, but they are spread over a screen that was first built for a different job (paper "model portfolios"). The plan was bolted on top. The result:

- **The flow is not natural.** There is no "limits" box. You set limits by typing into the Target column of five comparison grids on the right, after picking stocks in the middle. The order on screen is: account, lists, names, then limits. It should be: account, limits, then stocks.
- **Limits you never typed get saved.** The screen fills every Target box from what the account holds today. Leave them alone and they all become limits. On your real accounts this most likely makes Activate refuse with "Sectors add to 100%, more than Equities".
- **Sector, style and beta limits are measured two different ways.** The grid shows them as a share of the *invested* money. The checker reads the same number as a share of the *whole account*. In account F-A, Technology shows as 93% in the grid but is 47% of the account. A "10% IT" limit means two different things in two places.
- **Three ways to save, none clear.** "Save draft", "Activate", and "Save as…" (saved sets) overlap. Save draft says "the active plan has not changed" but it does change the buy list straight away.
- **A third of the screen is left over from the old job.** The "Portfolios" tab, the "Warnings" card, the "Running model" pill and the banner all belong to paper model portfolios. There is no button left to create one, and none exist in the database. They are dead ends.
- **You are only told about a limit if you go and look.** A buy is checked only if it is a saved pick with an amount, has a Buy call today, and you ticked it. Nothing says "you are close" and nothing flags a limit broken by a new positions file.

**What I recommend.**

1. One screen, three steps left to right: **1 Limits, 2 Pick stocks (optional), 3 Where I stand**.
2. One **Save plan** button. Saved means live. No draft, no saved sets.
3. Every limit is a **% of the whole account**. Blank means no limit. Nothing is pre-filled except asset classes.
4. A planned buy counts against the limits **as soon as you type its amount**. The Actionable call is shown next to it, not used as a gate.
5. Three plain states on every line: **OK, Near (90% used), Over**. Shown on the Builder and on the Actionable "My plan" chip.
6. Remove the left-overs: Portfolios tab, Warnings card, saved sets, Preset as a mode, the unused Plan/To do tab file.

Nothing is stored yet (no plans, no picks, no saved sets, no model portfolios in the database), so this clean-up loses nothing.

**Not checked in a browser.** The findings come from reading the code and running the limit maths on your real holdings (read-only). The developer should confirm the two bugs on screen before fixing.

## Design

### 1. Walk-through: your wish against today's screen

| # | Your step | Today | Verdict | Where |
|---|---|---|---|---|
| 1 | Pick an account; everything is by account | Account box top-left. Plan, picks and To do all follow it. | **Works**, with noise: a "Whole book (preview only)" choice that cannot have a plan, an "Amount" box that changes the grid's dollars but not the plan's, a "Running model" pill, a "Type" pill. | `web/builder.html` `.bld-acct`; `web/builder.js` `renderAcct` |
| 2 | Set asset class % totalling 100 | Type into the Target column of the "Asset class" grid in the right column. Cash has no box: it is "whatever is left". The box silently caps your number so the total cannot pass 100. No "Total 100%" line. | **Awkward.** It works, but it is hidden inside a comparison table, you cannot type Cash, and a capped number changes under you with no message. | `builder.js` `compareTable`, `setAssetTarget`, `planFromState` |
| 3 | Optional: sector, style, beta % | Type into the Target column of the Risk, Sectors and Style grids. | **Broken in two ways.** (a) All boxes are pre-filled from current holdings, so "optional" limits are set for you. (b) The grids say "% of the invested money"; the checker treats the number as % of the account. | `builder.js` `seedTargets`, `planFromState`; `etl/plan_check.py` `_line_rows` |
| 4 | Pick one stock | Tick it in the middle list. It appears in the symbol table with a "% of class" box and a "Buy $" box. | **Awkward.** Every holding is ticked for you on first load, so "my picks" is already full of things you did not pick. A pick only becomes a planned buy if it has a Buy $ **and** you press Save draft or Activate. | `builder.js` `loadSourceNames` (auto-pick), `symbolTable`; `etl/plan_store.py` `sync_buy_picks` |
| 5 | Pick a group (AAPL or MSFT) | Give both rows the same letter (A to F) in the "One of" drop-down. | **Awkward.** Works, but a letter is not a natural way to say "either of these". Limit of six groups. | `builder.js` `symbolTable` (`data-grp`) |
| 6 | Pick no stocks | Allowed. | **Works.** The To do block then shows only sells and room. | |
| 7 | Be told when a buy hits any limit | "To do" block, bottom-right, and pills in the Plan column on Actionable. | **Partly.** See section 4. A buy is only checked when it is a saved pick with an amount, has a Buy call today, and is ticked. No "near the limit" notice. | `plan_check.todo`; `plan_store.plan_check_page`; `web/actionable.js` `_planPillsHtml` |
| 8 | Natural order: account, limits, stocks | Screen order is account, lists, names, picks, then limits. | **Missing.** | `builder.html` three-column grid |

### 2. Redundancy audit

| # | Same thing, two ways | Decision | Why |
|---|---|---|---|
| R1 | **Save draft** vs **Activate** vs **Save as…** (saved sets) | **Merge into one "Save plan".** Remove saved sets. | Three saves for one plan per account. Draft adds a state nobody needs: you can already type without saving. Sets store the same things the plan stores. No sets exist. |
| R2 | `web/builder_plan.js` (Plan and To do tabs) vs the plan controls in `builder.js` | **Remove the file.** | It is not loaded by any page and its tabs are not in `builder.html`. It is a second, unused copy of the plan screen. |
| R3 | **To do block** amount box vs **Buy $** in the symbol table | **Merge: one amount, shown once.** | Two boxes for the same number. Editing one does not update the other; the next save puts the older one back. |
| R4 | **Preset** drop-down vs typed **Target** | **Keep as a one-time "Start from" fill.** | A preset is a starting point, not a mode. Today it flips to "Custom" the moment you type, which reads like something broke. |
| R5 | **Build new / Portfolios** (paper model portfolios) vs **the plan** | **Hide the Portfolios tab and its left-overs.** Keep the code and tables for now. | Both answer "what should this account look like". There is no button to create a model any more, and none exist. See Worth reconsidering. |
| R6 | **Warnings card** (4 tick-boxes) vs plan limit warnings | **Remove the card.** | It only applies to a frozen model portfolio. With no way to freeze one, the ticks do nothing. |
| R7 | "% of class" box per pick vs "Buy $" per pick | **Keep Buy $ only.** | Two ways to size a pick. The % box feeds the paper model, not the plan. |
| R8 | "Picks vs Portfolio" comparison grids vs To do "What is left" bars | **Merge into one "Where I stand" table.** | Both compare holdings with a target, in different units, in two cards. |
| R9 | "To plan" column (Sell all / Sell / Room) in the Asset class grid vs "Sell" section of To do | **Merge** into the Room column of "Where I stand". | Same sum shown twice. |
| R10 | "Match my holdings" and auto-ticking every holding | **Remove both.** | They exist to copy holdings into the paper model. Holdings are already counted by the plan without being picks. |
| R11 | "Show what's missing" vs clicking a row to filter the names list | **Keep the row click only.** | Same result. The row click is more direct. |
| R12 | Two account pickers on the page (build view, Portfolios list filter) | Goes away with R5. | |
| R13 | "Amount" box vs the account's own value | **Remove.** | The plan always uses the full account value. The box changes only the grid's dollars. |
| R14 | Quad rows and "Portfolio beta" as Targets | **Keep as information rows, no Target box.** | They take a Target today but are never saved in the plan or checked. |

Kept as is: lists to choose from, My stocks, the names list filters (list, class, sector, industry, factor, Quad, symbol), copy-symbols buttons.

### 3. Saving audit

**What is stored where**

| Store | Holds | Written by | Read by |
|---|---|---|---|
| `user_plan.draft` | Limits + every ticked name (JSON) | Save draft, Activate | Reopening the account |
| `user_plan.active` | Copy of the draft at Activate | Activate | To do, Actionable pills |
| `user_plan_pick` | Planned buys with an amount; ticked sells | Save draft, Activate, and directly from the To do block | To do, Actionable pills |
| `user_builder_set` | A named copy of the whole screen (account, picks, targets, mix, lists) | Save as… | Open |
| `user_my_stock` | Your own stock names | Add box | Names list |
| `user_model_portfolio` and related | Frozen paper portfolios | Nothing on the screen any more | Portfolios tab |
| Browser storage | Nothing | | |

All of these tables are **empty today**.

**Can you lose work, and is "saved" clear?**

| # | Problem | Effect |
|---|---|---|
| S1 | **Loaded limits get replaced.** When an account opens, the saved plan is applied and then the screen re-fills every Target from current holdings. | Your saved sector, style and beta limits are swapped for today's holdings. The pill does not say "unsaved". The next save stores the wrong numbers. Depends on which of two requests returns first, so it will look random. |
| S2 | **No warning on leaving.** Change account, change date, press Refresh or close the tab with unsaved changes. | Changes are dropped silently. |
| S3 | **"Save draft" is not only a draft.** It rewrites the planned buys, which the live To do list and Actionable use at once. | The message "the active plan has not changed" is not true for buys. |
| S4 | **Limits and buys are on different clocks.** Limits wait for Activate. Buys go live on Save draft. Amounts typed in To do go live at once and are not in the draft. | A later save can put an old amount back. |
| S5 | **Opening a saved set switches the account quietly** and does not reload that account's plan state. | The pill shows the previous account's state. Save draft then overwrites the other account's draft. |
| S6 | **"Save as…" with an existing name replaces it** with only a hint in the prompt. | Easy to overwrite a set. |
| S7 | **Things you can type that are never saved in the plan:** Quad targets, Portfolio beta target, the lists you ticked, the Amount box. | Gone on reload. |
| S8 | **Things that save but are never used:** the Warnings ticks, the picks' "% of class", picks with no amount (kept in the draft only), saved sets' `useDial`. | Clutter. |
| S9 | **Activate needs two clicks plus a hidden save.** Activate saves a draft first, then asks to confirm. | If you cancel, the draft (and the buys) were already changed. |
| S10 | **Stale buys.** A planned buy stays after you have bought the stock and the new positions file lands. | The stock is counted twice: once as held, once as planned. |

### 4. Limit validation audit

**What is checked today**

| Limit | Checked? | When over |
|---|---|---|
| Asset class % | Yes | Warns. Holdings in a class above its % are listed under Sell. |
| Sector % | Yes, but on the wrong basis (see G1) | Warns |
| Style % (Defensive, Offensive, Value, Growth, Mid) | Yes, same basis problem | Warns |
| Low beta (0.8 or less), High beta (over 1.2) | Yes, same basis problem | Warns |
| Cash: account cash, $1,000 floor, the plan's Cash % | Yes | Blocks or cuts the buy |

**Where you are told:** the To do block on the Builder, and the Plan column plus the "My plan (N)" chip on Actionable.

**Gaps against "notify me when I hit 10% high beta / 50% equities / 10% IT"**

| # | Gap | Example on your data |
|---|---|---|
| G1 | **Two bases.** The grid shows sector / style / beta as % of invested money. The checker reads the number as % of the account. | F-A: Technology is 93% of invested money, 47% of the account. High beta 92% vs 46%. |
| G2 | **Pre-filled limits.** Every sector, style and beta box is filled from holdings, including hidden "sectors" for non-equity classes (Fixed Income, Gold…) that the grid does not show but the plan saves. | IRA: the saved sector lines would add to about 100% against Equities of 39%, so Activate is refused. |
| G3 | **A buy is checked only after three conditions:** saved pick with an amount, a Buy call today, and ticked. | Type "$10,000 of NVDA" on a day with no Buy call and nothing is checked. |
| G4 | **Actionable warns only when a line is already full.** It does not know the amount, and there is no "close to the limit" state. | High beta limit 10%, held 9.5%: no pill until it passes 10%. |
| G5 | **No notice when holdings alone break a sector, style or beta limit.** Only classes get a Sell list. The others appear as one line of small text at the bottom of To do. | A price rise takes IT from 9% to 11%: nothing on Actionable, no badge. |
| G6 | **Nothing outside the Builder says a limit is broken** unless the stock also has a Buy call that day. | |
| G7 | **Names with no beta or no sector are skipped silently.** | Small today: every equity holding has a beta; F-M has 3.1% of the account with no sector; IRA has 3.2% with no asset class. |
| G8 | **Low / high beta count equities only in the checker, all classes in the grid.** | A bond fund with beta 0.2 is "low beta" in the grid, not in the check. |
| G9 | **Bought stocks stay as planned buys** (S10), so the after-buy numbers overstate. | |

### 5. Proposed flow

One view. No tabs. Full page width. Three columns, read left to right. Reuses today's classes (`bld-card`, `bld-step`, `bld-t`, `bld-exp`, `td-p`, `td-bar`, `bld-ftag`) and colours.

```
+--------------------------------------------------------------------------------------------------------------------------+
| Account [ IRA            v]   Value $419.7K · Cash $82.3K · Positions Nov 13      Plan saved Nov 14 · checks on          |
|                                                              [Start from v]  [Save plan]  [Pause checks]  (unsaved dot)  |
+---------------------------+----------------------------------------------+-----------------------------------------------+
| (1) LIMITS                | (2) PICK STOCKS  (optional)                  | (3) WHERE I STAND                             |
|                           |                                              |                                               |
| Asset class  (required)   | Lists: [x] Held [x] PS [ ] ETF ... My stocks | 1 over · 1 near · 5 OK                        |
|              Limit   Now  | [class v][sector v][factor v][Quad][symbol ] |                                               |
| Equities     [50]%   39%  |                                              | Line          Limit  Now  After buys  Room    |
| Fixed Income [20]%   22%  | [ ] AAPL  PS,ETF  Equities  Info Tech  1.18  | ASSET CLASS                                   |
| Gold         [ 5]%    6%  | [ ] MSFT  PS      Equities  Info Tech  0.97  | Equities       50%   39%   43%   $31.2K   OK  |
| Commodities  [10]%    4%  | [ ] XLU   ETF     Equities  Utilities  0.55  | Fixed Income   20%   22%   22%   -$8.4K  OVER |
| Crypto       [ 0]%    0%  | ...                                          | Gold            5%    6%    6%   -$4.2K  OVER |
| Currency     [ 0]%    0%  |                                              | Cash           15%   20%   16%   $6.0K to spend  |
| Cash         [15]%   20%  | 2 ticked:  [Plan to buy]  [Buy one of these] | OPTIONAL LIMITS                               |
| Total        100%  ✓      |                                              | High beta      10%    7%    9%    $4.2K  NEAR |
|                           |                                              | Info Tech      10%    9%   11%   -$5.8K  OVER |
| ▸ More limits (optional)  |                                              |                                               |
|   blank = no limit        |                                              | PLANNED BUYS                        Amount    |
|   High beta  [10]%    7%  |                                              | AAPL or MSFT   Buy call: MSFT       [$10,000] |
|   Low beta   [  ]%   36%  |                                              |   ⚠ Info Tech goes $5.8K over. $4,200 fits.   |
|   SECTOR                  |                                              | XLU            No Buy call yet      [ $5,000] |
|   Info Tech  [10]%    9%  |                                              |                                               |
|   Health Care[  ]%   14%  |                                              | SELL TO GET BACK ON PLAN                      |
|   ...                     |                                              | Fixed Income over by $8.4K                    |
|   STYLE                   |                                              |   [ ] TLT  $31.0K  Hold                       |
|   Defensive  [  ]%   31%  |                                              |   [ ] IEF  $12.4K  Sell Some                  |
+---------------------------+----------------------------------------------+-----------------------------------------------+
| The Builder never trades and never changes the Actionable Final Call.                                                    |
+--------------------------------------------------------------------------------------------------------------------------+
```

**Top bar**
- Account list holds real accounts only. "Whole book" is removed.
- One line of facts: Value, Cash, Positions file date. An old file shows the date in amber with the words "old file".
- Plan pill, one of: `No plan yet` · `Plan saved Nov 14 · checks on` · `Plan saved Nov 14 · checks paused`.
- **Start from** (fills the boxes once, saves nothing): `What this account holds` · each mix preset · `Copy <other account>'s plan`.
- **Save plan** is the only save. Disabled until something changed. A small amber dot and "unsaved changes" sit beside it while there are any.
- **Pause checks / Resume checks** replaces "Turn off". It keeps the plan and stops the warnings.

**Column 1, Limits** (about 300px wide)
- Asset class rows, each with a box and "Now". Cash has its own box. A Total line under them: green "100% ✓" or red "92%, must be 100".
- "More limits (optional)" opens to Beta, Sector, Style. Every box starts blank. Placeholder text in the box: "no limit". "Now" is always shown so you know where you stand before typing.
- Sector rows: every sector the account holds plus any with a limit, plus an "Add sector" pick list for the rest.
- A filled optional box shows a small × to clear it back to "no limit".
- All numbers are **% of the whole account**. The card title says so once: "Limits · % of the account".

**Column 2, Pick stocks** (unchanged list and filters)
- Nothing is ticked for you.
- Two buttons under the list replace the letter drop-down:
  - **Plan to buy** (one or more ticked): each ticked name becomes its own planned buy.
  - **Buy one of these** (two or more ticked): the ticked names become one planned buy.
- A name already in a planned buy shows a small "planned" tag instead of a tick-box.

**Column 3, Where I stand** (replaces the five comparison grids, the symbol table and the To do block)
- Headline count: "1 over · 1 near · 5 OK".
- One table. Columns: Line, Limit, Now, After buys, Room, status pill. A thin bar under each row (existing `td-bar`: grey = now, blue = after buys, amber when over).
- Rows with no limit are not listed. A "Show lines with no limit" link lists them, greyed, for information.
- Clicking a row filters the names list to it (existing click-to-filter).
- **Planned buys**: one row each. Names (joined by "or" for a group), today's Actionable call as a pill, one Amount box, a × to remove. Under the row, in amber or red, the plain sentence when it breaks something.
- **Sell to get back on plan**: classes over their limit with their holdings and a tick-box, as today.
- It updates as you type, before you save. Before the first save it carries a note: "Not saved yet. Actionable still uses the last saved plan."

**Status pills** (existing `td-p` colours)

| State | Pill | Colours |
|---|---|---|
| OK | `OK` | green `#e4efe7` / `#2f6b45` |
| Near | `Near` | amber `#fdf3e3` / `#b45309` |
| Over | `Over` | amber, bold, with the amount |
| Cash block | `No cash` | red `#f4e6e6` / `#9e3636` |

Over a limit is a warning, so it is amber. Red is kept for the one thing that blocks: cash.

**Tooltips** (bulleted, never one flat line). Example on the High beta row:
- Limit: 10% of the account = $42.0K
- Held now: $29.4K (7%)
- Planned buys: $8.4K
- Room left: $4.2K
- Counts: stocks with beta over 1.2
- Left out: names with no beta

**Wording**
- Over: "Info Tech goes $5,800 over its 10% limit. $4,200 fits."
- Near: "High beta is at 9% of a 10% limit. $4,200 left."
- Cash: "This account can spend $6,000. Cut from $10,000 to $6,000."
- Save refused: "Asset classes add to 92%. They must add to 100."
- Leaving with changes: "You have unsaved changes to IRA's plan. Save them?" [Save] [Discard] [Stay]

**On Actionable** (small additions to what is there)
- "My plan (N)" chip turns amber when any account has a line over its limit. Its tooltip lists them as bullets, e.g. "IRA: Info Tech $5.8K over".
- Plan column gains one pill: `Near limit in IRA` for a Buy call on a stock in a line that is Near.
- Existing pills stay: planned pick, buy-one-of, plan sell, over plan, low cash.

### Worth reconsidering

**Paper model portfolios (the Portfolios tab).** The engine behind it is large (freeze, daily marks, vs SPY, promise check, end-of-period review, back-test, compare). On the screen today there is no way to start one, and none exist. Keeping the tab makes the Builder look like two products. Better option: hide the tab and its left-overs now (one small task), live with the plan for a month, then decide whether to delete the engine or bring it back as its own screen. Hiding costs nothing and can be undone in a minute.

## Rules & numbers

**One basis.** Every limit is a percentage of the account's total value (holdings plus cash) from the latest positions file. Dollars for a limit = limit % × account value.

**Asset class limits (required)**
- Seven lines: Equities, Fixed Income, Gold, Commodities, Crypto, Currency, Cash.
- They must add to 100, within 0.1 (existing number). Save is refused otherwise.
- A class is a target: under it there is room to buy, over it there is something to sell.
- A class is "on plan" when it is within $500 of its limit (existing number).

**Optional limits (sector, style, low beta, high beta)**
- Blank = no limit. 0 = none allowed. These are different and the box shows which.
- Each is a ceiling: only "over" matters. Being under is never flagged.
- Sectors apply to equities only. Sector limits together cannot exceed the Equities limit; Save is refused otherwise (existing rule).
- Low beta = beta 0.8 or less. High beta = beta over 1.2 (existing numbers). Counted for equities only, in both the "Now" figure and the check.
- Style groups as today: Defensive, Offensive, Value, Growth, Mid. A stock can sit in more than one, so style lines do not add to 100.
- Low and high beta together cannot exceed 100 (existing rule).
- Nothing is ever pre-filled in an optional box.

**Line states**

| State | Rule |
|---|---|
| OK | After planned buys, the line uses less than 90% of its limit |
| Near | Uses 90% or more, and is not over. **GUESS: 90%** |
| Over | After planned buys, the line is more than $500 above its limit (same $500 as "on plan") |

"After planned buys" = held now, minus ticked sells, plus every planned buy that has an amount.

**Planned buys**
- A planned buy counts as soon as it has an amount. It does not wait for a Buy call. (Change from Spec 16; see Open questions.)
- The Actionable call is shown as information: "Buy call: MSFT", "No Buy call yet", "Sell call" (in red, as a caution).
- Buys are counted in the order they were made (existing rule).
- A "buy one of" group has one amount. It is counted against the member with the least room in its class (existing rule). If one member has a Buy call today, that member is used instead.
- A name can be in only one planned buy per account (existing rule).

**Cash (the only thing that blocks)**
- Cash you can spend = cash + ticked sells − the larger of: the cash floor ($1,000, existing) and the plan's Cash % of the account.
- A buy larger than that is cut to what fits, rounded down to $100. Nothing fits = blocked (existing rules).
- Cash from ticked sells is "expected": it is not in the broker file yet, and the screen says so.

**Saving**
- One saved plan per account. Save plan writes the limits and the planned buys together, in one step. Saved = the plan Actionable and the checks use.
- Save is refused only when classes do not add to 100, a number is negative, sectors exceed Equities, or low + high beta exceed 100.
- No draft. Typing changes nothing until Save plan.
- Pause checks keeps the plan and switches the warnings off. Resume switches them on.
- Leaving with unsaved changes (other account, other date, Refresh, closing the tab) asks first.
- Amounts and sell ticks typed in "Where I stand" are part of the plan and follow the same Save.

**Notices away from the Builder**
- Actionable "My plan" chip turns amber when any account with checks on has a line Over from holdings alone.
- Worked out when Actionable loads (existing 2-minute cache). No new table, no email.

**Edge cases**

| Case | What happens |
|---|---|
| No plan saved | "Where I stand" still works from what is typed. Actionable shows nothing for this account. |
| Account all cash (A, HSA today) | "Now" is 0% on every line but Cash. Start from "What this account holds" gives Cash 100. |
| Holding with no asset class | Counted in the account value, in no line. Note under the table: "$13.4K of holdings have no asset class. No limit covers them." |
| Equity with no sector | Counts in Equities, in no sector line. Note: "$14.0K of equities have no sector." |
| Equity with no beta | Counts in neither beta line. Note with the count and dollars. |
| Old positions file (over 3 trading days, existing number) | Checks still run. Date shown in amber with "old file". |
| Positions file newer than a planned buy, and the account now holds that stock | The buy row shows "You now hold $X. Done?" with a [Done] button that removes it. Nothing is removed automatically. |
| Two buys compete for the last room | First made wins; the second shows the Over sentence. |
| Group with no member having a Buy call | Counted against the member with the least room. |
| Limit typed at exactly what is held | Shows Near (fully used, not over). |
| Planned buy for a stock whose class limit is 0% | Shows Over for the full amount. |
| Date picker set to a past day | Shows that day's holdings against today's saved plan. A note says so. Save is disabled. |
| Sector limit on a sector the account no longer holds | Row stays, "Now 0%". |

**Where the numbers come from**
- 100 ± 0.1, $500, $1,000 cash floor: `etl/plan_check.py` (`TOL`, `MIN_NEED`, `DEFAULT_CASH_KEEP`). Unchanged.
- Beta 0.8 / 1.2 and style groups: `etl/plan_check.py`, `etl/derive_model_portfolio.py` (`FLAVOURS`). Unchanged.
- 3 stale days: `PB_PARAMS`. Unchanged.
- **90% Near: GUESS.** New. Should sit beside the others in `plan_check.py` so it can be changed in one place.
- Example figures in the mock-up are made up, apart from the account facts quoted in the audits (read from the database for 2026-11-13).

## Files likely touched

### Task list (ordered by value; each is useful on its own)

| # | Task | What you get | Size |
|---|---|---|---|
| T1 | **Fix the limit maths.** One basis (% of account) everywhere. Stop pre-filling optional limits. Drop the hidden non-equity "sector" lines. Stop the reload from replacing saved limits. Count beta for equities only in both places. | Limits mean what you typed. Activate stops being refused for limits you never set. | Small |
| T2 | **Remove the left-overs.** Portfolios tab, Warnings card, Running-model pill and banner, Amount box, "Whole book", saved sets row, `builder_plan.js`, Match my holdings, auto-ticking holdings, the "% of class" box. Hide, do not delete the back end. | A third less on the screen. Nothing lost: no data exists. | Small |
| T3 | **One Save plan.** Replace Save draft / Activate / Turn off with Save plan / Pause checks. Limits and buys saved together. Unsaved-changes dot and the leave prompt. | "Saved" means one thing. No silent loss. | Medium |
| T4 | **Limits card in column 1.** Asset classes with a Cash box and a Total line; optional limits collapsed; "Start from" menu replaces Preset. | The natural order: account, limits, stocks. | Medium |
| T5 | **"Where I stand" panel.** One table (Limit, Now, After buys, Room, state) plus Planned buys and Sells. Replaces the comparison grids, the symbol table and the To do block. Buys count once they have an amount. | Live "what is left" and warnings in one place. | Medium |
| T6 | **Near / Over notices on Actionable.** Amber chip with a bulleted list; "Near limit" pill. | You are told without opening the Builder. | Small |
| T7 | **Natural picking.** "Plan to buy" and "Buy one of these" buttons replace the letter drop-down; "planned" tag in the list; "Done?" on bought picks. | Groups read as plain English. No double counting. | Small |

T1 and T2 can ship first and in either order. T3 to T5 are best done in that order. T6 needs T1. T7 needs T5.

### Files

- `web/builder.html` — remove the tabs, Portfolios and detail views, Warnings card, saved-sets row, banner; add the Limits card and the "Where I stand" card; new top bar buttons; bump the script version.
- `web/builder.js` — remove `seedTargets`, saved-set functions, list / detail / review code paths from the page, auto-pick and match-holdings; replace `compareTable` / `symbolTable` / `todoRender` with the Limits card and the standing table; one save path; leave prompt.
- `web/builder_plan.js` — delete (unused).
- `etl/plan_check.py` — Near threshold constant; line state (OK / Near / Over); planned buys counted without a Buy call; beta on equities only stays as is.
- `etl/plan_store.py` — one save that writes limits and buys together; "checks on / paused" flag in place of draft / active; over-limit lines per account for the Actionable chip; a what-if call that takes the typed plan.
- `api/routers/builder.py` — save / pause endpoints replace draft / activate / off; a what-if endpoint; stop serving sets, compare, back-test and keep endpoints from the page (leave them until the model-portfolio decision).
- `db/baseline.sql` — `user_plan`: a "checks on" flag (the `draft` column can stay unused); no other change.
- `web/actionable.js`, `web/actionable.html` — amber state and bulleted tooltip on the "My plan" chip; "Near limit" pill.
- `tests/test_plan_check.py` — line states, counting without a Buy call, one basis.
- `docs/portfolio_builder_logic.md` — rewrite the "Plans per account" section (it still describes Plan and To do tabs that are not on the page, and lists the Actionable Plan column as not built).
- `CLAUDE.md` — one Lookup row to update (Builder Plan + To do tabs).

## Open questions

Decisions for you (each with my recommendation):

- **One "Save plan" instead of Save draft + Activate?** Recommended: yes. Saved means live. You can still try numbers freely before saving.
- **Hide the paper model portfolios (Portfolios tab)?** Recommended: hide now, decide on deleting the engine in a month. None exist and there is no button to make one.
- **Should a planned buy count against limits as soon as it has an amount, even with no Buy call that day?** Recommended: yes. Spec 16 counted it only on a Buy call, which is why limits looked unchecked.
- **Sector, style and beta as ceilings only (warn when over, never "short")?** Recommended: yes. Asset classes stay two-sided (room to buy, or sell).

Bugs found while reviewing (read from the code, not run in a browser; for the developer to confirm):

- `web/builder.js` `seedTargets` runs after `planApply` on account load and replaces `S.targets`, so saved optional limits are swapped for current holdings. `planApply` does not set `S.seeded`; `openSet` does, which is why saved sets do not show it.
- `seedTargets` also stores `sector:<asset class>` keys for non-equity classes (from `bd.exposure`, where a non-equity name's sector is its class). `compareTable` hides those rows but `planFromState` sends them, so `validate_plan` sees sectors adding to about 100% against Equities.
- Sector / style / beta targets on the page are % of invested money (`bd.exposure`); `plan_check._line_rows` reads them as % of account value.
- `save_draft` calls `sync_buy_picks`, so a "draft" save changes the live To do buys and the Actionable pills while the message says the active plan has not changed.
- Amounts edited in the To do block (`PATCH /api/builder/pick/{id}`) are not written back to the draft's picks; the next Save draft restores the grid's older amount.
- `openSet` changes `S.acct` without calling `planLoad`, so the plan pill and the next Save draft can target the wrong account's state.
- `web/builder_plan.js` is not referenced by any page; `GET /api/builder/plan` and `/api/builder/plan/states` have no other caller.
- `POST /api/builder/portfolios` (accept and freeze), `/api/builder/compare`, `/api/builder/backtest` and the keep endpoints have no caller in `web/builder.js`; the Warnings ticks and `S.horizon` / `S.useDial` have no control and no effect.
- `docs/portfolio_builder_logic.md` says Plan and To do are tabs and that the Actionable Plan column is not built; both are out of date.

## Status
READY_FOR_DEV
