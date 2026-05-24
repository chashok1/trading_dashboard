from config.settings import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.sqlalchemy_url)

with engine.connect() as conn:
    # Get a drv table with symbol
    result = conn.execute(text("""
        SELECT table_name FROM information_schema.columns
        WHERE column_name = 'symbol' AND table_name LIKE 'drv_%'
        LIMIT 1
    """))
    table_name = result.scalar()
    print(f"Testing table: {table_name}")

    if table_name:
        # Test 1: Count all rows
        result1 = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        total_count = result1.scalar()
        print(f"Total rows: {total_count}")

        # Test 2: Count rows with symbol filter
        result2 = conn.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE symbol = :sym"), {'sym': 'AAPL'})
        aapl_count = result2.scalar()
        print(f"Rows with symbol='AAPL': {aapl_count}")

        # Test 3: Check if as_of_date filter works
        result3 = conn.execute(text(f"SELECT MAX(as_of_date) FROM {table_name}"))
        latest_date = result3.scalar()
        print(f"Latest date: {latest_date}")

        # Test 4: Filter by date
        if latest_date:
            result4 = conn.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE as_of_date = :d"), {'d': latest_date})
            date_count = result4.scalar()
            print(f"Rows on {latest_date}: {date_count}")

        # Test 5: Filter by both date and symbol
        if latest_date:
            result5 = conn.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE as_of_date = :d AND symbol = :sym"),
                                  {'d': latest_date, 'sym': 'AAPL'})
            filtered_count = result5.scalar()
            print(f"Rows with date={latest_date} AND symbol=AAPL: {filtered_count}")
