$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $projectRoot "backend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$pidFile = Join-Path $backendDir ".hive-backend.pid"
$demoFile = Join-Path $projectRoot "Hive.skill-demo.html"

Write-Host "Hive.skill demo launcher" -ForegroundColor Yellow

if (-not (Test-Path -LiteralPath $venvPython)) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { $pythonCommand = Get-Command py -ErrorAction SilentlyContinue }
    if (-not $pythonCommand) { throw "Python 3.11+ was not found." }
    Write-Host "Creating the local Python environment..."
    & $pythonCommand.Source -m venv $venvDir
    if ($LASTEXITCODE -ne 0) { throw "Python could not create the virtual environment." }
}

& $venvPython -c "import fastapi, chromadb, pydantic_settings" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing backend dependencies (first run only)..."
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $backendDir "requirements.txt")
}

if ($LASTEXITCODE -ne 0) {
    Write-Warning "Backend installation failed. Opening the clearly labeled offline demo instead."
    Start-Process -FilePath $demoFile
    Read-Host "Press Enter to close"
    exit 0
}

$existingPid = $null
if (Test-Path -LiteralPath $pidFile) {
    $existingPid = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue
}
if ($existingPid -match '^\d+$' -and (Get-Process -Id ([int]$existingPid) -ErrorAction SilentlyContinue)) {
    Write-Host "Backend already running (PID $existingPid)."
} else {
    $backendProcess = Start-Process -FilePath $venvPython `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $backendDir -PassThru
    Set-Content -LiteralPath $pidFile -Value $backendProcess.Id -Encoding ascii
    Write-Host "Starting FastAPI and ChromaDB in a visible console..."
}

$healthy = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1
        if ($health.status -eq "ok") { $healthy = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 500
}

if ($healthy) { Write-Host "Backend ready: http://127.0.0.1:8000/docs" -ForegroundColor Green }
else { Write-Warning "Health check timed out; the HTML will use its explicit fallback." }

Start-Process -FilePath $demoFile
Write-Host "Demo opened. Run STOP_DEMO.cmd after the presentation."
Read-Host "Press Enter to close this launcher window"

