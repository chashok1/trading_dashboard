@echo off
REM ============================================================
REM  Activate CST + FT transaction file types
REM    1. Apply baseline.sql (idempotent — picks up new seed rows)
REM    2. Create the source dirs the scheduler is now watching
REM    3. Show the final ref_load_files state for both file types
REM  Safe to re-run.
REM ============================================================

setlocal
cd /d "%~dp0"

if not exist .venv\Scripts\activate.bat (
    echo ERROR: .venv not found. Run setup.bat first.
    exit /b 1
)

call .venv\Scripts\activate.bat

echo.
echo === Step 1: apply baseline ===
python -m db.init_db
if errorlevel 1 (
    echo FAILED at init_db. Check PG_PASSWORD in .env.
    exit /b 1
)

echo.
echo === Step 2: create source folders ===
if not exist "C:\Ashok\Investing\Stocks\CST\Archive" (
    mkdir "C:\Ashok\Investing\Stocks\CST\Archive"
    echo   created C:\Ashok\Investing\Stocks\CST\Archive
) else (
    echo   exists  C:\Ashok\Investing\Stocks\CST\Archive
)
if not exist "C:\Ashok\Investing\Stocks\FT\Archive" (
    mkdir "C:\Ashok\Investing\Stocks\FT\Archive"
    echo   created C:\Ashok\Investing\Stocks\FT\Archive
) else (
    echo   exists  C:\Ashok\Investing\Stocks\FT\Archive
)

echo.
echo === Step 3: confirm rows in ref_load_files ===
python _verify_cst_ft.py

if errorlevel 1 (
    echo.
    echo WARNING: expected 2 rows ^(CST + FT^) -- only the rows printed above are present.
    echo Check db/baseline.sql or query ref_load_files manually.
    exit /b 1
)

echo.
echo Done. Open the File Monitor and check the schedule for SUN 16:00.
echo Restart the scheduler ^(python -m etl.scheduler^) so it picks up the
echo new watched folders.
endlocal
