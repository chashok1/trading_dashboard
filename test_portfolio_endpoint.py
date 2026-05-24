#!/usr/bin/env python3
"""Quick test of portfolio endpoint."""
import urllib.request
import urllib.error
import json

try:
    print("Testing /api/dash...")
    req = urllib.request.Request("http://127.0.0.1:8000/api/dash?date=2026-05-16")
    with urllib.request.urlopen(req, timeout=5) as r:
        data = json.loads(r.read().decode())
        print(f"[OK] /api/dash working - {len(data)} symbols")

    # Find a symbol with portfolio data
    print("\nSearching for symbols with portfolio data...")
    test_symbols = ['AAPL', 'SPY', 'QQQ', 'IWM', 'GLD']

    for symbol in test_symbols:
        try:
            req = urllib.request.Request(f"http://127.0.0.1:8000/api/portfolio/{symbol}/detail?date=2026-05-16")
            with urllib.request.urlopen(req, timeout=5) as r:
                pdata = json.loads(r.read().decode())
                print(f"\n[OK] Found portfolio data for {symbol}")
                print(f"  Market Value: ${pdata.get('current', {}).get('market_value', 0):.2f}")
                print(f"  Gain: ${pdata.get('current', {}).get('total_gain_dollar', 0):.2f}")
                print(f"  Timeseries: {len(pdata.get('timeseries', []))} points")
                print(f"  Accounts: {len(pdata.get('accounts', []))}")
                break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  {symbol}: No data")
            else:
                print(f"  {symbol}: Error {e.code}")
        except Exception as e:
            print(f"  {symbol}: {e}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
