@echo off
REM ============================================================
REM  PGR Platform - frontend in DEV mode (hot reload) on :3000
REM  Use while actively editing UI code. NOTE: on OneDrive-synced
REM  folders Next.js dev can corrupt its chunk cache ("Cannot find
REM  module './xxx.js'"). If that happens, stop, delete frontend\.next,
REM  and restart - or just use start-frontend.bat (production).
REM ============================================================
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo Frontend dependencies not found. Run setup.bat first.
    pause & exit /b 1
)

echo Starting PGR frontend (dev / hot reload) on http://localhost:3000
echo (Press Ctrl+C to stop)
echo.
call npm run dev
pause
