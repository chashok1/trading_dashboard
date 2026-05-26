#!/usr/bin/env python3
import time

try:
    from PIL import ImageGrab
    print("Taking screenshot with PIL...")
    time.sleep(2)
    img = ImageGrab.grab()
    path = r'C:\Users\chash\actionable_with_export_time.png'
    img.save(path)
    print(f"Screenshot saved: {path}")
except ImportError:
    print("PIL not available")
except Exception as e:
    print(f"Error: {e}")
