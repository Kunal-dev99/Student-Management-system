@echo off
REM ============================================================
REM  PGR Platform - launch backend + worker + frontend in separate
REM  windows, wait for backend to be healthy BEFORE the frontend
REM  starts (so the login page never proxies to a dead backend and
REM  users never see ECONNREFUSED spam), then open the app.
REM
REM  Canonical ports:
REM    backend  :8001   (8000 is skipped — recurring orphan socket)
REM    frontend :3000
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
echo Freeing ports 8001 (backend) and 3000 (frontend) if anything is holding them...
for %%P in (8001 3000) do (
    for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do (
        echo   port %%P busy - killing PID %%A
        taskkill /F /PID %%A >nul 2>&1
    )
)
REM Give Windows a moment to release the sockets before uvicorn/next bind.
ping -n 3 127.0.0.1 >nul

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

echo.
echo Launching backend window ^(:8001^)...
start "PGR Backend (API :8001)" cmd /k "%~dp0start-backend.bat"

echo Waiting for backend health on http://127.0.0.1:8001/health/ready ...
set /a _btries=0
:backend_wait
set /a _btries+=1
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8001/health/ready; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto backend_ready
if %_btries% geq 30 goto backend_timeout
ping -n 3 127.0.0.1 >nul
goto backend_wait
:backend_timeout
echo.
echo ============================================================
echo   Backend didn't become healthy after ~90s.
echo   Check the "PGR Backend (API :8001)" window for the error
echo   (Postgres unreachable, migration failed, port collision).
echo   The frontend will still start, but /api calls will fail
echo   until the backend is up.
echo ============================================================
goto after_backend
:backend_ready
echo   Backend is healthy.
:after_backend

echo Launching worker window...
start "PGR Worker (background jobs)" cmd /k "%~dp0start-worker.bat"

echo Launching frontend window ^(:3000^)...
start "PGR Frontend (:3000)" cmd /k "%~dp0start-frontend.bat"

echo.
echo Waiting for the frontend to be ready on http://localhost:3000 ...
echo   (a cold production build can take ~1 minute the first time)
set /a _tries=0
:waitloop
set /a _tries+=1
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://localhost:3000; if ($r.Content -match 'PGR Platform') { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 goto frontend_ready
if %_tries% geq 60 goto frontend_timeout
ping -n 3 127.0.0.1 >nul
goto waitloop
:frontend_timeout
echo   Frontend still not responding after ~3 min. Check the "PGR Frontend (:3000)" window
echo   for a build error. If it loads a BLANK page, the .next build is stale/corrupt:
echo   close it, delete the frontend\.next folder, and run start-all.bat again to rebuild.
goto open_browser
:frontend_ready
echo   Frontend is ready.
:open_browser
echo Opening http://localhost:3000 ...
start "" http://localhost:3000

echo.
echo All servers are running in their own windows.
echo Close those windows (or press Ctrl+C in them) to stop.
echo To stop everything at once, run: stop.bat
