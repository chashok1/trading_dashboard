# DESIGN_WORK — Round 5: "Today's actions" — act only on what is required, ignore the noise

## Goal
After four rounds of research (`DESIGN_SPEC_2.md`, `_3.md`, `_4.md`) the app will emit many signals: trim,
trim-to-max, strong/light dip-buy, buy-back, WAIT, chasing tags, LOW CONF sells, cautions, plus the existing
Final Call. About 16 visible badges a day (23-28 with the Light chip). The user says:
**"I need precise action to take for a given day ... how I can just act on the ones that are required (not on
noise signals)."**
Design a short, ranked, per-account **"Today's actions" list** that tells the user exactly what to do on a
given day, and which signals can be safely ignored. Mark everything else clearly as optional or info only.

**Design and research only. Do not change application code. Nothing in this brief is approved to build.**

## Principles (from the user)
- Sells matter more than buys: a missed sell costs money, a missed buy only an opportunity.
- The user trims on strength and buys back; they hold ~42 stocks across IRA (Schwab), F-A and F-M (Fidelity).
- Plain English. Short. Bottom line first. Tooltips are bulleted lists, never one flat line.
- No email. Everything lives on the Actionable screen. Full width. No duplicate chips/pills.

## What to do
1. **Value of acting.** For every signal type (T1 spike trim, T2 trim-to-max at 1.25x/80% range/up 1 SD,
   existing kept sell sources PS/II/CALL/RTA/SSSCHG/Technical SELL ALL and SELL SOME, strong dip-buy 1.5 SD,
   light dip-buy 2.0 SD, buy-back, starter positions, stop-breached) estimate what acting is worth versus doing
   nothing: hit rate, average effect after 5 and 20 trading days relative to the same-day baseline, and the
   dollar value of a typical action using realistic sizes (one unit, back-to-max, starter at min). Use the
   history (Feb-Oct 2026) and say how much the falling-market sample limits each number. Separate:
   - **Risk control** (staying within limits, avoiding a big concentrated loss): worth acting on even if the
     expected gain is small.
   - **Opportunity** (dip-buys, starters, buy-backs): optional.
   - **Noise** (no measurable edge, tiny dollars, or contradicts another signal).
2. **Tiers.** Propose three tiers with a one-line reason each:
   **MUST DO TODAY**, **CONSIDER**, **IGNORE / INFO**. Put each signal type in a tier and justify with the
   numbers from step 1. Set a **daily budget** (for example at most N must-do actions) and say what happens
   when more signals fire (ranking and cut-off rule).
3. **Materiality.** Using the user's own trade sizes (`hist_cst` / `hist_ft`, account 85911 excluded, household
   net per stock per day) and account sizes, propose a minimum action size below which an action is not worth
   listing (in dollars and/or percent of the account), per account. Show how many of the user's real trades fell
   below it.
4. **Conflicts and consolidation.** Define one action per stock per account per day: how to merge a trim and a
   dip-buy on the same stock, a sell signal with a caution, signals in several accounts (which account first;
   use the "biggest dollar gap to min" idea already in spec 3 for starters; for trims, which account holds the
   excess), and the rule when the Final Call (ACTION column) disagrees with a live signal. Spell out
   precedence in a small table.
5. **Exact wording.** The list should read like orders: "SELL 120 TXG in IRA (back to max, $17k)", with the
   limit/line price when relevant, the reason in four words, and the confidence. Draft the wording for each
   signal type. Also define the quiet state: "No required actions today" and a "Why nothing" line.
6. **Where it appears.** On the Actionable screen without adding clutter: propose the least intrusive place
   (for example the top of the LIVE column sort, a single "Act (N)" filter chip next to "Live (N)", and one
   collapsible list at the top). Study `web/actionable.js` / `.html` and `docs/pvv_logic.md` §7 for the column /
   chip patterns and the existing colour tokens. Recommend one design, say what it replaces or merges with from
   spec 3 (the LIVE column and the "Live (N)" chip) so we do not duplicate anything.
7. **Replay.** Replay the last ~20 trading days (at least 10/1-10/9, and Friday 10/9 in detail) as far as the
   data allows: how many MUST DO and CONSIDER actions would the list have shown each day, how many of the
   user's actual trades would it have covered, which required actions the user did NOT take and what happened
   afterwards, and which of the user's trades would have been in IGNORE. Friday 10/9 detail: list the exact
   actions the list would have shown.
8. **Write `DESIGN_SPEC_5.md`**: bottom line first, tier table, budget, materiality, precedence table,
   wording, placement, replay results, open questions (only real ones), and a build order that slots into the
   consolidated build plan at the end of `DESIGN_SPEC_4.md` (say which phase it extends or replaces). Mark each
   item BUILD / NOTE-ONLY / DROP with a recommendation first. Be honest where the numbers do not support a
   tier.

## Read-only data access
- Read-only Python (`sqlalchemy` + `psycopg` v3; settings in `config/settings.py`; never print the password).
  `PYTHONPATH=.` from the project root, `PYTHONIOENCODING=utf-8`.
- Scratch scripts in the scratchpad `designer` folder, not the project folder.
- No DB writes, no derives, no file loads, no network. Each SQL statement <= 965 bytes.
- Use `tos_symbol` for `drv_*` tables.
- A developer is building Phase 0 and Phase 1 in the project right now (`AGENT_WORK.md`); the DB and files may
  change under you. Do not touch code, specs 2-4 or the task files.

## Output
`DESIGN_SPEC_5.md` in the project root, normal spec format. Keep it tight.
