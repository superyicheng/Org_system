$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

$health = Invoke-RestMethod -Uri "$base/health"
if ($health.status -ne "ok") { throw "Health check failed" }

$newcomer = Invoke-RestMethod -Method Post -Uri "$base/api/assist" -ContentType "application/json" -Body (@{
    role = "newcomer"
    title = "Tom"
    message = "I want to embed 30 days of Kubernetes logs for semantic incident search. Should I launch the full GPU job?"
} | ConvertTo-Json)
if (-not $newcomer.hit) { throw "Pre-flight recall did not match verified team experience" }
if ($newcomer.avoided.gpu_hours -ne 148) { throw "Avoided GPU-hour evidence was incorrect" }

$replay = Invoke-RestMethod -Method Post -Uri "$base/api/experiences/exp-verified-log-embedding/replay"
if (-not $replay.serveable) { throw "Independent evidence replay failed" }

Write-Host "org.system smoke test passed: verified experience intercepted duplicate work and replayed its evidence." -ForegroundColor Green
