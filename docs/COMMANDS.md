# Org_system commands

## Local demo

Start the service from `backend/`:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Check the service:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/dashboard/admin
```

The local demo authenticates as Demo User. Capture a candidate:

```bash
curl -X POST http://127.0.0.1:8000/api/capture \
  -H 'Content-Type: application/json' \
  -d '{"actor":"ignored in demo","task":"Run a validated simulation","trace_summary":"The run completed and emitted metrics.","tool_name":"simulation adapter","tags":["simulation"],"visibility":"team","consent":true}'
```

Verify the returned ID, then recall it:

```bash
curl -X POST http://127.0.0.1:8000/api/experiences/EXP_ID/verify \
  -H 'Content-Type: application/json' \
  -d '{"method":"outcome_signal","outcome_succeeded":true}'

curl -X POST http://127.0.0.1:8000/api/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"Postia spatial growth iDynoMiCS","consumer":"ignored in demo","limit":3}'
```

Exercise the Streamable HTTP MCP endpoint with the local-only `demo` token:

```bash
curl -X POST http://127.0.0.1:8000/mcp/ \
  -H 'Authorization: Bearer demo' \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

## Shared cloud requests

Employees should use the browser to generate their personal MCP token, then configure Codex according to [Codex employee setup](CODEX_EMPLOYEE_SETUP.md). The API accepts the same bearer token for troubleshooting calls:

```bash
export ORG_SYSTEM_MCP_TOKEN='orgmcp_personal_token'
export ORG_SYSTEM_URL='https://your-service.example'

curl "$ORG_SYSTEM_URL/health"
curl -X POST "$ORG_SYSTEM_URL/mcp/" \
  -H "Authorization: Bearer $ORG_SYSTEM_MCP_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'
```

Google browser sessions are obtained only through the hosted page; do not try to fabricate them in shell scripts.
