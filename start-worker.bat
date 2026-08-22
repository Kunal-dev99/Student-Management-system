@echo off
REM ============================================================
REM  PGR Platform - background worker (Phase 4A).
REM  Runs periodic jobs, outbox dispatch (retry/dead-letter), and
REM  notification/email delivery. Shares the backend venv + DB.
REM ============================================================
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo Backend venv not found. Run setup.bat first.
    pause & exit /b 1
)

echo Starting PGR background worker (scheduled jobs + outbox dispatch + notifications).
echo (Press Ctrl+C to stop)
echo.
".venv\Scripts\python.exe" -m app.worker
pause
