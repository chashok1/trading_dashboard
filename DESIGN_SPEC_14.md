# Design Spec — DESIGN_WORK_14

## Goal
Set the build once: a target mix for all accounts and a target list of names. Then the Builder hands over a ready-made buy list on trade day, so there is little to think about then. Limits warn but never block.

This document stands alone. It covers the Portfolio Builder screen of a local, single-user trading dashboard: a Python/FastAPI app with a PostgreSQL database and a plain-JavaScript web page. A reviewer does not need the code to follow it.

### In plain English (one page)
- **Today the Builder is a tool for picking names, not a guide.** You tick lists, filter hundreds of names, type a % per name and compare "Picks" with "Portfolio". Every visit starts from scratch, so it eats time every day.
- **New idea: set two things once, then use one ready list on trade day.**
  1. **The build**: a target mix for all accounts together, for example Equities 60, Fixed Income 25, Gold 5, Commodities 3, Crypto 2, Cash 5. Each class has a safe range around its target.
  2. **The target list**: inside each class, the segments you want and their share. Segments are sectors or areas, such as Technology 20% of Equities or TIPS 30% of Fixed Income. Inside each segment you list **any stocks or funds you like**, each with a share. There is no fixed menu of names.
- **"This week" card** is the first thing on the page. Green means nothing to do. Amber reads like "5 buys, about $14K, in 2 accounts". Red means something needs a look, such as old position files.
- **The buy list** under the card: "Buy 40 sh AGG in IRA, about $3.9K. TIPS is 6 points under target." The top block fits inside each account's cash and this week's budget. Lines that go beyond those are still listed below, with a clear warning.
- **Limits warn, they never block.** Going over a name cap, a sector cap, a class range, the weekly or daily spend, the cash floor, or the account's cash shows a warning. The warning names the limit and the amount over. Going over the account's cash is a loud, red warning. You can still go ahead.
- **Nothing trades by itself.** You place the orders. A "Done" tick records what you placed, so the next list does not count the same cash twice.
- **When to buy is a later phase.** The target list says *what* to own. Later, the Actionable screen's signals will decide *when* to buy toward it. For now, the Final Call is shown as information only.
- **A weekly email** sends the same card and list. On a green week it is one line.
- **Do first:** four fixes to the current screen. The Accept button is missing, the Horizon and Risk Dial controls are gone, the Warnings tick-boxes do nothing, and there is no keep-list screen.

### Your six decisions (detail and my recommendation in Open questions)
1. Phase 2: when a name you want is under target but its signal says Sell, should it show greyed under "Waiting" (A) or be hidden (B)? (Recommend A.)
2. Should the account type (Taxable / IRA / Roth / HSA / 401k) choose where each class is bought? (Recommend: not at first.)
3. Suggest trims only when a class is above its range? (Recommend yes.)
4. Send the weekly email every week, even when green? (Recommend yes, one line.)
5. Keep the frozen "model portfolio" tracking, fixed, or retire it? (Recommend keep.)
6. Confirm the starting numbers: ranges, caps, weekly spend, cash floor, smallest trade. (Recommend the defaults below.)

## Design

### 1. Current design (as built today)
**Purpose.** Build a "model portfolio" for one brokerage account, compare it with what the account holds, and optionally freeze it as a paper portfolio. The frozen portfolio is then marked to market each night against SPY and against the account. The Builder never trades and never changes the Actionable screen's "Final Call", which is the per-symbol buy/sell recommendation.

**Asset classes ("buckets").** Equities, Fixed Income, Gold, Commodities, Crypto, Currency, Cash. These are the same as the Portfolio screen's pie. Holdings with no class show as "Unmapped" and can never be a target.

**Screen `/builder`** (`web/builder.html`, `web/builder.js`). It has two tabs plus a detail view.
- **Build new tab**, three columns:
  - Left: account picker (each account shows its type), editable Amount, "Lists to choose from" tick-boxes, and the Warnings tick-boxes. The lists are HELD (your holdings), FUND (a fixed fund list), and the Hedgeye lists PS, GOANY, II, CALL, ETF, SSS and RR.
  - Middle, "Names": every name on the ticked lists. Filters cover list, class, sector, industry, factor, the Quads a name is favoured in (Q1-Q4), and symbol text. A tick adds a name to "picks". Buttons: Select all shown, Clear picks, Match my holdings, Show what's missing, Clear filters, and copy symbols.
  - Right, "Picks vs portfolio": a Preset picker, saved sets (Open / Save as / Delete), then five small grids: Asset class, Risk (beta), Quad favoured, Sectors, Style. Each grid has Target / Picks / Portfolio / Gap columns and a bar strip. Under the grids, a symbol table shows Picks % box, Portfolio $, Gap $ and "To match", grouped by class.
  - The preview re-runs on every change.
- **Portfolios tab**: the frozen models per account (return, vs SPY, vs account, status) and a household total. A row opens the **detail view**, which shows KPIs, alerts with opt-in warnings, a chart, the class drift table, holdings, a "vs your account" trade-to-match table with a taxable gain estimate, a promise check, and an end-of-period review (roll over / change recipe / close).

**How a preview is built** (`etl/builder_engine.py::build_positions`):
- It starts from the account's whole value as if it were cash.
- Class mix comes from a preset (`ref_pb_mix_preset`: Growth 80/15/5, Balanced 60/30/10, Defensive 40/50/10, All-weather, Quad-tilted), "My current mix", or custom.
- Optional brakes: Quad tilt, and a Risk Dial multiplier that moves risk to cash.
- In the hand-picked mode used today, each class is split across the picked names: typed % or equal shares, whole shares, leftovers to cash.
- Other modes exist in code (area fill by Quad stance, recipes Low volatility / Low beta / Momentum / Core), but today's page always sends `manual: true`.

**Rules already in code:**
- Fund cap 20% of the account; sector/area cap 40% of a class; 3% minimum weight.
- Kept holdings (`ref_account_keep`) are never traded.
- 401k accounts are "plan funds only, paper guide".
- Taxable accounts show an estimated gain if sold.
- Position files older than 3 trading days are flagged. Stale price (3 days) and possible split (±40% in a day) raise alerts.
- One running model per account; the Final Call is information only (since 2026-10-27).

**Files**

| Piece | File |
|---|---|
| Tunable numbers (`PB_PARAMS`), measures, recipes, mix, nightly marks | `etl/derive_model_portfolio.py` |
| Build engine, vs-account, drift, back-test (pure functions) | `etl/builder_engine.py` |
| Read-only loaders (accounts, holdings, classes, pools, Quad, Risk Dial) | `etl/builder_data.py` |
| Accept/freeze, marks, list, detail, review, warnings, keep list, saved sets | `etl/builder_store.py` |
| API | `api/routers/builder.py` |
| Page | `web/builder.html`, `web/builder.js` |
| Logic doc | `docs/portfolio_builder_logic.md` |

**Tables:**
- `ref_pb_universe`: fixed fund list with class and area.
- `ref_pb_mix_preset`: class mix presets.
- `ref_accounts.account_type`: TAXABLE / IRA / ROTH / HSA / 401K / OTHER.
- `ref_account_keep`: kept holdings.
- `user_builder_set`: saved picks and targets.
- `user_model_portfolio` and `user_model_position`: frozen models.
- `drv_model_mark` and `drv_model_position_mark`: nightly marks.
- `drv_pb_score`: nightly recipe scores.

**Endpoints** (`/api/builder/...`):
- `accounts`, `presets`, `recipes`, `sources`, `source-names`
- `preview` (POST), `asset-class` (POST), `compare`, `backtest`
- `portfolios` (POST = accept, GET = list), `portfolios/{id}`, `/vs-account`, `/review-preview`, `/review`, `/warnings` (PATCH)
- `accounts/{short}/keep/{symbol}` (PUT/DELETE), `accounts/{short}/keep-lt` (POST)
- `sets` (GET/PUT/DELETE)

**What works:**
- An honest single view of an account across class, beta, Quad, sector and style, using the pie's colours and the pie's class map.
- Kept holdings, account types, saved sets, click-to-filter, copy symbols.

**What costs time:**
- Every visit starts from scratch.
- There are no standing targets and no household (all-accounts) target.
- Picks re-model the whole account, not "add new money and nudge".
- Nothing checks real cash, and there is no weekly answer to "do I need to do anything?".

### 2. Fixes to the existing screen (do first)

| # | Symptom | Cause in code | Proposed fix |
|---|---|---|---|
| 0a | You cannot freeze a model: there is no Accept button on Build new. | `web/builder.html` lines 291-357: the Build view has no Accept control. `web/builder.js` never calls `POST /api/builder/portfolios` (endpoint at `api/routers/builder.py` 179-187, store `etl/builder_store.py::accept` 55-121). The preview already returns `accept_blocked` reasons (`builder.py` 72-82, 104), but nothing shows them. | Add an "Accept and track" button under the picks grid: it asks for a name, posts the current request, and is greyed with the `accept_blocked` reasons as a bulleted tooltip. |
| 0b | No way to choose 1/3/6/12 months or to use the Risk Dial. | `builder.js` line 38 sets `horizon: '3M'` and `useDial: false`. Nothing on the page changes them. `openSet` (line 619) and `prefill` (line 848) force `useDial = false`. Yet the engine defaults `use_risk_dial` to true (`builder_engine.py` ~line 185), and `/api/builder/presets` already returns the horizons (line 52). | Put a "How long" button group (1M/3M/6M/12M) and a "Use Risk Dial" tick-box back in the left column, store both in saved sets, and stop `openSet`/`prefill` from overwriting them. |
| 0c | The Warnings tick-boxes look active but do nothing. | `builder.html` 308-313 and `builder.js` 77 store them in `S.warn`, which is sent as `warnings` and saved only by `accept` (`builder_store.py` line 109). Without Accept (0a) they are never used. After a freeze, the detail view has its own working opt-ins (`builder.js` 757, `PATCH .../warnings`). | Move the Warnings tick-boxes into the Accept step from 0a, with the label "Alerts for this tracked model", so they appear only where they take effect. |
| 0d | You cannot see or edit kept holdings. | Endpoints exist: `PUT/DELETE /api/builder/accounts/{short}/keep/{symbol}` and `POST .../keep-lt` (`builder.py` 254-273). The page has no UI for them. Also, hand-picked builds ignore the keep list: `builder_data.manual_kwargs` sets `use_keep: False`. | Add a lock toggle on each held row of the symbol table plus an "Add my long-term holds" button. Show locked rows as "Kept" and count them in their class. Decide whether hand-picked builds honour the list (recommend yes). |

Minor: the fund list seed spells an area "Short Duration Tresuries" (`db/seeds_portfolio_builder.sql`). Fix the spelling when touching that seed.

### 3. Proposed changes (Today -> Proposed)

| Area | Today | Proposed |
|---|---|---|
| Tabs | Build new, Portfolios | **This week** (default), **Set the build**, **Explore** (today's Build new, renamed), **Models** (today's Portfolios, renamed) |
| Targets | Typed per visit; a saved set stores picks, not a standing target | A standing **household build**: class mix + ranges, saved once, used every week |
| Inside a class | Per-name % boxes for the names you picked this visit | **Target list**: segments (sector / area) with a share of the class, and any names in each segment with a share of the segment |
| Limits | Fund cap and sector cap applied silently in the engine; nothing about cash | All limits are **soft**: warnings that name the limit and the amount over, never a block. Over-cash is a loud red warning |
| Buy list | "To match" column: rebuild the whole account | **Shopping list**: buys toward target from real cash, top block within cash and budget, the rest below with warnings; optional trims |
| Household | "Whole book" preview only | Household is the main view: one target for all accounts, a class x account table, and a rule for which account buys each line |
| Email | Watch digest only (other screen) | Weekly **build digest** using the same email code |
| Models | Frozen paper portfolios (unreachable today) | Kept as an optional paper test once fixes 0a-0c land (see Open question 5) |

### 4. "This week" tab (the one-glance screen)
Full page width.
```
+------------------------------------------------------------------------------------------------------------------+
| THIS WEEK                                                                       Positions: 11-12 · Prices: 11-13 |
| [AMBER]  5 buys, about $14.2K, in 2 accounts.  2 warnings.                                    Next check: Monday |
+------------------------------------------------------------------------------------------------------------------+
| SHOPPING LIST                                                                                                    |
| #  Do    Shares  Name  Account  About   Why (one line)                                     Call   Warn    Done   |
| 1  Buy     40    AGG   IRA      $3.9K   Core bonds are 6 points under their target.        Hold           [ ]    |
| 2  Buy     12    GLD   Taxable  $2.9K   Gold is 3 points under target (2% vs 5%).           Buy            [ ]    |
| 3  Buy      9    NVDA  Taxable  $1.6K   NVDA is under its share of Technology.             Hold   ! cap   [ ]    |
| --- Beyond this week's budget ($25K) ------------------------------------------------------------------------- |
| 4  Buy     30    XLV   IRA      $4.4K   Health Care is 2 points under target.              Hold   ! week  [ ]    |
| --- Beyond the account's cash ----------------------------------------------------------------------------- RED |
| 5  Buy     10    VEA   Taxable  $1.4K   Foreign is under target.  OVER TAXABLE CASH BY $1.1K   Hold   !! cash [ ]    |
| OPTIONAL TRIMS (only because a class is above its range)                                                         |
| -  none this week                                                                                                |
+------------------------------------------------------------------------------------------------------------------+
| BEFORE -> AFTER (all accounts)   [top block | all lines]   | LIMITS                                              |
| Equities     63% -> 64%   range 55-65                       | ✓ Cash floor kept in every account (top block)     |
| Fixed Income 24% -> 26%   range 22.5-37.5                   | ! NVDA would be 5.6% of all accounts: 0.6 pts over |
| Gold          2% ->  4%   range 3.75-6.25                   |   the 5% single-stock cap ($1.2K over)             |
| Cash          8% ->  3%   range 3.75-6.25  (below range)    | ! Lines 4-5 go $5.8K over this week's $25K budget  |
| Unmapped      1% ->  1%   (no target)                       | !! Line 5 spends $1.1K more than Taxable's cash    |
| Total       100% -> 100%                                    | ✓ Kept holdings untouched · no cash moved between  |
|                                                             |   accounts                                         |
+------------------------------------------------------------------------------------------------------------------+
| WHERE IT SITS (household): class x account ($ and %), target, gap; click a class for its segments and names     |
+------------------------------------------------------------------------------------------------------------------+
```
- **Top block** = lines that fit inside each account's spendable cash, this week's budget and today's cap. These are what to place without thinking.
- **Below the dividers** = the rest of the way to target. They are listed so you can choose to go further. The warning names the limit and the amount over.
- **Card colours** reuse the existing ones: green `--act-buy-bg`/`--act-buy`, amber `--mr-warn-bg`/`--mr-warn`, red `--act-sell-strong-bg`/`--act-sell-strong`.
  - Green: "Nothing to do this week. Every class is in its range."
  - Amber: "N buys, about $X, in M accounts." plus a warning count.
  - Red, with one reason, for example: "Position files are 5 trading days old. Download new ones, then check again." or "Line 5 spends more than Taxable's cash." Red never hides the list.
- **Warn column**: `!` amber chip for a soft limit, `!!` red chip for over-cash. The chip text names the limit (cap, sector, range, week, day, floor, cash).
- **Editable shares**: you can change the shares on any line. Totals, before/after and warnings update at once.
- **Before/after toggle**: "top block" (default) or "all lines". Both always add to 100%, because buys move money from cash into a class and the total does not change. If "all lines" pushes an account's cash below 0, Cash shows a red negative number with the over-cash warning.
- **Call column**: today's Final Call badge, as information only.
- **Done tick**: records the line (see Rules). Ticked lines turn grey.
- Bars reuse the existing `.bld-viz .vtrack2` style: the fill is the after value in the class colour, a thin grey bar is the before value, and black ticks mark the range ends. Being outside a range gets an amber outline. Drift is not good or bad, so there is no green/red on the bars.
- Tooltips are bulleted lists, never a flat string. Example on line 3:
  - Technology now 18% of Equities, target 20%
  - NVDA target 30% of Technology; now 22%
  - Taxable has $4.6K spendable (cash $6.6K minus $2.0K floor)
  - 9 whole shares at $178.40 (price 11-13)
  - Warning: NVDA would be 5.6% of all accounts, single-stock cap 5%, over by $1.2K

### 5. "Set the build" tab
```
+------------------------------ THE BUILD (all accounts) ------------------------------+------ LIMITS (soft) ------+
| Start from: [My current mix] [Balanced 60/30/10] [Growth] [Defensive] [All-weather]  | Cash to keep per account  |
| Class         Target   Range (auto)    Now                                            |   1% (at least $500)      |
| Equities        60     55 - 65         63%                                            | Most spend in a week $25K |
| Fixed Income    25     18.75 - 31.25   24%                                            | Most spend in a day  $25K |
| Gold             5     3.75 - 6.25      2%                                            | One fund   20% of all     |
| Commodities      3     2.25 - 3.75      1%                                            | One stock   5% of all     |
| Crypto           2     1.5 - 2.5        0%                                            | One sector 40% of Equities|
| Cash             5     3.75 - 6.25      8%                                            | Smallest trade $500       |
| Total          100 ✓                                                                  | Warn me when Risk Dial    |
|                                                                                       | says "No new risk" [✓]    |
+------------------------------------ TARGET LIST --------------------------------------+---- PER ACCOUNT ----------+
| EQUITIES (60%)                       share of class   names (share of segment)        | IRA   floor $1,000        |
|   Broad US                               40%          SPY 60 · VTI 40          [+]    | 401k  guide only (plan    |
|   Technology                             20%          NVDA 30 · MSFT 30 · XLK 40 [+]  |       funds)              |
|   Health Care                            10%          XLV (equal)              [+]    | Taxable floor $2,000      |
|   Foreign                                15%          VEA 70 · EEM 30          [+]    |                           |
|   Financials                             15%          (no names yet) -> buys go to    |                           |
|                                                       the segment's suggested fund    |                           |
| FIXED INCOME (25%)                                                                     |                           |
|   IG Credit 40% · TIPS 30% · Treasury Bills 30%  ...                                  |                           |
| GOLD (5%)  one segment: GLD                                                            |                           |
+---------------------------------------------------------------------------------------+---------------------------+
| [Save the build]   Saved 11-12 · 2 warnings: NVDA target 7.2% of all accounts > 5% single-stock cap ...         |
+--------------------------------------------------------------------------------------------------------------------+
```
- **Segments.**
  - Equities segments use the sector names the Portfolio pie already uses (11 sectors) plus the Builder areas "Broad US" and "Foreign".
  - Fixed Income segments use the Builder areas already in `ref_pb_universe`: Treasury Bills, Short Duration Treasuries, Long Bond, TIPS, IG Credit, HY Credit, MBS, Munis, Preferreds, Leveraged Loans, EM & Debt.
  - Gold, Commodities, Crypto and Currency have one segment each unless you add more.
  - You choose which segments to use. Unused segments get 0.
- **Names: any stock or fund.** "+" opens a symbol box with search. Explore also gets an "Add to target list" button on each row, which opens Explore filtered to that segment.
  - A name whose own class or sector differs from the segment gets a small amber note ("MSFT is classed Technology; you put it in Broad US"). It is still allowed.
- **Shares**: segment shares are a % of the class, and name shares are a % of the segment. A blank share means "split the rest equally".
- **Segment with a share but no names**: buys go to the "suggested fund" for that segment, which is the first `ref_pb_universe` fund in that area. The line says "suggested". If there is none, a warning says "Financials has no names: add one".
- **Each name shows** its Final Call badge and Quad chip (B/H/S, existing `.bld-chip`) as information.
- **Start from** copies a preset or the household's current mix into the boxes. It never saves by itself.
- **Save** stores the build even when limits are exceeded, and lists the warnings under the button. It refuses only on data-sanity errors (see Rules).

### 6. Household view and which account buys what
- The target is for **all accounts together**. Account mixes are shown but are not targets, so "over in one account, under in another" is not a problem. Only the household number counts.
- The account for each line is chosen in this order:
  1. The account allows the name. For a 401k, only names tagged for it; otherwise the line is "Put about $X into a plan fund for <segment>".
  2. The account has spendable cash left.
  3. Prefer an account that already holds the name.
  4. Then the account with the most spendable cash.
  5. Tie: account name A-Z.
- If no account has cash left, the line still goes to the account with the most cash and carries the loud over-cash warning.
- The repo knows each account's type but has no tax lots, tax brackets or placement policy. Placement by type is Open question 2 and is off by default.
- Cash never moves between accounts in a line. Each line is paid by its own account.

### 7. Reducing the time spent
**Routine:** once a week, open "This week" or read the email. If amber, place the top-block orders and tick Done. If red, read the one reason. About 5 minutes.

**Weekly email** reuses `etl/notify.py::send_email` and the `maybe_send_watch_digest` scheduler pattern in `etl/scheduler.py`. No new outside services. If mail settings are empty, nothing is sent.
- **When**: once a week on `build_digest_weekday` (default Monday) at `build_digest_hour` (default 8, before the open), after the newest position files load.
- **Subject**: "Build check: nothing to do", "Build check: 5 buys, $14.2K", or "Build check: needs a look".
- **Body**: the card line, the top-block lines, then the warnings as bullets.

**What you can stop checking for allocation:** the Actionable screen, the Hedgeye panel, Explore's name lists, the Portfolio pie and the Models tab. Explore is for adding names to the target list a few times a year.

### 8. Phase 2 (later, with the Actionable screen)
- The target list says **what** to own. Later, the Actionable screen's signals (Final Call and others) will decide **when** to buy toward it. For example, a name under target with a Buy signal goes to the top of the list this week.
- A name under target whose signal says Sell would show greyed under "Waiting" (Open question 1, option A) or not show at all (option B).
- In this Builder phase, the Final Call stays information only and never changes the list. Phase 2 is not designed here.

### Worth reconsidering
- **Per-account target mixes for every account.** These multiply the work and create fake "over/under" readings in single accounts. Keep one household target plus a few account rules (cash floor, 401k plan funds).
- **Many names per segment.** Any number is allowed, but each name adds small lines and more warnings. Two or three per segment keeps the list short.

## Rules & numbers

### Where the numbers come from
- **Holdings, cash, account value**: the newest position files per account (`builder_data.account_positions`), classified with the Portfolio pie's map (`classify_holdings`). Cash uses the database function `is_cash()`.
- **Prices**: the latest app quote on the anchor date (`drv_quote`); if missing, the broker's price from the position file.
- **Segment of a held name**: the pie's sector map for Equities; the `ref_pb_universe` area for funds on that list; otherwise "Other" in that class.
- **Information only**: Final Call (`drv_actionable`), Quad chip (existing area stance), Risk Dial (`builder_data.risk_dial`).
- **Dates**: the week is Monday to Sunday of the app's anchor date (the latest daily data date), never the computer clock.

### Ranges
- Automatic range = target ± the smaller of 5 points or a quarter of the target (the common "5/25" rule). Examples: 60 -> 55-65; 5 -> 3.75-6.25. **GUESS**.
- A target of 0 has no range. Holdings above 2 points count as "over". **GUESS**.
- You can type your own min/max for any class.

### Soft limits (warnings only, never a block)
Each warning names the limit, the number, and the amount over in points and dollars. The list is always produced.

| Limit | Default | Warning text example |
|---|---|---|
| Class range | auto (above) | "Equities would be 66%, 1 pt above its top of 65% ($4.2K over)." |
| One fund | 20% of all accounts (today's `fund_cap`) **GUESS** | "SPY would be 21% of all accounts: 1 pt over the 20% fund cap ($4.1K)." |
| One stock | 5% of all accounts **GUESS** | "NVDA would be 5.6%: 0.6 pts over the 5% stock cap ($1.2K)." |
| One sector | 40% of Equities (today's `area_cap`) **GUESS** | "Technology would be 42% of Equities: 2 pts over ($2.5K)." |
| Week spend | 5% of household value **GUESS** | "This list spends $5.8K more than this week's $25K." |
| Day spend | = week cap | "Today's lines are $3K over the $25K day cap." |
| Cash floor | 1% of account, at least $500 **GUESS** | "IRA would keep $600, $400 under its $1,000 floor." |
| Account cash (LOUD, red `!!`) | the account's cash | "Line 5 spends $1.1K MORE THAN TAXABLE'S CASH." |
| Smallest trade | $500 **GUESS** | Lines under it are not proposed; if you type one, "Under the $500 smallest trade." |
| Risk Dial | warn on "No new risk" | "Risk Dial says no new risk: Equities, Commodities and Crypto buys are flagged." |

- Fund versus stock uses the position file's security type when known. Unknown types count as a stock (the stricter cap).
- Kept holdings (`ref_account_keep`) are never put on a buy or trim line in the account where they are kept. This is a rule, not a limit.
- **Nothing trades automatically. The Builder never changes the Final Call.**

### Save refusals (data sanity only)
- Class targets do not add to 100 (± 0.1).
- Typed segment shares in a class add to more than 100, or are all typed and do not add to 100. The same applies to name shares in a segment.
- Any negative number (target, share, cap, floor, budget).
- A range min above its max.

Everything else saves with warnings.

### How the shopping list is made
1. **Red card first** if: no build is saved; any account's position file is older than 3 trading days (existing rule); or household value is 0. The list is still computed, except when there is no build, and the card states the reason.
2. **Household now**: dollars per class, per segment and per name across all accounts, cash included. Unmapped is its own row with no target.
3. **Act?** Yes if any class is outside its range, OR household cash is above its range top. Otherwise the card is green and there is no list. A class inside its range is left alone, which keeps trades rare.
4. **Targets in dollars**: name target $ = household value x class % x segment % x name %.
5. **Shortfall** per name = target $ − held $ (only names below target). Order:
   - by class shortfall in points;
   - then by segment shortfall;
   - then by name shortfall;
   - ties follow the fixed class order (Equities, Fixed Income, Gold, Commodities, Crypto, Currency), then segment and name order in the target list.
6. **Size each line** to the name's shortfall, in whole shares rounded down. Pick the account by Design §6. Skip a line under $500, and skip a name with no price in 3 trading days or a ±40% one-day move (the reason is shown).
7. **Split into blocks.** Walk the ordered lines. A line goes in the **top block** while it fits all of these:
   - the account's spendable cash;
   - the week budget left;
   - the day cap;
   - the class range top;
   - the fund, stock and sector caps.

   A line that does not fit is first shrunk to fit. The remainder becomes a line below the matching divider ("Beyond this week's budget", "Beyond the account's cash", "Over a cap"), with its warning.
8. **Spendable cash** = cash − cash floor − Done buys not yet in a newer position file + Done sells not yet in a newer position file. Trims never fund buys in the same list.
9. **Trims** are shown only when a class is above its range top, sized back to the top. Non-taxable accounts come first. In Taxable, the name with the smallest estimated gain comes first (using cost basis, "estimate, not tax advice"). Never a kept holding. Type OTHER shows "tax unknown".
10. **After mix** = before + buys − trims per class. The total is unchanged, so before and after each add to 100%.
11. **Limit check-list**: one line per limit, either a ✓ pass with the number or a warning with the amount over, for the selected view (top block or all lines).

### Edge cases
- **No price for every name in a segment**: a warning, and that segment's shortfall is reported unfilled.
- **Same data in, same list out**: the fixed tie orders make the list repeatable.
- **Done ticks**: they reduce spendable cash until a newer position file arrives, then stop counting. By then the file shows either the trade or the cash back.
- **Orders placed without a Done tick**: not visible until the next position file. The card reminds you to tick Done.
- **Splits**: a ±40% one-day move skips the name that week.
- **Inactive account, or no position file**: left out, and named on the card.
- **Mutual funds with no app quote**: the broker price is used; whole shares only.
- **Unmapped holdings above 2% of all accounts**: warning "3 holdings have no asset class: set them in Explore." **GUESS**.

## Files likely touched
- `web/builder.html`, `web/builder.js`: fixes 0a-0d, new tabs "This week" and "Set the build", tab renames, "Add to target list" in Explore; bump the `?v=` cache-buster. The new tabs may go in a separate `web/builder_guide.js`.
- `etl/build_guide.py` (NEW, pure functions with no database): `bands_for`, `validate_build`, `build_warnings`, `household_mix`, `name_targets`, `spendable_cash`, `shopping_list`, `trims`, `limit_checks`, `card_status`.
- `etl/builder_data.py`: `household_context(session, d)` returns every account's holdings, cash, type, kept list, prices and segment of each name (reuses `account_positions`, `classify_holdings`, `keep_list`). `manual_kwargs` change for fix 0d.
- `etl/builder_store.py`: save/read the build, target list and done log.
- `api/routers/builder.py`: new endpoints (below).
- `etl/scheduler.py`: `maybe_send_build_digest(state_path)`, modelled on `maybe_send_watch_digest`.
- `db/baseline.sql`: three new tables. `db/seeds_build_guide.sql`: `ref_settings` rows `build_digest_weekday` (1), `build_digest_hour` (8), `build_band_pts` (5), `build_band_rel` (0.25), `build_min_trade_usd` (500), `build_stock_cap_pct` (5).
- `db/seeds_portfolio_builder.sql`: spelling fix "Treasuries".
- `docs/portfolio_builder_logic.md`: new section "Standing build and weekly guide", plus one CLAUDE.md lookup row.
- `tests/test_build_guide.py`: pure-function tests.

### New tables
`user_build_target`: one row per scope.

| column | type | note |
|---|---|---|
| scope | TEXT PK | 'HOUSEHOLD' or an account short name (account rows hold rules only) |
| mix | JSONB | {class: target %}, Cash included; household row |
| bands | JSONB | {class: [min, max]}; missing = automatic |
| cash_floor_pct / cash_floor_usd | NUMERIC | floor = the larger |
| max_spend_week / max_spend_day | NUMERIC | household row |
| fund_cap_pct / stock_cap_pct / sector_cap_pct | NUMERIC | 20 / 5 / 40 |
| min_trade_usd | NUMERIC | 500 |
| guide_only | BOOLEAN | account rows; TRUE for 401K by default |
| warn_on_risk_dial | BOOLEAN | TRUE |
| updated_at | TIMESTAMPTZ | |

`user_build_target_line`: the target list (segments and names in one table).

| column | type | note |
|---|---|---|
| line_id | SERIAL PK | single-column key |
| bucket | TEXT | asset class |
| segment | TEXT | sector / area name |
| tos_symbol | TEXT | NULL = the segment row itself |
| share_pct | NUMERIC | segment row: % of class; name row: % of segment; NULL = equal split of the rest |
| accounts | JSONB | NULL = any account; else list of short names (for 401k plan funds) |
| sort_order | INT | |
| active | BOOLEAN | |
| added_at | TIMESTAMPTZ | UNIQUE (bucket, segment, tos_symbol) |

`user_build_done`: what you placed.

| column | type | note |
|---|---|---|
| done_id | SERIAL PK | |
| account_short, tos_symbol, side (BUY/SELL) | TEXT | |
| shares, est_price, est_usd | NUMERIC | |
| list_date | DATE | anchor date of the list |
| done_at | TIMESTAMPTZ | |
| cleared_snap | DATE | set when a newer position file arrives; cleared rows stop counting |

There is no new derived table: the guide is computed live, and the email calls the same function.

### New endpoints
- `GET /api/builder/build`: the build, account rules, target list, automatic ranges, current mix, warnings.
- `PUT /api/builder/build/{scope}`: save. Returns `warnings` (soft); 400 only for data-sanity errors.
- `POST/PATCH/DELETE /api/builder/target-lines[/{id}]`.
- `GET /api/builder/guide?date=&view=top|all`: card, lines with blocks and warnings, trims, before/after, checks, household table.
- `POST /api/builder/done`, `DELETE /api/builder/done/{id}`.
- Existing endpoints stay; fixes 0a-0d use them.

### Build plan (each task ships and is tested on its own)

| # | Task | Acceptance checks (behaviour only) | DB |
|---|---|---|---|
| 0a | Accept button on Build new | Button posts the current request and a model appears under Models; when `accept_blocked` has reasons the button is greyed and the tooltip lists them as bullets | Yes |
| 0b | Horizon + Risk Dial controls | Choosing 6M sends `horizon: '6M'` and the saved set reopens with 6M; ticking Risk Dial sends `use_risk_dial: true` and survives Open/prefill | No (UI) |
| 0c | Warnings moved into the Accept step | Ticked alerts are stored on the new model (`warnings.opt_in`) and show checked in its detail view | Yes |
| 0d | Keep-list UI | Locking a held name calls the PUT endpoint and shows "Kept"; unlocking calls DELETE; kept names never get a trade line | Yes |
| 1 | `bands_for`, `validate_build`, `build_warnings` (pure) | 5/25 range values; class targets not adding to 100 refused; negative numbers refused; min > max refused; a build over a cap SAVES and returns a warning naming the cap and the amount over | No |
| 2 | `household_mix`, `name_targets`, `spendable_cash`, `shopping_list`, `trims`, `limit_checks`, `card_status` (pure) | For fake books: (a) whenever a line crosses a limit, a warning names that limit and the amount over, and the list is still produced; (b) a line that spends more than its account's cash carries the loud over-cash warning and turns the card red; (c) top-block buys per account <= spendable cash and the top-block total <= week and day caps; (d) before and after mix each add to 100% (± 0.01) in both views; (e) kept names never appear; (f) whole shares only, no proposed line under $500; (g) same input -> same list; (h) every class in range -> green, no list | No |
| 3 | Tables + seeds + build and target-line endpoints | Invalid save -> 400 and nothing written; a save over a cap -> 200 with warnings; round-trip | Yes |
| 4 | `household_context` + `GET /api/builder/guide` + done log | A Done tick lowers spendable cash; ticks older than a newer position file stop counting; an old position file -> red card with the reason, list still returned | Yes |
| 5 | Page: "Set the build" tab + "Add to target list" in Explore | Manual: preset fills the boxes, save shows warnings as bullets, refusals in plain words | No (UI) |
| 6 | Page: "This week" tab as default; tab renames; editable shares re-check warnings | Manual: blocks and dividers, red over-cash chip, before/after toggle adds to 100%, full width | No (UI) |
| 7 | Weekly email | At most once per week (state file); tests mock `send_email`, so no real email is ever sent | Mocked |
| 8 | Docs + CLAUDE.md lookup row | none | No |

Tasks 1 and 2 are pure Python on fake data and need no database.

### Risks and how each is handled

| Risk | Handling |
|---|---|
| Stale prices | Name skipped if no price in 3 trading days; card shows the price date |
| Old position files | Red card with the reason; the list is still shown but marked "based on positions from <date>" |
| Splits | A ±40% one-day move skips the name that week |
| Unmapped holdings | Own row, never a target; warning above 2% |
| Whole-share rounding | Always rounds down; leftover stays cash |
| Committed cash / pending orders the repo cannot see | Done log reduces spendable cash until a newer position file; cash floor as a buffer; reminder on the card |
| Unsettled sale cash | The repo cannot tell settled from unsettled cash. Trims never fund buys in the same list; raise the cash floor if your broker holds sale cash |
| User goes over limits on purpose | Allowed; every crossing is named with the amount, and the email repeats the warnings |
| 401k fund menus | Guide-only lines per segment unless a name is tagged for that account |
| Target list names in the wrong segment | Amber note on the name; still allowed |

## Open questions
- **1. Phase 2, "Waiting" names.** When a name is under target but its signal says Sell: (A) show it greyed under "Waiting" with the reason, or (B) hide it. Recommend A: you can still see the gap. Not built in this phase.
- **2. Account type for placement.** The repo knows each account's type but has no placement rules. Recommend: off at first (place by "already holds it", then "most cash"). Alternative: a small editable table, for example Fixed Income prefers IRA/401k and Equities prefers Roth/Taxable.
- **3. When to suggest trims.** Recommend: only when a class is above its range top, and only back to the top. Alternative: whenever above target (more trades, more tax in Taxable).
- **4. Weekly email when nothing to do.** Recommend: send a one-line "nothing to do" every week, so silence never hides a broken job. Alternative: email only when there is something to do.
- **5. Models tab.** Recommend: keep it as an optional paper test, with fixes 0a-0c making it work. Alternative: retire it. Then 0a-0c become "remove the dead controls", and the nightly model marking can stop.
- **6. Starting numbers.** Recommend:
  - ranges by the 5/25 rule;
  - fund cap 20% and single-stock cap 5% of all accounts;
  - sector cap 40% of Equities;
  - week cap 5% of household value, day cap equal to the week cap;
  - cash floor 1% of the account, at least $500;
  - smallest trade $500.

  All are GUESS values, and all are soft.
- Note: read-only database queries were blocked in this session, so the dollar amounts in the mock-ups are made up, not taken from real accounts.

## Status
READY_FOR_DEV — Builder phase (fixes 0a-0d, then Tasks 1-8). Phase 2 (Actionable timing) not designed.
