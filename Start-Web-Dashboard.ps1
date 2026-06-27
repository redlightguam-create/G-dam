$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$BackendScript = Join-Path $Root "Start-Backend.ps1"
$FrontendScript = Join-Path $Root "Start-Frontend.ps1"

function Wait-ForUrl {
    param(
        [string] $Url,
        [int] $TimeoutSeconds = 90
    )

    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
            return $true
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $false
}

Write-Host "Launching Music Distribution Organizer web dashboard..." -ForegroundColor Green
Write-Host ""
Write-Host "Backend:  http://127.0.0.1:8000/docs"
Write-Host "Frontend: http://127.0.0.1:5173/"
Write-Host ""
Write-Host "Two PowerShell windows will open. Keep both open while using the web dashboard."
Write-Host ""

Start-Process powershell.exe -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$BackendScript`"" -WorkingDirectory $Root

Start-Sleep -Seconds 2

Start-Process powershell.exe -ArgumentList "-NoExit -ExecutionPolicy Bypass -File `"$FrontendScript`"" -WorkingDirectory $Root

Start-Sleep -Seconds 3

Write-Host "Waiting for backend..." -ForegroundColor Yellow
$BackendReady = Wait-ForUrl "http://127.0.0.1:8000/docs"

Write-Host "Waiting for frontend..." -ForegroundColor Yellow
$FrontendReady = Wait-ForUrl "http://127.0.0.1:5173/"

if ($FrontendReady) {
    Write-Host "Dashboard is ready." -ForegroundColor Green
    Start-Process "http://127.0.0.1:5173/"
} else {
    Write-Host "Frontend did not respond yet. Keep the frontend window open and try http://127.0.0.1:5173/ in a moment." -ForegroundColor Yellow
}

if (-not $BackendReady) {
    Write-Host "Backend did not respond yet. Check the backend window for errors." -ForegroundColor Yellow
}
