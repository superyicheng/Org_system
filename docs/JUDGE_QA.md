# Judge Q&A

## Is this just RAG?

No. RAG retrieves notes. Org_system captures an experience lifecycle: candidate, verification verdict, visibility/consent, stale state, provenance receipt, and a measured consumption event. Candidate and stale entries cannot be served as trustworthy context.

## Is the simulator real in the demo?

The product contract is real and the metric comparator is executable. The browser demo uses labelled local metrics fixtures because an iDynoMiCS runtime is not bundled. The adapter seam and full Postia asset schema are included so a real runner can replace the fixture without changing capture, verification, storage, or serving.

## What is the MCP implementation?

The shared service exposes authenticated Streamable HTTP at `POST /mcp/` through the official MCP SDK. Each employee creates a personal revocable bearer token after Google sign-in; the token identifies the employee to `recall_experience`, `avoid_duplicate_work`, `store_experience`, and `record_completed_work`. The repository retains a stdio fallback only for the offline award demo. `POST /api/gateway/events` remains the capture boundary.

## Why PostgreSQL/SQLite rather than SYNAPSE?

SYNAPSE code is not a dependency of this hackathon build. The deployed path uses Cloud SQL PostgreSQL; SQLite keeps the local demo reproducible. Both use the same narrow `ExperienceStore` boundary, episodic records, semantic vectors, and activation-lite scoring today; a released native engine can replace it later.
