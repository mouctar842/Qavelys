param([Parameter(ValueFromRemainingArguments=$true)][string[]]$DjangoArgs)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$envFile = Join-Path $projectRoot '.env'
if (!(Test-Path -LiteralPath $envFile)) { throw 'Créer .env à partir de .env.example et renseigner les secrets.' }
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([A-Z][A-Z0-9_]*)=(.*)$') { [Environment]::SetEnvironmentVariable($matches[1], $matches[2], 'Process') }
}
Push-Location (Join-Path $projectRoot 'backend')
try {
    # Un log HTTP sur stderr devient un ErrorRecord avec redirection sous PowerShell.
    # Seul le code de sortie de Python doit déterminer l’échec de la commande.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & (Join-Path $projectRoot '.venv/Scripts/python.exe') manage.py @DjangoArgs
        $backendExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    exit $backendExit
} finally { Pop-Location }
