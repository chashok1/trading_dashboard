"""HTML page routes + the /static asset mount.

This router is included LAST in main.py so the explicit page routes here take
precedence and the catch-all /static mount only handles bare asset paths.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api._helpers import WEB_DIR

router = APIRouter()


# -----------------------------------------------------------------------------
# Page routes — serve the static HTML for each web/*.html file.
# Static assets (CSS, JS) are served from /static/* via the mount below.
# -----------------------------------------------------------------------------

@router.get("/")
def page_index():
    return FileResponse(WEB_DIR / "index.html", media_type="text/html; charset=utf-8")


@router.get("/cockpit")
def page_cockpit():
    return FileResponse(WEB_DIR / "cockpit.html", media_type="text/html; charset=utf-8")


@router.get("/composite-edit")
def page_composite_edit():
    return FileResponse(WEB_DIR / "composite_edit.html", media_type="text/html; charset=utf-8")


@router.get("/dbstats")
def page_dbstats():
    return FileResponse(WEB_DIR / "dbstats.html", media_type="text/html; charset=utf-8")


@router.get("/explore")
def page_explore():
    return FileResponse(WEB_DIR / "explore.html", media_type="text/html; charset=utf-8")


@router.get("/file-monitor")
def page_file_monitor():
    return FileResponse(WEB_DIR / "file_monitor.html", media_type="text/html; charset=utf-8")


@router.get("/groups")
def page_groups():
    return FileResponse(WEB_DIR / "groups.html", media_type="text/html; charset=utf-8")


@router.get("/ref")
def page_ref():
    return FileResponse(WEB_DIR / "ref.html", media_type="text/html; charset=utf-8")


@router.get("/rule-performance")
def page_rule_performance():
    return FileResponse(WEB_DIR / "rule_performance.html", media_type="text/html; charset=utf-8")


@router.get("/rules")
def page_rules():
    return FileResponse(WEB_DIR / "rules.html", media_type="text/html; charset=utf-8")


@router.get("/param-sets")
def page_param_sets():
    return FileResponse(WEB_DIR / "param_sets.html", media_type="text/html; charset=utf-8")


@router.get("/rules-health")
def page_rules_health():
    return FileResponse(WEB_DIR / "rules_health.html", media_type="text/html; charset=utf-8")


@router.get("/test-results")
def page_test_results():
    return FileResponse(WEB_DIR / "test_results.html", media_type="text/html; charset=utf-8")


@router.get("/api/test-results")
def api_test_results():
    """Serve the JSON written by pytest --json-report (docs/test_results.json).

    The test runner produces this file via:
      python -m pytest tests/ --json-report --json-report-file=docs/test_results.json

    The /test-results page polls this endpoint to render the dashboard.
    """
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent.parent / "docs" / "test_results.json"
    if not p.exists():
        return {"summary": {"total": 0}, "tests": [], "warning":
                "docs/test_results.json missing — run tests with --json-report"}
    return FileResponse(p, media_type="application/json")


@router.get("/rule-flow")
def page_rule_flow():
    return FileResponse(WEB_DIR / "rule_flow.html", media_type="text/html; charset=utf-8")


@router.get("/trace")
def page_trace():
    return FileResponse(WEB_DIR / "trace.html", media_type="text/html; charset=utf-8")


@router.get("/actionable")
def page_actionable():
    return FileResponse(WEB_DIR / "actionable.html", media_type="text/html; charset=utf-8")


@router.get("/portfolio")
def page_portfolio():
    return FileResponse(WEB_DIR / "portfolio.html", media_type="text/html; charset=utf-8")


@router.get("/trig")
def page_trig():
    return FileResponse(WEB_DIR / "trig.html", media_type="text/html; charset=utf-8")


# -----------------------------------------------------------------------------
# Static asset mount — serves web/*.css, web/*.js, etc. under /static/<file>.
# Mounted via main.py AFTER all routers are included so the page routes above
# take precedence. We expose the mount as a module-level object so main.py can
# attach it via app.mount() in the correct order.
# -----------------------------------------------------------------------------

static_files = StaticFiles(directory=WEB_DIR)
