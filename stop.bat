@echo off
REM ============================================================
REM  PGR Platform - stop whatever is listening on :8001 and :3000
REM  (Also tries :8000 in case an old build is still around.)
REM ============================================================
echo Stopping backend (:8001) and frontend (:3000)...

for %%P in (8001 8000 3000) do (
    for /f "tokens=5" %%A in ('netstat -ano ^| findstr ":%%P " ^| findstr LISTENING') do (
        echo   killing PID %%A on port %%P
        taskkill /F /PID %%A >nul 2>&1
    )
)

echo Done.
ping -n 2 127.0.0.1 >nul
