@echo off
REM ============================================================
REM  PGR Platform - backend API (FastAPI) on http://localhost:8000
REM
REM  Bound to 0.0.0.0 (all interfaces). The frontend proxy target is 8000
REM  everywhere; keep them aligned with start-frontend.bat.
REM ============================================================
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo Backend venv not found. Run setup.bat first.
    pause & exit /b 1
)

REM --- Free port 8000 before binding (self-reliant: kill any stale listener) ---
echo Freeing port 8000 if anything is holding it...
for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do (
    echo   port 8000 busy - killing PID %%A
    taskkill /F /PID %%A >nul 2>&1
)
REM Give Windows a moment to release the socket before uvicorn binds.
ping -n 3 127.0.0.1 >nul

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
