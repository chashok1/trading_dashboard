#!/usr/bin/env python3
import sys

# Read the file as bytes to see actual content
with open('web/portfolio.html', 'rb') as f:
    content_bytes = f.read()

# Find 'kpiMV' and show surrounding bytes
search = b'kpiMV'
idx = content_bytes.find(search)
if idx >= 0:
    start = max(0, idx - 20)
    end = min(len(content_bytes), idx + 30)
    snippet = content_bytes[start:end]
    print("Found kpiMV at position", idx)
    print("Raw bytes:", snippet)
    print("As string:", snippet.decode('utf-8', errors='replace'))
    print("\nByte values:")
    for i, b in enumerate(snippet):
        print(f"  {i}: {b:3d} {chr(b) if 32 <= b < 127 else '?'}")

# Now fix: replace curly quotes with straight quotes
content = content_bytes.decode('utf-8')
fixed = content.replace('"', '"').replace('"', '"').replace(''', "'").replace(''', "'")

# Also try the escaped versions in case encoding is different
fixed = fixed.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")

with open('web/portfolio.html', 'w', encoding='utf-8') as f:
    f.write(fixed)

print("\nFixed and saved")
