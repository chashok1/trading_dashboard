# TASK 154 — Nightly "win %" per technical step, shown in the Action popup

## Goal (plain English)
Each technical step (the numbered situations 1a..3s) should carry a track record: "when this situation fired in the past, how often did the stock go UP / DOWN over the next 3 days". A nightly job computes it, and the Action popup's "Technical steps" list shows it next to the step that fired for that stock. Display only. It must NOT change consolidated_action, trig_action or any rule.

## Reference implementation (read first)
The analysis was prototyped in a scratch folder (read-only reference, do not write there):
`C:\Users\chash\AppData\Local\Temp\claude\C--Ashok-Invest-Projects-trading-dashboard\1345be8b-a1af-471a-b4a4-57f09439c64f\scratchpad\`
- `backtest.py` = the engine (loads drv_tn_td_bb_rr + drv_quote + drv_rr + drv_cat_atomic_input + hist_td + hist_tw, classifies every stock-day into a chart id, computes forward returns). Port its logic; do not import from the scratchpad.
- `verdict.py`, `tbl.json` = how results were summarised. `technical_steps.html` = what each id means (titles).

## Step ids (stored code -> id)
- Step 1 `trend_trade_rule`: 3/4->1a, 0->1b, 1->1c (1d = bounce exception, rebuilt), 2->1e, -1->1f, -2->1g
- Step 2 `bb_rng_strk_rule`: 3,4->2a; 2->2b; 1->2c; 0->2d; -1->2e; <=-2->2f
- Step 3: broken support = (LRR - price) > 2 ATR -> 3a. Rising bands (bb_rng_strk_rule>=2) `bull_rr_action` 6->3b,5->3c,4->3d,3->3e,2->3f,7->3g,1->3h,-1->3i. Flat (rule 0/1) `not_bull_rr_action` 5->3j,-1->3k,4->3l,3->3m,2->3n. Falling (rule<0) same codes -> 3o,3p,3q,3r,3s.
- 1b, 1d, 3a are rebuilt from raw prices because stored flags (lrr_idx_eff, bounce_exempt, qe 0/5) exist only for recent days. Keep the rebuild exactly as in backtest.py.

## Rules the job must follow (these came from data-quality findings)
1. STALE FIX: drop dates where >90% of stocks have a price identical to the prior day (weekends/holidays/stale feed), and blank any stock-day whose price equals that stock's previous kept day. Without this ~35% of days look unchanged and results are wrong.
2. Horizons: 1, 2, 3, 4 days (MAIN, short term) plus 10 and 15 days (reference only). Forward return = price N kept-trading-days later / price now - 1, clipped to +-50%.
3. Per step store: n signals, n distinct stocks, % up and % down at each horizon (up = return>0, down = return<0, as a share of signals that have follow-up), n with follow-up per horizon. Also 3-day up/down split by the stock's outlook that day (drv_rr.outlook grouped Bullish incl. Light/Mild Bullish, Bearish incl. Mild Bearish, Neutral) and by Trade/Trend position (qe 3/4 above both, 1 above Trend below Trade, 2 above Trade below Trend).
4. Reliability flags: `few` when n < 30 signals; `thin` when < 30 distinct stocks. A percentage is only shown when not `few`.
5. Tag: "mostly UP" if up/(up+down) >= 55%, "mostly DOWN" if <= 45%, else "even" (3-day).
6. Percentages count signals (a stock firing several days counts several times) — keep it that way and say so in tooltips.

## Suggested design (change if the codebase suggests better; keep it small)
- New table `drv_signal_winrate` in `db/baseline.sql` (idempotent, `CREATE TABLE IF NOT EXISTS`): PK (step_id, horizon_days, split_key) with split_key like 'all', 'out:bull', 'out:bear', 'out:neu', 'pos:both', 'pos:trend_only', 'pos:trade_only'; columns n_signals, n_stocks, n_followup, pct_up, pct_down, computed_at, history_from, history_to. It is a history statistic, not per as_of_date, so it is replaced wholesale each run (note this against the "drv_* DELETE WHERE as_of_date" convention in a comment).
- New `etl/derive_signal_winrate.py` with `run()` + `python -m etl.derive_signal_winrate`. Use `tos_symbol` everywhere (CLAUDE.md rule 15), SQLAlchemy + psycopg v3, queries <= 965 bytes each.
- Schedule it nightly in `etl/scheduler.py` next to the other nightly job (the one that refreshes `ref_vlm_intraday_curve`); do not run it on every load. Log to `meta_derived_run` / scheduler log like its neighbours.
- Wiring to the popup: add the step id to what `etl/technical_why.py::technical_trail` returns for each stage that fired (look at how `drv_tn_td_bb_rr.tech_trail` and `drv_actionable.why_card` are built), then in the API/why-card builder join the win % from `drv_signal_winrate` (live join at read time is fine and avoids re-deriving daily). The popup is `web/actionable_pops.js::_actpopWhyCardHtml` (Technical stages section).
- Display next to each fired step, short plain English, e.g. `1c  ·  3 days: 48% up / 51% down (n=17,400)` with a small tag (mostly UP / mostly DOWN / even). If `few`: "too few past signals". Hover tooltip as a bulleted list (rule: rich tooltips must be bulleted): 1/2/4-day up %, 10/15-day reference, outlook split, Trade/Trend split, history date range, "counts signals, not distinct stocks". Palette: use existing CSS classes/vars, no new hexes.
- Bump the `?v=` cache-buster on any edited web JS (every web/*.html script tag).

## Acceptance
- Running `python -m etl.derive_signal_winrate` fills the table for all step ids that occurred; numbers for the sample ids match the prototype within rounding when run on the same data. Reference 3-day (up/down): 1a 50/49, 1b 44/56, 1c 48/51, 1d 41/58, 1e 54/46, 1f 54/45, 1g 52/48, 3a 38/62 (54 signals, only 10 stocks), 3c 47/53, 3e 55/45, 3h 56/43 (history grows daily so small drift is expected; the date range must be ~163 real trading days, 2 Feb to 22 Oct 2026, ~1,100 stocks).
- Idempotent: running twice gives the same rows.
- The Action popup shows win % next to each fired technical step; no change to any action value (diff drv_actionable consolidated_action/trig_action before vs after = identical).
- Task-acceptance tests only under `tests/acceptance/` marked `@pytest.mark.acceptance` (CLAUDE.md #18); a small pure-Python unit test for the stale-fix and tag logic is welcome under `tests/`.

## Constraints
- NO git commit/push. LF line endings (write with newline='\n'; check `git diff --stat`). Verify edited Python with `ast.parse`, JS with `node --check`.
- No external side effects: no real emails, no network calls, no files outside the project folder. Do not run the full pytest suite for the UI part; run only tests you add/affected.
- Do not touch existing rules, thresholds or the existing technical-step logic in `etl/derive.py` (it has uncommitted edits from another task — leave them alone).
- Write a short `DEV_HANDOFF.md` entry (plain English first) when done and end with `ALL_DONE`.
