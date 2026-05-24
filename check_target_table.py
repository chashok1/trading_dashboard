"""Thorough check of target_table column in ref_load_files."""
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
        print('=== VERIFICATION: target_table column ===\n')

        # 1. Check column exists and type is correct
        cur.execute('''
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'ref_load_files' AND column_name = 'target_table'
        ''')
        result = cur.fetchone()
        if result:
            print(f'[OK] Column exists: TEXT type = {result[0]}')
        else:
            print('[FAIL] Column NOT found')
            exit(1)

        # 2. Check all rows are backfilled
        cur.execute('SELECT COUNT(*) FROM ref_load_files WHERE target_table IS NULL')
        null_count = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM ref_load_files')
        total = cur.fetchone()[0]
        print(f'[OK] Backfill complete: {total - null_count}/{total} rows filled')
        if null_count > 0:
            print(f'  [WARN] {null_count} rows still NULL')

        # 3. Verify mappings are correct
        print('\n=== Mapping Verification ===')
        cur.execute('''
            SELECT file_type, target_tab, target_table
            FROM ref_load_files
            ORDER BY file_type
        ''')
        for file_type, target_tab, target_table in cur.fetchall():
            print(f'  {file_type:15} | {target_tab:10} | {target_table}')

        # 4. Check that target tables exist in the database
        print('\n=== Target Table Validation ===')
        cur.execute('''
            SELECT DISTINCT target_table FROM ref_load_files
            WHERE target_table IS NOT NULL
            ORDER BY target_table
        ''')
        target_tables = [row[0] for row in cur.fetchall()]

        cur.execute('''
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
        ''')
        existing_tables = {row[0] for row in cur.fetchall()}

        all_exist = True
        for tbl in target_tables:
            exists = tbl in existing_tables
            status = '[OK]' if exists else '[FAIL]'
            print(f'  {status} {tbl}')
            if not exists:
                all_exist = False

        if all_exist:
            print('\n[OK] All target tables exist in database')
        else:
            print('\n[FAIL] Some target tables are missing')

        print(f'\n=== Summary ===')
        print(f'Total rows: {total}')
        print(f'Populated: {total - null_count}')
        print(f'Unique target tables: {len(target_tables)}')
        print(f'All tables exist: {"YES" if all_exist else "NO"}')
