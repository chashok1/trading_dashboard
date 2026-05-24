from config.settings import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.sqlalchemy_url)

with engine.connect() as conn:
    print("Derivations run per date (last 10 days):\n")

    # Get unique dates from the last 10 days
    result = conn.execute(text("""
        SELECT DISTINCT as_of_date FROM meta_derived_run
        WHERE as_of_date >= CURRENT_DATE - INTERVAL '10 days'
        ORDER BY as_of_date DESC
    """))

    for (d,) in result:
        print(f"{d}:")

        # Get all target tables for this date
        result2 = conn.execute(text("""
            SELECT target_table, COUNT(*), SUM(rows_built) as total_rows, MAX(finished_at)
            FROM meta_derived_run
            WHERE as_of_date = :d
            GROUP BY target_table
            ORDER BY MAX(finished_at) DESC
        """), {"d": d})

        for table, count, total_rows, last_run in result2:
            print(f"  - {table}: {count} run(s), {total_rows} rows total")
        print()
