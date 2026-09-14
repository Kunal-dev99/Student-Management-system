@echo off
REM ============================================================
REM  PGR Platform - bulk ICR demo population.
REM  Runs, in order:
REM    0. clear_bulk_students  - remove any old test-format (BULK-*) seed data
REM    1. seed.py              - base roles/admin/demo data (seed.bat's job)
REM    2. seed_icr             - ICR department, programmes, funders
REM    3. seed_tenant_icr      - ICR as a real tenant (login institution)
REM    4. seed_bulk_students   - 300 students, 5 through to alumni, with docs
REM
REM  Every step is idempotent - safe to re-run any time.
REM  Requires setup.bat to have already run (venv + migrations in place).
REM ============================================================
setlocal
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ============================================================
    echo ERROR: backend venv not found at .venv\Scripts\python.exe
    echo Run setup.bat first.
    echo ============================================================
    pause & exit /b 1
)

echo.
echo === [0/4] Clearing previous test-format seed (BULK-* students) ===
".venv\Scripts\python.exe" -m scripts.clear_bulk_students
if not errorlevel 1 goto :clear_ok
echo.
echo ============================================================
echo ERROR: cleanup step failed. Scroll up for the traceback.
echo ============================================================
pause & exit /b 1
:clear_ok

echo.
echo === [1/4] Base seed (roles, admin, demo data) ===
".venv\Scripts\python.exe" -m app.db.seed
if not errorlevel 1 goto :base_ok
echo.
echo ============================================================
echo ERROR: base seed failed. Scroll up for the traceback.
echo ============================================================
pause & exit /b 1
:base_ok

echo.
echo === [2/4] ICR department, programmes, funders ===
".venv\Scripts\python.exe" -m scripts.seed_icr
if not errorlevel 1 goto :icr_ok
echo.
echo ============================================================
echo ERROR: ICR programme seed failed. Scroll up for the traceback.
echo ============================================================
pause & exit /b 1
:icr_ok

echo.
echo === [3/4] ICR tenant (login institution) ===
".venv\Scripts\python.exe" -m scripts.seed_tenant_icr
if not errorlevel 1 goto :tenant_ok
echo.
echo ============================================================
echo ERROR: ICR tenant seed failed. Scroll up for the traceback.
echo ============================================================
pause & exit /b 1
:tenant_ok

echo.
echo === [4/4] Bulk student population (300 students, 5 to alumni) ===
".venv\Scripts\python.exe" -m scripts.seed_bulk_students
if not errorlevel 1 goto :bulk_ok
echo.
echo ============================================================
echo ERROR: bulk student seed failed. Scroll up for the traceback.
echo Common cause: step [2/4] above did not actually create the ICR
echo programmes/funders this script depends on.
echo ============================================================
pause & exit /b 1
:bulk_ok

echo.
echo ============================================================
echo  Bulk seed complete.
echo  300 ICR students created, 5 reached alumni with a thesis and
echo  certificate document each; every student has at least one
echo  attached document.
echo  Login: admin@example.com / admin123
echo ============================================================
pause
