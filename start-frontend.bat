@echo off
REM ============================================================
REM  PGR Platform - frontend (Next.js 14) on http://localhost:3000
REM  Proxies /api/v1 + /health to the backend on :8000.
REM
REM  Auto-picks the right mode for the environment:
REM    - OneDrive-synced checkout (the local dev box): the Next DEV server. OneDrive rewrites
REM      .next chunk files mid-build, so a production build fails with "Cannot find module
REM      './xxxx.js'". Dev compiles on demand and is stable on synced folders.
REM    - Anywhere else (the hosting VM): a PRODUCTION build + start. Next bakes the rewrite
REM      destination at build time, so we rebuild when the baked backend origin is stale.
REM ============================================================
cd /d "%~dp0frontend"

if not exist "node_modules" (
    echo Frontend dependencies not found. Run setup.bat first.
    pause & exit /b 1
)

REM Canonical backend origin - must match start-backend.bat. Read at runtime by dev,
REM baked at build time for production. Persist so rebuilds pick up the same value.
set "BACKEND_ORIGIN=http://127.0.0.1:8000"
> .env.local echo BACKEND_ORIGIN=%BACKEND_ORIGIN%

REM --- Local (OneDrive) dev box: run the Next dev server (stable on synced folders) ---
echo "%~dp0" | findstr /I "OneDrive" >nul
if not errorlevel 1 (
    echo OneDrive checkout detected - starting the Next DEV server on http://localhost:3000
    echo ^(dev mode is stable on synced folders; production build is not. Press Ctrl+C to stop.^)
    echo.
    call npm run dev
    pause
    exit /b 0
)

REM ============================================================
REM  VM / non-OneDrive: PRODUCTION build + start (bakes BACKEND_ORIGIN at build time).
REM ============================================================
REM Rebuild when there's no prior build, or the baked rewrite destination is stale.
set "NEED_BUILD="
if not exist ".next\BUILD_ID" set "NEED_BUILD=1"
if exist ".next\routes-manifest.json" (
    findstr /C:"127.0.0.1:8000" ".next\routes-manifest.json" >nul 2>&1
    if errorlevel 1 set "NEED_BUILD=1"
)

REM A .next present without a BUILD_ID is a half-finished / corrupt build - wipe it before
REM rebuilding. A healthy build keeps its .next cache, so normal deploys stay fast.
if defined NEED_BUILD (
    if exist ".next" if not exist ".next\BUILD_ID" (
        echo Removing an incomplete/corrupt .next before rebuild...
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

echo Starting PGR frontend ^(production^) on http://localhost:3000
echo (Press Ctrl+C to stop)
echo.
call npm run start
pause
