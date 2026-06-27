$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

Set-Location $Root

if (-not (Test-Path $VenvPython)) {
    Write-Host "Python virtual environment is missing. Creating .venv..." -ForegroundColor Yellow
    py -m venv .venv
    if (-not (Test-Path $VenvPython)) {
        throw "Unable to create .venv. Make sure Python is installed and available as 'py'."
    }
}

$DependencyCheck = & $VenvPython -c "import uvicorn, fastapi, pydrive2" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Backend Python dependencies are missing. Installing requirements..." -ForegroundColor Yellow
    & $VenvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Backend dependency install failed. Check your internet connection, then run: .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    }
}

Write-Host "Starting backend API on http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Project folder: $Root"
& $VenvPython -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
