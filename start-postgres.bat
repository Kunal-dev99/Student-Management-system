@echo off
REM ============================================================
REM  PGR Platform - ensure the PostgreSQL service is running.
REM  (Postgres 18 is installed as a Windows service set to auto-start,
REM   so this is usually already up. Starting it may need admin rights.)
REM ============================================================
set "PG_SERVICE=postgresql-x64-18"

sc query "%PG_SERVICE%" | find "RUNNING" >nul
if errorlevel 1 (
    echo %PG_SERVICE% is not running - starting it...
    net start "%PG_SERVICE%"
    if errorlevel 1 (
        echo.
        echo Could not start it automatically. Open an ADMIN terminal and run:
        echo     net start %PG_SERVICE%
    )
) else (
    echo %PG_SERVICE% is already running.
)
echo.
echo (Server on localhost:5432, database 'pgr'.)
ping -n 2 127.0.0.1 >nul
