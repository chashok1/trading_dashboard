import urllib.request
import json

try:
    # Test dates endpoint
    resp = urllib.request.urlopen('http://127.0.0.1:8000/api/dates')
    dates = json.loads(resp.read())
    print(f'Available dates: {dates[:3]}')

    # Test portfolio endpoint with latest date
    if dates:
        latest_date = dates[0]
        print(f'Testing portfolio with date: {latest_date}')
        try:
            resp2 = urllib.request.urlopen(f'http://127.0.0.1:8000/api/portfolio?date={latest_date}')
            pf = json.loads(resp2.read())
            print(f'Portfolio rows returned: {len(pf)}')
            if len(pf) > 0:
                print(f'First row keys: {list(pf[0].keys())}')
                print(f'First row: {pf[0]}')
            else:
                print('Portfolio returned empty list')
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print(f'API Error {e.code}: {error_body[:1000]}')
    else:
        print('No dates available')
except Exception as e:
    print(f'Error: {e}')
