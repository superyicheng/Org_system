$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot "backend\.org-system-backend.pid"

if (-not (Test-Path $pidFile)) {
    Write-Host "org.system backend is not running."
    exit 0
}

$process = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
if ($process) { Stop-Process -Id $process.Id -Force }
Remove-Item $pidFile -Force
Write-Host "org.system backend stopped."
