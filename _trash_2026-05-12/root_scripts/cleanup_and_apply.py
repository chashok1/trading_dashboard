import psycopg
from config.settings import settings
from pathlib import Path
import subprocess
import sys

conn = psycopg.connect(
    host=settings.pg_host,
    port=settings.pg_port,
    dbname=settings.pg_database,
    user=settings.pg_user,
    password=settings.pg_password
)

# Step 0: Drop existing drv2_* tables/views if they exist
print("=" * 80)
print("STEP 0: Cleaning up existing drv2_* objects")
print("=" * 80)

drv2_tables = [
    "drv2_call", "drv2_etf", "drv2_etfchg", "drv2_holdings",
    "drv2_ii", "drv2_ma_thin", "drv2_ps", "drv2_rr", "drv2_ssh",
    "drv2_ssl", "drv2_sss", "drv2_td", "drv2_tl", "drv2_tw"
]

try:
    with conn.cursor() as cur:
        for tbl in drv2_tables:
            # Drop as table, ignore if doesn't exist or is a view
            try:
                cur.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE;")
            except:
                try:
                    cur.execute(f"DROP VIEW IF EXISTS {tbl} CASCADE;")
                except:
                    pass  # Object doesn't exist
        conn.commit()
        print("[OK] Cleaned up existing objects\n")
except Exception as e:
    conn.rollback()
    print(f"[ERROR] Cleanup failed: {e}")
    sys.exit(1)

# Step 1: Apply the new schema
sql_file = Path("db/15_drv2_tables.sql")

if not sql_file.exists():
    print(f"ERROR: {sql_file} not found")
    sys.exit(1)

print("=" * 80)
print("STEP 1: Applying new schema (db/15_drv2_tables.sql)")
print("=" * 80)

sql_content = sql_file.read_text()

try:
    with conn.cursor() as cur:
        print("Executing schema SQL...")
        cur.execute(sql_content)
        conn.commit()
        print("[OK] Schema applied\n")
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
    print("\n[OK] Derivation complete")
except Exception as e:
    print(f"[ERROR] {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL STEPS COMPLETED SUCCESSFULLY")
print("=" * 80)
