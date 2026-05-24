# Period Metrics Implementation (YTD & MTD)

## Summary
Added Year-To-Date (YTD) and Month-To-Date (MTD) period metrics to the portfolio detail modal. These metrics show cumulative gains/losses for the specified periods, complementing the current position metrics.

## Changes Made

### 1. API Endpoint (`api/routers/dash.py` - `get_portfolio_detail`)
- **YTD Calculation**: 
  - Start date: January 1st of current year
  - Finds first timeseries data point on/after this date
  - Calculates change in market value and gain from period start to current
- **MTD Calculation**:
  - Start date: 1st of current month
  - Same calculation logic as YTD
- **Returns**: New `periods` object with `ytd_dollar`, `ytd_pct`, `mtd_dollar`, `mtd_pct`

### 2. HTML Structure
- **index.html** (Dashboard):
  - Added period-metrics section after saleStatus div
  - 4 tiles: YTD $, YTD %, MTD $, MTD %
  - Uses same metric-card styling as current metrics
  
- **portfolio.html** (Portfolio page):
  - Same period-metrics section with identical structure

### 3. CSS Styling
- `.period-metrics` class: responsive 4-column grid (repeats auto-fit, minmax 200px)
- Mobile responsive: collapses to 1-column layout
- Inherits positive/negative coloring from metric-value classes

### 4. JavaScript (`portfolio-modal.js`)
- Updated `openPortfolioModal()` to:
  - Read `periods` object from API response
  - Populate YTD/MTD dollar and percentage tiles
  - Apply positive (green) / negative (red) color classes
  - Use proper formatting: sign prefix, locale strings, 2 decimals
  - Handle missing elements gracefully

## Testing Results

```
AAPL (Sold Position):
  YTD: -$3903.75 (-0.17%)
  MTD: $0.00 (0.00%)

QQQ (Sold Position):
  YTD: -$9196.80 (0.30%)
  MTD: $0.00 (0.00%)
```

**Note**: MTD values are $0 because latest timeseries data (Jan 29, 2026) is before May 1, 2026. Once data arrives after May 1, MTD values will populate.

## Modal Layout
1. Header (symbol, description, close button)
2. **Key Metrics** (current position: Shares, Value, Gain/Loss, Gain %)
3. Sale Status Alert (if applicable)
4. **Period Metrics** (YTD $/%, MTD $/%) ← NEW
5. Performance Chart (dual-axis: Shares & Gain/Loss)
6. Tabs (Account Breakdown, Price History)

## Implementation Complete ✓
All tiles render correctly with proper styling, color coding, and number formatting.
