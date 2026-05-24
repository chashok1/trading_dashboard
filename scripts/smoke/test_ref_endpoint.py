import urllib.request
import urllib.error
import json
import socket

BASE_URL = "http://127.0.0.1:8000"

print("Testing /api/ref/tables endpoint...\n")

try:
    # Test health
    print("1. Checking API health...")
    with urllib.request.urlopen(f"{BASE_URL}/health", timeout=2) as resp:
        health = json.loads(resp.read())
        print(f"   Status: {health['status']}")
        print(f"   DB: {health['db']}\n")

    # Test ref tables endpoint
    print("2. Fetching /api/ref/tables...")
    with urllib.request.urlopen(f"{BASE_URL}/api/ref/tables", timeout=5) as resp:
        tables = json.loads(resp.read())
        print(f"   SUCCESS! Got {len(tables)} tables:\n")
        for t in tables:
            tunable_mark = " [tunable]" if t['tunable'] else " [read-only]"
            print(f"   - {t['name']:<35} {t['row_count']:>6} rows{tunable_mark}")

except urllib.error.URLError as e:
    print(f"   FAILED: Cannot connect to API at 127.0.0.1:8000")
    print(f"   Reason: {e.reason}")
    print("   → Start the API with: start.bat")
except socket.timeout:
    print("   FAILED: API timeout (took >5 seconds)")
except Exception as e:
    print(f"   FAILED: {type(e).__name__}: {e}")
