from config.settings import settings
from etl.db import session_scope
from sqlalchemy import text

with session_scope() as s:
    # Check what v_available_dates returns
    print("Available dates from v_available_dates:")
    result = s.execute(text("""
        SELECT as_of_date
        FROM v_available_dates
        ORDER BY as_of_date DESC
        LIMIT 5
    """)).fetchall()

    if result:
        for row in result:
            print(f"  {row[0]}")
    else:
        print("  [NO DATES AVAILABLE]")

    # Check raw drv_ma dates
    print("\nDates in drv_ma:")
    raw = s.execute(text("""
        SELECT DISTINCT as_of_date
        FROM drv_ma
        ORDER BY as_of_date DESC
        LIMIT 5
    """)).fetchall()

    for row in raw:
        print(f"  {row[0]}")

    # Check the latest date
    latest = s.execute(text("""
        SELECT MAX(as_of_date) FROM drv_ma
    """)).scalar()

    print(f"\nLatest date available: {latest}")
    print(f"This should be the DEFAULT shown in dashboard date picker")
