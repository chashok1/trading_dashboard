@echo off
REM ============================================================
REM  One-shot fix for "File Monitor blank grids"
REM    1. Migrate ref_load_files PK so file_time becomes editable
REM    2. Test the actual API endpoints the screen calls
REM    3. If the API is healthy, the screen issue is browser-side
REM ============================================================

setlocal
cd /d "%~dp0"
call .venv\Scripts\activate.bat

echo.
echo === Step 1: Migrate the PK ===
python migrate_ref_load_files_pk.py
if errorlevel 1 (
    echo Migration failed; bailing.
    exit /b 1
)

echo.
echo === Step 2: Probe the API endpoints File Monitor depends on ===
python _probe_api.py

if errorlevel 1 (
    echo.
    echo One or more endpoints failed. Restart uvicorn:
    echo   taskkill /F /IM python.exe
    echo   start.bat
    exit /b 1
)

echo.
echo === Step 3: All endpoints respond with data ===
echo.
echo If File Monitor still shows blank grids, the browser has stale cache.
echo Hard-refresh with Ctrl+F5  (or open DevTools, right-click reload, "Empty Cache and Hard Reload")
echo.
endlocal
