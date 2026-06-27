$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ClientSecretsPath = Join-Path $Root "client_secrets.json"
$TokenPath = Join-Path $env:LOCALAPPDATA "Music Distribution Organizer\google_drive_token.pickle"
$OutputPath = Join-Path $Root "hosted-secrets.txt"

if (-not (Test-Path -LiteralPath $ClientSecretsPath)) {
    throw "Missing client_secrets.json in $Root"
}

if (-not (Test-Path -LiteralPath $TokenPath)) {
    throw "Missing Google token at $TokenPath. Run the app locally and finish Google sign-in first."
}

$ClientSecretsBase64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($ClientSecretsPath))
$TokenBase64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($TokenPath))

$Content = @"
Paste these into Render as backend environment variables.

GOOGLE_CLIENT_SECRETS_BASE64=$ClientSecretsBase64

GOOGLE_DRIVE_TOKEN_BASE64=$TokenBase64

Also set:
GDAM_HOSTED=1
CORS_ORIGINS=https://YOUR-VERCEL-APP.vercel.app,http://127.0.0.1:5173,http://localhost:5173
"@

Set-Content -LiteralPath $OutputPath -Value $Content -Encoding UTF8
Write-Host "Wrote hosted deployment secrets to:"
Write-Host $OutputPath
Write-Host ""
Write-Host "Do not commit or share this file."
