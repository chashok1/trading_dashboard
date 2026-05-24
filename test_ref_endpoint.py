from config.settings import settings
from sqlalchemy import create_engine, text
from api.routers.ref import get_ref_table
from etl.db import session_scope

# Test the /api/ref/{table_name} endpoint
try:
    result = get_ref_table('ref_asset_allocation', date=None, limit=10, offset=0)
    print(f"Successfully fetched: {result.table}")
    print(f"Columns: {[c.name for c in result.columns[:5]]}")
    print(f"Total rows: {result.total}")
    print(f"Returned rows: {len(result.rows)}")
    if result.rows:
        print(f"First row keys: {list(result.rows[0].keys())}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
