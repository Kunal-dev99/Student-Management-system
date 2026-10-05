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
    REM OneDrive turns idle .next files into cloud placeholders ^(reparse points^); Next's startup
    REM cleanup then fails with "EINVAL: readlink .next\package.json". Dev rebuilds .next on
    REM demand, so clear it first.
    if exist ".next" (
        echo Clearing .next ^(OneDrive can leave unreadable placeholder files in it^)...
        rmdir /s /q ".next" 2>nul
    )
    echo.
    REM Dev builds each page on its first visit (the half-second "lag" on first clicks). Warm-up
    REM requests every page once in the background, so they're built before anyone clicks.
    echo Warming up pages in the background - "[warm-up] ... compiled" appears when done.
    start "" /b node scripts\warmup.mjs
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

REM Rebuild when the SOURCE changed since the last build. next start serves the built .next, so a
REM `git pull` alone leaves the public URL on the old build. Compare the current git commit to the
REM stamp written after the last successful build, and rebuild if they differ.
set "CUR_COMMIT="
for /f "delims=" %%H in ('git rev-parse HEAD 2^>nul') do set "CUR_COMMIT=%%H"
set "BUILT_COMMIT="
if exist ".next\COMMIT_ID" set /p BUILT_COMMIT=<".next\COMMIT_ID"
if defined CUR_COMMIT if not "%CUR_COMMIT%"=="%BUILT_COMMIT%" set "NEED_BUILD=1"

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
    REM Stamp the build with the commit it was built from, so the next start rebuilds only when
    REM the source has actually moved on.
    if defined CUR_COMMIT ( >".next\COMMIT_ID" echo %CUR_COMMIT%)
) else (
    echo Reusing existing build ^(commit %BUILT_COMMIT%, backend origin %BACKEND_ORIGIN%^).
)

echo Starting PGR frontend ^(production^) on http://localhost:3000
echo (Press Ctrl+C to stop)
echo.
call npm run start
pause
