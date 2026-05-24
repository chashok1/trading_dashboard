#!/usr/bin/env python3
"""Test period metrics (YTD, MTD) for various symbols."""
import urllib.request
import urllib.error
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

def test_symbol(symbol):
    """Test a specific symbol's period metrics."""
    url = f"{BASE_URL}/api/portfolio/{symbol}/detail"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

            current = data.get('current', {})
            periods = data.get('periods', {})

            print(f"\n{symbol}:")
            print(f"  Current Position: {current.get('qty', 0):.0f} shares, ${current.get('market_value', 0):.2f}")
            print(f"  Current Gain/Loss: ${current.get('total_gain_dollar', 0):.2f} ({current.get('avg_gain_pct', 0):.2f}%)")
            print(f"  YTD: ${periods.get('ytd_dollar', 0):.2f} ({periods.get('ytd_pct', 0):.2f}%)")
            print(f"  MTD: ${periods.get('mtd_dollar', 0):.2f} ({periods.get('mtd_pct', 0):.2f}%)")
            print(f"  Is Sold: {data.get('is_sold', False)}")

            # Verify periods exist in response
            if 'periods' not in data:
                print(f"  [ERROR] No periods in response!")
            elif not all(k in periods for k in ['ytd_dollar', 'ytd_pct', 'mtd_dollar', 'mtd_pct']):
                print(f"  [ERROR] Missing period keys!")
            else:
                print(f"  [OK] Period metrics present and valid")

    except urllib.error.HTTPError as e:
        print(f"{symbol}: [ERROR] HTTP {e.code}")
    except Exception as e:
        print(f"{symbol}: [ERROR] {e}")

if __name__ == "__main__":
    print("="*60)
    print("Testing Period Metrics (YTD / MTD)")
    print("="*60)

    # Test a few symbols
    symbols = ["AAPL", "QQQ", "VTI", "TSLA"]
    for sym in symbols:
        test_symbol(sym)

    print("\n" + "="*60)
    print("Period Metrics Test Complete")
    print("="*60)
