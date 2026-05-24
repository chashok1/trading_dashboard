"""DEPRECATED — use ``python -m etl.execute_build`` instead.

This subprocess-based orchestrator has been retired in favor of
``etl.execute_build`` which uses direct imports for cleaner error
handling.  The string-edit-derive.py step that used to live here is
no longer needed: the per-cat-table wiring now lives in
``etl/derive.py`` directly.

If you need to run the build, use:

    python -m etl.execute_build
"""
from __future__ import annotations
import sys


def main() -> None:
    sys.stderr.write(
        "build_drv_cat_layers.py is deprecated.\n"
        "Run: python -m etl.execute_build\n"
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
