# DESIGN_WORK — Friday 10/9 trades vs. our recommendations and rules

## Goal
I bought and sold stocks on **Friday 2026-10-09**. Find out which of those trades our system
had recommended (an action, a fired rule, a rule group, a cross-asset signal, an area verdict)
and which trades matched **nothing**. For the unmatched trades, work out why and how we could
add rules (or tweak existing ones) so the system would have flagged them.

This is an **analysis and report** task. Do thorough work. Do not change any application code.

## Who uses it
Me (the only user). I want plain English, short sentences, no jargon. Put the bottom line first.

## What to do
1. **List every trade on 2026-10-09**, all accounts (Schwab and Fidelity). Buys, sells, partial
   and full. Use the transaction tables (`hist_cst` Schwab, `hist_ft` Fidelity) and cross-check
   against position changes (`hist_cs` / `hist_f`, `drv_realized_gain`). Show symbol, account,
   buy/sell, shares, price, $ amount.
2. **For each trade, find what the system said before the trade** (as of the close on Thursday
   10/8, and what was showing on Friday 10/9 itself):
   - `drv_actionable`: `consolidated_action`, `trig_action`, `triggered_group_ids`, `source_actions`
   - Fired atomic/composite rules and rule groups (`drv_trig`, `docs/rules_logic.md`,
     `docs/rule_groups_logic.md`)
   - Cross-asset signals (`drv_cross_asset_signal`)
   - Area verdict for the stock's area (`drv_area_verdict`, `drv_driver_exposure`)
   - Hedgeye outlooks and source standing (`drv_source_standing`, `drv_outlooks`)
   - Buy tradability score, risk-range position (LRR/TRR), Quad fit
3. **Classify each trade** as one of:
   - **Matched**: system action agreed with my trade (say which rule/action).
   - **Opposed**: system said the opposite (say what).
   - **Silent**: nothing fired either way.
4. **For Opposed and Silent trades, explain why.** What was I probably reacting to (price near
   a range edge, news, a Hedgeye call, rebalancing, tax, cash needs)? Use only what the data
   shows; mark anything you are guessing as **GUESS**.
5. **Propose how to add them.** For each pattern you see, propose a concrete rule idea in plain
   words: the condition, the action, the data it needs, and an expected hit rate if you can
   estimate it from history (use `docs/rule_tuning_and_outcomes.md` and `v_rule_scorecard` for
   how we judge a rule). Say whether it needs a new rule, a threshold change on an existing one,
   or is not worth a rule (one-off, discretionary).
6. **Sanity check against history.** If cheap to do, look at the previous few weeks of my trades
   to see whether the 10/9 pattern is typical or a one-off, so we do not build a rule for noise.

## How to get the data (read-only)
- You may run **read-only** queries through Python (`sqlalchemy` + `psycopg` v3, settings in
  `config/settings.py`, password in `.env`; never print the password).
- Put any scratch scripts in the scratchpad directory, not the project folder.
- **Do not** write to the database, run derives, load files, or call the network.
- Keep each SQL statement at or under 965 bytes.
- Use `tos_symbol`, not raw `symbol`, for `drv_*` tables.
- Date logic: the derive anchor is `MAX(export_date)` in `hist_td`; `docs/derive_date_logic.md`
  explains it. Position files dated pre-open map to the previous market day, so check that
  Friday's trades are not showing under Thursday or Monday.

## What to hand back
`DESIGN_SPEC_<N>.md` (per your usual format), where:
- **Design** = the trade-by-trade report: a table (one row per trade) with the columns
  Symbol, Account, Side, $ amount, System said, Rule/source, Verdict (Matched/Opposed/Silent),
  Likely reason. Then a short summary: counts of Matched / Opposed / Silent.
- **Rules & numbers** = the proposed new or changed rules, each in plain words, with thresholds
  marked GUESS unless backed by data.
- **Open questions** = only real decisions for me.
- Add a `### Worth reconsidering` note if any proposed rule would be wasteful or noisy.

## Out of scope
- Writing or changing any code, rules, seeds or tables.
- Backfilling or re-deriving anything.
- Emailing, committing or pushing.
