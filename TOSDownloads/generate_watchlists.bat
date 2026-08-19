@echo off
REM Step 1 of 3: generate WL1..WLn.csv / additions.csv / overflow.csv
REM from ref_watchlist_assignment via etl.generate_watchlist_files.
REM Output lands in C:\Ashok\Investing\Stocks\Scripts\TOSDownloads\WatchlistLoads\
REM (settings.watchlist_files_dir).

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
