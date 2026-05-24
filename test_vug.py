#!/usr/bin/env python3
import urllib.request, json

url = 'http://127.0.0.1:8000/api/portfolio/VUG/detail'
try:
    with urllib.request.urlopen(url, timeout=5) as r:
        data = json.loads(r.read().decode())
        c = data['current']
        p = data['periods']
        print(f"VUG - Current: {c['qty']:.0f} shares, ${c['market_value']:.2f}")
        print(f"  Gain/Loss: ${c['total_gain_dollar']:.2f} ({c['avg_gain_pct']:.2f}%)")
        print(f"  YTD: ${p['ytd_dollar']:.2f} ({p['ytd_pct']:.2f}%)")
        print(f"  MTD: ${p['mtd_dollar']:.2f} ({p['mtd_pct']:.2f}%)")
except Exception as e:
    print(f'VUG: {e}')
