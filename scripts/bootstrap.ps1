# One-command bootstrap: .env -> docker engine -> compose up -> wait for health
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less scripts as ANSI.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 [-NoBuild]
param(
    [switch]$NoBuild
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host '[OK] .env created from .env.example'
    Write-Host '[!!] Replace SECRET_KEY and credentials before any public deployment' -ForegroundColor Yellow
}

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host '[..] Docker engine not ready, starting Docker Desktop'
    & (Join-Path $PSScriptRoot 'start-docker.ps1')
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker engine is not available'
    }
}

$composeArgs = @('compose', 'up', '-d')
if (-not $NoBuild) {
    $composeArgs += '--build'
}
Write-Host "[..] docker $($composeArgs -join ' ')"
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw 'docker compose up failed'
}

Write-Host '[..] waiting for backend /health (up to 180s)'
$healthy = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 3
    $code = curl.exe -s -o NUL -w "%{http_code}" http://localhost:8000/health 2>$null
    if ($code -eq '200') {
        $healthy = $true
        break
    }
}

if (-not $healthy) {
    Write-Host '[!!] backend not healthy yet, check: docker compose logs backend' -ForegroundColor Yellow
    docker compose ps
    exit 1
}

Write-Host '[OK] backend healthy'
docker compose ps

Write-Host ''
Write-Host 'Frontend : http://localhost:8080'
Write-Host 'API docs : http://localhost:8000/docs'
Write-Host 'Health   : http://localhost:8000/health'
Write-Host 'Login    : admin / 123456 (SEED_DEFAULT_DATA=true)'
exit 0
