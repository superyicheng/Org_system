# Org_system implementation architecture

```text
MCP client / tool adapter
          │
          ├── POST /mcp (recall_experience, store_experience)
          └── POST /api/gateway/events (captured trace)
                           │
                           ▼
                 ExperienceStore.create_candidate()
                           │ candidate: never served
                           ▼
                 verifier (outcome / test / rerun)
                           │ verified, stale, or rejected
                           ▼
 SQLite episodic records + tag semantic nodes + usage events
                           │
                           ▼
           visibility-filtered activation-lite recall
                           │
                           ▼
     teammate's AI gets a provenance + verification receipt
```

`ExperienceStore` is the `MemoryStore` seam. SQLite keeps the hackathon project runnable with no cloud account. Its retrieval is deliberately modest: token overlap finds entry nodes, tag overlap adds a semantic activation bonus, then the store returns only consented, `verified` experiences. The public API does not pretend this is native SYNAPSE; a native graph/vector engine can replace this file without changing the routes.

Lifecycle state is explicit:

```text
candidate --verify(pass)--> verified --reverify(diverge/env break)--> stale
candidate --verify(fail)--> candidate with REJECTED verdict
```

The dashboard queries are derived from the same storage: contribution comes from `experiences`; attribution comes from `usage_events`; health and rot come from lifecycle fields and `capture_events`.
