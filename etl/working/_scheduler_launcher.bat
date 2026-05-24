@echo off
cd /d "C:\Ashok\Invest\Projects\trading-dashboard"
call "C:\Ashok\Invest\Projects\trading-dashboard\.venv\Scripts\activate.bat"
"C:\Ashok\Invest\Projects\trading-dashboard\.venv\Scripts\python.exe" -m etl.scheduler >> "C:\Ashok\Invest\Projects\trading-dashboard\etl\working\scheduler_crash.log" 2>&1
