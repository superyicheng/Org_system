# Org_system commands

Start the API from `backend/`:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Check the service:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/dashboard/admin
```

Capture an experience candidate:

```bash
curl -X POST http://127.0.0.1:8000/api/capture \
  -H 'Content-Type: application/json' \
  -d '{"actor":"Sarah","task":"Run a validated simulation","trace_summary":"The run completed and emitted metrics.","tool_name":"simulation adapter","tags":["simulation"],"visibility":"team","consent":true}'
```

Verify the returned experience ID with an objective outcome:

```bash
curl -X POST http://127.0.0.1:8000/api/experiences/EXP_ID/verify \
  -H 'Content-Type: application/json' \
  -d '{"method":"outcome_signal","outcome_succeeded":true}'
```

Recall for a teammate. This call creates an attributed usage event by default:

```bash
curl -X POST http://127.0.0.1:8000/api/recall \
  -H 'Content-Type: application/json' \
  -d '{"query":"Postia spatial growth iDynoMiCS","consumer":"Tom","limit":3}'
```

Exercise the MCP tools:

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"recall_experience","arguments":{"query":"Postia spatial growth","consumer":"Tom"}}}'
```
