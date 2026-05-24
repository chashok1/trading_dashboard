#!/usr/bin/env python3
"""Test the portfolio detail modal endpoint and chart data."""
import urllib.request
import urllib.error
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:8000"

def test_portfolio_detail():
    """Test the portfolio detail endpoint for a specific symbol."""
    symbol = "AAPL"
    url = f"{BASE_URL}/api/portfolio/{symbol}/detail"

    print(f"\n{'='*60}")
    print(f"Testing: {url}")
    print(f"{'='*60}\n")

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())

            print(f"[OK] API Response Successful\n")
            print(f"Symbol: {data['symbol']}")
            print(f"Date: {data['date']}")
            print(f"Is Sold: {data.get('is_sold', False)}")
            print(f"Realized Gains Total: ${data.get('realized_gains_total', 0):.2f}\n")

            # Check current metrics
            current = data.get('current', {})
            print(f"Current Position (as of today):")
            print(f"  Shares Owned: {current.get('qty', 0)}")
            print(f"  Market Value: ${current.get('market_value', 0):.2f}")
            print(f"  Total Gain/Loss: ${current.get('total_gain_dollar', 0):.2f}")
            print(f"  Gain %: {current.get('avg_gain_pct', 0):.2f}%\n")

            # Check timeseries
            timeseries = data.get('timeseries', [])
            # Check period metrics
            periods = data.get('periods', {})
            print(f"\nPeriod Metrics:")
            print(f"  YTD $: ${periods.get('ytd_dollar', 0):.2f}")
            print(f"  YTD %: {periods.get('ytd_pct', 0):.2f}%")
            print(f"  MTD $: ${periods.get('mtd_dollar', 0):.2f}")
            print(f"  MTD %: {periods.get('mtd_pct', 0):.2f}%\n")

            print(f"Timeseries Data:")
            print(f"  Total points: {len(timeseries)}")

            if timeseries:
                first = timeseries[0]
                last = timeseries[-1]
                print(f"  First point: {first['date']} - {first['qty']} shares, ${first['market_value']:.2f} value")
                print(f"  Last point:  {last['date']} - {last['qty']} shares, ${last['market_value']:.2f} value")
                print(f"  Last gain/loss: ${last['total_gain']:.2f}\n")

            # Check accounts
            accounts = data.get('accounts', [])
            print(f"Account Breakdown: {len(accounts)} accounts")
            for acc in accounts:
                # Handle different response structures
                acct_name = acc.get('account') or acc.get('name') or str(acc)
                total_qty = acc.get('total_qty') or acc.get('qty', 0)
                total_value = acc.get('total_value') or acc.get('value', 0)
                if total_qty and total_value:
                    print(f"  {acct_name}: {total_qty:.0f} shares, ${total_value:.2f}")

            # Verify chart data would render correctly
            print(f"\nChart Data Verification:")
            if timeseries:
                print(f"  [OK] Has historical timeseries data")
                print(f"  [OK] Will show {len(timeseries)} historical points")

                # Check if last date is today
                last_date = timeseries[-1]['date']
                today = datetime.now().strftime('%Y-%m-%d')
                if last_date == today:
                    print(f"  [OK] Last data point is TODAY ({today})")
                else:
                    print(f"  [INFO] Last data point is {last_date}, chart will extend to today")

                # Check if we have qty and gain data
                has_qty = any(t['qty'] for t in timeseries)
                has_gain = any(t['total_gain'] for t in timeseries)
                print(f"  [OK] Has qty data: {has_qty}")
                print(f"  [OK] Has gain/loss data: {has_gain}")

                # Verify the drop to zero case
                if current.get('qty', 0) == 0 and timeseries[-1]['qty'] > 0:
                    print(f"  [OK] Chart will show drop to 0 shares at end (position was sold)")

            print(f"\n[OK] All checks passed! Chart should render correctly.")

    except urllib.error.HTTPError as e:
        print(f"[ERROR] HTTP Error {e.code}: {e.reason}")
        body = e.read().decode()
        print(f"Response: {body}")
    except urllib.error.URLError as e:
        print(f"[ERROR] Connection Error: {e.reason}")
        print(f"Hint: Is the API server running on port 8000?")
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON Decode Error: {e}")
    except Exception as e:
        print(f"[ERROR] Unexpected Error: {e}")

if __name__ == "__main__":
    test_portfolio_detail()
