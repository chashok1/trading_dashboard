# Portfolio rewrite — verification recipe

Five things changed:

1. New schema: `hist_f_transactions` + `drv_realized_gain`
2. New loader: `load_f_transactions` for `Accounts_History*.csv`
3. New derivation: `derive_realized_gain` (FIFO across CS + F)
4. Three new endpoints: `/api/portfolio/activity`, `/api/portfolio/realized`, `/api/portfolio/snapshot-status`
5. Portfolio screen now has Positions / Activity / Realized tabs + a snapshot-staleness banner

Run these checks after `python -m db.init_db`.

---

## 1. Schema is in place

```sql
\d hist_f_transactions
\d drv_realized_gain
```

`hist_f_transactions` should show columns including `account_number`, `trade_date`, `settlement_date`, `action_kind` (default `'OTHER'`), `quantity`, `accrued_interest`, etc. `drv_realized_gain` should show `(source, account, symbol, sell_date, shares_sold)` as PK with a `lots_consumed` JSONB column.

Also confirm the retention policy row landed:
```sql
SELECT * FROM meta_cleanup_policy WHERE table_name = 'hist_f_transactions';
```
Should show `retention_days = 365`. Bump this later when you start downloading longer history.

---

## 2. Drop the Fidelity CSV in

Put `Accounts_History.csv` somewhere the scheduler watches, or load it manually:

```cmd
python -m etl.etl_load "C:\Ashok\Invest\Projects\trading-dashboard\Accounts_History.csv"
```

Expected log output:
```
LOADED hist_f_transactions: N read, M ins, K skip
drv_realized_gain rebuilt: P sell-event rows
```

Sanity check the load:
```sql
SELECT action_kind, COUNT(*)
FROM hist_f_transactions
GROUP BY action_kind ORDER BY 1;
```
You should see BUY / SELL / DIV / CASH rows — CASH is dominant for SPAXX sweeps but it's filtered out of realized-gain matching, so this is fine.

To re-run the same file (e.g. after a Fidelity re-download), the loader is idempotent via the PK `(account, trade_date, action, symbol, quantity, price)` — re-runs report `0 ins, N skip` and don't re-compute.

To set up scheduler auto-pickup, add a row to `LoadFiles.xlsx`:
| source_dir | file_type | tab | weekday | time |
|---|---|---|---|---|
| `C:\path\to\Schwab\Activity`   | CST | (blank) | ALL | (blank) |
| `C:\path\to\Fidelity\Activity` | FT  | (blank) | ALL | (blank) |

(File types: **CST** = Charles Schwab Transactions, **FT** = Fidelity Transactions, matching the existing short-code convention used by **CS** / **TL** / **TD** etc.)

Then `python -m etl.tickers_initial_load` to absorb the edit. The scheduler picks the folder up next start. The detection in `etl_load.py` is by filename — any CSV starting with `Accounts_History` goes through the Fidelity loader.

---

## 3. FIFO realized-gain spot-check

Pick a symbol you've bought and sold within the window:

```sql
SELECT source, account, symbol, sell_date, shares_sold,
       sell_proceeds, cost_basis, realized_gain, realized_gain_pct,
       holding_days_avg, is_long_term,
       jsonb_array_length(lots_consumed) AS n_lots
FROM drv_realized_gain
WHERE symbol = 'TXG'
ORDER BY sell_date DESC;
```

Drill into the lots:
```sql
SELECT sell_date, shares_sold, realized_gain,
       jsonb_pretty(lots_consumed) AS lots
FROM drv_realized_gain
WHERE source = 'F' AND symbol = 'TXG'
ORDER BY sell_date DESC LIMIT 5;
```

Each `lots_consumed` entry shows `{buy_date, shares, cost_per_share, src_file}` — that's your audit trail. If you see a `{"warning": "Unmatched N sh — buy history before transaction window not loaded"}` entry, that means the sell hit history that's older than your 1-year window. Expand the window or accept the partial cost basis until you back-fill.

Force a full rebuild any time:
```cmd
python -m etl.derive_realized
```
prints `drv_realized_gain rebuilt: N sell-event rows`.

---

## 4. API smoke tests

```cmd
curl "http://127.0.0.1:8000/api/portfolio/snapshot-status"
```
One row per (source, account) with `last_snapshot` + `days_stale`.

```cmd
curl "http://127.0.0.1:8000/api/portfolio/activity?days=30&kind=SELL"
```
Should be normalized to one shape regardless of source: `{source, account, symbol, trade_date, action_kind, action, quantity, price, amount, fees, description}`.

```cmd
curl "http://127.0.0.1:8000/api/portfolio/realized?group_by=symbol" | head -40
```
Per-symbol rollup with YTD / MTD / LT / ST splits.

```cmd
curl "http://127.0.0.1:8000/api/portfolio/realized?group_by=none&symbol=TXG"
```
Raw sell events for one symbol with `lots_consumed`.

---

## 5. Portfolio screen walkthrough

Open `/portfolio`.

**Snapshot staleness banner** (yellow, top): shows only when one or more accounts haven't been snapshotted in ≥ 2 days. Example:
> *Stale snapshots:* **F Rollover IRA:** last snapshot 2026-05-10 (7 days stale) — Activity / Realized tabs use transactions and are unaffected.

**Positions tab** (default): unchanged from before — current holdings from the latest `hist_cs` / `hist_f` snapshots.

**Activity tab**: filterable transaction feed.
- Source / Kind / Window / Symbol / Account filters.
- One row per transaction, normalized across CS + F.
- The full Action text shows in a tooltip on hover — useful for the long Fidelity strings.
- Color-coded Kind chips: green=BUY, red=SELL, blue=DIV, grey=CASH.

**Realized tab**: FIFO realized gains.
- Six KPI tiles: YTD / MTD / Total realized + LT / ST split + sell-event count.
- "Group by" selector — Symbol (default) / Account / Raw sell events.
- Raw-sells view drills into individual sells with lot-level detail visible via the API.

---

## 6. Common gotchas

- **Realized table is empty** → either no sells loaded yet, or `derive_realized_gain` errored on first run. Check:
  ```cmd
  python -m etl.derive_realized
  ```
  Any traceback there means the issue is in the FIFO walker, not the loader.

- **"Unmatched shares" warnings in `lots_consumed`** → the sell consumed more shares than the transaction history covers. Fix by downloading more transaction history. Until then, the reported `cost_basis` is the matched portion only, so the realized number understates cost (overstates gain) for the missing shares.

- **Activity shows duplicate rows after reloading the CSV** → it shouldn't, but if a duplicate PK fails to match exactly (off-by-one in price decimals, e.g. `100.00` vs `100`), you'll see two rows. PK is `(account, trade_date, action, symbol, quantity, price)`. Inspect with:
  ```sql
  SELECT account, trade_date, action, symbol, quantity, price, COUNT(*)
  FROM hist_f_transactions GROUP BY 1,2,3,4,5,6 HAVING COUNT(*) > 1;
  ```

- **Snapshot tab shows stale numbers, Realized tab shows fresh ones** → that's the design. Snapshots are downloaded sporadically; transactions are continuous. The banner above the tabs flags when snapshot staleness might mislead.

- **CASH / SPAXX rows clutter the Activity feed** → use the Kind dropdown to filter them out. CASH is excluded from the FIFO walker so the Realized tab is unaffected.

---

## What I deliberately did NOT do

- **No wash-sale adjustments.** `realized_gain` is gross, not §1091-adjusted. For tax filings, use what the brokerage 1099-B reports — this number is for monitoring, not filing.
- **No cross-account FIFO.** Each (account, symbol) is its own queue. A buy in IRA followed by a sell in Brokerage is invisible to the FIFO walker. Brokerages generally do this same — it's the right behavior for tax-lot tracking.
- **No splits / spin-offs / mergers.** If you see "Unmatched shares" warnings on a symbol that had a split, that's why. Manually backfill a synthetic BUY/SELL pair as a workaround, or wait for me to add a `hist_corporate_actions` table.
- **No LoadFiles.xlsx auto-add.** You have to add the Fidelity row by hand (it's outside the project — that's your spreadsheet). The detection-by-filename works regardless.
