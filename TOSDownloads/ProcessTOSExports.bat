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

:: Pre-create empty placeholder files for manual exports -- if you ever need
:: to export a watchlist by hand from TOS instead of the automated clicks,
:: the filename already exists in the Save-As dialog's file list so you can
:: just click it instead of typing it out.
for /f "usebackq delims=" %%A in ("%fileList%") do (
	if not exist "%inputDir%\%%A" (
		echo Creating file %%A in %inputDir%
		type nul > "%inputDir%\%%A"
	)
)

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
