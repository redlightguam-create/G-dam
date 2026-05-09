$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$BackendScript = Join-Path $Root "Start-Backend.ps1"
$FrontendScript = Join-Path $Root "Start-Frontend.ps1"

Write-Host "Launching Music Distribution Organizer web dashboard..." -ForegroundColor Green
Write-Host ""
Write-Host "Backend:  http://127.0.0.1:8000/docs"
Write-Host "Frontend: http://127.0.0.1:5173/"
Write-Host ""
Write-Host "Two PowerShell windows will open. Keep both open while using the web dashboard."
Write-Host ""

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $BackendScript
) -WorkingDirectory $Root

Start-Sleep -Seconds 2

Start-Process powershell.exe -ArgumentList @(
    "-NoExit",
    "-ExecutionPolicy", "Bypass",
    "-File", $FrontendScript
) -WorkingDirectory $Root

Start-Sleep -Seconds 3
Start-Process "http://127.0.0.1:5173/"
