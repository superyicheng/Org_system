# org.system implementation conformance report

This file compares the current repository against `SYSTEM_DESIGN_AND_BUILD_REPORT.md`. It distinguishes implemented behavior from hackathon substitutes; “working demo” does not mean every production component in the report exists.

## Strict comparison with the design text

| Milestone | What the text requires | What exists now | Strict status |
|---|---|---|---|
| M0 | FastAPI `/health` and an empty Next.js app | FastAPI `/health`; zero-build HTML instead of Next.js | Partial |
| M1 | Experience model, swappable `MemoryStore`, Cognee or SQLite+embedding, write/recall proof | JSON Schema validation, `MemoryStore` protocol, SQLite episodic records, deterministic semantic vectors, hybrid recall, SHA-256 receipts | Complete for the allowed SQLite+embedding path |
| M2 | MCP server plus a gateway that proxies and logs real client tool traffic | stdio MCP server, HTTP JSON-RPC tools, project `.codex/config.toml`, server instructions, gateway event log, verified handshake test | Mostly complete; a live Codex screenshot/tool-call receipt is still a submission-evidence task |
| M3 | Automatic session boundary detection and Claude distillation with near-zero effort | Gateway `task_completed` boundary automatically distills and stores a consented trace; `AGENTS.md` instructs Codex to capture completed work | Complete for the hackathon connector path; not a universal transparent proxy |
| M4 | `outcome_signal`, real `llm_judge`, verdict transitions, scheduled re-verification | Objective evidence, CI exit code, OpenAI/mock judge receipt, fail-closed replay, lifecycle transitions, background freshness worker | Complete for the defined verifier seam |
| M5 | Verified/visible serving with receipts and a second user's AI receiving context | Filtering, receipts, attribution, usage recording, MCP recall, end-to-end tests | Backend complete; real Codex context injection still needs live proof |
| M6 | Three pages: user, team discovery, admin health | User attribution, team knowledge map, trust center, and impact views are live in the single-page demo | Complete as three product views (single zero-build HTML shell) |
| M7 | Real iDynoMiCS adapter and true `rerun_and_compare` simulation reproduction | A safe bundled subprocess replays a deterministic cost/quality workflow | Partial; it proves the verifier contract but is not iDynoMiCS |

## What is genuinely working

1. Sarah can submit a completed trace and create a schema-valid verified experience.
2. Tom or Mei can retrieve only verified, consented, visible experience.
3. A verified negative result can stop a duplicate resource-heavy proposal.
4. Every result includes origin, verdict, activation score, and content hash.
5. Private experience is not exposed to another person.
6. Missing replay metrics fail closed.
7. The bundled verification worker really executes in a separate process.
8. MCP exposes recall, duplicate-work preflight, candidate capture, and completed-work capture tools.
9. The HTTP flow runs Sarah capture, Tom recall, and evidence replay end to end.
10. Paraphrased proposals activate the correct experience through semantic vectors.
11. The AI judge returns a score, rationale, rubric, and provider/fallback receipt.
12. Three governance views and measured impact are visible in the browser.

## Hackathon-safe substitutes

| Component | Real behavior | Substitute or gap |
|---|---|---|
| Storage | SQLite persistence, access filtering, receipts, hybrid semantic vector activation | Not Cognee or native SYNAPSE |
| Capture | Real gateway event log, task-boundary distillation, and persistence | Not a universal proxy for every third-party MCP transport |
| LLM | OpenAI Responses API when configured | Deterministic English fallback; design text specified Claude |
| Verification | Real state transitions, complete metric comparison, subprocess replay | Bounded local workflow, not iDynoMiCS |
| MCP | Working stdio tools, Codex project config, server instructions, and HTTP JSON-RPC handler | Live Codex call evidence must be recorded after restarting the trusted project |
| Presentation | Working org.system demo with Tom/Sarah/Mei and three governance views | Zero-build HTML, not Next.js |

## Next work required for literal compliance

1. Restart Codex in the trusted repository and record one real `avoid_duplicate_work` call for submission evidence.
2. If literal production compliance is required, replace the connector boundary with a universal transparent MCP proxy.
3. If literal M0 UI compliance is required, port the zero-build shell to Next.js without changing the API.
4. Implement the real iDynoMiCS `SimulationRunner` adapter when the simulator runtime and Postia assets are available.
