@echo off
rem Start Laya (API + dashboard) after setup.bat has been run.
cd /d "%~dp0laya"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Laya is not set up yet. Run setup.bat first.
  pause
  exit /b 1
)
echo Starting Laya at http://127.0.0.1:8000  (Ctrl+C to stop)
start "" "http://127.0.0.1:8000"
"%~dp0.venv\Scripts\python.exe" -m laya.cli serve
