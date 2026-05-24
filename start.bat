@echo off
REM ============================================================
REM start.bat - launches FastAPI + opens dashboard
REM ============================================================
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo .venv not found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat

if not exist ".env" (
    echo .env not found. Copy .env.example to .env and set PG_PASSWORD.
    exit /b 1
)

REM Open the browser shortly after the server starts (5 seconds gives uvicorn time to bind)
start "" cmd /c "timeout /t 5 /nobreak >nul && start http://127.0.0.1:8000/"

echo Starting FastAPI server at http://127.0.0.1:8000/  ...
echo (Ctrl+C to stop)
REM --reload-dir api  -> ONLY watch api/ for changes. Without this, uvicorn
REM also watches etl/working/ where the scheduler writes heartbeat / crash
REM log / lifecycle log files -- any heartbeat refresh triggers a reload,
REM which on Windows can kill uvicorn entirely.
uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload --reload-dir api --log-level debug
echo.
echo === uvicorn exited (exit code %ERRORLEVEL%) ===
pause

endlocal
