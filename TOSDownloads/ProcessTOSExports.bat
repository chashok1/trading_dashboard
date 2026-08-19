@echo off
setlocal enabledelayedexpansion

if "%1"=="" (
	echo parameter - TOS Download Type {TOSD, TOSW, TOSL} is requried
	goto :EOF
)

:: Define paths
set "TOSType=%1"
set "sourceDir=C:\Ashok\Investing\Stocks\%TOSType%"
set "fileList=%sourceDir%\FilesList.txt"
set "inputDir=%sourceDir%\Input"
set "imagesDir=C:\Ashok\Investing\Stocks\Scripts\TOSDownloads\Images"
set "watchlistCsv=C:\Ashok\Investing\Stocks\Scripts\TOSDownloads\%TOSType%.csv"
set "lockFile=C:\Ashok\Investing\Stocks\Scripts\TOSDownloads\TOS.lock"
set "timeout=30"

:: Merge only -- skip the TOS download automation entirely and just merge
:: whatever fragment CSVs are already in the Input folder (e.g. after a
:: manual export, or to retry a merge that failed without re-downloading).
if "%2"=="Y" (

	python.exe "C:\Ashok\Investing\Stocks\Scripts\TOSDownloads\TOSDownloads.py" "%watchlistCsv%" "%inputDir%" "%imagesDir%" "%lockFile%" "N" "N" "Y"

	goto :EOF

)

:: Ensure destination folder exists
if not exist "%inputDir%" mkdir "%inputDir%"

:: 2026-08-19: disabled -- this pre-created empty placeholder files so a
:: manual by-hand TOS export would find the filename already in the Save-As
:: dialog's file list. But on this (the automated) path, TOSDownloads.py's
:: main() deletes every .csv in inputDir as its very first action (clearing
:: stale leftovers) before any download happens -- so these placeholders
:: were being created and immediately trashed again every single run, for
:: no benefit, since no human gets a chance to use them in between. Left
:: commented out (not deleted) in case a manual-export workflow needs it
:: back -- run this block by hand if you're exporting from TOS yourself.
REM for /f "usebackq delims=" %%A in ("%fileList%") do (
REM 	if not exist "%inputDir%\%%A" (
REM 		echo Creating file %%A in %inputDir%
REM 		type nul > "%inputDir%\%%A"
REM 	)
REM )

:: 2026-08-16: TOSDownloads.py and MergeExports.py were merged into one
:: script -- download + merge now happen in a single python.exe call
:: (previously two separate calls, one before and one after this point).
python.exe "C:\Ashok\Investing\Stocks\Scripts\TOSDownloads\TOSDownloads.py" "%watchlistCsv%" "%inputDir%" "%imagesDir%" "%lockFile%"

if errorlevel 1 (
	echo error while executing python
	pause
	goto :EOF
)

:EOF
:: Check if a key is pressed to exit
echo %TIME%: Press y to pause or will exit in %timeout% seconds
choice /t %timeout% /d N /n /c YN >nul
if errorlevel 2 (
    exit
) else (
	pause
    exit
)

endlocal
