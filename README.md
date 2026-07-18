# Org_system

Org_system is an organizational experience layer for AI tools. It captures a completed tool trace as an **experience candidate**, verifies the claim, stores it with visibility and provenance, and lets a teammate's AI recall only verified, visible experiences with an attribution receipt.

This repository implements the vertical slice described in [the system design report](docs/SYSTEM_DESIGN_AND_BUILD_REPORT.md):

```text
MCP / tool adapter → automatic capture → verifier → MemoryStore → receipt-backed recall → dashboards
```

The local implementation uses SQLite as a swappable, SYNAPSE-compatible memory backend: each experience is an episodic record, tags act as semantic nodes, and retrieval uses lexical matching plus a small graph-activation bonus. It is intentionally behind `ExperienceStore`, so a native SYNAPSE or graph/vector backend can replace it later.

## What works now

- `POST /mcp`: JSON-RPC MCP surface with `recall_experience` and `store_experience`.
- `POST /api/gateway/events`: capture boundary for a proxy or adapter to log a completed tool call.
- `POST /api/capture`: creates a consent-scoped, non-serveable candidate.
- `POST /api/experiences/{id}/verify`: pluggable `outcome_signal`, `tests_ci`, `llm_judge`, and tolerance-based `rerun_and_compare` verification.
- `POST /api/recall`: filters to verified and visible experience, returns provenance/verification receipts, and records attributed reuse.
- User, team-discovery, and admin-health dashboards in the zero-build frontend.
- A first simulation workflow based on the Postia/iDynoMiCS design asset; the on-screen rerun uses a clearly labelled local metrics fixture, not a real simulator execution.

## Run locally

Requirements: Python 3.11+.

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Then open `http://127.0.0.1:8000` for the dashboard. Alternatively, serve the standalone [frontend/index.html](frontend/index.html):

```bash
cd frontend
python -m http.server 3000
```

API documentation is available at `http://127.0.0.1:8000/docs`.

The first launch creates `backend/data/org_system.sqlite3` and seeds three explicitly labelled local fixtures. Use **Reset demo** to restore them. That database is intentionally ignored by Git.

## Verify the core loop

```bash
cd backend
python -m unittest discover -s tests -v
```

The test proves that a candidate cannot be recalled until it passes verification, then confirms that a teammate can retrieve it with a receipt. For the scripted demo, follow [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## MCP test request

```bash
curl -X POST http://127.0.0.1:8000/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Hackathon evidence: Codex and timeframe

The official rules require a project made with **Codex using GPT-5.6**, a public <3-minute YouTube demo that explains how both were used, a working repository, and the `/feedback` Session ID from the project thread where most core functionality was built. They also require new projects to be created during the Submission Period, or existing projects to be meaningfully extended during it with clear evidence distinguishing old and new work.

This repository's baseline `Hive.skill` prototype was replaced by the Org_system implementation in this working tree. Before submitting, follow [docs/HACKATHON_EVIDENCE.md](docs/HACKATHON_EVIDENCE.md): make a dated commit of this implementation during the July 13–21, 2026 PT Submission Period; obtain the actual `/feedback` Session ID from the GPT-5.6 Codex thread; and replace its placeholders with honest, timestamped evidence. Do not invent a session ID or claim a model version that the session metadata does not confirm.

The required Codex collaboration narrative and the project-specific engineering decisions are in [docs/SUBMISSION_SUMMARY.md](docs/SUBMISSION_SUMMARY.md). The recommended category is **Work & Productivity**.

## Project map

- [backend/app/main.py](backend/app/main.py) — FastAPI layer and API routes.
- [backend/app/experience_store.py](backend/app/experience_store.py) — `MemoryStore` implementation, access filtering, activation-lite recall, and dashboard queries.
- [backend/app/verifiers.py](backend/app/verifiers.py) — verification lifecycle rules.
- [backend/app/mcp_server.py](backend/app/mcp_server.py) — MCP tool surface.
- [frontend/index.html](frontend/index.html) — interactive capture → verify → serve demo and dashboards.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — implementation architecture.
- [docs/COMMANDS.md](docs/COMMANDS.md) — API examples.
