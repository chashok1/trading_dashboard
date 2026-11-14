# DESIGN_WORK — Round 16: Builder = activated plan + pick-and-track picker + Actionable warnings (design only, no app code)

## What the user wants (their words)
1. "I want to assign % in asset class, sectors, styles etc (current screen design). I can do this every day (no limit). then activate the plan."
2. "I buy based on my universe or existing rules (typically HE outlook) but I also want to add my own risky stocks but should not exceed my percentages based on the above plan. I may want to choose a list of stocks that I want to buy from the existing HE outlook universe and my risky stocks and want to set amounts."
3. "Once I start picking the stocks and amount, it should tell me what is left so I can pick or stop picking stocks."
4. Next step: "in actionable screen we will have warnings."
Earlier: user answered YES to "no override on money limits; change the plan instead". They said no fixed weekly dollar amount: limits are checked against the trades they pick / Actionable recommends.

## Context
`DESIGN_SPEC_15.md` (and 14) are the previous rounds; this round REPLACES their model. Read `DESIGN_WORK_15.md`, `DESIGN_SPEC_15.md`, `docs/portfolio_builder_logic.md`,
the current Builder (`web/builder.html`, `web/builder.js`, `etl/builder_*.py`, `api/routers/builder.py`) and the Actionable screen (`web/actionable.js`, `docs/actionable_logic.md`) as far as needed.
Visual walk-through the user already saw: https://claude.ai/artifact/NjzWgKKRNDHaHAYn639vPc (local copy: scratchpad `builder_how_it_works.html`). Keep what they liked: plain-English reasons, OK / Shrunk / Blocked, mix bars now vs after.

## Your job
1. **Plan with Activate.** Keep the current screen's way of assigning % by asset class, sectors, styles (check what the screen already does and reuse it). Plans are editable any day, unlimited drafts; only one is ACTIVE. Design Save draft / Activate / switch, and what "active" changes (only the checks and warnings; nothing trades).
2. **Picker.** A list to pick from: the Hedgeye outlook universe (what the existing rules/outlook say to buy) plus the user's own added risky stocks. User ticks names and types a dollar amount (and/or shares) per name and account. Decide how risky stocks are handled (recommended: its own "Risky" slice with a % cap in the plan, on top of class/sector/style %).
3. **"What is left" tally.** As the user picks and types amounts, a live panel shows what is left in each class / sector / style / Risky slice / account cash, and what is the most they can still add to a name, so they can keep picking or stop. Design the exact panel, what happens when an amount goes over (warn vs shrink vs block), and the order of picking.
4. **Actionable warnings.** On the Actionable screen, a buy that would break the active plan gets a plain-English warning on its row (and a tooltip as a bulleted list). Design where it appears, wording, how it relates to existing badges, and that it never changes the Final Call.
5. **Hard vs warn.** Recommended default: real money limits (account cash, cash floor, household cash target) BLOCK; drift against class/sector/style/Risky percentages WARN with the amount over and the most allowed. Decide and justify; flag it as an open question.
6. Drop what no longer fits from Spec 15 (fixed weekly amount, Builder-made buy list, 6-line cap) unless you see a reason to keep it; list "what changed vs Spec 15".
7. You MAY run read-only queries on the local trading DB (standing permission) for real numbers. No external calls.
8. Do not ask the user things you can decide. Max 5 open questions, each with your recommendation.

## Output
Write `DESIGN_SPEC_16.md`: one-page plain-English summary first (short business-analyst sentences, no jargon), open questions, "what changed vs Spec 15", then detail, mock-ups, files likely touched, task list (each task useful alone), `## Status`. Full page width; tooltips are bulleted lists, never flat middot strings. No application code changes.
