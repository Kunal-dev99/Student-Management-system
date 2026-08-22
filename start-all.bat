@echo off
REM ============================================================
REM  PGR Platform - launch backend + frontend in separate windows,
REM  then open the app in your browser.
REM ============================================================
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
    echo Setup not done yet. Running setup.bat first...
    call "%~dp0setup.bat"
)
if not exist "frontend\node_modules" (
    echo Frontend deps missing. Running setup.bat first...
    call "%~dp0setup.bat"
)

echo.
echo Ensuring PostgreSQL is running...
set "PG_SERVICE=postgresql-x64-18"
sc query "%PG_SERVICE%" | find "RUNNING" >nul
if errorlevel 1 (
    echo   %PG_SERVICE% is not running - attempting to start it...
    net start "%PG_SERVICE%" >nul 2>&1
    if errorlevel 1 (
        echo   Could not start %PG_SERVICE% automatically.
        echo   It may need administrator rights, or the service name may differ.
        echo   Open an ADMIN terminal and run:  net start %PG_SERVICE%
        echo   ^(Postgres is set to auto-start, so it is usually already running.^)
    ) else (
        echo   %PG_SERVICE% started.
    )
) else (
    echo   %PG_SERVICE% already running.
)

echo Launching backend window...
start "PGR Backend (API :8000)" cmd /k "%~dp0start-backend.bat"

echo Launching worker window...
start "PGR Worker (background jobs)" cmd /k "%~dp0start-worker.bat"

echo Launching frontend window...
start "PGR Frontend (:3000)" cmd /k "%~dp0start-frontend.bat"

echo.
echo Waiting for servers to start (about 15 seconds)...
ping -n 16 127.0.0.1 >nul

echo Opening http://localhost:3000 ...
start "" http://localhost:3000

echo.
echo Both servers are running in their own windows.
echo Close those windows (or press Ctrl+C in them) to stop.
echo To stop everything at once, run: stop.bat
