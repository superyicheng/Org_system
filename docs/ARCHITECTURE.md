# Org_system implementation architecture

```text
Employee Codex / browser
          │
          ├── Google ID token → signed browser session
          ├── personal bearer token → POST /mcp/ (Streamable HTTP)
          └── POST /api/gateway/events (captured trace)
                           │
                           ▼
                 ExperienceStore.create_candidate()
                           │ candidate: never served
                           ▼
                 verifier (outcome / test / rerun)
                           │ verified, stale, or rejected
                           ▼
 PostgreSQL (cloud) / SQLite (local) episodic records + tag semantic nodes + usage events
                           │
                           ▼
           visibility-filtered activation-lite recall
                           │
                           ▼
     teammate's AI gets a provenance + verification receipt
```

`ExperienceStore` is the `MemoryStore` seam. The same SQLAlchemy implementation uses PostgreSQL for the shared hosted service and SQLite for a zero-account local demo. Its retrieval is deliberately modest: token overlap finds entry nodes, tag overlap adds a semantic activation bonus, then the store returns only consented, `verified` experiences. The public API does not pretend this is native SYNAPSE; a native graph/vector engine can replace this file without changing the routes.

Cloud access is deliberately centralized: Google identity authorizes the browser, `ORG_SYSTEM_ADMIN_EMAILS` grants the boss admin capability, and each employee gets a separate revocable bearer token for Codex. The MCP transport validates that token for every request and resolves it to the same employee identity used by the API. The database stores only the token's hash.

Lifecycle state is explicit:

```text
candidate --verify(pass)--> verified --reverify(diverge/env break)--> stale
candidate --verify(fail)--> candidate with REJECTED verdict
```

The dashboard queries are derived from the same storage: contribution comes from `experiences`; attribution comes from `usage_events`; health and rot come from lifecycle fields and `capture_events`.
