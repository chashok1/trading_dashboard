import psycopg
from config.settings import Settings

settings = Settings()
conn = psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password
)

with conn.cursor() as cur:
    cur.execute("""
        SELECT
            drv_cat_table,
            COUNT(*) as null_count
        FROM ref_ma_columns
        WHERE source_expr IS NULL
        GROUP BY drv_cat_table
        ORDER BY null_count DESC
    """)

    rows = cur.fetchall()
    print(f"Summary: NULL source_expr by Category Table\n")
    print(f"{'Category Table':<40} | Missing Columns")
    print("-" * 60)

    total = 0
    for table_name, count in rows:
        print(f"{table_name:<40} | {count:>5}")
        total += count

    print("-" * 60)
    print(f"{'TOTAL':<40} | {total:>5}")

conn.close()
