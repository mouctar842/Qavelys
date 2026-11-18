param([int]$FrontendPort = 5174, [int]$BackendPort = 8001)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
if ($FrontendPort -in @(5173,8000) -or $BackendPort -in @(5173,8000) -or $FrontendPort -eq $BackendPort) { throw 'Utiliser des ports de test distincts des serveurs utilisateur.' }
function Invoke-E2ENative {
    param([scriptblock]$Command)
    $previous = $ErrorActionPreference
    try { $ErrorActionPreference = 'Continue'; & $Command; $taskExit = $LASTEXITCODE } finally { $ErrorActionPreference = $previous }
    if ($taskExit -ne 0) { throw "E2E en echec (code $taskExit). Les donnees de test sont conservees." }
}
Get-Content -LiteralPath (Join-Path $projectRoot '.env') | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
if ($env:POSTGRES_HOST -eq 'localhost') { $env:POSTGRES_HOST = '127.0.0.1' }
$runId = (Get-Date -Format 'yyyyMMddHHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,8)
$env:QAVELYS_E2E = '1'
$env:QAVELYS_E2E_RUN_ID = $runId
$env:POSTGRES_DB = 'qavelys_e2e_' + $runId
$env:QAVELYS_E2E_FRONTEND_PORT = "$FrontendPort"
$env:QAVELYS_E2E_BACKEND_PORT = "$BackendPort"
$env:DJANGO_SECRET_KEY = (& (Join-Path $projectRoot '.venv/Scripts/python.exe') -c 'import secrets; print(secrets.token_urlsafe(50))')
$env:DJANGO_DEBUG = '1'
$env:REQUIRE_EMAIL_VERIFICATION = '0'
$env:DJANGO_ALLOWED_HOSTS = 'localhost,127.0.0.1'
$env:FRONTEND_URL = "http://127.0.0.1:$FrontendPort"
$env:EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
$env:EMAIL_FILE_PATH = Join-Path $projectRoot ".local/e2e-runs/$runId/emails"
$env:MEDIA_ROOT = Join-Path $projectRoot ".local/e2e-runs/$runId/media"
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
Push-Location $projectRoot
try {
    Invoke-E2ENative { & $python infrastructure/prepare_e2e.py }
    Invoke-E2ENative { & $python backend/manage.py migrate --noinput }
    Push-Location (Join-Path $projectRoot 'frontend')
    try { Invoke-E2ENative { & npm.cmd run test:e2e } } finally { Pop-Location }
    Write-Output "E2E termine. Rapport : .local/e2e-runs/$runId/report/index.html"
} finally { Pop-Location }
