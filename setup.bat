@echo off
setlocal EnableDelayedExpansion
rem ============================================================
rem  Laya (System One AI) - one-click setup for Windows
rem  Creates a venv, installs everything, downloads the 0.5B
rem  model, builds the dashboard, then starts Laya.
rem  Flags:  /nomodel  skip model download (use mock model)
rem          /norun    set up only, do not start the server
rem ============================================================
cd /d "%~dp0"
set "ROOT=%CD%"
set "NOMODEL=0"
set "NORUN=0"
for %%A in (%*) do (
  if /i "%%A"=="/nomodel" set "NOMODEL=1"
  if /i "%%A"=="/norun" set "NORUN=1"
)

echo.
echo === [1/6] Checking prerequisites ===
where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python 3.10+ not found. Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  goto :fail
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo ERROR: Python 3.10 or newer is required.
  goto :fail
)
where npm >nul 2>nul
if errorlevel 1 (
  echo ERROR: Node.js 18+ not found. Install it from https://nodejs.org/ then run this again.
  goto :fail
)

echo.
echo === [2/6] Creating virtual environment ===
if not exist "%ROOT%\.venv\Scripts\python.exe" (
  python -m venv "%ROOT%\.venv"
  if errorlevel 1 goto :fail
)
set "PY=%ROOT%\.venv\Scripts\python.exe"
"%PY%" -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo.
echo === [3/6] Installing Laya ===
pushd "%ROOT%\laya"
"%PY%" -m pip install -e ".[dev]"
if errorlevel 1 ( popd & goto :fail )

set "HAVE_LLM=0"
if "%NOMODEL%"=="0" (
  echo.
  echo === [4/6] Installing local model runtime and downloading the 0.5B model ===
  echo Installing llama-cpp-python - prebuilt CPU wheel, no compiler needed...
  "%PY%" -m pip install --prefer-binary --only-binary=llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu "llama-cpp-python>=0.2.90" huggingface-hub
  if errorlevel 1 (
    echo WARNING: could not install llama-cpp-python. Laya will use the built-in mock model instead.
  ) else (
    if exist "models\qwen2.5-0.5b-instruct-q4_k_m.gguf" (
      echo Model already downloaded.
      set "HAVE_LLM=1"
    ) else (
      "%PY%" scripts\download_model.py
      if errorlevel 1 (
        echo WARNING: model download failed. Laya will use the mock model. Re-run setup.bat to retry.
      ) else (
        set "HAVE_LLM=1"
      )
    )
  )
) else (
  echo.
  echo === [4/6] Skipped model download - /nomodel ===
)

echo.
echo === [5/6] Running tests ===
"%PY%" -m pytest -q
if errorlevel 1 (
  echo WARNING: some tests failed - continuing anyway.
)
popd

echo.
echo === [6/6] Building the dashboard ===
pushd "%ROOT%\dashboard"
call npm install --no-audit --no-fund
if errorlevel 1 ( popd & goto :fail )
call npm run build
if errorlevel 1 ( popd & goto :fail )
popd

echo.
echo ============================================================
echo  Setup complete.
if "!HAVE_LLM!"=="1" ( echo  Model: Qwen2.5-0.5B ^(local^) ) else ( echo  Model: mock ^(scripted stand-in^) - run setup.bat again without /nomodel for the real one )
echo  Start later with run.bat
echo ============================================================
if "%NORUN%"=="1" goto :end

echo.
echo Starting Laya at http://127.0.0.1:8000  ^(Ctrl+C to stop^)
start "" "http://127.0.0.1:8000"
cd /d "%ROOT%\laya"
"%ROOT%\.venv\Scripts\laya.exe" serve
goto :end

:fail
echo.
echo Setup failed. See the messages above.
pause
exit /b 1

:end
endlocal
