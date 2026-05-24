#!/usr/bin/env python3
import urllib.request
import json

try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/monitor/schedule', timeout=5) as r:
        print('[OK] Response:', r.status)
        data = json.loads(r.read().decode())
        print(f'Records: {len(data.get("schedule", []))}')
        if len(data.get("schedule", [])) == 0:
            print('[ERROR] No schedule records returned')
        else:
            print('[OK] Sample record:', data["schedule"][0])
except Exception as e:
    print(f'[ERROR] {type(e).__name__}: {e}')
