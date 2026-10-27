@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo Ready. Run the pet launcher to start.
pause
exit /b 0
:failed
echo Setup failed. Please check Python and network access.
pause
exit /b 1
