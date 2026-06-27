@echo off
set "ROOT=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%Export-Hosted-Secrets.ps1"
if errorlevel 1 (
  echo.
  echo Hosted secret export failed.
  exit /b 1
)
