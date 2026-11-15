# DESIGN_WORK — Round 17: REVIEW of the Builder screen (design only, no app code)

## What the user wants (their words)
"I want to pick an account, set asset class %s (total 100%), e.g. Equities 50%. Others optional, or I can set style, sector etc: IT 10%, high beta 10%.
Then I can pick the stocks to make up those percentages: one stock, a group of stocks (buy any of the similar ones, AAPL or MSFT), or no stocks at all.
In any case, when I start buying, ALL limits must be validated: if I buy high-beta stocks and reach 10%, or equities go above 50%, or IT above 10%, any factor, I must be notified.
I need a NATURAL way of choosing on the builder screen: pick an account (everything is by account), set limits, then pick stocks or not. The ONLY required feature is limits on asset class."
Also: look for REDUNDANT functionality on the screen, and check the SAVING functionality (save draft / activate / saved sets / freeze / portfolios).

## Context
Round 16 (`DESIGN_SPEC_16.md`) and its build (see "Plans per account, picks and the To do list" in `docs/portfolio_builder_logic.md`) are already largely built.
Read: `docs/portfolio_builder_logic.md`, `DESIGN_SPEC_16.md`, `web/builder.html`, `web/builder.js`, `web/builder_plan.js`, `etl/plan_check.py`, `etl/plan_store.py`, `api/routers/builder.py`.
The screen grew over rounds 9-16 and now has: Plan / To do / Build new / Portfolios tabs, mix presets, "Saved" sets (setSave/setOpen), Save draft / Activate / Turn off, Accept-and-freeze model portfolios with marks, Compare grids, Warnings card, Lists-to-choose-from, a names side panel with many filters, My stocks, To do block.

## Your job
1. Walk the user's wish above step by step against what the screen does today. For each step say: works / awkward / missing. Be concrete (which control, which file).
2. **Redundancy audit.** List every place the same thing can be done two ways or saved two ways (e.g. Save draft vs "Save as…" saved sets vs Accept/freeze; Plan tab vs the plan controls on the Build tab; To do tab vs the To do block; Preset vs typed Target; Build-new model portfolios vs the Plan). Decide: keep / merge / remove, with the reason.
3. **Saving audit.** What is stored where (user_plan draft/active, user_plan_pick, saved sets, user_model_portfolio, localStorage?). Can the user lose work? Is it clear what "saved" means? Are there silent overwrites, stale drafts, or things that save but never get used?
4. **Limit validation audit.** Do class / sector / style / beta limits truly get checked at buy time, and where is the user told (Builder To do, Actionable pills)? Gaps against "notify me when I hit 10% high beta / 50% equities / 10% IT".
5. Propose the simplest natural flow (pick account -> set class % (required) -> optional sector/style/beta -> optionally pick stocks/groups -> live "what is left" + warnings), as a short mock-up and a numbered, independently-useful task list ordered by value. Prefer REMOVING things over adding.
6. Do not ask the user things you can decide. Max 4 open questions, each with your recommendation. You MAY run read-only queries on the local trading DB. No external calls.

## Output
Write `DESIGN_SPEC_17.md`: one-page plain-English summary first (short business-analyst sentences, no jargon), then the walk-through, redundancy table, saving audit, validation audit, proposed flow, task list, `## Status`. Full page width. No application code changes.
