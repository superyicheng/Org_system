# Hive.skill

Hive.skill turns proven fixes and failed experiments into executable team memory. It retrieves that memory when a new engineer encounters the same error—or before an expensive plan consumes resources.

## Fastest start on Windows

1. Double-click `START_DEMO.cmd`.
2. Wait for the browser to open.
3. Use the prompts in `demo-prompts.txt`.
4. Double-click `STOP_DEMO.cmd` after the presentation.

The first launch creates `backend/.venv` and installs local dependencies. If installation or the LLM fails, the demo still runs with an explicit mock label.

## Manual backend start

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Open `Hive.skill-demo.html` in Edge or Chrome. API documentation is at <http://127.0.0.1:8000/docs>.

## Optional live LLM

Copy `backend/.env.example` to `backend/.env` and set:

```env
HIVE_LLM_API_KEY=your_api_key
HIVE_LLM_MODEL=gpt-5.6-luna
```

No key is required for the complete offline demo.

## What is real and what is simulated

Real:

- deterministic fingerprint extraction;
- ChromaDB vector storage and similarity retrieval;
- `/retrieve`, `/distill`, `/preflight`, and `/hive/stats` APIs;
- optional LLM reasoning and script adaptation;
- executable Bash scripts shown in the editor.

Simulated for the two-day hackathon:

- terminal execution animation;
- Kubernetes/GPU resource creation and blocking;
- the final savings animation.

## API summary

- `POST /distill` — persists a solved incident as a reusable skill.
- `POST /retrieve` — retrieves a successful fix and adapts its script.
- `POST /preflight` — retrieves failed experiments before execution.
- `GET /hive/stats` — returns team-memory impact statistics.
- `GET /health` — launcher health check.

## Validation

With the backend running:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-test.ps1
```

See `docs/` for the pitch, judge Q&A, architecture, and presentation checklist.

