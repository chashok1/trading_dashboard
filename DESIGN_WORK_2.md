# DESIGN_WORK — Friday 10/9 trades, round 2 (real transactions now loaded)

## Goal
Round 1 (`DESIGN_SPEC_1.md`) worked out Friday 2026-10-09 trades from **position changes**, because
the transaction files stopped at 10/1. I have now **loaded the 10/9 transactions** into `hist_cst`
(Schwab) and `hist_ft` (Fidelity). Redo the research on the real trades and tell me which
rules / fixes are still worth building.

Analysis and design only. Do not change application code.

## Who uses it
Me (the only user). Plain English, short sentences, bottom line first.

## What to do
1. **Re-list every trade on 2026-10-09** from `hist_cst` and `hist_ft` (all accounts), with real
   fill prices. Note: Fidelity rows have `tos_symbol` NULL; the ticker is in brackets at the end
   of `action`, e.g. `YOU BOUGHT ... (TXG) (Cash)`. Ignore the 401k funds (account 85911).
   Show per stock and account: gross shares bought, gross shares sold, average buy price, average
   sell price, net change.
2. **Compare with round 1.** Round 1 saw only net position changes. Real transactions show same-day
   **round trips** (e.g. Schwab TXG bought 200 and sold 300; ILMN bought 25 and sold 50; IGV sold
   64 and bought 75; NET, TEAM, MSFT mixed). Say which round-1 conclusions change:
   - R1 "trim over-max positions on strength": does it still catch the sells? Check the trade
     was a real net reduction, not an in-account shuffle.
   - R2, R3, R4, the look-ahead scoring bug, the area gaps (CRAK, BLOK, HOOD) and the
     "Chasing?" idea: keep, change or drop, with one line of reason each.
3. **Fill-price quality.** For each stock, compare my fill with Friday's close and with the day's
   range if `hist_*` has it. Did I buy near the day's high / sell near the day's low? Does that point
   to a useful rule (e.g. warn on buying more than X% above prior close)? Mark guesses as **GUESS**.
4. **Account shuffles.** Several stocks were sold in one account and bought in another (Schwab vs
   Fidelity accounts). Decide whether that is rebalancing between accounts rather than a view on
   the stock, and whether the app should treat it as neutral. Propose how.
5. **Check how many of these trades were repeated recently.** Look at the previous 4 weeks of
   `hist_cst` / `hist_ft` for the same stocks: is trimming into strength and adding to
   Hedgeye-Bullish names a habit (worth a rule) or a one-off?
6. **Write the spec** (`DESIGN_SPEC_2.md`): final rule list with plain-words conditions, numbers,
   evidence, edge cases, and the questions I still need to answer. Mark each rule
   BUILD / NOTE-ONLY / DROP, with a recommendation first.

## Read-only data access
- Read-only Python queries (`sqlalchemy` + `psycopg` v3; settings in `config/settings.py`; never print
  the password). Run scripts with `PYTHONPATH=.` from the project root.
- Scratch scripts go in the scratchpad directory, not the project folder.
- No DB writes, no derives, no file loads, no network. Each SQL statement at or under 965 bytes.
- Use `tos_symbol` for `drv_*` tables. Recommendation as of Thursday close = `drv_actionable`
  where `as_of_date = '2026-10-08'`.

## Output
`DESIGN_SPEC_2.md` in the project root, in your normal spec format. Keep it tight.
