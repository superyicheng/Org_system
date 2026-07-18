$projectRoot = Split-Path -Parent $PSScriptRoot
$pidFile = Join-Path $projectRoot "backend\.hive-backend.pid"

if (-not (Test-Path -LiteralPath $pidFile)) {
    Write-Host "Hive.skill backend is not running."
    exit 0
}

$backendPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue
if ($backendPid -match '^\d+$') {
    Stop-Process -Id ([int]$backendPid) -ErrorAction SilentlyContinue
}
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Write-Host "Hive.skill backend stopped."

