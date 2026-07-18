$ErrorActionPreference = "Stop"
$base = "http://127.0.0.1:8000"

$health = Invoke-RestMethod -Uri "$base/health"
if ($health.status -ne "ok") { throw "Health check failed" }

$candidate = Invoke-RestMethod -Method Post -Uri "$base/api/capture" -ContentType "application/json" -Body (@{
    actor = "SmokeTest"; task = "Validate a captured simulation"; trace_summary = "The simulation completed.";
    tool_name = "smoke adapter"; tags = @("simulation", "smoke"); visibility = "team"; consent = $true
} | ConvertTo-Json)

$verification = Invoke-RestMethod -Method Post -Uri "$base/api/experiences/$($candidate.experience.id)/verify" -ContentType "application/json" -Body (@{
    method = "outcome_signal"; outcome_succeeded = $true
} | ConvertTo-Json)
if (-not $verification.serveable) { throw "Verified experience was not serveable" }

$recall = Invoke-RestMethod -Method Post -Uri "$base/api/recall" -ContentType "application/json" -Body (@{
    query = "captured simulation"; consumer = "Tom"; limit = 3
} | ConvertTo-Json)
if ($recall.receipts.Count -lt 1) { throw "Recall returned no receipt" }

Write-Host "Org_system smoke test passed." -ForegroundColor Green
