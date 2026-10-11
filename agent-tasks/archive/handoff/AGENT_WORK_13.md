# AGENT_WORK — Developer pointer

## Active task — TASK_103 (fix RR + PS parsers so all 5 feeds emit files)

**Goal:** After TASK_102's clean reprocess, IIChange/ETFChange/call emit files correctly
but **RR and PS produce 0 rows** — their parsers can't read the actual email body.
Fix both parsers so all 5 feeds emit workbook files to their Archive folders.

### RR parser issue
`parse_risk_range` in `etl/hedgeye/parsers.py` uses a `_RR_HEAD` regex that doesn't
match the actual email plaintext for the Jun 24/25 emails (only Jun 26 partially worked
via a separate code path). Fix the regex/parser logic so it extracts rows from the real
email body.

### PS parser issue  
`parse_portfolio_solutions` uses `_html_tables` to find an HTML rank table — but the
PS email body format doesn't match. Fix the HTML extraction so it finds the actual table.

### How to diagnose
Read the raw email body from the mailbox for a RR and PS email, print it, and update
the parser to match the real format. Use:
```python
python -m etl.hedgeye_fetch --dry-run --backfill 2026-06-24
```
Or fetch the raw body directly:
```python
from etl.hedgeye.source import fetch_messages
from etl.hedgeye.classify import classify
msgs = fetch_messages(since_date=..., until_date=...)
for m in msgs:
    et = classify(m)
    if et in ('risk_range', 'portfolio_solutions'):
        print('=== EMAIL TYPE:', et)
        print('PLAIN:', m.plain_text[:3000])
        print('HTML tables:', m.html[:2000])
```

### After fixing parsers
1. Clear the ledger + meta_file_processed + hist rows for the 5 feeds (2026-06-24→26)
2. Run: `python -m etl.hedgeye_fetch --backfill 2026-06-24`
3. Manually load any emitted files via `etl_load.load_one_file` if scheduler not running
4. **Confirm ALL 5 Archive files exist**: RR 2026-06-26.xlsx, IIChange 2026-06-24.xlsx,
   ETFChange 2026-06-24.xlsx, PS 2026-06-26.xlsx, call 2026-06-24.csv (or similar)
5. Confirm DB rows populated for all 5 feeds

### Archive folder paths (from ref_load_files)
- RR:        C:\Ashok\Investing\Stocks\RR\Archive\
- IIChange:  C:\Ashok\Investing\Stocks\IIChange\Archive\
- ETFChange: C:\Ashok\Investing\Stocks\ETFChange\Archive\
- PS:        C:\Ashok\Investing\Stocks\PS\Archive\
- Call:      C:\Ashok\Investing\Stocks\Call\Archive\

Archive AGENT_WORK.md → AGENT_WORK_13.md. Log to DEV_HANDOFF.md, end ALL_DONE. No commits.
