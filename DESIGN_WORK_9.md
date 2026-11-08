# DESIGN_WORK — Round 8: "Set it and forget it" Portfolio Builder (design only, no app code)

## What the user wants (their words, lightly cleaned)
"I need a way to set up my portfolio based on quad factors, risk factors, low volatility, beta, etc., using a time
horizon (monthly, quarterly, yearly...). I should be able to simply choose something (factor based, fixed income,
equities, bonds, foreign currency, whatever factor I can think of), get a portfolio, and not touch it for the
period I picked. Do your best."

The user reads plain English first (business-analyst sentences, technical detail only on request). Screens use full
page width. Tooltips are bulleted lists, never flat middot strings.

## Your job
Design the feature end to end and write `DESIGN_SPEC_<next n>.md` for the developer. The main Claude session will
review your spec with the user and send back changes, so: lead with a one-page plain-English summary, list the open
questions that need the user's decision (max 6, each with your recommendation), then the detail. Expect 2+ rounds.

## Questions the design must answer
1. **The user's flow.** Pick a horizon (1M / 3M / 6M / 12M), pick a "recipe" (one or several blended), set size /
   cash, see a proposed portfolio, accept it. Then it is frozen until the horizon ends. Sketch the screen(s) (ASCII
   wireframe is fine) and where it lives in the nav.
2. **Recipes / factors to offer.** At minimum: Quad-regime aligned (use current Quad and the quad-transition risk),
   Low volatility, Low beta / defensive, High beta / offense, Momentum (Hedgeye signal + trend), Income / yield
   (dividends), Fixed income (duration / credit), Equities by sector/style, FX / currencies, Commodities / gold,
   Balanced "all-weather". Say which are buildable NOW from data we already hold, which need a new feed, and which
   to drop. Propose how recipes blend (e.g. 60% Quad + 40% Low-vol) without becoming confusing.
3. **How a recipe becomes a portfolio.** Universe, ranking/scoring, number of positions, weighting (equal, inverse
   volatility, risk parity, capped), per-position and per-sector caps, minimum liquidity, how cash is treated,
   how the Risk Dial size multiplier is respected. Keep it simple and explainable: every position must carry a
   one-line "why it is here".
4. **The holding period.** What "don't touch it" means: fixed target weights until the end date; what (if
   anything) may override early (e.g. a stop / Quad flips / data failure) — default should be NO tinkering, with a
   clearly separate, opt-in "alert only" tripwire. Define the end-of-period review: rebalance proposal, carry or
   change recipe.
5. **Fit with the user's real book.** The user holds real positions in `hist_cs` / `hist_f`. Decide: is this a
   separate *model portfolio* tracked on paper, a target the real book is compared to ("drift" and "trades needed
   to match"), or both? Recommend one. Show how it avoids clashing with the Actionable screen's Final Call (the
   builder must not silently contradict it — show conflicts).
6. **Tracking and honesty.** Show model-portfolio return vs SPY and vs the user's own book over the period; hit
   rate vs what the recipe promised (e.g. did Low-vol actually have lower realized vol?). Include a back-test
   preview before the user commits ("this recipe over the last N months would have...") — say how, and how to avoid
   look-ahead bias, and what history we really have (be honest if it is too short).
7. **Data and storage.** Which existing tables/screens feed it (read, do not guess: `docs/quad_design.md`,
   `docs/quad_money_design.md`, `docs/market_state_factor_sss_design.md`, `docs/dashboard_cockpit_design.md`,
   `docs/macro_areas_design.md`, `etl/derive_risk_dial.py`, `drv_category_perf`, `drv_market_stat`, `drv_symbol_tier`,
   `drv_technicals`, `drv_outlooks`, `hist_quote_daily`, the existing Portfolio screen `web/portfolio.*`). Propose new
   tables (`ref_*` for recipes, `drv_*`/`hist_*` for frozen portfolios + daily marks), the derive step, and API
   endpoints, following CLAUDE.md conventions (tos_symbol in all drv_*, idempotent derives, schema in
   `db/baseline.sql`, seeds in `db/seeds_*.sql`).
8. **Phasing.** A smallest-useful v1 (one afternoon of dev per task, numbered TASK-sized slices) and what waits for
   v2. Prefer v1 = Quad + Low-vol + Low-beta + Momentum recipes, paper-tracked, with drift vs real book.

## Ground rules
- Research and design only. Read-only SELECTs are allowed; do not change application code, tables, or settings.
- Verify what data really exists (row counts, date ranges, columns) before promising a recipe depends on it.
- Do not give investment advice claims; the tool applies the user's own chosen factor rules mechanically.
- Be concrete: formulas for scores/weights, example output for today's data with ~10 positions, edge cases (symbol
  missing from TOS, stale data, a held symbol that the recipe excludes).
- Use plain English first, as above.
