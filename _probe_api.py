"""Probe the five API endpoints File Monitor depends on. Exit 0 if all OK."""
import sys
import urllib.request
import json

ENDPOINTS = [
    "/api/monitor/summary",
    "/api/monitor/schedule",
    # /api/monitor/etl-runs has a minimum limit of 25 (Query(50, ge=25, le=250)),
    # so always probe with at least 25.
    "/api/monitor/etl-runs?limit=50",
    "/api/monitor/derive-runs",
    "/api/monitor/scheduler",
]

BASE = "http://127.0.0.1:8000"
all_ok = True

for ep in ENDPOINTS:
    try:
        with urllib.request.urlopen(BASE + ep, timeout=5) as r:
            status = r.status
            body = r.read().decode("utf-8")
            try:
                data = json.loads(body)
                n = len(data) if isinstance(data, list) else "object"
            except Exception:
                n = f"{len(body)} bytes (not JSON)"
            print(f"  {status}  {ep:45} -> {n} items")
            all_ok = all_ok and status == 200
    except Exception as e:
        print(f"  ---  {ep:45} -> {type(e).__name__}: {e}")
        all_ok = False

sys.exit(0 if all_ok else 1)
