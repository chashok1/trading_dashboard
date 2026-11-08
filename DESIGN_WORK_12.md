# DESIGN_WORK — Round 12: Tradability Score vs Final Call vs Trade / Trade2 (analysis + proposal, no app code)

## What the user wants (their words)
"Look into the tradability score from the overall picture (final action, Trade(2) views) and also double dipping
too. Same factors are going into the Final Call and the score. Do a comprehensive analysis and propose."

The user reads plain English first (short business-analyst sentences, technical detail only if asked). Lead your spec
with a one-page plain-English summary, then the open questions (max 6, each with your recommendation), then detail.
The main session will review it with the user; expect 2+ rounds. Do NOT change application code.

## What triggered it (a live example, 2026-10-28)
TXG (held): Final Call BUY MORE (winning source TOP5, Technical BM, MACRO HOLD) passes the basic Trade buy test but
sits in **Trade2** because its Tradability Score is below 12. Why it scored low: price is ~54% of the way up the Risk
Range (no LRR points, and LRR is 10x weighted), IV is 1.17x its own 63-day average (-3), and MACRO is HOLD with a
conflict (so no full 3-way agreement). So a stock the Final Call says BUY MORE is shown to the user as "not clean".
The user wants to know whether that is coherent, and whether the same evidence is being counted twice.

## Where to look (read these, do not re-derive from scratch)
- Score: `web/actionable_pops.js` — `_buyTradabilityScore`, `_lrrProximityScore`, `_rawRrPos`, `_ivRatioScore`,
  `_sourceTrackRecordScore`, `_factorWinRateDelta`, `_buyAgreementSubTier`, `_tradabilityBreakdown`,
  `_TRADABILITY_BADGE_MIN` (=12), `_ENTRY_RIPE_TECH`. Header comments hold the history and the user's earlier asks.
- Trade / Trade2 gates: `web/actionable.js` — `_isTradeModeQualifyingBuyLoose`, `_isTradeModeQualifyingBuy`,
  `_isTradeModeDiffBuy`, `_matchesTradeMode`, `_matchesTradeModeDiff`, `_isTradeModeHeldSell`, `_isFixedIncome`.
- Default sort / tiers: `web/actionable.js` — `_computePriority`, `_buyNoiseGated`, the Watchlist band, the 🎯 badge.
- Final Call: `etl/derive_actionable.py` (`_compute_final_call`, winner pick, trig_action), `etl/derive_outlook_action.py`,
  `etl/derive.py` (Technical Pass 1/1b/2), `etl/technical_rules.py`, `etl/technical_why.py`, `etl/why_card.py`.
  Docs: `docs/actionable_logic.md`, `docs/actionable_playbook.md`, `docs/rule_tuning_and_outcomes.md`.
- Evidence tables/views: `v_factor_scorecard`, `v_source_edge_scorecard`, `v_final_call_scorecard`,
  `v_agreement_scorecard` (reported EMPTY in the code comments — verify), `drv_factor_snapshot`, `drv_signal_winrate`,
  `drv_rule_outcome`. You may read the database (read-only) with `.venv/Scripts/python.exe` + `etl.db.session_scope`.
  Do not write to it.

## Questions the analysis must answer
1. **Inventory.** For one BUY row, list every input that reaches (a) the Final Call, (b) the Tradability Score,
   (c) the Trade/Trade2 gates, (d) the default sort. One table: factor × where it is used. Include Technical
   (rr_action, Range position / LRR-TRR, Trade/Trend lines), the winning source and its track record, MACRO,
   PVV, RSI, RVOL, IV, stop, agreement, asset class / macro-instrument flag.
2. **Double dipping.** Where is the same evidence counted more than once? Examples to test (not exhaustive):
   Technical code is a Final Call driver AND +2 in the score AND a Trade gate AND part of Agreement; LRR/Range
   position is inside Technical Step 3 AND the score's dominant 10x term; the winning source drives the Final Call AND
   its win rate is a score term AND Agreement counts Sources again; MACRO is a Final Call input AND a Trade veto AND
   Agreement; PVV AVOID is a Strict veto AND may feed other places. For each: is it a true duplicate (same
   information), a correlated-but-different view, or an intended confirmation? Quantify where the data allows
   (correlation between score terms and Final Call codes, how often a gate and the score reject the same row).
3. **Coherence of the three layers.** Final Call says BUY MORE, the score says "not clean", Trade2 says "buys Trade
   rejects". Is this the story we want the user to read? Count how many rows per day land in each outcome (BUY in
   Trade, BUY in Trade2, BUY in Watchlist, BUY nowhere) over the recent anchors, and what happened to them after
   (20d win rate / edge by bucket — use the scorecards; say plainly where the sample is too small).
4. **Does the score earn its weight?** The LRR term is 10x and decides most outcomes; agreement has "ZERO"
   validation rows per the code comments; the 12 cutoff was tuned to "top 15–20%". Does a high score actually
   predict better forward returns than the Final Call alone? Does Trade2 (score < 12) do worse than Trade, or just
   look different? If the evidence says no edge, say so.
5. **Options and a recommendation.** At least three, e.g.: (A) keep as is, document it; (B) remove double-counted
   terms from the score so it measures only what the Final Call does not already say (entry quality / timing);
   (C) turn the score into an entry-quality label shown beside the Final Call and stop using it as a hard Trade2
   gate; (D) fold the useful pieces into the Final Call and retire the score; (E) rename/reshape Trade vs Trade2 so
   the split means something the user can act on (e.g. "buy now" vs "buy on a pullback"). For each: what changes
   on screen, what changes in code (files), risk, and what the user gives up. Recommend one and say why.
6. **Display.** Whatever you recommend, how does the user read it? The Action popup, the 🎯 badge, the Trade /
   Trade2 buttons and the legend text must tell one consistent plain-English story. Sketch the popup/legend wording
   (ASCII is fine). Tooltips are bulleted lists, never flat middot strings.

## Constraints
- Informational/advisory only changes unless you clearly flag a change to what the Final Call or `consolidated_action`
  would be — those need explicit user approval.
- Screens use full page width. Keep the CLAUDE.md rule that CLAUDE.md stays an index (details go in `docs/`).
- Keep every threshold you propose data-backed or clearly marked as a judgement call the user must make.
- If a number needs a database query, run it yourself and show the query result in the spec (date, sample size).

## Deliverable
`DESIGN_SPEC_<next n>.md` (next free number is 12) in the project root. When done, rename this file to
`DESIGN_WORK_12.md` as the previous rounds did.
