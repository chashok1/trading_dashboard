# TASK_151 — Phase 1: per-account min / max / unit sizes (spec 3, P1)

**Design source:** `DESIGN_SPEC_3.md`, section "P1 — Per-account sizes from percentages" (DECIDED). Also read the
sizing table in `docs/actionable_logic.md` (~lines 262-275: ADD/INCREASE/REDUCE and `suppressed_reason`).
The user approved this build on 2026-10-11. You choose the implementation; the spec fixes behaviour.

## Goal
Today every stock has ONE min / max / unit dollar number for the whole household (`ref_asset_allocation`
dollar columns = percent x a fixed $400,000). The user thinks of min/max **per account** (e.g. IRA min 4k, F-A
min 2k, made aggressive at 200%). Build per-account sizes:

`account min / max / unit = category percent x that account's own value x the account's multiplier`, then
**rounded to the nearest $1,000** (exactly $500 rounds up; anything above $0 never goes below $1,000).
`units_pct = units / 400000` (the existing `units` column over the old fixed base; it is half the min percent).
Both the raw and the rounded amounts are saved.

## Inputs
- **Category** per stock: same lookup the Final Call sizing already uses (`ref_asset_allocation` by
  `asset_class` for PS/ETF/ETFCHG winners, else `position_category`). Neutral and Other categories stay at **$0**
  (DECIDED).
- **Account value:** the latest position-file total per account on or before the anchor date: Schwab
  `hist_cs.market_value` summed per account; Fidelity `hist_f.current_value` summed per `account_number`. Include
  cash, money market and pending activity. Use the 10/9 figures as a reference: IRA ~$419.9k, F-A ~$178.2k,
  F-M ~$445.6k. If an account has no position file within 5 trading days, write no size rows for it.
- **Multiplier:** new column `ref_accounts.size_mult` (numeric, default 0, allowed 0-5), editable on `/ref`
  (`ref_accounts` has a single-column key; `web/ref.js` renders PK columns read-only, so check it is editable).
  Seed by `short_name`: IRA 1, F-A 2, F-M 1; 401K, HSA, A, Ra = 0 (0 means "not a trading account": no rows).
  Rows that share a short name (two HSA rows) must carry the same value; use the active row. Account 85911
  (401k) is always excluded.
- Expected result (check against these, 10/9 values):

| Account | Call: min / max / unit | Equities: min / max / unit |
|---|---|---|
| IRA (x1) | $4k / $17k / $2k | $8k / $25k / $4k |
| F-A (x2) | $4k / $14k / $2k | $7k / $21k / $4k |
| F-M (x1) | $4k / $18k / $2k | $9k / $27k / $4k |

## What to build
1. **Schema** (`db/baseline.sql`, idempotent; `ref_accounts.size_mult`; `ref_asset_allocation.units_pct`; and a
   new derived table, e.g. `drv_account_size`, keyed by (as_of_date, tos_symbol, account_short) holding category,
   account value used, multiplier, raw and rounded min/max/unit, the account's held dollars in that stock,
   and an over-max flag). Seeds in `db/seeds_*.sql`. Add a line to `docs/migrations.md`. `init_db` swallows DO
   blocks; if you need one, also provide a `migrate_*.py` (template in repo root).
2. **Derive** the per-account sizes inside the normal derive cascade (`derive_all`, after the position tables and
   alongside `drv_actionable`; `DELETE WHERE as_of_date = D` then INSERT; `tos_symbol` only). Per-account held
   dollars come from the position files per account (Schwab per account name, Fidelity per account number).
   **Freshness contract** (docs/agent_handoff_workflow.md): name the job that refreshes it and add the
   `ref_freshness_contract` row in the same task.
3. **API:** add per-account sizes and per-account held/over-max to the `/api/actionable` payload
   (`api/routers/dash.py`) for each row, e.g. a compact list of accounts with min/max/unit/held/over.
4. **UI** (`web/actionable.js`, bump `?v=` in `actionable.html`): the **OVER MAX pill becomes per account**,
   text like `IRA over max ($30.9k / $17k)`; the Action popup / pill tooltip lists, as a **bulleted list**
   (never one flat line), each trading account's min / max / unit / held, e.g. `IRA x1.0`, `F-A x2.0`, `F-M x1.0`.
   Do not add new columns, chips or pills elsewhere (the user dislikes duplicates). Full-width layouts only.
5. **Household figures:** the household min/max shown for context = the SUM of the rounded account amounts.

## IMPORTANT scope limit
**Do NOT change the existing Final Call, `consolidated_action`, `suggested_target_dollar`, `suggested`/AMT$ or
`target_min_dollar`/`target_max_dollar` behaviour in this phase.** The household sizing the Final Call uses
today stays exactly as it is. This phase only ADDS per-account sizes and a per-account over-max display. In
`DEV_HANDOFF.md` record, as a risk/decision for the user, how the household sizing would change if it were
switched to the sum of account amounts (e.g. a Call stock's household min would go from $4k to $12k), but do not
make that switch.

## Check (10/8 or 10/9 anchor)
- The expected table above matches for a Call stock and an Equities stock.
- TXG shows `IRA over max ($30.9k / $17k)`; per account, about 7 stocks are over max on 10/8 and 8 on 10/9 (the old
  household count was 11 and 13). List them in the handoff.
- Changing `size_mult` for F-A on `/ref` and re-deriving changes F-A's amounts (restore it to 2 afterwards).
- Nothing above $0 rounds to $0; Neutral/Other are $0.

## Rules for this task
- Convention list in `CLAUDE.md` applies (idempotent derives, `tos_symbol`, SQL <= 965 bytes, schema in
  `db/baseline.sql`). Preserve LF line endings; check `git diff --stat` is small.
- `etl/` changes need the server restarted before re-deriving.
- Do not run DB writes outside the app's own derive; no emails/network; nothing outside the project folder.
- No tests this round; sanity checks only (`ast.parse`, `node --check`, TestClient load of `/actionable`).
