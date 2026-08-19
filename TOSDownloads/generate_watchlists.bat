@echo off
REM Step 1 of 3: generate WL1..WLn.csv / overflow.csv / additions.csv / removals.csv
REM from ref_watchlist_assignment via etl.generate_watchlist_files.
REM WL*.csv/overflow.csv -> C:\Ashok\Investing\Stocks\TOS Watchlists\Watchlists\
REM   (settings.watchlist_files_dir)
REM additions.csv/removals.csv -> C:\Ashok\Investing\Stocks\TOS Watchlists\
REM   (settings.watchlist_lists_dir)

cd /d "C:\Ashok\Invest\Projects\trading-dashboard"

echo === Generating Tier 1 watchlist files only (WL1-10) ===
".venv\Scripts\python.exe" -m etl.generate_watchlist_files --mode daily

if errorlevel 1 (
    echo.
    echo *** FAILED - see error above ***
) else (
    echo.
    echo === Done. Next: import_watchlists_full.bat or import_watchlists_delta.bat ===
)

pause
