@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo RUN_UPDATE_AND_PUSH da duoc toi uu.
echo Mac dinh se chay FULL REFRESH INCREMENTAL.
echo De nhanh hon hay dung RUN_FAST.bat hoac RUN_REFRESH_ONE_BANK.bat.
echo ============================================================
call RUN_FULL_REFRESH.bat
exit /b %errorlevel%
