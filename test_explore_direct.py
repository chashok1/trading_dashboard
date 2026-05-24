"""Test the Explore endpoint directly using FastAPI test client."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

print("Testing /api/data/hist_ii endpoint for 2026-05-11\n")

# Test hist_ii with date filter
response = client.get("/api/data/hist_ii?limit=200&offset=0&date=2026-05-11")

print(f"Status: {response.status_code}")

if response.status_code == 200:
    data = response.json()

    columns = data.get('columns', [])
    col_names = [c['name'] for c in columns]
    print(f"Columns: {col_names}")

    total = data.get('total', 0)
    rows = data.get('rows', [])

    print(f"\nAPI Response:")
    print(f"  Total count: {total}")
    print(f"  Rows returned: {len(rows)}")

    print(f"\nSymbols in response (sorted):")
    symbols = sorted([row['symbol'] for row in rows])
    for i, symbol in enumerate(symbols, 1):
        outlook = [row['outlook'] for row in rows if row['symbol'] == symbol][0]
        print(f"  {i:2d}. {symbol}: {outlook}")

    # Check for missing symbols
    expected = {'APD', 'CAVA', 'CZR', 'DAR', 'HCA', 'MUSA', 'OLLI', 'ONON', 'PVH', 'RBLX', 'ROP', 'SWBI', 'ULS', 'WING'}
    actual = set(symbols)
    missing = expected - actual
    extra = actual - expected

    print(f"\n=== Analysis ===")
    print(f"Expected count: {len(expected)}")
    print(f"Actual count: {len(actual)}")

    if missing:
        print(f"\n[FAIL] MISSING from API: {sorted(missing)}")
    if extra:
        print(f"\n[FAIL] EXTRA in API: {sorted(extra)}")
    if not missing and not extra:
        print(f"\n[OK] All 14 symbols present")
else:
    print(f"Error: {response.text}")
