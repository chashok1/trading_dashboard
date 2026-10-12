# TASK_152 — Phases 2 + 3: frozen night plan, live checks, tiers (back end only)

**Design sources (read only the sections named):**
- `DESIGN_SPEC_3.md`: "Plan plus live check" (§5), rules P1, T1, T2, DB, B, C, PVV, D2, D3.
- `DESIGN_SPEC_4.md`: L1 (T2 1.25x leg), G1 ("Don't sell the low"), N1-N3 notes, and the notes for the developer.
- `DESIGN_SPEC_5.md`: tiers, budgets, materiality, precedence (§5), rules A1-A6. **Overridden by the user, see below.**
The user approved this build on 2026-10-12. You choose the implementation; the specs fix behaviour.
Where spec and live code/data disagree, trust live and say so in `DEV_HANDOFF.md`.

## User decisions that override the specs (2026-10-12)
1. **Accounts are independent.** Being over max in one account does NOT block buys of that stock in other
   accounts. **Drop precedence rows 2 and 3 of spec 5.** Spec 3's fallback starter (held only in over-max accounts ->
   starter in one non-holding account) stays as written.
2. **SELL ALL (row 1) still applies to every account that holds the stock** and still blocks buys of that stock.
   (It is a stock-wide call, not an account limit.) Flag this in the handoff so the user can confirm.
3. **Hold snooze: yes.** A stock with the existing long-term note `drv_actionable.conviction_direction = 'HOLD'` drops
   from MUST to CONSIDER ("you marked Hold"). 'AVOID' blocks buys. Nothing new to build for the note itself.
4. **Final Call sizing stays untouched.** Do not change `consolidated_action`, `final_code`, `suggested_target_dollar`,
   AMT$, or `target_min/max_dollar`. All new numbers come from `drv_account_size` (TASK_151).
5. **One combined list.** Besides MUST and CONSIDER, the live result has a third tier, **BUYIDEA**: the buys that
   Trade Mode shows today (see below), **capped at 5**, ranked by suggested dollars.

## What to build
### 1. Schema (`db/baseline.sql`, seeds in `db/seeds_*.sql`, dated line in `docs/migrations.md`)
- `hist_advice_plan` (append-only; key plan_date, tos_symbol, account_short) — columns per spec 3 D2. May be
  rewritten until 9:30 ET, then frozen.
- `hist_advice_live` (key checked_at, tos_symbol, account_short) — columns per spec 3 D3, **plus** `tier`
  (MUST/CONSIDER/BUYIDEA/INFO), `list_rank`, `in_list`, `est_value`, `carried_days`, `size_dollar`, `shares`, plus the
  G1 caution/bounce price and the note fields (gain %, outlook-turned, sector share). To keep the table small: write
  rows whose signal is not NONE, plus one NONE row per stock per day.
- `ref_settings` keys (seed, idempotent): `overmax_any_day_ratio` 1.25, `today_floor_dollar` 1500,
  `today_must_budget` 5, `today_consider_budget` 8, `today_buyidea_budget` 5, `must_overmax_ratio` 1.25,
  `must_sellall_sources` 'PS,II,CALL,RTA,SSSCHG,TOP5', `rank_edge_buyback` 1.2, `rank_edge_dip` 0.8,
  `rank_edge_sellsome` 0.5, `rank_edge_trim` 0.4, `rank_edge_trim_to_max` 0.3, `dont_sell_low_sd` 1.5,
  `sell_bounce_sd` 0.5, `sell_bounce_days` 5, `note_gain_pct` 20, `note_sector_share_pct` 35,
  `trim_sd` 1.5, `dip_strong_sd` 1.5, `dip_light_sd` 2.0, `buyback_sd` 0.5, `buyback_days` 5.
- Freshness-contract rows for both tables (see `docs/agent_handoff_workflow.md`).

### 2. Frozen night plan — new `etl/derive_live_advice.py` (plan part)
Built after the end-of-day derive for the next trading day, from `drv_actionable`, `drv_account_size`, `drv_rr`,
`drv_quote`/`hist_y` (prior close, SD20), account positions and the last sell per account. Per stock and per trading
account (size_mult > 0): last night's Final Call, outlook, stop status, cash/macro flags, sizes and held, prior close,
SD20 (20 close-to-close moves ending at the prior close), LRR/TRR, trim line, over-max trim line, dip tier and line
and size, starter account and order, last sell price and buy-back line. Eligibility for dip-buy is frozen here
(spec 3 DB: Bullish, not cash, not macro instrument, no hit stop, held or not, plus stocks sold in the last 5 trading
days). Trade Mode is NOT used for eligibility. Edge cases exactly as spec 3 T1 (fewer than 15 moves: no fire;
SD < 0.5%: skip; SD over 3x its 60-day median: use the median; cash: skip; no TRR: SD leg only).

### 3. Live checks (same module, hooked into price pulls)
On every price pull (`etl/yahoo_fetch.py` pulls, the 10:00 / 15:00 ET fallback in `etl/scheduler.py`
`_INTRADAY_QUOTE_TIMES`, and TOSL loads in `etl/etl_load.py`): compare each plan row with live price and day
high/low, set the signal (TRIM, TRIM_TO_MAX, DIP_BUY_STRONG, DIP_BUY_LIGHT, BUY_BACK, WAIT, NONE) per spec 3 T1, T2
(with the 1.25x any-day leg from spec 4 L1), DB, B, C; add the G1 "Don't sell the low" caution + bounce price (spec 4);
save the check. Stale price (older than 45 min): keep the last tier, mark stale. No new fires from a stale price.
Then apply **tiers, merge, floor, budgets, ranking** (spec 5 A1-A6 with the overrides above):
- MUST: kept-source SELL ALL on a held stock (`final_code` SA and `winning_source` in `must_sellall_sources`, REMOVE
  or REDUCE side) and T2 on the more-than-1.25x leg. No buys in MUST. Budget 5 for display; overflow is shown, never
  dropped.
- CONSIDER (budget 8, overflow counted as "+N more"): buy-back, spike trim, SELL SOME from a kept source,
  Strong dip-buy, T2 at 1.0-1.25x with a trigger. Rank by est. value = size x `rank_edge_*`; ties: bigger dollars,
  then sell before buy, then IRA, F-A, F-M.
- BUYIDEA (budget 5): stocks that pass the client rule `web/actionable.js::_isTradeModeQualifyingBuy` today. That
  rule lives in JS. **Port it to Python in the module (same conditions; read it and keep the behaviour) and say in
  the handoff exactly which conditions you ported and any you could not.** Skip a stock already in MUST/CONSIDER.
  Rank by suggested dollars. Size = the Final Call's existing suggested $ (unchanged).
- INFO (not listed, still in grid): LOW CONF sells, Technical-only sells, stop hits (warning only), Light dips,
  WAIT, anything under the floor `today_floor_dollar` per account order (these appear in the tooltip as
  "too small to list"), notes.
- Precedence per spec 5 §5 rows 1, 4, 5, 6, 7, 8, 9, 10, 11 (rows 2 and 3 dropped). Same stock in MUST and CONSIDER =
  one row under MUST with the optional account lines inside. Account with no position file in 5 days: no lines for it
  and a "Can't size IRA: no position file since 10/2." message in the payload.
- `carried_days`: count consecutive days a MUST item has been open, from the saved checks, not from the plan.

### 4. API (`api/routers/dash.py`)
New `GET /api/actionable/live` returning, in one call: per stock the latest check (signal, tier, rank, lines per
account with shares/dollars/limit price, tooltip fields, caution, chase, PVV line, stale flag, price time), plus a
`today` block: `must`, `consider`, `buyideas`, `more_count`, `not_listed` counts by reason, `why` line (spec 5 quiet
states wording), `price_time`, and any "can't size" messages. Wording per spec 5 §6 table.

## Checks (use the 10/9 anchor; there are no price rows for 9/25 and 9/28 -- report, do not invent)
- A plan for 10/12 exists, with the TXG IRA trim line near $84.24 and the right sizes from `drv_account_size`.
- Replaying 10/9 gives MUST = XLE, TXG, MSFT, AAPL (account lines per spec 5 §7 mock); CONSIDER about 8 of 20; BUYIDEA
  at most 5; AAPL IRA starter IS allowed (no cross-account block).
- MSOS: PS REMOVE while `final_code` HOLD -- find out why and report (spec 5 note). Buy-back for MSOS not listed.
- A held stock marked HOLD drops MUST -> CONSIDER (test with any existing conviction note).
- Re-running the same check twice does not duplicate rows (idempotent).
- `GET /api/actionable/live` returns 200 via TestClient and a `today` block.

## Rules for this task
- `CLAUDE.md` conventions: `tos_symbol` only in derives, schema in `db/baseline.sql`, SQL <= 965 bytes, no raw `hist_*`
  deletes, idempotent derives. Preserve each file's existing line endings.
- No emails, no network calls from your checks (use stored prices), nothing outside the project folder.
- No tests, no pytest this round; sanity checks only (`ast.parse`, TestClient load, the checks above).
- `etl/` changes need the server restarted before re-deriving.
