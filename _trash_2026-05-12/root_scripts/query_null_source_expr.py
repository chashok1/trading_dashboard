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
    # Get count of NULL source_expr entries
    cur.execute("SELECT COUNT(*) FROM ref_ma_columns WHERE source_expr IS NULL")
    total_count = cur.fetchone()[0]

    # Get the actual rows
    cur.execute("""
        SELECT
            column_name,
            drv_cat_table,
            pipeline_stage,
            concept,
            source_table
        FROM ref_ma_columns
        WHERE source_expr IS NULL
        ORDER BY drv_cat_table, column_name
    """)

    rows = cur.fetchall()
    print(f"Total columns with NULL source_expr: {total_count}\n")
    print(f"{'Category Table':<35} | {'Column Name':<30} | {'Concept':<25} | Source Table")
    print("-" * 120)

    current_table = None
    table_count = 0

    for row in rows:
        col_name, cat_table, stage, concept, src_table = row

        if cat_table != current_table:
            if current_table is not None:
                print(f"  [{table_count} columns in {current_table}]")
            current_table = cat_table
            table_count = 0

        table_count += 1
        print(f"{cat_table:<35} | {col_name:<30} | {concept or 'N/A':<25} | {src_table or 'N/A'}")

    if current_table is not None:
        print(f"  [{table_count} columns in {current_table}]")

conn.close()
