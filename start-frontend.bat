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

REM Canonical backend origin — must match start-backend.bat
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

REM --- Hosting-safe .next cleanup: wipe ONLY when a rebuild is happening AND the build is at
REM risk, so a healthy deploy keeps its .next cache (fast rebuilds on the VM). Two risk signals:
REM   1) .next exists but has no BUILD_ID  -> a previous build was interrupted / is corrupt.
REM   2) this checkout lives under OneDrive -> OneDrive dehydrates .next files into reparse points
REM      that Next's cleaner chokes on (EINVAL readlink) mid-rebuild.
REM The VM path isn't under OneDrive and has a healthy BUILD_ID, so it never wipes here.
set "WIPE_NEXT="
REM 1) .next present but no BUILD_ID -> a previous build was interrupted / is corrupt.
if exist ".next" if not exist ".next\BUILD_ID" set "WIPE_NEXT=1"
REM 2) OneDrive-synced checkout -> reparse-point corruption on rebuild.
echo "%~dp0" | findstr /I "OneDrive" >nul
if not errorlevel 1 if exist ".next" set "WIPE_NEXT=1"
REM Wipe only when we are actually rebuilding AND it is risky (a healthy VM cache is left alone).
if defined NEED_BUILD (
    if defined WIPE_NEXT (
        echo Removing an at-risk .next before rebuild ^(interrupted build or OneDrive checkout^)...
        rmdir /s /q ".next" 2>nul
    )
)

if defined NEED_BUILD (
    echo Building frontend ^(baking BACKEND_ORIGIN=%BACKEND_ORIGIN%^) - one-time, ~1 min...
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
