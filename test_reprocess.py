#!/usr/bin/env python
import requests
import json
import sys
from urllib.parse import quote

file_path = r"C:\Ashok\Investing\Stocks\RR\Archive\RR 2026-05-15.xlsx"
url = f"http://127.0.0.1:8000/api/monitor/reprocess?file_path={quote(file_path)}&file_type=RR"

try:
    response = requests.post(url, timeout=30)
    result = response.json()
    print("Response:", json.dumps(result, indent=2))
    sys.exit(0)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
