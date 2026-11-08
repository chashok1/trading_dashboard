# Design Spec — DESIGN_WORK_9 (revision 2: accounts + asset allocation)

## Goal
Build a "set it and forget it" model portfolio **for one account at a time**:
1. pick the account;
2. pick the mix by asset class (Equities / Fixed Income / Gold / Commodities / Cash ...);
3. let a recipe fill each part (for example, equities by Momentum, bonds by Low volatility);
4. freeze it for 1, 3, 6 or 12 months.

The app tracks it on paper and compares it with what that account really holds.

> This revises `DESIGN_SPEC_9.md` (left untouched) after user feedback: "I have multiple accounts. I need to
> choose by account. Maybe by asset allocation makes sense?" Everything in spec 9 still applies unless this
> spec says it changed. The "What changed from spec 9" section lists every removal and merge. Mockup updated in
> place: `docs/mockups/builder_mockup.html`.

---

## One-page summary (plain English)

**The flow is now account first, mix second, recipes third.**

0. **Pick the account.** The list is your accounts, grouped the same way the account watchlist files group them
   (by short name, so a renamed broker account still counts as one), plus "Whole book". The amount fills in
   with that account's current value, and the starting mix fills in with what it holds today, cash included.
1. **Pick how long:** 1, 3, 6 or 12 months (unchanged).
2. **Pick the mix.** Choose a preset (My current mix, Growth 80/15/5, Balanced 60/30/10, Defensive 40/50/10,
   All-weather, Quad-tilted) or move the sliders yourself. The buckets are the same ones as the Asset Allocation
   pie on the Portfolio screen. A bar shows **current vs target** for the account, with the dollars that would
   move.
3. **Pick a recipe for each bucket.**
   - Equities choose from Quad, Low volatility, Low beta or Momentum.
   - Fixed Income chooses from Core, Quad or Low volatility.
   - Gold, Commodities, Crypto and Currency each hold one standard fund (for example GLD for gold). We do not
     track enough funds there for a recipe to choose between.
4. **See and accept.** Same grid as before, now grouped by bucket. Holdings you have marked **"keep as is"**
   stay untouched: they count toward their bucket, and the builder fills only the rest.

**One model per account at a time.** Each frozen model belongs to one account, so nothing is double counted.
The list of model portfolios gets an **Account** column, an account filter and a totals row per account.
"vs your book" compares the model with **that account's holdings only**, bucket by bucket and fund by fund.

**Account types matter a little, not a lot.** Each account gets a type (Taxable, IRA, Roth, HSA, 401k). Taxable
accounts show the gain you would realise if you sold to match the model. A 401k is paper-only: it can usually buy
only plan funds, so no trade list is shown. v1 does nothing cleverer with taxes.

**Simpler than spec 9.**
- The "blend two recipes with a slider" idea is gone. The mix by asset class does that job more clearly.
- The Risk Dial now simply moves money from the risky buckets into Cash.
- The "Only from" filter is gone, because the bucket *is* the filter.
- The area cap now applies only to sectors inside Equities.

**Data note.** Read-only database checks were blocked again in this session. Account names, bucket coverage
and all example numbers below come from the code and the docs, and the numbers are **illustrative**. Task 1
confirms them.

---

## Open questions (my recommendation first)

1. **One running model per account?** *Recommend:* yes. Building a new one for that account replaces the
   running one (Roll over). *Alternative:* allow several partial models per account, each with its own amount
   (needs overlap rules and gets confusing fast).
2. **Where does the "keep as is" list come from?** *Recommend:* a new per-account list you tick right in the
   builder, with a one-click "add my LT Hold names held in this account" helper (from `ref_conviction_hold`).
   *Alternative:* reuse the LT Hold list as-is, but that list is household-wide, not per account.
3. **What counts as the account's "cash" bucket?** *Recommend:* real cash plus money-market and cash-like rows,
   using the existing `is_cash()` test, exactly as the Portfolio pie does. Short-term bond funds (BUXX) stay in
   Fixed Income, as the pie has them. *Alternative:* count BUXX / BIL as cash.
4. **Presets: are my starting numbers right?** *Recommend:* ship the six below as editable rows in a table
   (`ref_pb_mix_preset`), so you can change them later without code. Growth / Balanced / Defensive use your
   numbers. All-weather and Quad-tilted are GUESSes: please confirm or change.
5. **Account types:** *Recommend:* add a `type` to each account (Taxable / IRA / Roth / HSA / 401k / Other), set
   once on the Ref Data screen. In v1 it only (a) shows the realised gain on taxable sells and (b) hides the trade
   list for 401k. *Alternative:* skip types in v1.
6. **"Whole book" as a choice:** *Recommend:* allow it **for preview only**. It shows a household-level target vs
   current, but cannot be frozen, so it can never double count against account models. *Alternative:* allow
   freezing it as a separate paper model shown in its own row and left out of the account totals.

(Spec 9's questions on paper model vs real target, funds only, Yahoo backfill, Final Call skip and holding
shares stay as recommended there, unless the user says otherwise. Q4 there, Risk Dial sizing, is now rule R5
below.)

---

## Design

### What changed from spec 9 (removed / merged)

| Spec 9 | Spec 10 | Why |
|---|---|---|
| Amount typed by hand | Defaults to the chosen account's value (still editable) | Account first |
| Cash % box | Cash is one bucket of the mix; defaults to the account's real cash % | One place for cash |
| Blend two recipes (sleeves, 60/40 slider) | **Removed.** One recipe per bucket | The mix already says "60% of the money does X" |
| "Only from" filter | **Removed** (v2 may add "Equities: only Tech") | The bucket is the filter |
| Area cap 40% across everything | Sector cap 40% **of the Equities bucket** only | Other buckets hold 1-7 funds; caps there would only fight the mix |
| Fund cap 20% of portfolio | No fund above 20% of the account, **except** single-fund buckets and Cash (for example GLD in a 10% Gold bucket is fine; a 30% Gold bucket shows a note) | Keeps All-weather possible |
| Risk Dial puts the uninvested part in cash | Risk Dial **trims the risky buckets into Cash** (R5) | Same effect, visible on the mix bar |
| Positions (5-20) for the whole portfolio | Positions **per bucket**: Equities 8 (4-15), Fixed Income 3 (1-5), others 1 | The bucket size decides |
| "vs your book": whole book or an account, scaled | That account only, by bucket then by fund, not scaled | The model *is* that account |
| List view without accounts | Account column, filter, totals row per account | Feedback |

Unchanged from spec 9:
- the fund list and eligibility (R0);
- the measures (R1);
- the recipe scores, now used inside Equities (R2);
- weights inside a bucket (R3);
- the Final Call skip (R6);
- holding day-1 shares (R7);
- warnings (R8);
- the promise check (R9);
- the back-test (R10), now run per bucket and summed with the bucket weights.

### Step 0 — Account picker (top of Build new, full width)

```
Account  [ F-A  (Fidelity, Taxable)   $412,300  v ]   Type: Taxable   Running model: none   Kept: 3 holdings ($61,200)
```

- **Options:** one per active `short_name` in `ref_accounts` (`is_active = TRUE`), the same grouping as
  `etl/generate_account_watchlist_files.py`. Each shows its value and type. "Whole book (preview only)" comes
  last.
- **Value** = latest positions file for that account group (`hist_cs` + `hist_f`, latest snapshot per source),
  cash rows included. The same number the Portfolio screen shows for that account filter.
- **If the account already has a running model:** a banner says "F-A already has a running model: Quad 3M
  (ends Jan 23). Accepting a new one will close it and start this one." The Accept button becomes
  "Replace and freeze".
- **Stale positions file** (older than 3 trading days, GUESS): an amber note "Positions as of Oct 17". Preview
  still works.

### Step 2 — The mix (Layer 1)

```
Mix   Preset [ Balanced 60/30/10        v ]     (My current mix | Growth | Balanced | Defensive | All-weather | Quad-tilted | Custom)

               Current   Target                    $ change
Equities       71%  ========o---------  60%   -45,400
Fixed Income   12%  =====o-------------  30%   +74,200
Gold            4%  o------------------   0%   -16,500
Commodities     0%  o------------------   0%         0
Crypto          3%  o------------------   0%   -12,400   (Kept: IBIT $12,400 is a kept holding -> floor 3%)
Currency        0%  o------------------   0%         0
Cash           10%  (the rest)            10%       0
                                         ----
                                         100%
Current |██████████████ Equities ███████|█FI█|G|C|▒Cash▒|
Target  |███████████ Equities ███|████ Fixed Income ███|▒Cash▒|
Risk Dial: Caution x0.70 -> Equities 60% becomes 42%, Cash 10% becomes 28%   [x] apply
```

- **Buckets** are exactly the Portfolio pie's asset classes, in the same colours (`_PM_ASSET_COLORS` in
  `web/portfolio_mix.js`): Equities, Fixed Income, Gold, Commodities, Crypto, FX (labelled "Currency"), Cash.
  The pie's "Unmapped" holdings are shown in the current bar as grey "Unmapped" and **cannot** be a target.
  Task 1 lists them so they can be fixed in `ref_sector`.
- **Sliders** move in 5% steps (1% by typing). Cash is always "the rest" and cannot go below 0. Moving a slider
  past the room left is stopped there.
- **Kept holdings set a floor:** a bucket cannot go below the share its kept holdings already fill. Hover
  explains this as bullets.
- **The current-vs-target bar** is two stacked bars, one per row, using the pie colours. Each segment has its
  label when it is 6% or more; smaller ones show on hover.
- **$ change** = (target - current) x account value. It is shown with no colour (it is a move, not a gain);
  "+" means more money goes into that bucket.

### Step 3 — Recipes per bucket (Layer 2)

```
Equities (60% = $247,400)   Recipe [ Momentum         v ]   Positions [8]
Fixed Income (30% = $123,700) Recipe [ Core           v ]   Positions [3]
Gold / Commodities / Crypto / Currency: one standard fund each (GLD / GSG / IBIT / UUP), shown only if > 0%
Cash: stays cash (0% interest assumed in v1)
```

| Bucket | Recipes offered | Standard (no-choice) fund | Funds in the list (~80) |
|---|---|---|---|
| Equities | Quad, Low volatility, Low beta, Momentum (spec 9 R2) | - | ~55: 11 sector funds, SPY / QQQ / IWM / DIA, style funds (MTUM, SPLV, VYM, USMV*, VTV*, VUG*, SPHB*, MDY*, QUAL*), foreign (EEM, EFA, EWJ, EWZ, EWG ...) |
| Fixed Income | **Core** (inverse-swing weighted across the list), **Quad** (Fixed Income sub-class stance: Long Bond, IG Credit, HY Credit, ...), **Low volatility** (calmest) | - | 7 now: TLT, IEF, HYG, LQD, BUXX, CLOX, CLOZ. Up to 12 with SHV*, BIL*, AGG*, BND*, TIP* |
| Gold | none | GLD | GLD (IAU* optional) |
| Commodities | none | GSG | GSG, DBC*; SLV goes where `ref_sector` puts it (Task 1 checks) |
| Crypto | none | IBIT | IBIT |
| Currency | none | UUP | UUP |
| Cash | none | cash | - |

`*` = not yet in the daily export; added in Task 1 (no history until it builds up, or until the Yahoo backfill
runs).

- **Why recipes only for Equities and Fixed Income:** the other buckets have one or two funds, and a "recipe"
  choosing between one fund would be pretend choice.
- **Empty bucket:** a bucket with 0% hides its recipe row.
- **Too few funds:** if a recipe bucket has fewer eligible funds than positions asked, it takes what exists. If
  it has 0, its money goes to Cash with a note.

### Step 4 — Proposed portfolio

The grid from spec 9, **grouped by bucket**, with a sub-total row per bucket. New columns:
- **Kept:** a lock icon on kept holdings, shown with their current value. Their "why" is "Kept as is (your
  list)".
- **You hold now $:** what this account holds of that fund today.

Under the grid:
- "Skipped because of a Sell call" (unchanged);
- "Held, not in model" (non-kept holdings the model does not include);
- for taxable accounts, **"Selling to match would realise about $X gain / $Y loss"** (from the positions
  file's cost basis; illustrative, not tax advice).

### Warnings, accept, back-test
Unchanged from spec 9, except:
- the portfolio name defaults to "<account> <preset> <recipe> <horizon> <Mon-YY>";
- the back-test runs each bucket's recipe on its own and adds them up by the target weights. Kept holdings are
  replayed as held.

### View 2 — My model portfolios (list)

```
Account [ All accounts v ]   Status [ Running + review due v ]

Account     Name                         Mix         Period          Day    Value      Return  vs SPY  vs account  Status
F-A         F-A Balanced Mom 3M Oct-26   60/30/10    Oct 23-Jan 23   3/63   $412,900   +0.8%   +0.3%   -0.2%       Running
F-A         F-A Growth Quad 1M Sep-26    80/15/5     Sep 25-Oct 23   done   $409,100   +2.1%   +0.9%   +1.4%       Closed
  F-A total                                                                  $412,900*  running: +0.8%   all periods: +$8,950
HSA         HSA Defensive LowVol 6M      40/50/10    Oct 23-Apr 23   3/126  $88,400    +0.2%   -0.3%   +0.1%       Running
  HSA total                                                                  $88,400    running: +0.2%   all periods: +$180
All accounts                                                                 $501,300   running: +0.7%  (value-weighted)
```

- The list is grouped by account, with a totals row per account and a grand total.
- **Totals add up running models only** (one per account, so there is no double counting). "All periods" sums
  the paper $ gain of every model, closed ones included, for that account. (*Value counts the running model
  only.)
- "vs account" = model return minus that account's own time-weighted return over the same dates (spec 9 R7,
  restricted to the account).

### View 3 — Detail: new "Allocation drift" card (above "vs your account")

```
ALLOCATION DRIFT  (F-A, today)
               Target   Model now   Account now   Account vs target
Equities        42%       43%          71%          +29 pts   (amber)
Fixed Income    30%       29%          12%          -18 pts   (amber)
Cash            28%       28%          10%          -18 pts   (amber)
Gold             0%        0%           4%           +4 pts
Crypto           0%        0%           3%           +3 pts   (kept)
[Target bar] [Model-now bar] [Account-now bar]  - three stacked bars, pie colours
```

- **"Model now"** drifts with prices, because we hold shares, not weights.
- **"Account now"** is the real account today.
- **Amber when a gap is 5 points or more** (GUESS); otherwise plain. Drift is not good or bad, so there is no
  green or red.
- "vs your account" (fund level) works as in spec 9, but only for this account's holdings and with no scaling.
  Kept holdings show "Kept" in the trade column.

---

## Rules & numbers

### A1 — Accounts
- **Account group** = `ref_accounts.short_name` among `is_active = TRUE` rows. Holdings are summed across the
  raw account numbers in the group, as the account watchlist generator does.
- Inactive accounts never appear.
- An account with no `short_name` is listed under its `account_number`.
- **New column `ref_accounts.account_type`:** TAXABLE / IRA / ROTH / HSA / 401K / OTHER, default OTHER, edited
  on /ref.
  - From the names seen in `db/baseline.sql`: "Rollover_IRA ...892" is IRA and "HSA ...311" is HSA. The
    "Designated_Bene_Individual" rows are probably taxable (transfer-on-death individual), a GUESS. The Fidelity
    numbers are unknown. **The user sets these.**
- **What the type changes in v1:**

  | Type | Effect |
  |---|---|
  | TAXABLE | The trade list shows the estimated realised gain/loss on sells, using cost basis from `hist_cs.cost_basis` / `hist_f.cost_basis_total` |
  | IRA / ROTH / HSA | No tax line. All funds allowed. Nothing in the fund list is leveraged, inverse or futures, which is where IRA limits usually bite |
  | 401K | Model is paper-only: the trade list is replaced by "Plan funds only, use as a guide". Drift is still shown |
  | OTHER | Same as TAXABLE but without the tax line |

- **Not in v1:** wash-sale checks, tax-lot choice, placing funds by account type (for example bonds in the IRA).
  These are listed for v2 as "household placement".

### A2 — Amount and starting mix
- **Amount** = account value (A1), editable. Lowering it means "model only part of the account". The leftover
  is treated as kept-as-is cash outside the model, and the bar shows it.
- **Starting mix** = the account's current bucket shares (preset "My current mix").
- **Current bucket of a holding:**
  - the same map the pie uses (`/api/portfolio/asset-class-map` → `_category_axis_map(..., "asset_class")`,
    normalised by `_normAssetClass`);
  - cash = `is_cash()` rows;
  - anything else is "Unmapped" (shown, cannot be a target).
- **Bucket of a fund in the list:** `ref_pb_universe.bucket` is checked in Task 1 to agree with that same map. If
  they disagree, the map wins and Task 1 reports the row.

### A3 — Keep-as-is list
- **New table** `ref_account_keep (account_short, tos_symbol, note, added_at)`, PK `(account_short, tos_symbol)`.
  Edited from the builder with a lock toggle on the holdings list, and from /ref.
- **A kept holding:**
  - keeps its current shares;
  - counts toward its bucket at today's value;
  - is never in the trade list;
  - is never "Held, not in model";
  - is excluded from the recipe's picks (so it is not bought twice).
- **Bucket money for the recipe** = target $ - kept $ in that bucket. If kept $ exceeds the target:
  - the bucket's recipe buys nothing;
  - the excess shows as a note: "Kept holdings already put Equities at 66%, 6 points over target";
  - the slider floor (Step 2) keeps the user from setting a target below the kept share without seeing this.
- **Kept holdings in the paper model** are marked like any holding (shares frozen at accept), so the model
  return includes them.
- The Final Call is shown on kept holdings but never causes a skip.

### A4 — Several models and the same fund in several accounts
- **One RUNNING (or PENDING) model per account group.** Accepting a new one sets the old one to CLOSED with
  reason "replaced", and links them (`rolled_from_id`). REVIEW_DUE models do not block.
- **"Whole book"** is preview only (Q6). Its current mix sums all active accounts; its target uses the same
  presets.
- **The same fund in several account models:** fine, because each model is separate. The list view's grand
  total row has a hover listing funds that appear in 2+ running models, with the combined $ (for example "XLK: 3
  models, $41,000 = 8% of all running models").
  - If any fund is over **20% of all running models combined** (GUESS), it gets an amber note there. Nothing
    is blocked.
- **The Actionable Final Call sizing** (`ref_asset_allocation` / `drv_account_size`) stays separate. The
  builder never writes to it. The "You hold now" column plus the Final Call column make any disagreement visible.

### A5 — Presets (`ref_pb_mix_preset`, editable seed)

| Preset | Equities | Fixed Income | Gold | Commodities | Crypto | Currency | Cash | Source |
|---|---|---|---|---|---|---|---|---|
| My current mix | account's own | | | | | | | computed |
| Growth | 80 | 15 | 0 | 0 | 0 | 0 | 5 | user |
| Balanced | 60 | 30 | 0 | 0 | 0 | 0 | 10 | user |
| Defensive | 40 | 50 | 0 | 0 | 0 | 0 | 10 | user |
| All-weather | 30 | 55 | 7.5 | 7.5 | 0 | 0 | 0 | GUESS (classic stocks / long + mid bonds / gold / commodities) |
| Quad-tilted | Balanced, shifted by the Quad (below) | | | | | | | GUESS |

- **All-weather** sets the Fixed Income recipe to "Duration split": TLT 25 / IEF 15 / the rest Core, as a share
  of the account (GUESS).
- **Quad-tilted:**
  - For each bucket, take its `ref_quad_outlook` "Asset Class" stance (+1 / 0 / -1) under the horizon-matched
    Quad window (spec 9 R2).
  - New share = base share x (1 + 0.25 x stance) for Equities, Fixed Income, Gold and Commodities (GUESS 0.25).
    Cash and Crypto are not tilted.
  - Then rescale the non-cash buckets so Cash keeps its base share.
  - Recomputed at **build time only** and then frozen like everything else. The hover shows the stance per
    bucket as bullets.

### R5 (replaces spec 9 R5) — Risk Dial
- If "apply" is ticked: each **risky bucket** (Equities, Commodities, Crypto) is multiplied by the Risk Dial
  `suggested_size_multiplier`, and the money removed goes to Cash. Fixed Income, Gold and Currency are untouched.
- Kept holdings are never trimmed: the trim stops at the kept floor.
- Read once at build, stored on the model, never applied mid-period. With no dial reading, nothing is trimmed and
  a note says so.

### R2b — Fixed Income recipes
- **Core:** all eligible Fixed Income funds, inverse-swing weighted (spec 9 R3), top N by lowest swings when there
  are more than N.
- **Quad:** each fund's stance under the `ref_quad_outlook` "Fixed Income" category, by its `sub_asset_class`
  (as `derive_macro` does). Keep stance > 0, rank by stance, then lower swings. If none is > 0, fall back to Core
  and say so.
- **Low volatility:** lowest vol63 first. It will mostly pick short-term funds (BUXX, SHV, BIL), and the
  description says so: "calmest, mostly short-term".

### Edge cases added
- **Account with no positions file yet:** not listed.
- **Account value is 0, or all cash:** allowed. The current bar is 100% Cash.
- **Fractional shares in the account:** the trade list rounds to whole shares. The leftover goes to the Cash
  bucket.
- **Account renamed by the broker mid-period:** grouping by `short_name` keeps it the same model, as the
  watchlists do.
- **Account made inactive mid-period:** the model keeps marking on its frozen shares. The "Account now" columns
  show "account inactive".
- **Option or short positions in the account:** counted in "Unmapped" for the current bar, never a target.
  Flagged in "Held, not in model".

### Example (ILLUSTRATIVE, not real data)
F-A (Taxable), $412,300, Balanced 60/30/10, Risk Dial Caution x0.70 applied, Equities = Momentum (8), Fixed Income
= Core (3), kept: AAPL $38,000, MSFT $23,200.

| Bucket | Target | $ | Picks |
|---|---|---|---|
| Equities | 42% | 173,200 | kept AAPL 38,000 + MSFT 23,200; Momentum fills 112,000: XLK, SMH*, XLI, XLF, MTUM, IWM, EEM, XLC (inverse-swing, sector cap 40% of the bucket) |
| Fixed Income | 30% | 123,700 | Core: BUXX 52,000, IEF 38,900, LQD 32,800 |
| Cash | 28% | 115,400 | 10% preset + 18% moved by the Risk Dial |

`*` only if SMH is in the fund list. Taxable line: "Selling to match would realise about +$14,800 gain" (made
up).

---

## Files likely touched (in addition to spec 9's list)
- `db/baseline.sql`:
  - `ref_accounts.account_type`;
  - new `ref_account_keep` and `ref_pb_mix_preset`;
  - `user_model_portfolio` gains `account_short`, `mix_target JSONB`, `mix_at_build JSONB` (current mix at
    accept), `bucket_recipes JSONB`, `kept JSONB`, `close_reason`;
  - `user_model_position` gains `bucket`, `is_kept`;
  - `drv_model_mark` gains `account_twr`, `account_mix JSONB`;
  - the `recipe_mix` / blend fields from spec 9 are dropped.
- `db/seeds_portfolio_builder.sql`: presets, plus `bucket` per fund in `ref_pb_universe`.
- `api/routers/builder.py`: preview body becomes {account, horizon, amount, mix, bucket_recipes, positions per
  bucket, use_risk_dial, skip_sells}. New endpoints:
  - `GET /api/builder/accounts` (groups, value, type, current mix, running model, kept list);
  - `PUT/DELETE /api/builder/accounts/{short}/keep/{symbol}`;
  - `GET /api/builder/presets`;
  - `GET /api/builder/portfolios?account=`.
- `api/routers/dash.py`: reuse `_category_axis_map` (import it, do not copy it).
- `web/builder.js` / `builder.html`: account bar, mix step (sliders + two bars), per-bucket recipes, grouped grid,
  list grouping and totals, drift card. Reuse `_PM_ASSET_COLORS` / `_normAssetClass` from `web/portfolio_mix.js`
  (load that script) so the colours and names match the pie.
- `web/ref.js`: nothing (the generic editor handles the new column and tables).
- `docs/portfolio_builder_logic.md`: one detail doc covering both specs.

## Phasing (one afternoon each; replaces spec 9's list)

| # | Task | Done when |
|---|---|---|
| 1 | Data check + fund list: confirm the account groups and types, each account's current mix through the pie map, Unmapped holdings, bucket coverage of the fund list; seed `ref_pb_universe` (with bucket) + presets; add missing funds to the daily export | Report with real numbers replaces the illustrative example |
| 2 | Measures + Equities recipes + Fixed Income recipes as pure functions, `drv_pb_score` nightly, unit tests | Scores match a hand check |
| 3 | Build engine: account value, mix (presets, Quad tilt, Risk Dial trim, kept floors), fill buckets, caps, Final Call skip, why lines; `POST /api/builder/preview`, `GET /api/builder/accounts` | Preview JSON for 2 accounts |
| 4 | Builder page: account bar, mix step with current-vs-target bar, recipe per bucket, grouped grid + keep toggle | User sees a proposal per account |
| 5 | Accept / freeze (one per account, replace flow) + daily marks + list view with account grouping and totals | Two accounts' models mark for 2 dates |
| 6 | Detail: allocation drift card + fund-level "vs your account" + taxable gain line | Drift matches the Portfolio pie for that account |
| 7 | Back-test per bucket (+ Yahoo backfill if approved) | Honest period counts |
| 8 | Warnings, promise check, end-of-period review / roll / close | Review works on a back-dated test model |

v2: household placement by account type, "Equities: only Tech" filters, more recipes (High beta, Income, ...),
dividends in returns, cash earning a T-bill rate, freezing a Whole-book model.

### Worth reconsidering
- **Crypto and Currency as targets.** Each is one fund (IBIT, UUP). Keep them in the bar because the pie
  shows them, but leave them out of every preset (0%) and let only Custom set them. That keeps the presets
  readable.
- **Per-account models for small accounts.** An 8-fund Equities bucket in a $20k account makes $1-2k
  positions. Suggest the builder lowers the default positions when the bucket is under $40k (GUESS: 1 position
  per $5k, minimum 4).

## Open questions
1. One running model per account (replace on new), yes?
2. "Keep as is" list per account, with a helper to pull in LT Hold names?
3. Cash bucket = `is_cash()` rows only (as the pie does), with short bond funds staying in Fixed Income?
4. Presets: confirm All-weather 30/55/7.5/7.5/0 and the Quad tilt (±25% on each bucket's Quad stance).
5. Add an account type (Taxable / IRA / Roth / HSA / 401k), used in v1 only for the taxable gain line and to hide
   trades for 401k?
6. "Whole book": preview only, never frozen?
- Data note: read-only database queries were blocked in this session (both attempts). All numbers are
  illustrative; Task 1 replaces them.

## Status
READY_FOR_DEV
