# Judge Q&A

## Is this just RAG?

No. RAG retrieves notes. Org_system captures an experience lifecycle: candidate, verification verdict, visibility/consent, stale state, provenance receipt, and a measured consumption event. Candidate and stale entries cannot be served as trustworthy context.

## Is the simulator real in the demo?

The product contract is real and the metric comparator is executable. The browser demo uses labelled local metrics fixtures because an iDynoMiCS runtime is not bundled. The adapter seam and full Postia asset schema are included so a real runner can replace the fixture without changing capture, verification, storage, or serving.

## What is the MCP implementation?

`POST /mcp/` implements the two product tools through the official Python MCP SDK's Streamable HTTP transport: `recall_experience` and `store_experience`. It requires a per-employee bearer token and resolves the token to the employee identity before every call. `POST /api/gateway/events` is the proxy/adaptor capture boundary.

## Why PostgreSQL/SQLite rather than SYNAPSE?

SYNAPSE code is not a dependency of this hackathon build. The shared deployment uses PostgreSQL; SQLite makes the no-account local demo reproducible. Both use the same narrow `ExperienceStore` boundary with episodic records, semantic tag nodes, and activation-lite scoring. A released native engine can replace that layer later.
