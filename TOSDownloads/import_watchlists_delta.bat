@echo off
REM Step 3 of 3 (Program 2): delta-only import - just the additions.csv
REM produced by generate_watchlists.bat. Requires: TOS already open, and
REM the same per-watchlist screenshot set as the full import for any
REM watchlist that has additions - missing images = that watchlist is
REM skipped with a warning, nothing else happens.

cd /d "C:\Ashok\Investing\Stocks\Scripts\TOSDownloads"

echo === Delta watchlist import (additions.csv only) ===
echo Make sure TOS is already open before continuing.
pause

python.exe ImportAdditions.py "C:\Ashok\Investing\Stocks\Watchlists\TOS\additions.csv" "C:\Ashok\Investing\Stocks\Watchlists\TOS\Watchlists" Images TOS.lock

if errorlevel 1 (
    echo.
    echo *** FAILED - see error above ***
) else (
    echo.
    echo === Delta import complete ===
)

pause
