$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

Set-Location $Root

if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

Write-Host "Starting backend API on http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Project folder: $Root"
& $Python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
