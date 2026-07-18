$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

$health = Invoke-RestMethod -Uri "$base/health"
$stats = Invoke-RestMethod -Uri "$base/hive/stats"
$retrieve = Invoke-RestMethod -Method Post -Uri "$base/retrieve" -ContentType "application/json" `
    -Body '{"error":"PostgreSQL FATAL: no pg_hba.conf entry; connection timed out"}'
$preflight = Invoke-RestMethod -Method Post -Uri "$base/preflight" -ContentType "application/json" `
    -Body '{"plan":"Vectorize 8 TB of production Kubernetes logs from 30 days using 8 GPUs"}'

if ($health.status -ne "ok") { throw "Health check failed" }
if (-not $retrieve.hit) { throw "Retrieve flow did not hit a skill" }
if (-not $preflight.hit) { throw "Preflight flow did not hit failed knowledge" }

Write-Host "PASS health" -ForegroundColor Green
Write-Host "PASS stats: $($stats.skill_count) skills"
Write-Host "PASS retrieve: $($retrieve.skill_name) / $([math]::Round($retrieve.similarity * 100))%"
Write-Host "PASS preflight: $($preflight.skill_name) / $([math]::Round($preflight.similarity * 100))%"

