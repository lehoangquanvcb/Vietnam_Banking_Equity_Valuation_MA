@echo off
setlocal
cd /d "%~dp0"
set "PYBRONZE=C:\Users\HP\.venv\Scripts\python.exe"
if not exist "%PYBRONZE%" set "PYBRONZE=python"
set "VNSTOCK_WORKERS=2"

echo ============================================================
echo REFRESH NHANH 1 NGAN HANG
set /p BANK=Nhap ma ngan hang (vi du STB, MBB, VCB): 
if "%BANK%"=="" goto :error

echo [1/4] Doc assumptions tu Excel Master...
"%PYBRONZE%" scripts\export_master_inputs.py
if errorlevel 1 goto :error

echo [2/4] Refresh %BANK% - Fundamental + gia incremental...
"%PYBRONZE%" scripts\refresh_vnstock.py --mode full --tickers %BANK% --workers %VNSTOCK_WORKERS%
if errorlevel 1 goto :error

echo [3/4] Build lai valuation cho universe...
"%PYBRONZE%" scripts\apply_historical_supplement.py
if errorlevel 1 goto :error

"%PYBRONZE%" scripts\build_valuation.py
if errorlevel 1 goto :error

echo [4/4] Push GitHub...
call :gitpush "Refresh %BANK% bank valuation"
if errorlevel 1 goto :error

echo.
echo HOAN TAT %BANK%.
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
echo CO LOI hoac chua nhap ma ngan hang.
pause
exit /b 1
