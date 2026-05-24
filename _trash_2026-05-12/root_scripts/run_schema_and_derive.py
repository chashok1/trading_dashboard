import psycopg
from config.settings import settings
from pathlib import Path
import subprocess
import sys

# Step 1: Apply the new schema
sql_file = Path("db/15_drv2_tables.sql")

if not sql_file.exists():
    print(f"ERROR: {sql_file} not found")
    sys.exit(1)

print("=" * 80)
print("STEP 1: Applying new schema (db/15_drv2_tables.sql)")
print("=" * 80)

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
        print("Executing schema SQL...")
        cur.execute(sql_content)
        conn.commit()
        print("[OK] SUCCESS: Schema applied\n")
except Exception as e:
    conn.rollback()
    print(f"[ERROR] {e}")
    sys.exit(1)
finally:
    conn.close()

# Step 2: Re-derive
print("=" * 80)
print("STEP 2: Re-deriving data (python -m etl.derive)")
print("=" * 80)

try:
    result = subprocess.run(
        [sys.executable, "-m", "etl.derive"],
        cwd=Path.cwd(),
        capture_output=False,
        text=True
    )
    if result.returncode != 0:
        print(f"\n[ERROR] Derive failed with exit code {result.returncode}")
        sys.exit(1)
    print("\n[OK] SUCCESS: Derivation complete")
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL STEPS COMPLETED SUCCESSFULLY")
print("=" * 80)
