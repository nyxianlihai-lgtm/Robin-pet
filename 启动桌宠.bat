@echo off
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Please run setup.bat first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -c "import PySide6" >nul 2>nul
if errorlevel 1 (
  echo Dependencies are missing. Please run setup.bat first.
  pause
  exit /b 1
)
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
