import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Delete the old transactions with wrong account name
        cur.execute("DELETE FROM hist_cst WHERE account = 'Rollover_IRA_XXX892'")
        print(f"Deleted {cur.rowcount} rows with wrong account name")

        # Delete the derived realized gains (they'll be recalculated)
        cur.execute("DELETE FROM drv_cs_realized_gain")
        print(f"Deleted {cur.rowcount} rows from drv_cs_realized_gain")

        # Mark the file as not processed so it can be reloaded
        cur.execute("DELETE FROM meta_file_processed WHERE file_type = 'CST'")
        print(f"Cleared {cur.rowcount} rows from meta_file_processed")

        conn.commit()
        print("Done")
