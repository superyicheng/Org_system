param([switch]$OpenBrowser)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$pidFile = Join-Path $backendDir ".org-system-backend.pid"

if (Test-Path $pidFile) {
    $existing = Get-Process -Id (Get-Content $pidFile) -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "org.system is already running at http://127.0.0.1:8000" -ForegroundColor Yellow
        exit 0
    }
    Remove-Item $pidFile -Force
}

$pythonCandidates = @()
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) { $pythonCandidates += $pythonCommand.Source }
$pyCommand = Get-Command py -ErrorAction SilentlyContinue
if ($pyCommand) { $pythonCandidates += $pyCommand.Source }
$localPythonRoot = Join-Path $env:LOCALAPPDATA "Python"
if (Test-Path $localPythonRoot) {
    $pythonCandidates += Get-ChildItem $localPythonRoot -Recurse -Filter python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
}
$python = $null
foreach ($candidate in $pythonCandidates | Select-Object -Unique) {
    & $candidate -c "import fastapi, uvicorn, jsonschema" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}
if (-not $python) { throw "Python dependencies are missing. Run the setup commands in README.md first." }

Push-Location $backendDir
try {
    $process = Start-Process -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" -WindowStyle Hidden -PassThru
    $process.Id | Set-Content $pidFile
} finally {
    Pop-Location
}

Write-Host "org.system started at http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Open http://127.0.0.1:8000 for the live demo." -ForegroundColor Cyan
if ($OpenBrowser) { Start-Process "http://127.0.0.1:8000" }
