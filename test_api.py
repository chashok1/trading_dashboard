import urllib.request
import json
from datetime import date

BASE_URL = "http://127.0.0.1:8000"

def fetch_json(url):
    """Fetch JSON from URL"""
    try:
        with urllib.request.urlopen(url) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return None, str(e)

print("=" * 60)
print("TESTING API ENDPOINTS")
print("=" * 60)

# Test 1: Check available dates
print("\n1. GET /api/dates")
try:
    dates = fetch_json(f"{BASE_URL}/api/dates")
    if dates and isinstance(dates, list):
        print(f"   Status: OK")
        print(f"   First 5 dates: {dates[:5]}")
        print(f"   Last date in list: {dates[-1] if dates else 'NONE'}")
        latest_date = dates[0] if dates else None
    else:
        print(f"   ERROR: No dates returned")
        latest_date = None
except Exception as e:
    print(f"   FAILED: {e}")
    latest_date = None

# Test 2: Check portfolio summary for latest date
if latest_date:
    print(f"\n2. GET /api/portfolio/summary?date={latest_date}")
    try:
        data = fetch_json(f"{BASE_URL}/api/portfolio/summary?date={latest_date}")
        if data:
            print(f"   Status: OK")
            print(f"   Market Value: ${data.get('market_value', 'N/A')}")
            print(f"   Positions: {data.get('positions', 'N/A')}")
            print(f"   Date in response: {data.get('as_of_date', 'N/A')}")
        else:
            print(f"   ERROR: No data returned")
    except Exception as e:
        print(f"   FAILED: {e}")

# Test 3: Check portfolio rows
if latest_date:
    print(f"\n3. GET /api/portfolio?date={latest_date}")
    try:
        rows = fetch_json(f"{BASE_URL}/api/portfolio?date={latest_date}")
        if rows and isinstance(rows, list):
            print(f"   Status: OK")
            print(f"   Row count: {len(rows)}")
            if rows:
                first_row = rows[0]
                print(f"   First row snapshot_date: {first_row.get('snapshot_date', 'N/A')}")
                print(f"   First row symbol: {first_row.get('symbol', 'N/A')}")
        else:
            print(f"   ERROR: No data returned")
    except Exception as e:
        print(f"   FAILED: {e}")

# Test 4: Check without date (should default to latest)
print(f"\n4. GET /api/portfolio/summary (NO DATE - should default to latest)")
try:
    data = fetch_json(f"{BASE_URL}/api/portfolio/summary")
    if data:
        default_date = data.get('as_of_date', 'N/A')
        print(f"   Status: OK")
        print(f"   Default date returned: {default_date}")
        print(f"   Expected: {latest_date}")
        if str(default_date) == latest_date:
            print(f"   SUCCESS - defaults to latest date")
        else:
            print(f"   ISSUE - defaulting to old date!")
    else:
        print(f"   ERROR: No data returned")
except Exception as e:
    print(f"   FAILED: {e}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
