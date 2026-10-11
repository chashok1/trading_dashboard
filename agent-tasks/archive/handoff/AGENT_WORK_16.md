# AGENT_WORK — Developer pointer

## Active task — TASK_106 (Fix ETFChange/IIChange description + Call outlook/modifier)

Three parser issues in `etl/hedgeye/parsers.py`. Archive AGENT_WORK.md → AGENT_WORK_16.md. Write DEV_HANDOFF.md ending ALL_DONE. No commits.

---

## Issue 1 — ETFChange: Description missing

`parse_etf_changes` extracts action/side/symbol but never captures the description (company name).

**Email body format:**
```
We are ADDING Long position
Company Name (TICKER)
```

When the parser matches `re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", ln)` to get TICKER,
the text BEFORE the `(TICKER)` on that line IS the description.

**Fix:** extract description from the same line as the ticker:
```python
m = re.search(r"\(([A-Z][A-Z0-9.\-]{0,9})\)", ln)
if m:
    desc = ln[:m.start()].strip() or None
    rows.append({..., "description": desc, ...})
```

Also make sure the emitter uses `r.get("description")` — it already does (emit.py line ~194).

---

## Issue 2 — IIChange: Description missing

`parse_investing_ideas` extracts action/side/symbol from subject and body, but never extracts description.

**Email subject formats:**
- "Add AGILITI (AGTI) to LONG Side"  → description = "AGILITI"
- "Remove iShares (EWJ) from LONG Side" → description = "iShares"

**Fix:** extract the company name from the subject — the text between the action word (Add/Remove) and the `(TICKER)` paren:

```python
# After extracting action/side, extract description from subject
desc = None
m_desc = re.search(r"(?:Add|Remove)\s+(.+?)\s*\(([A-Z][A-Z0-9.\-]{0,9})\)", subj, re.I)
if m_desc:
    desc = m_desc.group(1).strip()
```

Then include `"description": desc` in each row dict.

---

## Issue 3 — CALL: Outlook must be BULLISH/BEARISH/NEUTRAL; outlook_modifier must be extracted

Current parser stores: LONGS→"long", SHORTS→"short", NEUTRAL→"neutral" in `outlook`.
But `hist_call.outlook` must be BULLISH/BEARISH/NEUTRAL (matching the old ProcessCall.py convention).
And `hist_call.outlook_modifier` must capture the specific modifier (e.g., "long bench", "short bench",
"best idea long", "best idea short") found for each symbol in the body.

### Step 1 — Fetch a call email to see actual body format

Write to temp file and run:
```python
# C:\Users\chash\AppData\Local\Temp\claude\fetch_call_body.py
import sys
sys.path.insert(0, r'C:\Ashok\Invest\Projects\trading-dashboard')
from dotenv import load_dotenv; load_dotenv()
from etl.db import session_scope
from sqlalchemy import text
import imaplib, email as emaillib

with session_scope() as s:
    cfg = dict(s.execute(text("SELECT key, value FROM ref_settings WHERE key IN ('imap_host','imap_user','imap_pass','imap_folder')")).fetchall())

mail = imaplib.IMAP4_SSL(cfg.get('imap_host','imap.mail.yahoo.com'))
mail.login(cfg['imap_user'], cfg['imap_pass'])
mail.select(cfg.get('imap_folder','Hedgeye'))
_, ids = mail.search(None, 'SINCE 24-Jun-2026 BEFORE 27-Jun-2026')
for num in ids[0].split():
    _, data = mail.fetch(num, '(RFC822)')
    msg = emaillib.message_from_bytes(data[0][1])
    subj = msg.get('Subject','')
    if 'call' in subj.lower() or 'replay' in subj.lower():
        print(f'=== {subj} ===')
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                body = part.get_payload(decode=True).decode('utf-8','replace')
                print(body[:6000])
                break
mail.logout()
```

Run: `python C:\Users\chash\AppData\Local\Temp\claude\fetch_call_body.py`

Look for:
- How LONGS/SHORTS/NEUTRAL sections are structured
- Whether there are sub-sections like "BEST IDEA LONGS:", "SHORT BENCH:", "LONG BENCH:", "BEST IDEA SHORTS:"
- Whether modifiers appear inline, e.g. "Long Bench: AAPL, MSFT" or "AAPL (Long Bench)"

### Step 2 — Implement the fix

**Outlook mapping (always):**
```python
_CALL_OUTLOOK = {"longs": "BULLISH", "shorts": "BEARISH", "neutral": "NEUTRAL"}
```

**Outlook modifier detection:**
The modifier is the most specific classification for each symbol. Priority order (from ProcessCall.py):
1. "long bench" / "short bench" (weight 5)
2. "best idea long" / "best idea short" (weight 4)
3. No modifier (just the base BULLISH/BEARISH/NEUTRAL)

**Strategy 1 — Section-based (if modifiers are section headers):**
```
BEST IDEA LONGS: MSFT, NVDA
LONG BENCH: AAPL
SHORTS: TSLA
SHORT BENCH: META
```
Parse each section header → assign modifier to its symbols.

**Strategy 2 — Body scan (if inline sentences):**
For each symbol, scan body sentences containing that symbol for modifier keywords:
"long bench", "short bench", "best idea long", "best idea short"

Use whichever approach matches the actual email format. Modifier keywords to detect:
- "best idea long" → "best idea long"  
- "best idea short" → "best idea short"
- "long bench" → "long bench"
- "short bench" → "short bench"
- (case-insensitive)

**Row structure:**
```python
pos_rows.append({
    "snapshot_date": email.edt_date,
    "message_id": email.message_id,
    "symbol": sym, "tos_symbol": sym,
    "outlook": "BULLISH",           # or BEARISH or NEUTRAL
    "outlook_modifier": modifier,   # "long bench", "short bench", etc. or None
})
```

---

## Issue 4 — Action value consistency (ETFChange/IIChange)

The loader already handles both old format (Long/Short in Outlook col) and new format (add/remove in Action col).
The DB has `action` and `side` columns in hist_etfchg/hist_iichg (added separately from outlook/change_str).

For emit-path rows, populate BOTH the old-style `outlook`/`change_str` fields AND new `action`/`side` fields
so the DB has consistent data regardless of ingestion path:

In emit.py `render_etf_changes` and `render_investing_ideas`, the Outlook column (col 4) carries `side`
("long"/"short") and Action col 5 carries `action` ("add"/"remove"). This is correct — the loader
maps col4→outlook, col5→change_str. No change needed in emit.py.

However, also make sure in the parser rows that `side` is normalized to lowercase:
"Long"→"long", "SHORT"→"short". Already done but confirm.

---

## Step 3 — Clear state and reprocess

```python
python -c "
import os, shutil
os.chdir(r'C:\\Ashok\\Invest\\Projects\\trading-dashboard')
from dotenv import load_dotenv; load_dotenv()
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    for et in ('the_call','etf_changes','investing_ideas'):
        n = s.execute(text(f\"DELETE FROM meta_hedgeye_msg WHERE email_type='{et}'\")).rowcount
        print(f'cleared ledger {et}:', n)
    for ft in ('CALL','ETFCHANGE','IICHANGE'):
        n = s.execute(text(f\"DELETE FROM meta_file_processed WHERE UPPER(file_type)='{ft}'\")).rowcount
        print(f'cleared processed {ft}:', n)
    s.execute(text(\"DELETE FROM hist_iichg WHERE event_date BETWEEN '2026-06-24' AND '2026-06-26'\"))
    s.execute(text(\"DELETE FROM hist_etfchg WHERE event_date BETWEEN '2026-06-24' AND '2026-06-26'\"))
    s.execute(text(\"DELETE FROM hist_call WHERE snapshot_date BETWEEN '2026-06-24' AND '2026-06-26'\"))
    s.commit()
    print('hist tables cleared')

dirs = {
    'Call': r'C:\Ashok\Investing\Stocks\Call\Archive',
    'ETFChange': r'C:\Ashok\Investing\Stocks\ETFChange\Archive',
    'IIChange': r'C:\Ashok\Investing\Stocks\IIChange\Archive',
}
test_dates = ['2026-06-24','2026-06-25','2026-06-26']
for name, d in dirs.items():
    bk = os.path.join(d, '_backup_test_106')
    os.makedirs(bk, exist_ok=True)
    for f in os.listdir(d):
        if any(dt in f for dt in test_dates) and '_backup' not in f:
            shutil.move(os.path.join(d,f), os.path.join(bk,f))
            print(f'moved {name}: {f}')
"
```

Reprocess:
```
python -m etl.hedgeye_fetch --backfill 2026-06-24
```

Load emitted files:
```python
python -c "
import os
os.chdir(r'C:\\Ashok\\Invest\\Projects\\trading-dashboard')
from dotenv import load_dotenv; load_dotenv()
from etl.etl_load import load_one_file
from etl.db import session_scope

dirs = [
    r'C:\Ashok\Investing\Stocks\Call\Archive',
    r'C:\Ashok\Investing\Stocks\ETFChange\Archive',
    r'C:\Ashok\Investing\Stocks\IIChange\Archive',
]
test_dates = ['2026-06-24','2026-06-25','2026-06-26']
for d in dirs:
    if not os.path.isdir(d): continue
    for f in sorted(os.listdir(d)):
        if any(dt in f for dt in test_dates) and '_backup' not in f:
            path = os.path.join(d, f)
            print(f'Loading: {path}')
            with session_scope() as s:
                result = load_one_file(s, path, no_derive=False)
                print(f'  {result}')
"
```

---

## Step 4 — Verify

**ETFChange xlsx — description populated:**
```python
python -c "
import openpyxl, os
for dt in ['2026-06-24','2026-06-25','2026-06-26']:
    path = rf'C:\Ashok\Investing\Stocks\ETFChange\Archive\ETFChange {dt}.xlsx'
    if not os.path.exists(path): continue
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    print(f'{dt}: {ws.max_row-1} rows')
    for r in range(2, ws.max_row+1):
        print(f'  {ws.cell(r,1).value} | {ws.cell(r,2).value} | {ws.cell(r,3).value} | {ws.cell(r,4).value} | {ws.cell(r,5).value}')
"
```
Expect: Description (col 2) non-empty for each row.

**IIChange xlsx — description populated:**
```python
python -c "
import openpyxl, os
for dt in ['2026-06-24','2026-06-25','2026-06-26']:
    path = rf'C:\Ashok\Investing\Stocks\IIChange\Archive\IIChange {dt}.xlsx'
    if not os.path.exists(path): continue
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    print(f'{dt}: {ws.max_row-1} rows')
    for r in range(2, ws.max_row+1):
        print(f'  {[ws.cell(r,c).value for c in range(1,6)]}')
"
```

**Call CSV — Outlook is BULLISH/BEARISH/NEUTRAL:**
```python
python -c "
import csv, os
for dt in ['2026-06-24','2026-06-26']:
    path = rf'C:\Ashok\Investing\Stocks\Call\Archive\call {dt}.csv'
    if not os.path.exists(path): continue
    with open(path) as f:
        rows = list(csv.DictReader(f))
    print(f'{dt}: {len(rows)} rows')
    for r in rows[:5]: print(f'  {r}')
    outlooks = set(r.get('Outlook','') for r in rows)
    print(f'  distinct Outlook values: {outlooks}')
    mods = set(r.get('Outlook Modifier','') for r in rows)
    print(f'  distinct Modifiers: {mods}')
"
```
Expect: Outlook values = {BULLISH, BEARISH, NEUTRAL}. Modifier values = subset of {long bench, short bench, best idea long, best idea short, ''}.

**DB spot-check:**
```python
python -c "
import os; os.chdir(r'C:\\Ashok\\Invest\\Projects\\trading-dashboard')
from dotenv import load_dotenv; load_dotenv()
from etl.db import session_scope
from sqlalchemy import text
with session_scope() as s:
    # ETFChange descriptions
    r = s.execute(text(\"SELECT event_date, symbol, description, outlook, change_str FROM hist_etfchg WHERE event_date BETWEEN '2026-06-24' AND '2026-06-26' ORDER BY event_date, symbol\")).fetchall()
    print(f'hist_etfchg ({len(r)} rows):')
    for row in r: print(' ', row)
    # IIChange descriptions
    r = s.execute(text(\"SELECT event_date, symbol, description, outlook, change_str FROM hist_iichg WHERE event_date BETWEEN '2026-06-24' AND '2026-06-26' ORDER BY event_date, symbol\")).fetchall()
    print(f'hist_iichg ({len(r)} rows):')
    for row in r: print(' ', row)
    # Call outlooks
    r = s.execute(text(\"SELECT snapshot_date, symbol, outlook, outlook_modifier FROM hist_call WHERE snapshot_date BETWEEN '2026-06-24' AND '2026-06-26' ORDER BY snapshot_date, symbol LIMIT 10\")).fetchall()
    print(f'hist_call sample:')
    for row in r: print(' ', row)
    # Distinct outlooks in call
    r = s.execute(text(\"SELECT DISTINCT outlook, outlook_modifier FROM hist_call WHERE snapshot_date BETWEEN '2026-06-24' AND '2026-06-26' ORDER BY 1,2\")).fetchall()
    print('distinct call outlook/modifier:', r)
"
```
Expect:
- hist_etfchg.description non-null for all rows
- hist_iichg.description non-null for all rows
- hist_call.outlook ∈ {BULLISH, BEARISH, NEUTRAL}
- hist_call.outlook_modifier ∈ {long bench, short bench, best idea long, best idea short, None} or similar

---

## Constraints
- PowerShell max 965 bytes — write longer scripts to temp files
- No commits
- Use Python/SQLAlchemy for DB ops
- hist_call PK is (snapshot_date, symbol) — already in ON CONFLICT logic via insert_upsert
