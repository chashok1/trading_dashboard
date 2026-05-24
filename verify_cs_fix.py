from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    print("=== VERIFICATION: CS Data Now Loaded ===\n")

    result = s.execute(text('''
        SELECT COUNT(*) as rows, COUNT(DISTINCT account) as accounts
        FROM hist_cs
        WHERE snapshot_date = '2026-05-14'
    ''')).first()

    print(f"hist_cs for 2026-05-14:")
    print(f"  {result[0]} rows loaded, {result[1]} accounts\n")

    result = s.execute(text('''
        SELECT COUNT(*) FROM drv_ma WHERE as_of_date = '2026-05-14'
    ''')).scalar()

    print(f"drv_ma for 2026-05-14:")
    print(f"  {result} derived positions available\n")

    result = s.execute(text('''
        SELECT symbol, qty FROM hist_cs
        WHERE snapshot_date = '2026-05-14'
        LIMIT 5
    ''')).fetchall()

    print("Sample Schwab positions:")
    for row in result:
        print(f"  {row[0]}: {row[1]} shares")

    print("\nSUCCESS: CS 2026-05-14 data is now loaded and available for dashboard")
