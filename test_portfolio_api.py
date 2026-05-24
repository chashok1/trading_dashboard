#!/usr/bin/env python3

import urllib.request
import json

try:
    print("Testing /api/portfolio/summary endpoint:")
    with urllib.request.urlopen('http://127.0.0.1:8000/api/portfolio/summary?date=2026-05-13') as response:
        data = json.loads(response.read())
        print(json.dumps(data, indent=2)[:2000])
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()
