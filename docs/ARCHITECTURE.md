# Architecture

```text
Veteran resolution
    ↓ POST /distill
Fingerprint + assumptions + executable fix
    ↓
Local ChromaDB collection

New-hire error
    ↓ POST /retrieve
Noise reduction → vector search → LLM validation/adaptation
    ↓
Executable fix script

New-hire execution plan
    ↓ POST /preflight
Plan fingerprint → failed-run vector search → LLM applicability check
    ↓
Evidence comparison + safer capped script
```

## Components

- `Hive.skill-demo.html`: zero-build stage UI with explicit API/mock labels.
- `backend/app/main.py`: FastAPI routes and orchestration.
- `backend/app/vector_store.py`: ChromaDB persistence, fingerprints, retrieval.
- `backend/app/llm_client.py`: switchable Responses API client with mock fallback.
- `backend/app/seed_data.py`: four idempotent seed skills, including one failed experiment.
- `scripts/`: launcher, stop control, and smoke test.

## Demo safety boundaries

- No real production credentials are stored.
- Scripts use environment-variable placeholders.
- No Docker sandbox or real GPU workload is launched.
- LLM failure never breaks the presentation path.

