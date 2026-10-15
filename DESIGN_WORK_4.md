# DESIGN_WORK — Round 4: the sell side (protect money first)

## Goal
The user says **sells matter more than buys**: a missed buy costs an opportunity, a missed sell costs money.
Design the sell side of the app so it covers all four things the user worries about:
1. **Protecting profits** on winners.
2. **Cutting losses** on stocks that are falling.
3. **Staying within limits** (over a position's max).
4. **Concentration** in one sector / theme / area / asset class.

**Design and research only. Do not change application code. The user has NOT approved any build.**
Stay consistent with the DECIDED items in `DESIGN_SPEC_3.md` (per-account sizes from percent x account
value x multiplier, rounded to $1,000; one-unit trims with the existing REDUCE rule; over max goes
straight back to max; LIVE column on the Actionable grid like PVV; no email; plain SELL SOME is a
caution tag, not a block; nightly frozen plan + saved live checks).

## What the assistant already found (verify independently, tell us where you differ)
Held stock-days, Feb-Oct 2026, measured from the night the call was made (held names fell over the
next 5 days 54% of the time in this period, so it is a weak, falling sample):
- Night Final Call SELL ALL (n=313): fell next 5d 53%, 20d 52%. SELL SOME/STM (n=639): 50% / 56%.
  HOLD: 55% / 56%. Stop breached (n=542): 55% / 56%. So the app's existing SELL calls showed **no edge**
  at spotting declines.
- **Over max (n=634): fell 53% (5d) / 66% (20d), avg -0.6%.** Over max AND up >= 1.5 SD that day (n=33):
  58% / 68%, 20d avg -1.4%. This is the only sell-side signal that stood out.
- Held names down >= 2 SD on the day (n=109) **rebounded**: next 5d avg +0.9%; with the stop also
  breached (n=47) +1.7%. So "sell after a big drop" would tend to sell the low.
- Spike days (up >= 1.5 SD) do not predict a fall by themselves; the trim is a swing trade.

## What to do
1. **Audit the existing sell machinery.** Which sources / rules / rule groups produce SELL ALL, SELL
   SOME, REDUCE, REMOVE, stop-breached, `SA/SS/STM/SW` Final Call codes (see `docs/actionable_logic.md`,
   `docs/rules_logic.md`, `docs/rule_groups_logic.md`, `etl/derive_actionable.py`)? Use
   `v_rule_scorecard` / `docs/rule_tuning_and_outcomes.md` (direction-adjusted edge) to say which sell
   rules have a positive edge and which do not. Recommend KEEP / DEMOTE (show as lower-confidence) /
   DROP for each. Say how many held stock-days each fires on so the effect is clear.
2. **Classify the user's own sells** (last 8+ weeks, `hist_cst` + `hist_ft`; Fidelity ticker is in
   brackets at the end of `action`; ignore account 85911; household net per stock per day) by reason:
   over max, spike trim, profit-take on a gain, loss-cut, concentration/theme trim, full exit. Measure
   what happened after each kind (5d / 20d, and the round trip when a buy-back followed). Use
   `hist_cs` (`cost_basis`, `gain_pct`) and `hist_f` (`cost_basis_total`, `total_gl_pct`) to know gain
   or loss at the time of the sell. Which kinds were worth it? Which were noise?
3. **Profit protection.** Test simple, same-for-every-stock candidates: give-back from the peak since
   purchase or since the 20d/60d high in normal-move (SD20) units; touching the top of the risk range
   (TRR) with a large gain; gain >= X% with price falling back through the trade line. For each, report
   how often it would fire, what happened next, and what it would have saved or cost versus holding.
4. **Loss cutting.** The assistant's test says stop-based and big-drop sells rebound on average. Test
   what actually separates falling-knife losses from rebounds (trend line break, below LRR, breadth,
   outlook flip, volume). Is there any loss-cut rule with positive edge? If not, say so and recommend
   keeping the existing stop as a warning only. Do not invent a rule that the data does not support.
5. **Limits.** Confirm and finalize T2 (over max back to max) as the lead sell signal: thresholds,
   how far over max, per-account behavior, how it relates to the 2x-max leg. Is "how far over max"
   predictive (1.0-1.25x vs 1.5x vs 2x+)?
6. **Concentration.** How are sector / area / theme / asset-class exposures available today
   (`drv_actionable.sector`, `asset_class`, `drv_area_verdict`, `drv_driver_exposure`,
   `docs/area_driver_rules_logic.md`, `ref_asset_allocation`)? Design a simple, consistent concentration
   check (for example household exposure of one sector, area or theme above a percent of the
   portfolio, or a combined position in correlated names such as TXG/NET/MSFT/...). Use history to say
   whether concentration breaches preceded drawdowns. If there is no edge, make it a NOTE-ONLY tag.
   Be explicit about which dimension to use first and why.
7. **Fit into the LIVE column.** Propose which sell signals appear there (badge names, colours, tooltip
   bullets, rank order so the most important sell sorts first), how they relate to the existing ACTION
   column Final Call, and the expected signals per day. Keep the total manageable (the user already
   said ~22-27 badges a day was too many).
8. **Replay Friday 10/9 sells** under the final sell design: of the 13 net sells (~$95k) how many are
   matched, which are not, and what would the new signals have said about the stocks the user did NOT
   sell (for example anything over max or concentrated that Friday).
9. Write `DESIGN_SPEC_4.md`: plain words, bottom line first, rules with numbers, evidence strength
   (strong / weak / none), edge cases, open questions, build order. Mark each item BUILD / NOTE-ONLY /
   DROP with a recommendation first. Be honest where the data shows no edge. The sample is a falling
   market; say how much that limits each conclusion.

## Read-only data access
- Read-only Python (`sqlalchemy` + `psycopg` v3; settings in `config/settings.py`; never print the
  password). Run with `PYTHONPATH=.` from the project root, `PYTHONIOENCODING=utf-8`.
- Scratch scripts go in the scratchpad `designer` folder, not the project folder.
- No DB writes, no derives, no file loads, no network. Each SQL statement <= 965 bytes.
- Use `tos_symbol` for `drv_*` tables.

## Output
`DESIGN_SPEC_4.md` in the project root, normal spec format. Keep it tight.
