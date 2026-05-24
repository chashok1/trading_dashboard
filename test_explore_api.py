"""Test the Explore API endpoint for hist_ii."""
import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_api():
    """Test the /api/data/{table} endpoint."""

    # Test hist_ii with date filter
    url = f"{BASE_URL}/api/data/hist_ii?limit=200&offset=0&date=2026-05-11"

    print(f"Testing: {url}\n")

    try:
        response = requests.get(url)
        print(f"Status: {response.status_code}")

        if response.ok:
            data = response.json()
            print(f"\nColumns: {data.get('columns', [])}")
            print(f"Total: {data.get('total', 0)}")
            print(f"Rows returned: {len(data.get('rows', []))}")

            rows = data.get('rows', [])
            print(f"\nSymbols in response:")
            for row in sorted(rows, key=lambda r: r['symbol']):
                print(f"  {row['symbol']}: {row['outlook']}")

            # Check for missing symbols
            expected = {'APD', 'CAVA', 'CZR', 'DAR', 'HCA', 'MUSA', 'OLLI', 'ONON', 'PVH', 'RBLX', 'ROP', 'SWBI', 'ULS', 'WING'}
            actual = {row['symbol'] for row in rows}
            missing = expected - actual
            extra = actual - expected

            if missing:
                print(f"\nMISSING from API response: {sorted(missing)}")
            if extra:
                print(f"\nEXTRA in API response: {sorted(extra)}")
            if not missing and not extra:
                print(f"\n[OK] All 14 symbols present in API response")
        else:
            print(f"Error: {response.text}")
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to API. Is the server running?")
        print("Run: uvicorn api.main:app --host 127.0.0.1 --port 8000")

if __name__ == '__main__':
    test_api()
