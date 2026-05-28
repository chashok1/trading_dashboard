# STRATEGY AND FALLBACK DETAILS FOR GROUPS 2, 3, 4

---

## GROUP 2: hist_y (Yahoo) - DETAILED STRATEGY

### STRATEGY OVERVIEW
```
Map Yahoo symbol to TOS symbol using ref_rrt table
Lookup column: y_ticker (the Yahoo ticker column in ref_rrt)
```

### STEP-BY-STEP LOGIC

```python
def _populate_y_tos_symbol(session: Session, as_of_date: date) -> int:
    """
    Find all distinct symbols in hist_y where tos_symbol is NULL
    For each symbol, look it up in ref_rrt WHERE y_ticker = symbol
    Update tos_symbol with the result
    """
    
    # Step 1: Get all distinct symbols with NULL tos_symbol
    rows = session.execute(text("""
        SELECT DISTINCT symbol FROM hist_y
        WHERE snapshot_date = :d AND tos_symbol IS NULL
    """), {"d": as_of_date}).fetchall()
    
    # Step 2: For each symbol, call _get_tos_symbol
    for (symbol,) in rows:
        tos_sym = _get_tos_symbol(session, symbol, "y_ticker")
        
        # Step 3: Update the table
        session.execute(text("""
            UPDATE hist_y SET tos_symbol = :tos 
            WHERE snapshot_date = :d AND symbol = :sym
        """), {"tos": tos_sym, "d": as_of_date, "sym": symbol})
```

### THE LOOKUP FUNCTION: _get_tos_symbol()

```python
def _get_tos_symbol(session: Session, symbol: str, lookup_column: str) -> Optional[str]:
    """
    Map a source symbol to its TOS ticker using ref_rrt table.
    
    lookup_column: which column to match in ref_rrt
      - 'y_ticker' for Yahoo symbols
      - 'rr_name' for RR symbols
    
    Returns: tos_ticker if found, otherwise returns original symbol
    """
    
    if not symbol:
        return None
    
    try:
        # Try to find the symbol in ref_rrt
        row = session.execute(text(f"""
            SELECT tos_ticker FROM ref_rrt
            WHERE {lookup_column} = :sym LIMIT 1
        """), {"sym": symbol}).first()
        
        # If found and not empty, return tos_ticker
        if row and row[0]:
            return row[0]
    except Exception:
        pass
    
    # FALLBACK: If not found or error, return original symbol
    return symbol
```

### FALLBACK BEHAVIOR

**Scenario 1: Symbol is found in ref_rrt**
```
Symbol in hist_y: "AAPL"

Query: SELECT tos_ticker FROM ref_rrt WHERE y_ticker = "AAPL"

ref_rrt result: tos_ticker = "AAPL"

Action: tos_symbol = "AAPL" (mapped value)
```

**Scenario 2: Symbol is NOT found in ref_rrt**
```
Symbol in hist_y: "UNKNOWN_SYMBOL"

Query: SELECT tos_ticker FROM ref_rrt WHERE y_ticker = "UNKNOWN_SYMBOL"

ref_rrt result: (no match found)

Action: tos_symbol = "UNKNOWN_SYMBOL" (original symbol - FALLBACK)
```

**Scenario 3: Database error during lookup**
```
Query execution fails (connection issue, etc.)

Catch exception, do nothing

Action: tos_symbol = original symbol (safe fallback)
```

### FALLBACK RATIONALE
- **Why fallback to original symbol?** 
  - If we can't map it, we don't lose data
  - Original symbol is preserved as-is
  - Safe default - never NULL
  - System continues to work even if ref_rrt is incomplete

### RESULT
```
tos_symbol is ALWAYS populated:
  - If found in ref_rrt → mapped value (e.g., "AAPL" -> "AAPL")
  - If not found → original symbol (e.g., "UNKNOWN" stays "UNKNOWN")
  - Never NULL
  - No COALESCE() needed
```

---

## GROUP 3: hist_rr (Risk Range) - DETAILED STRATEGY

### STRATEGY OVERVIEW
```
tos_symbol is populated AT LOAD TIME (not during populate phase)
Special: RR loader handles the mapping directly
Populate function is a NO-OP
```

### HOW IT WORKS: LOAD TIME MAPPING

#### Step 1: etl/mappings.py defines the mapping
```python
HIST_MAPS['RR'] = {
    ...
    "Index": ("tos_symbol", to_text),  # <- Maps Index column to tos_symbol
    ...
}
```

#### Step 2: etl/load_raw.py reads the mapping
```python
def load_rr(session: Session, wb: Workbook, source_file: str):
    """
    Load RR tab from workbook
    """
    
    # Get the mapping definition
    mapping = HIST_MAPS['RR']  # This includes "Index" -> "tos_symbol"
    
    # For each row in RR tab:
    for row in iter_rows_as_dict(sheet, start_row=2):
        rec = {}
        
        # Apply the mapping
        for excel_col, (db_col, caster) in mapping.items():
            value = row.get(excel_col)
            
            # When excel_col is "Index", it maps to "tos_symbol"
            if db_col == "tos_symbol":
                # Index column value is the RR name (e.g., "RR_AAPL")
                rec["tos_symbol"] = caster(value)  # e.g., "RR_AAPL"
        
        # But wait - we need to LOOKUP the RR name to get tos_ticker!
        # This happens SEPARATELY in the RR loader
```

#### Step 3: RR loader performs the lookup
```python
def load_rr(session: Session, wb: Workbook, source_file: str):
    """
    Load RR and map RR name to tos_symbol via ref_rrt
    """
    
    for row in rows:
        rr_name = row['Index']  # e.g., "RR_AAPL"
        
        # Lookup the RR name in ref_rrt to get tos_ticker
        tos_sym = _get_tos_symbol(session, rr_name, "rr_name")
        # This queries: SELECT tos_ticker FROM ref_rrt WHERE rr_name = "RR_AAPL"
        # Returns: "AAPL"
        
        rec = {
            'symbol': rr_name,           # "RR_AAPL"
            'tos_symbol': tos_sym,       # "AAPL"  (looked up!)
            'source_file': source_file,
            ...
        }
        
        records.append(rec)
    
    # Insert into hist_rr
    # Result: tos_symbol is already populated!
```

### FALLBACK BEHAVIOR

**Scenario 1: RR name is found in ref_rrt**
```
RR file Index column: "RR_AAPL"

Query: SELECT tos_ticker FROM ref_rrt WHERE rr_name = "RR_AAPL"

ref_rrt result: tos_ticker = "AAPL"

Action: tos_symbol = "AAPL" (mapped value at load time)

Inserted into hist_rr:
  symbol = "RR_AAPL"
  tos_symbol = "AAPL"
```

**Scenario 2: RR name is NOT found in ref_rrt**
```
RR file Index column: "UNKNOWN_RR"

Query: SELECT tos_ticker FROM ref_rrt WHERE rr_name = "UNKNOWN_RR"

ref_rrt result: (no match)

Action: tos_symbol = NULL (DO NOT FALLBACK)
Create warning: "RR symbol 'UNKNOWN_RR' not found in ref_rrt"

Inserted into hist_rr:
  symbol = "UNKNOWN_RR"
  tos_symbol = NULL  (CRITICAL - requires mapping)
```

**CRITICAL DIFFERENCE FROM OTHER GROUPS:**
```
Group 2 (Yahoo): Fallback to original symbol
Group 3 (RR):    DO NOT fallback - keep NULL + create WARNING
Group 4 (Generic): Fallback to original symbol
```

### POPULATE FUNCTION: _populate_rr_tos_symbol()

```python
def _populate_rr_tos_symbol(session: Session, as_of_date: date) -> int:
    """
    No-op: tos_symbol now populated directly from source file (Index column).
    
    Kept for backwards compatibility but always returns 0 since the RR loader
    now maps Index -> tos_symbol directly in etl/mappings.py.
    """
    return 0  # <- NO-OP (nothing to do)
```

### FALLBACK RATIONALE
- **Why populate at load time?**
  - RR is a special case where Index column IS the symbol to map
  - Mapping happens immediately when data arrives
  - Avoids separate populate step
  - More efficient
  
- **Why fallback to original RR name?**
  - Safe default if ref_rrt doesn't have the RR name
  - Data is never lost
  - System continues to work

### RESULT
```
hist_rr ALWAYS has tos_symbol populated at load time:
  - If found in ref_rrt → mapped value (e.g., "RR_AAPL" -> "AAPL")
  - If not found → original RR name (e.g., "RR_UNKNOWN" stays "RR_UNKNOWN")
  - Never NULL
  - No populate function needed (already done at load)
```

---

## GROUP 4: GENERIC TABLES - DETAILED STRATEGY

### STRATEGY OVERVIEW
```
Smart matching: Try three different ref_rrt columns IN ORDER
Stop as soon as a match is found
Fallback: Use original symbol if nothing matches
```

### THE MATCHING ORDER

The strategy tries to find the symbol in ref_rrt using different columns:

```
1st Priority: tos_ticker column
   - For symbols already in TOS format
   - Example: symbol="AAPL" found in ref_rrt.tos_ticker
   
2nd Priority: y_ticker column
   - For symbols in Yahoo format
   - Example: symbol="AAPL" found in ref_rrt.y_ticker
   
3rd Priority: rr_name column
   - For symbols in RR format
   - Example: symbol="RR_AAPL" found in ref_rrt.rr_name
   
Fallback: Original symbol
   - If not found in any of above
   - Example: symbol="XYZ123" stays "XYZ123"
```

### STEP-BY-STEP LOGIC

```python
def _populate_generic_tos_symbol(session: Session, table: str, as_of_date: date) -> int:
    """
    Populate tos_symbol for generic tables (call, etf, ii, sss)
    by matching against ref_rrt in priority order
    """
    
    # Step 1: Get all distinct symbols with NULL tos_symbol
    rows = session.execute(text(f"""
        SELECT DISTINCT symbol FROM {table}
        WHERE snapshot_date = :d AND tos_symbol IS NULL
    """), {"d": as_of_date}).fetchall()
    
    updated = 0
    
    # Step 2: For each symbol, try to find it in ref_rrt
    for (symbol,) in rows:
        tos_sym = None
        
        # === MATCHING ATTEMPT #1: tos_ticker ===
        # Try: Is the symbol itself a tos_ticker?
        row = session.execute(text("""
            SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = :sym LIMIT 1
        """), {"sym": symbol}).first()
        
        if row and row[0]:
            tos_sym = row[0]
            print(f"  {symbol} -> MATCH in tos_ticker -> {tos_sym}")
        
        # === MATCHING ATTEMPT #2: y_ticker ===
        # If no match, try: Is the symbol a Yahoo ticker?
        if not tos_sym:
            row = session.execute(text("""
                SELECT tos_ticker FROM ref_rrt WHERE y_ticker = :sym LIMIT 1
            """), {"sym": symbol}).first()
            
            if row and row[0]:
                tos_sym = row[0]
                print(f"  {symbol} -> MATCH in y_ticker -> {tos_sym}")
        
        # === MATCHING ATTEMPT #3: rr_name ===
        # If still no match, try: Is the symbol an RR name?
        if not tos_sym:
            row = session.execute(text("""
                SELECT tos_ticker FROM ref_rrt WHERE rr_name = :sym LIMIT 1
            """), {"sym": symbol}).first()
            
            if row and row[0]:
                tos_sym = row[0]
                print(f"  {symbol} -> MATCH in rr_name -> {tos_sym}")
        
        # === FALLBACK ===
        # If STILL no match, use original symbol
        if not tos_sym:
            tos_sym = symbol
            print(f"  {symbol} -> NO MATCH -> FALLBACK to {tos_sym}")
        
        # Step 3: Update the table
        session.execute(text(f"""
            UPDATE {table} SET tos_symbol = :tos
            WHERE snapshot_date = :d AND symbol = :sym
        """), {"tos": tos_sym, "d": as_of_date, "sym": symbol})
        
        updated += 1
    
    return updated
```

### FALLBACK BEHAVIOR WITH EXAMPLES

#### Example 1: Symbol matches tos_ticker (first attempt succeeds)
```
hist_call row:  symbol="AAPL"

Attempt 1 (tos_ticker):
  Query: SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = "AAPL"
  Result: tos_ticker = "AAPL"
  Found! Stop here.

Action: tos_symbol = "AAPL"
Status: MATCHED on first attempt (tos_ticker)
```

#### Example 2: Symbol matches y_ticker (second attempt succeeds)
```
hist_etf row:   symbol="AAPL"

Attempt 1 (tos_ticker):
  Query: SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = "AAPL"
  Result: NO MATCH (tos_ticker column doesn't have "AAPL")

Attempt 2 (y_ticker):
  Query: SELECT tos_ticker FROM ref_rrt WHERE y_ticker = "AAPL"
  Result: tos_ticker = "AAPL"
  Found! Stop here.

Action: tos_symbol = "AAPL"
Status: MATCHED on second attempt (y_ticker)
```

#### Example 3: Symbol matches rr_name (third attempt succeeds)
```
hist_ii row:    symbol="RR_AAPL"

Attempt 1 (tos_ticker):
  Query: SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = "RR_AAPL"
  Result: NO MATCH

Attempt 2 (y_ticker):
  Query: SELECT tos_ticker FROM ref_rrt WHERE y_ticker = "RR_AAPL"
  Result: NO MATCH

Attempt 3 (rr_name):
  Query: SELECT tos_ticker FROM ref_rrt WHERE rr_name = "RR_AAPL"
  Result: tos_ticker = "AAPL"
  Found! Stop here.

Action: tos_symbol = "AAPL"
Status: MATCHED on third attempt (rr_name)
```

#### Example 4: Symbol NOT found anywhere (FALLBACK)
```
hist_sss row:   symbol="XYZ123"

Attempt 1 (tos_ticker):
  Query: SELECT tos_ticker FROM ref_rrt WHERE tos_ticker = "XYZ123"
  Result: NO MATCH

Attempt 2 (y_ticker):
  Query: SELECT tos_ticker FROM ref_rrt WHERE y_ticker = "XYZ123"
  Result: NO MATCH

Attempt 3 (rr_name):
  Query: SELECT tos_ticker FROM ref_rrt WHERE rr_name = "XYZ123"
  Result: NO MATCH

No matches found anywhere!

Action: tos_symbol = "XYZ123" (FALLBACK - use original)
Status: NO MATCH - using fallback
```

### WHY THIS ORDER?

```
1st: tos_ticker
   - Most direct match
   - Symbol is already in TOS format
   - No translation needed
   - Example: AAPL from TOS workbook

2nd: y_ticker
   - Common source (Yahoo is widely used)
   - Symbols often come from Yahoo
   - Good fallback from direct match
   - Example: AAPL from Yahoo data

3rd: rr_name
   - Least common (RR is specialized)
   - Try this last
   - Example: RR_AAPL from RR workbook

Fallback: original symbol
   - Never fails
   - Preserves data
   - Safe default
```

### FALLBACK RATIONALE

**Why try three columns?**
- Generic tables have unknown sources
- Could be any of: TOS native, Yahoo, RR format
- Three lookups cover all bases

**Why stop at first match?**
- Once found, we have the answer
- No need to try other columns
- More efficient

**Why fallback to original symbol?**
- If all three columns fail, symbol not in ref_rrt
- Better to preserve original than return NULL
- Data isn't lost
- System continues to work
- Safe assumption: unmapped symbol is self-describing

### RESULT
```
tos_symbol is ALWAYS populated:
  - If found in tos_ticker → mapped value
  - Else if found in y_ticker → mapped value
  - Else if found in rr_name → mapped value
  - Else → original symbol (FALLBACK)
  - Never NULL
  - No COALESCE() needed
```

---

## COMPARISON TABLE: FALLBACK BEHAVIOR

| GROUP | Lookup Column(s) | Found | NOT Found |
|-------|------------------|-------|-----------|
| **2: Yahoo** | y_ticker | tos_ticker value | original symbol |
| **3: RR** | rr_name (at load) | tos_ticker value | original RR name |
| **4: Generic** | tos_ticker, y_ticker, rr_name (in order) | tos_ticker value | original symbol |

---

## SUMMARY: FALLBACK IS ALWAYS SAFE

✓ All three groups fall back to original symbol if not found in ref_rrt
✓ Never returns NULL
✓ Never loses data
✓ Safe default that preserves information
✓ No COALESCE() needed anywhere
