@echo off
setlocal
cd /d "%~dp0"
set "PYBRONZE=C:\Users\HP\.venv\Scripts\python.exe"
if not exist "%PYBRONZE%" set "PYBRONZE=python"
set "VNSTOCK_WORKERS=4"

echo ============================================================
echo REFRESH BCTC / RATIOS - KHONG TAI LAI GIA CO PHIEU
echo 20 ngan hang, xu ly song song %VNSTOCK_WORKERS% workers
echo ============================================================

echo [1/4] Doc assumptions tu Excel Master...
"%PYBRONZE%" scripts\export_master_inputs.py
if errorlevel 1 goto :error

echo [2/4] Refresh Fundamental Bronze...
"%PYBRONZE%" scripts\refresh_vnstock.py --mode fundamentals --workers %VNSTOCK_WORKERS%
if errorlevel 1 goto :error

echo [3/4] Build valuation + M^&A outputs...
"%PYBRONZE%" scripts\build_valuation.py
if errorlevel 1 goto :error

echo [4/4] Push GitHub...
call :gitpush "Refresh bank financials and valuation"
if errorlevel 1 goto :error

echo.
echo HOAN TAT. Gia co phieu cu duoc giu nguyen; BCTC/ratios da cap nhat.
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
