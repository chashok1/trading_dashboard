import psycopg
from config.settings import settings
from pathlib import Path

sql_file = Path("db/20_data_filter_logic.sql")

if not sql_file.exists():
    print(f"ERROR: {sql_file} not found")
    exit(1)

print(f"Reading {sql_file}...")
sql_content = sql_file.read_text()

print(f"Connecting to {settings.pg_database}...")
conn = psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password
)

try:
    with conn.cursor() as cur:
        print("Executing SQL...")
        cur.execute(sql_content)
        conn.commit()
        print("SUCCESS: SQL executed and committed")
except Exception as e:
    conn.rollback()
    print(f"ERROR: {e}")
    exit(1)
finally:
    conn.close()
