# DESIGN_WORK — Round 3: advice that stays right during the day (live trim / buy-back)

## Goal
Round 2 (`DESIGN_SPEC_2.md`) judged Friday 10/9 trades against Thursday-night advice. The user pointed
out the real problem: **Thursday-night advice goes stale during the day.** Example: TXG closed Thu
$77.28, hit $85.12 on Friday (+10%), the user trimmed near the top (sold 625 @ avg $84.05), and when
it came back down bought back 375 @ avg $81.25 (close $80.65). The user does this style of trade on
every stock with the same consistent rule. Design how the app should handle this.

**Design and research only. Do not change application code. The user has NOT approved any build.**

## Answers the user gave (treat as requirements)
1. **Sizes.** Min/max dollar amounts are already derived from percentages. Add an **account-level
   adjustment** (multiplier). Example: F-A is made aggressive at **200%** = double the normal amounts
   (e.g. min 4k instead of 2k). Today min/max is one number per stock for the whole household
   (`drv_actionable.target_min_dollar/target_max_dollar`, see `docs/actionable_logic.md`). Account
   names/short names are in `ref_accounts` (IRA = Schwab Rollover IRA ...892, F-A = Fidelity 249118149,
   F-M = Fidelity 261408079). Design how the per-account multiplier works and how the household
   number and per-account numbers relate. Say where the multiplier is stored and edited.
2. **When to trim during the day:** several signals together: price at the **top of its risk range**,
   **and/or** up more than some **standard deviation** of that stock's normal daily move. The user
   asks YOU to recommend the percentage / multiple, based on the user's own live trades.
3. **When to buy back:** after price falls from its peak and **stabilizes**, and the day action is
   BUY. The user suggests standard deviation, low volume since the peak, and price falling. You
   recommend the exact test.
4. **One consistent rule for all stocks** (no per-stock tuning).
5. **How the app should tell the user during the day** (screen banner vs alert/email vs both):
   recommend one, with reason. The existing 🔔 Watch feature (`ref_watch`, `etl/derive_watch.py`) and
   hourly Yahoo refresh (`etl/yahoo_fetch.py::fetch_hourly_quotes`, `etl/scheduler.py`) already exist;
   build on them where possible.

## What to do
1. **Find out what intraday data really exists** (read-only): what the hourly refresh stores and for
   how long (price only? day high/low? volume?), what `hist_y` sequences exist, what `drv_quote`
   holds. The buy-back test (low volume since the peak, stabilizing) may need data we do not save.
   If it is missing, say exactly what must be saved and propose the smallest way to do it.
2. **Calibrate the trim trigger from the user's real trades.** Use `hist_cst` and `hist_ft` (Fidelity
   ticker is in brackets at the end of `action`; ignore account 85911). For the sell legs of the last
   8+ weeks, measure how far above the prior close the sell happened in units of the stock's own
   normal daily move (e.g. 20-day standard deviation of daily returns) and where it sat in the risk
   range (`drv_rr` lrr/trr). Report the typical multiple and range position, and what share of
   "spike days" (stock up >= k standard deviations) the user actually trimmed. Recommend one
   threshold that is the same for every stock. Mark guesses as GUESS.
3. **Calibrate the buy-back trigger** the same way: for the user's buys that came after a same-stock
   sell within 1-5 days, how far below the peak / sell price, how long after, and what the price did
   next. Recommend one stabilization test using data we actually have.
4. **Staleness design.** Propose how Thursday-night advice becomes a **plan plus live adjustment**:
   what is written at night (target size per account, trigger prices) and what is re-checked hourly.
   Include: the advice must be **saved each hour** (a history) so trades can be scored against the
   advice that was live at the time, not rebuilt afterwards. Say what table/columns that needs.
5. **Re-check round 2's rules under this model** (R1 trim-to-max, R5 household-net scoring, "Chasing?"
   line, R3, R2, R4): which become part of the live layer, which change, which are dropped. Is the
   TXG round trip now "following the app"? Replay Friday's 10/9 trades (84 fills in 35 stocks) as
   far as the data allows and say how many would have been matched by the new live rules.
6. **Daily permanent report.** The user wants to run the Friday-style review every day. Describe what
   it needs (transaction files loaded same day, hourly advice history), the sections it should have,
   and whether it should be a screen, a generated file, or both. Design only.
7. Write `DESIGN_SPEC_3.md`: rules in plain words with numbers and edge cases, per-account
   multiplier, data needs, open questions, build order. Mark each item BUILD / NOTE-ONLY / DROP.

## Read-only data access
- Read-only Python (`sqlalchemy` + `psycopg` v3; settings in `config/settings.py`; never print the
  password). Run with `PYTHONPATH=.` from the project root. Use `PYTHONIOENCODING=utf-8`.
- Scratch scripts go in the scratchpad `designer` folder, not the project folder.
- No DB writes, no derives, no file loads, no network. Each SQL statement <= 965 bytes.
- Use `tos_symbol` for `drv_*` tables.

## Output
`DESIGN_SPEC_3.md` in the project root, normal spec format, plain English, bottom line first.
