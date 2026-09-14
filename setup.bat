@echo off
REM ============================================================
REM  PGR Platform - one-time setup (backend venv + deps, frontend deps)
REM  Run this ONCE before start-all.bat. Safe to re-run.
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo === [0/5] Environment file ===
cd /d "%~dp0backend"
if exist ".env" goto :env_ok
echo.
echo ============================================================
echo WARNING: backend\.env does not exist. ".env" is gitignored, so
echo a fresh clone/pull NEVER brings it across - you must create it
echo yourself on this machine, every time, on every machine.
echo.
echo Without it, DATABASE_URL falls back to a local SQLite file
echo sqlite+aiosqlite:///./pgr_dev.db - the app APPEARS to work,
echo then breaks in confusing ways once Postgres-only assumptions,
echo like concurrent workers and real production data, don't hold.
echo.
echo Copy backend\.env.example to backend\.env and fill in a real
echo DATABASE_URL, APP_SECRET_KEY and your LLM key before continuing.
echo ============================================================
pause
:env_ok

echo.
echo === [1/5] Backend virtual environment ===
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
echo === [2/5] Backend dependencies ===
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if not errorlevel 1 goto :deps_ok
echo.
echo ============================================================
echo ERROR: backend pip install failed. Scroll up for which package.
echo The app WILL start and then crash later with a confusing
echo ModuleNotFoundError deep in a request or worker traceback if
echo you ignore this - fix the install error here, not there.
echo ============================================================
pause & exit /b 1
:deps_ok

echo.
echo === [3/5] Database migrations ===
echo Target: check backend\.env DATABASE_URL - SQLite by default if unset.
".venv\Scripts\alembic.exe" upgrade head
if not errorlevel 1 goto :migrate_ok
echo.
echo ============================================================
echo ERROR: alembic upgrade failed. STOPPING here on purpose.
echo Continuing past this used to produce a silent half-migrated
echo database - the app would start fine, then crash at runtime
echo with "no such table" the first time a background job or a
echo rarely-hit endpoint touched the table that was never created.
echo Common causes: DATABASE_URL wrong or unset in backend\.env,
echo the Postgres service not running, or a migration conflict -
echo read the error above, fix it, then re-run setup.bat.
echo ============================================================
pause & exit /b 1
:migrate_ok

echo.
echo === [4/5] Seed demo data (roles, admin user, sample persons) ===
".venv\Scripts\python.exe" -m app.db.seed
if errorlevel 1 (
    echo WARNING: seed failed - continuing, since a re-run or an
    echo already-seeded database is a common, harmless cause. If
    echo login then fails with no admin user, run this seed step
    echo manually and read its actual error.
)

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
