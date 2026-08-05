@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_database.ps1" %*
set "SETUP_EXIT_CODE=%ERRORLEVEL%"

if not "%SETUP_EXIT_CODE%"=="0" (
    echo.
    echo Database setup failed. Review the message above.
    pause
)

exit /b %SETUP_EXIT_CODE%
