# Portfolio Builder logic

Screen `/builder`. The Builder is a **per-account planning screen**. It **never trades and never changes the Actionable Final Call**.
History: the first version (DESIGN_SPEC_9/10/11) built paper "model portfolios" you could freeze and track. That was removed on 2026-11-15
(no freeze, no daily marks, no back-test, no Compare, no Portfolios tab; tables dropped). Round 16-18 design notes: `DESIGN_SPEC_16/17/18.md`.

## Flow
Account -> asset class % (required, Cash is a class, adds to 100) -> optional sector / style / beta limits -> optionally pick stocks or
"buy any one of these" groups -> amounts -> **Save**. The **active** plan is the one the To do list and the Actionable "My plan" chip read.

A new account opens already started from its holdings (classes, held stocks, limits = holdings, so the bars are green). **Start from my holdings**
does the same on demand. All limits are a **% of the whole account** (one basis).

## Plans (per account)
- `user_plan_version` (`account_short`, `name`, `plan`): saved plans by name (default name `Plan MM-DD-YYYY`). `user_plan.active` is the ONE active
  copy (`active_name` says which), `user_plan_pick` holds its planned buys / ticked sells, `user_my_stock` is the user's own stock list.
- Buttons: **Save** (keeps the plan you are on), **Save as...** (copy under a new name, not active), **Activate** (saves and makes it the active plan),
  **Delete** (deleting the active plan stops the To do list and clears its planned buys). The dropdown ticks the active plan; the label says which is active.
- A plan stores asset class %, beta (low / middle / high / no beta known) / sector (equity sectors only) / style (incl. "No style tag") / Quad favored (Q1-Q4, money in names Hedgeye favours as Bull, any asset class) limits, picks (with amounts and buy-one-of groups) and the ticked lists.
- Saved edits, switching account and date change are guarded by an "unsaved" flag and confirms (`PL.dirty` in `web/builder.js`).

## Checking (pure maths in `etl/plan_check.py`, tests `tests/test_plan_check.py`)
- Planned buys count against the limits **as soon as they have an amount** (a Buy call is not needed: this is planning).
- Line states: asset classes Room / On plan / Over (Cash: Room / On plan / Short); sector, style, beta OK / Near (90% used, `NEAR`) / Over.
  On-plan band = the smaller of $500 and 0.5% of the account (`tolerance`). Both numbers are GUESSES in one place.
- Per planned buy: `max_add` = the smallest room among cash to spend, class, sector, styles, beta and the stock's own Max (from the existing amount
  rules `drv_account_size`: Min / Max / Unit); `binding` names the tightest; `suggest` = Min if not held, else one Unit, capped at `max_add`.
- Money BLOCKS or cuts a buy (account cash, `cash_keep` $1,000, the plan's Cash %); class / sector / style / beta only WARN. Nothing trades.
- There is **no top-bar warning** and no check message on save (decided 2026-11-15: the row bars already show where you stand).

## The screen build / preview
`POST /api/builder/preview` (`etl/builder_engine.py::build_positions`, `vs_account`) turns the typed picks into whole-share positions. A held stock whose
target is within half a share of its holding keeps the held shares and value, so "match my holdings" gives a gap of 0 (trade column says **Matched**).
`exposure()` in `etl/builder_data.py` gives % of the account per sector / style / Quad / beta (plus Middle beta, No beta known, No style tag rows). Beta and style lines count **equities only**, the same as `plan_check`; "No sector" is a guide (not saved, not checked).
Charts and grids sit in one collapsible panel; each section collapses too (remembered in the browser).

## Max $ and the starting Buy $ (2026-11-17)
`plan_check.room_for` (pure, tests in `tests/test_plan_check.py`) works out, for every stock in the picks grids (held or picked), **Max $**: the most that
still fits, counting every OTHER typed Buy $ (its own is taken back out): smallest room among cash to spend, class, sector, styles, beta, Quad and the
stock's own Max rule; rounded down to $100, never below 0; `binding` names the tightest. WARN-ONLY: the Buy $ box turns red when it is over Max $, nothing is cut.
A pick with no typed amount and no buy-one-of group gets `start` unless it is already held (held names keep their Max $ but never take the starting money before a new pick) (a Buy call is NOT needed: this is planning; picks with a Buy call are served first) = what still fits after the picks before it (first come, first
served in the order picked); the screen fills Buy $ with it (`autoAmt` in `web/builder.js`) until you type your own. Held names that are not picks only show Max $.
Two numbers (2026-11-18): **Max $** (`stock`) = the most this ONE stock can still be bought (its amount rule `drv_account_size` less what is held; an Equities name -- ETFs count as equities --
with no rule uses the account's usual rule, `plan_store.account_default_size`; other classes without a rule have none, shown as a dash) and **Bucket $** (`bucket`) = the room left in cash,
class, sector, style, beta and Quad after the other planned buys. `max` = the smaller; the starting Buy $ is that smaller number. The names list "Can pick" column shows `max`.
`POST /api/builder/preview` takes `plan` (the screen's limits and picks, auto amounts sent as 0) and returns `room` and `room_calls`. Typing a limit re-runs the preview.
The Room column (last column of each chart grid) = limit in dollars minus held; the Covered column = held up to the limit, as a % of it.
Not yet counted: sells ticked on the To do list (they free room in the To do list, not here). Class names in the picks grids are display-only short forms (`CLS_ABBR`).

## What a pick is worth (2026-11-19)
In the hand-picked build (`manual`) a pick without a typed % is sized as **what the account holds of it + its planned Buy $** (`amt`): held stocks are never scaled when a class target
goes up, so a bigger target leaves room for new stocks. A typed % still overrides it (that % of the class target dollars). "Allocate my holdings" / "Start from my holdings" only tick the
held stocks (no % shares are written). A class with a 0% target still shows its held picks. The Picks column and the class totals are therefore held + planned buys.
Note: `etl/` is not hot-reloaded by uvicorn (`--reload-dir api`): touch `api/routers/builder.py` or restart after an `etl/` edit.

## Files
| Piece | File |
|---|---|
| Tunable numbers, measures, recipes, area fill, mix, caps (PURE) | `etl/derive_model_portfolio.py` (`PB_PARAMS`) |
| Build / preview engine (PURE) | `etl/builder_engine.py` |
| Read-only loaders (funds, Quad mix, accounts, holdings, presets, source names, exposure) | `etl/builder_data.py` |
| Plan maths (PURE) | `etl/plan_check.py` |
| Plan storage, versions, picks, To do page data, Actionable plan check | `etl/plan_store.py` |
| API | `api/routers/builder.py` (`/api/builder/*`: accounts, presets, preview, asset-class, sources, source-names, plan/*, todo, plan-check, pick*, my-stocks*) |
| Page | `web/builder.html`, `web/builder.js`; nav item in `web/_common.js`; route in `api/routers/pages.py` |
| Tables | `ref_pb_universe`, `ref_pb_mix_preset`, `ref_account_keep` (read by the preview), `user_plan`, `user_plan_version`, `user_plan_pick`, `user_my_stock` (`db/baseline.sql`); seeds `db/seeds_portfolio_builder.sql` |
| Tests | `tests/test_plan_check.py`, `tests/test_model_portfolio.py` (pure functions, no DB) |

## Source pool (kept)
Tick Hedgeye lists (PS, GOANY, II, CALL, ETF, SSS, RR), HELD or MINE and their names appear in the names list (`GET /api/builder/source-names`,
bullish per `builder_data.source_bullish`). The names list filters by list, class, sector, industry, factor, Quad and symbol.

## Rules still in the engine (unchanged)
Quad mix over the holding period, area stance and `fill_areas`, `pick_in_area`, Quad tilt, Risk Dial trim, kept holdings, whole shares
(see the pure functions and tests). The Final Call is shown per name but never removes a pick.

## Removed 2026-11-15
Accept / freeze, daily marks (`drv_model_mark`, `drv_model_position_mark`), nightly `drv_pb_score`, back-test, Compare, end-of-period review, warnings card,
saved sets (`user_builder_set`), Portfolios list / detail views, the top-bar plan warning, and `etl/builder_store.py`.
`web/builder_plan.js` is an unused leftover from round 16 (not loaded by any page).

## Apply
`python -m db.init_db` (drops the removed tables), apply `db/seeds_portfolio_builder.sql`, set each account's type on Ref Data, restart the server
(`etl/` is not hot-reloaded).
