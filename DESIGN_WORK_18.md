# DESIGN_WORK — Round 18: REDESIGN the Builder screen flow so it is easy (design only, no app code)

## What the user wants
The Builder screen is clumsy. Redesign the flow so it is easy and natural. Their wish (unchanged): pick an account; set asset class % (total 100, Cash is a class; the ONLY required part); optionally sector / style / beta limits; optionally pick stocks, a "buy any one of these" group, or nothing; every limit is validated when buying and the user is told (near / over), on the Builder and on Actionable / the warning badge.

## Decisions already made by the user (do not reopen)
- NO paper model portfolios: remove the Accept/freeze models, Portfolios tab, back-test/Compare, marks and the model Warnings card from the screen. (Engine code deletion is a later step; design the screen without them.)
- Planned buys count against limits as soon as they have an amount, even with no Buy call today. State what happens to cash.
- One "Save plan" button replaces Save draft + Activate (decided earlier by default: yes) and sector/style/beta are ceilings only; asset classes show Room / On plan / Over.
- Every limit is a % of the WHOLE account (one basis).
- The save bugs (reload overwrite, picks leaking between accounts, date/Refresh clobbering edits, auto-filled amounts) are being fixed separately in code now; design so they cannot recur (e.g. an explicit "unsaved changes" state).

## Read first
`DESIGN_SPEC_17.md` (proposed 3-step flow, task list), `DESIGN_CRITIQUE_17.md` (critic's changes: reuse `web/builder_plan.js` pieces, "tell me" via the warning badge on every screen, "Near" for ceilings only, drop "Pause checks"), `web/builder.html`, `web/builder.js`, `web/builder_plan.js`, `docs/portfolio_builder_logic.md`.

## Your job
1. Produce ONE concrete screen design: layout (full page width), what is visible at each step, default state for a new account, what the user clicks in order, how unsaved changes show, how "what is left" updates live while picking, where near/over warnings appear. Include an ASCII mock-up of the screen in 3 states: (a) new account, only class % set; (b) limits plus picks with one group; (c) over a limit.
2. List every existing control/section and say KEEP / MOVE / REMOVE (include the names side panel filters, My stocks, Lists to choose from, Preset, Saved sets, Match my holdings, Show what's missing, Compare, To do block, Warnings card). Prefer removing.
3. Where the Actionable screen and the warning badge show limit problems, specify the wording (bulleted tooltips, plain English).
4. Task list in build order, each task useful alone, small enough for one session; mark which reuse builder_plan.js.
5. Max 2 open questions, each with your recommendation. No external calls. Read-only DB queries allowed.

## Output
Write `DESIGN_SPEC_18.md`: one-page plain-English summary first (short sentences, no jargon), mock-ups, KEEP/MOVE/REMOVE table, wording, task list, `## Status`. No application code changes.
