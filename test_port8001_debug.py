#!/usr/bin/env python3
import urllib.request, json

try:
    r = urllib.request.urlopen('http://127.0.0.1:8001/api/monitor/schedule')
    data = json.loads(r.read().decode())

    print(f'Response type: {type(data)}')
    if isinstance(data, dict):
        print(f'Keys: {list(data.keys())}')
        if 'schedule' in data:
            print(f'Schedule is: {type(data["schedule"])}')
            print(f'Schedule length: {len(data["schedule"])}')
            if len(data["schedule"]) > 0:
                print(f'First record: {data["schedule"][0]}')
    elif isinstance(data, list):
        print(f'List length: {len(data)}')
        if len(data) > 0:
            print(f'First record: {data[0]}')

except Exception as e:
    print(f'[ERROR] {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
