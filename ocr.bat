@echo off
REM ocr.bat - convert an image to text via Tesseract OCR (etl/ocr_image.py).
REM Usage: ocr.bat "C:\path\to\image.png"
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo .venv not found. Run setup.bat first.
    exit /b 1
)
call .venv\Scripts\activate.bat

if "%~1"=="" (
    echo Usage: ocr.bat "C:\path\to\image.png"
    exit /b 1
)

python -m etl.ocr_image %*
