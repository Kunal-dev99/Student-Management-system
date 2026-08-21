@echo off
REM ============================================================
REM  PGR Platform - backend API (FastAPI) on http://localhost:8000
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
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
pause
