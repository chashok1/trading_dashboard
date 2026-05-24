from config.settings import settings
from sqlalchemy import create_engine, text, inspect

engine = create_engine(settings.sqlalchemy_url)
inspector = inspect(engine)

# Get all tables
all_tables = inspector.get_table_names()
drv_tables = sorted([t for t in all_tables if t.startswith('drv_')])
hist_tables = sorted([t for t in all_tables if t.startswith('hist_')])
ref_tables = sorted([t for t in all_tables if t.startswith('ref_')])

print("=" * 70)
print("DATA AVAILABLE FOR 2026-05-11")
print("=" * 70)

with engine.connect() as conn:
    # Check drv tables
    print("\nDERIVED TABLES (drv_*):")
    print("-" * 70)
    for table in drv_tables:
        # Get the date column name
        cols = inspector.get_columns(table)
        date_col = None
        for col in cols:
            if col['name'] in ('as_of_date', 'snapshot_date', 'event_date'):
                date_col = col['name']
                break

        if date_col:
            result = conn.execute(text(f'SELECT COUNT(*) FROM {table} WHERE {date_col} = :d'),
                                 {'d': '2026-05-11'})
            count = result.scalar()
            if count and count > 0:
                print(f"  [OK] {table}: {count:,} rows")
            else:
                print(f"    {table}: 0 rows")
        else:
            result = conn.execute(text(f'SELECT COUNT(*) FROM {table}'))
            count = result.scalar()
            print(f"  ? {table}: {count:,} rows (no date column)")

    # Check hist tables
    print("\nRAW HISTORY TABLES (hist_*):")
    print("-" * 70)
    for table in hist_tables:
        cols = inspector.get_columns(table)
        date_col = None
        for col in cols:
            if col['name'] in ('as_of_date', 'snapshot_date', 'event_date'):
                date_col = col['name']
                break

        if date_col:
            result = conn.execute(text(f'SELECT COUNT(*) FROM {table} WHERE {date_col} = :d'),
                                 {'d': '2026-05-11'})
            count = result.scalar()
            if count and count > 0:
                print(f"  [OK] {table}: {count:,} rows")
            else:
                print(f"    {table}: 0 rows")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    result = conn.execute(text("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_type = 'BASE TABLE'
          AND (table_name LIKE 'drv_%' OR table_name LIKE 'hist_%')
    """))

    has_data_count = 0
    no_data_count = 0

    for (tbl,) in result:
        cols = inspector.get_columns(tbl)
        date_col = None
        for col in cols:
            if col['name'] in ('as_of_date', 'snapshot_date', 'event_date'):
                date_col = col['name']
                break

        if date_col:
            r = conn.execute(text(f'SELECT COUNT(*) FROM {tbl} WHERE {date_col} = :d'),
                            {'d': '2026-05-11'})
            count = r.scalar()
            if count and count > 0:
                has_data_count += 1
            else:
                no_data_count += 1

    print(f"Tables WITH data for 2026-05-11: {has_data_count}")
    print(f"Tables WITHOUT data for 2026-05-11: {no_data_count}")
