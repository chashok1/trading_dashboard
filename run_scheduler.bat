@echo off
REM ============================================================
REM run_scheduler.bat - keep-alive wrapper for the ETL scheduler.
REM
REM The scheduler can die for reasons Python cannot catch (native
REM C-extension crash in pandas/psycopg/numpy, libc abort(), Windows
REM TerminateProcess, etc.). When that happens, this loop relaunches
REM it. The scheduler is idempotent on restart (already-processed
REM files are skipped via meta_file_processed), so this is safe.
REM
REM Stop with Ctrl+C twice (once to interrupt the scheduler, once
REM to break out of the loop).
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo .venv not found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat

REM Enable DB logging so the File Monitor "Scheduler output" panel sees fresh
REM entries (panel reads from meta_scheduler_log). Off by default for
REM bare CLI loaders; on for the long-running scheduler.
set TD_DB_LOG=1

set RESTARTS=0
:loop
set /a RESTARTS+=1
echo.
echo === Scheduler launch #!RESTARTS! at %DATE% %TIME% ===

REM No file cleanup needed — the OS file-lock on scheduler.lock is released
REM automatically when the scheduler process exits (clean OR crash). The
REM lock file itself can stay; only the lock state matters.

python -m etl.scheduler
set EXITCODE=!ERRORLEVEL!

echo.
echo === Scheduler exited (code !EXITCODE!) - restarting in 2s ===
echo === Press Ctrl+C now to stop the keep-alive loop ===

timeout /t 2 /nobreak >nul
goto loop
