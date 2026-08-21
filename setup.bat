@echo off
REM ============================================================
REM  PGR Platform - one-time setup (backend venv + deps, frontend deps)
REM  Run this ONCE before start-all.bat. Safe to re-run.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === [1/4] Backend virtual environment ===
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" (
    echo Creating venv...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: could not create venv. Is Python installed and on PATH?
        pause & exit /b 1
    )
) else (
    echo venv already exists - skipping.
)

echo.
echo === [2/4] Backend dependencies ===
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo ERROR: backend pip install failed. & pause & exit /b 1 )

echo.
echo === [3/5] Database migrations (SQLite by default) ===
".venv\Scripts\alembic.exe" upgrade head
if errorlevel 1 ( echo WARNING: alembic upgrade failed - continuing. )

echo.
echo === [4/5] Seed demo data (roles, admin user, sample persons) ===
".venv\Scripts\python.exe" -m app.db.seed
if errorlevel 1 ( echo WARNING: seed failed - continuing. )

echo.
echo === [5/5] Frontend deps + production build (this can take a few minutes) ===
cd /d "%~dp0frontend"
call npm install --no-audit --no-fund
if errorlevel 1 ( echo ERROR: npm install failed. Is Node.js installed? & pause & exit /b 1 )
call npm run build
if errorlevel 1 ( echo ERROR: frontend build failed. & pause & exit /b 1 )

echo.
echo ============================================================
echo  Setup complete. Launch the app with:  start-all.bat
echo  Login: admin@example.com / admin123
echo ============================================================
pause
