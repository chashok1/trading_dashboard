# Design Spec — DESIGN_WORK_13

## Goal
A Factor Weights table showing how much each Actionable column has really mattered for each Final Call group, with
the same evidence counted only once. It is for you, to judge which columns to trust. It is research only and never
changes a call.

## Design

### 1. Plain-English summary (one page)

**What you get.** One new screen, **Factor Weights**, found next to Performance.
- You pick a Final Call group: BUY, SELL, HOLD, or the exact codes BUY MORE and BUY TO MIN.
- It shows one row per column and value, for example "RSI = Oversold" or "Range = LRR zone". It covers every
  Actionable column that has past data.
- Each row says how much that value moved the result 5, 10 or 20 trading days later, **after allowing for all the
  other columns at once**. So if RSI and Range tell the same story, they share the credit instead of both getting it.
- Each row carries:
  - how many separate cases it is based on
  - a 90% range for the weight
  - a plain flag: **Trust (helps)**, **Trust (hurts)**, **No effect**, **Unstable**, **Too few**, or
    **Contradicts the call**
- A **Today (N)** link opens the Actionable grid filtered to today's stocks with that value.

**What the data says so far.** These are BUY calls from 11 May to 29 Sep 2026: 1,776 separate cases across 334
stocks, scored on the 20-day result against the median stock.
- **Helps a BUY:**
  - Price below its Trend line (a dip): about +3.7 points.
  - Price in the LRR zone: about +2.2 points.
- **Hurts a BUY:**
  - Price above TRR: about −1.7 points.
  - PS as the winning source: about −2.7 points.
- **No effect** (or too few cases):
  - RSI, MACD, MACDH, IV percentile, volume, Bollinger streak, held / not held, MACRO, and most sources.
- **SELL calls** (493 cases): nothing is reliable yet.

**No combined score yet.** You asked for a combined score only if it works on later months it was not built on. It
does not. We built it on earlier months and tested it on each following month (June to September):
- BUY: it ranked stocks the right way in 3 of 4 months and the wrong way in August.
- SELL: it was no better than chance.

So the deliverable is the weights table alone. The test re-runs each month by itself. A combined score appears only
once it passes.

**Two data problems found and fixed in the design.**
1. **The old "baseline" was wrong.** The current scorecard measures forward days by counting derive dates,
   weekends included (21 of 204 dates are weekends). It also counts frozen prices as losses: 8.9% of rows show a
   return of exactly zero. That pulled the all-stock win rate down to 46%. The real figure is about 51%. This is why
   nearly every RSI or volume value looked "better than baseline".
2. **One bad price can skew a whole day.** A few broken prices moved the day's average return by more than 3 points
   on 24 of 172 days. The new design compares each stock against the day's **median** stock instead, and drops
   impossible moves (over 100%) as data errors.

I re-checked the Round 12 conclusions the new way. They still hold: Trade did not beat Trade2, and the old score
still did not predict results.

**What it will not do.**
- Change the Final Call.
- Trade.
- Feed any score.

If you later want a trusted row to change something, that becomes its own approved spec (section 11).

### 2. Decisions for you (full list under Open questions)
1. Ship the weights table alone, with no combined score, and re-test it each month by itself? **Recommend yes.**
2. Exact-code tables only for BUY MORE and BUY TO MIN, the only codes with enough cases? **Recommend yes.**
3. Fit on 11 May onwards, when MACRO history starts? **Recommend yes.**
4. Switch the grid's RSI / IV edge tags to the corrected data after one week side by side? **Recommend yes.**
5. Rebuild "Technical step" history using today's (23 Oct) rules, clearly labelled? **Recommend yes.**
6. Accept the trust thresholds (at least 50 cases, at least 20 stocks, a 90% range that does not cross zero, and the
   same direction in both halves)? **Recommend yes**, as judgement calls.

### 3. Data inventory: which columns have history

Checked with read-only queries on 28 Oct 2026. "From" = first date with data. Buckets reuse the grid's or the
Technical rules' existing cut-offs unless marked.

| Grid column / info | Has history? | Where it lives | From | Buckets |
|---|---|---|---|---|
| Final Call code / side | yes | `drv_actionable.final_code / final_side` | 2 Feb 2026 (one stray 2025-01-01 date ignored) | the group itself |
| Held | yes | `drv_actionable.held_today` | 2 Feb | Held / Not held |
| Sources: winning source | yes | `drv_actionable.winning_source` | 2 Feb | each source (11) |
| Technical code | yes | `drv_tn_td_bb_rr.td_tn_bb_action_desc` | 2 Feb (rules changed 23 Oct) | BM / BS / BMN / SS / STM / SA / none |
| Technical step (S1-a … 3x) | stored only from 23 Oct; **rebuildable** with `etl/technical_rules.classify` (as `drv_signal_winrate` already does) | `drv_tn_td_bb_rr` inputs | 2 Feb (rebuilt) | step ids |
| RR: range position | yes | `drv_rr.lrr / trr` + price | 2 Feb | Below LRR / LRR zone 0–25 / Mid 25–60 / Upper 60–80 / TRR zone 80–100 / Above TRR (settings `range_lrr_zone_pct`, Technical's 60, `range_trr_zone_pct`) |
| Price vs Trade line | yes | `drv_technicals.a_trade_value` | 2 Feb | Above / Below |
| Price vs Trend line | yes | `drv_technicals.a_trend_value` | 2 Feb | Above / Below |
| Bollinger streak | yes | `drv_tn_td_bb_rr.bb_rng_strk_rule` | 2 Feb | Rising (≥2) / Flat / Falling (<0), the Technical's own |
| RSI | yes | `drv_technicals.rsi` | 2 Feb | Oversold / Neutral / Overbought (`rsi_oversold` / `rsi_overbought`) |
| MACD | yes | `drv_technicals.a_macd_brr` | 2 Feb | Up (>0) / Down |
| MACDH | yes | `drv_technicals.a_macdh_d_brr` | 2 Feb | Up (>0) / Down (the scorecard's existing bucket) |
| Vlm: RVOL + direction | yes | `drv_tw.w_vlm_expn_ratio` + `drv_quote.pct_change` | 2 Feb | the 3 existing buckets (`vlm_rvol_avoid_threshold`) |
| IV percentile | yes | `drv_technicals.iv_percentile` | 2 Feb | Low ≤30 / Mid / Elevated 70–90 / Extreme ≥90 |
| IV vs own 63-day average | **too short** | `drv_technicals.iv_ratio` | 14 Aug | <1 / 1–1.15 / >1.15. Added once it has 3 months of 20-day results (about late Dec) |
| PVV | yes | `drv_pvv.decision` | 2 Feb | each decision; WATCH (retired 16 Aug) is mapped to NO_ACTION |
| MACRO | yes | `drv_macro_score.macro_action` | **11 May** | SA / STM / HOLD / BS / BM |
| Sector / styles / asset class | today's label only | `ref_sector` | — | today's label applied to all history (labels rarely change) |
| Index / futures / FX flag, fixed income | today's label only | `ref_rrt`, asset class | — | yes / no |
| Earnings soon | yes | `drv_technicals.earnings_days` | 2 Feb | Within 7 days / Not soon (judgement: 7 days) |
| Rules (edge): a rule fired | yes | `drv_actionable.rules_engine_fires` | 2 Feb | on / off per rule. Only rules with ≥50 cases in the group (59 rules fired in Sept) |
| Stop signal | too few | `drv_actionable.stop_signal` | 12 Aug (614 rows) | covered by "vs Trade / Trend line" |
| Reclaim buy, Why card | too short | `drv_actionable` | 21 Oct / 19 Oct | — |
| LIVE, Act (N), Today's panel | **no history at the close** | `hist_advice_live` (intraday, October only) | — | not a factor |
| 🔔 Watch | **no history** | `ref_watch` (current only) | — | — |
| 🔭 LT conviction | **too few** | 52 rows, 14 Aug – 21 Sep | — | — |
| CALC, P(↑20d), Agree | **no history** | no active model | — | — |
| 🎯 Tradability score | not stored (client-only, retired by Spec 12) | — | — | Entry label = the Range factor above |
| POS$, AMT$, %CHG, H, bulk | sizing / tools, not signals | — | — | left out |

The "no history" rows are listed on the screen under **Not enough history yet**, with their start date. They are
never shown with fake numbers.

### 4. Outcome definition
- **Start price.** The end-of-day close on the anchor date. That is `drv_quote.last_price`, and it must come from
  that day's end-of-day TOS export, not an intraday quote. Weekend and holiday re-derives are not start points.
- **End price.** The close on the 5th, 10th and 20th next **trading** day, using the NYSE calendar
  (`etl/market_date.py`). If there is no clean price that day, the outcome is left empty. Prices are never carried
  forward.
- **Return.** Price change in %. Dividends are not added back, which makes payers look about 0.1–0.3% worse over 20
  days. **GUESS**, small.
- **Data errors and splits.** A case is dropped, and counted under "skipped", if:
  - its return over the horizon is above 100%, or
  - it has a one-day jump over 50%, or
  - its start price equals its 5-day price exactly (a frozen price).

  The 100% and 50% limits are judgement calls. Under the old method, 202 of 144,858 rows were above 100% over 20 days.
- **Excess return.** The stock's return minus the **median** return of all stocks that day. We use the median, not
  the mean: the mean was off by more than 3 points on 24 of 172 days because of a few broken prices.
- **Direction.**
  - BUY: excess as is.
  - SELL: sign flipped, so a fall counts as good.
  - HOLD: excess as is, read as "which HOLD rows later went up or down".
- **Win.** Direction-adjusted excess above 0. A result of exactly 0 is left out.
- **Look-ahead.**
  - Every bucket uses only values stored for that date.
  - Cut-offs are fixed settings, never fitted to outcomes.
  - The Final Call is the one shown that day.
  - Source and score "track record" terms are not used as factors, because they are built from outcomes.

### 5. Repeated days: episodes
A stock that keeps the same Final Call code day after day is one case, not many.
- An **episode** is a run of trading days with the same code. A gap of more than 5 trading days starts a new one.
- Each episode counts once, scored from its first day: the day the call appeared.
- The screen shows days and episodes side by side, and every threshold uses episodes.

What that does to the counts (read-only, rebuilt in scratch):

| Group | Rows (days) | Episodes | Stocks | Window |
|---|---|---|---|---|
| BUY | 6,870 | 2,250 | 378 | Feb–Sep |
| SELL | 1,655 | 631 | 185 | Feb–Sep |
| BUY (model window) | — | 1,776 | 334 | 11 May – 29 Sep, core inputs present |
| SELL (model window) | — | 493 | 155 | same |
| HOLD (model window) | — | 1,842 | 345 | same |
| BUY TO MIN | — | 1,108 | 312 | same |
| BUY MORE | — | 553 | 193 | same |
| SELL SOME | — | 289 | 124 | same |
| BUY SOME / SELL ALL / SELL OVER / SELL TO MIN | — | 115 / 92 / 77 / 35 | 70 / 69 / 56 / 30 | same, too few for their own table |

Intervals also allow for days clustering together: the bootstrap resamples whole stocks **and** whole calendar
weeks (section 7).

### 6. The `v_factor_scorecard` baseline bug: cause and fix
- **Cause.** `etl/compute_factor_outcomes.py` takes forward prices with `LEAD(…, 5/20)` over `drv_ma` rows.
  - Those rows include 21 weekend re-derive dates, so the "5 days" are not 5 trading days.
  - Many forward prices are stale, so 12,893 of 144,858 rows (8.9%) show a return of exactly 0, which counts as a loss.
  - Rows with no RSI (16,206) won only 14.7% of the time.
  - Together these pull the "All stocks" baseline to 46.2%, against 50.7% once zero rows are removed.
- **Fix in this design:**
  1. Count forward days on the trading calendar.
  2. Drop frozen-price cases.
  3. Compare like with like: a bucket's baseline uses only rows that have a value for that factor.
- **For the grid.** Re-point `v_factor_scorecard` to the new table under the same column names, so the grid's
  RSI / IV edge tags pick up the fix with no web change (Q4).

### 7. How the weights are worked out
- **Method.** A ridge regression (ordinary regression with a mild pull toward zero). There is one per group per
  horizon.
  - Inputs: every factor as on / off buckets, with each factor's most common bucket as the reference ("vs Mid 25–60").
  - Target: the direction-adjusted excess return, capped at the group's 1st / 99th percentile so a few huge moves
    can't decide a weight.
  - **Why ridge:** with all columns in one fit, overlapping columns split the credit instead of both taking it (the
    double counting from Round 12). The pull toward zero keeps rare buckets from getting wild weights.
  - The pull strength is chosen by fitting on earlier months and scoring on later ones.
- **Second column, "win effect".** The same fit on win / lose, read as points of win rate.
- **90% range.** Bootstrap, 500 reps, resampling whole stocks **and** whole calendar weeks with repeats. Repeated
  days of one stock, or one wild week, can't fake certainty.
- **Stability.** The same fit on the first half and the second half of the window, split at the median date. The two
  halves must point the same way.
- **Missing data.** Cases missing a core input (price, RSI, Trade line, MACRO) are left out of the fit and counted.
  "n/a" buckets are never weighted.
- **Prototype result** (BUY, 20 days, 11 May – 29 Sep; 1,776 episodes, 334 stocks; read-only scratch rebuild,
  `r13f.py`):

| Factor = bucket (vs) | Weight (pts) | 90% range | Episodes | Stocks | Early / Late | Flag |
|---|---|---|---|---|---|---|
| Trend line = Below (vs Above) | +3.7 | +1.4 … +4.3 | 122 | 80 | +3.1 / +2.5 | Trust (helps) |
| Range = LRR zone (vs Mid 25–60) | +2.2 | +0.6 … +3.0 | 233 | 153 | +3.0 / +0.8 | Trust (helps) |
| Range = Above TRR | −1.7 | −2.7 … −0.0 | 100 | 80 | −1.7 / −1.8 | Trust (hurts) |
| Source = PS (vs CALL) | −2.7 | −3.5 … −0.6 | 129 | 51 | −3.6 / −1.1 | Trust (hurts) |
| MACRO = STM (vs HOLD) | −2.1 | −3.2 … −0.6 | 167 | 99 | −4.1 / +0.4 | Unstable |
| PVV = BUY_DIP (vs NO_ACTION) | +1.7 | −0.1 … +2.8 | 48 | 40 | — | Too few |
| RSI, MACD, MACDH, IV %, Volume, BB, Held, other MACRO, most sources | −1.5 … +1.4 | all cross 0 | — | — | — | No effect |

SELL (493 episodes): no trusted row except one data-gap bucket (style "n/a"). That row is ignored, and n/a buckets
are excluded in the build.

### 8. Combined score: the pass test, and today's result
- **Test.** Walk-forward: fit on all months before month M, predict the episodes in month M, then repeat month by
  month.
- **Pass rule** (judgement, stated up front):
  1. Prediction and result rank the same way in at least 4 of the last 5 test months.
  2. Over all test months together, the top fifth of predictions beat the bottom fifth, with a 90% range above zero.
- **Today** (20 days):

| Group | Jun | Jul | Aug | Sep | Pass? |
|---|---|---|---|---|---|
| BUY: rank link / top − bottom fifth | +0.17 / +5.1 | +0.08 / +4.3 | −0.17 / −3.5 | +0.06 / +2.3 | **No**: only 4 test months, one wrong-way month |
| SELL | n/a (43 to train) | −0.01 / −0.7 | +0.02 / +1.4 | +0.04 / +5.0 | **No** |

- **Result.** There is no combined score. The screen shows: "Combined score: not shown. It did not pass the
  later-months test (BUY right in 3 of 4 months, SELL no better than chance)." The test re-runs every month after the
  nightly fit. It appears only once it passes, and even then only as an optional, informational column.

### 9. The screen (full width)
Nav: a **Factor Weights** link beside Performance (`/rule-performance`). Route `/factor-weights`.

```
+-----------------------------------------------------------------------------------------------------------------+
| Factor Weights   [BUY] [SELL] [HOLD] [BUY MORE] [BUY TO MIN]      Horizon: (5d) (10d) (*20d)                       |
| 1,776 cases · 334 stocks · 11 May – 29 Sep 2026 · rebuilt 28 Oct 02:10 · result = vs the median stock, same day   |
| Combined score: not shown. Did not pass the later-months test (BUY right in 3 of 4 months).    [How this works]  |
+-----------------------------------------------------------------------------------------------------------------+
| Show: (*all) (trusted only)                                             Sort: (*flag, then size) (by column group) |
+--------------------+------------------+---------------+-------------+-------+-------+-----------+---------------+--------+
| Column             | Value            | vs            | Weight      | 90%   | Cases | Stocks    | Flag          | Today  |
+--------------------+------------------+---------------+-------------+-------+-------+-----------+---------------+--------+
| Price & Range                                                                                                     |
|  vs Trend line     | Below            | Above         | +3.7 ███▌   | +1.4…+4.3 | 122 | 80    | Trust (helps) | 6 →    |
|  RR                | LRR zone         | Mid 25-60     | +2.2 ██     | +0.6…+3.0 | 233 | 153   | Trust (helps) | 6 →    |
|  RR                | Above TRR        | Mid 25-60     | -1.7 ▐█     | -2.7…-0.0 | 100 | 80    | Trust (hurts) | 0      |
| Sources                                                                                                           |
|  Winning source    | PS               | CALL          | -2.7 ▐██    | -3.5…-0.6 | 129 | 51    | Contradicts   | 1 →    |
| Momentum                                                                                                          |
|  RSI               | Overbought       | Neutral       | +0.6        | -1.0…+2.0 | 182 | 91    | No effect     | 2 →    |
|  ...                                                                                                              |
+-----------------------------------------------------------------------------------------------------------------+
| Not enough history yet: IV vs own average (from 14 Aug) · LIVE · Watch · LT notes · CALC / P(↑20d) / Agree       |
+-----------------------------------------------------------------------------------------------------------------+
```

Notes on the screen:
- Weight bars: green to the right, red to the left. The SELL tab uses the same direction-adjusted sign, so green
  always means "helped the call".
- Groups follow the grid: Price & Range, Momentum, Volume, Volatility, Signals (PVV, MACRO), Sources, Position,
  Classification, Calendar, Rules.

Row hover, as bullets:
- BUY rows with price below the Trend line did 3.7 points better over 20 days than similar BUY rows above it, with
  the other columns held equal.
- 90% range: +1.4 to +4.3
- 122 separate cases from 80 stocks (11 May – 29 Sep)
- First half +3.1, second half +2.5: same direction
- Win-rate effect: +x points

**Today (N) bridge.**
- **What N counts:** today's stocks in this group with this value. They come from today's row of `drv_factor_lab`,
  which is built nightly without outcomes.
- **Click:** opens `/actionable?lab=BUY|vs_trend|Below`.
- **On the grid:** the URL fills the existing multi-symbol filter and shows a removable chip, "Lab: BUY · vs Trend
  line = Below (6) ×".
- **When N is 0:** it is plain text, not a link.

### 10. Plain-English flags and wording
| Flag | Rule | Wording (hover first line) |
|---|---|---|
| Too few | fewer than 50 episodes or fewer than 20 stocks | "Too few cases to trust (n episodes, s stocks)." |
| No effect | 90% range crosses 0 | "No clear effect once the other columns are allowed for." |
| Unstable | the halves point opposite ways | "Helped in one half of the period and hurt in the other. Do not rely on it." |
| Trust (helps) | range above 0, halves agree, enough cases | "Helps this call: about +X points over N days." |
| Trust (hurts) | range below 0, halves agree, enough cases | "Hurts this call: about −X points over N days." |
| Contradicts the call | Trust (hurts) **and** the bucket's own direction-adjusted median result is below 0 | "When this shows, the {BUY} call itself has usually been wrong." |

### 11. What it must NOT do, and how it fits with the Entry label
- **Research only.** It never writes to `drv_actionable`, never changes `consolidated_action` / `final_code`, never
  trades, and never feeds the grid or the Entry label.
- **Entry label (Spec 12).** It is a fixed rule using the same range cut-offs as this table's RR rows:
  - Buy now = LRR zone
  - Pullback = Mid + Upper
  - Stretched = TRR zone + Above TRR
- **How they work together.**
  - This table is how you check the Entry label each month. Today it agrees with it: LRR zone is a trusted "helps"
    and Above TRR a trusted "hurts".
  - The Entry label does not change by itself if the table changes. You decide.
- **A later step, only if you ask.**
  1. You pick a trusted row.
  2. A new spec turns it into a named rule (a caution pill, or a Final Call change).
  3. That rule gets its own before / after back-test.
  4. You approve it.
  5. Only then is code changed.

  The weights are never copied into live logic automatically. A combined score that later passes the test would also
  start as an optional, informational column.

### 12. Build plan for the developer
Order of work:
1. **Schema** in `db/baseline.sql`:
   - `drv_factor_lab`: one row per trading anchor date per stock.
     - The call: `final_code`, `final_side`, `group_key`, `held`.
     - Episodes: `episode_id`, `is_episode_start`.
     - About 18 bucket columns, plus `rules_fired` as a JSONB list.
     - Outcomes: `px_start`, `ret_5/10/20`, `xs_5/10/20`, and `skip_reason`.
     - PK `(as_of_date, tos_symbol)`.
   - `drv_factor_weight`: one row per group / horizon / factor / bucket.
     - The bucket: `ref_bucket`, `weight`, `lo90`, `hi90`, `win_effect`.
     - Counts and stability: `n_episodes`, `n_stocks`, `w_early`, `w_late`.
     - `flag`, plus the window dates.
   - `drv_factor_weight_wf`: one row per group / horizon / test month.
     - `n_train`, `n_test`, `rank_corr`, `spread`, `passed`.
   - Every SQL command stays under 965 bytes.
2. **`etl/derive_factor_lab.py`.** Builds the rows.
   - Bucket helpers are pure functions that reuse `ref_settings`.
   - Technical steps come from `etl/technical_rules.classify`.
   - Outcomes use the trading calendar from `etl/market_date.py`.
   - Episodes and the skip rules are built here.
   - Nightly it rebuilds the last 30 trading days plus today, because forward returns mature over time. `--full`
     rebuilds everything. Idempotent: delete the date range, then insert.
3. **`etl/compute_factor_weights.py`.** Runs the ridge fit, bootstrap, halves, flags and the walk-forward test, using
   numpy only (no new package). Fits: BUY, SELL, HOLD, BM, BMN × 5 / 10 / 20 days.
4. **Scheduler.** Add both steps to the nightly job in `etl/scheduler.py`, after `derive_all`. They replace the
   `compute_factor_outcomes` run once Q4 is approved.
5. **API.** New router `api/routers/factor_weights.py`:
   - `GET /api/factor-weights?group=&horizon=`
   - `GET /api/factor-weights/validation?group=&horizon=`
   - `GET /api/factor-weights/today?group=&factor=&bucket=` (returns symbols)
   - Register it in `api/main.py`. Add the page route in `api/routers/pages.py`.
6. **Web.** `web/factor_weights.html` + `web/factor_weights.js`, full width, rows with bulleted tooltips, and a nav
   link. In `web/actionable.js`, handle `?lab=` so it fills `symbols_multi` and shows the chip.
7. **Grid fix (after Q4).** Re-point the `v_factor_scorecard` view to `drv_factor_lab`.
8. **Docs.** New `docs/factor_weights_logic.md`, plus one Lookup row in `CLAUDE.md`.

Tests (behaviour / schema only, per the test-debt policy):
- **Pure Python:**
  - bucket boundaries and ties (a value on a cut-off goes to the lower bucket)
  - missing values give "n/a"
  - forward returns: skip weekends, no carry-forward, frozen price dropped, over 100% dropped
  - SELL sign flip
  - episode builder (the 5-day gap rule)
  - the flag function
  - the ridge fit recovers a planted effect on synthetic data
  - the walk-forward pass / fail rule
- **DB:** a schema test that the 3 tables and their PKs exist (auto-skipped without Postgres).
- **One-off checks:** a run against real data goes in `tests/acceptance/`.

Runtime (**GUESS**, based on the scratch runs):
- Full lab rebuild: about 200k rows, 2–4 minutes.
- Nightly incremental run: under 1 minute.
- Weights: 15 fits × 500 bootstraps on 3k × 50 inputs or fewer, under 1 minute.
- Storage: under 100 MB.

Out of scope for v1:
- A combination explorer or factor picker (dropped at your request)
- IV vs own average (until it has 3 months of results)
- Per-account views
- LIVE / intraday factors
- Your own Done / Skip actions as a factor
- Exact-code tables below the size threshold
- Any automatic use of the weights

### Worth reconsidering
The table finds only four trusted rows out of about 45 for BUY, and none for SELL. Nearly all the "evidence" columns
on the grid add nothing once range position and the Trend line are known. Before adding new columns or rules:
- Use this table for a month as a monthly check-up.
- Then decide in one go which grid columns to hide. Spec 12 already proposes hiding MACD / MACDH / PVV, and this
  data backs it.

## Rules & numbers
- **Groups.** BUY = BM / BS / BMN; SELL = SA / SS / STM / SO; HOLD = HOLD / none. An exact code gets its own table
  only with ≥300 episodes and ≥100 stocks in the window. Today that is BMN (1,108 / 312) and BM (553 / 193). This
  threshold is a judgement call.
- **Window.** 11 May 2026 (MACRO start) to the latest date with a 20-day result. The 5d and 10d tables use the same
  start.
- **Episodes.** Same code on consecutive trading days. A gap of more than 5 trading days starts a new one. Scored
  from the first day.
- **Outcome.** Trading-day forward close against the anchor close, minus that day's median stock, signed by the call.
  Dropped:
  - frozen prices
  - moves over 100% over the horizon, or over 50% in one day (judgement)
  - missing end prices (never carried forward)
- **Cap.** The target is capped at the group's 1st / 99th percentile.
- **Trust.**
  - at least 50 episodes and at least 20 stocks
  - a 90% two-way bootstrap range (stocks × weeks, 500 reps) that does not cross 0
  - the same sign in both halves

  All three are judgement calls (Q6).
- **Contradicts.** Trust (hurts) plus a bucket median result below 0.
- **Combined score.** Shown only if it ranks the right way in at least 4 of the last 5 test months **and** the pooled
  top-fifth minus bottom-fifth range is above 0. Today: fails.
- **Missing.** Core inputs missing means the case is excluded from the fit and counted. "n/a" buckets are never
  weighted.
- **Edge cases.**
  - A stock that changes code mid-run starts a new episode in the new group.
  - A delisted stock has no end price, so its outcome is empty.
  - Settings changes (for example the RSI cut-offs) apply to the whole history at the next rebuild, and the screen
    shows the settings used.
- **Data notes.** All numbers come from read-only SELECTs on 28 Oct 2026. The scratch scripts are `r13a.py`–`r13f.py`
  in the session scratchpad (not in the project).
- **Round 12 re-check** (median baseline + data-error guard):
  - Trade: −1.18% mean, −2.01% median
  - Trade2: −0.74% mean, −0.20% median
  - The old score still has no link to outcome (0.025)

  The Spec 12 conclusions stand.

## Files likely touched
- `db/baseline.sql` — three new tables; `v_factor_scorecard` re-pointed (after Q4).
- `etl/derive_factor_lab.py` (new) — lab rows, buckets, outcomes, episodes.
- `etl/compute_factor_weights.py` (new) — weights, intervals, flags, walk-forward test.
- `etl/scheduler.py` — nightly hook. `etl/compute_factor_outcomes.py` — retired after Q4.
- `api/routers/factor_weights.py` (new), `api/main.py`, `api/routers/pages.py` — endpoints and page route.
- `web/factor_weights.html`, `web/factor_weights.js` (new) — the screen. The shared nav gets the new link.
- `web/actionable.js` — `?lab=` deep link into `symbols_multi`, plus the chip. Bump its `?v=` in `web/actionable.html`.
- `docs/factor_weights_logic.md` (new). `CLAUDE.md` — one Lookup row.
- `tests/test_factor_lab_pure.py` (new, behaviour), a schema test, and one-off checks in `tests/acceptance/`.

## Open questions
1. **Ship the weights table alone, with no combined score, and re-test monthly by itself?**
   - Recommend yes. The combined score failed on later months (BUY right in 3 of 4; SELL chance).
   - Alternative: show the combined score anyway, marked "unproven". Not recommended.
2. **Exact-code tables only for BUY MORE and BUY TO MIN (≥300 episodes, ≥100 stocks)? The other codes appear only
   inside BUY / SELL.**
   - Recommend yes.
   - Alternative: also SELL SOME at 289 episodes, flagged.
3. **One fitting window from 11 May, when MACRO starts?**
   - Recommend yes, so every row is comparable.
   - Alternative: a second, MACRO-less table from 2 Feb, with more cases but a different mix.
4. **Re-point `v_factor_scorecard` (the grid's RSI / IV edge tags) to the corrected data after one week side by
   side?**
   - Recommend yes. It fixes the baseline bug everywhere at once.
5. **Rebuild "Technical step" history using today's (23 Oct) rules, labelled "today's rules applied to history"?**
   - Recommend yes. It is the only way to weigh the current Technical.
   - The stored old codes stay as their own "Technical code" row.
6. **Accept the trust thresholds as stated?** These are at least 50 episodes, at least 20 stocks, a 90% range not
   crossing zero, and both halves agreeing.
   - Recommend yes, as judgement calls.
   - Alternative: stricter (100 episodes, 95% range). That gives fewer trusted rows; today it would likely leave only
     "below Trend line".

Bugs noted (no decision needed):
- **The `v_factor_scorecard` baseline** is wrong because of weekend derive dates in its forward-day count and frozen
  prices counted as losses (section 6).
- **`drv_quote`-based day averages** are distorted by a few broken prices on 24 of 172 days. Use medians, or
  guard the data.

## Status
READY_FOR_DEV
