# Portfolio Screen Column Mapping
## Complete Trace from UI Display → API → Database → Source Table

All mappings below are for **Charles Schwab (CS)** source. The Fidelity (F) source has separate columns from hist_f.

---

## UI Column → API Response Field → Database Source

| **Portfolio UI Column** | **API Field Name** | **Database Source** | **hist_cs Column** | **Notes** |
|---|---|---|---|---|
| **Acct** (Account Tag) | `source`, `account` | API combines and decorates | `account` | Prefix (C/F) + number, styled per account |
| **Symbol** | `symbol` | hist_cs | `symbol` | Securities identifier |
| **Description** | `description` | hist_cs | `description` | Security name from Schwab |
| **Qty** | `qty` | hist_cs | `qty` | Share quantity |
| **AVG$** (Avg Cost per Share) | `avg_cost` | Computed in API | `cost_basis / qty` | API line 417: `CASE WHEN qty > 0 THEN cost_basis / qty ELSE NULL END` — displayed with 2 decimals |
| **PRICE** (Share Price) | `last_price` | hist_cs | `price` | Most recent price from Schwab — displayed with 2 decimals |
| **MKT$** (Market Value) | `market_value` | hist_cs | `market_value` | qty × last_price |
| **Cost Basis** | `cost_basis` | hist_cs | `cost_basis` | Total cost basis for position |
| **TODAY$** (Today's Gain $) | `today_gain_dollar` | hist_cs | `day_chng_dollar` | Today's dollar change — displayed with 2 decimals |
| **TODAY%** (Today's Gain %) | `today_gain_pct` | hist_cs | `day_chng_pct` | Today's percent change |
| **TOT$** (Total Gain $) | `total_gain_dollar` | hist_cs | `gain_dollar` | Lifetime gain/loss in dollars |
| **TOT%** (Total Gain %) | `total_gain_pct` | hist_cs | `gain_pct` | Lifetime gain/loss as percent |
| **% Acct** (% of that account, per broker export) | `pct_of_account` | hist_cs / hist_f | `pct_of_account` (Fidelity only; NULL for Schwab) | Broker's own per-account percentage, as exported. For Fidelity cash, this is recomputed (not the raw export value — see CASH row note below) |
| **% of TP** (% of Total Portfolio) | `pct_of_tp` | Computed in API | `market_value` + live import total | `(market_value / tot_amt * 100)`, where `tot_amt` = SUM(hist_f.current_value) + SUM(hist_cs.market_value) for the resolved date (includes cash) |

**CASH row (Fidelity only).** Fidelity exports cash as up to two separate rows per account — `SPAXX**` (money market) and `Pending activity` (unsettled trades/transfers, can be negative). The API merges these into a single synthetic `CASH` row per account (`api/routers/dash.py`, `/api/portfolio`) with `market_value` = their sum. `pct_of_account` for this row is *recomputed* as combined cash ÷ that account's total (market value + cash) — Fidelity's own raw "Percent of account" only covers whichever single row it's attached to (e.g. just SPAXX), so it understates the true cash share whenever Pending Activity is non-zero. `pct_of_tp` then falls out of the normal formula using the combined `market_value`, so it's automatically correct with no special-casing.
| **Sector** | `sector` | drv_dash | — (via tos_symbol lookup) | API lines 485-491: `SELECT sector FROM drv_dash WHERE tos_symbol=X ORDER BY as_of_date DESC LIMIT 1` |
| **Action** (Recommended Action) | `consolidated_action` | drv_actionable | — (via tos_symbol lookup) | API lines 495-501: consolidated action recommendation from rules engine |
| **Limit Min–Max** (Position Limits) | `limit_min`, `limit_max`, `limit_status` | ref_asset_allocation | — (category lookup) | API lines 614-684: based on `applied_category` from winning_source |

---

## Secondary API Fields (Support Data)

These fields are returned in JSON but not directly displayed as columns; they're used for filtering, styling, and drilldown:

| **Field** | **Source** | **hist_cs Column** | **Purpose** |
|---|---|---|---|
| `source` | Hardcoded | — | 'CS' for Charles Schwab |
| `account_id` | hist_cs | `account` | Same as `account` (used for deduplication) |
| `security_type` | hist_cs | `security_type` | Equity / ETF / Mutual Fund / etc. |
| `snapshot_date` | hist_cs | `snapshot_date` | Date of the position snapshot |
| `consolidated_action` | drv_actionable | — | Unified action from all sources |
| `winning_source` | drv_actionable | — | Which source (PS/ETF/II) drove the action |
| `winning_priority` | drv_actionable | — | Priority ranking of the winning rule |
| `suggested_target_dollar` | drv_actionable | — | Target position size in dollars |
| `in_my_list` | ref_my_stocks | — | Y/N: is this symbol in your watchlist |
| `applied_category` | Computed | — | Asset allocation category for position limits |
| `limit_maintain_min` | ref_asset_allocation | — | Flag: whether min must be maintained |
| `pct_of_account` | hist_cs | `pct_of_account` | **Always NULL for CS** (only filled for Fidelity) |

---

## hist_cs Table Schema (Relevant Columns)

**PK:** (snapshot_date, account, symbol)

| **hist_cs Column** | **Type** | **Source (Schwab CSV)** | **Used by UI?** |
|---|---|---|---|
| `snapshot_date` | DATE | "Date" | ✓ Date filtering, YTD/MTD calculation |
| `account` | TEXT | "Account" | ✓ Account filtering, display |
| `symbol` | TEXT | "Symbol" | ✓ Symbol link, sector lookup |
| `description` | TEXT | "Description" | ✓ Tooltip, drilldown |
| `security_type` | TEXT | "Security Type" | Modal detail |
| `qty` | NUMERIC | "Qty" or "Qty (Quantity)" | ✓ Display, cost calc |
| `price` | NUMERIC | "Price" | ✓ Display as "Last" |
| `market_value` | NUMERIC | "Mkt Val (Market Value)" | ✓ Primary sort, KPI totals |
| `cost_basis` | NUMERIC | "Cost Basis" | ✓ Display, avg_cost calc |
| `day_chng_dollar` | NUMERIC | "Day Chng $ (Day Change $)" | ✓ Display as "Today $" |
| `day_chng_pct` | NUMERIC | "Day Chng % (Day Change %)" | ✓ Display as "Today %" |
| `gain_dollar` | NUMERIC | "Gain $ (Gain/Loss $)" | ✓ Display as "Total $", YTD/MTD calc |
| `gain_pct` | NUMERIC | "Gain % (Gain/Loss %)" | ✓ Display as "Total %", bar width |
| `price_chng_dollar` | NUMERIC | "Price Chng $ (Price Change $)" | — |
| `price_chng_pct` | NUMERIC | "Price Chng % (Price Change %)" | — |
| `imported_date` | DATE | "Imported Date" | — |
| `reinvest` | TEXT | "Reinvest?" | — |
| `reinvest_cap_gains` | TEXT | "Reinvest Capital Gains?" | — |

---

## Data Flow Diagram

```
Schwab CSV File
    ↓
etl/load_raw.py (load via mappings.py "CS" entry)
    ↓
hist_cs Table (raw holdings snapshot)
    ├─ snapshot_date, account, symbol, qty, price, market_value, gain_dollar, gain_pct, ...
    ↓
/api/portfolio (GET) — SQL query at dash.py:408-430
    ├─ Selects from hist_cs (latest snapshot ≤ date)
    ├─ Computes avg_cost = cost_basis / qty
    ├─ Decorates with sector (lookup → drv_dash)
    ├─ Decorates with actions (lookup → drv_actionable)
    ├─ Computes YTD/MTD (hist_cs historical snapshots)
    ├─ Applies position limits (→ ref_asset_allocation)
    └─ Returns JSON with all fields
        ↓
portfolio.js (web/portfolio.js)
    ├─ loadPortfolio() → fetch /api/portfolio?date=X
    ├─ renderGrid() → map API fields to table columns
    ├─ Filters/sorts client-side by account, limit status, search
    └─ Displays portfolio table (Portfolio screen)
```

---

## Important Notes

1. **YTD/MTD Calculations** (lines 550-557 of dash.py):
   - Fetches the latest hist_cs snapshot *before* Jan 1 (YTD) and before month start (MTD)
   - Subtracts that prior total_gain_dollar from current to get YTD/MTD-only gain

2. **Avg Cost per Share** (line 417):
   - CS doesn't provide avg_cost directly; computed as `cost_basis / qty`
   - If qty = 0, avg_cost is NULL

3. **Sector Lookup**:
   - NOT from hist_cs; comes from drv_dash (derived table)
   - Uses most recent drv_dash row ≤ snapshot date

4. **Position Limits**:
   - Category determined by winning_source (PS/ETF/ETFCHGs/others)
   - Min/Max/Units from ref_asset_allocation table keyed by category
   - Status computed on-the-fly in API (lines 670-684)

5. **CS vs F Differences**:
   - CS doesn't populate `pct_of_account` (always NULL)
   - F has account_name, CS has only account (account number/name as-is)
   - F's gain_dollar is called `total_gl_dollar`, CS is `gain_dollar`

6. **Data Lag**:
   - Portfolio screen shows latest snapshot ≤ selected date
   - If no CS data for selected date, falls back to most recent earlier date
   - YTD/MTD calculated based on that snapshot date, not today

---

## hist_cs Table DDL Reference

See `db/02_schema_hist.sql` for the complete CREATE TABLE statement:

```sql
CREATE TABLE IF NOT EXISTS hist_cs (
    snapshot_date DATE NOT NULL,
    account TEXT NOT NULL,
    symbol TEXT NOT NULL,
    qty NUMERIC,
    price NUMERIC,
    market_value NUMERIC,
    cost_basis NUMERIC,
    day_chng_dollar NUMERIC,
    day_chng_pct NUMERIC,
    gain_dollar NUMERIC,
    gain_pct NUMERIC,
    description TEXT,
    security_type TEXT,
    price_chng_dollar NUMERIC,
    price_chng_pct NUMERIC,
    imported_date DATE,
    reinvest TEXT,
    reinvest_cap_gains TEXT,
    PRIMARY KEY (snapshot_date, account, symbol),
    ...
);
```

All column mappings here derive directly from this schema and the ETL load flow.
