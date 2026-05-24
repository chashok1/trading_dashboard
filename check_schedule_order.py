import urllib.request
import json

try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/monitor/schedule') as resp:
        data = json.loads(resp.read().decode())

    print("Today's Schedule - Status Distribution:")
    status_counts = {}
    status_order = []

    for row in data:
        status = row.get('status', 'unknown')
        if status not in status_counts:
            status_counts[status] = 0
            status_order.append(status)
        status_counts[status] += 1

    print("\nOrder as returned by API:")
    for i, status in enumerate(status_order, 1):
        print(f"  {i}. {status}: {status_counts[status]} files")

    print("\nFirst 15 files (in order returned):")
    for i, row in enumerate(data[:15], 1):
        file_type = row.get('file_type', '?')[:15]
        status = row.get('status', '?')[:12]
        week_day = row.get('week_day', '?')
        print(f"  {i:2}. {file_type:15} | status={status:12} | day={week_day}")

except Exception as e:
    print(f"Error: {e}")
