"""Check what was loaded from II 2026-05-11.xlsx into hist_ii."""
import psycopg
from datetime import datetime
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check what's in hist_ii for 2026-05-11
        cur.execute('''
            SELECT COUNT(*) FROM hist_ii WHERE snapshot_date = '2026-05-11'
        ''')
        count = cur.fetchone()[0]
        print(f'[DB] hist_ii for 2026-05-11: {count} rows')

        # Show the actual data
        cur.execute('''
            SELECT * FROM hist_ii
            WHERE snapshot_date = '2026-05-11'
            ORDER BY symbol
        ''')
        rows = cur.fetchall()
        print(f'\nDetailed data ({len(rows)} rows):')
        # Get column names
        col_names = [desc[0] for desc in cur.description]
        for row in rows:
            print(f'  {dict(zip(col_names, row))}')

        # Check for duplicates
        cur.execute('''
            SELECT symbol, COUNT(*) as cnt
            FROM hist_ii
            WHERE snapshot_date = '2026-05-11'
            GROUP BY symbol
            HAVING COUNT(*) > 1
        ''')
        dups = cur.fetchall()
        if dups:
            print(f'\nDuplicates found:')
            for dup in dups:
                print(f'  {dup[0]}: {dup[1]} copies')
        else:
            print(f'\nNo duplicates found')

        # Check meta_etl_run for this file
        cur.execute('''
            SELECT file_path, status, rows_read, rows_inserted, rows_skipped
            FROM meta_etl_run
            WHERE file_path LIKE '%II 2026-05-11%'
            ORDER BY started_at DESC
            LIMIT 1
        ''')
        meta = cur.fetchone()
        if meta:
            print(f'\nETL log for this file:')
            print(f'  Path: {meta[0]}')
            print(f'  Status: {meta[1]}')
            print(f'  Read: {meta[2]}, Inserted: {meta[3]}, Skipped: {meta[4]}')
        else:
            print(f'\nNo ETL log found for this file')
