from config.settings import settings
from sqlalchemy import create_engine, text, inspect

engine = create_engine(settings.sqlalchemy_url)
inspector = inspect(engine)

# Check if drv_outlook_action exists
tables = inspector.get_table_names()
if 'drv_outlook_action' in tables:
    print("[OK] drv_outlook_action table EXISTS")

    # Check data
    with engine.connect() as conn:
        result = conn.execute(text('SELECT COUNT(*) FROM drv_outlook_action'))
        total = result.scalar()
        print(f"  Total rows: {total}")

        if total > 0:
            result2 = conn.execute(text('SELECT MAX(as_of_date), COUNT(DISTINCT as_of_date) FROM drv_outlook_action'))
            latest, distinct = result2.fetchone()
            print(f"  Latest date: {latest}")
            print(f"  Distinct dates: {distinct}")

            result3 = conn.execute(text('SELECT as_of_date, COUNT(*) FROM drv_outlook_action GROUP BY as_of_date ORDER BY as_of_date DESC LIMIT 5'))
            print('\n  Rows by date (latest 5):')
            for row in result3:
                print(f'    {row[0]}: {row[1]} rows')
else:
    print("[ERROR] drv_outlook_action table DOES NOT EXIST")
    print("\n  Available drv_ tables:")
    for t in sorted([x for x in tables if x.startswith('drv_')]):
        print(f"    - {t}")
