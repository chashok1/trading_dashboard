import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_database,
    user=settings.pg_user, password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Delete all transaction data
        cur.execute("DELETE FROM hist_cst")
        tx_count = cur.rowcount
        print(f"[OK] Deleted {tx_count} rows from hist_cst")

        # Delete all realized gains
        cur.execute("DELETE FROM drv_cs_realized_gain")
        rg_count = cur.rowcount
        print(f"[OK] Deleted {rg_count} rows from drv_cs_realized_gain")

        # Clear file processing record for CS transactions
        cur.execute("DELETE FROM meta_file_processed WHERE file_type = 'CST'")
        fp_count = cur.rowcount
        print(f"[OK] Deleted {fp_count} rows from meta_file_processed (cs_transactions)")

        # Clear ETL run records for CS transactions
        cur.execute("DELETE FROM meta_etl_run WHERE target_tab = 'hist_cst'")
        er_count = cur.rowcount
        print(f"[OK] Deleted {er_count} rows from meta_etl_run (hist_cst)")

        conn.commit()
        print("\n[DONE] All transaction data and derived gains have been cleared")
