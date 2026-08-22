@echo off
setlocal
cd /d "%~dp0"
set "PYBRONZE=C:\Users\HP\.venv\Scripts\python.exe"
if not exist "%PYBRONZE%" set "PYBRONZE=python"

echo ============================================================
echo ENGINE V5.0 - CHE DO NHANH - KHONG GOI VNSTOCK
echo Excel assumptions ^> valuation/report outputs ^> GitHub
echo ============================================================

echo [1/4] Doc assumptions tu Excel Master...
"%PYBRONZE%" scripts\export_master_inputs.py
if errorlevel 1 goto :error

echo [2/4] Sua du lieu cache + guardrails CAR/NPL/CIR...
"%PYBRONZE%" scripts\repair_cached_data.py
if errorlevel 1 goto :error

echo [3/4] Build lai valuation + M^&A + report outputs tu CSV hien co...
"%PYBRONZE%" scripts\build_valuation.py
if errorlevel 1 goto :error

echo [4/4] Push GitHub neu co thay doi...
call :gitpush "Fast rebuild valuation and reports"
if errorlevel 1 goto :error

echo.
echo HOAN TAT - KHONG CO API VNSTOCK NAO DUOC GOI.
pause
exit /b 0

:gitpush
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m %1
  if errorlevel 1 exit /b 1
  git push origin main
  if errorlevel 1 exit /b 1
) else (
  echo Khong co thay doi Git de commit.
)
exit /b 0

:error
echo.
echo CO LOI. Xem thong bao phia tren.
pause
exit /b 1
