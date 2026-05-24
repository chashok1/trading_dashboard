# Trigger Rules Analyzer UI — User Guide

**Status:** ✅ LIVE & FUNCTIONAL  
**Access:** http://127.0.0.1:8000/trig  
**Last Updated:** 2026-05-08

---

## Overview

The **Trigger Rules Analyzer** is an interactive UI for visualizing which trading rules fire (trigger) for each stock. It helps you understand:

- Which composite rules are active for each stock
- The scoring breakdown (how many atomic rules hit)
- Which rules are triggered vs. not triggered
- Filtering and analysis capabilities

---

## What It Shows

### Statistics Panel (Top)
- **Rules Triggered** — Total count of triggered rules across all stocks
- **Not Triggered** — Total count of non-triggered rules
- **Composite Rules** — Number of unique rule codes available
- **Avg Score** — Average score across all rules

### Stock List (Left Panel)
- Scrollable list of all symbols in the dataset
- Shows how many rules triggered for each stock (e.g., "3/63 rules triggered")
- Click any stock to view its rule details
- Pagination support for large datasets (50 stocks per page)

### Rule Details (Right Panel)
- **Symbol Header** — Shows which stock is selected
- **Rule Summary** — Count of triggered rules + total score
- **Rule Rows** — Each composite rule displayed with:
  - **Rule Code** — Composite rule name (e.g., "TREND-UP", "VOLATILITY-LOW")
  - **Status Badge** — ✓ TRIGGERED or ✗ NO
  - **Atomic Rules Hit** — How many sub-rules matched
  - **Score** — Numerical score for this rule
  
**Color Coding:**
- 🟢 **Green background** = Rule TRIGGERED (score > 0)
- 🔴 **Red background** = Rule NOT triggered (score ≤ 0)

---

## How to Use

### 1. Basic Navigation

1. **Open the page:** Click "Trig Rules" in the dashboard header, or visit `/trig`
2. **Select a stock:** Click any stock in the left panel
3. **View rules:** Right panel shows all rules for that stock, sorted by triggered first

### 2. Filtering

**Filter by Triggered Status:**
- Click the "Filter Triggered" dropdown
- Options: All Rules | Triggered Only | Not Triggered
- List updates instantly to show only matching rules

**Filter by Composite Rule:**
- Click the "Composite Rule" dropdown
- Select a specific rule code (e.g., "TREND-UP", "VOLATILITY-LOW")
- Combines with the triggered filter

### 3. Example Workflow

**Scenario:** Find all stocks where TREND-UP rule is triggered

1. Select "Filter Triggered" = "Triggered Only"
2. Select "Composite Rule" = "TREND-UP"
3. List now shows only stocks with TREND-UP triggering
4. Click any stock to see its TREND-UP score and atomic breakdown

---

## Understanding the Data

### Atomic Rules vs. Composite Rules

**Atomic Rules** — Individual conditions
- Examples: "MACD > 0", "RSI > 70", "IV < 30%ile"
- Each has a breakpoint-based weight (below/between/above)

**Composite Rules** — Groups of atomic rules
- Examples: "TREND-UP" (combines MACD + RSI + other conditions)
- Score = Sum of all atomic weights in the composite

### Score Interpretation

| Score | Meaning |
|-------|---------|
| > 0 | Triggered ✓ (bullish or long signal) |
| = 0 | Not triggered (neutral, all weights cancel) |
| < 0 | Triggered ✗ (bearish or short signal) |

### Atomic Rules Hit

- Count of sub-rules within the composite that contributed weight
- Example: "3/7" means 3 out of 7 atomic rules scored non-zero

---

## Example Interpretations

### Stock: AAPL

**TREND-UP Rule:**
- Status: ✓ TRIGGERED
- Score: 2
- Atomic Rules Hit: 3
- **Interpretation:** 3 of the trend conditions are met (e.g., MACD > 0 + RSI > 50 + Price above SMA)

**VOLATILITY-LOW Rule:**
- Status: ✗ NOT TRIGGERED
- Score: -1
- Atomic Rules Hit: 1
- **Interpretation:** IV percentile is high (not low), so volatility rule doesn't trigger

---

## Performance Notes

- **Dataset:** 73,458 total rules (1,166 stocks × ~63 composite rules)
- **Load Time:** < 2 seconds for full dataset
- **Pagination:** 50 stocks per page for smooth scrolling
- **Filtering:** Real-time, no server round-trip required

---

## Technical Details

### Files Created

| File | Purpose |
|------|---------|
| `web/trig.html` | UI layout and structure |
| `web/trig.js` | JavaScript logic (filtering, rendering, API calls) |
| `api/main.py` | Route handler for `/trig` page + `/api/data/drv_trig` endpoint |
| `web/index.html` | Updated with navigation link |

### API Endpoints Used

```
GET /api/data/drv_trig?limit=10000&offset=0&date=2026-05-06
```

Returns:
- `rows[]` — Array of rule records
  - `symbol` — Stock ticker
  - `composite_rule_code` — Rule identifier
  - `score` — Numeric score
  - `triggered` — Boolean flag
  - `n_atomic_hit` — Count of atomic rules that contributed
- `total` — Total count of rules matching filters
- `columns[]` — Column metadata

---

## Future Enhancements

Potential improvements (not yet implemented):

1. **Rule Details Drill-Down**
   - Click a rule code to see which atomic rules contributed
   - View the exact breakpoint logic (brkeout_from, brkeout_to, weights)

2. **Historical Tracking**
   - Compare rule triggering across multiple dates
   - Identify persistent vs. temporary triggers

3. **Export / Reporting**
   - Export triggered rules to CSV
   - Email alerts when specific rules trigger

4. **Rule Builder**
   - Visual interface to create new composite rules
   - Test rules against historical data

5. **Performance Optimization**
   - Cache rule definitions locally
   - Faster filtering for large datasets

---

## Troubleshooting

**Q: Page loads but list is empty**  
A: Ensure the date picker matches an available date. Check browser console for errors.

**Q: Rules don't load when I select a stock**  
A: The API endpoint `/api/data/drv_trig` may not be returning data. Verify ETL has run for the selected date.

**Q: Filters don't seem to work**  
A: Clear both filters and re-select. Refresh the page if issues persist.

**Q: Stock list is very long**  
A: Use pagination (Next/Previous buttons) to navigate through 50-stock pages.

---

## Quick Reference

| Action | How To |
|--------|--------|
| View triggered rules only | Filter Triggered = "Triggered Only" |
| View a specific rule for all stocks | Composite Rule dropdown = select rule code |
| Sort rules by score | Rules are auto-sorted by triggered status, then score |
| Go back to dashboard | Click "← Dashboard" link at top |
| View raw data | Use Data Explorer at `/explore` and select `drv_trig` table |

---

## Integration with Dashboard

The Trig Rules page integrates seamlessly with the main dashboard:

1. **Navigation** — "Trig Rules" link in the topbar next to Explore and Ref Tables
2. **Date Awareness** — Uses the same snapshot date as the dashboard
3. **Styling** — Matches dashboard CSS and color scheme
4. **Keyword Highlighting** — Not applied to trig data (rule codes are not text fields)

---

## Contact / Support

For questions about:
- **Rule definitions** → See `ref_trig_atomic_rule` and `ref_trig_composite_mapping` in database
- **Scoring logic** → See `etl/derive.py::_derive_trig_impl` and `_bucket_weight()`
- **UI issues** → Check browser console and API `/docs` endpoint
