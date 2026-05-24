"""
Force a clean reload of the CS positions CSV:
  1. Wipe meta_file_processed audit for that file
  2. Delete existing hist_cs rows for the file's snapshot date
  3. Call load_cs_positions_csv directly

Run from project root:
    python force_cs_reload.py
"""
import os, sys
from sqlalchemy import text
from config.settings import settings
from etl.db import session_scope

CSV = r"C:\Ashok\Investing\Stocks\CS\Archive\CS 2026-05-18.csv"

if not os.path.exists(CSV):
    print(f"ERROR: file not found: {CSV}")
    sys.exit(1)

# Import the loader fresh from disk
import importlib, etl.load_raw
importlib.reload(etl.load_raw)
from etl.load_raw import load_cs_positions_csv

with session_scope() as s:
    # 1) Clear audit so etl_load.already_processed returns False on future runs
    deleted_audit = s.execute(text(
        "DELETE FROM meta_file_processed WHERE LOWER(file_path) = LOWER(:p)"
    ), {"p": CSV}).rowcount
    print(f"meta_file_processed rows removed: {deleted_audit}")

    # 2) Wipe existing hist_cs rows for this snapshot date so we're rebuilding cleanly
    deleted_hist = s.execute(text(
        "DELETE FROM hist_cs WHERE snapshot_date = '2026-05-18' AND source_file = :sf"
    ), {"sf": os.path.basename(CSV)}).rowcount
    print(f"hist_cs rows removed for 2026-05-18: {deleted_hist}")

    # 3) Run loader directly
    read, ins, skp = load_cs_positions_csv(s, CSV, os.path.basename(CSV))
    print(f"\nloader returned: read={read}  ins={ins}  skp={skp}")

    # 4) Re-query to confirm cash rows now present
    rows = s.execute(text("""
        SELECT account, symbol, security_type, market_value
          FROM hist_cs
         WHERE snapshot_date = '2026-05-18'
           AND (symbol = 'Cash & Cash Investments'
                OR security_type = 'Cash and Money Market')
         ORDER BY account
    """)).all()
    print(f"\nCash rows now in hist_cs for 2026-05-18: {len(rows)}")
    for r in rows:
        print(f"  acct={r.account!r}  symbol={r.symbol!r}  "
              f"st={r.security_type!r}  mv={r.market_value}")
