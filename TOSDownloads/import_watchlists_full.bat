@echo off
REM Step 2 of 3 (Program 1): full re-import of every watchlist CSV into TOS.
REM Requires: TOS already open, and menu_WL<n>.png / Watchlist_WL<n>.png /
REM "Edit WL<n>.png" / EditDialogWL<n>.png present in Images for every
REM watchlist being imported - missing images = that watchlist is skipped
REM with a warning, nothing else happens.

cd /d "C:\Ashok\Investing\Stocks\Scripts\TOSDownloads"

echo === Full watchlist import (all WL*.csv) ===
echo Make sure TOS is already open before continuing.
pause

python.exe LoadWatchlists.py "C:\Ashok\Investing\Stocks\Watchlists\TOS\Watchlists" Images TOS.lock

if errorlevel 1 (
    echo.
    echo *** FAILED - see error above ***
) else (
    echo.
    echo === Full import complete ===
)

pause
