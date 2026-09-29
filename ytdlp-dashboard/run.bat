@echo off
setlocal
cd /d "%~dp0"

rem Find a real Python (the Microsoft Store "python" shortcut fails --version)
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (python --version >nul 2>&1 && set "PY=python")

if not defined PY (
  echo Python is not installed. Installing Python 3.12 with winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo.
    echo Automatic install failed. Install Python from https://www.python.org/downloads/
    echo ^(tick "Add python.exe to PATH"^), then run this file again.
    pause
    exit /b 1
  )
  echo.
  echo Python installed. Close this window and run run.bat again so PATH refreshes.
  pause
  exit /b 0
)

echo Installing / updating yt-dlp...
%PY% -m pip install -q -U yt-dlp
if errorlevel 1 (
  echo pip failed. See the error above.
  pause
  exit /b 1
)

where ffmpeg >nul 2>&1
if errorlevel 1 (
  echo ffmpeg not found. Installing it with winget ^(needed for HD video and mp3^)...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  if not errorlevel 1 (
    echo.
    echo ffmpeg installed. Close this window and run run.bat again so PATH refreshes.
    pause
    exit /b 0
  )
  echo Could not install ffmpeg automatically; continuing with limited formats.
)

start "" http://127.0.0.1:8080
%PY% server.py
pause
