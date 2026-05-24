#!/usr/bin/env python3
import urllib.request
import json

try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/monitor/schedule', timeout=5) as r:
        print('[OK] Response:', r.status)
        data = json.loads(r.read().decode())
        print(f'Records: {len(data.get("schedule", []))}')
except urllib.error.HTTPError as e:
    print(f'[ERROR] HTTP {e.code}')
    try:
        error_body = e.read().decode()
        print(f'Response: {error_body}')
    except:
        print('Could not read error body')
except Exception as e:
    print(f'[ERROR] {type(e).__name__}: {e}')
