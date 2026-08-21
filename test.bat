@echo off
REM ============================================================
REM  PGR Platform - run backend tests + frontend production build
REM ============================================================
cd /d "%~dp0"

echo === Backend tests (pytest) ===
cd /d "%~dp0backend"
if not exist ".venv\Scripts\python.exe" ( echo Run setup.bat first. & pause & exit /b 1 )
".venv\Scripts\python.exe" -m pytest -q
set BE_RESULT=%errorlevel%

echo.
echo === Frontend build (next build) ===
cd /d "%~dp0frontend"
if not exist "node_modules" ( echo Run setup.bat first. & pause & exit /b 1 )
call npm run build
set FE_RESULT=%errorlevel%

echo.
echo ============================================================
if "%BE_RESULT%"=="0" (echo Backend tests : PASS) else (echo Backend tests : FAIL)
if "%FE_RESULT%"=="0" (echo Frontend build: PASS) else (echo Frontend build: FAIL)
echo ============================================================
pause
