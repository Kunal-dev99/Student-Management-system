@echo off
REM ============================================================
REM  PGR Platform - backend API (FastAPI) on http://localhost:8001
REM
REM  Port 8001 (not 8000) — Windows has a recurring orphan-socket
REM  issue on 8000 where a dead PID keeps the listener bound and
REM  even taskkill can't free it without a reboot. The frontend
REM  proxy target is 8001 everywhere; keep them aligned.
REM ============================================================
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo Backend venv not found. Run setup.bat first.
    pause & exit /b 1
)

echo Starting PGR backend API on http://localhost:8001
echo   Health : http://localhost:8001/health/ready
echo   Docs   : http://localhost:8001/api/v1/docs
echo (Press Ctrl+C to stop)
echo.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
pause
