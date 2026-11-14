# DESIGN_WORK — Round 15: Builder redesign, second opinion (design only, no app code)

## What the user wants (their words)
"Work with designer_Fable_5_2 on builder redesign. Review and propose changes or a more effective design based on my needs and wants."

Their needs, from Round 14: "Builder screen -> review the design. We can work in the improvements. Somehow I am spending so much time every day
looking at stocks and trading. I need to get out. I should be able to set the build and, based on that, guide me what
I should buy, and make sure I don't exceed the money (doesn't exceed the limits). Overall account mixture."

## Context
Round 14 already produced `DESIGN_SPEC_14.md` (status READY_FOR_DEV, nothing built yet). Read `DESIGN_WORK_14.md` for the original brief
and `DESIGN_SPEC_14.md` for that design. You are the second pair of eyes: do NOT just polish it.

## Your job
1. Review the current Builder (`/builder`: `docs/portfolio_builder_logic.md`, `web/builder.html`, `web/builder.js`, `etl/builder_*.py`,
   `etl/derive_model_portfolio.py`, `api/routers/builder.py`) and the Round 14 spec. Say plainly what is strong, weak, over-built or missing
   against the user's goal: spend minutes a week, not hours a day; get a short "what to buy" list; never overspend; see the overall account mix.
2. Propose a more effective design where you see one. Challenge the spec: is it too big? Are the 8 tasks the shortest route to the goal?
   What could ship first and already save the user time? Anything to cut?
3. Settle the tension about limits. The user said "make sure I don't exceed the limits", yet Round 14 made all limits soft ("warn but never block").
   Decide which limits should be hard (screen refuses) and which warn, and say why.
4. You MAY run read-only queries on the local trading DB (standing permission) so mock-ups use real account numbers, not made-up ones.
5. Do not ask the user questions you can decide yourself. Keep at most 5 open questions, each with your recommendation.

## Output
Write `DESIGN_SPEC_15.md`. Start with a one-page plain-English summary (short business-analyst sentences, no jargon), then open questions,
then a "what changed vs Spec 14" section, then detail. Full page width on screens. Tooltips are bulleted lists, never flat middot strings.
End with a `## Status` line. No application code changes.
