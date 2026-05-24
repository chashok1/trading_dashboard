@echo off
REM ============================================================
REM setup.bat - first-time environment setup
REM 1. creates virtualenv
REM 2. installs requirements
REM 3. (optional) initializes database schema
REM ============================================================
setlocal

cd /d "%~dp0"

if not exist ".venv" (
    echo Creating virtual environment .venv ...
    python -m venv .venv || goto :err
) else (
    echo .venv already exists. Skipping creation.
)

call .venv\Scripts\activate.bat || goto :err

echo Upgrading pip ...
python -m pip install --upgrade pip || goto :err

echo Installing requirements ...
pip install -r requirements.txt || goto :err

if not exist ".env" (
    echo.
    echo .env not found. Copying .env.example to .env ...
    copy ".env.example" ".env" >nul
    echo.
    echo *** EDIT .env NOW and set PG_PASSWORD before continuing ***
    echo.
    goto :end
)

echo.
echo Running database DDL ...
python -m db.init_db || goto :err

echo.
echo Setup complete.
goto :end

:err
echo.
echo *** Setup FAILED. See messages above. ***
exit /b 1

:end
endlocal
