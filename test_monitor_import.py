#!/usr/bin/env python3
import sys
sys.path.insert(0, '.')

try:
    from api.routers import monitor
    print("[OK] Monitor imported successfully")
    print("  Router object: " + str(monitor.router))
    print("  Router prefix: " + str(monitor.router.prefix))
    print("  Number of routes: " + str(len(monitor.router.routes)))
    for route in monitor.router.routes:
        print("    - " + str(route.path) + " " + str(route.methods))
except Exception as e:
    print("[ERROR] Error importing monitor: " + str(e))
    import traceback
    traceback.print_exc()
