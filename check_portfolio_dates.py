from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    print("Portfolio data availability:\n")

    # Check hist_f (Fidelity)
    print("hist_f (Fidelity):")
    result = s.execute(text("""
        SELECT snapshot_date, COUNT(DISTINCT account_number) as accounts, COUNT(*) as rows
        FROM hist_f
        GROUP BY snapshot_date
        ORDER BY snapshot_date DESC
        LIMIT 5
    """))
    for row in result:
        print(f"  {row[0]}: {row[1]} accounts, {row[2]} positions")

    # Check hist_cs (Schwab)
    print("\nhist_cs (Charles Schwab):")
    result = s.execute(text("""
        SELECT snapshot_date, COUNT(DISTINCT account) as accounts, COUNT(*) as rows
        FROM hist_cs
        GROUP BY snapshot_date
        ORDER BY snapshot_date DESC
        LIMIT 5
    """))
    for row in result:
        print(f"  {row[0]}: {row[1]} accounts, {row[2]} positions")

    print("\n" + "="*60)
    print("PROBLEM:")
    print("  Portfolio data last updated: 2026-04-25")
    print("  Dashboard showing: Yesterday's date (2026-05-13)")
    print("  But data is from: 2026-04-25 (20 days old!)")
    print("\nSOLUTION:")
    print("  Need to load F and CS files for today (2026-05-15)")
    print("  F file: C:\\Ashok\\Investing\\Stocks\\Fidelity\\Archive\\F YYYY-MM-DD.csv")
    print("  CS file: C:\\Ashok\\Investing\\Stocks\\CS\\Archive\\CS YYYY-MM-DD.csv")
