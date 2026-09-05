# Dividend Income Logic

Added 2026-09-05. User: "how does the app handle dividends, extra cash?" →
"track it".

## What "gross" means here

Total dividend income = **cash-received dividends + reinvested (DRIP)
amounts**. This matches what a 1099-DIV reports — DRIP is still income,
it's just immediately used to buy more shares rather than sitting as cash.

Both brokers record a DRIP leg as a `BUY`-tagged transaction row, never as a
dividend — so a naive "sum rows tagged as dividends" query silently
undercounts income for any holding with DRIP on. This module deliberately
also matches the reinvestment-specific action text (`REINVESTMENT` for
Fidelity, `Reinvest Dividend` for Schwab) to capture that leg too.

## The money-market/cash-sweep double-row trap

For a **cash-sweep or money-market fund** (e.g. Fidelity's `SPAXX`),
Fidelity's export records ONE dividend event as **two** rows on the same
date, for the identical amount:

- a `DIVIDEND RECEIVED` row (the cash-received leg)
- a `REINVESTMENT` row (the same cash auto-swept back into buying more of
  the fund)

Summing both would double-count — this is one economic event, not two. A
genuine stock/fund **DRIP** (e.g. Schwab's `SWPPX`) instead produces
**only** the reinvestment-tagged row, with no separate cash leg — that one
row is the *only* record of the income and must be kept.

`etl/derive_dividend_income.py::derive_dividend_income` handles this with a
dedup rule: group candidate rows by `(account, symbol, pay_date, amount)`;
if the group contains a cash-received row, drop any reinvested row(s) in
that same group as the sweep-pattern duplicate; otherwise keep the
reinvested row(s) (they're the only evidence of that dividend). Verified
against live data at build time — every `SPAXX` payment had a matching
cash+reinvested pair at the identical amount; `SWPPX` had only the
reinvested row.

## Source data

- `hist_ft` (Fidelity transactions): `action_kind='DIV'` already covers cash
  dividends AND capital-gain distributions (`_f_action_kind()`'s
  `"DIVIDEND RECEIVED"` / `"LONG-TERM CAP GAIN"` / `"SHORT-TERM CAP GAIN"`
  patterns, `etl/load_raw.py`). The DRIP leg is classified `action_kind='BUY'`
  (the loader matches `"REINVESTMENT"` before any DIV check), so it's
  matched on the raw `action` text instead.
- `hist_cst` (Schwab transactions): no normalized action-kind column. Real
  action-text values seen in production (confirmed 2026-09-05 after the
  user asked specifically about 4 symbols showing zero income despite real
  payments — the ORIGINAL version of this module matched only `'DIVIDEND'`,
  which Schwab's export never actually uses):
  - Cash-received: `'Cash Dividend'`, `'Qualified Dividend'`,
    `'Non-Qualified Div'`, `'Pr Yr Cash Div'` (prior-year true-up),
    `'Long Term Cap Gain'`, `'Short Term Cap Gain'` (capital-gain
    distributions, mirroring Fidelity's `action_kind='DIV'` which already
    folds those in).
  - Reinvested (DRIP): `'Reinvest Dividend'`, `'Qual Div Reinvest'`.
  - Deliberately **not** `'Reinvest Shares'` — that's the negative-amount
    BUY *execution* half of the `'Qual Div Reinvest'` pair (same date/
    symbol/amount, opposite sign), not an income record itself — same role
    a plain BUY row plays elsewhere.
- Grouped by `account_number` for Fidelity (not `account` — same reason
  `etl/derive_realized.py` uses it: `hist_ft.account` is inconsistently
  populated across load batches for the same physical account), `account`
  for Schwab.

## Pipeline

Not FIFO — a straight filter+classify+dedup of the transaction tables, no
lot matching needed (unlike `etl/derive_realized.py`'s buy-lot walk).

```
hist_cst / hist_ft  (transaction files load)
  → etl/etl_load.py triggers derive_dividend_income() right after,
    same trigger points as derive_realized_gain (both read the same
    transaction tables, so it's cheap to keep them in lockstep)
  → etl/derive_dividend_income.py: TRUNCATE + rebuild drv_dividend_income
  → GET /api/portfolio/dividends (api/routers/dash.py) — same shape as
    /api/portfolio/realized on purpose: group_by=symbol|account|none,
    server-computed YTD/MTD via CASE WHEN pay_date >= :ytd/:mtd
  → web/portfolio.js — "Dividends" tab (pf-pane-dividends), same filter/
    KPI-strip/table pattern as the Realized tab
  → api/routers/universe.py's dividends_by_account (same shape/reuse
    pattern as realized_by_account) → web/universe.js's Account tile
    tooltip, a "Dividends (YTD)" row next to "Realized (YTD)"
```

`drv_dividend_income` schema (`db/baseline.sql`): one row per (source,
account, tos_symbol, pay_date, amount, is_reinvested) — a leg, not a
rollup. `raw_action` carries the original broker text for audit.

## Manual rebuild

```cmd
python -m etl.derive_dividend_income
```

## Yield on cost / Investment

`GET /api/portfolio/dividends` (`group_by=symbol|account`) also returns
`cost_basis` (labeled "Investment" in the UI) and `yield_on_cost_pct` per
bucket. This went through two wrong designs before landing on the current
one — both wrong attempts and why are worth keeping, since the failure
modes are non-obvious and could easily be reintroduced.

**Attempt 1 (wrong): current snapshot only.** `cost_basis` straight from
`get_portfolio()` — works only for still-held positions; 66 of 79 symbols
with dividend history had none at all (simply no longer held). User: "Why
not all symbols have the values in that column".

**Attempt 2 (wrong): sum every historical BUY transaction.** Falls back to
`SUM(ABS(amount))` over `hist_cst`/`hist_ft` BUY-side rows when no current
position exists, so a closed position still gets a figure. User: "Can't you
get the proper information from CST and FT?" — confirmed live this produces
**nonsensical numbers for any actively-traded symbol**: `GOOGL` showed
**$431k** "invested" against a $34.85 dividend, because the account trades
it in small lots dozens of times a year and gross-summing every buy (never
netting the sells) compounds every round-trip into one wildly inflated
total. User: "numbers doesn't make sense."

**Current design: point-in-time cost basis per payment.** `hist_f`/`hist_cs`
are append-only position-snapshot history, not just the latest snapshot —
so for each dividend payment, a LATERAL join looks up what was ACTUALLY
HELD (real cost basis) on the closest snapshot on or before that specific
`pay_date`. Falls back to the nearest snapshot within 30 days *after* it
(flagged `cost_basis_is_approx` → `investment_basis: "point_in_time_approx"`
→ UI marks it with `~`) for a position opened right around payment time
with no earlier snapshot yet.

- **Yield on cost** = the AVERAGE of each individual payment's own yield
  (that payment's $ ÷ what was actually held right then), not total income
  ÷ one snapshot — correct for a position whose size changes payment to
  payment, which an actively-traded book always has.
- **Investment**, for `group_by=symbol`: the position size as of the MOST
  RECENT payment, summed across every *(account, symbol)* pair that
  contributes to that symbol (each pair's own latest snapshot) — a symbol
  held in two accounts needs both counted, not just whichever one paid most
  recently (a first cut using a single `DISTINCT ON` on the bucket alone
  silently dropped every account but one).
- **Investment**, for `group_by=account`: reverts to `get_portfolio()`'s
  CURRENT total cost basis across every symbol in that account — an
  account persists (never "closes" the way an individual symbol position
  can), so its current total is a coherent, single point-in-time figure.
  Summing each symbol's own point-in-time snapshot (the symbol-grouping
  approach) does NOT work at the account level: it adds together snapshots
  from *different calendar dates* per symbol, which can badly overstate the
  account's real size once capital has rotated between symbols — confirmed
  live: summed to **$577k** for an account whose real current total was
  **$242k**. `yield_on_cost_pct` (an average of *rates*, not summed
  dollars) doesn't have this problem and is computed the same way for both
  groupings.

A pure cash-sweep fund, a position built entirely via reinvestment, or a
symbol bought before the loaded transaction history begins still correctly
falls through to `null` (N/A in the UI) rather than a misleading number —
confirmed against `SPAXX`/`KO` (no real BUY-side snapshot ever) and
`BAC`/`SWVXX` (only SELL + dividend rows in the loaded window).

Gotcha hit building the account-total fallback: calling a FastAPI route
function directly (not through an actual HTTP request) skips FastAPI's own
`Query(...)` resolution — any param left at the function signature's
default stays a raw `Query` object, not the plain value it resolves to over
HTTP. Pass every parameter explicitly (`get_portfolio(date=...,
consolidated=False, account=None, source=None, latest_prices=False)`), same
as `api/routers/universe.py`'s existing `get_portfolio_realized(...)` calls
already do.

## Known gaps

- Tax character (qualified vs. ordinary dividend, return of capital) isn't
  tracked — this is a cash-flow figure, not a tax one.
- Cross-account transfers of a dividend-paying position mid-quarter aren't
  reconciled (same limitation `etl/derive_realized.py` has).
