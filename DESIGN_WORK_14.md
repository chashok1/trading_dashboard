# DESIGN_WORK — Round 14: "Builder as autopilot guide" (design only, no app code)

## What the user wants (their words)
"Builder screen -> review the design. We can work in the improvements. Somehow I am spending so much time every day
looking at stocks and trading. I need to get out. I should be able to set the build and, based on that, guide me what
I should buy, and make sure I don't exceed the money (doesn't exceed the limits). Overall account mixture."

The user reads plain English first (short business-analyst sentences, technical detail only on request). Lead the spec
with a one-page plain-English summary, then max 6 open questions (each with your recommendation), then the detail.
Screens use full page width. Tooltips are bulleted lists, never flat middot strings. No app code changes.
Do not wait on the user for things you can decide yourself.

## The goal behind the request
Today the user watches stocks daily. They want to set a target build ONCE (how much in Equities / Fixed Income / Gold /
Commodities / Crypto / Currency / Cash, and how it is split inside), then have the screen tell them, in a few lines,
"what to buy (and what to trim) to get back to the build", with hard guard-rails so they can never overspend. The aim is
to check this a few minutes a week, not stare at stocks every day.

## Your job
1. **Review the current Builder** (`/builder`). Read `docs/portfolio_builder_logic.md`, `DESIGN_SPEC_9.md`, `_10`, `_11`,
   `web/builder.html`, `web/builder.js`, `etl/builder_engine.py`, `etl/builder_store.py`, `etl/builder_data.py`,
   `api/routers/builder.py`, plus the Portfolio screen's pie/holdings and the Actionable screen only as far as needed.
   Say plainly what works, what is confusing, what is missing for the goal above. Think about the daily-time problem:
   which parts of today's flow make the user hunt, and which could be one glance.
2. **"Set the build" as a standing target** (not only a one-time freeze of a model). Design how the user saves a target
   mix per account AND for the overall household (all accounts together), with the limits they care about:
   per-bucket min/max, per-fund cap, per-sector cap, cash floor, max spend per day/week, max new money per account.
   Decide what is a hard limit (can never be exceeded, the screen refuses) and what is a warning.
3. **"What should I buy" guide.** From the standing target + current holdings + cash available, produce a short,
   ranked shopping list: buy X shares of Y in account Z, trim A, with the reason in one plain sentence, the dollars,
   and the resulting mix. It must (a) never exceed available cash (per account, and no cross-account cash moves unless
   stated), (b) never break a limit, (c) respect kept holdings and the account types already in the repo, (d) show
   "before vs after" mix and a check-list of limits that passed. Decide how it uses the existing signals (Final Call
   is information only in the Builder per the 2026-10-27 rule - keep that unless you can justify a change and flag it
   as an open question), Quad mix, Risk Dial, source pools, drift.
4. **Overall account mixture.** A household view: combine all accounts, show current vs target by asset class and by
   area, which account is best placed to buy each thing (tax/account type if the repo already knows it; otherwise say
   it does not and do not invent), and how to avoid buying in one account what is already over in another.
5. **Reduce the daily-time burden.** Propose the minimum routine: e.g. a "This week" card (green = nothing to do /
   amber = N small buys), an optional email/notification digest (the repo already has `etl/notify.py` and the watch
   digest pattern - reuse, do not add outside services), and drift alerts only when a limit is near. Say what the user
   can STOP checking.
6. **Layout.** Mock the page with ASCII or a table: the first screen the user sees must answer "do I need to do
   anything?" in one glance. Keep the existing flow reachable (account -> period -> mix -> split -> accept) but say what
   moves, what is renamed, what is removed. Reuse existing endpoints/tables where possible; list new tables/endpoints
   needed, with column lists, and any seeds. Nothing may trade automatically; the Builder never changes the Final Call.
7. **Build plan.** Split into small tasks (TASK-sized, each independently shippable and testable), in order, with
   acceptance checks that assert behaviour (limits cannot be exceeded; shopping list sums <= cash; before/after mix adds
   to 100%). Note which parts are pure functions testable without a DB.
8. **Risks.** Things that could make the guide wrong or unsafe (stale prices, splits, unmapped holdings, whole-share
   rounding, cash that is already committed, pending orders the repo cannot see). State how each is handled.

## Deliverable
`DESIGN_SPEC_14.md` in the project root. Do not edit app code. When done, rename this file to `DESIGN_WORK_14.md`.
