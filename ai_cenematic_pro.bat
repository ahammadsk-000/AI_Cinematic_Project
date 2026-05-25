@echo off
title Cineforge - Cinematic AI Video Platform - Launcher
setlocal enabledelayedexpansion

echo ==================================================
echo   Cineforge - Cinematic AI Video Platform
echo ==================================================
echo.

set "ROOT=%~dp0"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"
set "VENV=%ROOT%.venv"

:: ---------------------------------------------------------------------------
:: Release the ports first. A previous uvicorn/Next worker whose window was
:: closed with X (not Ctrl+C) keeps its socket bound; the new process then
:: fails to bind silently. We kill only the PID owning each port.
:: ---------------------------------------------------------------------------
echo [INFO] Releasing port %BACKEND_PORT% (backend) and %FRONTEND_PORT% (frontend)...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr LISTENING ^| findstr ":%BACKEND_PORT% "') do (
    taskkill /F /PID %%P >nul 2>&1
)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr LISTENING ^| findstr ":%FRONTEND_PORT% "') do (
    taskkill /F /PID %%P >nul 2>&1
)

:: ---------------------------------------------------------------------------
:: Python virtual environment. Create + install backend deps on first run.
:: ---------------------------------------------------------------------------
if not exist "%VENV%\Scripts\python.exe" goto MAKE_VENV
goto CHECK_DEPS

:MAKE_VENV
echo [INFO] First run: creating Python virtual environment...
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from https://python.org
    goto FAIL
)
python -m venv "%VENV%"

:CHECK_DEPS
:: Verify a representative backend dependency is present. If the venv is missing
:: or incomplete (e.g. created before a requirement was added), (re)install the
:: full requirements. import is cheap; a satisfied pip install is a no-op.
"%VENV%\Scripts\python.exe" -c "import fastapi, asyncpg, uvicorn" >nul 2>nul
if not errorlevel 1 goto VENV_OK
echo [INFO] Installing/updating backend dependencies (one-time, please wait)...
"%VENV%\Scripts\python.exe" -m pip install -q --upgrade pip
"%VENV%\Scripts\python.exe" -m pip install -q -r "%ROOT%apps\api\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Backend dependency install failed.
    goto FAIL
)
:VENV_OK

:: Put the venv's Scripts on PATH for the child windows (quoted so the
:: existing PATH, which may contain parentheses like "Program Files (x86)",
:: cannot break parsing).
set "PATH=%VENV%\Scripts;%PATH%"

:: ---------------------------------------------------------------------------
:: npm / Node.js (with PATH fallback for a fresh Node install)
:: ---------------------------------------------------------------------------
where npm >nul 2>nul
if not errorlevel 1 goto NPM_OK
if exist "%ProgramFiles%\nodejs\npm.cmd" set "PATH=%ProgramFiles%\nodejs;%PATH%"
if exist "%LOCALAPPDATA%\Programs\nodejs\npm.cmd" set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
where npm >nul 2>nul
if not errorlevel 1 goto NPM_OK
echo [ERROR] npm not found. Install Node.js 18+ from https://nodejs.org
echo         If you just installed it, open a NEW window (or reboot) and retry.
goto FAIL
:NPM_OK

if exist "%ROOT%apps\web\node_modules" goto NPM_DEPS_OK
echo [INFO] Installing frontend npm packages (one-time)...
cd /d "%ROOT%apps\web"
call npm install
if errorlevel 1 (
    echo [ERROR] npm install failed.
    goto FAIL
)
:NPM_DEPS_OK

:: ---------------------------------------------------------------------------
:: Backend environment (set in THIS shell; the child window inherits it).
::   * If apps\api\.env exists  -> CLOUD mode: the backend reads DB/Redis from
::     that file (point it at Supabase + Upstash so a Colab worker shares the
::     same queue). We don't override those vars here.
::   * Else if Docker is running -> local Postgres + Redis.
::   * Else                       -> local SQLite (UI works; rendering needs a worker).
:: ---------------------------------------------------------------------------
set "ENVIRONMENT=dev"
set "PYTHONIOENCODING=utf-8"

if exist "%ROOT%apps\api\.env" goto DB_ENVFILE

set "SECRET_KEY=local-dev-secret"
set "DATABASE_URL=sqlite+aiosqlite:///./cineforge_dev.db"
set "ENABLE_REAPER=false"

where docker >nul 2>nul
if errorlevel 1 goto DB_SQLITE
docker info >nul 2>nul
if errorlevel 1 goto DB_SQLITE
echo [INFO] Docker detected - starting Postgres + Redis...
cd /d "%ROOT%"
docker compose up -d postgres redis >nul 2>&1
if errorlevel 1 goto DB_SQLITE
set "DATABASE_URL=postgresql+asyncpg://cineforge:cineforge@localhost:5432/cineforge"
set "ENABLE_REAPER=true"
echo [INFO] Postgres + Redis are up (full job queue enabled).
goto DB_DONE
:DB_SQLITE
echo [INFO] Docker not available - using a local SQLite database.
echo        You can register, browse and use the UI. Rendering videos needs
echo        Redis + a GPU worker (see docs\SETUP.md).
goto DB_DONE
:DB_ENVFILE
echo [INFO] CLOUD mode: backend reading DB/Redis from apps\api\.env
echo        (point a Colab worker at the SAME Supabase + Upstash to render).
:DB_DONE

:: ---------------------------------------------------------------------------
:: Start the backend (FastAPI / uvicorn) in its own window. Run from apps\api
:: so "app.main" resolves. The simple command inherits env + PATH from here.
:: ---------------------------------------------------------------------------
echo [INFO] Starting Backend on port %BACKEND_PORT%...
start "Cineforge Backend" /d "%ROOT%apps\api" cmd /k python -m uvicorn app.main:app --reload --host 0.0.0.0 --port %BACKEND_PORT%

:: Wait up to ~20s for the backend health endpoint
echo [INFO] Waiting for backend to start...
set /a TRIES=0
:WAIT_LOOP
timeout /t 2 /nobreak >nul
curl -s http://localhost:%BACKEND_PORT%/health | findstr "ok" >nul
if not errorlevel 1 goto BACKEND_READY
set /a TRIES+=1
if !TRIES! lss 10 goto WAIT_LOOP
echo [WARN] Backend not responding yet, continuing anyway...

:BACKEND_READY
:: Start the frontend (Next.js dev server) in its own window
echo [INFO] Starting Frontend on port %FRONTEND_PORT%...
start "Cineforge Frontend" /d "%ROOT%apps\web" cmd /k npm run dev

:: Give Next.js a moment to compile, then open the browser
echo [INFO] Opening the studio in your browser...
timeout /t 6 /nobreak >nul
start "" "http://localhost:%FRONTEND_PORT%"

echo.
echo ==================================================
echo   CINEFORGE IS RUNNING
echo ==================================================
echo   Studio (UI) : http://localhost:%FRONTEND_PORT%
echo   Backend API : http://localhost:%BACKEND_PORT%
echo   API docs    : http://localhost:%BACKEND_PORT%/docs
echo --------------------------------------------------
echo   To render videos, start a GPU worker:
echo     - Local GPU : python -m gpu_worker
echo     - Free GPU  : notebooks\colab_gpu_worker.ipynb
echo ==================================================
echo.
echo Keep the Backend and Frontend windows open.
echo Press any key to close THIS launcher window only.
echo.
pause
goto END

:FAIL
echo.
echo [ERROR] Launcher stopped. See the message above.
echo.
pause

:END
endlocal
