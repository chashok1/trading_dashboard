@echo off
REM ============================================================
REM  Clean recovery — kill stale Python processes, migrate the
REM  transactions schema, then start one fresh scheduler.
REM  Idempotent. Safe to run repeatedly.
REM ============================================================

setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\activate.bat (
    echo ERROR: .venv missing. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat

echo.
echo === Step 1: Kill any running Python processes ===
echo (this releases the heartbeat lock and stops any duplicate schedulers)
tasklist /FI "IMAGENAME eq python.exe" /FO CSV 2>nul | findstr /R "python" >nul
if errorlevel 1 (
    echo   No python.exe processes running — skipping.
) else (
    taskkill /F /IM python.exe 2>&1 | findstr /V "ERROR"
    timeout /t 2 /nobreak >nul
)

echo.
echo === Step 2: Remove any stale heartbeat file ===
if exist "etl\working\scheduler_heartbeat.txt" (
    del "etl\working\scheduler_heartbeat.txt"
    echo   Removed stale heartbeat.
) else (
    echo   No heartbeat to remove.
)

echo.
echo === Step 3: Migrate transactions tables PK (so NULL qty/price load) ===
python migrate_transactions_pk.py
if errorlevel 1 (
    echo Migration failed. Bailing.
    exit /b 1
)

echo.
echo === Step 4: Start the scheduler (foreground; Ctrl+C to stop) ===
echo You should see:
echo   - "scheduler PID lock acquired: ..."
echo   - "initial scan of N dirs"
echo   - per-file LOADED lines
echo   - "scheduler running. Ctrl+C to stop."
echo.
python -m etl.scheduler

endlocal
