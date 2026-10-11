# AGENT_WORK — Developer pointer

## Active task — TASK_104 (RR OutBucket symbols: missing Description + zero prices)

**Symptom (Ashok):** In the emitted RR xlsx, OutBucket symbols are either missing entirely
OR appear with a blank Description column; their BUY TRADE / SELL TRADE / Prev Close are
zero (that zero part is correct — OutBucket symbols have no price targets).

**Root cause to find:** The RR email plaintext has two kinds of symbol entries:
- Normal symbols: SYMBOL (OUTLOOK) / Asset Name  BUY  SELL  PREV
- OutBucket symbols: likely SYMBOL (#OUTBUCKET) / Asset Name  0  0  0  (or no price line)

The parser in `etl/hedgeye/parsers.py::parse_risk_range` probably strips `#OUTBUCKET` from
the outlook field and possibly misses the Description (asset name) for those rows.

## Steps

1. **Print the raw email body** for a RR email to see the exact OutBucket symbol format:
   ```python
   # fetch raw RR email and print the plaintext around OutBucket symbols
   python -m etl.hedgeye_fetch --dry-run  # or fetch directly via IMAP
   ```
   Or read the body from a cached/fetched message. If --dry-run isn't supported, fetch
   directly via IMAP (see TASK_103 fetch script pattern in prior DEV_HANDOFF).

2. **Read `parse_risk_range` in `etl/hedgeye/parsers.py`** completely. Understand:
   - How it parses SYMBOL (OUTLOOK) lines
   - How it parses the Description (asset name) line that follows
   - What it does when outlook is `#OUTBUCKET` or contains `#OUTBUCKET`

3. **Fix the parser** so OutBucket symbols:
   - Are included in the output rows (not dropped)
   - Have their Description populated (the asset name from the email)
   - Have BUY TRADE = 0, SELL TRADE = 0, Prev Close = 0 (or None → 0 in the xlsx)
   - Have Outlook = the stripped outlook value (e.g. `BEARISH` or `NEUTRAL` — whatever
     the email shows; if the email just says `#OUTBUCKET`, use that as the Outlook value)

4. **Verify the fix** by doing a clean reprocess:
   - Clear meta_hedgeye_msg for risk_range, meta_file_processed for RR (test dates),
     delete hist_rr rows for test dates, move/delete existing RR Archive files for
     test dates to a backup folder
   - Run: `python -m etl.hedgeye_fetch --backfill 2026-06-24`
   - Manually load the generated RR xlsx files
   - Open / inspect the generated RR 2026-06-26.xlsx: ALL symbols should be present,
     OutBucket rows should have a populated Description, prices 0 or None is OK

5. **Check DB**: `SELECT symbol, description, outlook, buy_trade, sell_trade, prev_close
   FROM hist_rr WHERE snapshot_date = '2026-06-26' AND (buy_trade = 0 OR buy_trade IS NULL)
   ORDER BY symbol;` → OutBucket symbols should appear with their description.

Archive AGENT_WORK.md → AGENT_WORK_14.md. Log to DEV_HANDOFF.md, end ALL_DONE. No commits.
