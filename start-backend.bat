@echo off
REM ============================================================
REM  PGR Platform - backend API (FastAPI) on http://localhost:8000
REM
REM  Port 8000 is the canonical backend port - the frontend proxy target
REM  (start-frontend.bat / BACKEND_ORIGIN) must match it.
REM  Windows sometimes leaves an orphan socket holding 8000 after a hard
REM  kill: if uvicorn reports the address is in use, run stop.bat first.
REM ============================================================
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo Backend venv not found. Run setup.bat first.
    pause & exit /b 1
)

echo Starting PGR backend API on http://localhost:8000
echo   Health : http://localhost:8000/health/ready
echo   Docs   : http://localhost:8000/api/v1/docs
echo (Press Ctrl+C to stop)
echo.
REM Apply any pending schema migrations before serving. New commits routinely add
REM Alembic revisions; without this the models run ahead of the database and every
REM endpoint touching a newly added column fails with a 500 (the whole analytics /
REM reports surface did, on programme.programme_type). setup.bat is not enough --
REM it only runs once, while migrations keep arriving with new commits.
echo Applying database migrations...
".venv\Scripts\alembic.exe" upgrade head
if errorlevel 1 (
    echo.
    echo ERROR: alembic upgrade failed - refusing to serve on a stale schema.
    echo Check that PostgreSQL is running and backend\.env has a valid DATABASE_URL.
    pause ^& exit /b 1
)
echo.
REM Binding to 0.0.0.0 exposes the API on every network interface. Only safe when this box
REM sits behind a firewall / reverse-proxy that fronts it; on a direct-to-internet host the
REM API is exposed on the public IP without TLS.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
