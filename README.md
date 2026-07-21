# org.system

org.system is a verified organizational memory layer for AI work. It captures completed work—including expensive failures—distills it into a reusable experience, verifies the evidence, and intercepts a teammate's similar proposal before the team spends the same resources twice.

The winning demo story is concrete: Sarah records that embedding 8 TB of Kubernetes logs consumed 148 GPU-hours for only a 3% quality gain. Later, Tom proposes the same full-scale job. org.system retrieves Sarah's verified negative result, generates an evidence-grounded answer, and recommends a 5% measured pilot before any expensive execution begins. Mei remains available as a third teammate to demonstrate that the memory is shared across the group.

## What is real

- Natural-language input from Tom, Sarah, and Mei; there are no scenario buttons.
- Automatic trace distillation through a switchable LLM client.
- Verified-only, consent-aware, visibility-aware hybrid retrieval (lexical + local semantic vectors).
- JSON Schema validation and a SHA-256 content receipt for every stored asset.
- Failed experiments can be VERIFIED negative results when their evidence is confirmed.
- Fail-closed metric verification: a missing metric cannot silently pass.
- Independent evidence replay in a separate Python process.
- Attributed reuse receipts and an avoided-resource impact signal.
- A project-scoped Codex MCP configuration plus `AGENTS.md` pre-flight/capture rules.
- A task-boundary gateway that automatically distills completed, consented traces.
- Provider-backed AI judging with an explicit deterministic fallback receipt.
- User attribution, team discovery, trust-center, and measured-impact views.
- Eleven automated tests covering the full lifecycle, semantic recall, local demo flow, cloud permissions, replay, and MCP.

## Shared cloud system (Google Cloud)

For real employee use, deploy the FastAPI service to **Cloud Run** and use **Cloud SQL for PostgreSQL** as the shared store. Google Identity signs employees into the web app; the boss allowlists employee addresses in Trust center, and each employee downloads a personal, revocable bearer-token setup for Codex or another Streamable HTTP MCP client. Their laptops do not run a database or expose any service.

Start with [Google Cloud production deployment](docs/GOOGLE_CLOUD_DEPLOYMENT.md). It identifies the one Google Cloud project, OAuth web client, Cloud SQL instance, secrets, and Cloud Run service to create. Then use [Codex employee setup](docs/CODEX_EMPLOYEE_SETUP.md) on every laptop.

## Demo-safe boundary

- With `OPENAI_API_KEY`, language distillation and answer generation use the OpenAI Responses API.
- Without a key, the app uses deterministic English copy. Retrieval, storage, verification, replay, and usage tracking remain real.
- The bundled replay worker is a real executable cost/quality workflow for the hackathon story. It is not an iDynoMiCS binary or a production GPU scheduler.
- No Docker sandbox and no arbitrary browser-supplied command execution are used.

## Fastest start: two terminal commands

Requirements: Python 3.11 or newer.

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). API documentation is at [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).

You can also double-click `START_DEMO.cmd`. Double-click `STOP_DEMO.cmd` when finished. `org.system-demo.html` opens the running demo directly.

## Offline/mock mode

Mock mode is automatic when no API key is present. To make it explicit:

```powershell
$env:ORG_SYSTEM_LLM_MODE="mock"
python -m uvicorn app.main:app --reload --port 8000
```

This is the recommended on-stage configuration because the full product loop still runs without network risk.

## Live AI mode

Set the key only in the terminal session; never paste it into the HTML or commit it.

```powershell
$env:OPENAI_API_KEY="YOUR_KEY"
$env:ORG_SYSTEM_LLM_MODE="openai"
$env:OPENAI_MODEL="gpt-5.6-luna"
python -m uvicorn app.main:app --reload --port 8000
```

The header badge shows `AI · openai` when live mode is active. If the provider times out, the same request automatically falls back to deterministic copy without breaking the demo.

## The 2-minute live path

1. Select **Sarah** and type:

   `We embedded 8 TB of Kubernetes logs for semantic incident search. The completed run consumed 148 GPU-hours but improved accuracy by only 3%. The better path is to sample 5%, cluster recurring log fingerprints, and set a go/no-go quality gate before scaling.`

2. Watch org.system type its answer and store a verified negative result.
3. Switch to **Tom** and type:

   `I want to embed 30 days of Kubernetes logs for semantic incident search. Can I launch the full 8 TB GPU job?`

4. Watch the verified receipt appear and the avoided impact change to **148 GPUh**.
5. Click **Replay evidence in isolated process**. The backend launches the bundled worker, extracts all metrics, and checks them against the stored receipt.

The full narration is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## Connect org.system to Codex through MCP

The website does not require MCP. In the shared Cloud Run system, it is how the same organizational memory reaches Codex on each employee laptop.

For the cloud system, use **Connect Codex** in the signed-in web app. It displays a one-time personal token and the exact remote MCP configuration. Follow [Codex employee setup](docs/CODEX_EMPLOYEE_SETUP.md); do not commit a token. The checked-in `.codex/config.toml` is deliberately disabled template text only.

For the local award demo only, `AGENTS.md` and `backend/mcp_stdio.py` remain available as a stdio MCP fallback:

From a terminal where `codex` and Python are available:

```powershell
codex mcp add org-system -- python C:\Users\BitAltas\Documents\GitHub\Org_system\backend\mcp_stdio.py
codex mcp list
```

org.system exposes three tools:

- `recall_experience` — retrieve verified visible experience with receipts.
- `avoid_duplicate_work` — run a pre-flight check against a proposed task.
- `store_experience` — capture an unverified candidate for later verification.
- `record_completed_work` — capture and verify a consented, evidence-backed lesson at task completion.

If `python` resolves incorrectly on Windows, replace it in the command with the full path returned by `Get-Command python` or your installed Python executable.

## Verify everything

```powershell
cd C:\Users\BitAltas\Documents\GitHub\Org_system\backend
python -m unittest discover -s tests -v
```

With the server running:

```powershell
powershell -ExecutionPolicy Bypass -File ..\scripts\smoke-test.ps1
```

## API map

- `POST /api/distill` — transcript to candidate experience.
- `POST /api/assist` — conversational capture or pre-flight recall.
- `POST /api/capture` — explicit structured capture.
- `POST /api/experiences/{id}/verify` — pluggable evidence verification.
- `POST /api/experiences/{id}/replay` — safe independent workflow replay.
- `POST /api/experiences/{id}/verify/ai` — rubric-based AI judge with provider receipt.
- `POST /api/recall` — verified and permitted recall with attribution.
- `POST /api/gateway/events` — automatic connector capture boundary.
- `POST /mcp/` — authenticated Streamable HTTP MCP endpoint (cloud).
- `GET /api/dashboard/user/{title}`, `/team`, `/admin` — contribution, discovery, and health views.
- `GET /api/dashboard/impact` — measured reuse and avoided-resource accounting.

## Project map

- `frontend/index.html` — final English hackathon interface.
- `backend/app/main.py` — FastAPI routes and conversational orchestration.
- `backend/app/distiller.py` / `llm_client.py` — live AI plus deterministic fallback.
- `backend/app/experience_store.py` — schema-validated memory, permissions, receipts, and recall.
- `backend/app/auth.py` / `mcp_service.py` — Google identity, revocable Codex tokens, and remote MCP service.
- `backend/app/verifiers.py` / `runners.py` — fail-closed verification and real process replay.
- `backend/mcp_stdio.py` — Codex-compatible stdio MCP entrypoint.
- `backend/tests/` — local-demo and cloud-mode lifecycle/integration tests.
- `docs/BUILD_COMPLETION_REPORT.md` — design-outline completion record and honest boundaries.

The product name is `org.system`; the repository folder remains `Org_system` for compatibility with the existing workspace.
