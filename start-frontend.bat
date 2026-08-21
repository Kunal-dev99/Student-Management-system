@echo off
REM ============================================================
REM  PGR Platform - frontend (Next.js 14) on http://localhost:3000
REM  Runs a PRODUCTION build (stable on OneDrive; dev-mode hot reload
REM  corrupts its chunk cache on synced folders). Proxies /api/v1 + /health
REM  to the backend on :8000.
REM ============================================================
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo Frontend dependencies not found. Run setup.bat first.
    pause & exit /b 1
)

if not exist ".next\BUILD_ID" (
    echo No production build found - building now (one-time, ~1 min)...
    call npm run build
    if errorlevel 1 ( echo Build failed. & pause & exit /b 1 )
)

echo Starting PGR frontend on http://localhost:3000
echo (Press Ctrl+C to stop)
echo.
call npm run start
pause
