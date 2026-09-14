@echo off
REM ============================================================
REM  PGR Platform - run the database seed on its own.
REM  Use this to (re)seed without re-running the whole setup.bat
REM  (which also does venv creation, pip install, migrations, and
REM  a frontend build - unnecessary if the venv and schema are
REM  already in place and you just need seed data).
REM
REM  Seeds: roles, permissions, a demo admin user, and sample
REM  persons/students/supervisors for testing.
REM  Login after seeding:  admin@example.com / admin123
REM
REM  Safe to re-run - the seed is idempotent (checks for existing
REM  rows before inserting).
REM ============================================================
setlocal
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ============================================================
    echo ERROR: backend venv not found at .venv\Scripts\python.exe
    echo Run setup.bat first - it creates the venv and installs
    echo dependencies before any seeding can work.
    echo ============================================================
    pause & exit /b 1
)

if not exist ".env" (
    echo.
    echo ============================================================
    echo WARNING: backend\.env does not exist. Seeding will fall back
    echo to a local SQLite file instead of your real Postgres database
    echo unless DATABASE_URL is set. Press Ctrl+C now to stop and
    echo create backend\.env first, or any other key to continue
    echo anyway.
    echo ============================================================
    pause
)

echo.
echo === Running database seed ===
".venv\Scripts\python.exe" -m app.db.seed
if not errorlevel 1 goto :seed_ok
echo.
echo ============================================================
echo ERROR: seeding failed. Scroll up for the actual traceback.
echo Common causes: migrations were never run (run setup.bat or
echo alembic upgrade head first), or DATABASE_URL in backend\.env
echo points at a database that doesn't exist yet.
echo ============================================================
pause & exit /b 1
:seed_ok

echo.
echo ============================================================
echo  Seed complete.
echo  Login: admin@example.com / admin123
echo ============================================================
pause
