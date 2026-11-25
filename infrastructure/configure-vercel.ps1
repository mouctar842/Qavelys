param([Parameter(Mandatory=$true)][string]$BackendOrigin)
$ErrorActionPreference = 'Stop'
$origin = $null
if (![Uri]::TryCreate($BackendOrigin, [UriKind]::Absolute, [ref]$origin) -or
    $origin.Scheme -ne 'https' -or $origin.UserInfo -or $origin.Query -or
    $origin.Fragment -or $origin.AbsolutePath -ne '/' -or
    $origin.Host -in @('localhost', '127.0.0.1', 'backend.example.com')) {
    throw 'Fournir une origine HTTPS réelle, sans chemin, identifiants, paramètres ni fragment.'
}
$configPath = Join-Path (Split-Path $PSScriptRoot -Parent) 'frontend/vercel.json'
$config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
$config.rewrites[0].destination = $origin.GetLeftPart([UriPartial]::Authority) + '/api/:path*'
$json = $config | ConvertTo-Json -Depth 10
[IO.File]::WriteAllText($configPath, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Output 'Configuration Vercel prête. Aucun déploiement effectué.'
