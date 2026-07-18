# Org_system — System Design & Build-From-Nothing Report

*A complete guide for someone with zero prior knowledge of this project. Read top to bottom. By the end you will understand **what** we are building, **why**, and **how to build it from an empty folder** — including which mature open-source pieces to use so you never build commodity plumbing yourself.*

Working name: **Org_system** (an *organizational experience layer for AI tools*). Version of this document: draft v0.2. Context: built for a hackathon; the simulation pieces from the author's other projects are used only as the **first test workflow**, not as core infrastructure.

---

## 1. The one-paragraph version

When people do real work through AI tools (coding agents, simulation runners, research assistants), they generate hard-won experience — what worked, what failed, the exact settings that made something run, the reason a dead end is a dead end. Today that experience dies inside individual chat sessions. **Org_system automatically captures that experience from the AI tools people already use, checks that it is actually correct, stores it in a brain-inspired memory (SYNAPSE), and serves it back as context to a *teammate's* AI tool — so your colleague's AI inherits your experience without anyone writing documentation.** It is infrastructure *for the team's AI workforce*, not a human-facing wiki.

---

## 2. The problem (why this needs to exist)

A concrete story. Sarah spends two weeks getting a simulation to converge. She learns that one specific setting is the difference between "the colony grows" and "nothing happens," and that a certain configuration is a dead end. Sarah graduates. Six months later, Tom's AI agent tries the exact dead end Sarah already ruled out, and re-derives the same setting from scratch over another two weeks. **The team paid for the same lesson twice**, because the lesson lived only in Sarah's head and her closed laptop sessions.

Every knowledge-management tool of the last 30 years (wikis, Confluence, Notion, SharePoint) tried to fix this by asking humans to *write down* what they know. They mostly failed, for reasons that are worth memorizing because our design is a direct response to each:

1. **Nobody wants to do the writing.** Depositing knowledge costs the writer and benefits everyone else. → *So we capture automatically from work; humans deposit nothing.*
2. **The valuable knowledge is the hardest to write down** ("we know more than we can tell"). → *So we capture the actual execution trace, not a person's summary of it.*
3. **Written knowledge rots** and a confidently-wrong stale note is worse than nothing. → *So every stored experience is periodically re-checked and marked stale when it fails.*
4. **You can't trust retrieved knowledge** without re-verifying it (which erases the time saved). → *So every experience carries a machine-checked verdict; retrieval hands you a receipt, not a rumor.*

The single idea that makes Org_system different from a "graveyard with a search bar" is a **verifier**: an automatic check for "is this experience actually correct and still true?" Domains that have a verifier (code has tests, simulation has reproducibility) can *distill* trustworthy experience. Domains that don't can only *retrieve* and stay shallow. **We start in a domain where verification is cheap (simulation), prove the loop, then generalize.**

---

## 3. The solution in one picture

Six things happen in a loop. Everything in this document is one of these six boxes.

```
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
   │ 1 CONNECT│──▶│ 2 CAPTURE│──▶│ 3 VERIFY │──▶│ 4 STORE  │──▶│ 5 SERVE  │
   │ to a tool│   │ activity │   │ is it    │   │ SYNAPSE  │   │ to a     │
   │ (general)│   │ automat- │   │ correct? │   │ memory   │   │ colleague│
   │          │   │ ically   │   │ (simple) │   │          │   │ 's AI    │
   └──────────┘   └──────────┘   └──────────┘   └──────────┘   └────┬─────┘
        ▲                                                            │
        │                    ┌───────────────────────┐              │
        └────────────────────│ 6 SEE & MANAGE (UI)   │◀─────────────┘
                             │ user + admin dashboards│
                             └───────────────────────┘
```

1. **Connect** — plug into the AI tools the team uses, through one general connection.
2. **Capture** — automatically turn their activity into a structured "Experience."
3. **Verify** — check the experience is correct (simple check now; stronger later).
4. **Store** — put it in SYNAPSE, the brain-inspired memory.
5. **Serve** — when a teammate's AI works, inject the relevant verified experiences as context.
6. **See & manage** — dashboards: what I've contributed, whose experience I'm using, and (for the admin/"boss") the health of the whole store.

---

## 4. Glossary (read this once)

| Term | Plain meaning |
|---|---|
| **Experience / Experience Asset** | One unit of captured work-knowledge. The atom of the system. Defined by `schemas/experience_asset.schema.json`. |
| **Connector / ToolConnector** | The adapter that plugs us into one AI tool. Two jobs: *observe* (capture) and *inject* (serve context). |
| **MCP (Model Context Protocol)** | The open standard AI tools use to talk to external tools/data. Our **general connection** rides on it. |
| **MCP Gateway** | A proxy that sits between a user's AI tool and its MCP tools; it passes calls through while logging them (capture) and adding our own tools (recall/store). |
| **SYNAPSE** | A brain-inspired memory that stores experiences as a graph and retrieves by "spreading activation" instead of plain vector search. Our **storage layer**. |
| **Verifier** | The automatic check that decides if an experience is trustworthy. Simple now (LLM-judge / did-it-work); reproducibility for simulation. |
| **Verdict / Status** | `UNVERIFIED → VERIFIED → STALE → RETIRED`. Only VERIFIED experiences are served as trustworthy. |
| **Episodic vs Semantic node** | SYNAPSE terms. *Episodic* = one raw experience. *Semantic* = an abstracted concept synthesized from many experiences ("how to configure X"). |

---

## 5. Architecture — the six layers in detail

### Layer 1 — Connection (the "general connection" question, answered)

**The problem:** we want to connect to *every* AI tool a team might use, without writing custom code for each one.

**The answer:** provide **one general connection** and let users configure a small adapter only for tools that fall outside it.

- **General connection = MCP.** Model Context Protocol is how modern AI tools (Claude Code, Cursor, Claude Desktop, and most agent frameworks) already connect to external tools. We ship two MCP pieces:
  1. **An MCP Gateway (proxy).** The user points their AI tool's MCP config at our gateway instead of directly at their tools. The gateway forwards their normal tool calls untouched, but along the way it (a) **logs every call and result** (that is the automatic capture) and (b) **exposes two extra tools** to the AI: `recall_experience(query)` and (optionally) `store_experience(...)`. It can also **inject** relevant experience into the context before the AI acts.
  2. **An MCP Server.** For teams that don't want a proxy, we run a plain MCP server exposing just `recall_experience` and `store_experience`. The AI calls `recall` on its own initiative. Less automatic, zero setup friction.
- **Long-tail tools = user-configured adapter.** A tool that doesn't speak MCP (a web app, a proprietary IDE, a lab instrument) gets a thin **ToolConnector adapter** the user drops in. The interface is deliberately tiny:

```python
class ToolConnector(Protocol):
    def observe(self) -> Iterable[RawActivity]: ...      # capture: emit raw activity events
    def inject(self, context: list[Experience]) -> None: ...  # serve: push experience into the tool
```

  Concretely, adapters can be: a webhook receiver, a log-file tailer, an IDE/editor plugin, a browser extension, or a wrapper around a CLI (this is exactly how the first simulation adapter works — it wraps the simulation runner).

**So the design rule is:** *We provide the general connection (MCP gateway + server). Users only write an adapter for tools outside the MCP standard, against a 2-method interface.* This is the same "one narrow adapter per tool" pattern used everywhere else in the system, which is what keeps it general.

> Security note: an MCP gateway sees tool traffic, so treat it like any audit proxy — scoped credentials, per-call correlation IDs, and it must honor each experience's `visibility`/`consent` (Section 9). MCP "context poisoning" is a known 2026 risk; verified-only serving is part of the mitigation.

### Layer 2 — Capture (grab information automatically)

Raw activity from Layer 1 is noisy (individual tool calls, outputs, logs). Capture turns a *session or run* into one clean **candidate Experience**:

1. **Collect** the trace (tool calls, inputs/outputs, final result) for a unit of work.
2. **Detect a boundary** — a task finished, a run completed, a session closed, or the user/agent tagged something "good."
3. **Distill** with an LLM (Claude): summarize what was attempted, what worked, what failed, key parameters, and the outcome, into the `Experience Asset` fields.
4. **Emit** a `candidate` Experience (status = candidate, verdict = UNVERIFIED).

Human effort target: **≈ zero.** At most an optional one-line "why it works." If even that blocks people, drop it and back-fill later. Automatic capture is the whole point — the moment capture needs real effort, we are back to the wiki that nobody fills in.

### Layer 3 — Verification (simple now, pluggable forever)

This is what keeps the store from becoming a graveyard. A verifier takes a candidate Experience and returns a verdict.

- **Simple defaults (build these first):**
  - `outcome_signal` — did the task objectively succeed? (tests passed, run completed, user marked good). Cheapest.
  - `llm_judge` — an LLM grades the experience against a short rubric. Cheap, gameable, fine to start.
- **Stronger, per-domain (plug in later):**
  - `rerun_and_compare` — re-run the captured work and check it reproduces within tolerance. **This is the simulation verifier** and the strongest one we have; see `docs/PHASE0_SPEC.md`.
  - `tests_ci` — run the repo's tests for a coding experience.
- **Verdict drives status:** VERIFIED → serveable; REJECTED/STALE/INCONCLUSIVE → not served as trustworthy. A scheduled **re-verify** (`reverify_after_days`) catches rot: an experience that no longer reproduces flips to `stale` automatically.

The verifier is a pluggable interface so the *same* system works in a domain with a strong verifier (simulation) and one with only a weak verifier (general knowledge work):

```python
class Verifier(Protocol):
    def verify(self, exp: Experience) -> Verdict: ...
```

### Layer 4 — Storage (SYNAPSE)

**What SYNAPSE is** ([arXiv 2601.02744](https://arxiv.org/abs/2601.02744)): a memory that stores experiences as a **graph of episodic and semantic nodes** and retrieves by **spreading activation** — a query lights up entry nodes, activation spreads across related nodes, *lateral inhibition* suppresses competing/irrelevant branches, and *temporal decay* fades old memories. It beats plain vector search on multi-hop questions (~+23% accuracy, ~-95% tokens on the LoCoMo benchmark) because relevance *emerges from the network* instead of being a single similarity score.

**How we use it:** each verified Experience becomes an **episodic node**; a background process synthesizes recurring patterns into **semantic nodes** ("the standard way to configure X"). Retrieval (Layer 5) runs spreading activation from the query.

**Practical caveat (important for a hackathon):** as of this writing SYNAPSE's own code is *"available upon acceptance"* and no public repo is confirmed. So we **do not depend on SYNAPSE's code directly.** We define a `MemoryStore` interface and pick an engine behind it:

```python
class MemoryStore(Protocol):
    def write(self, exp: Experience) -> MemoryRefs: ...              # returns episodic/semantic node ids
    def recall(self, query: Query, k: int) -> list[ScoredExperience]: ...
    def reverify_due(self) -> list[Experience]: ...
```

| Engine option | Use when | Notes |
|---|---|---|
| **SYNAPSE (native)** | its code is released and stable | the target; best retrieval |
| **Cognee** (open-source graph+vector semantic memory) | you need something mature *today* | closest mature stand-in; graph + vector |
| **Neo4j + Qdrant + our own spreading-activation-lite** | you want full control | ~200 lines to approximate activation over a graph |
| **Easybase** (the author's existing BM25 store) | baseline / comparison only | works, but "old"; use to benchmark against SYNAPSE |

Building against `MemoryStore` means you can start on Cognee this weekend and swap in SYNAPSE later with no changes above the interface.

**Multi-tenancy lives here too:** every node carries `actor` and `visibility`. Recall must filter by "can this consumer see this experience?" before activation even starts.

### Layer 5 — Serving (context for the colleague's AI)

When a teammate's AI is about to work, it (or the gateway on its behalf) calls `recall_experience(query)`. We:

1. Build a query from the teammate's current task/context.
2. Run SYNAPSE spreading-activation recall, **filtered to what this person is allowed to see and to `verified`, non-stale** experiences.
3. Return each hit **with its receipt**: whose experience it is (`actor`), when, the verdict, freshness, and provenance.
4. Record the consumption in `usage.served_to` — this is what powers "whose experiences am I using."

The colleague's AI now works *with* Sarah's verified experience in context, and Sarah gets attribution.

### Layer 6 — Presentation (the three pages you asked for)

All three are simple web pages over the same API.

**A. User dashboard — "my experience."** For every team member.
```
┌─ My Experience ─────────────────────────────────────────────┐
│  Experiences I've contributed:      42   (37 verified, 5 stale)│
│  Times my experience helped others: 118                       │
│  ▁▂▅▇▆▃  contributions over time                              │
│                                                               │
│  Whose experience I'm using:                                  │
│   • Sarah  ▇▇▇▇▇▇  61%   (simulation configs)                 │
│   • Tom    ▇▇▇     24%   (environment setup)                  │
│   • Mei    ▇▇      15%   (data provenance)                    │
└───────────────────────────────────────────────────────────────┘
```
Two questions answered directly: *how many experiences have I conducted* (contributed) and *whose experiences am I using* (consumption, attributed).

**B. Team / discovery view.** Browse and search experiences; see *who-knows-what* (which teammate is the source of experience in each area) — the "who to ask" map that is often more valuable than any document.

**C. Admin / "boss" dashboard — storage management.** For the team lead.
```
┌─ Storage & Health (Admin) ──────────────────────────────────┐
│  Total experiences: 1,204   Verified 71% · Candidate 18% ·   │
│                             Stale 9% · Retired 2%             │
│  Storage engine: SYNAPSE   Nodes 3,880   Semantic 412        │
│  Re-verify queue: 63 due   ·  Avg verify latency 4.2s        │
│                                                               │
│  Contribution by member:  Sarah 210 · Tom 180 · ...          │
│  Access / visibility:  private 12% · team 74% · org 14%      │
│  Cost this month:  $__   ·  [Purge stale] [Export] [Roles]   │
└───────────────────────────────────────────────────────────────┘
```
The admin sees and *manages the data store*: verification health, rot queue, per-member contribution, access controls, retention, and cost.

---

## 6. The data model

The core is **`schemas/experience_asset.schema.json`** — deliberately *tool-agnostic*. Anything domain-specific (simulation metrics, code diffs) goes under `domain_extension`, which for simulation points at **`schemas/simulation_experience_asset.schema.json`**. Key design choices:

- **The claim is separated from the story.** Machine-checkable fields (`outcome`, `domain_extension` metrics) are what the verifier tests; `content.rationale` *explains* but never *certifies*. This is the line a retrieve-only product cannot draw.
- **Attribution & consumption are first-class** (`actor`, `usage.served_to`) — the dashboards are just views over these.
- **Permissions & consent are first-class** (`visibility.scope`, `visibility.consent`) — capture and serving both honor them.
- **Rot is a state, not a guess** (`status`, `verification.reverify_after_days`).

---

## 7. Technology stack (specific, hackathon-optimized)

Pick mature, boring, well-documented pieces. Do **not** hand-roll storage, protocol, or auth.

| Layer | Choice | Why |
|---|---|---|
| Connection | **MCP** — official Python (`mcp`) / TypeScript SDKs; gateway = a thin proxy | industry standard; every major AI tool already speaks it |
| Capture distillation | **Claude API** (`claude-opus-4-8` / `claude-sonnet-5`) | strong summarization of traces into structured JSON |
| Storage | **Cognee** now → **SYNAPSE** when released, behind a `MemoryStore` interface | mature today, upgradeable; never blocked |
| Verifier | plain Python; `llm_judge` via Claude; `rerun_and_compare` wraps the sim runner | simple now, pluggable |
| Backend/API | **FastAPI** (Python) | matches the simulation/scientific ecosystem; fast to build |
| App metadata DB | **Postgres** (or SQLite for the demo) | boring and reliable |
| Frontend | **Next.js + React + Tailwind** | quickest path to three clean dashboards |
| Auth / tenancy | a managed auth provider (e.g. Clerk/Auth0) or simple JWT for the demo | don't build auth during a hackathon |

Everything the author already has (iDynoMiCS 2, Simtool, ManageSim, Easybase) is **optional reference material or the first test workflow — not required infrastructure.**

---

## 8. Build plan from an empty folder

Order matters: each milestone is independently demoable and de-risks the next. Rough hackathon slicing in brackets.

- **M0 — Skeleton [hour 0–1].** Create the repo layout (Section 10). Stand up FastAPI with a `/health` route and an empty Next.js app.
- **M1 — Data model + store interface [1–3].** Implement the `Experience` model from the schema. Implement `MemoryStore` with a **Cognee** (or SQLite+embedding) backend. Prove: write an experience, recall it by query.
- **M2 — The general connection [3–6].** Stand up the MCP server exposing `recall_experience` and `store_experience`. Then the MCP gateway that proxies + logs. Prove: point Claude Code / Cursor at it, watch a tool call get captured.
- **M3 — Capture [6–9].** The distiller: turn a captured trace into a candidate Experience via Claude. Prove: a real session becomes a clean Experience with ~0 human effort.
- **M4 — Verify [9–11].** Implement `outcome_signal` + `llm_judge`. Wire verdict → status. Prove: a good experience becomes VERIFIED, a bad one gets REJECTED.
- **M5 — Serve end-to-end [11–14].** Recall filtered to verified + visible, returned with receipts, consumption recorded. Prove: a *second* user's AI receives the *first* user's verified experience as context.
- **M6 — Dashboards [14–20].** The three pages (user / team / admin) over the API.
- **M7 — First real workflow [20–24].** Plug in the **simulation** adapter and the `rerun_and_compare` verifier (Section 9 / `PHASE0_SPEC.md`) so at least one experience type is verified by true reproducibility, not just an LLM judge. This is the credibility demo.

**The falsification test to run at the end:** capture one experience automatically from user A, have user B's AI recall it, confirm it is correct and actually gets reused. If capture needed real effort, or the experience didn't hold up for B, the core loop needs rethinking before adding more tools.

---

## 9. The first test workflow (concrete instance #1)

To prove the loop with a *strong* verifier, the first plugged-in workflow is a computational **simulation** (the author's iDynoMiCS 2 *Postia placenta* work). It is one instance of the general system:

- **Connector:** a `ToolConnector` wrapping the simulation runner (`observe` = watch a run to completion; `inject` = hand a prior config to a new run).
- **Experience:** a converged simulation config + environment + the reason it works, captured automatically when a run is judged good.
- **Verifier:** `rerun_and_compare` — re-run it and check it reproduces within tolerance. This is the strongest verifier we have and the reason to start here: **correctness is machine-checkable for free.** Full detail in `docs/PHASE0_SPEC.md` and `schemas/simulation_experience_asset.schema.json`.

Once this instance works, generalizing = *add another connector + pick that domain's verifier*. Nothing else in Layers 2–6 changes.

---

## 10. Suggested repo layout

```
Org_system/
├── docs/
│   ├── SYSTEM_DESIGN_AND_BUILD_REPORT.md   ← this file
│   └── PHASE0_SPEC.md                        ← the simulation instance (strong-verifier proof)
├── schemas/
│   ├── experience_asset.schema.json          ← the general data model
│   └── simulation_experience_asset.schema.json ← simulation domain extension
├── examples/
│   └── postia_converged_config.sea.json
├── connectors/          # Layer 1: MCP gateway, MCP server, ToolConnector adapters
│   ├── mcp_server/
│   ├── mcp_gateway/
│   └── adapters/idynomics2/
├── capture/             # Layer 2: trace collection + LLM distillation
├── verify/              # Layer 3: outcome_signal, llm_judge, rerun_and_compare
├── memory/              # Layer 4: MemoryStore interface + cognee/synapse backends
├── serve/               # Layer 5: recall API, filtering, receipts, usage logging
├── api/                 # FastAPI app tying layers together
├── web/                 # Layer 6: Next.js dashboards (user / team / admin)
└── README.md
```

---

## 11. How to generalize after the test (the whole point)

The system is general by construction. To onboard a new tool or workflow you touch exactly two small things:

1. **A connector** — if the tool speaks MCP, none (it just works through the gateway). If not, one `ToolConnector` adapter (2 methods).
2. **A verifier choice** — pick the strongest verifier that domain affords (`tests_ci` for code, `rerun_and_compare` for simulation, `outcome_signal`/`llm_judge` for judgment work).

Layers 2 (capture), 4 (storage/SYNAPSE), 5 (serving), and 6 (dashboards) are **unchanged** across every tool and workflow. That is the design's core promise: *prove one workflow, then scale by adding thin adapters, never by rebuilding the middle.*

---

## 12. Risks & open decisions

- **SYNAPSE code availability.** Not confirmed public yet → build on the `MemoryStore` interface with Cognee as the working backend; treat SYNAPSE as a hot-swap upgrade.
- **Weak verifiers get gamed.** `llm_judge` is cheap and gameable. Keep the strong (`rerun_and_compare`, `tests_ci`) verifiers as the trust anchor; use weak ones only where nothing better exists.
- **Consent / surveillance.** Capturing real work is sensitive. Make capture scoped, inspectable, and opt-in (`visibility.consent`); the admin dashboard must show exactly what is captured and served.
- **MCP context poisoning.** Serving experience *into* an AI's context is an injection surface. Mitigate with verified-only serving, provenance receipts, and gateway-side sanitization.
- **Attribution fairness.** Contribution/consumption stats create incentives; decide early whether they are private, team-visible, or gamified — it changes behavior.

---

## 13. Sources

- SYNAPSE — Empowering LLM Agents with Episodic-Semantic Memory via Spreading Activation: https://arxiv.org/abs/2601.02744
- HippoRAG — Neurobiologically Inspired Long-Term Memory for LLMs (background on brain-inspired memory): https://arxiv.org/abs/2405.14831
- Model Context Protocol (overview): https://en.wikipedia.org/wiki/Model_Context_Protocol
- Cognee (open-source semantic memory layer): https://github.com/topoteretes/cognee
- Auditing MCP server access & activity logs (capture pattern): https://tyk.io/learning-center/how-to-audit-mcp-server-access-activity-logs/

---

*Bottom line for a newcomer: build the six-box loop — Connect (MCP) → Capture (auto-distill) → Verify (simple, pluggable) → Store (SYNAPSE, via a swappable interface) → Serve (to teammates' AI, with receipts) → See/Manage (three dashboards). Prove it on one simulation workflow where correctness is free to check, then scale to any tool by adding a thin adapter and picking that domain's verifier. The storage and retrieval are commodity; the verifier and the automatic capture are the product.*
