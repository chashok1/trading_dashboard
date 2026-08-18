@echo off
setlocal enabledelayedexpansion

:: Runs LoadWatchlists.py (2026-08-17) -- imports each <WatchlistName>.csv/
:: .txt file in the symbols folder into its correspondingly-named TOS
:: watchlist (e.g. WL1.csv -> the "WL1" watchlist). Import-only, no export
:: follows -- see LoadWatchlists.py's own header for the per-watchlist
:: screenshot requirement (a watchlist with no matching images is skipped
:: with a warning, not a fatal error).

set "scriptsDir=C:\Ashok\Investing\Stocks\Scripts\TOSDownloads"
set "symbolsFolder=%scriptsDir%\WatchlistLoads"
set "imagesDir=%scriptsDir%\Images"
set "lockFile=%scriptsDir%\TOS.lock"
set "timeout=30"

if not exist "%symbolsFolder%" mkdir "%symbolsFolder%"

python.exe "%scriptsDir%\LoadWatchlists.py" "%symbolsFolder%" "%imagesDir%" "%lockFile%"

if errorlevel 1 (
	echo error while executing python
	pause
	goto :EOF
)

:EOF
echo %TIME%: Press y to pause or will exit in %timeout% seconds
choice /t %timeout% /d N /n /c YN >nul
if errorlevel 2 (
    exit
) else (
	pause
    exit
)

endlocal
