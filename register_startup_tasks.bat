@echo off
REM ============================================================
REM register_startup_tasks.bat
REM
REM Run this ONCE as administrator to register both auto-start
REM tasks in Windows Task Scheduler.
REM
REM After this runs successfully, you never need admin again —
REM the tasks persist and start automatically at every login.
REM ============================================================

cd /d "%~dp0"

echo Registering for user: %USERDOMAIN%\%USERNAME%
echo.

echo Registering ETL Scheduler task...
schtasks /create /tn "TradingDashboard-ETLScheduler" /f /sc ONLOGON /ru "%USERDOMAIN%\%USERNAME%" /it /tr "%~dp0run_etl_scheduler.bat"
if %errorlevel% neq 0 (
    echo FAILED to register ETL Scheduler.
) else (
    echo OK - ETL Scheduler registered.
)

echo.
echo Registering Trading App task...
schtasks /create /tn "TradingDashboard-TradingApp" /f /sc ONLOGON /ru "%USERDOMAIN%\%USERNAME%" /it /tr "%~dp0run_trading_app.bat"
if %errorlevel% neq 0 (
    echo FAILED to register Trading App.
) else (
    echo OK - Trading App registered.
)

echo.
echo Done. You can close this window.
pause
