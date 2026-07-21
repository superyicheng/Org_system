# org.system command reference

## Start in offline-safe mode

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
python -m pip install -r requirements.txt
$env:ORG_SYSTEM_LLM_MODE="mock"
python -m uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`.

For the shared Cloud Run and Cloud SQL setup, follow [GOOGLE_CLOUD_DEPLOYMENT.md](GOOGLE_CLOUD_DEPLOYMENT.md) instead of exposing a local development server.

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

## Cloud MCP OAuth check

There is no token to paste. These three calls need no credentials and prove that an MCP
client can discover and authenticate to the service on its own. Run them against the exact
hosted URL.

```powershell
$service = "https://your-service.example"

# 1. An unauthenticated call must be challenged, and the challenge must name its metadata.
try {
  Invoke-WebRequest -Method Post -Uri "$service/mcp/" -ContentType application/json `
    -Headers @{ Accept = "application/json, text/event-stream" } `
    -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}'
} catch {
  $_.Exception.Response.StatusCode.value__          # expect 401
  $_.Exception.Response.Headers["WWW-Authenticate"] # contains resource_metadata="..."
}

# 2. The metadata document the challenge points at must actually resolve.
Invoke-RestMethod "$service/.well-known/oauth-protected-resource/mcp"

# 3. The authorization server must advertise PKCE and dynamic client registration.
Invoke-RestMethod "$service/.well-known/oauth-authorization-server"
```

Expect `401` with a `resource_metadata` pointer, then two `200` documents. If the URL in the
challenge does not resolve, discovery is broken and no client can connect, even though the
endpoint itself is up.

To actually call a tool, connect a real client and let it complete the OAuth flow:

```powershell
codex mcp add org_system --url https://your-service.example/mcp/
codex mcp login org_system
codex mcp list
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
