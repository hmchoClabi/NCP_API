@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_service.ps1"
if errorlevel 1 pause
endlocal
