@echo off
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%Start-Web-Dashboard.ps1"
if errorlevel 1 (
  echo.
  echo Launch failed. Press any key to close this window.
  pause >nul
)
