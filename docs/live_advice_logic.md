# Live advice: night plan, live checks, Today's actions (TASK_152 / TASK_153)

Specs: `DESIGN_SPEC_3.md` (plan + live rules), `DESIGN_SPEC_4.md` (sell side), `DESIGN_SPEC_5.md` (tiers, budgets,
wording). The user's 2026-10-12 decisions override the specs: **accounts are independent**, **Hold = snooze**,
**one combined list** (Do today / Consider / Buy ideas), **Final Call sizing is untouched**.

ADDITIVE ONLY. Nothing here changes `consolidated_action`, `final_code`, `suggested_target_dollar`, AMT$ or
`target_min/max_dollar`. Sizes come from `drv_account_size` (TASK_151).

## Flow

```
end-of-day derive_all(anchor)
  -> build_plan_safe -> hist_advice_plan   (next trading day; rewritten until 09:30 ET, then frozen)
price pull (Yahoo hourly/10:00/15:00, fetch_y_smart, TOSL load)
  -> run_live_check_safe -> hist_advice_live  (one saved check per price time)
GET /api/actionable/live -> build_live_payload  (latest check + plan)
web/actionable.js: LIVE column + #todayPanel + Act (N) chip
```

Code: `etl/derive_live_advice.py` (plan, rules, tiers, payload). Hooks: `etl/derive.py` (plan step after
`drv_account_size`), `etl/yahoo_fetch.py::_run_live_advice_check` (after `fetch_hourly_quotes` / `fetch_y_smart`),
`etl/etl_load.py` (after a TOSL load). Settings: `ref_settings` keys in `db/seeds_live_advice.sql`.

## Night plan (`hist_advice_plan`)

One row per stock per trading account (`ref_accounts.size_mult > 0`) that has a `drv_account_size` row and is held
anywhere, dip-eligible, or sold in the last 5 trading days. Columns: last night's Final Call, kept-source flags,
sizes (min/max/unit), held $ and shares, prior close, SD20, LRR/TRR, trim line, over-max line, dip tier/line/size,
starter order, last sell price, buy-back line/size.

- **SD20** = population SD of the last 20 close-to-close moves ending at the prior close (`hist_y`, last row per day).
  Fewer than 15 moves = no price rules. SD under 0.5% = skip (cash-like funds). SD above 3x its 60-day median uses
  the median.
- **Trim line (T1)** = lower of prior x (1 + 1.5 SD) and max(TRR, prior x (1 + 1.0 SD)). Size = one unit, or the
  position if smaller.
- **Over-max line (T2)** = lower of prior x (1 + 1.0 SD) and 80% of the risk range.
- **Dip eligibility (frozen)**: outlook Bullish (`drv_rr`, exact "bullish"), not cash, not a macro instrument, no hit
  stop; plus any stock you sold in a trading account in the last 5 trading days. Trade Mode is NOT used here.
  Strong = last night's `final_code` BM/BMN/BS (line at -1.5 SD); otherwise Light (-2.0 SD).
- **Dip size**: held account below max = one unit capped at max. Held only where at/over max, or not held: a starter
  at min in ONE non-holding account (largest $ gap to min, then most cash, then IRA, F-A, F-M; cash must cover it).
- **Buy-back**: sold in this account in the last 5 trading days (`hist_cst` / `hist_ft`), net of buys. Line = average
  sell price - 0.5 SD. Size = the net sold $ capped at the room to max.

## Live check (`hist_advice_live`)

Prices: `cache_yahoo_quote` (today ET), or a fresher TOSL quote from `drv_quote`. A check is keyed by its price
time, so a re-run rewrites the same rows (idempotent). A check whose newest price is older than 45 minutes is not
saved ("no new fires from a stale price"); the API marks the list stale. Touch semantics: day high for trims, day low
for dips and buy-backs.

Signals: `SELL_ALL`, `TRIM_TO_MAX`, `TRIM`, `SELL_SOME`, `DIP_BUY_STRONG`, `DIP_BUY_LIGHT`, `BUY_BACK`, `WAIT`,
`BUY_IDEA` (stock-level, account `ALL`), `NONE`. The first check of a plan day also saves the `NONE` rows; later
checks save only non-`NONE` rows (plus caution-only rows). The newest check is the truth.

- **TRIM_TO_MAX**: account above its max AND (above 1.25x max on any day, OR high >= over-max line).
- **Chase tag** on buys: top 20% of the day range, or >= 90% of the risk range.
- **"Don't sell the low" (G1)**: held, price <= prior - 1.5 SD, and a sell path (stop, SA/SS/STM, source
  REMOVE/REDUCE, or the 1.25x trim). No caution when a CALL/RTA/TOP5 sell is behind it, a trend break today, or an
  earnings gap. Bounce price = price at first caution + 0.5 SD (frozen for the day).
- Blocks: SELL ALL (any source), a hit stop, or a conviction note of Avoid block live buys; a kept-source REMOVE also
  blocks buy-back (MSOS case). SELL ALL from a kept source also applies to every account holding the stock.

## Tiers (DESIGN_SPEC_5 with the overrides)

| Tier | What |
|---|---|
| MUST (Do today) | kept-source SELL ALL on a held stock (`final_code` SA, winning source in `must_sellall_sources`, REMOVE/REDUCE, not LOW CONF). No buys. (TRIM_TO_MAX was demoted to INFO on 2026-10-12: housekeeping, not timing. A spike TRIM wins over it when both fire.) |
| CONSIDER | buy-back, spike trim, kept-source SELL SOME, Strong dip, Top 8 by est. value (size x `rank_edge_*`), rest "+N more". Ties: bigger $, sell before buy, IRA/F-A/F-M. |
| BUYIDEA | Trade Mode strict buys not already above; top 5 by the Final Call's own AMT$. |
| INFO | LOW CONF / Technical-only sells, stop hits, Light dips, WAIT, orders under the $1,500 floor. Shown in the grid/tooltip only. |

Precedence (spec 5 section 5): rows 2 and 3 are DROPPED (accounts independent). Kept: 1, 4, 5, 6, 7, 8, 9, 10, 11.
Hold note (`ref_conviction_hold`, direction HOLD) moves MUST to CONSIDER ("you marked Hold"). Same stock in MUST and
CONSIDER = one row under MUST with the optional lines inside. `carried_days` counts consecutive earlier days with a
MUST tier in the saved checks.

### Buy ideas = Trade Mode strict buys

The rule is the one in `web/actionable.js::_isTradeModeQualifyingBuy`, applied in Python by
`etl/export_trade_mode.py::_is_qualifying_buy(strict=True)` (the same port the nightly Trade Mode email uses; keep
the two in step) on the rows of `get_actionable`. Conditions: BM/BMN final code, feasible, Technical entry-ripe (RTA
exempt in the loose step only), no stop, MACRO not SA/STM, not a macro instrument, tradability score >= 12, PVV not
AVOID, BMN only above the Trade line.

## Screen

- The top `#todayPanel` was REMOVED 2026-10-12 (user): same stocks as the grid, nothing extra. The API still returns
  `today` (counts, act_symbols); the LIVE column + Act (N) chip are the UI. Over-max (TRIM->MAX) shows muted in the LIVE
  column and tooltip but is not counted in Act.
- LIVE column after PVV (`_liveCellHtml`, `_buildLivePopHtml`, bulleted tooltip). Sort: tier first, then signal order,
  then larger dollars. INFO badges show only after "Show all live signals".
- **Act (N)** chip (next to "In headwind area") filters the grid to the stocks in the panel.
- The **Trade** toolbar button is gone and Trade no longer starts ON; Trade2 and WL are unchanged.

## Known limits

- Same-day sells are not known at plan time, so a same-day buy-back (spec 3 rule B, same-day branch) is not built.
- The plan is frozen from 09:30 ET; positions bought intraday do not change starter accounts until the next plan.
- `hist_y` has no rows for 9/25 and 9/28 (moves across the gap span two days).
