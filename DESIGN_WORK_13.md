# DESIGN_WORK — Round 13: "Factor Lab" (design only, no app code)

## What the user wants (their words)
"How can I check all factors at once, for example IV, MACD, RSI?" ... "Build the factor lab for all columns and
information that we see, based on the final action." Then: "why can't the designer come up with this based on existing
data points and decisions?" — so YOU design it from what the data and the code already hold; do not wait on the user
for things you can decide yourself.

The user reads plain English first (short business-analyst sentences, technical detail only on request). Lead the spec
with a one-page plain-English summary, then max 6 open questions (each with your recommendation), then the detail.
Screens use full page width. Tooltips are bulleted lists, never flat middot strings. No app code changes.

## The idea (from the main session, change anything that does not hold up)
A screen where the user picks a Final Call group (buy / sell / hold, or an exact code like BM, BMN, SA, SS) and then
adds ANY combination of the factors visible on the Actionable grid (IV, RSI, MACD, MACDH, volume/RVOL, Range position,
Technical code, PVV, MACRO, source, sector, style, which rules fired, held or not, price vs Trade/Trend line, etc.).
It shows how many past cases matched and how they did afterwards (5d / 10d / 20d, average AND median, win rate,
vs the baseline of the same Final Call group), always with the sample size and a plain "too few to trust" warning.
Plus a "which single factor helps / hurts most for this action" ranking and a one-line plain-English verdict.

## Your job — use what you already learned in Round 12 (DESIGN_SPEC_12.md and your scratch scripts q3–q7)
1. **Data inventory.** Which Actionable columns / information have usable HISTORY (so past cases can be rebuilt) and
   which do not (LIVE, Watch, LT conviction, etc. — say "no history yet", never fake it). For each usable factor: where
   the historical value lives (drv_actionable, drv_technicals, drv_cat_atomic_input, drv_tn_td_bb_rr, drv_pvv,
   drv_factor_snapshot, hist_*, ...), how far back it goes, and how to bucket it (reuse the bucket definitions the
   grid and the Technical rules already use; do not invent new cut-offs without saying so).
2. **Outcome definition.** Forward 5/10/20 trading-day return from which price (the anchor-date close in drv_ma?);
   how sells are scored (a fall = good); how to handle dividends/splits, missing prices, overlapping days (one stock
   firing 10 days in a row is not 10 independent samples — propose de-dup or clustering and say what it does to n).
   Fix or avoid the v_factor_scorecard baseline bug you found.
3. **The engine.** One nightly table (one row per stock per day: Final Call code + every bucketed factor + forward
   returns) rebuilt from history, and a query path for "any 1–3 factors AND-ed within a Final Call group". Say how
   many combinations are allowed and why (sample size vs false discoveries). Include a multiple-testing guard so the
   screen does not hand the user a lucky 8-sample "winner" — e.g. minimum n, confidence interval, out-of-sample
   split (earlier months vs later months), and a plain-English "do not trust" flag. Say how the lab avoids look-ahead.
4. **The screen.** ASCII wireframe, full width. Where in the nav. Factor picker (grouped the way the grid is grouped),
   the results panel, the single-factor ranking, saved views (maybe), how a result links back to the Actionable grid
   (e.g. "show today's stocks that match this combination" — a very useful bridge; design it).
5. **Plain-English output.** The verdict wording for strong / weak / too-few / contradicts-the-Final-Call cases.
6. **What it must NOT do.** It is research only: it never changes the Final Call, never trades, never feeds the score.
   State how it stays separate from the Entry label proposed in DESIGN_SPEC_12 and how the two can work together.
7. **Build plan for the developer.** Files (new etl module + table in db/baseline.sql, api router, web page, docs
   row in CLAUDE.md lookup index), order of work, a test strategy that follows the test-debt policy (behaviour/schema
   tests only), runtime/cost of the nightly job, and what is out of scope for v1.

## Constraints
- Database is read-only for you (`.venv/Scripts/python.exe`, `etl.db.session_scope`, SELECT only). Show the query
  result (date range, n) behind any number you quote.
- Anything that would change `consolidated_action` / the Final Call is out of scope; flag it if you find a need.
- Keep every cut-off data-backed or marked as a judgement call for the user.

## Deliverable
`DESIGN_SPEC_13.md` in the project root. When done, rename this file to `DESIGN_WORK_13.md`.
