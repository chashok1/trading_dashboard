# DETAILED BREAKDOWN OF FOUR GROUPS

## GROUP 1: TOS TABLES (hist_tl, hist_td, hist_to, hist_tw)

### DEFINITION
Tables loaded directly from TOS (thinkOrSwim) workbook tabs.
Symbol column already contains TOS ticker symbols.

### SOURCE WORKBOOK
- `hist_tl`: TL tab (TOS Latest quotes)
- `hist_td`: TD tab (TOS Daily analytics)
- `hist_to`: TO tab (TOS Overview fundamentals)
- `hist_tw`: TW tab (TOS Weekly analytics)

### STRATEGY
```
tos_symbol = symbol (DIRECT COPY - no mapping needed)
```

### POPULATE FUNCTION
```python
_populate_tos_table_tos_symbol(session, table, as_of_date)

SQL: UPDATE hist_* SET tos_symbol = symbol 
     WHERE snapshot_date = :d AND tos_symbol IS NULL
```

### WHY THIS WORKS
TOS workbook uses TOS ticker symbols natively.
Example: AAPL in TL tab is the TOS ticker for Apple — no translation needed.

### EXAMPLE
```
Input:  symbol = "AAPL"  (from TOS workbook)
Output: tos_symbol = "AAPL"  (direct copy)
```

### REF_RRT LOOKUP
**NONE** (no lookup performed)

---

## GROUP 2: hist_y (Yahoo Source)

### DEFINITION
Loaded from Yahoo workbook tab.
Symbol column contains Yahoo ticker symbols.
Need to map Yahoo symbol → TOS symbol.

### SOURCE WORKBOOK
- `hist_y`: Y tab (Yahoo quotes and fundamentals)

### STRATEGY
```
Look up symbol in ref_rrt WHERE y_ticker = symbol
Return tos_ticker if found, else return original symbol
```

### POPULATE FUNCTION
```python
_populate_y_tos_symbol(session, as_of_date)

For each symbol in hist_y WHERE tos_symbol IS NULL:
  - Call _get_tos_symbol(session, symbol, "y_ticker")
  - Query: SELECT tos_ticker FROM ref_rrt WHERE y_ticker = symbol
  - Fallback: if not found, return original symbol
```

### REF_RRT LOOKUP COLUMN
`y_ticker` (Yahoo ticker column in ref_rrt table)

### EXAMPLE
```
ref_rrt row:    rr_name="RR_AAPL" | y_ticker="AAPL" | tos_ticker="AAPL"

hist_y row:     symbol="AAPL"  (from Yahoo workbook)

Lookup:         SELECT tos_ticker FROM ref_rrt WHERE y_ticker = "AAPL"
Result:         tos_ticker = "AAPL"
Update:         tos_symbol = "AAPL"
```

### FALLBACK BEHAVIOR
If symbol not in ref_rrt (no matching y_ticker):
```
tos_symbol = original symbol (e.g., "AAPL" stays "AAPL")
```

---

## GROUP 3: hist_rr (Risk Range Source)

### DEFINITION
Loaded from Risk Range (RR) workbook.
**Special**: tos_symbol IS POPULATED AT LOAD TIME (not during populate phase).

### SOURCE WORKBOOK
- `hist_rr`: RR tab (Risk Range zones)

### STRATEGY
```
tos_symbol populated directly by load_rr() in load_raw.py
Maps Index column (RR name) to tos_symbol at load time
etl/mappings.py has: "Index" -> "tos_symbol" mapping
```

### POPULATE FUNCTION
```python
_populate_rr_tos_symbol(session, as_of_date)

This is a NO-OP (returns 0)
Already populated during load phase
```

### WHY
RR loader in `load_raw.py` handles the mapping:
1. Reads "Index" column from RR tab
2. Looks up in ref_rrt WHERE rr_name = Index
3. Directly sets tos_symbol in record before INSERT

### EXAMPLE
```
ref_rrt row:    rr_name="RR_AAPL" | tos_ticker="AAPL"

hist_rr loaded:
  symbol = "RR_AAPL"  (from Index column)
  tos_symbol = "AAPL"  (mapped at load time)
```

### LOAD TIME MAPPING
- `etl/mappings.py`: "Index" → "tos_symbol"
- `load_rr()` looks up rr_name and sets tos_symbol during load

### RESULT
hist_rr's tos_symbol is set at load time. **Important**: unlike Groups 2 and 4, RR does NOT fall back to the original RR name if the lookup misses — `tos_symbol` stays NULL and a warning is created in the `data-quality` screen (the canonical strategy in `docs/tos_symbol_normalization.md`). Missing RR mappings are surfaced for manual intervention rather than silently aliased.

---

## GROUP 4: GENERIC TABLES (hist_call, hist_etf, hist_ii, hist_sss)

### DEFINITION
Tables from unknown/generic sources.
Symbol column may be in any format (Yahoo, TOS, or other).
Need smart matching to find correct tos_symbol.

### SOURCE WORKBOOK
- `hist_call`: CALL tab (Options data)
- `hist_etf`: ETF tab (ETF fundamental data)
- `hist_ii`: II tab (Industry Index data)
- `hist_sss`: SSS tab (Signal Strength Summary)

### STRATEGY
Try matching IN ORDER until found:
1. Check if symbol matches `tos_ticker` column in ref_rrt
2. Check if symbol matches `y_ticker` column in ref_rrt
3. Check if symbol matches `rr_name` column in ref_rrt
4. If no match found: use original symbol as fallback

### POPULATE FUNCTION
```python
_populate_generic_tos_symbol(session, table, as_of_date)

For each symbol WHERE tos_symbol IS NULL:
  tos_sym = None
  
  # Try tos_ticker
  row = SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = symbol
  if found: tos_sym = row[0]
  
  # Try y_ticker
  if not tos_sym:
    row = SELECT tos_ticker FROM ref_rrt WHERE y_ticker = symbol
    if found: tos_sym = row[0]
  
  # Try rr_name
  if not tos_sym:
    row = SELECT tos_ticker FROM ref_rrt WHERE rr_name = symbol
    if found: tos_sym = row[0]
  
  # Fallback
  if not tos_sym:
    tos_sym = symbol
  
  UPDATE table SET tos_symbol = tos_sym WHERE symbol = symbol
```

### REF_RRT LOOKUP COLUMNS (in order)
1. `tos_ticker`
2. `y_ticker`
3. `rr_name`

### EXAMPLES

**Case 1: Symbol is already tos_ticker**
```
hist_call row:  symbol="AAPL"
Lookup (tos_ticker): SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = "AAPL"
Result:         tos_ticker = "AAPL"
Update:         tos_symbol = "AAPL"
```

**Case 2: Symbol is Yahoo format**
```
hist_etf row:   symbol="AAPL"
Lookup (tos_ticker): no match
Lookup (y_ticker): SELECT tos_ticker FROM ref_rrt WHERE y_ticker = "AAPL"
Result:         tos_ticker = "AAPL"
Update:         tos_symbol = "AAPL"
```

**Case 3: Symbol is RR format**
```
hist_ii row:    symbol="RR_AAPL"
Lookup (tos_ticker): no match
Lookup (y_ticker): no match
Lookup (rr_name): SELECT tos_ticker FROM ref_rrt WHERE rr_name = "RR_AAPL"
Result:         tos_ticker = "AAPL"
Update:         tos_symbol = "AAPL"
```

**Case 4: Symbol not in ref_rrt**
```
hist_sss row:   symbol="XYZ123"
All lookups:    no match
Fallback:       tos_symbol = "XYZ123"
(safe default - preserves original symbol if not found)
```

### WHY THIS ORDER
1. `tos_ticker`: Direct match — already TOS format
2. `y_ticker`: Yahoo format mapping — common source
3. `rr_name`: Risk Range format — less common
4. Fallback: Preserve original if nothing matches

### FALLBACK BEHAVIOR
If no match in any ref_rrt column:
```
tos_symbol = original symbol
(safe - always returns something, never NULL)
```

---

## SUMMARY TABLE

| GROUP           | TABLES                    | LOOKUP          | STRATEGY
|-----------------|---------------------------|-----------------|------------------
| TOS Direct      | tl, td, to, tw            | NONE            | Copy symbol
| Yahoo           | y                         | y_ticker        | Map via y_ticker
| RR (Pre-mapped) | rr                        | rr_name (load)  | Populate at load
| Generic         | call, etf, ii, sss        | Try all 3       | Smart match

---

## FINAL RESULT FOR ALL GROUPS

✓ **tos_symbol is ALWAYS populated (never NULL)**
✓ **Safe fallback to original symbol if no match**
✓ **No need for COALESCE() — just use tos_symbol directly**
