from config.settings import settings
from sqlalchemy import create_engine, text

engine = create_engine(settings.sqlalchemy_url)

with engine.connect() as conn:
    print("meta_derived_run entries for drv_actionable on 2026-05-11:\n")

    result = conn.execute(text("""
        SELECT run_id, started_at, finished_at, as_of_date, target_table, rows_built, status, error_msg
        FROM meta_derived_run
        WHERE as_of_date = '2026-05-11' AND target_table = 'drv_actionable'
        ORDER BY started_at ASC
    """))

    for row in result:
        run_id, started, finished, date, table, rows, status, error = row
        print(f"Run {run_id}:")
        print(f"  Started: {started}")
        print(f"  Finished: {finished}")
        print(f"  Rows built: {rows}")
        print(f"  Status: {status}")
        if error:
            print(f"  Error: {error}")
        print()

    print("\nActual drv_actionable rows for 2026-05-11:")
    result2 = conn.execute(text('SELECT COUNT(*) FROM drv_actionable WHERE as_of_date = :d'), {"d": "2026-05-11"})
    print(f"  {result2.scalar()} rows")

    print("\nAll drv_actionable dates:")
    result3 = conn.execute(text('SELECT DISTINCT as_of_date FROM drv_actionable ORDER BY as_of_date DESC'))
    for (d,) in result3:
        print(f"  {d}")
