#!/usr/bin/env python
"""Test the stats API endpoint."""
import urllib.request
import json

try:
    response = urllib.request.urlopen("http://127.0.0.1:8000/api/stats/tables")
    data = json.loads(response.read().decode())
    print("SUCCESS: Endpoint working!")
    print("Returned {} table stats\n".format(len(data)))
    print("First 5 tables:")
    for table in data[:5]:
        print("  {:30} | {:10} | {:6} total rows".format(table['name'], table['category'], table['total_rows']))
except Exception as e:
    print("FAILED: {}".format(e))
