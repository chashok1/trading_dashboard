"""
FastAPI app for Trading Dashboard.

Thin shell: builds the app, wires CORS, includes routers, and mounts /static.
Route handlers live in api/routers/{health,dash,ref,rules,trace,pages}.py;
shared helpers in api/_helpers.py.

Run from project root:
  .venv\\Scripts\\activate
  uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
"""
from __future__ import annotations

import logging
import sys
import traceback

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
_log = logging.getLogger("main")
_log.info("main.py loading — Python %s", sys.version)

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    _log.info("FastAPI imported OK")
except Exception:
    _log.critical("Failed to import FastAPI:\n%s", traceback.format_exc())
    raise

_routers: dict = {}
for _name in ("dash", "health", "macro", "monitor", "pages", "ref", "rules", "trace"):
    try:
        import importlib
        _routers[_name] = importlib.import_module(f"api.routers.{_name}")
        _log.info("router loaded: %s", _name)
    except Exception:
        _log.critical("FATAL: failed to load router '%s':\n%s", _name, traceback.format_exc())
        raise

dash    = _routers["dash"]
health  = _routers["health"]
macro   = _routers["macro"]
monitor = _routers["monitor"]
pages   = _routers["pages"]
ref     = _routers["ref"]
rules   = _routers["rules"]
trace   = _routers["trace"]


app = FastAPI(
    title="Trading Dashboard API",
    description="Replaces the Tickers Excel workbook. Snapshot-date aware.",
    version="0.1.0",
)

# Permissive CORS for local dev. Tighten in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup():
    _log.info("=== Trading Dashboard startup ===")
    try:
        from etl.db import session_scope
        from sqlalchemy import text
        with session_scope() as s:
            s.execute(text("SELECT 1"))
        _log.info("DB connection OK")
    except Exception:
        _log.error("DB connection FAILED:\n%s", traceback.format_exc())

    # Auto-heal stale drv_actionable dates in a background thread so the
    # Actionable screen reflects the latest ingested data. Non-blocking:
    # startup is not delayed by the re-derive.
    def _stale_heal() -> None:
        try:
            from etl.derive_freshness import run_stale_heal
            result = run_stale_heal()
            _log.info("startup stale-heal: %s", result)
        except Exception:
            _log.error("startup stale-heal FAILED:\n%s", traceback.format_exc())

    try:
        import threading
        threading.Thread(target=_stale_heal, name="stale-heal",
                         daemon=True).start()
    except Exception:
        _log.error("startup stale-heal thread FAILED:\n%s",
                   traceback.format_exc())


@app.on_event("shutdown")
async def _shutdown():
    _log.info("=== Trading Dashboard shutdown ===")


# API routers
app.include_router(health.router)
app.include_router(dash.router)
app.include_router(macro.router)
app.include_router(monitor.router)
app.include_router(ref.router)
app.include_router(rules.router)
app.include_router(trace.router)

# Pages router MUST be included LAST so its explicit page routes
# (and its trailing /static mount registered below) take precedence
# correctly relative to the API routes above.
app.include_router(pages.router)

# Static asset mount — registered AFTER all routers so the named page routes
# in pages.router take precedence. Serves web/*.css, web/*.js, etc. under
# /static/<file>.
app.mount("/static", pages.static_files, name="static")
_log.info("app configured — %d routes registered", len(app.routes))
