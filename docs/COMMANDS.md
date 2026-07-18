# Commands

## One-click Windows launch

```text
START_DEMO.cmd
```

Stop the background API:

```text
STOP_DEMO.cmd
```

## Manual setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

## Health and stats

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/hive/stats
```

## Retrieve a proven fix

```powershell
$body = @{ error = "PostgreSQL FATAL: no pg_hba.conf entry; connection timed out" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/retrieve -ContentType application/json -Body $body
```

## Guard an expensive plan

```powershell
$body = @{ plan = "Vectorize 8 TB of production Kubernetes logs from 30 days using 8 GPUs" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/preflight -ContentType application/json -Body $body
```

## Distill a veteran resolution

```powershell
$body = @{ transcript = "Solved PostgreSQL access using corporate VPN, internal CA, and sslmode verify-full." } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/distill -ContentType application/json -Body $body
```

## Run all smoke checks

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-test.ps1
```

