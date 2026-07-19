# Org_system

Org_system is a shared organizational experience layer for AI tools. It captures completed work as a candidate, verifies the claim, stores consent and provenance, and lets a teammate's AI retrieve only verified experience with an attribution receipt.

```text
Codex / tool adapter → capture → verification gate → shared memory → receipt-backed recall
```

It is no longer just a localhost dashboard. The repository now includes a deployable shared-service path:

- HTTPS FastAPI web app and standard Streamable HTTP MCP endpoint at `/mcp/`.
- PostgreSQL for the shared cloud system; SQLite only for the zero-account local demo.
- Google sign-in for browser access, a Workspace-domain allowlist option, and admin emails for the boss role.
- A separate, hash-stored, revocable bearer token for every employee's Codex laptop.
- A hosted UI that creates the exact Codex configuration after an employee signs in.

## Deploy for the team

Start with [Cloud deployment](docs/CLOUD_DEPLOYMENT.md). It covers Google configuration, the included Docker/Render deployment files, the environment values to set, and the shared-service verification checklist. Then give every employee [Codex employee setup](docs/CODEX_EMPLOYEE_SETUP.md).

The employee's Codex configuration uses the official remote MCP pattern:

```toml
[mcp_servers.org_system]
url = "https://your-service.example/mcp/"
bearer_token_env_var = "ORG_SYSTEM_MCP_TOKEN"
```

The full configuration and token lifecycle are documented in the employee guide.

## What works

- `POST /mcp/`: bearer-authenticated Streamable HTTP MCP with `recall_experience` and `store_experience`.
- `POST /api/gateway/events`: consent-scoped capture boundary for a tool proxy or adapter.
- `POST /api/capture`: creates a non-serveable candidate.
- `POST /api/experiences/{id}/verify`: outcome, test, LLM-judge, and rerun comparison verification modes.
- `POST /api/recall`: returns only verified, visible experiences and records attributed reuse.
- Google browser sessions, per-laptop MCP tokens, revocation, and employee/admin authorization boundaries.
- User, team-discovery, and admin-health dashboards.

## Run the local demo

Requirements: Python 3.11+.

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open `http://127.0.0.1:8000`. Local mode is explicitly a demo: it uses a local SQLite file, automatically signs in as Demo User, and accepts the demo MCP token shown by the UI. It is not a multi-employee deployment.

## Test

```bash
cd backend
python -m unittest discover -s tests -v
```

See [Commands](docs/COMMANDS.md) for local and authenticated cloud requests, and [Operations runbook](docs/OPERATIONS_RUNBOOK.md) for access and incident handling.

## Hackathon evidence

The project is designed for the OpenAI Codex hackathon. The official rules require a project made with Codex using the required model, a public <3-minute demo video that explains both, a working repository, and the `/feedback` Session ID from the project thread where most core functionality was built. They also require new work during the submission period, or a meaningful, clearly evidenced extension of an existing project.

Use [Hackathon evidence](docs/HACKATHON_EVIDENCE.md) before submitting. Do not invent a Session ID or claim a model version that the session metadata does not confirm. The required collaboration narrative is in [Submission summary](docs/SUBMISSION_SUMMARY.md).

## Project map

- [backend/app/main.py](backend/app/main.py) — API, identity, roles, and browser routes.
- [backend/app/mcp_service.py](backend/app/mcp_service.py) — standard authenticated Streamable HTTP MCP tools.
- [backend/app/experience_store.py](backend/app/experience_store.py) — shared SQL store, visibility filtering, recall, and token records.
- [frontend/index.html](frontend/index.html) — browser UI, Google sign-in, and employee Codex setup.
- [Dockerfile](Dockerfile), [compose.yaml](compose.yaml), [render.yaml](render.yaml) — deployment assets.
