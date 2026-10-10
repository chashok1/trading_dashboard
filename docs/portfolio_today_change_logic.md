# Portfolio "Today's change" (2026-10-09)

**Headline = account value change**: (market value + cash) now minus the previous snapshot of the same
account (`value_change_dollar`, `value_change_pct`, `prev_total_value`; `GET /api/portfolio/summary`,
`by_account[]` + global totals). The broker's own day change only covers shares still held at the close, so it
misses the move on shares sold that day.

**Breakdown** (all in the same payload; tooltip on the number + small "Δ" line in the web UI):
`held_gain_dollar` (broker day change on held shares) + `sold_move_dollar` (move on shares sold today:
real from hist_cst / hist_ft, else the `drv_realized_gain_estimate` provisional number) + `div_int_dollar`
+ `flow_diff_dollar` (everything not explained: deposits, withdrawals, fees, price gaps).
`txn_loaded` / `txn_through`: true when the transaction table (hist_cst for CS, hist_ft for F) reaches the
snapshot date; if false, `flow_diff_dollar` also contains the sold-share move and trades.

Deposits/withdrawals are **not** entered anywhere; they show up as the unexplained leftover and are reconciled
by loading the transaction files. Verified on 9/30 and 10/1: CS and F pieces reconcile to within $2.

Fidelity specifics: real sold-move = (sell price − previous-snapshot price) x qty from hist_ft SELL rows; money-market
(SPAXX) interest is booked in hist_ft one day before the cash balance rises, so it counts on the next snapshot.
`today_gain_dollar` keeps its old meaning (profit = held + sold-move + dividends) and still drives the P&L trend chart;
for F it now includes the real sold-move/dividends once hist_ft covers the day.

Frontend: `todayChange()/todayTip()/todayDiffHtml()` in `web/portfolio.js`. Entries without `value_change_dollar`
(category-filter aggregates, grid-derived "latest prices" view) fall back to `today_gain_dollar`.
Tests: `tests/test_portfolio_value_change.py`.
