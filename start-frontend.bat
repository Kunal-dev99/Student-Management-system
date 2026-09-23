@echo off
REM ============================================================
REM  PGR Platform - frontend (Next.js 14) on http://localhost:3000
REM  Runs a PRODUCTION build (stable on OneDrive; dev-mode hot reload
REM  corrupts its chunk cache on synced folders). Proxies /api/v1 + /health
REM  to the backend on :8000.
REM
REM  IMPORTANT: Next bakes rewrite destinations at BUILD time. If the
REM  baked backend origin doesn't match what we want, we rebuild.
REM ============================================================
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo Frontend dependencies not found. Run setup.bat first.
    pause & exit /b 1
)

REM --- Free port 3000 before binding (self-reliant: kill any stale Next server) ---
echo Freeing port 3000 if anything is holding it...
for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":3000 " ^| findstr LISTENING') do (
    echo   port 3000 busy - killing PID %%A
    taskkill /F /PID %%A >nul 2>&1
)
ping -n 3 127.0.0.1 >nul

REM Canonical backend origin - must match start-backend.bat
set "BACKEND_ORIGIN=http://127.0.0.1:8000"

REM Persist to .env.local so future rebuilds (from anywhere) pick up the same value.
> .env.local echo BACKEND_ORIGIN=%BACKEND_ORIGIN%

REM Decide whether we need to (re)build:
REM   - No prior build (.next\BUILD_ID missing), OR
REM   - The baked rewrite destination doesn't contain "8000" (stale build).
set "NEED_BUILD="
if not exist ".next\BUILD_ID" set "NEED_BUILD=1"
if exist ".next\routes-manifest.json" (
    findstr /C:"127.0.0.1:8000" ".next\routes-manifest.json" >nul 2>&1
    if errorlevel 1 set "NEED_BUILD=1"
)

if defined NEED_BUILD (
    echo Building frontend ^(baking BACKEND_ORIGIN=%BACKEND_ORIGIN%^) - one-time, ~1 min...
    REM OneDrive turns .next files into reparse points that Next's own cleaner
    REM chokes on (EINVAL readlink). Wipe .next ourselves first so the build is clean.
    if exist ".next" rmdir /s /q ".next" 2>nul
    call npm run build
    if errorlevel 1 (
        echo.
        echo ============================================================
        echo BUILD FAILED. Frontend will not start.
        echo Scroll up for the error. Common fixes:
        echo   - Type errors: run 'npx tsc --noEmit' in the frontend folder
        echo   - Missing deps: run setup.bat again
        echo ============================================================
        pause
        exit /b 1
    )
) else (
    echo Reusing existing build ^(backend origin already baked as %BACKEND_ORIGIN%^).
)

echo Starting PGR frontend on http://localhost:3000
echo (Press Ctrl+C to stop)
echo.
call npm run start
pause
