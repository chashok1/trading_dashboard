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
            column_name,
            concept,
            pipeline_stage,
            source_table,
            source_expr
        FROM ref_ma_columns
        WHERE drv_cat_table = 'drv_cat_atomic_input'
        AND source_expr IS NULL
        ORDER BY column_name
    """)

    rows = cur.fetchall()
    print(f"139 Missing Source Expressions in drv_cat_atomic_input:\n")
    print(f"{'Column Name':<35} | {'Concept':<25} | {'Stage':<15} | Source Table")
    print("-" * 100)

    for col_name, concept, stage, src_table, expr in rows:
        print(f"{col_name:<35} | {concept or 'N/A':<25} | {stage or 'N/A':<15} | {src_table or 'N/A'}")

conn.close()
