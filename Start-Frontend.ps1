$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$FrontendDir = Join-Path $Root "frontend"

Set-Location $FrontendDir

if (-not (Test-Path "package.json")) {
    throw "Could not find frontend\package.json. Run this script from the project root."
}

if (-not (Test-Path "node_modules")) {
    Write-Host "Frontend dependencies are missing. Running npm install..." -ForegroundColor Yellow
    npm install
}

Write-Host "Starting frontend dashboard on http://127.0.0.1:5173" -ForegroundColor Green
npm run dev
