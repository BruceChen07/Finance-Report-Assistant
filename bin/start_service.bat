@echo off
setlocal enableextensions

rem ==============================================================================
rem Finance Report Assistant - Start Services (Windows)
rem - Starts backend (FastAPI/Uvicorn) and frontend (Vite) from any working folder
rem - Writes startup logs under: <project_root>\output\logs\
rem - Performs basic dependency checks and prints status
rem ==============================================================================

set "SCRIPT_DIR=%~dp0"
set "ROOT_DIR=%SCRIPT_DIR%.."
for %%I in ("%ROOT_DIR%") do set "ROOT_DIR=%%~fI"

rem Warn if path contains non-ASCII characters (best-effort)
echo %ROOT_DIR% | findstr /r "[^ -~]" >nul
if not errorlevel 1 (
  echo [WARN] Project path contains non-ASCII characters. Some tools may misbehave:
  echo        %ROOT_DIR%
)

set "FRONTEND_DIR=%ROOT_DIR%\frontend"
set "VENV_PY=%ROOT_DIR%\.venv\Scripts\python.exe"

set "LOG_DIR=%ROOT_DIR%\output\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>nul

for /f "tokens=1-3 delims=/ " %%a in ("%date%") do set "DATE_STAMP=%%a%%b%%c"
for /f "tokens=1-3 delims=:., " %%a in ("%time%") do set "TIME_STAMP=%%a%%b%%c"
set "TIME_STAMP=%TIME_STAMP: =0%"

set "BACKEND_LOG=%LOG_DIR%\backend_%DATE_STAMP%_%TIME_STAMP%.log"
set "FRONTEND_LOG=%LOG_DIR%\frontend_%DATE_STAMP%_%TIME_STAMP%.log"

echo [INFO] Project root: %ROOT_DIR%
echo [INFO] Logs:
echo        %BACKEND_LOG%
echo        %FRONTEND_LOG%

rem ---- Dependency checks ----
set "PY="

rem Prefer the currently activated virtual environment (PowerShell/CMD) if present
if defined VIRTUAL_ENV (
  if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
    set "PY=%VIRTUAL_ENV%\Scripts\python.exe"
  )
)

rem Fallback to project-local venv under .venv
if not defined PY (
  if exist "%VENV_PY%" (
    set "PY=%VENV_PY%"
  )
)

rem Fallback to system Python on PATH
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 (
    set "PY=python"
  ) else (
    where py >nul 2>nul
    if not errorlevel 1 (
      set "PY=py"
    )
  )
)

rem Final validation
if not defined PY (
  echo [ERROR] Python not found.
  echo         Install Python and ensure python/py is on PATH, or activate/create a virtual environment.
  echo         Expected project venv path: %VENV_PY%
  exit /b 2
)

if /i not "%PY%"=="python" if /i not "%PY%"=="py" (
  if not exist "%PY%" (
    echo [ERROR] Python executable not found: %PY%
    exit /b 2
  )
)

where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js not found. Install Node.js (LTS recommended).
  exit /b 2
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm not found. Ensure Node.js installation includes npm.
  exit /b 2
)

if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] Frontend package.json not found: %FRONTEND_DIR%\package.json
  exit /b 2
)

if not exist "%ROOT_DIR%\src\main.py" (
  echo [ERROR] Backend entry not found: %ROOT_DIR%\src\main.py
  exit /b 2
)

echo [INFO] Checking backend Python deps...
pushd "%ROOT_DIR%" >nul
"%PY%" -c "import fastapi, uvicorn" 1>nul 2>nul
if errorlevel 1 (
  echo [ERROR] Missing backend deps. Run: pip install -r requirements.txt
  popd >nul
  exit /b 2
)
popd >nul

echo [INFO] Checking frontend deps...
if not exist "%FRONTEND_DIR%\node_modules" (
  echo [WARN] frontend\node_modules not found. Run npm install under frontend\ first.
)

rem ---- Environment variables ----
set "FRA_HOST=127.0.0.1"
set "FRA_PORT=8000"
set "FRA_LOG_PROFILE=development"
set "FRA_LOG_DIR=%LOG_DIR%"

rem Optional: enable hot-reload if supported by backend logging system
set "FRA_LOG_HOT_RELOAD=true"
set "FRA_LOG_RELOAD_INTERVAL_SECONDS=2.0"

rem ---- Start backend ----
echo [INFO] Starting backend on http://%FRA_HOST%:%FRA_PORT% ...
pushd "%ROOT_DIR%" >nul
start "FRA Backend" cmd /c ""%PY%" -m src.main --serve 1>>"%BACKEND_LOG%" 2>>&1"
popd >nul

rem ---- Start frontend ----
echo [INFO] Starting frontend (Vite dev server) on http://localhost:5173 ...
pushd "%FRONTEND_DIR%" >nul
start "FRA Frontend" cmd /c "npm run dev 1>>"%FRONTEND_LOG%" 2>>&1"
popd >nul

echo [OK] Services started.
echo [OK] Backend logs:  %BACKEND_LOG%
echo [OK] Frontend logs: %FRONTEND_LOG%
echo [HINT] Close the opened service windows to stop them.
exit /b 0