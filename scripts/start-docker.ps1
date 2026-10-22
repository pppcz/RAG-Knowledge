# Start Docker Desktop and wait until the engine is ready.
# ASCII-only on purpose: PowerShell 5.1 reads BOM-less scripts as ANSI.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\start-docker.ps1
param(
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'

function Test-DockerEngine {
    docker info *> $null
    return ($LASTEXITCODE -eq 0)
}

function Wait-DockerEngine {
    param([int]$Seconds)

    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerEngine) { return $true }
        Start-Sleep -Seconds 3
        Write-Host '.' -NoNewline
    }
    Write-Host ''
    return $false
}

if (Test-DockerEngine) {
    Write-Host '[OK] Docker engine is ready'
    docker info --format 'Server {{.ServerVersion}} / {{.OSType}} / {{.Architecture}}'
    exit 0
}

Write-Host '[..] Docker engine not ready, trying to start Docker Desktop'
$desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
if (Test-Path $desktop) {
    Start-Process -FilePath $desktop | Out-Null
} else {
    Write-Warning "Not found: $desktop - please start Docker Desktop manually"
}

Write-Host "[..] Waiting for docker info (up to $TimeoutSeconds seconds)"
if (Wait-DockerEngine -Seconds $TimeoutSeconds) {
    Write-Host '[OK] Docker engine is ready'
    exit 0
}

Write-Warning '[..] Still failing, trying to repair WSL'
wsl --update
wsl --shutdown

Write-Warning 'Please start Docker Desktop manually, then rerun this script'
if (Wait-DockerEngine -Seconds $TimeoutSeconds) {
    Write-Host '[OK] Docker engine is ready'
    exit 0
}

Write-Error @'
[DOCKER FAILED] Cannot reach the Docker engine. Triage steps:
  1) Open Docker Desktop and make sure the engine is running
  2) wsl -l -v : docker-desktop distro exists and is Running
  3) Settings -> General -> enable "Use the WSL 2 based engine"
  4) Settings -> Resources -> WSL Integration : enable your distro
  5) Restart Docker Desktop and retry
'@
exit 1
