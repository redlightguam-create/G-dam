$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$FrontendDir = Join-Path $Root "frontend"

Set-Location $FrontendDir

if (-not (Test-Path "package.json")) {
    throw "Could not find frontend\package.json. Run this script from the project root."
}

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "npm was not found. Install Node.js, then run the launcher again."
}

if (-not (Test-Path "node_modules") -or -not (Test-Path "node_modules\.bin\vite.cmd")) {
    Write-Host "Frontend dependencies are missing. Running npm install..." -ForegroundColor Yellow
    npm.cmd install
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend dependency install failed. Check your internet connection, then run: cd frontend; npm.cmd install"
    }
}

Write-Host "Starting frontend dashboard on http://127.0.0.1:5173" -ForegroundColor Green
npm.cmd run dev
if ($LASTEXITCODE -ne 0) {
    throw "Frontend dev server failed to start. Try closing old frontend windows and run the launcher again."
}
