#!/usr/bin/env python3
import urllib.request, json

try:
    r = urllib.request.urlopen('http://127.0.0.1:8001/api/monitor/schedule')
    data = json.loads(r.read().decode())

    print(f'[OK] Schedule records: {len(data["schedule"])}')

    etf = [x for x in data['schedule'] if x['file_type'] == 'ETF']
    if etf:
        print(f'ETF status: {etf[0]["status"]}')
        print(f'ETF file_date: {etf[0]["file_date"]}')

    toso = [x for x in data['schedule'] if x['file_type'] == 'TOSO']
    if toso:
        print(f'TOSO status: {toso[0]["status"]}')
        print(f'TOSO file_date: {toso[0]["file_date"]}')

except Exception as e:
    print(f'[ERROR] {type(e).__name__}: {e}')
