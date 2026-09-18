@echo off
REM ============================================================
REM  PGR Platform - backend API (FastAPI) on http://localhost:8000
REM
REM  Canonical port 8000, bound to 0.0.0.0 (all network interfaces). The
REM  frontend proxy target is 8000 everywhere; keep them aligned. If Windows
REM  leaves an orphan socket on 8000 (a dead PID keeping the port bound),
REM  run stop.bat to free it before starting again.
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
REM Binding to 0.0.0.0 exposes the API on every network interface. Only safe when this box
REM sits behind a firewall / reverse-proxy that fronts it; on a direct-to-internet host the
REM API is exposed on the public IP without TLS.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
