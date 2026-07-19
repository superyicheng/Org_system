# org.system command reference

## Start in offline-safe mode

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
python -m pip install -r requirements.txt
$env:ORG_SYSTEM_LLM_MODE="mock"
python -m uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

## Start with live OpenAI generation

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
$env:OPENAI_API_KEY="YOUR_KEY"
$env:ORG_SYSTEM_LLM_MODE="openai"
$env:OPENAI_MODEL="gpt-5.6-luna"
python -m uvicorn app.main:app --reload --port 8000
```

## Health and test suite

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
python -m unittest discover -s tests -v
powershell -ExecutionPolicy Bypass -File ..\scripts\smoke-test.ps1
```

## Tom pre-flight API

```powershell
$body = @{
  role = "newcomer"
  title = "Tom"
  message = "I want to embed 30 days of Kubernetes logs for semantic incident search. Can I launch the full 8 TB GPU job?"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/assist -ContentType application/json -Body $body
```

## Independent evidence replay

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/experiences/exp-verified-log-embedding/replay
```

## MCP HTTP check

```powershell
$body = @{
  jsonrpc = "2.0"
  id = 1
  method = "tools/call"
  params = @{
    name = "avoid_duplicate_work"
    arguments = @{
      proposal = "Embed Kubernetes logs for semantic search"
      consumer = "Tom"
    }
  }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/mcp -ContentType application/json -Body $body
```

## Codex stdio MCP registration

```powershell
codex mcp add org-system -- python C:\Users\BitAltas\Documents\GitHub\Org_system\backend\mcp_stdio.py
codex mcp list
```

## Reset and stop

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/demo/reset
```

In a foreground terminal, press `Ctrl+C`. If started using `START_DEMO.cmd`, double-click `STOP_DEMO.cmd`.
