@echo off
setlocal
cd /d "%~dp0"
set "PYBRONZE=C:\Users\HP\.venv\Scripts\python.exe"
if not exist "%PYBRONZE%" set "PYBRONZE=python"
set "VNSTOCK_WORKERS=4"

echo ============================================================
echo CAP NHAT GIA CO PHIEU - INCREMENTAL, KHONG GOI BCTC
echo ============================================================
"%PYBRONZE%" scripts\refresh_vnstock.py --mode prices --workers %VNSTOCK_WORKERS%
if errorlevel 1 goto :error
"%PYBRONZE%" scripts\build_valuation.py
if errorlevel 1 goto :error
git add -A
git diff --cached --quiet
if errorlevel 1 (
  git commit -m "Refresh bank market prices"
  git push origin main
) else echo Khong co thay doi Git de commit.
echo.
echo HOAN TAT.
pause
exit /b 0
:error
echo CO LOI. Xem thong bao phia tren.
pause
exit /b 1
