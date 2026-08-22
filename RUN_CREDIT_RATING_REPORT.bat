@echo off
setlocal
cd /d "%~dp0"
set /p TICKER=Nhap ma ngan hang (VD: KLB, STB, VCB): 
if "%TICKER%"=="" set TICKER=KLB
if not exist reports mkdir reports
python scripts\generate_credit_rating_report.py --ticker %TICKER% --out_dir reports
if errorlevel 1 (
  echo.
  echo CO LOI KHI TAO BAO CAO XHTN.
  pause
  exit /b 1
)
echo.
echo HOAN TAT. Bao cao nam trong thu muc reports.
pause
