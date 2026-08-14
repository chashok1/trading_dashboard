@echo off
REM ============================================================
REM fetch_vix9d.bat - daily VIX9D pull (etl/fetch_vix9d.py).
REM Same venv-activation convention as start.bat/run_scheduler.bat.
REM Scheduled via Windows Task Scheduler (see docs/migrations.md /
REM commit history for setup date) -- runs after market close so the
REM day's close is settled, same timing convention as TOSL/YFiles
REM (db/baseline.sql: "TOSL and YFiles run optionally several times
REM per day after 16:00").
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo .venv not found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat

python -m etl.fetch_vix9d
exit /b %ERRORLEVEL%
