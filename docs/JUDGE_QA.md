# Judge Q&A

## Is this just RAG?

No. RAG retrieves notes. Org_system captures an experience lifecycle: candidate, verification verdict, visibility/consent, stale state, provenance receipt, and a measured consumption event. Candidate and stale entries cannot be served as trustworthy context.

## Is the simulator real in the demo?

The product contract is real and the metric comparator is executable. The browser demo uses labelled local metrics fixtures because an iDynoMiCS runtime is not bundled. The adapter seam and full Postia asset schema are included so a real runner can replace the fixture without changing capture, verification, storage, or serving.

## What is the MCP implementation?

`POST /mcp` implements the two product tools through JSON-RPC: `recall_experience` and `store_experience`. `POST /api/gateway/events` is the proxy/adaptor capture boundary. Production deployment should mount the same handlers through the official streamable-HTTP MCP SDK transport.

## Why SQLite rather than SYNAPSE?

SYNAPSE code is not a dependency of this hackathon build. SQLite makes the demo reproducible and has a narrow `ExperienceStore` boundary. It uses episodic records, semantic tag nodes, and activation-lite scoring today; a released native engine can replace it later.
