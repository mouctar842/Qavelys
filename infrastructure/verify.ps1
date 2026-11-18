param([ValidateSet('all', 'backend', 'frontend', 'build')][string]$Scope = 'all')
$ErrorActionPreference = 'Stop'

function Invoke-CheckedNative {
    param([scriptblock]$Command, [string]$FailureMessage)
    # Windows PowerShell transforme stderr en ErrorRecord lors d'une redirection.
    # Les avertissements npm ne sont pas des echecs : verifier le code de sortie.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $Command
        $taskExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    if ($taskExitCode -ne 0) { throw "$FailureMessage (code $taskExitCode)" }
}
$projectRoot = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $projectRoot '.env'
if (!(Test-Path -LiteralPath $envFile)) { throw 'Créer .env avant les vérifications.' }
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if ($Scope -in @('all', 'backend')) {
    if (!(Test-Path -LiteralPath $pythonPath)) { throw 'Environnement Python absent.' }
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        Invoke-CheckedNative { & $pythonPath manage.py check } 'Controle Django en echec'
        Invoke-CheckedNative { & $pythonPath manage.py makemigrations --check --dry-run } 'Modeles et migrations divergents'
        Invoke-CheckedNative { & $pythonPath manage.py migrate --check } 'Migrations non appliquees'
        Invoke-CheckedNative { & $pythonPath -m pytest -q } 'Tests backend en echec'
    } finally { Pop-Location }
}
if ($Scope -in @('all', 'frontend', 'build')) {
    $null = Get-Command npm.cmd -ErrorAction Stop
    Push-Location (Join-Path $projectRoot 'frontend')
    try {
        if ($Scope -ne 'build') { Invoke-CheckedNative { & npm.cmd test } 'Tests frontend en echec' }
        Invoke-CheckedNative { & npm.cmd run build } 'Build frontend en echec'
    } finally { Pop-Location }
}
