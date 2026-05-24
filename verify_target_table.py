"""Verify target_table column was added and backfilled in ref_load_files."""
import psycopg
from config.settings import settings

with psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password,
) as conn:
    with conn.cursor() as cur:
        # Check the column exists
        cur.execute('''
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'ref_load_files'
            ORDER BY ordinal_position
        ''')
        print('=== ref_load_files columns ===')
        for col in cur.fetchall():
            print(f'  {col[0]}: {col[1]}')

        # Show the data
        print('\n=== Sample data ===')
        cur.execute('SELECT file_type, target_tab, target_table FROM ref_load_files LIMIT 10')
        for row in cur.fetchall():
            print(f'  {row[0]:20} -> {row[1]:15} -> {row[2]}')

        # Count rows with target_table populated
        cur.execute('SELECT COUNT(*) FROM ref_load_files WHERE target_table IS NOT NULL')
        count = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM ref_load_files')
        total = cur.fetchone()[0]
        print(f'\n=== Backfill status ===')
        print(f'  {count}/{total} rows have target_table populated')
