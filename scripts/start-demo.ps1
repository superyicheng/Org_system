param([switch]$OpenBrowser)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$pidFile = Join-Path $backendDir ".org-system-backend.pid"

if (Test-Path $pidFile) {
    $existing = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "Org_system API is already running at http://127.0.0.1:8000" -ForegroundColor Yellow
        exit 0
    }
    Remove-Item $pidFile -Force
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction Stop).Source }

Push-Location $backendDir
try {
    & $python -c "import fastapi, uvicorn" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Install dependencies first: $python -m pip install -r requirements.txt"
    }
    $process = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -PassThru
    $process.Id | Set-Content $pidFile
} finally {
    Pop-Location
}

Write-Host "Org_system API started at http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Open http://127.0.0.1:8000 for the dashboard." -ForegroundColor Cyan
if ($OpenBrowser) { Start-Process "http://127.0.0.1:8000/docs" }
