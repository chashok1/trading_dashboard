@echo off
setlocal
rem Backs up the "trading" database to backups\trading_YYYY-MM-DD_HHMM.dump
rem (compressed pg_dump). Keeps the newest 14 dumps, deletes older ones.
rem Password: read from PG_PASSWORD in .env (never printed).
rem Restore into a NEW db first to check it:
rem   pg_restore -U postgres -d trading_restored backups\FILE.dump

cd /d "%~dp0"

set "PGBIN=C:\Program Files\PostgreSQL\17\bin"
set "PGHOST=localhost"
set "PGPORT=5432"
set "PGUSER=postgres"
set "DB=trading"
set "KEEP=14"

if not exist "%PGBIN%\pg_dump.exe" (
  echo pg_dump not found at "%PGBIN%". Edit PGBIN in this file.
  exit /b 1
)

if not defined PGPASSWORD (
  for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="PG_PASSWORD" set "PGPASSWORD=%%b"
  )
)
if not defined PGPASSWORD (
  echo PG_PASSWORD not found in .env or environment.
  exit /b 1
)

if not exist backups mkdir backups

for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set "STAMP=%%t"
set "OUT=backups\trading_%STAMP%.dump"

echo Backing up "%DB%" to %OUT% ...
"%PGBIN%\pg_dump.exe" -h %PGHOST% -p %PGPORT% -U %PGUSER% -Fc -f "%OUT%" %DB%
if errorlevel 1 (
  echo BACKUP FAILED.
  if exist "%OUT%" del "%OUT%"
  exit /b 1
)

rem Keep only the newest %KEEP% dumps.
powershell -NoProfile -Command "Get-ChildItem 'backups\trading_*.dump' | Sort-Object LastWriteTime -Descending | Select-Object -Skip %KEEP% | Remove-Item -Force"

echo.
echo Done. Backups now in the folder:
powershell -NoProfile -Command "Get-ChildItem 'backups\trading_*.dump' | Sort-Object LastWriteTime -Descending | ForEach-Object { '{0,10:N1} MB  {1}' -f ($_.Length/1MB), $_.Name }"
endlocal
